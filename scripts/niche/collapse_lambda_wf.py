#!/usr/bin/env python3
"""
IS THE COLLAPSE EDGE INFORMATION OR VARIANCE?  (the single most important test of the forensics run)

The champion `favorite` runs at k=0 because lambda~0.14 [0.06,0.28] — ~86% of its "edge" is variance
premium, not information — AND that lambda was itself INDETERMINATE (20% trajectory coverage, fallback-
dominated). This asks the same question of the collapse model, but with two advantages the champion
never had: (1) we hold the FULL intl price path per market (harvest_fills), so CLV coverage is ~100%,
not 20%; (2) we can do a PROPER walk-forward, not one A/B split (ITER-5 died at exactly this step:
single-split +1.58% but walk-forward -2.75%).

Three tests, all on the intl book, clean settlement (trader_fills.outcome_won), market-clustered:

  A) WALK-FORWARD. Sort markets by last-harvest ts; expanding-window folds (>=3). Retrain the HGB
     each fold, test on the next block, at the price actually on offer + verified fee. Pooled OOS ROI.
     Kill: pooled walk-forward mean <= 0 => the +4.14% single-split intl edge was a lucky window.

  B) LAMBDA / info-vs-variance. For each OOS model-selected decision point: entry = price at the
     decision; close = the LAST non-degenerate print (in [0.02,0.98]) STRICTLY AFTER the decision
     time (a real forward CLV, degenerate-guarded like clv_lambda.py); surplus = won - entry;
     CLV = close - entry (value the market later confirmed); residual = won - close (variance).
     lambda = mean_CLV / mean_surplus, market-clustered bootstrap CI. Coverage reported.
     Kill: lambda CI lower bound <= 0 => the edge is variance, size nothing (same disease as champion).

  C) BRIER-BEAT, OUT OF TIME. Pooled OOS: model Brier vs the market price's Brier at the SAME
     decision points. A model that only harvests variance cannot beat the market's own price.

  ./collapse_lambda_wf.py --self-test
  ./collapse_lambda_wf.py --folds 4          # full run (re-queries DB, caches to reports/niche/)
"""
import argparse
import os
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse_risk as C  # noqa: E402  (psql, featurize, fee, q_lit, SPORTS, BAND_LO, MAX_DP, SEED)

GUARD_LO, GUARD_HI = 0.02, 0.98
WF_CACHE = "reports/niche/.collapse_wf_cache.pkl"


def build_wf(limit_mkts=0):
    """Like collapse_risk.build but ALSO records, per decision point: the decision epoch t, and the
    market's forward close (last non-degenerate print strictly after t). Cached separately."""
    if os.path.exists(WF_CACHE):
        print(f"loading wf cache {WF_CACHE}")
        with open(WF_CACHE, "rb") as f:
            return pickle.load(f)

    mk = C.psql(f"""
        SELECT m.condition_id, m.niche, w.mts
        FROM harvest_markets m
        JOIN (SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) w USING (condition_id)
        WHERE NOT m.truncated AND m.niche IN ({C.q_lit(C.SPORTS)})
        ORDER BY m.condition_id
        {'LIMIT ' + str(limit_mkts) if limit_mkts else ''};""")
    print(f"{len(mk):,} sports markets")
    niche_of = {r["condition_id"]: r["niche"] for r in mk}
    mts_of = {r["condition_id"]: float(r["mts"]) for r in mk}
    mkts = [r["condition_id"] for r in mk]

    rows, rng = [], np.random.default_rng(C.SEED)
    for i in range(0, len(mkts), C.BATCH):
        ch = mkts[i:i + C.BATCH]
        tape = defaultdict(list)
        for r in C.psql(f"""
              SELECT condition_id, outcome_index, EXTRACT(EPOCH FROM ts) t, price p
              FROM harvest_fills
              WHERE side='BUY' AND is_maker=false AND condition_id IN ({C.q_lit(ch)});"""):
            tape[(r["condition_id"], r["outcome_index"])].append((float(r["t"]), float(r["p"])))
        won = {}
        for r in C.psql(f"""
              SELECT condition_id, outcome_index, BOOL_OR(outcome_won)::int w
              FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL
                AND condition_id IN ({C.q_lit(ch)}) GROUP BY 1,2;"""):
            won[(r["condition_id"], r["outcome_index"])] = float(r["w"])

        for k, tp in tape.items():
            if k not in won or len(tp) < 5:
                continue
            tp.sort()
            cand = [j for j, (t, p) in enumerate(tp) if p >= C.BAND_LO]
            if not cand:
                continue
            pick = cand if len(cand) <= C.MAX_DP else list(rng.choice(cand, C.MAX_DP, replace=False))
            cid, oi = k
            n = niche_of[cid]
            # forward closes: for each print, precompute is easier per decision point
            for j in sorted(pick):
                t_dec = tp[j][0]
                p = tp[j][1]
                # forward close = last non-degenerate print strictly after the decision time
                close = None
                for (tt, pp) in reversed(tp):
                    if tt > t_dec and GUARD_LO <= pp <= GUARD_HI:
                        close = pp
                        break
                rows.append({"cid": cid, "oi": oi, "niche": n, "mts": mts_of[cid],
                             "t": t_dec, "x": C.featurize(tp, j, n), "y": won[k], "p": p,
                             "net": won[k] - p - C.fee(p, n), "close": close})
        sys.stdout.write(f"\r  {min(i+C.BATCH, len(mkts)):,}/{len(mkts):,} markets  {len(rows):,} rows")
        sys.stdout.flush()
    print()
    os.makedirs(os.path.dirname(WF_CACHE), exist_ok=True)
    with open(WF_CACHE, "wb") as f:
        pickle.dump(rows, f)
    return rows


def boot_by_market(rows, n_boot=3000, seed=C.SEED):
    """rows = [(cid, value)] -> market-clustered mean + 95% CI + p(mean<=0)."""
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


def roi_by_market(rows, n_boot=3000, seed=C.SEED):
    """rows = [(cid, net, p)] -> market-clustered ROI-on-turnover + CI."""
    by = defaultdict(lambda: [0.0, 0.0])
    for cid, net, p in rows:
        by[cid][0] += net
        by[cid][1] += p
    mkts = list(by)
    if len(mkts) < 20:
        return None
    roi = np.array([by[m][0] / by[m][1] for m in mkts if by[m][1] > 0], float)
    rng = np.random.default_rng(seed)
    bs = roi[rng.integers(0, len(roi), (n_boot, len(roi)))].mean(1)
    return {"roi": float(roi.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p": float((bs <= 0).mean()), "n_markets": len(mkts)}


def self_test():
    C.self_test()
    # forward-close routing: last non-degenerate print strictly after t_dec
    tp = [(0, .5), (10, .85), (20, .90), (30, .99), (40, .97)]
    # decision at index 1 (t=10): forward closes at t>10 non-degenerate in [.02,.98] -> last is .97 (t=40)
    close = None
    for (tt, pp) in reversed(tp):
        if tt > 10 and GUARD_LO <= pp <= GUARD_HI:
            close = pp
            break
    assert close == .97, close
    # boot ROI clusters on market
    r = roi_by_market([("m", 0.05, 0.85)] * 50 + [(f"x{i}", 0.0, 0.85) for i in range(25)])
    assert r["n_markets"] == 26
    print("wf self-test OK (forward-close routing, market-clustered ROI)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--thr", type=float, default=0.01, help="model EV gate for the traded set")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score, brier_score_loss

    rows = build_wf(a.limit)
    print(f"\n{len(rows):,} decision points / {len({r['cid'] for r in rows}):,} markets")

    # ---- order markets by their last-harvest ts (the A/B clock); expanding-window folds
    mkts = sorted({r["cid"] for r in rows}, key=lambda c: next(r["mts"] for r in rows if r["cid"] == c))
    mts_of = {r["cid"]: r["mts"] for r in rows}
    order = sorted(mkts, key=lambda c: mts_of[c])
    n = len(order)
    K = a.folds
    # fold b (1..K-1): train on first (b/(K+1)) ... test on the next 1/(K+1) block -> expanding train
    # simplest robust scheme: split markets into K+1 equal time-blocks; fold b trains on blocks[0..b],
    # tests on block b+1. Gives K OOS folds, each strictly later than its training data.
    edges = [int(round(x)) for x in np.linspace(0, n, K + 2)]
    blocks = [set(order[edges[i]:edges[i + 1]]) for i in range(K + 1)]

    def rows_in(cids):
        return [r for r in rows if r["cid"] in cids]

    print(f"\nWALK-FORWARD: {K} expanding folds over {n:,} markets "
          f"(each test block strictly later than its train)\n")
    print(f"{'fold':>4s} {'train mk':>9s} {'test mk':>8s} {'blind ROI':>10s} "
          f"{'model ROI':>10s} {'model CI':>20s} {'p':>6s} {'AUC':>6s}")
    print("-" * 82)
    pooled_model, pooled_blind, pooled_lambda_rows = [], [], []
    pooled_brier_model, pooled_brier_mkt = [], []
    fold_rois = []
    for b in range(1, K + 1):
        train_cids = set().union(*blocks[:b])
        test_cids = blocks[b]
        A_ = rows_in(train_cids)
        B_ = rows_in(test_cids)
        if len(A_) < 500 or len(B_) < 200:
            continue
        Xa = np.array([r["x"] for r in A_], float)
        ya = np.array([r["y"] for r in A_], float)
        Xb = np.array([r["x"] for r in B_], float)
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
                                             min_samples_leaf=80, l2_regularization=1.0,
                                             random_state=C.SEED)
        clf.fit(Xa, ya)
        pw = clf.predict_proba(Xb)[:, 1]
        ev = np.array([pw[i] - B_[i]["p"] - C.fee(B_[i]["p"], B_[i]["niche"]) for i in range(len(B_))])
        yb = np.array([r["y"] for r in B_], float)

        blind = [(B_[i]["cid"], B_[i]["net"], B_[i]["p"]) for i in range(len(B_))]
        model = [(B_[i]["cid"], B_[i]["net"], B_[i]["p"]) for i in range(len(B_)) if ev[i] > a.thr]
        rb = roi_by_market(blind)
        rm = roi_by_market(model)
        auc = roc_auc_score(yb, pw) if len(set(yb)) > 1 else float("nan")
        pooled_blind += blind
        pooled_model += model
        if rm:
            fold_rois.append(rm["roi"])
        # lambda rows for OOS model-selected with a valid forward close
        for i in range(len(B_)):
            if ev[i] > a.thr and B_[i]["close"] is not None:
                pooled_lambda_rows.append((B_[i]["cid"], B_[i]["p"], B_[i]["y"], B_[i]["close"]))
        # brier at OOS model-selected points
        for i in range(len(B_)):
            if ev[i] > a.thr:
                pooled_brier_model.append((yb[i], pw[i]))
                pooled_brier_mkt.append((yb[i], B_[i]["p"]))
        print(f"{b:>4d} {len(train_cids):>9,} {len(test_cids):>8,} "
              f"{(rb['roi']*100 if rb else float('nan')):>+9.2f}% "
              f"{(rm['roi']*100 if rm else float('nan')):>+9.2f}% "
              f"[{(rm['lo']*100 if rm else 0):+.2f},{(rm['hi']*100 if rm else 0):+.2f}] "
              f"{(rm['p'] if rm else float('nan')):>6.3f} {auc:>6.3f}")

    print("-" * 82)
    rmp = roi_by_market(pooled_model)
    rbp = roi_by_market(pooled_blind)
    print(f"POOLED walk-forward   blind ROI {rbp['roi']*100:+.2f}% "
          f"[{rbp['lo']*100:+.2f},{rbp['hi']*100:+.2f}]   "
          f"MODEL ROI {rmp['roi']*100:+.2f}% [{rmp['lo']*100:+.2f},{rmp['hi']*100:+.2f}] "
          f"p={rmp['p']:.3f}  ({rmp['n_markets']} mkts)")
    if fold_rois:
        print(f"  per-fold model ROI: {['%+.2f%%' % (x*100) for x in fold_rois]}  "
              f"min={min(fold_rois)*100:+.2f}%  (all folds > 0 ? {all(x > 0 for x in fold_rois)})")

    # ---- LAMBDA on pooled OOS model-selected
    print("\n" + "=" * 82)
    print("LAMBDA — info vs variance on the pooled walk-forward MODEL selections (EV>%.2f)" % a.thr)
    print("=" * 82)
    lam_rows = pooled_lambda_rows
    n_sel_total = len(pooled_model)
    cov = len(lam_rows) / n_sel_total if n_sel_total else 0.0
    by_m = defaultdict(lambda: {"clv": [], "sur": []})
    for cid, entry, won, close in lam_rows:
        by_m[cid]["clv"].append(close - entry)
        by_m[cid]["sur"].append(won - entry)
    mkeys = list(by_m)
    clv_m = np.array([np.mean(by_m[m]["clv"]) for m in mkeys])
    sur_m = np.array([np.mean(by_m[m]["sur"]) for m in mkeys])
    mean_clv, mean_sur = float(clv_m.mean()), float(sur_m.mean())
    resid = mean_sur - mean_clv
    rng = np.random.default_rng(C.SEED)
    idx = rng.integers(0, len(mkeys), (4000, len(mkeys)))
    clv_bs = clv_m[idx].mean(1)
    lam_bs = np.clip(clv_bs / np.maximum(sur_m[idx].mean(1), 1e-9), 0, 1)
    lam_hat = max(0.0, min(1.0, mean_clv / mean_sur)) if mean_sur > 0 else float("nan")
    print(f"  forward-close coverage: {cov:.1%}  ({len(lam_rows):,} of {n_sel_total:,} selections)")
    print(f"  mean surplus (won-entry)   = {mean_sur:+.4f}")
    print(f"  mean CLV     (close-entry) = {mean_clv:+.4f}   95% CI "
          f"[{np.percentile(clv_bs,2.5):+.4f},{np.percentile(clv_bs,97.5):+.4f}]  "
          f"p(CLV<=0)={float((clv_bs<=0).mean()):.3f}")
    print(f"  residual     (won-close)   = {resid:+.4f}   (variance/static premium)")
    print(f"  lambda_hat = CLV/surplus   = {lam_hat:.3f}   95% CI "
          f"[{np.percentile(lam_bs,2.5):.3f},{np.percentile(lam_bs,97.5):.3f}]")
    lam_lo = float(np.percentile(lam_bs, 2.5))
    clv_lo = float(np.percentile(clv_bs, 2.5))
    print(f"  >> {'INFORMATION (CLV LB>0)' if clv_lo > 0 else 'NOT proven information (CLV CI includes 0)'}"
          f" — lambda LB={lam_lo:.3f}")

    # ---- BRIER-BEAT out of time
    print("\n" + "=" * 82)
    print("BRIER-BEAT (pooled OOS model-selected): does the model's prob beat the market price?")
    print("=" * 82)
    if pooled_brier_model:
        ym = np.array([x[0] for x in pooled_brier_model])
        pm = np.array([x[1] for x in pooled_brier_model])
        pk = np.array([x[1] for x in pooled_brier_mkt])
        bm = float(brier_score_loss(ym, np.clip(pm, 0, 1)))
        bk = float(brier_score_loss(ym, np.clip(pk, 0, 1)))
        print(f"  n={len(ym):,}   model Brier {bm:.4f}   market-price Brier {bk:.4f}   "
              f"{'MODEL BEATS MARKET' if bm < bk else 'market wins'} (lower=better)")


if __name__ == "__main__":
    main()
