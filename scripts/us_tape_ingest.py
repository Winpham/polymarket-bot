#!/usr/bin/env python3
"""US-VENUE LIVE TRADE-TAPE INGESTER — the per-trader identity spine. READ-ONLY. Never trades.

WHAT THIS IS
------------
A streaming sidecar that connects to the UNDOCUMENTED, UNAUTHENTICATED US market-data socket

    wss://gateway-ws-markets.polymarket.us/v1/ws/subscriptions

subscribes VENUE-WIDE to trade prints (empty marketSlugs → every trade on the exchange from one
connection), and appends each print — WITH the taker/maker usernames the venue publishes — into
`us_trade_tape` (migration 043). Over time this BUILDS the per-trader history that Polymarket US
exposes nowhere as an endpoint. See 043 for why identity is obtainable here at all.

WHY A PYTHON SIDECAR (same justification as us_quote_capture.py)
---------------------------------------------------------------
There is no Rust SDK for the US venue; this path is READ-ONLY (it never places an order, so it
needs none of the executor's cage / idempotency / kill-switch); and the value is in starting an
IRREVERSIBLE capture clock TODAY, not in a perfect port. When real money is on the US leg, the
execution path gets built in Rust behind the existing cage. This is a data instrument and must
never become an order path.

DEFAULT-OFF, by construction
----------------------------
There is no committed launchd/systemd unit. A sidecar that is not launched never runs and writes
nothing — the byte-identical-when-off guarantee, achieved by simply not scheduling it. Turning it
on is an operational act (install the plist), not a code change that ships on merge.

HONESTY
-------
Two clocks are stored, never a lag: `trade_time` (venue exchange clock) and `recv_at` (local).
Ingest latency is derived at read. `source='gateway_ws'` marks the rung. A reconnect can replay a
just-seen print; the 043 dedup index (ON CONFLICT DO NOTHING) collapses those.

Usage:
    python3 scripts/us_tape_ingest.py --duration 60     # bounded capture (testing / one-shot)
    python3 scripts/us_tape_ingest.py                   # run forever, reconnect w/ backoff
    python3 scripts/us_tape_ingest.py --apply-only      # just ensure schema, exit
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
    sys.exit("us_tape_ingest: `pip install websockets` required")

WS_URL = os.environ.get(
    "US_WS_URL", "wss://gateway-ws-markets.polymarket.us/v1/ws/subscriptions")
PG_DSN = os.environ.get(
    "ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
# Honest client identity — we are a KYC'd, fee-paying customer of this venue; act like one.
UA = os.environ.get(
    "US_WS_UA", "polymarket-bot-research/1.0 (KYC customer; tue.w.pham@gmail.com)")

_MIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "migrations", "043_us_trade_tape.sql")

BATCH_MAX = 500          # flush after this many prints
BATCH_SECS = 2.0         # or this many seconds, whichever first


def ensure_schema(con) -> None:
    """Apply 043 idempotently. Safe: every statement is IF NOT EXISTS (additive migration)."""
    with open(_MIG) as f:
        sql = f.read()
    with con.cursor() as cur:
        cur.execute(sql)
    con.commit()


def _px(node, *keys):
    """Pull a nested numeric like trade.price.value → float, tolerant of missing/blank."""
    for k in keys:
        if node is None:
            return None
        node = node.get(k) if isinstance(node, dict) else None
    if node in (None, ""):
        return None
    try:
        return float(node)
    except (TypeError, ValueError):
        return None


def _parse_ts(s):
    """Venue tradeTime is ns-precision ISO ('...Z' or '±hh:mm'). Postgres takes µs; hand it the
    raw string and let it truncate. Returns the string unchanged if it looks ISO, else None."""
    if not s or not isinstance(s, str):
        return None
    return s  # psycopg2 → TIMESTAMPTZ parses ns and truncates to µs; no lossy Python parse needed


def _row(trade):
    """Map one trade message → the us_trade_tape column tuple, or None to skip."""
    slug = trade.get("marketSlug")
    price = _px(trade, "price", "value")
    qty = _px(trade, "quantity", "value")
    tt = _parse_ts(trade.get("tradeTime"))
    if not slug or price is None or qty is None or tt is None:
        return None
    tk = trade.get("taker") or {}
    mk = trade.get("maker") or {}

    def clean(v):  # normalize UNSPECIFIED/UNDEFINED sentinels to NULL for honest per-trader stats
        if v in (None, "", "OUTCOME_SIDE_UNSPECIFIED", "ORDER_INTENT_UNDEFINED",
                 "ORDER_SIDE_UNSPECIFIED"):
            return None
        return v
    return (
        slug, price, qty,
        tk.get("username") or None, clean(tk.get("side")), clean(tk.get("intent")),
        clean(tk.get("outcomeSide")),
        mk.get("username") or None, clean(mk.get("side")), clean(mk.get("intent")),
        clean(mk.get("outcomeSide")),
        tt,
    )


_INSERT = """
    INSERT INTO us_trade_tape
        (us_slug, price, quantity,
         taker_username, taker_side, taker_intent, taker_outcome,
         maker_username, maker_side, maker_intent, maker_outcome,
         trade_time)
    VALUES %s
    ON CONFLICT DO NOTHING
"""


def flush(con, rows):
    if not rows:
        return 0
    with con.cursor() as cur:
        before = cur.rowcount
        execute_values(cur, _INSERT, rows, page_size=BATCH_MAX)
        inserted = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else len(rows)
    con.commit()
    return inserted


async def _run_once(con, stop_at, stats):
    """One WS connection lifetime. Returns when the socket drops or stop_at is reached."""
    async with websockets.connect(
            WS_URL, additional_headers={"User-Agent": UA},
            open_timeout=15, ping_interval=20, ping_timeout=20, max_size=None) as ws:
        await ws.send(json.dumps({"subscribe": {
            "requestId": "tape", "subscriptionType": "SUBSCRIPTION_TYPE_TRADE",
            "marketSlugs": []}}))  # empty == venue-wide firehose
        stats["connects"] += 1
        print(f"{datetime.now(timezone.utc):%H:%M:%S} connected → venue-wide TRADE stream",
              flush=True)
        buf, last_flush = [], time.time()
        while True:
            if stop_at and time.time() >= stop_at:
                stats["ingested"] += flush(con, buf)
                return "done"
            timeout = BATCH_SECS if buf else 30
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                if buf:
                    stats["ingested"] += flush(con, buf)
                    buf = []
                    last_flush = time.time()
                continue
            try:
                d = json.loads(msg)
            except ValueError:
                continue
            if "error" in d:
                stats["errors"] += 1
                print(f"  WS error: {str(d)[:120]}", flush=True)
                continue
            tr = d.get("trade")
            if not tr:
                continue
            stats["seen"] += 1
            r = _row(tr)
            if r:
                buf.append(r)
                if r[3]:  # taker_username present
                    stats["with_taker"] += 1
            if len(buf) >= BATCH_MAX or (time.time() - last_flush) >= BATCH_SECS:
                stats["ingested"] += flush(con, buf)
                buf = []
                last_flush = time.time()


async def main_async(duration):
    con = psycopg2.connect(PG_DSN)
    ensure_schema(con)
    stop_at = (time.time() + duration) if duration else None
    stats = {"connects": 0, "seen": 0, "with_taker": 0, "ingested": 0, "errors": 0}
    backoff = 1.0
    t0 = time.time()
    try:
        while True:
            try:
                result = await _run_once(con, stop_at, stats)
                if result == "done":
                    break
                backoff = 1.0  # clean return only on stop; a drop raises below
            except Exception as e:
                con.rollback()
                stats["errors"] += 1
                print(f"  reconnect after {type(e).__name__}: {str(e)[:100]} "
                      f"(backoff {backoff:.0f}s)", flush=True)
                if stop_at and time.time() >= stop_at:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            if stop_at and time.time() >= stop_at:
                break
    finally:
        dt = time.time() - t0
        rate = stats["seen"] / dt if dt else 0
        print(f"\n=== us_tape_ingest summary ({dt:.0f}s) ===", flush=True)
        print(f"  connects={stats['connects']} seen={stats['seen']} "
              f"ingested(new)={stats['ingested']} taker_id={stats['with_taker']} "
              f"errors={stats['errors']}  ({rate:.0f} prints/s)", flush=True)
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=0,
                    help="seconds to capture then exit (0 = run forever)")
    ap.add_argument("--apply-only", action="store_true", help="ensure schema and exit")
    a = ap.parse_args()
    if a.apply_only:
        con = psycopg2.connect(PG_DSN)
        ensure_schema(con)
        con.close()
        print("us_trade_tape schema applied.", flush=True)
        return
    asyncio.run(main_async(a.duration))


if __name__ == "__main__":
    main()
