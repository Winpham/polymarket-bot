#!/usr/bin/env python3
"""US-VENUE MID TAPE — the true-mid + near-touch-depth series. READ-ONLY. Never trades.

WHY (short version; the long one is in migrations/047_us_mid_tape.sql)
---------------------------------------------------------------------
To decide take-vs-make on US we must measure ADVERSE SELECTION: how far fair value moves against
a maker after their fill. That is a MARKOUT, and an honest markout is measured against the MID.
Computing it from subsequent TRADE PRICES instead would bake in the bid-ask bounce and report the
half-spread as profit -- making every maker look good no matter how hard they are picked off (the
error class behind the retracted "+4.8% maker-copy"). 043 gives fills; this gives the mid.

It also records depth NEAR THE TOUCH, which is the pro-rata denominator of the venue's Liquidity
Incentive Program (reward = f(price-proximity, size) / sum over all resting competitors). Without
it, any reward number is the published schedule, not realized income.

SCOPE (why this isn't the firehose)
-----------------------------------
Venue-wide MARKET_DATA is ~733 msg/s, ~241/s of which move the BBO (~21M rows/day) over 8,682
markets. We don't need that. A markout only needs a mid where trades actually HAPPEN (measured:
~180 distinct markets trade per 5-min window), and the reward model only needs the incentive-pool
families. So we persist exactly two sets:

  track_reason='traded' -- rolling active set, fed by the TRADE stream on the SAME socket family.
                           A slug stays tracked for ACTIVE_WINDOW_S after its last print, which
                           must exceed the longest markout horizon (else the markout has no mid to
                           land on -- the window is derived from MARKOUT_MAX_S, not guessed).
  track_reason='pool'   -- the reward universe READ from the venue's public incentives endpoint
                           (richest markets by POOL PER MARKET), tracked even while idle, because
                           the liquidity reward pays for RESTING, not for filling.

DEFAULT-OFF, by construction: no committed launch unit. Starting it is an operational act.

Usage:
    python3 scripts/us_mid_tape.py                  # run forever (reconnect w/ backoff)
    python3 scripts/us_mid_tape.py --duration 300   # bounded capture
    python3 scripts/us_mid_tape.py --apply-only     # ensure schema, exit
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

try:
    import websockets
except ImportError:
    sys.exit("us_mid_tape: `pip install websockets` required")

WS_URL = os.environ.get(
    "US_WS_URL", "wss://gateway-ws-markets.polymarket.us/v1/ws/subscriptions")
PG_DSN = os.environ.get(
    "ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
UA = os.environ.get(
    "US_WS_UA", "polymarket-bot-research/1.0 (KYC customer; tue.w.pham@gmail.com)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_MIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "migrations", "047_us_mid_tape.sql")

# The longest markout horizon we intend to measure. The active-tracking window is DERIVED from it
# (with headroom) so that every fill has mid coverage out to its full horizon. Raising the markout
# horizon without raising the window would silently truncate the tail of the measurement.
MARKOUT_MAX_S = 300
ACTIVE_WINDOW_S = MARKOUT_MAX_S + 120      # keep a slug tracked ~7 min past its last print

# The 'pool' universe is not guessed from slug tokens — it is READ from the venue's own public
# incentives endpoint (us_incentives.top_reward_slugs), ranked by POOL PER MARKET. Guessing by
# token would have tracked 1,172 PGA markets paying $13 each while missing that the entire World
# Cup moneyline pool ($24,700) sits on just 6 markets. Refreshed periodically: pools open, close,
# and re-fund per period, so a universe pinned at process start goes stale within the day.
POOL_UNIVERSE_N = 300
POOL_REFRESH_S = 900

# Write policy, per track_reason. These are NOT symmetric, and the asymmetry is the point:
#
#   'traded' is the MARKOUT universe -- the measurement the whole run turns on. It is never
#   capped and never starved: a markout needs the touch as it stood at the fill, so it gets
#   sub-second resolution. (Measured: only ~180 markets trade per 5-min window, so this is cheap.)
#
#   'pool' exists only to size the PRO-RATA DENOMINATOR of the liquidity reward -- competing
#   resting depth, which moves slowly. It needs a representative series, not a tick series, so it
#   is sampled coarsely and capped. An earlier build let pool slugs fill a shared cap FIRST and
#   silently evict traded slugs, which would have quietly truncated the crux measurement while
#   still looking like it was recording fine. Hence: separate budgets, traded uncapped.
TRADED_WRITE_INTERVAL_S = 0.5    # 2 Hz per market: finer than the shortest markout horizon (1s)
POOL_WRITE_INTERVAL_S = 5.0      # resting depth is slow-moving; 5s is plenty to model a share
MAX_POOL_TRACKED = 400           # bound on pool slugs (traded slugs are NEVER capped)
BATCH_MAX = 500
BATCH_SECS = 2.0


def ensure_schema(con) -> None:
    with open(_MIG) as f:
        sql = f.read()
    with con.cursor() as cur:
        cur.execute(sql)
    con.commit()


def _f(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _levels(side):
    """[{px:{value},qty}] -> sorted [(price, qty)]. Tolerant of missing/blank."""
    out = []
    for lv in side or []:
        p = _f((lv.get("px") or {}).get("value"))
        q = _f(lv.get("qty"))
        if p is not None and q is not None:
            out.append((p, q))
    return out


def _depth_within(levels, mid, cents):
    """Resting size within `cents` of mid. The pro-rata denominator of the reward model."""
    if mid is None:
        return None
    lim = cents / 100.0
    return sum(q for p, q in levels if abs(p - mid) <= lim + 1e-9)


def _row(md, reason):
    slug = md.get("marketSlug")
    tt = md.get("transactTime")
    if not slug or not tt:
        return None

    bids = sorted(_levels(md.get("bids")), key=lambda x: -x[0])    # best bid = highest
    asks = sorted(_levels(md.get("offers")), key=lambda x: x[0])   # best ask = lowest

    bb, bbq = (bids[0] if bids else (None, None))
    ba, baq = (asks[0] if asks else (None, None))
    # A one-sided book has no mid. Store the row anyway (its one-sidedness is a fact about
    # whether a maker can even reference a fair value there) but leave mid/spread/depth NULL.
    mid = (bb + ba) / 2.0 if (bb is not None and ba is not None) else None
    spread = (ba - bb) if (bb is not None and ba is not None) else None

    st = md.get("stats") or {}

    def sv(k):
        return _f((st.get(k) or {}).get("value")) if isinstance(st.get(k), dict) else _f(st.get(k))

    return (
        slug, bb, bbq, ba, baq, mid, spread,
        _depth_within(bids, mid, 1), _depth_within(bids, mid, 2), _depth_within(bids, mid, 5),
        _depth_within(asks, mid, 1), _depth_within(asks, mid, 2), _depth_within(asks, mid, 5),
        sum(q for _, q in bids) or None, sum(q for _, q in asks) or None,
        _f(st.get("openInterest")), _f(st.get("sharesTraded")),
        sv("notionalTraded"), sv("lastTradePx"),
        md.get("state"), reason, tt,
    )


_INSERT = """
    INSERT INTO us_mid_tape
        (us_slug, best_bid, best_bid_qty, best_ask, best_ask_qty, mid, spread,
         bid_qty_1c, bid_qty_2c, bid_qty_5c, ask_qty_1c, ask_qty_2c, ask_qty_5c,
         bid_qty_total, ask_qty_total,
         open_interest, shares_traded, notional_traded, last_trade_px,
         state, track_reason, transact_time)
    VALUES %s
    ON CONFLICT DO NOTHING
"""


def flush(con, rows):
    if not rows:
        return 0
    with con.cursor() as cur:
        execute_values(cur, _INSERT, rows, page_size=BATCH_MAX)
        n = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    con.commit()
    return n


async def pool_universe_refresher(pool_universe, stats):
    """Keep the reward universe fresh from the venue's public incentives endpoint."""
    import us_incentives
    while True:
        try:
            slugs = await asyncio.get_event_loop().run_in_executor(
                None, lambda: set(us_incentives.top_reward_slugs(POOL_UNIVERSE_N)))
            if slugs:
                pool_universe.clear()
                pool_universe.update(slugs)
                print(f"  reward universe refreshed: {len(pool_universe)} slugs", flush=True)
        except Exception as e:                                   # noqa: BLE001
            stats["errors"] += 1
            print(f"  reward-universe refresh failed: {type(e).__name__}", flush=True)
        await asyncio.sleep(POOL_REFRESH_S)


async def trade_watcher(active, stats):
    """TRADE stream -> rolling active set. This process does NOT write trades (us_tape_ingest.py
    owns 043); it only learns WHICH markets are live so the mid writer can scope itself."""
    while True:
        try:
            async with websockets.connect(
                    WS_URL, additional_headers={"User-Agent": UA},
                    open_timeout=15, ping_interval=20, ping_timeout=20, max_size=None) as ws:
                await ws.send(json.dumps({"subscribe": {
                    "requestId": "mid-active", "subscriptionType": "SUBSCRIPTION_TYPE_TRADE",
                    "marketSlugs": []}}))
                print(f"{datetime.now(timezone.utc):%H:%M:%S} active-set watcher on TRADE stream",
                      flush=True)
                async for msg in ws:
                    try:
                        tr = (json.loads(msg) or {}).get("trade")
                    except ValueError:
                        continue
                    if tr and tr.get("marketSlug"):
                        active[tr["marketSlug"]] = time.time()
        except Exception as e:                                   # noqa: BLE001 - keep the tape alive
            stats["trade_reconnects"] += 1
            print(f"  active-watcher reconnect: {type(e).__name__}", flush=True)
            await asyncio.sleep(3)


async def book_writer(con, active, pool_universe, stop_at, stats):
    """MARKET_DATA stream -> persist BBO+depth for tracked slugs, on CHANGE only."""
    last_bbo, last_write, pool_slugs = {}, {}, set()
    backoff = 1.0
    while True:
        if stop_at and time.time() >= stop_at:
            return
        try:
            async with websockets.connect(
                    WS_URL, additional_headers={"User-Agent": UA},
                    open_timeout=15, ping_interval=20, ping_timeout=20, max_size=None) as ws:
                await ws.send(json.dumps({"subscribe": {
                    "requestId": "mid", "subscriptionType": "SUBSCRIPTION_TYPE_MARKET_DATA",
                    "marketSlugs": []}}))
                stats["connects"] += 1
                print(f"{datetime.now(timezone.utc):%H:%M:%S} connected -> venue-wide MARKET_DATA",
                      flush=True)
                backoff = 1.0
                buf, last_flush = [], time.time()
                while True:
                    if stop_at and time.time() >= stop_at:
                        stats["written"] += flush(con, buf)
                        return
                    timeout = BATCH_SECS if buf else 30
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        if buf:
                            stats["written"] += flush(con, buf)
                            buf, last_flush = [], time.time()
                        continue
                    try:
                        md = (json.loads(msg) or {}).get("marketData")
                    except ValueError:
                        continue
                    if not md:
                        continue
                    stats["seen"] += 1
                    slug = md.get("marketSlug")
                    if not slug:
                        continue

                    now = time.time()
                    bids = sorted(_levels(md.get("bids")), key=lambda x: -x[0])
                    asks = sorted(_levels(md.get("offers")), key=lambda x: x[0])

                    # SCOPE. 'traded' wins whenever the slug is in the rolling active set -- it is
                    # the markout universe and is never capped or evicted. 'pool' is a fallback,
                    # and only for a market we could plausibly rest in: open, two-sided, and with
                    # real volume (a zero-volume pool market is a dead future).
                    if (now - active.get(slug, 0)) <= ACTIVE_WINDOW_S:
                        reason, interval = "traded", TRADED_WRITE_INTERVAL_S
                    elif (slug in pool_universe and bids and asks
                            and md.get("state") == "MARKET_STATE_OPEN"):
                        if slug not in pool_slugs and len(pool_slugs) >= MAX_POOL_TRACKED:
                            stats["capped"] += 1
                            continue
                        pool_slugs.add(slug)
                        reason, interval = "pool", POOL_WRITE_INTERVAL_S
                    else:
                        continue

                    key = (bids[0] if bids else None, asks[0] if asks else None)
                    if last_bbo.get(slug) == key:          # BBO unchanged -> nothing to record
                        stats["nochange"] += 1
                        continue
                    if now - last_write.get(slug, 0) < interval:
                        stats["throttled"] += 1
                        continue
                    last_bbo[slug] = key
                    last_write[slug] = now

                    r = _row(md, reason)
                    if r:
                        buf.append(r)
                        stats[reason] += 1
                    if len(buf) >= BATCH_MAX or (time.time() - last_flush) >= BATCH_SECS:
                        stats["written"] += flush(con, buf)
                        buf, last_flush = [], time.time()
        except Exception as e:                                   # noqa: BLE001
            con.rollback()
            stats["errors"] += 1
            print(f"  book-writer reconnect after {type(e).__name__}: {str(e)[:90]} "
                  f"(backoff {backoff:.0f}s)", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def reporter(active, stats, t0):
    while True:
        await asyncio.sleep(60)
        dt = time.time() - t0
        print(f"  [{dt/60:5.1f}m] tracked={len(active)} written={stats['written']} "
              f"traded={stats['traded']} pool={stats['pool']} nochange={stats['nochange']} "
              f"throttled={stats['throttled']} errors={stats['errors']}", flush=True)


async def main_async(duration):
    con = psycopg2.connect(PG_DSN)
    ensure_schema(con)
    stop_at = (time.time() + duration) if duration else None
    active, t0 = {}, time.time()
    stats = {"connects": 0, "seen": 0, "written": 0, "traded": 0, "pool": 0,
             "nochange": 0, "throttled": 0, "capped": 0, "errors": 0, "trade_reconnects": 0}

    pool_universe = set()
    tasks = [asyncio.create_task(trade_watcher(active, stats)),
             asyncio.create_task(pool_universe_refresher(pool_universe, stats)),
             asyncio.create_task(reporter(active, stats, t0))]
    await asyncio.sleep(2)          # let the reward universe land before the first book messages
    try:
        await book_writer(con, active, pool_universe, stop_at, stats)
    finally:
        for t in tasks:
            t.cancel()
        dt = time.time() - t0
        print(f"\n=== us_mid_tape summary ({dt:.0f}s) ===", flush=True)
        print(f"  seen={stats['seen']} written={stats['written']} "
              f"(traded={stats['traded']} pool={stats['pool']}) "
              f"nochange={stats['nochange']} throttled={stats['throttled']} "
              f"capped={stats['capped']} errors={stats['errors']}", flush=True)
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=0, help="seconds then exit (0 = forever)")
    ap.add_argument("--apply-only", action="store_true", help="ensure schema and exit")
    a = ap.parse_args()
    if a.apply_only:
        con = psycopg2.connect(PG_DSN)
        ensure_schema(con)
        con.close()
        print("us_mid_tape schema applied.", flush=True)
        return
    asyncio.run(main_async(a.duration))


if __name__ == "__main__":
    main()
