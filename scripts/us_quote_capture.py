#!/usr/bin/env python3
"""US-VENUE FORWARD QUOTE CAPTURE — the Phase C/D spine. Read-only. No order is ever placed.

THE CLOCK STARTS HERE, AND IT CANNOT BE REWOUND
-----------------------------------------------
The decisive question — "does the intl consensus signal certify when priced at the US book,
after the US fee?" — CANNOT BE ANSWERED FROM HISTORY. Polymarket US publishes no price
history: /candles, /prices-history and /trades all 404, and /bbo on a settled market returns
bestBid=NULL, bestAsk=NULL. There is no US ask at any past fire time, anywhere.

So the US basis is measurable only FORWARD, and every day this does not run is a day of
realizable-edge truth that can never be recovered. Same irreversible clock as the at-fire ask
capture, for the same reason.

WHY A PYTHON SIDECAR AND NOT RUST (the choice, justified in writing as the brief requires)
-----------------------------------------------------------------------------------------
The bot is Rust, and the venue leg will eventually have to live there. But TODAY: there is no
Rust SDK for the US venue, the verified mapper is ~300 lines of Python with an adversarial
test suite behind it (406/406 resolution agreement), and this capture is READ-ONLY — it never
places an order, so it needs none of the executor's cage, idempotency or kill-switch. Porting
the mapper to Rust first would buy nothing and would cost days of unrecoverable capture. A
sidecar starts the clock now. When Phase D returns a verdict and real money is on the table,
the venue leg gets built properly in Rust behind the existing cage; this script is a
data-collection instrument, not the execution path, and must never become one.

THE PLACEBO IS NOT OPTIONAL
---------------------------
Every quote we take on a signalled market, we also take on a MATCHED CONTROL — a market of the
same league and date that we did NOT signal — through the same code path, at the same instant.
The retracted "15 min = 8¢" latency finding collapsed to +2.05¢ ± 4.0¢ (p=0.36) the moment a
control was finally added, and the placebo median had drifted MORE than the treatment. A basis
measured without a control is not evidence. If the control is not captured now, it will not
exist when the analysis needs it.

Usage:
    python3 scripts/us_quote_capture.py --once     # one sweep (what launchd runs)
    python3 scripts/us_quote_capture.py --loop 60  # continuous, 60s cadence
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.request
from datetime import datetime, timezone

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_mapper as M  # noqa: E402

GW = "https://gateway.polymarket.us"
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
PLACEBO_PER_SWEEP = int(os.environ.get("US_PLACEBO_PER_SWEEP", "40"))


def bbo(slug: str):
    try:
        r = urllib.request.Request(f"{GW}/v1/markets/{slug}/bbo",
                                   headers={"User-Agent": "research/1.0"})
        with urllib.request.urlopen(r, timeout=15) as resp:
            return json.load(resp).get("marketData") or {}
    except Exception:
        return None


def _f(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    try:
        return float(cur)
    except (TypeError, ValueError):
        return None


def our_side_quote(best_bid, best_ask, side_index):
    """The price WE would pay/receive, for the side WE would buy.

    `/bbo` quotes ONE side of the binary — side_index 0 (the first `side_desc` entry, "Yes" on
    a proposition market). It does NOT quote our side. If we are buying side 1 ("No"), our ask
    is the complement of THEIR BID, not their ask:

        our_ask(1) = 1 - best_bid        our_bid(1) = 1 - best_ask

    Reading `bestAsk` regardless of side is a SILENT PRICE INVERSION. Measured on the first
    sweep: the weather arm buys NO, and the raw `bestAsk` produced a basis of -0.57 to -0.93 —
    a 90-cent "disagreement" between two venues on the same event, which is impossible and was
    the tell. Every number derived from a side-blind price is garbage.
    """
    if side_index is None or best_bid is None or best_ask is None:
        return (None, None)
    if side_index == 0:
        return (best_bid, best_ask)
    return (1.0 - best_ask, 1.0 - best_bid)   # (our_bid, our_ask)


def side_index(side_desc_json: str, label: str):
    """Which side would we BUY? Index into side_desc == index into outcomePrices.

    See scripts/us_mapper_verify.py: `outcomes` is NOT reliably ordered; `side_desc` is the
    orientation. Refuse on ambiguity — never guess a side.
    """
    try:
        sides = json.loads(side_desc_json or "[]")
    except Exception:
        return (None, None)
    lab = (label or "").strip().lower()
    if lab in ("yes", "no"):
        for i, s in enumerate(sides):
            if str(s).strip().lower() == lab:
                return (str(s), i)
        return (None, None)
    want = M.name_tokens(label or "")
    cands = [(str(s), i) for i, s in enumerate(sides) if want & M.name_tokens(str(s))]
    return cands[0] if len(cands) == 1 else (None, None)


def sweep(con, idx, us_meta) -> tuple[int, int]:
    cur = con.cursor()
    cur.execute("""
        SELECT id, condition_id, outcome_index, event_slug, slug, title, outcome_label,
               first_detected_at
        FROM consensus_signals
        WHERE NOT resolved AND strategy NOT LIKE '\\_%'
          AND strategy IN ('favorite','weather_fav','favorite_v2','elite_fresh_fav')
    """)
    rows = cur.fetchall()

    now = datetime.now(timezone.utc)
    n_sig = 0
    seen_ld = set()   # (league, date) of the markets we DID signal — the placebo must avoid these
    for sid, cond, oidx, es, ms, title, label, fdet in rows:
        m = M.map_signal(idx, es, ms, title)
        if m.confidence < M.THRESHOLD:
            continue
        meta = us_meta.get(m.us_slug)
        if not meta or str(meta["closed"]).lower() in ("true", "1"):
            continue
        sd, si = side_index(meta["side_desc"], label)
        d = bbo(m.us_slug)
        if not d:
            continue
        bb, ba = _f(d, "bestBid", "value"), _f(d, "bestAsk", "value")
        ourb, oura = our_side_quote(bb, ba, si)
        p = M.parse_us(m.us_slug)
        if p:
            seen_ld.add((p[1], p[3]))
        lag = (now - fdet).total_seconds() if fdet else None
        cur.execute("""
            INSERT INTO us_quotes (signal_id, condition_id, outcome_index, us_slug, us_side,
                us_side_index, ts, best_bid, best_ask, our_bid, our_ask, bid_depth_usd,
                ask_depth_usd, last_trade_px, shares_traded, capture_lag_s, mapper_conf, is_placebo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)
        """, (sid, cond, oidx, m.us_slug, sd, si, now,
              bb, ba, ourb, oura,
              _f(d, "bidDepth"), _f(d, "askDepth"),
              _f(d, "lastTradePx", "value"), _f(d, "sharesTraded"),
              lag, m.confidence))
        n_sig += 1

    # ---- matched placebo: same (league, date) cells, markets we did NOT signal ----
    pool = [s for s, mm in us_meta.items()
            if str(mm["closed"]).lower() in ("false", "0")
            and (pp := M.parse_us(s)) and (pp[1], pp[3]) in seen_ld]
    random.shuffle(pool)
    n_pl = 0
    for slug in pool[:PLACEBO_PER_SWEEP]:
        d = bbo(slug)
        if not d:
            continue
        cur.execute("""
            INSERT INTO us_quotes (us_slug, ts, best_bid, best_ask, bid_depth_usd,
                ask_depth_usd, last_trade_px, shares_traded, is_placebo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
        """, (slug, now, _f(d, "bestBid", "value"), _f(d, "bestAsk", "value"),
              _f(d, "bidDepth"), _f(d, "askDepth"),
              _f(d, "lastTradePx", "value"), _f(d, "sharesTraded")))
        n_pl += 1

    con.commit()
    return n_sig, n_pl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="seconds between sweeps")
    a = ap.parse_args()

    import duckdb
    dcon = duckdb.connect()
    idx = M.build_index(dcon)
    us_meta = {r[0]: {"closed": r[1], "side_desc": r[2]} for r in dcon.execute(
        f"SELECT slug, closed, side_desc FROM read_parquet('{M.US_PARQUET}')").fetchall()}
    print(f"US index ready: {len(us_meta):,} markets", flush=True)

    con = psycopg2.connect(PG_DSN)
    while True:
        t0 = time.time()
        try:
            s, p = sweep(con, idx, us_meta)
            print(f"{datetime.now(timezone.utc):%H:%M:%S}  signals={s:<4} placebo={p:<4} "
                  f"({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            con.rollback()
            print(f"sweep failed: {str(e)[:160]}", flush=True)
        if a.once or not a.loop:
            break
        time.sleep(max(5, a.loop - (time.time() - t0)))


if __name__ == "__main__":
    main()
