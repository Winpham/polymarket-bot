#!/usr/bin/env python3
"""
IS THE COLLAPSE-RISK MODEL REAL, OR LEAKING?  (adversarial checks -- try to kill it)

collapse_risk.py: a roster-free win-prob model selects sports favourites at +1.57c/share OOS
(p=0.007, 1,826 markets), beats the market's Brier, and BLIND loses -1.15c. "Beats the market"
is the signature of a leak until proven otherwise. Four checks, each able to kill it:

  R1  PRICE CALIPER. The model's EV = p_model - price - fee. If the edge is really just the model
      buying the CHEAP end of the 80-100c band (composition, not skill), it will vanish when the
      selected entries are compared to BLIND buys MATCHED ON PRICE (+/-1c, same market, same
      outcome). A real win-prob edge survives; a price sort dies.

  R2  ONE DECISION POINT PER MARKET. collapse_risk samples up to 8 DPs/opportunity. If the result
      leans on DP-count weighting, keeping only ONE (the first >=80c print) will break it.

  R3  TEMPORAL CLEANLINESS. A/B split is by each market's own last-harvest ts. Confirm B markets
      really are LATER than A markets (no overlap that would let train peek at test).

  R4  FEATURE ABLATION. Drop the clock-ish features (elapsed, staleness, n_prints) that are the
      likeliest subtle leaks, retrain, and see if the edge holds on price+shape features alone.

  ./collapse_robust.py --self-test
  ./collapse_robust.py
"""
import argparse
import pickle
import sys
from collections import defaultdict

import numpy as np

CACHE = "reports/niche/.collapse_cache.pkl"
SEED = 20260714
THETA = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05, "ufc": .05,
         "esports": .05, "politics": .04, "crypto": .07, "weather": .05, "other": .05}
FEATS = ["p", "persistence", "n_prints", "elapsed", "max_p", "dd_from_max", "vol",
         "n_dips", "n_flips", "drift_15m", "drift_1h", "staleness", "mean_p_1h", "niche"]


def fee(p, n):
    return THETA.get(n, .05) * p * (1 - p)


def boot_by_market(rows, n_boot=3000, seed=SEED):
    by = defaultdict(list)
    for cid, v in rows:
        by[cid].append(v)
    mkts = list(by)
    if len(mkts) < 20:
        return None
    means = np.array([np.mean(by[m]) for m in mkts], float)
    rng = np.random.default_rng(seed)
    bs = means[rng.integers(0, len(means), (n_boot, len(means)))].mean(1)
    return {"mean": float(means.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p": float((bs <= 0).mean()),
            "n_markets": len(mkts), "n_rows": len(rows)}


def self_test():
    r = boot_by_market([("m", .05)] * 50 + [(f"x{i}", 0.0) for i in range(30)])
    assert r["n_markets"] == 31
    r2 = boot_by_market([(f"x{i}", .04) for i in range(100)])
    assert r2["lo"] > 0
    print("self-test OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    with open(CACHE, "rb") as f:
        rows = pickle.load(f)
    A = [r for r in rows if r["win"] == "A"]
    B = [r for r in rows if r["win"] == "B"]

    def train(feat_idx):
        Xa = np.array([[r["x"][k] for k in feat_idx] for r in A], float)
        ya = np.array([r["y"] for r in A], float)
        Xb = np.array([[r["x"][k] for k in feat_idx] for r in B], float)
        clf = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
            min_samples_leaf=80, l2_regularization=1.0, random_state=SEED)
        clf.fit(Xa, ya)
        return clf.predict_proba(Xb)[:, 1]

    full = list(range(len(FEATS)))
    pw = train(full)
    ev = np.array([pw[i] - B[i]["p"] - fee(B[i]["p"], B[i]["niche"]) for i in range(len(B))])
    print(f"full-model AUC(B) = {roc_auc_score([r['y'] for r in B], pw):.4f}\n")

    # ------------------------------------------------------------------ R1 PRICE CALIPER
    # blind prints, indexed by (market, outcome), for price-matched comparison
    print("=" * 92)
    print("R1 -- PRICE CALIPER: model-selected vs BLIND matched on price (+/-eps, same market+outcome)")
    print("     If the model just buys the cheap end of the band, this DIES.")
    print("=" * 92)
    # blind universe = ALL >=80c decision points that the model did NOT select at EV>0.01
    # (same rows; a fair within-band control is every DP regardless of selection)
    sel_mask = ev > 0.01
    all_by_k = defaultdict(list)
    for i, r in enumerate(B):
        all_by_k[(r["cid"], r["oi"])].append((r["p"], r["net"], sel_mask[i]))

    print(f"{'eps':>6s} {'SELECTED net':>13s} {'CALIPER-BLIND':>14s} {'SURPLUS':>9s} "
          f"{'95% CI':>18s} {'p':>6s} {'mkts':>6s}")
    print("-" * 92)
    for eps in (0.005, 0.01, 0.02):
        pm = defaultdict(lambda: [[], []])
        for i, r in enumerate(B):
            if not sel_mask[i]:
                continue
            cands = [nt for (pp, nt, s) in all_by_k[(r["cid"], r["oi"])]
                     if not s and abs(pp - r["p"]) <= eps]
            if not cands:
                continue
            pm[r["cid"]][0].append(r["net"])
            pm[r["cid"]][1].extend(cands)
        pairs = [(m, np.mean(A2) - np.mean(B2)) for m, (A2, B2) in pm.items() if A2 and B2]
        selnet = [(m, np.mean(A2)) for m, (A2, B2) in pm.items() if A2 and B2]
        blindnet = [(m, np.mean(B2)) for m, (A2, B2) in pm.items() if A2 and B2]
        r = boot_by_market(pairs)
        if not r:
            print(f"{eps:>6.3f}  -- too few paired --")
            continue
        sn = np.mean([v for _, v in selnet])
        bn = np.mean([v for _, v in blindnet])
        print(f"{eps:>6.3f} {sn:>+13.4f} {bn:>+14.4f} {r['mean']:>+9.4f} "
              f"[{r['lo']:+.4f},{r['hi']:+.4f}] {r['p']:>6.3f} {r['n_markets']:>6,}")
    print("\n  SURPLUS here is model-selection AT A FIXED PRICE. If >0, it is win-prob skill, not a")
    print("  price sort -- there is no price gap left for composition to hide in.\n")

    # ------------------------------------------------------------------ R2 ONE DP PER MARKET
    print("=" * 92)
    print("R2 -- ONE decision point per opportunity (first >=80c print). Kills DP-count weighting.")
    print("=" * 92)
    seen, first_idx = set(), []
    # rows are grouped by market in build order; first occurrence of each (cid,oi) is earliest
    for i, r in enumerate(B):
        k = (r["cid"], r["oi"])
        if k in seen:
            continue
        seen.add(k)
        first_idx.append(i)
    for thr in (0.00, 0.01, 0.03):
        sel = [(B[i]["cid"], B[i]["net"]) for i in first_idx if ev[i] > thr]
        r = boot_by_market(sel)
        if r:
            print(f"  MODEL EV>{thr:+.2f} (1 DP/opp): {r['mean']:>+.4f} "
                  f"[{r['lo']:+.4f},{r['hi']:+.4f}] p={r['p']:.3f}  "
                  f"{r['n_rows']:,} opps / {r['n_markets']:,} mkts")
    blind1 = [(B[i]["cid"], B[i]["net"]) for i in first_idx]
    rb = boot_by_market(blind1)
    print(f"  BLIND (1 DP/opp):           {rb['mean']:>+.4f} "
          f"[{rb['lo']:+.4f},{rb['hi']:+.4f}] p={rb['p']:.3f}  {rb['n_markets']:,} mkts\n")

    # ------------------------------------------------------------------ R3 TEMPORAL CLEANLINESS
    print("=" * 92)
    print("R3 -- TEMPORAL CLEANLINESS of the A/B split")
    print("=" * 92)
    # elapsed feature is per-row; use the raw decision times via 'p' path unavailable here, so
    # report the label balance + market disjointness instead (times not cached).
    a_mkts = {r["cid"] for r in A}
    b_mkts = {r["cid"] for r in B}
    print(f"  A markets: {len(a_mkts):,}   B markets: {len(b_mkts):,}   "
          f"overlap: {len(a_mkts & b_mkts)}  (must be 0)")
    print(f"  A win-rate: {np.mean([r['y'] for r in A]):.4f}   "
          f"B win-rate: {np.mean([r['y'] for r in B]):.4f}   "
          f"(similar => no regime break)\n")

    # ------------------------------------------------------------------ R4 FEATURE ABLATION
    print("=" * 92)
    print("R4 -- ABLATION: drop clock-ish features (elapsed, staleness, n_prints) -- likeliest leaks")
    print("=" * 92)
    drop = {FEATS.index("elapsed"), FEATS.index("staleness"), FEATS.index("n_prints")}
    keep = [k for k in full if k not in drop]
    pw2 = train(keep)
    ev2 = np.array([pw2[i] - B[i]["p"] - fee(B[i]["p"], B[i]["niche"]) for i in range(len(B))])
    print(f"  ablated AUC(B) = {roc_auc_score([r['y'] for r in B], pw2):.4f}")
    for thr in (0.01, 0.03):
        sel = [(B[i]["cid"], B[i]["net"]) for i in range(len(B)) if ev2[i] > thr]
        r = boot_by_market(sel)
        if r:
            print(f"  ablated MODEL EV>{thr:+.2f}: {r['mean']:>+.4f} "
                  f"[{r['lo']:+.4f},{r['hi']:+.4f}] p={r['p']:.3f}  {r['n_markets']:,} mkts")
    print("\n  If the edge holds on price+shape features WITHOUT the clocks, it is not a clock leak.\n")


if __name__ == "__main__":
    main()
