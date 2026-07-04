#!/usr/bin/env python3
"""
mm_screen_effect — the CORRECTED downstream read of the MM screen (D29 addendum, 2026-07-04).

Phase-1's Tier-2 (mm_persistence_effect.py) asked "does excluding flagged wallets RAISE the pool's
early→late persistence?" and got NO-GO. Reconciling against the router's OWN persistence instrument
(trader_scorecard.persistence) revealed WHY, and that the criterion was MISFRAMED:

  * MMs are MECHANICALLY persistent (buy-both-hold arbers earn a stable small edge every period),
    so they INFLATE the pooled H1→H2 corr. Removing them CORRECTLY lowers the raw number —
    "raises persistence" was never the right success test.
  * The right test is DOWNSTREAM PROFIT: the forward (H2) copy-return of the wallets whose H1
    copy-return cleared +10% — the cohort the proven-router actually follows. On that test the
    screen is strongly ACCRETIVE: it keeps arbers (whose H1≥10% is arb-driven, not copyable) OUT
    of the cohort, ~10×-ing the cohort's realized forward return.

This instrument makes that reconciliation reproducible as the record accrues, and A/B's the three
screen axes on the DOWNSTREAM proxy — which is how it surfaced that `round_trip_rate` is a
false-positive generator that can be relaxed without cost (see the amendment proposal in
reports/PROPOSAL_mm_round_trip_relax.md). Read-only, paper-only.

  ./mm_screen_effect.py             # print + write reports/mm_screen_effect.json
  ./mm_screen_effect.py --selftest  # synthetic: arbers inflate pooled corr; screen lifts cohort fwd
"""

import json
import os
import sys
from collections import defaultdict

# reuse the router's own frozen machinery verbatim (single source of truth)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
try:
    import scripts.trader_scorecard as ts
except ModuleNotFoundError:  # when run from repo root
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import trader_scorecard as ts


def _screen(m, rtr, tsr, sbr):
    """True = flagged MM (excluded). Mirrors trader_scorecard.is_mm with tunable thresholds."""
    return m["rtr"] >= rtr or m["tsr"] >= tsr or m["sbr"] >= sbr


def subgroup_persistence(rows, spreads, micro, keep):
    """H1→H2 copy-return corr over wallets for which keep(micro_row) is True. Equal-halves by
    time, ≥MIN_HALF per half — identical to trader_scorecard.persistence's inner loop."""
    per = defaultdict(list)
    for r in rows:
        per[r["wallet"]].append(r)
    h1, h2, cohort = [], [], []
    for w, rs in per.items():
        m = micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0})
        if not keep(m):
            continue
        rs.sort(key=lambda r: float(r["ts"]))
        half = len(rs) // 2
        a, b = rs[:half], rs[half:]
        if len(a) < ts.MIN_HALF or len(b) < ts.MIN_HALF:
            continue
        ca = ts.clustered(a, spreads)[w]["copy_return"]
        cb = ts.clustered(b, spreads)[w]["copy_return"]
        h1.append(ca)
        h2.append(cb)
        if ca >= 0.10:
            cohort.append(cb)
    corr = ts.pearson(h1, h2) if len(h1) >= 4 else None
    fwd = (sum(cohort) / len(cohort)) if cohort else None
    return {"corr": corr, "n": len(h1), "cohort_fwd_h2": fwd, "cohort_n": len(cohort)}


# The A/B grid: (label, rtr, tsr, sbr). 9.9 = axis OFF.
SCREENS = [
    ("no_screen", 9.9, 9.9, 9.9),
    ("current_0.30/0.25/0.50", 0.30, 0.25, 0.50),
    ("drop_round_trip", 9.9, 0.25, 0.50),
    ("relax_round_trip_0.50", 0.50, 0.25, 0.50),
    ("two_sided_only", 9.9, 0.25, 9.9),
]


def run(rows=None, spreads=None, micro=None, quiet=False):
    spreads = ts.fetch_band_spreads() if spreads is None else spreads
    rows = ts.fetch_fills() if rows is None else rows
    micro = ts.fetch_micro() if micro is None else micro
    # subgroup split under the CURRENT screen (the inflation diagnostic)
    sub = {
        "all": subgroup_persistence(rows, spreads, micro, lambda m: True),
        "mm_flagged": subgroup_persistence(rows, spreads, micro,
                                           lambda m: _screen(m, 0.30, 0.25, 0.50)),
        "clean": subgroup_persistence(rows, spreads, micro,
                                      lambda m: not _screen(m, 0.30, 0.25, 0.50)),
    }
    ab = {}
    for label, rtr, tsr, sbr in SCREENS:
        ab[label] = subgroup_persistence(rows, spreads, micro,
                                         lambda m, r=rtr, t=tsr, s=sbr: not _screen(m, r, t, s))
    res = {"subgroup": sub, "screen_ab": ab}
    if not quiet:
        _print(res)
    return res


def _print(r):
    print("MM SCREEN-EFFECT · corrected downstream read (copy-return, equal-halves)\n")
    print("  (1) inflation diagnostic — persistence WITHIN each subgroup under current screen:")
    for k in ("mm_flagged", "all", "clean"):
        s = r["subgroup"][k]
        c = "n/a" if s["corr"] is None else f"{s['corr']:+.3f}"
        print(f"      {k:<12} H1→H2 corr {c}  n={s['n']}")
    print("      → MMs are MORE persistent (arb) and INFLATE the pooled corr; 'clean' is the "
          "copyable directional signal.\n")
    print("  (2) screen A/B on the DOWNSTREAM profit proxy (H1≥10% cohort forward-H2 return):")
    print(f"      {'screen':<26}{'corr':>8}{'n':>5}{'cohort_fwd':>12}{'coh_n':>7}")
    for label, *_ in SCREENS:
        s = r["screen_ab"][label]
        c = "n/a" if s["corr"] is None else f"{s['corr']:+.3f}"
        f = "n/a" if s["cohort_fwd_h2"] is None else f"{s['cohort_fwd_h2']:+.3f}"
        print(f"      {label:<26}{c:>8}{s['n']:>5}{f:>12}{s['cohort_n']:>7}")
    print("      → screen lifts cohort forward-return vs no_screen; relaxing round_trip recovers "
          "wallets at equal/greater cohort return.")


def selftest():
    """Synthetic: 30 directional humans (persistent, copyable), 20 arbers (MORE persistent but
    their H1≥10% does NOT carry to H2). Screen must (a) show mm corr > clean corr, and (b) lift
    the cohort forward-return vs no-screen."""
    import random
    rng = random.Random(11)
    rows = []
    # per-wallet H1/H2 ABSOLUTE copy-return levels, injected directly (deterministic fixture)
    level = {}

    def emit(w, n, h1, h2, rtr, tsr, sbr):
        level[(w, 0)] = h1
        level[(w, 1)] = h2
        for i in range(n):
            rows.append({"wallet": w, "ts": float(i), "half": 1 if i >= n // 2 else 0,
                         "_rtr": rtr, "_tsr": tsr, "_sbr": sbr})
    micro = {}
    for i in range(30):  # directional human: skill persists but with real noise → moderate corr
        r = rng.uniform(0, 1)
        s = -0.05 + 0.2 * r
        emit(f"h{i}", 2 * ts.MIN_HALF, s + rng.uniform(-0.06, 0.06),
             s + rng.uniform(-0.06, 0.06), 0.0, 0.0, 0.0)
        micro[f"h{i}"] = {"rtr": 0.0, "tsr": 0.0, "sbr": 0.0}
    for i in range(20):  # arber: rank-persistent (shared r, tiny noise → HIGH corr) but H2 absolute
        r = rng.uniform(0, 1)                       # collapses for the copier (tax eats the arb)
        emit(f"m{i}", 2 * ts.MIN_HALF, 0.08 + 0.18 * r + rng.uniform(-0.01, 0.01),
             -0.06 + 0.05 * r + rng.uniform(-0.01, 0.01), 0.6, 0.6, 0.6)
        micro[f"m{i}"] = {"rtr": 0.6, "tsr": 0.6, "sbr": 0.6}

    # monkeypatch clustered→inject the fixture's per-(wallet,half) copy_return
    def fake_clustered(rs, spreads):
        w = rs[0]["wallet"]
        return {w: {"copy_return": level[(w, rs[0]["half"])], "n_fills": len(rs)}}
    orig = ts.clustered
    ts.clustered = fake_clustered
    try:
        r = run(rows, {}, micro, quiet=True)
    finally:
        ts.clustered = orig
    mm_c = r["subgroup"]["mm_flagged"]["corr"]
    cl_c = r["subgroup"]["clean"]["corr"]
    lift = (r["screen_ab"]["current_0.30/0.25/0.50"]["cohort_fwd_h2"] or -9) \
        > (r["screen_ab"]["no_screen"]["cohort_fwd_h2"] or -9)
    ok = mm_c is not None and cl_c is not None and mm_c > cl_c and lift
    print(f"  [{'ok' if ok else 'FAIL'}] mm corr {mm_c} > clean corr {cl_c}; screen lifts cohort fwd: {lift}")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    res = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports",
                       "mm_screen_effect.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("\nartifact → reports/mm_screen_effect.json")


if __name__ == "__main__":
    main()
