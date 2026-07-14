#!/usr/bin/env python3
"""US-VENUE BOOK-DEPTH SAMPLER — time-of-day depth series for our arms' families. READ-ONLY.

Answers "can the US book fill a $50 / $250 clip in the families we trade?" WITH a time-of-day
control the one-shot snapshot lacked. Each sweep:
  1. Discovers currently-ACTIVE markets + their mid via a short venue-wide LITE stream pull
     (only active markets stream, so this is a clean active-set discovery — no 223k-market page).
  2. Classifies each into a family: 'weather' (tc-temp* slug) or 'favorite' (mid in 0.71-0.98,
     our champion cell) — plus an optional random 'other' control sample.
  3. Fetches the FULL public /book for the target set and stores the decision-relevant depth
     summary (BBO, spread, touch/full depth, $50 & $250 fill/slip) into us_book_tape (migration 045).

Public gateway, unauthenticated, ≤12 concurrent — well under the 20 rps/IP limit. Never trades.

Usage:
    python3 scripts/us_book_sampler.py --once                # one sweep
    python3 scripts/us_book_sampler.py --loop 900            # every 15 min (time-of-day series)
    python3 scripts/us_book_sampler.py --once --other 100    # + 100 random control markets
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import psycopg2
from psycopg2.extras import execute_values

try:
    import websockets
except ImportError:
    sys.exit("us_book_sampler: `pip install websockets` required")

GW = os.environ.get("US_GATEWAY", "https://gateway.polymarket.us")
WS_URL = os.environ.get("US_WS_URL", "wss://gateway-ws-markets.polymarket.us/v1/ws/subscriptions")
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
UA = os.environ.get("US_WS_UA", "polymarket-bot-research/1.0 (KYC customer; tue.w.pham@gmail.com)")
_MIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "migrations", "045_us_book_tape.sql")

FAV_LO, FAV_HI = 0.71, 0.98      # the champion favorite band ([[project-polymarket-cell-scan]])
DISCOVERY_SECS = 8


def ensure_schema(con):
    with open(_MIG) as f:
        con.cursor().execute(f.read())
    con.commit()


async def discover(seconds=DISCOVERY_SECS):
    """Short LITE pull → {slug: mid} for currently-active markets (only active markets stream)."""
    mids = {}
    async with websockets.connect(WS_URL, additional_headers={"User-Agent": UA},
                                  open_timeout=12, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"subscribe": {
            "requestId": "disc", "subscriptionType": "SUBSCRIPTION_TYPE_MARKET_DATA_LITE",
            "marketSlugs": []}}))
        t0 = time.time()
        while time.time() - t0 < seconds:
            try:
                m = await asyncio.wait_for(ws.recv(), timeout=seconds)
            except asyncio.TimeoutError:
                break
            md = json.loads(m).get("marketDataLite")
            if not md:
                continue
            slug = md.get("marketSlug")
            bb = _val(md.get("bestBid")); ba = _val(md.get("bestAsk"))
            if slug and bb is not None and ba is not None:
                mids[slug] = (bb + ba) / 2.0
    return mids


def _val(node):
    if not isinstance(node, dict):
        return None
    v = node.get("value")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify(slug, mid, want_other):
    if slug.startswith("tc-temp"):
        return "weather"
    if mid is not None and FAV_LO <= mid <= FAV_HI:
        return "favorite"
    return "other" if want_other else None


def get_book(slug):
    try:
        r = urllib.request.Request(f"{GW}/v1/markets/{slug}/book", headers={"User-Agent": UA})
        with urllib.request.urlopen(r, timeout=20) as resp:
            return slug, json.load(resp).get("marketData") or {}
    except Exception:
        return slug, None


def _levels(side):
    out = []
    for l in side or []:
        p = _val(l.get("px")); q = l.get("qty")
        try:
            q = float(q)
        except (TypeError, ValueError):
            q = None
        if p and p > 0 and q:
            out.append((p, q))
    return out


def _fill(asks, dollars):
    """Walk asks spending `dollars`. Return (vwap, exhausted)."""
    spent = shares = 0.0
    for p, q in asks:
        take = min(p * q, dollars - spent)
        shares += take / p
        spent += take
        if spent >= dollars - 1e-9:
            return spent / shares, False
    return (spent / shares if shares else None), True


def summarize(slug, family, d):
    st = d.get("state")
    bids = sorted(_levels(d.get("bids")), key=lambda x: -x[0])
    asks = sorted(_levels(d.get("offers")), key=lambda x: x[0])
    stats = d.get("stats") or {}
    row = dict(us_slug=slug, family=family, state=st,
               best_bid=None, best_ask=None, mid=None, spread_c=None,
               n_bid_levels=len(bids), n_ask_levels=len(asks),
               touch_bid_usd=None, touch_ask_usd=None,
               full_bid_usd=sum(p * q for p, q in bids), full_ask_usd=sum(p * q for p, q in asks),
               fill50_ok=None, slip50_c=None, fill250_ok=None, slip250_c=None,
               last_trade_px=_val(stats.get("lastTradePx")),
               shares_traded=_f(stats.get("sharesTraded")),
               open_interest=_f(stats.get("openInterest")))
    if bids:
        row["best_bid"] = bids[0][0]; row["touch_bid_usd"] = bids[0][0] * bids[0][1]
    if asks:
        row["best_ask"] = asks[0][0]; row["touch_ask_usd"] = asks[0][0] * asks[0][1]
        for size, okk, slipk in ((50, "fill50_ok", "slip50_c"), (250, "fill250_ok", "slip250_c")):
            vwap, exh = _fill(asks, float(size))
            row[okk] = (not exh)
            row[slipk] = (vwap - asks[0][0]) * 100 if (vwap and not exh) else None
    if bids and asks:
        row["mid"] = (bids[0][0] + asks[0][0]) / 2.0
        row["spread_c"] = (asks[0][0] - bids[0][0]) * 100
    return row


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_COLS = ["us_slug", "family", "state", "best_bid", "best_ask", "mid", "spread_c",
         "n_bid_levels", "n_ask_levels", "touch_bid_usd", "touch_ask_usd",
         "full_bid_usd", "full_ask_usd", "fill50_ok", "slip50_c", "fill250_ok", "slip250_c",
         "last_trade_px", "shares_traded", "open_interest"]


def sweep(con, want_other):
    mids = asyncio.run(discover())
    targets = []
    seen_other = 0
    for slug, mid in mids.items():
        fam = classify(slug, mid, want_other and seen_other < want_other)
        if fam == "other":
            seen_other += 1
        if fam:
            targets.append((slug, fam))
    fams = {}
    for _, f in targets:
        fams[f] = fams.get(f, 0) + 1
    books = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        for slug, d in ex.map(lambda s: get_book(s[0]), targets):
            books[slug] = d
    rows = []
    for slug, fam in targets:
        d = books.get(slug)
        if d is None:
            continue
        r = summarize(slug, fam, d)
        rows.append(tuple(r[c] for c in _COLS))
    if rows:
        execute_values(con.cursor(),
                       f"INSERT INTO us_book_tape ({','.join(_COLS)}) VALUES %s", rows)
        con.commit()
    return len(mids), fams, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="seconds between sweeps")
    ap.add_argument("--other", type=int, default=0, help="also sample N random control markets")
    a = ap.parse_args()
    con = psycopg2.connect(PG_DSN)
    ensure_schema(con)
    while True:
        t0 = time.time()
        try:
            n_active, fams, stored = sweep(con, a.other)
            from datetime import datetime, timezone
            print(f"{datetime.now(timezone.utc):%H:%M:%S}  active={n_active} "
                  f"sampled={fams} stored={stored} ({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            con.rollback()
            print(f"sweep failed: {type(e).__name__}: {str(e)[:160]}", flush=True)
        if a.once or not a.loop:
            break
        time.sleep(max(5, a.loop - (time.time() - t0)))
    con.close()


if __name__ == "__main__":
    main()
