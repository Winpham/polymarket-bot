#!/usr/bin/env python3
"""
INTERNATIONAL COPY-EDGE RE-VERIFICATION HARNESS.

The collapse/copy edge on the intl book is a measured NULL:
  walk-forward ROI +1.34% [+0.40,+2.25]  (vs +4.14% single-split),
  lambda = 0.000 [0.000, 0.141] @ 94% forward-close coverage,
  Brier-beat FAILS out of sample.
Original run: scripts/niche/collapse_lambda_wf.py --folds 4 (cached in .collapse_wf_cache.pkl).

This harness re-runs the SAME walk-forward + lambda + Brier machinery on arbitrary
row-SUBSETS of that cache, so we can stress the two artefact hypotheses the user raised:
  (a) data-loss / ingestion break, (b) a thin-games / low-volume window,
and search for ANY regime/subpopulation where lambda > 0 that GENERALISES.

Every metric is computed the SAME way as the original (market-clustered bootstrap,
verified fee, leak-free as-of features from the cache, expanding-window folds), so
numbers are directly comparable. Nothing is re-selected in-sample: a positive cell must
survive its own walk-forward AND (test 3) an out-of-cohort re-fit + multiplicity control.

  ./intl_reverify.py --self-test          # asserts full-cache reproduction of the null
  ./intl_reverify.py --test thin          # thin-window sensitivity
  ./intl_reverify.py --test regime        # per-niche / band / vol / time-block + BH
"""
import argparse
import os
import pickle
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse_risk as C          # noqa: E402
import collapse_lambda_wf as WF    # noqa: E402

CACHE = "reports/niche/.collapse_wf_cache.pkl"


def load(cache=CACHE):
    with open(cache, "rb") as f:
        return pickle.load(f)


def dstr(x):
    return datetime.fromtimestamp(x, timezone.utc).strftime("%Y-%m-%d")


def roi_by_market(sel, seed=C.SEED, n_boot=3000):
    """sel = [(cid, net, p)] -> market-clustered ROI-on-turnover + CI + p(<=0)."""
    by = defaultdict(lambda: [0.0, 0.0])
    for cid, net, p in sel:
        by[cid][0] += net
        by[cid][1] += p
    roi = np.array([by[m][0] / by[m][1] for m in by if by[m][1] > 0], float)
    if len(roi) < 20:
        return None
    rng = np.random.default_rng(seed)
    bs = roi[rng.integers(0, len(roi), (n_boot, len(roi)))].mean(1)
    return {"roi": float(roi.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p": float((bs <= 0).mean()),
            "n_markets": int(len(roi))}


def run(rows, folds=4, thr=0.01, seed=C.SEED):
    """Replicate collapse_lambda_wf.main() on an arbitrary row subset.
    Returns the pooled walk-forward ROI, lambda, coverage and Brier-beat, all comparable
    to the original run. Returns None if the subset is too thin to fold."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score, brier_score_loss

    mkts_set = {r["cid"] for r in rows}
    if len(mkts_set) < 200:
        return {"error": f"too few markets ({len(mkts_set)})", "n_markets": len(mkts_set),
                "n_rows": len(rows)}
    mts_of = {r["cid"]: r["mts"] for r in rows}
    # replicate collapse_lambda_wf.main() ordering EXACTLY (two-step sort by mts) so the
    # full-cache run reproduces byte-for-byte; ties resolved identically to the original.
    mkts = sorted(mkts_set, key=lambda c: mts_of[c])
    order = sorted(mkts, key=lambda c: mts_of[c])
    n = len(order)
    K = folds
    edges = [int(round(x)) for x in np.linspace(0, n, K + 2)]
    blocks = [set(order[edges[i]:edges[i + 1]]) for i in range(K + 1)]

    def rows_in(cids):
        return [r for r in rows if r["cid"] in cids]

    pooled_model, pooled_blind, pooled_lambda_rows = [], [], []
    pooled_bm, pooled_bk, fold_rois, fold_meta = [], [], [], []
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
                                             random_state=seed)
        clf.fit(Xa, ya)
        pw = clf.predict_proba(Xb)[:, 1]
        ev = np.array([pw[i] - B_[i]["p"] - C.fee(B_[i]["p"], B_[i]["niche"]) for i in range(len(B_))])
        yb = np.array([r["y"] for r in B_], float)
        blind = [(B_[i]["cid"], B_[i]["net"], B_[i]["p"]) for i in range(len(B_))]
        model = [(B_[i]["cid"], B_[i]["net"], B_[i]["p"]) for i in range(len(B_)) if ev[i] > thr]
        pooled_blind += blind
        pooled_model += model
        rm = roi_by_market(model, seed)
        if rm:
            fold_rois.append(rm["roi"])
        fold_meta.append({"fold": b, "train_mk": len(train_cids), "test_mk": len(test_cids),
                          "model_roi": rm["roi"] if rm else None,
                          "auc": float(roc_auc_score(yb, pw)) if len(set(yb)) > 1 else None})
        for i in range(len(B_)):
            if ev[i] > thr:
                if B_[i]["close"] is not None:
                    pooled_lambda_rows.append((B_[i]["cid"], B_[i]["p"], B_[i]["y"], B_[i]["close"]))
                pooled_bm.append((yb[i], pw[i]))
                pooled_bk.append((yb[i], B_[i]["p"]))

    rmp = roi_by_market(pooled_model, seed)
    rbp = roi_by_market(pooled_blind, seed)
    n_sel = len(pooled_model)
    cov = len(pooled_lambda_rows) / n_sel if n_sel else 0.0

    # lambda
    lam = clv = clv_lo = clv_hi = lam_lo = lam_hi = clv_p = float("nan")
    if len(pooled_lambda_rows) >= 20:
        by_m = defaultdict(lambda: {"clv": [], "sur": []})
        for cid, entry, won, close in pooled_lambda_rows:
            by_m[cid]["clv"].append(close - entry)
            by_m[cid]["sur"].append(won - entry)
        mkeys = list(by_m)
        clv_m = np.array([np.mean(by_m[m]["clv"]) for m in mkeys])
        sur_m = np.array([np.mean(by_m[m]["sur"]) for m in mkeys])
        mean_clv, mean_sur = float(clv_m.mean()), float(sur_m.mean())
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, len(mkeys), (4000, len(mkeys)))
        clv_bs = clv_m[idx].mean(1)
        lam_bs = np.clip(clv_bs / np.maximum(sur_m[idx].mean(1), 1e-9), 0, 1)
        lam = max(0.0, min(1.0, mean_clv / mean_sur)) if mean_sur > 0 else float("nan")
        clv = mean_clv
        clv_lo, clv_hi = float(np.percentile(clv_bs, 2.5)), float(np.percentile(clv_bs, 97.5))
        lam_lo, lam_hi = float(np.percentile(lam_bs, 2.5)), float(np.percentile(lam_bs, 97.5))
        clv_p = float((clv_bs <= 0).mean())   # one-sided p: P(mean CLV <= 0) under bootstrap

    bm = bk = float("nan")
    if pooled_bm:
        ym = np.array([x[0] for x in pooled_bm]); pm = np.array([x[1] for x in pooled_bm])
        pk = np.array([x[1] for x in pooled_bk])
        bm = float(brier_score_loss(ym, np.clip(pm, 0, 1)))
        bk = float(brier_score_loss(ym, np.clip(pk, 0, 1)))

    return {
        "n_rows": len(rows), "n_markets": len(mkts), "n_sel": n_sel,
        "wf_roi": rmp["roi"] if rmp else None, "wf_lo": rmp["lo"] if rmp else None,
        "wf_hi": rmp["hi"] if rmp else None, "wf_p": rmp["p"] if rmp else None,
        "blind_roi": rbp["roi"] if rbp else None,
        "per_fold_roi": fold_rois, "fold_meta": fold_meta,
        "lam": lam, "lam_lo": lam_lo, "lam_hi": lam_hi,
        "clv": clv, "clv_lo": clv_lo, "clv_hi": clv_hi, "clv_p": clv_p, "cov": cov,
        "brier_model": bm, "brier_mkt": bk,
    }


def fmt(r, label=""):
    if r is None:
        return f"{label:>28s}   -- None --"
    if "error" in r:
        return f"{label:>28s}   {r['error']}"
    wf = f"{r['wf_roi']*100:+.2f}% [{r['wf_lo']*100:+.2f},{r['wf_hi']*100:+.2f}] p={r['wf_p']:.3f}" \
        if r['wf_roi'] is not None else "n/a"
    lam = f"{r['lam']:.3f} [{r['lam_lo']:.3f},{r['lam_hi']:.3f}]" if r['lam'] == r['lam'] else "n/a"
    clvlb = f"{r['clv_lo']*100:+.3f}c" if r['clv_lo'] == r['clv_lo'] else "n/a"
    brier = ("MODEL" if r['brier_model'] < r['brier_mkt'] else "mkt") if r['brier_model'] == r['brier_model'] else "n/a"
    return (f"{label:>28s}  mk={r['n_markets']:>5d} sel={r['n_sel']:>6d} cov={r['cov']:.0%}  "
            f"WF {wf}  lam {lam} CLV_lb {clvlb}  Brier:{brier}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--test", default="")
    ap.add_argument("--folds", type=int, default=4)
    a = ap.parse_args()

    if a.self_test:
        rows = load()
        r = run(rows, folds=4)
        print(fmt(r, "FULL CACHE"))
        assert r["n_rows"] == 76551, r["n_rows"]
        assert r["n_markets"] == 10857, r["n_markets"]
        assert abs(r["wf_roi"] - 0.0134) < 0.0005, r["wf_roi"]
        assert r["lam"] == 0.0, r["lam"]
        assert abs(r["lam_hi"] - 0.141) < 0.01, r["lam_hi"]
        assert abs(r["cov"] - 0.944) < 0.005, r["cov"]
        assert r["brier_model"] > r["brier_mkt"], (r["brier_model"], r["brier_mkt"])
        print("SELF-TEST OK: full-cache reproduction of the null matches collapse_lambda_wf")
        return 0

    rows = load()

    if a.test == "thin":
        print("=" * 120)
        print("TEST 2 — THIN-WINDOW SENSITIVITY  (does the null depend on the 07-13/14 ingestion-break days?)")
        print("=" * 120)
        print(fmt(run(rows, a.folds), "0. FULL CACHE (ref)"))
        # markets resolving on the two broken days
        broken = {r["cid"] for r in rows if dstr(r["mts"]) in ("2026-07-13", "2026-07-14")}
        print(f"    [broken-day markets (mts 07-13/14): {len(broken)} of "
              f"{len({r['cid'] for r in rows})}]")
        # (i) exclude the broken days
        print(fmt(run([r for r in rows if r["cid"] not in broken], a.folds),
                  "(i) excl broken days"))
        # (ii) high-volume core: markets resolving 07-01..07-12
        core = [r for r in rows if "2026-07-01" <= dstr(r["mts"]) <= "2026-07-12"]
        print(fmt(run(core, a.folds), "(ii) hi-vol core 0701-0712"))
        # (iii) full pre-crash: everything with mts strictly before 07-13
        pre = [r for r in rows if dstr(r["mts"]) < "2026-07-13"]
        print(fmt(run(pre, a.folds), "(iii) full pre-crash <=0712"))
        # (iv) ALSO drop any decision points whose tape/decision time is on the broken days
        #      (guards against truncated forward closes contaminating lambda)
        clean = [r for r in rows if dstr(r["t"]) < "2026-07-13" and dstr(r["mts"]) < "2026-07-13"]
        print(fmt(run(clean, a.folds), "(iv) decision-t & mts pre-crash"))
        # (v) rich-volume markets only: last two full weeks that had 2-3M fills/day
        rich = [r for r in rows if "2026-06-30" <= dstr(r["mts"]) <= "2026-07-12"]
        print(fmt(run(rich, a.folds), "(v) rich window 0630-0712"))
        return 0

    if a.test == "regime":
        print("=" * 120)
        print("TEST 3 — REGIME / CONDITIONING SEARCH  (any cell with CLV lower-bound > 0 that survives BH?)")
        print("=" * 120)
        cells = {}
        # per niche
        for nz in sorted({r["niche"] for r in rows}):
            cells[f"niche={nz}"] = [r for r in rows if r["niche"] == nz]
        # per price-band (entry price of the decision print)
        bands = [(0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.01)]
        for lo, hi in bands:
            cells[f"band={lo:.2f}-{hi:.2f}"] = [r for r in rows if lo <= r["p"] < hi]
        # per volume-regime: bucket each DECISION POINT by its AS-OF tape depth (n_prints feature,
        # = number of prints strictly up to & incl. the decision). Leak-free: known at decision time.
        # (A per-market count of sampled points would be LOOKAHEAD — only known at settlement.)
        npi = C.FEATS.index("n_prints")
        npv = np.array([r["x"][npi] for r in rows])
        vt = np.percentile(npv, [33, 67])
        cells["vol=thin(asof prints)"] = [r for r in rows if r["x"][npi] <= vt[0]]
        cells["vol=mid(asof prints)"] = [r for r in rows if vt[0] < r["x"][npi] <= vt[1]]
        cells["vol=deep(asof prints)"] = [r for r in rows if r["x"][npi] > vt[1]]
        # per time-block (market resolution week)
        for wk in ("2026-05", "2026-06e", "2026-07a", "2026-07b"):
            if wk == "2026-05":
                sel = [r for r in rows if dstr(r["mts"]) < "2026-06-01"]
            elif wk == "2026-06e":
                sel = [r for r in rows if "2026-06-01" <= dstr(r["mts"]) < "2026-07-01"]
            elif wk == "2026-07a":
                sel = [r for r in rows if "2026-07-01" <= dstr(r["mts"]) < "2026-07-07"]
            else:
                sel = [r for r in rows if "2026-07-07" <= dstr(r["mts"])]
            cells[f"time={wk}"] = sel

        results = {}
        for name, cr in cells.items():
            res = run(cr, a.folds)
            results[name] = res
            print(fmt(res, name))

        # ---- Benjamini-Hochberg on the one-sided CLV p-values (H0: mean CLV <= 0)
        print("\n" + "-" * 120)
        print("MULTIPLICITY CONTROL (Benjamini-Hochberg, FDR=0.05) on one-sided p(mean CLV<=0):")
        pv = [(n, r.get("clv_p")) for n, r in results.items()
              if r and r.get("clv_p") == r.get("clv_p") and r.get("wf_roi") is not None]
        pv = [(n, p) for n, p in pv if p == p]
        pv.sort(key=lambda x: x[1])
        m = len(pv)
        bh_hits = []
        for i, (n, p) in enumerate(pv, 1):
            crit = 0.05 * i / m
            hit = p <= crit
            if hit:
                bh_hits.append(n)
            print(f"  {i:>2d}/{m}  p={p:.4f}  BH-crit={crit:.4f}  {'<== SURVIVES' if hit else ''}  {n}")
        print(f"\n  cells tested: {m}   BH survivors (CLV>0 as information): "
              f"{bh_hits if bh_hits else 'NONE'}")
        # also flag any cell with raw CLV lower-bound > 0 (pre-multiplicity)
        raw = [n for n, r in results.items() if r and r.get("clv_lo") == r.get("clv_lo")
               and r.get("clv_lo", -1) > 0]
        print(f"  cells with raw CLV lower-bound>0 (pre-multiplicity): {raw if raw else 'NONE'}")

        # ---- LOOKAHEAD DIAGNOSTIC: bucket markets by their SETTLEMENT-time sampled-point count.
        # This is NOT tradeable (you can't know a market's final #points at decision time). If it
        # manufactures a fake edge where the as-of partition shows none, that proves the "vol=mid"
        # kind of positive is a lookahead artifact, not a regime.
        print("\n" + "-" * 120)
        print("LOOKAHEAD DIAGNOSTIC (DISQUALIFIED partition: per-market count known only at settlement)")
        cnt = defaultdict(int)
        for r in rows:
            cnt[r["cid"]] += 1
        ct = np.percentile(list(cnt.values()), [33, 67])
        print(fmt(run([r for r in rows if cnt[r["cid"]] <= ct[0]], a.folds), "LA vol=thin"))
        print(fmt(run([r for r in rows if ct[0] < cnt[r["cid"]] <= ct[1]], a.folds), "LA vol=mid"))
        print(fmt(run([r for r in rows if cnt[r["cid"]] > ct[1]], a.folds), "LA vol=deep"))
        print("  ^ if LA vol=mid shows a big CLV/lambda that the leak-free as-of vol=mid does NOT,"
              " the positive is a settlement-conditioned artifact.")
        return 0

    print(fmt(run(rows, a.folds), "FULL CACHE (ref)"))


if __name__ == "__main__":
    sys.exit(main())
