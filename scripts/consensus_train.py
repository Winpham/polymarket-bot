#!/usr/bin/env python3
"""Train the consensus-native arms from our OWN forward-tracked signal data.

Reads resolved `_blind` rows (the band-matched capture-all population) from
Postgres — features + `outcome_won` — grouped by event, and trains TWO models the
Rust consensus path loads:

  * consensus_win.json  — logistic (RobustScaler + LogisticRegression) for the
    `consensus_logit` arm. Schema = {feature_names, center, scale, weights, bias,
    trained_through}, matching common/src/model/consensus_win.rs.
  * consensus_ens.json  — XGBoost (native save_model) for the `consensus_ens`
    arm, loaded by the pure-Rust XgbModel (trees are scale-invariant → no scaler).

Honesty: GroupKFold(groups=event) so correlated outcomes of one event never span
the train/test split (the within-match leak); we report OOF AUC + Brier (raw and
isotonic-calibrated) but do NOT tune to them — the belief-blind promotion gate in
the Rust bot, on forward data, is the sole arbiter of whether an arm has edge.
`trained_through` = max(resolved_at) stamps the forward-only cutoff the arms honor.

Usage:
    # From Postgres (default DATABASE_URL or --db):
    python3 scripts/consensus_train.py --out-dir model
    # From a JSON fixture (list of row dicts) — used by the smoke test:
    python3 scripts/consensus_train.py --input fixture.json --out-dir /tmp/cm
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Feature order — MUST equal CONSENSUS_FEATURE_NAMES in
# common/src/model/consensus_win.rs and consensus_feature_vec in
# copy-trading-bot/src/scanner/enrich/features.rs.
FEATURE_NAMES = [
    "mean_price",
    "price_std",
    "net_count",
    "net_quality",
    "n_backers",
    "n_opposers",
    "ln_total_usd",
    "recency_mins",
    "best_backer_rank",
    "is_sports",
]

SQL = """
    SELECT COALESCE(event_slug, condition_id) AS ev,
           outcome_won::int                   AS label,
           mean_price, price_std, net_count, net_quality,
           n_backers, n_opposers, total_usd, recency_mins,
           best_backer_rank, is_sports, resolved_at
    FROM consensus_signals
    WHERE strategy = '_blind' AND resolved AND outcome_won IS NOT NULL
    ORDER BY resolved_at
"""


def _row_to_features(r: dict) -> list:
    """Build the fixed-order feature vector from a raw row dict."""
    total_usd = float(r.get("total_usd") or 0.0)
    rank = r.get("best_backer_rank")
    return [
        float(r["mean_price"]),
        float(r["price_std"]),
        float(r["net_count"]),
        float(r["net_quality"]),
        float(r["n_backers"]),
        float(r["n_opposers"]),
        float(np.log1p(max(total_usd, 0.0))),
        float(r["recency_mins"]),
        float(rank) if rank is not None else 999.0,
        1.0 if r.get("is_sports") else 0.0,
    ]


def load_rows(args) -> list:
    if args.input:
        with open(args.input) as f:
            return json.load(f)
    db = args.db or os.environ.get("DATABASE_URL")
    if not db:
        sys.exit("No --input fixture and no --db / DATABASE_URL set.")
    import psycopg2  # noqa: PLC0415 — optional dep, only for the DB path
    import psycopg2.extras  # noqa: PLC0415

    conn = psycopg2.connect(db)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(SQL)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _trained_through(rows: list, override: str | None) -> str:
    if override:
        return override
    stamps = []
    for r in rows:
        ts = r.get("resolved_at")
        if ts is None:
            continue
        if isinstance(ts, datetime):
            stamps.append(ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
        else:
            try:
                stamps.append(datetime.fromisoformat(str(ts).replace("Z", "+00:00")))
            except ValueError:
                pass
    if not stamps:
        return datetime.now(timezone.utc).isoformat()
    m = max(stamps)
    return m.astimezone(timezone.utc).isoformat()


def train(rows: list, out_dir: Path, trained_through: str) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, roc_auc_score
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import RobustScaler

    X = np.array([_row_to_features(r) for r in rows], dtype=float)
    y = np.array([int(r["label"]) for r in rows], dtype=int)
    groups = np.array([str(r["ev"]) for r in rows])
    n, n_events = len(y), len(set(groups.tolist()))
    print(f"rows={n}  events={n_events}  positives={int(y.sum())}")
    if n < 10 or len(set(y.tolist())) < 2:
        sys.exit("Too few rows / only one class — not enough to train honestly.")

    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Honest OOF evaluation (GroupKFold by event) ---
    n_splits = max(2, min(5, n_events))
    auc = brier = float("nan")
    try:
        oof = np.full(n, np.nan)
        gkf = GroupKFold(n_splits=n_splits)
        for tr, te in gkf.split(X, y, groups):
            if len(set(y[tr].tolist())) < 2:
                continue
            sc = RobustScaler().fit(X[tr])
            lr = LogisticRegression(max_iter=1000).fit(sc.transform(X[tr]), y[tr])
            oof[te] = lr.predict_proba(sc.transform(X[te]))[:, 1]
        mask = ~np.isnan(oof)
        if mask.sum() > 0 and len(set(y[mask].tolist())) > 1:
            auc = roc_auc_score(y[mask], oof[mask])
            brier = brier_score_loss(y[mask], oof[mask])
        print(f"logit  OOF AUC={auc:.3f}  Brier={brier:.3f}  (event-grouped, leak-free)")
    except Exception as e:  # noqa: BLE001 — eval is best-effort
        print(f"OOF eval skipped: {e}")

    # --- Fit the exported logistic on ALL rows ---
    scaler = RobustScaler().fit(X)
    logit = LogisticRegression(max_iter=1000).fit(scaler.transform(X), y)
    win = {
        "feature_names": FEATURE_NAMES,
        "center": scaler.center_.tolist(),
        "scale": scaler.scale_.tolist(),
        "weights": logit.coef_[0].tolist(),
        "bias": float(logit.intercept_[0]),
        "trained_through": trained_through,
    }
    win_path = out_dir / "consensus_win.json"
    win_path.write_text(json.dumps(win, indent=2))
    print(f"wrote {win_path}")

    # --- Ensemble (XGBoost native JSON; trees are scale-invariant → raw X) ---
    try:
        import xgboost as xgb  # noqa: PLC0415

        clf = xgb.XGBClassifier(
            n_estimators=120,
            max_depth=3,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
        )
        clf.fit(X, y)
        ens_path = out_dir / "consensus_ens.json"
        clf.get_booster().save_model(str(ens_path))
        print(f"wrote {ens_path}")
    except ImportError:
        print("xgboost not installed — skipped consensus_ens.json (logit still exported)")

    return {"rows": n, "events": n_events, "auc": auc, "brier": brier, "trained_through": trained_through}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="JSON fixture (list of row dicts) instead of DB")
    ap.add_argument("--db", help="Postgres URL (default $DATABASE_URL)")
    ap.add_argument("--out-dir", default="model", type=Path)
    ap.add_argument("--trained-through", help="override RFC3339 cutoff")
    args = ap.parse_args()

    rows = load_rows(args)
    if not rows:
        sys.exit("No resolved _blind rows — let the bot accrue forward data first.")
    train(rows, args.out_dir, _trained_through(rows, args.trained_through))


if __name__ == "__main__":
    main()
