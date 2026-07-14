#!/usr/bin/env python3
"""
The ONE candidate cause that survived Phase B: tennis went +13.4% -> -9.9%.

This script exists to try to KILL that finding, not to confirm it. Three attacks:

  ATTACK 1 -- MULTIPLICITY. Tennis was found by scanning 7 categories x 4 windows, not
     pre-registered. Its p must be charged the full search cost (Bonferroni over the
     categories actually scanned, and BH over the whole axis-3 family).

  ATTACK 2 -- POWER / CI. 19 recent matches. What is the cluster-robust CI on -9.9%?
     If it contains the earlier +13.4%, the "decay" is not distinguishable from noise.

  ATTACK 3 -- OOS / LODO. Does the tennis drop survive dropping its worst single day
     (07-13, which carries 10 of the 19)? A "decay" that is one bad slate is one bad slate.

  ATTACK 4 -- HOLD-OUT LOGIC. Even if tennis really decayed, does EXCLUDING tennis improve
     the strategy out-of-sample? Removing whatever lost last week ALWAYS improves the
     backtest. The only honest check is whether the exclusion has a mechanism that would
     have been predicted BEFORE looking -- and whether the non-tennis remainder is itself
     still positive with a positive LB.

Read-only. Emits reports/EROSION-TENNIS-TEST.json.
"""

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import effective_n as EN  # noqa: E402
import erosion_lib as E  # noqa: E402
import market_taxonomy as TAX  # noqa: E402
import erosion_decompose as D  # noqa: E402

RNG = np.random.default_rng(20260714)
SPLIT_DAY = "2026-07-10"   # tennis "recent" = matches first firing on/after this day
N_CATS_SCANNED = 7         # ATTACK 1: the search cost we must pay
N_PERM = 20000


def main():
    rows = E.fetch()
    ls, blind, nb = D.enrich(rows)
    mday = E.match_day(ls)

    ten = [l for l in ls if l["cat"] == "tennis"]
    rec = [l for l in ten if mday[l["key"]] >= SPLIT_DAY]
    ear = [l for l in ten if mday[l["key"]] < SPLIT_DAY]

    u_rec = list(D.match_units(rec).values())
    u_ear = list(D.match_units(ear).values())
    roi_rec, roi_ear = D._roi(u_rec), D._roi(u_ear)
    obs = roi_rec - roi_ear

    out = {"split_day": SPLIT_DAY,
           "tennis_recent": {"matches": len(u_rec), "roi": roi_rec, "lb95": D._lb(u_rec)},
           "tennis_earlier": {"matches": len(u_ear), "roi": roi_ear, "lb95": D._lb(u_ear)},
           "observed_diff": obs}

    # ATTACK 1+2 -- permutation p on tennis matches, then charged for the search
    allu = u_ear + u_rec
    arr = np.array(allu, dtype=float)
    n_rec = len(u_rec)
    hits = 0
    for _ in range(N_PERM):
        idx = RNG.permutation(len(arr))
        r, e = arr[idx[:n_rec]], arr[idx[n_rec:]]
        d = (r[:, 0].sum() / r[:, 1].sum()) - (e[:, 0].sum() / e[:, 1].sum())
        if d <= obs + 1e-12:
            hits += 1
    p_raw = (hits + 1) / (N_PERM + 1)
    p_bonf = min(1.0, p_raw * N_CATS_SCANNED)
    out["p_raw_permutation"] = p_raw
    out["p_bonferroni_over_categories"] = p_bonf
    out["n_categories_scanned"] = N_CATS_SCANNED

    # ATTACK 2 -- does the recent CI contain the earlier point estimate?
    n = len(u_rec)
    tt = sum(u[1] for u in u_rec)
    contrib = np.array([u[0] / (tt / n) for u in u_rec])
    se = float(contrib.std(ddof=1) / np.sqrt(n))
    t = EN._t_ppf(0.975, n - 1)
    ci = (roi_rec - t * se, roi_rec + t * se)
    out["tennis_recent_ci95"] = list(ci)
    out["ci_contains_earlier_estimate"] = bool(ci[0] <= roi_ear <= ci[1])

    # ATTACK 3 -- LODO within recent tennis
    lodo = {}
    for d in sorted({mday[l["key"]] for l in rec}):
        sub = [l for l in rec if mday[l["key"]] != d]
        u = list(D.match_units(sub).values())
        lodo[d] = {"matches_dropped": len({l["key"] for l in rec if mday[l["key"]] == d}),
                   "roi_without": D._roi(u) if u else None}
    out["lodo_recent_tennis_by_day"] = lodo
    vals = [v["roi_without"] for v in lodo.values() if v["roi_without"] is not None]
    out["lodo_any_day_flips_positive"] = bool(any(v > 0 for v in vals))

    # ATTACK 4 -- would excluding tennis even be defensible? non-tennis remainder, recent window
    non = [l for l in ls if l["cat"] != "tennis"]
    non_rec = [l for l in non if mday[l["key"]] >= SPLIT_DAY]
    u_non_rec = list(D.match_units(non_rec).values())
    out["non_tennis_recent"] = {"matches": len(u_non_rec),
                                "roi": D._roi(u_non_rec) if u_non_rec else None,
                                "lb95": D._lb(u_non_rec)}

    os.makedirs("reports", exist_ok=True)
    with open("reports/EROSION-TENNIS-TEST.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"tennis EARLIER : {len(u_ear):3d} matches  ROI {100*roi_ear:+6.1f}%  LB95 "
          f"{100*out['tennis_earlier']['lb95']:+.1f}%")
    print(f"tennis RECENT  : {len(u_rec):3d} matches  ROI {100*roi_rec:+6.1f}%  LB95 "
          f"{100*out['tennis_recent']['lb95']:+.1f}%")
    print(f"  95% CI on recent tennis: [{100*ci[0]:+.1f}%, {100*ci[1]:+.1f}%]")
    print(f"  CI contains the earlier +{100*roi_ear:.1f}%?  "
          f"{'YES -> not distinguishable from noise' if out['ci_contains_earlier_estimate'] else 'no'}")
    print(f"\nATTACK 1 (multiplicity): p_raw={p_raw:.4f}  "
          f"p_Bonferroni(x{N_CATS_SCANNED} categories)={p_bonf:.4f}")
    print("\nATTACK 3 (LODO within recent tennis):")
    for d, v in lodo.items():
        print(f"    without {d} ({v['matches_dropped']:2d} M): {100*v['roi_without']:+6.1f}%")
    print(f"  any single day flips it positive? {out['lodo_any_day_flips_positive']}")
    nr = out["non_tennis_recent"]
    print(f"\nATTACK 4 (the remainder): non-tennis recent = {nr['matches']} matches, "
          f"ROI {100*nr['roi']:+.1f}%, LB95 {100*nr['lb95']:+.1f}%")
    print("-> reports/EROSION-TENNIS-TEST.json")


if __name__ == "__main__":
    main()
