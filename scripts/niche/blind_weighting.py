#!/usr/bin/env python3
"""
WHERE IS D(won) ACTUALLY COMING FROM?  (the crux -- do not trust any number until this is settled)

Established: 51,003/51,006 markets are BINARY and their two outcomes' prices are COMPLEMENTARY
(sum ~ 1.0, verified). Therefore, at any one instant, only ONE outcome can print >=80c.

That implies: under a TIGHT time-match (blind print within +/-5min of the roster's), copy and blind
must be buying THE SAME OUTCOME, so they win or lose TOGETHER, so

        D(won) MUST BE ~ 0.

But timing_forensics.py measures D(won) = +0.0198, CI [+0.0110,+0.0283], at tau=5min. Something in
the model of the data is wrong, and until it is found NOTHING downstream can be trusted.

The hypothesis: PRINT-VOLUME WEIGHTING. The blind leg samples uniformly over *prints*, not over
*opportunities*. Lead-change moments generate far more prints than quiet ones. So in a market where
the roster ALSO bought a side that later collapsed, the blind sample is over-weighted toward the
collapsing side's high-volume moments -- producing D(won) > 0 through pure weighting, with no skill.

This script settles it three ways:

  D1  DIRECT: what fraction of time-matched blind prints are on a DIFFERENT outcome than their
      paired copy print? If ~0, D(won) cannot be real and there is a BUG. If material, the effect
      is "blind buys the wrong side during lead changes" -- real, but a volume artifact, not skill.

  D2  DECOMPOSE D(won) into the same-outcome part (must be exactly 0) and the different-outcome part.

  D3  RE-RUN the comparison EQUAL-WEIGHTING OPPORTUNITIES, not prints: at most ONE blind entry per
      (market, outcome), so a noisy lead-change cannot outvote a quiet favourite. If the surplus
      survives equal-weighting, it is real. If it dies, the headline was a weighting artifact.

  ./blind_weighting.py --self-test
  ./blind_weighting.py
"""
import argparse
import pickle
import sys
from collections import defaultdict

import numpy as np

CACHE = "reports/niche/.timing_cache.pkl"
SEED = 20260714
LAG = 5
THETA = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05, "ufc": .05,
         "esports": .05, "politics": .04, "crypto": .07, "weather": .05, "other": .05}
SPORTS = ("soccer", "mlb", "tennis", "esports", "nba", "nhl", "ufc")


def fee(p, n):
    return THETA.get(n, .05) * p * (1 - p)


def band(p):
    return min(int(p * 5), 4)


def boot(vals, n_boot=4000, seed=SEED):
    a = np.array(vals, float)
    if len(a) < 20:
        return None
    rng = np.random.default_rng(seed)
    bs = a[rng.integers(0, len(a), (n_boot, len(a)))].mean(1)
    return {"mean": float(a.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p": float((bs <= 0).mean()), "n": len(a)}


def self_test():
    # same-outcome pairs can NEVER produce a win-rate difference
    A = [{"oi": "0", "won": 1.0}]
    B = [{"oi": "0", "won": 1.0}, {"oi": "0", "won": 1.0}]
    assert np.mean([x["won"] for x in A]) - np.mean([x["won"] for x in B]) == 0.0

    # a different-outcome blind print is the ONLY way D(won) can move
    B2 = [{"oi": "1", "won": 0.0}]
    assert np.mean([x["won"] for x in A]) - np.mean([x["won"] for x in B2]) == 1.0

    # volume weighting: 1 quiet winning print vs 9 noisy losing prints on the other side
    B3 = [{"oi": "0", "won": 1.0}] + [{"oi": "1", "won": 0.0}] * 9
    per_print = np.mean([x["won"] for x in B3])                       # 0.10  <- volume-weighted
    per_opp = np.mean([np.mean([x["won"] for x in B3 if x["oi"] == o])
                       for o in sorted({x["oi"] for x in B3})])       # 0.50  <- opportunity-weighted
    assert abs(per_print - 0.10) < 1e-9 and abs(per_opp - 0.50) < 1e-9, \
        "print-weighting vs opportunity-weighting must differ -- that is the whole hypothesis"
    print("self-test OK  (print-weighting and opportunity-weighting are distinguishable)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    with open(CACHE, "rb") as f:
        sigs, takers, wonmap, niche_of, depth_of, rosterset = pickle.load(f)

    copy_rows = []
    for s in sigs:
        cid, oi, n = s["condition_id"], s["outcome_index"], s["niche"]
        t0, w0 = float(s["t"]), s["wallet"]
        nxt = next(((t, p) for (t, p, w) in takers.get((cid, oi), [])
                    if t >= t0 + LAG and w != w0), None)
        if nxt is None:
            continue
        tx, px = nxt
        copy_rows.append({"cid": cid, "oi": oi, "niche": n, "band": band(px), "t": tx, "p": px,
                          "won": float(s["won"]), "net": float(s["won"]) - px - fee(px, n)})
    blind_rows = []
    for (cid, oi), prints in takers.items():
        w = wonmap.get((cid, oi))
        if w is None:
            continue
        n = niche_of[cid]
        for (t, p, wal) in prints:
            if wal in rosterset:
                continue
            blind_rows.append({"cid": cid, "oi": oi, "niche": n, "band": band(p), "t": t, "p": p,
                               "won": w, "net": w - p - fee(p, n)})
    bl_by_mkt = defaultdict(list)
    for r in blind_rows:
        bl_by_mkt[r["cid"]].append(r)

    # ==================================================================== D1 + D2
    print("=" * 96)
    print("D1/D2 -- IS THE TIME-MATCHED BLIND LEG EVEN ON THE SAME OUTCOME?   (band 80-100c)")
    print("=" * 96)
    for tau in (300, 1800, 7200):
        same = diff = 0
        dwon_same, dwon_diff = [], []
        for r in copy_rows:
            if r["band"] != 4:
                continue
            cand = [b for b in bl_by_mkt.get(r["cid"], [])
                    if b["band"] == 4 and abs(b["t"] - r["t"]) <= tau]
            for b in cand:
                if b["oi"] == r["oi"]:
                    same += 1
                    dwon_same.append(r["won"] - b["won"])
                else:
                    diff += 1
                    dwon_diff.append(r["won"] - b["won"])
        tot = same + diff
        if not tot:
            continue
        print(f"  tau={tau//60:>3}min   same-outcome {same:>7,} ({same/tot:6.2%})   "
              f"DIFFERENT-outcome {diff:>7,} ({diff/tot:6.2%})")
        print(f"              D(won) | same-outcome prints = {np.mean(dwon_same):+.4f}  "
              f"(MUST be 0.0)")
        if dwon_diff:
            print(f"              D(won) | diff-outcome prints = {np.mean(dwon_diff):+.4f}  "
                  f"<- the ENTIRE effect lives here")
    print("\n  If 'different-outcome' is a small fraction of prints but carries all of D(won), the")
    print("  headline is a LEAD-CHANGE / VOLUME-WEIGHTING effect, not selection skill.\n")

    # ==================================================================== D3
    print("=" * 96)
    print("D3 -- OPPORTUNITY-WEIGHTED blind  (<=1 blind entry per (market,outcome): a noisy")
    print("      lead-change can no longer outvote a quiet favourite)")
    print("=" * 96)
    print(f"{'cell':>22s} {'weighting':>14s} {'SURPLUS':>9s} {'95% CI':>18s} {'p':>6s} | "
          f"{'D(won)':>8s} {'mkts':>6s}")
    print("-" * 96)

    for nm, sel in [("band 80-100c", lambda r: r["band"] == 4),
                    ("FAV 80-100 x SPORTS", lambda r: r["band"] == 4 and r["niche"] in SPORTS),
                    ("band 60-80c", lambda r: r["band"] == 3)]:
        for wlab in ("per-PRINT", "per-OPPORTUNITY"):
            pm = defaultdict(lambda: [[], []])
            for r in copy_rows:
                if not sel(r):
                    continue
                cand = [b for b in bl_by_mkt.get(r["cid"], []) if sel(b)]
                if not cand:
                    continue
                pm[r["cid"]][0].append(r)
                pm[r["cid"]][1].extend(cand)
            dn, dw = [], []
            for m, (A, B) in pm.items():
                if not A or not B:
                    continue
                if wlab == "per-PRINT":
                    bn = np.mean([x["net"] for x in B])
                    bw = np.mean([x["won"] for x in B])
                else:
                    # collapse each (market,outcome) to ONE blind entry first, then average
                    byo = defaultdict(list)
                    for x in B:
                        byo[x["oi"]].append(x)
                    bn = np.mean([np.mean([x["net"] for x in v]) for v in byo.values()])
                    bw = np.mean([np.mean([x["won"] for x in v]) for v in byo.values()])
                dn.append(np.mean([x["net"] for x in A]) - bn)
                dw.append(np.mean([x["won"] for x in A]) - bw)
            rn, rw = boot(dn), boot(dw)
            if not rn:
                continue
            print(f"{nm:>22s} {wlab:>14s} {rn['mean']:>+9.4f} [{rn['lo']:+.4f},{rn['hi']:+.4f}] "
                  f"{rn['p']:>6.3f} | {rw['mean']:>+8.4f} {rn['n']:>6,}")
        print()

    print("  If the surplus SURVIVES opportunity-weighting, the roster really does pick the right")
    print("  side. If it COLLAPSES, the headline was counting the losing side's prints many times.\n")


if __name__ == "__main__":
    main()
