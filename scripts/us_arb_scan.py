#!/usr/bin/env python3
"""CROSS-VENUE ARBITRAGE SCANNER — US book vs international CLOB. READ-ONLY. Never trades.

Tue holds both books (US directly; intl via a family member abroad). Same event, two separate
order books, so the same outcome can be two prices at once. This scans for the RISK-FREE arb:
buy outcome O where O is cheap, buy ¬O where ¬O is cheap; if the combined cost < $1 − fees the
edge is locked at settlement — valid because the mapper certifies both contracts settle to the
same event (conf ≥ 0.90 only). See migration 046 for the full structure and honesty contract.

Reuses the VETTED pieces by import (no reinvention of the side-inversion bug):
  * us_mapper.map_signal / parse_us / THRESHOLD
  * us_quote_capture.our_side_quote / side_index / bbo   (the US /bbo + complement logic)
Intl legs come from clob_price_tape (best_ask of the leg for outcome_index O = price to buy O
on intl). A stale intl leg fails closed (is_actionable stays false).

Usage:
    python3 scripts/us_arb_scan.py --once
    python3 scripts/us_arb_scan.py --loop 120
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_mapper as M          # noqa: E402
import us_quote_capture as Q   # noqa: E402  (our_side_quote, side_index, bbo — vetted side logic)

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
INTL_STALE_MAX_S = float(os.environ.get("INTL_STALE_MAX_S", "180"))   # fail closed beyond this
INTL_FEE = float(os.environ.get("INTL_FEE", "0.0"))                   # intl CLOB taker fee ≈ 0
_MIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "migrations", "046_cross_venue_basis.sql")


def us_taker_fee(price):
    """US taker fee per share = 0.06·p·(1−p) ([[project-polymarket-us-venue]] fee schedule)."""
    if price is None:
        return 0.0
    return 0.06 * price * (1.0 - price)


def ensure_schema(con):
    with open(_MIG) as f:
        con.cursor().execute(f.read())
    con.commit()


def intl_legs(cur, condition_id, outcome_index):
    """Freshest clob_price_tape ask for outcome O and its complement, + the age of O's leg."""
    if condition_id is None or outcome_index is None:
        return None
    comp = 1 - outcome_index  # binary
    out = {}
    for idx in (outcome_index, comp):
        cur.execute("""
            SELECT best_ask, best_bid, extract(epoch from now()-recv_at)
            FROM clob_price_tape
            WHERE condition_id = %s AND outcome_index = %s AND best_ask IS NOT NULL
            ORDER BY recv_at DESC LIMIT 1
        """, (condition_id, idx))
        r = cur.fetchone()
        out[idx] = r  # (ask, bid, age_s) or None
    o = out.get(outcome_index)
    c = out.get(comp)
    return dict(ask_o=o[0] if o else None, age_o=o[2] if o else None,
                ask_comp=c[0] if c else None)


_COLS = ["signal_id", "condition_id", "outcome_index", "us_slug", "us_side_index", "mapper_conf",
         "us_ask_o", "us_ask_comp", "intl_ask_o", "intl_ask_comp", "basis_o",
         "arb_us_intl", "arb_intl_us", "best_arb_cost", "fee_total", "arb_edge",
         "is_actionable", "intl_age_s", "is_placebo", "us_ts"]


def scan(con, idx, us_meta):
    cur = con.cursor()
    cur.execute(r"""
        SELECT id, condition_id, outcome_index, event_slug, slug, title, outcome_label
        FROM consensus_signals
        WHERE NOT resolved AND strategy NOT LIKE '\_%'
    """)
    signals = cur.fetchall()
    rows, actionable = [], 0
    now = datetime.now(timezone.utc)
    for sid, cond, oidx, es, ms, title, label in signals:
        m = M.map_signal(idx, es, ms, title)
        if m.confidence < M.THRESHOLD:
            continue
        meta = us_meta.get(m.us_slug)
        if not meta or str(meta["closed"]).lower() in ("true", "1"):
            continue
        _, si = Q.side_index(meta["side_desc"], label)
        if si is None:
            continue
        d = Q.bbo(m.us_slug)
        if not d:
            continue
        bb = Q._f(d, "bestBid", "value")
        ba = Q._f(d, "bestAsk", "value")
        us_ask_o = Q.our_side_quote(bb, ba, si)[1]           # buy O on US
        us_ask_comp = Q.our_side_quote(bb, ba, 1 - si)[1]    # buy ¬O on US

        legs = intl_legs(cur, cond, oidx)
        intl_ask_o = legs["ask_o"] if legs else None
        intl_ask_comp = legs["ask_comp"] if legs else None
        age = legs["age_o"] if legs else None

        basis_o = (us_ask_o - intl_ask_o) if (us_ask_o is not None and intl_ask_o is not None) else None
        arb_ui = (us_ask_o + intl_ask_comp) if (us_ask_o is not None and intl_ask_comp is not None) else None
        arb_iu = (intl_ask_o + us_ask_comp) if (intl_ask_o is not None and us_ask_comp is not None) else None
        legs_present = [x for x in (arb_ui, arb_iu) if x is not None]
        best = min(legs_present) if legs_present else None
        # fee on whichever US leg is bought in the cheaper basket
        fee = None
        if best is not None:
            us_leg_px = us_ask_o if (arb_ui is not None and best == arb_ui) else us_ask_comp
            fee = us_taker_fee(us_leg_px) + INTL_FEE
        edge = (1.0 - best - fee) if (best is not None and fee is not None) else None
        fresh = (age is not None and age <= INTL_STALE_MAX_S)
        act = bool(edge is not None and edge > 0 and fresh)
        if act:
            actionable += 1
        rows.append((sid, cond, oidx, m.us_slug, si, m.confidence,
                     us_ask_o, us_ask_comp, intl_ask_o, intl_ask_comp, basis_o,
                     arb_ui, arb_iu, best, fee, edge, act, age, False, now))
    if rows:
        execute_values(cur, f"INSERT INTO cross_venue_basis ({','.join(_COLS)}) VALUES %s", rows)
        con.commit()
    return len(signals), len(rows), actionable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0)
    a = ap.parse_args()

    import duckdb
    dcon = duckdb.connect()
    idx = M.build_index(dcon)
    us_meta = {r[0]: {"closed": r[1], "side_desc": r[2]} for r in dcon.execute(
        f"SELECT slug, closed, side_desc FROM read_parquet('{M.US_PARQUET}')").fetchall()}
    print(f"mapper index + {len(us_meta):,} US markets ready", flush=True)

    con = psycopg2.connect(PG_DSN)
    ensure_schema(con)
    while True:
        t0 = time.time()
        try:
            nsig, scanned, act = scan(con, idx, us_meta)
            print(f"{datetime.now(timezone.utc):%H:%M:%S}  signals={nsig} mapped+priced={scanned} "
                  f"ACTIONABLE_ARB={act}  ({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            con.rollback()
            print(f"scan failed: {type(e).__name__}: {str(e)[:160]}", flush=True)
        if a.once or not a.loop:
            break
        time.sleep(max(5, a.loop - (time.time() - t0)))
    con.close()


if __name__ == "__main__":
    main()
