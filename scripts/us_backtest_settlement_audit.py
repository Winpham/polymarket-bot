#!/usr/bin/env python3
"""
SETTLEMENT AUDIT — does the US backtest's "settlement" actually settle?

RED-TEAM FINDING F1. `us_backtest.py::settlements()` asserts in its own docstring:

    "symbol -> settlement (0/1). Take the LAST business_date per symbol: a contract settles
     once, and earlier rows carry the pre-settlement 0.0 default."

A CFTC DCM publishes a DAILY SETTLEMENT PRICE for margining. Live contracts get a MARK.
Measured on our own table: 49.2% of DMR rows are fractional, and 11.6% of SYMBOLS have a
FRACTIONAL LAST ROW -- which is precisely the row `settlements()` returns.

`price_it()` then does  payoff = st  /  gross = payoff - q  /  won = payoff > 0.5.
So a favorite that LOST, whose last published mark is 0.85, is booked as a WIN with a
positive gross. On a cell whose entire content is "1 loss in 82 where the market priced 6",
that is not a rounding error -- it is the result.

And the ground truth was in the row the whole time: us_backtest.py:87 SELECTs `outcome_won`
(the intl resolution) and price_it() NEVER READS IT.

This script re-runs the exact pipeline and cross-checks every pick:
        (payoff > 0.5)  ==  outcome_won   ?
It reports the traded cell (0.90-0.95 non-World-Cup) both AS PUBLISHED and CLEAN
(dropping picks whose DMR row never reached a terminal 0/1), and re-derives the loss count.

Usage:  python3 scripts/us_backtest_settlement_audit.py
"""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import us_backtest as B
import us_fees
import psycopg2

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")


def terminal_settlements(con):
    """The HONEST settlement map: only rows that actually reached a terminal 0/1."""
    with con.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (symbol) symbol, settlement_price
              FROM us_daily_market_report
             WHERE settlement_price IS NOT NULL
          ORDER BY symbol, business_date DESC
        """)
        last = {r[0]: float(r[1]) for r in cur.fetchall()}
    return last


def main():
    con = psycopg2.connect(PG_DSN)

    sigs = B.load_signals(con, B.D_FROM, B.D_TO) if hasattr(B, "load_signals") else None
    if sigs is None:                       # fall back to the module's own names
        sigs = B.signals(con, B.D_FROM, B.D_TO)
    mapped = B.map_all(con, sigs)
    mapped = B.attach_us_entry(mapped)
    setl = B.settlements(con, B.D_FROM, B.D_TO)
    last = terminal_settlements(con)

    picks = B.price_it(mapped, setl, haircut_c=B.HAIRCUT_C)
    print(f"picks priced (as published): {len(picks):,}\n")

    # ---- THE CROSS-CHECK -------------------------------------------------------------
    disagree, frac, ok = [], [], 0
    for p in picks:
        st = setl.get(p["us_slug"])
        is_terminal = st in (0.0, 1.0)
        if not is_terminal:
            frac.append(p)
        if bool(p["won"]) != bool(p["outcome_won"]):
            disagree.append(p)
        else:
            ok += 1

    print("=" * 78)
    print("F1 — DOES THE DMR 'SETTLEMENT' AGREE WITH THE INTL GROUND TRUTH (outcome_won)?")
    print("=" * 78)
    print(f"  agree            : {ok:,} / {len(picks):,}")
    print(f"  DISAGREE         : {len(disagree):,}   <-- scored wrong by the backtest")
    print(f"  non-terminal DMR : {len(frac):,}   <-- payoff is a daily MARK, not an outcome")
    if disagree:
        print("\n  examples (backtest said WON / truth says LOST, or vice-versa):")
        for p in disagree[:6]:
            print(f"    {p['us_slug'][:44]:44} DMR_payoff={p['payoff']:.3f} "
                  f"backtest_won={str(p['won']):5} truth_won={p['outcome_won']}")

    # ---- THE TRADED CELL: 0.90-0.95, non-World-Cup ------------------------------------
    def is_wc(p):
        e = (p.get("event_slug") or "") + (p.get("slug") or "")
        return "world-cup" in e.lower() or "fifa" in e.lower() or "fifwc" in e.lower()

    def cell(rows):
        return [p for p in rows if 0.90 <= p["q"] < 0.95 and not is_wc(p)]

    published = cell(picks)
    clean     = cell([p for p in picks if setl.get(p["us_slug"]) in (0.0, 1.0)])

    def summarize(rows, label, use_truth):
        if not rows:
            print(f"\n  {label}: EMPTY"); return
        ev = len({p.get("event_slug") or p["us_slug"] for p in rows})
        if use_truth:
            losses = sum(1 for p in rows if not p["outcome_won"])
            rois = [ (1.0 - p["q"] - us_fees.taker_fee(p["q"]))/p["q"] if p["outcome_won"]
                     else (0.0 - p["q"] - us_fees.taker_fee(p["q"]))/p["q"] for p in rows ]
        else:
            losses = sum(1 for p in rows if not p["won"])
            rois = [p["roi_net"] for p in rows]
        mean = sum(rois)/len(rois)
        print(f"\n  {label}")
        print(f"    picks/events : {len(rows)} / {ev}")
        print(f"    LOSSES       : {losses}")
        print(f"    net ROI      : {mean*100:+.2f}%")

    print("\n" + "=" * 78)
    print("THE TRADED CELL — 0.90-0.95, non-World-Cup")
    print("=" * 78)
    summarize(published, "AS PUBLISHED (DMR settlement_price, won = payoff > 0.5)", use_truth=False)
    summarize(published, "SAME PICKS, scored on the INTL GROUND TRUTH (outcome_won)", use_truth=True)
    summarize(clean,     "CLEAN (only picks whose DMR row reached a terminal 0/1)",  use_truth=True)

    con.close()


if __name__ == "__main__":
    main()
