#!/usr/bin/env python3
"""
atfire_bias.py -- does the at-fire capture fix (migration 042) actually kill the
capture-selection bias? This is the instrument that ANSWERS that, and it is the whole
reason mig 042 exists.

THE BIAS, RESTATED. `entry_ask` (mig 030/032) is captured on the first HOUSEKEEPING pass
that reaches an open signal -- ~10-15 min after it fired. Markets that resolve FAST
(obvious chalk -> winners) resolve before that pass and never get an ask at all; only
slow, contested (loss-prone) markets get one. So the ask-priced sample is loser-tilted,
and every "realizable" number built on `entry_ask` reads ~7pts PESSIMISTIC. That single
bias is why the champion shows ~+1.3% realizable while the (optimistic, full-population)
MID basis shows ~+8.0% -- and why NEITHER is the truth.

`entry_ask_fire` (mig 042) is captured at the INSTANT the signal fires, inside the
consensus cycle, so fast- and slow-resolving picks both get a representative price.

WHAT THIS SCRIPT MEASURES (read-only; writes no DB rows, arms nothing):
  A. COVERAGE      -- what fraction of signals got each kind of ask. The bias shows up
                      here first: housekeeping coverage is systematically MISSING the
                      fast winners.
  B. THE SMOKING GUN -- win rate of captured vs uncaptured under EACH capture method.
                      Housekeeping should show a large gap (85% vs 98% historically).
                      If at-fire capture works, its gap should COLLAPSE toward zero --
                      that is the falsifiable prediction, and the pass/fail of the fix.
  C. LAG           -- seconds from fire to capture. Housekeeping ~600-900s; at-fire
                      should be ~seconds. If the at-fire lag creeps up, the bias is
                      creeping back.
  D. ROI BY BASIS  -- realizable ROI-on-turnover under mid / housekeeping-ask / fire-ask,
                      match-clustered with the corrected fee. The at-fire number is the
                      first HONEST realizable figure this project has ever had.

Until CAPTURE_ENTRY_ASK_AT_FIRE is armed there are zero at-fire rows, and this script
says so plainly rather than printing a fake verdict.

Usage:
  ./atfire_bias.py                # live read-only run
  ./atfire_bias.py --since 2026-07-12
  ./atfire_bias.py --strategy favorite
"""
import argparse
import os
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from superkey import super_event  # noqa: E402 -- the frozen match-clustering key

PG_CONTAINER = os.environ.get("PG_CONTAINER", "polymarket-bot-postgres-1")
BAND_LO, BAND_HI = 0.71, 0.98  # the frozen favorite-consensus band


def fee(p):
    """Corrected spread/fee per share -- the frozen convention (0.03*p*(1-p))."""
    return 0.03 * p * (1.0 - p)


def psql(sql):
    out = subprocess.run(
        ["docker", "exec", "-i", PG_CONTAINER, "psql", "-U", "bot", "-d", "polymarket",
         "--csv", "-q", "-t", "-A", "-F", "\t", "-c", sql],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        print(f"psql failed:\n{out.stderr}", file=sys.stderr)
        sys.exit(1)
    return [r for r in out.stdout.strip().split("\n") if r]


def load(strategy, since):
    rows = psql(f"""
        select id,
               coalesce(initial_mean_price, mean_price)                 as mid,
               entry_ask, entry_ask_fire, entry_ask_fire_mid,
               outcome_won::int                                          as won,
               coalesce(event_slug,'')                                   as es,
               coalesce(slug,'')                                         as slug,
               condition_id,
               extract(epoch from (entry_ask_at      - first_detected_at)) as hk_lag,
               extract(epoch from (entry_ask_fire_at - first_detected_at)) as fire_lag
        from consensus_signals
        where strategy = '{strategy}'
          and resolved and outcome_won is not null
          and coalesce(initial_mean_price, mean_price) between {BAND_LO} and {BAND_HI}
          and first_detected_at >= '{since}'
    """)
    NCOLS = 11
    recs = []
    for r in rows:
        f = r.split("\t")
        # psql drops TRAILING empty fields on some rows, so a row whose last columns
        # are all NULL (e.g. every row before at-fire capture is armed) comes back
        # short. Pad to the full width -- a missing tail column IS a NULL.
        if len(f) < NCOLS:
            f += [""] * (NCOLS - len(f))

        def num(x):
            return float(x) if x not in ("", None) else None
        recs.append(dict(
            mid=num(f[1]), hk_ask=num(f[2]), fire_ask=num(f[3]), fire_mid=num(f[4]),
            won=int(f[5]),
            mk=super_event(f[6], f[7]) or f[8],
            hk_lag=num(f[9]), fire_lag=num(f[10]),
        ))
    return recs


def win_gap(recs, key):
    """B. THE SMOKING GUN: win rate among signals this method PRICED vs those it MISSED.

    A large positive gap (uncaptured wins more) is the selection bias: the method is
    systematically missing the fast-resolving winners. At-fire capture should collapse it.
    """
    got = [r for r in recs if r[key] is not None]
    missed = [r for r in recs if r[key] is None]
    wr_got = 100.0 * sum(r["won"] for r in got) / len(got) if got else None
    wr_missed = 100.0 * sum(r["won"] for r in missed) / len(missed) if missed else None
    gap = (wr_missed - wr_got) if (wr_got is not None and wr_missed is not None) else None
    return len(got), len(missed), wr_got, wr_missed, gap


def roi_turn(recs, price_key):
    """D. Match-clustered ROI-on-turnover at a given entry-price basis."""
    priced = [r for r in recs if r[price_key] is not None]
    if not priced:
        return None, 0, 0
    num = den = 0.0
    for r in priced:
        p = r[price_key]
        num += (r["won"] - p) - fee(p)
        den += p
    matches = len({r["mk"] for r in priced})
    return (num / den * 100.0 if den else None), len(priced), matches


def pct(x, nd=1):
    return "n/a" if x is None else f"{x:+.{nd}f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="favorite")
    ap.add_argument("--since", default="2026-06-29")
    a = ap.parse_args()

    recs = load(a.strategy, a.since)
    n = len(recs)
    print("=" * 78)
    print(f"AT-FIRE CAPTURE BIAS -- strategy={a.strategy} band={BAND_LO}-{BAND_HI} since={a.since}")
    print("read-only; writes nothing; arms nothing")
    print("=" * 78)
    if not n:
        print("no resolved signals in band -- nothing to measure.")
        return
    print(f"\nresolved signals in band: {n}")

    # --- A. COVERAGE ---
    n_hk = sum(1 for r in recs if r["hk_ask"] is not None)
    n_fire = sum(1 for r in recs if r["fire_ask"] is not None)
    print("\n--- A. COVERAGE (what fraction got each kind of ask) ---")
    print(f"  housekeeping ask (entry_ask)      : {n_hk:>4}/{n}  ({100.0*n_hk/n:.1f}%)")
    print(f"  AT-FIRE ask     (entry_ask_fire)  : {n_fire:>4}/{n}  ({100.0*n_fire/n:.1f}%)")

    if n_fire == 0:
        print("\n" + "!" * 78)
        print("NO AT-FIRE ROWS YET -- CAPTURE_ENTRY_ASK_AT_FIRE is not armed (or has not")
        print("fired since arming). The fix is BUILT but UNPROVEN until rows accrue.")
        print("Arm it in .env.consensus AND the docker-compose.consensus.yml env block:")
        print("    CAPTURE_ENTRY_ASK_AT_FIRE=true")
        print("Backfill is IMPOSSIBLE -- the at-fire book is gone once it moves. Every day")
        print("this stays off is a day whose true realizable edge can never be known.")
        print("!" * 78)

    # --- B. THE SMOKING GUN ---
    print("\n--- B. SELECTION BIAS (win% of PRICED vs MISSED; gap>0 => missing the winners) ---")
    for label, key in (("housekeeping", "hk_ask"), ("AT-FIRE     ", "fire_ask")):
        got, missed, wr_g, wr_m, gap = win_gap(recs, key)
        if not got or not missed:
            print(f"  {label}: n/a (priced={got}, missed={missed} -- need both to compare)")
            continue
        verdict = ""
        if gap is not None:
            verdict = "  <-- BIASED (missing fast winners)" if gap >= 3.0 else "  <-- bias collapsed ✓"
        print(f"  {label}: priced n={got} win {wr_g:.1f}%  |  missed n={missed} win {wr_m:.1f}%"
              f"  |  gap {gap:+.1f}pp{verdict}")
    print("  (historical housekeeping gap ~ +13pp: 85% priced vs 98% missed. If AT-FIRE's")
    print("   gap collapses toward 0, the fix works and its ROI is the honest one.)")

    # --- C. LAG ---
    print("\n--- C. CAPTURE LAG (fire -> ask; the mechanism behind the bias) ---")
    for label, key in (("housekeeping", "hk_lag"), ("AT-FIRE     ", "fire_lag")):
        lags = sorted(r[key] for r in recs if r[key] is not None)
        if not lags:
            print(f"  {label}: n/a (no captures)")
            continue
        med = lags[len(lags) // 2]
        print(f"  {label}: n={len(lags)}  median {med:,.0f}s  min {lags[0]:,.0f}s  max {lags[-1]:,.0f}s")

    # --- D. ROI BY BASIS ---
    print("\n--- D. ROI-on-turnover BY ENTRY BASIS (match-clustered, fee 0.03p(1-p)) ---")
    for label, key, note in (
        ("mid (full population)  ", "mid", "optimistic: you cannot buy at the mid"),
        ("housekeeping ask       ", "hk_ask", "BIASED pessimistic (~7pt) -- loser-tilted sample"),
        ("AT-FIRE ask            ", "fire_ask", "the honest realizable figure"),
    ):
        roi, np_, nm = roi_turn(recs, key)
        if roi is None:
            print(f"  {label}: n/a (0 priced)          [{note}]")
        else:
            print(f"  {label}: {pct(roi):>7}  (n={np_}, {nm} matches)  [{note}]")

    # Honest haircut, only where we have a TRUE mid from the same instant (defect D2).
    hc = [r["fire_ask"] - r["fire_mid"] for r in recs
          if r["fire_ask"] is not None and r["fire_mid"] is not None]
    if hc:
        hc.sort()
        print(f"\n  true at-fire execution haircut (ask - REAL mid, same /book instant):")
        print(f"    n={len(hc)}  median {100*hc[len(hc)//2]:.2f}c  mean {100*sum(hc)/len(hc):.2f}c")
        print("    (this is the real copier cost. Defect D2: the old 'at-fire mid' was the")
        print("     consensus vote-mean, not a mid, and understated this by ~1.65c.)")

    print("\n" + "=" * 78)
    print("VERDICT: the at-fire ROI in (D) is trustworthy only once (B)'s AT-FIRE gap has")
    print("collapsed AND coverage in (A) is high. Until then it is a preview, not a number")
    print("to bet on. No real money regardless -- forward gate first (PREREG_20260710).")
    print("=" * 78)


if __name__ == "__main__":
    main()
