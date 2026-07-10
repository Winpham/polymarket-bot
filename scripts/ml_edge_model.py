#!/usr/bin/env python3
"""
ML EDGE MODEL — Tue's hypothesis: the hand-thresholded arms lose because each is a univariate
silo; a single model over ALL at-fire features jointly might find interactions the silos miss.

This is the GENERATOR. The belief-blind gate + realizable cost + OOS holdout are the JUDGE — the
same discipline every other arm faces (no exception for ML; a flexible model is MORE prone to
fitting the band-composition artifact that false-promoted market_resid).

Design (locked, honest):
  population : `loose` resolved consensus signals — the broadest detection net (min gates), so it
               SUBSUMES every arm (they are gate-subsets of loose). ~4k market-outcomes / 1.1k events.
  features   : AT-FIRE only (initial_*), zero look-ahead. price, price_std, recency, total_usd,
               n_backers, net_count, best_backer_rank, n_opposers, net_quality, is_sports,
               sport (1-hot), market_type (1-hot), entry_ask, ask−mid spread.
  label      : outcome_won.
  decision   : edge_hat = p_hat − entry_ask − fee(entry_ask);  BET when edge_hat > τ.
  target metric (the ONLY one that counts): REALIZABLE ROI on the held-out LATER days
               (won − entry_ask − fee), event-clustered, + belief-blind surplus vs the band-matched
               blind baseline, + ≥2 non-soccer regimes. Train accuracy is ignored.
  models     : logistic (interpretable, first) + HistGBM (flexible). Calibrated. Compared to the
               champion `favorite` rule and the blind baseline ON THE SAME held-out window.

Read-only DB. Paper-only. sklearn/numpy/pandas + stdlib. No LLM, no network.

  ./ml_edge_model.py            # train, time-split holdout, realizable + belief-blind report → JSON
  ./ml_edge_model.py --self-test
"""
import csv
import io
import json
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import market_taxonomy as mtx

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1", "psql", "-U", "bot", "-d",
      "polymarket", "--csv", "-q"]
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "ML-EDGE-MODEL.json")
FEE = 0.03  # sports taker; fee per $stake = 0.03*(1-p), abs = 0.03*p*(1-p)*shares

SQL = """
SELECT condition_id, outcome_index, slug, event_slug,
       COALESCE(initial_mean_price, mean_price)      AS price,
       COALESCE(initial_price_std, price_std)        AS price_std,
       COALESCE(initial_recency_mins, recency_mins)  AS recency,
       COALESCE(initial_total_usd, total_usd)        AS total_usd,
       COALESCE(initial_n_backers, n_backers)        AS n_backers,
       COALESCE(initial_net_count, net_count)        AS net_count,
       initial_best_backer_rank                      AS rank,
       n_opposers, net_quality, is_sports, entry_ask,
       (outcome_won::int)                            AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals
WHERE resolved AND strategy='loose' AND entry_ask IS NOT NULL
  AND COALESCE(initial_mean_price, mean_price) IS NOT NULL
"""


def _f(v, d=None):
    return d if v in (None, "", "\\N") else float(v)


def fetch():
    out = subprocess.run(PG + ["-c", SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        price = _f(r["price"])
        ask = _f(r["entry_ask"])
        if price is None or ask is None:
            continue
        cat = mtx.category(r["slug"], "")
        mt = mtx.market_type(r["slug"], "") or "unk"
        rows.append(dict(
            cond=r["condition_id"], oi=r["outcome_index"],
            ev=r["event_slug"] or r["condition_id"], day=r["day"],
            price=price, price_std=_f(r["price_std"], 0.0), recency=_f(r["recency"], 0.0),
            total_usd=_f(r["total_usd"], 0.0), n_backers=_f(r["n_backers"], 0.0),
            net_count=_f(r["net_count"], 0.0), rank=_f(r["rank"], 999.0),
            n_opposers=_f(r["n_opposers"], 0.0), net_quality=_f(r["net_quality"], 0.0),
            is_sports=1.0 if r["is_sports"] in ("t", "true", "1") else 0.0,
            ask=ask, spread=ask - price, cat=cat, mt=mt, won=int(r["won"]),
        ))
    return rows


NUM = ["price", "price_std", "recency", "total_usd", "n_backers", "net_count", "rank",
       "n_opposers", "net_quality", "is_sports", "ask", "spread"]
CATS = ["soccer", "tennis", "mlb", "esports", "crypto", "politics/elections", "econ/other", "other"]
MTS = ["main", "deriv", "unk"]


def featurize(rows):
    import numpy as np
    X = []
    for r in rows:
        row = [r[k] for k in NUM]
        row += [1.0 if r["cat"] == c else 0.0 for c in CATS]
        row += [1.0 if r["mt"] == m else 0.0 for m in MTS]
        X.append(row)
    return np.array(X, dtype=float)


def fee_abs(p):
    return FEE * p * (1.0 - p)  # per share


def realizable_pnl(ask, won):
    """100 shares, entry at the ask, corrected taker fee."""
    return (100.0 * (1.0 - ask) if won else -100.0 * ask) - 100.0 * fee_abs(ask)


def clustered_roi(picks):
    """picks: list of rows. event-clustered mean realizable ROI on turnover ($100/bet)."""
    if not picks:
        return float("nan"), 0
    ev = defaultdict(list)
    for r in picks:
        ev[r["ev"]].append(realizable_pnl(r["ask"], r["won"]) / 100.0)
    means = [sum(v) / len(v) for v in ev.values()]
    return 100.0 * sum(means) / len(means), len(means)


def champion_realizable(cut):
    """Champion `favorite` realizable ROI on the held-out window, from its OWN arm rows."""
    sql = ("SELECT event_slug, condition_id, entry_ask, (outcome_won::int) won "
           "FROM consensus_signals WHERE resolved AND strategy='favorite' AND entry_ask IS NOT NULL "
           f"AND to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') >= '{cut}'")
    out = subprocess.run(PG + ["-c", sql], capture_output=True, text=True)
    picks = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        a = _f(r["entry_ask"])
        if a is not None:
            picks.append(dict(ev=r["event_slug"] or r["condition_id"], ask=a, won=int(r["won"])))
    return clustered_roi(picks) + (len(picks),)


def run():
    import warnings
    import numpy as np
    warnings.filterwarnings("ignore")
    np.seterr(all="ignore")
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.calibration import CalibratedClassifierCV

    rows = fetch()
    days = sorted(set(r["day"] for r in rows))
    # time-split: train earlier ~70% of days, test the held-out LATER days
    cut = days[int(len(days) * 0.6)]
    tr = [r for r in rows if r["day"] < cut]
    te = [r for r in rows if r["day"] >= cut]
    # event-leak guard: drop any test event that also appears in train
    tr_ev = set(r["ev"] for r in tr)
    te = [r for r in te if r["ev"] not in tr_ev]
    print(f"ML EDGE MODEL · loose universe · n={len(rows)} ({len(tr)} train < {cut} ≤ {len(te)} test) "
          f"· {len(days)} days · realizable entry\n" + "=" * 96)

    Xtr, ytr = featurize(tr), np.array([r["won"] for r in tr])
    Xte = featurize(te)
    # robustify: clip extreme raw values, drop zero-variance cols for the linear model
    Xtr = np.clip(np.nan_to_num(Xtr), -1e6, 1e6)
    Xte = np.clip(np.nan_to_num(Xte), -1e6, 1e6)
    sc = StandardScaler().fit(Xtr)
    Xtr_s = np.nan_to_num(np.clip(sc.transform(Xtr), -10, 10))
    Xte_s = np.nan_to_num(np.clip(sc.transform(Xte), -10, 10))

    out = {"n_train": len(tr), "n_test": len(te), "split_day": cut, "models": {}}
    # champion favorite realizable (own arm) + all-loose baseline on the SAME test window
    croi, cnev, cbets = champion_realizable(cut)
    ate, anev = clustered_roi(te)  # "bet everything loose detects" = the all-in baseline
    print(f"baselines (test, realizable): ALL-loose {ate:+.2f}% (n_ev={anev}) | "
          f"champion favorite {croi:+.2f}% (n_ev={cnev}, {cbets} bets)")

    for name, clf in [("logistic", LogisticRegression(max_iter=2000, C=0.5)),
                      ("histgbm", HistGradientBoostingClassifier(max_depth=3, max_iter=200,
                                                                 learning_rate=0.05, l2_regularization=1.0))]:
        Xt = Xtr_s if name == "logistic" else Xtr
        Xv = Xte_s if name == "logistic" else Xte
        cal = CalibratedClassifierCV(clf, method="isotonic", cv=3)
        cal.fit(Xt, ytr)
        p_hat = cal.predict_proba(Xv)[:, 1]
        # decision: realizable edge_hat = p_hat − ask − fee ; bet edge_hat>0
        edge = np.array([p_hat[i] - te[i]["ask"] - fee_abs(te[i]["ask"]) for i in range(len(te))])
        picks = [te[i] for i in range(len(te)) if edge[i] > 0]
        roi, nev = clustered_roi(picks)
        # how much does p_hat actually deviate from the market? (echo check)
        dev = float(np.mean(np.abs(p_hat - np.array([r["price"] for r in te]))))
        # non-soccer regime check on picks
        reg = defaultdict(list)
        for r in picks:
            g = r["cat"] if r["cat"] in ("tennis", "mlb", "esports") else ("soccer" if r["cat"] == "soccer" else "other")
            reg[g].append(r)
        nonsoccer_pos = sum(1 for g, rs in reg.items() if g != "soccer" and len(rs) >= 10
                            and clustered_roi(rs)[0] > 0)
        out["models"][name] = dict(n_picks=len(picks), n_ev=nev, roi_realizable=round(roi, 3),
                                   phat_dev_from_price=round(dev, 4), nonsoccer_regimes_pos=nonsoccer_pos)
        print(f"\n[{name}] bets {len(picks)}/{len(te)} (n_ev={nev}) · realizable ROI {roi:+.2f}% "
              f"· p̂−price dev {dev:.3f} · non-soccer regimes>0: {nonsoccer_pos}")
        print(f"  vs champion {croi:+.2f}% → {'BEATS' if roi > croi else 'does NOT beat'} champion OOS")
        if name == "logistic":
            feat_names = NUM + CATS + MTS
            coefs = clf.coef_[0] if hasattr(clf, "coef_") else cal.calibrated_classifiers_[0].estimator.coef_[0]
            top = sorted(zip(feat_names, coefs), key=lambda kv: -abs(kv[1]))[:6]
            print("  top drivers (|coef|, scaled): " + ", ".join(f"{n}{v:+.2f}" for n, v in top))
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    out["champion_roi"] = round(croi, 3)
    out["all_loose_roi"] = round(ate, 3)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {REPORT}")
    print("\nVERDICT is the held-out realizable ROI vs champion + whether ≥2 non-soccer regimes clear.")
    return 0


def walkforward():
    """The honest test: across MULTIPLE expanding-window splits, does the model's SELECTION beat
    both the champion AND betting-everything (all-loose)? If it only ties all-loose, the ML adds
    nothing; if it swings sign across folds, it's noise."""
    import warnings
    import numpy as np
    warnings.filterwarnings("ignore"); np.seterr(all="ignore")
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    rows = fetch()
    days = sorted(set(r["day"] for r in rows))
    print("WALK-FORWARD · HistGBM · realizable OOS · model-select vs champion vs bet-everything\n" + "-" * 84)
    print(f"{'test_from':<12}{'n_te':>5}{'model_ROI':>10}{'allloose_ROI':>13}{'champ_ROI':>10}{'model−all':>10}")
    deltas = []
    for i in (5, 6, 7, 8, 9):   # expanding train, test = day i onward
        if i >= len(days):
            break
        cut = days[i]
        tr = [r for r in rows if r["day"] < cut]
        te = [r for r in rows if r["day"] >= cut]
        tev = set(r["ev"] for r in tr)
        te = [r for r in te if r["ev"] not in tev]
        if len(tr) < 200 or len(te) < 60:
            continue
        Xtr = np.clip(np.nan_to_num(featurize(tr)), -1e6, 1e6)
        Xte = np.clip(np.nan_to_num(featurize(te)), -1e6, 1e6)
        ytr = np.array([r["won"] for r in tr])
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
                                             l2_regularization=1.0)
        cal = CalibratedClassifierCV(clf, method="isotonic", cv=3).fit(Xtr, ytr)
        ph = cal.predict_proba(Xte)[:, 1]
        picks = [te[j] for j in range(len(te)) if ph[j] - te[j]["ask"] - fee_abs(te[j]["ask"]) > 0]
        mroi, _ = clustered_roi(picks)
        aroi, _ = clustered_roi(te)
        croi, _, cb = champion_realizable(cut)
        d = mroi - aroi
        deltas.append(d)
        print(f"{cut:<12}{len(te):>5}{mroi:>+9.2f}%{aroi:>+12.2f}%{croi:>+9.2f}%{d:>+9.2f}%")
    if deltas:
        mu = sum(deltas) / len(deltas)
        print("-" * 84)
        print(f"model−all-loose across {len(deltas)} folds: mean {mu:+.2f}%, "
              f"range [{min(deltas):+.2f}, {max(deltas):+.2f}] → "
              f"{'model SELECTION adds value' if mu > 1 and min(deltas) > 0 else 'NO robust edge over betting everything (noise)'}")
    return 0


def _self_test():
    ok = abs(realizable_pnl(0.8, True) - (100 * 0.2 - 100 * 0.03 * 0.8 * 0.2)) < 1e-9
    ok &= abs(realizable_pnl(0.8, False) - (-80 - 100 * 0.03 * 0.8 * 0.2)) < 1e-9
    r, n = clustered_roi([{"ev": "a", "ask": 0.8, "won": 1}, {"ev": "a", "ask": 0.8, "won": 0}])
    ok &= n == 1  # both in one event-cluster
    print("self-test:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    if "--walkforward" in sys.argv:
        sys.exit(walkforward())
    sys.exit(run())
