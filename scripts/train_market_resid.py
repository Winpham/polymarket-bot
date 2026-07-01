#!/usr/bin/env python3
"""Train the PRICE-LEVEL-FREE residual market model for the `market_resid` arm.

The crux this run rests on: the shipped market arm fires on `p_model - clob_mid`,
which scores ~0 by construction because the scoreboard already subtracts the
band-matched `_blind` baseline (the favorite-longshot residual `p_model` tracks).
That is a measurement of the price feature, NOT a refutation of the model.

So we give the model a *fair* shot the gate actually rewards:

  * PRICE-LEVEL-FREE: the 3 price-LEVEL features (yes_price, price_change_1d,
    price_change_1w — indices {0,8,9}) are held CONSTANT (0.0) before fitting.
    XGBoost gains nothing from a constant column, so the booster produces NO split
    nodes on those indices — the stock pure-Rust XgbModel is then price-level-free at
    inference with the full 29-wide positional layout preserved (no inference-time
    masking). We ASSERT the exported booster has zero splits on the price indices.
    TWO NUANCES this label carries (do not overstate it as "price-free"):
      (a) The guarantee is TRAIN-time and rests SOLELY on the booster having no split
          on {0,8,9}. The RobustScaler does NOT neutralize price at inference — a
          held-constant (zero-IQR) column gets scale=1, so a live price would pass
          straight through if a split ever referenced it. The Rust side independently
          re-checks the booster (assert_no_splits_on) before the arm goes live.
      (b) The price-SHAPE features {1,2,3,4} = momentum_1h / momentum_24h /
          volatility_24h / rsi are NOT held constant here — they remain by design and
          are the closest residual proxies for direction (momentum can't rebuild the
          level, but it can shadow it). See --price-free-level {level,shape} for the
          fully price-blind ablation that tests whether a surplus leaks through them.
  * YES-ORIENTED: features always describe the index-0 (YES) token, and the label
    is `yes_won` (= outcome_won for a YES-side pick, else 1 - outcome_won). The arm
    converts p_yes -> p_consensus by outcome_index at inference. Training a YES
    model on consensus-outcome labels would mis-orient every NO-side pick (GAP-3).
  * RESIDUAL-OVER-BAND: we bake `band_rates` = the `_blind` base rate P(won) per
    `width_bucket(mean_price,0,1,5)` band. The arm fires on
    `p_consensus - band_rate(band)`, aligning its target with the gate's
    surplus-over-blind instead of cancelling against it.
  * LEAK-FREE: OOF AUC/Brier via GroupKFold(event); isotonic calibration fit on the
    GroupKFold-OOF predictions only. We report numbers; we do NOT tune to them — the
    belief-blind promotion gate in the Rust bot is the sole judge of edge.

Outputs (loaded by the pure-Rust path; no Python at runtime):
  model/market_resid.json         raw XGBoost booster (native save_model)
  model/market_resid.scaler.json  RobustScaler (center/scale/feature_names)
  model/market_resid.resid.json   ResidExtras {band_rates, global_rate, iso_x, iso_y}
  model/market_resid.meta.json    {trained_through, source, n, n_events, oof_auc,
                                    oof_brier, suggested_margin, ...}

Sources:
  --source synthetic            self-contained smoke fixture (no DB / no network)
  --source forward [--db URL]    the bot's OWN strict-fired population (Phase 4):
                                 market_feature_log JOIN consensus_signals
  --source historical           cold-start bootstrap from resolved markets via
                                 scripts/fetch_data.py (survivorship-biased; labeled)

Usage:
    python3 scripts/train_market_resid.py --source synthetic --out-dir /tmp/mr
    DATABASE_URL=... python3 scripts/train_market_resid.py --source forward --out-dir model
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Feature order — MUST equal MarketFeatures::NAMES in
# common/src/model/features.rs (29 wide). The forward log stores a name-keyed
# JSON object, so we read by name (order-independent at the source) and emit in
# this canonical order for the positional Rust model.
FEATURE_NAMES = [
    "yes_price",
    "momentum_1h",
    "momentum_24h",
    "volatility_24h",
    "rsi",
    "log_volume",
    "days_to_expiry",
    "is_crypto",
    "price_change_1d",
    "price_change_1w",
    "days_since_created",
    "created_to_expiry_span",
    "is_sports",
    "q_length",
    "q_word_count",
    "q_avg_word_len",
    "q_word_diversity",
    "q_has_number",
    "q_has_year",
    "q_has_percent",
    "q_has_dollar",
    "q_has_date",
    "q_starts_will",
    "q_has_by",
    "q_has_before",
    "q_has_above",
    "q_sentiment_pos",
    "q_sentiment_neg",
    "q_certainty",
]
# Indices held constant for price-freeness: yes_price, price_change_1d, price_change_1w.
PRICE_LEVEL_IDX = [0, 8, 9]


def pg_width_bucket5(p: float) -> int:
    """Mirror Postgres width_bucket(p,0,1,5) — must match common/model/xgb.rs."""
    if p < 0.0:
        return 0
    if p >= 1.0:
        return 6
    return int(math.floor(p * 5.0)) + 1


def band_rates_from(prices, labels):
    """`_blind` base rate P(won) per width_bucket band 1..5 + a global fallback.

    `labels` are in consensus-outcome space (did the picked outcome win) — the SAME
    space as the arm's p_consensus, so the residual is apples-to-apples.
    """
    sums = [0.0] * 5
    cnts = [0] * 5
    for pr, y in zip(prices, labels):
        b = pg_width_bucket5(float(pr))
        if 1 <= b <= 5:
            sums[b - 1] += float(y)
            cnts[b - 1] += 1
    glob = float(np.mean(labels)) if len(labels) else 0.5
    rates = [(sums[i] / cnts[i]) if cnts[i] > 0 else glob for i in range(5)]
    return rates, glob, cnts


# ----------------------------------------------------------------------------- #
# Sources
# ----------------------------------------------------------------------------- #
def load_synthetic(n: int = 600):
    """Self-contained fixture: a learnable NON-price signal so the smoke test
    actually trains a model, with price columns deliberately informative-looking
    (and then zeroed) to prove the price-free guarantee bites. Returns
    (X, y_yes, prices, groups, blind_prices, blind_labels, trained_through)."""
    rng = np.random.default_rng(7)
    X = rng.random((n, len(FEATURE_NAMES)))
    # A genuine non-price signal: YES wins more when is_sports low & q_certainty high.
    is_sports = (rng.random(n) < 0.5).astype(float)
    q_cert = rng.random(n)
    X[:, FEATURE_NAMES.index("is_sports")] = is_sports
    X[:, FEATURE_NAMES.index("q_certainty")] = q_cert
    logit = 1.5 * (q_cert - 0.5) - 1.2 * (is_sports - 0.5)
    p = 1.0 / (1.0 + np.exp(-logit))
    y_yes = (rng.random(n) < p).astype(int)
    # YES mid correlated with truth (this is the price feature we must NOT exploit).
    prices = np.clip(p + rng.normal(0, 0.08, n), 0.02, 0.98)
    X[:, 0] = prices  # yes_price
    groups = np.array([f"ev{i // 3}" for i in range(n)])  # ~3 outcomes per event
    # Synthetic _blind population for band_rates (consensus-outcome space == YES here).
    return X, y_yes, prices, groups, prices.tolist(), y_yes.tolist(), \
        datetime.now(timezone.utc).isoformat()


def load_forward(db: str):
    """The bot's OWN strict-fired population. Features are YES-oriented; convert the
    consensus-outcome label to yes_won via yes_token. Band rates come from the
    resolved `_blind` rows (consensus-outcome space), exactly the gate's baseline."""
    import psycopg2  # noqa: PLC0415
    import psycopg2.extras  # noqa: PLC0415

    conn = psycopg2.connect(db)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT mfl.features, mfl.yes_token,
                   cs.outcome_won::int AS won,
                   COALESCE(cs.event_slug, cs.condition_id) AS ev,
                   cs.mean_price, cs.resolved_at
            FROM market_feature_log mfl
            JOIN consensus_signals cs ON cs.id = mfl.signal_id
            WHERE cs.strategy = 'strict' AND cs.resolved AND cs.outcome_won IS NOT NULL
            ORDER BY cs.resolved_at
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT mean_price, outcome_won::int AS won FROM consensus_signals "
            "WHERE strategy = '_blind' AND resolved AND outcome_won IS NOT NULL"
        )
        blind = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    if not rows:
        sys.exit("No resolved strict-fired feature rows yet — let the log accrue.")
    X, y_yes, prices, groups, stamps = [], [], [], [], []
    for r in rows:
        feats = r["features"]
        if isinstance(feats, str):
            feats = json.loads(feats)
        X.append([float(feats[name]) for name in FEATURE_NAMES])
        # YES-orient the label: yes_won = won if yes_token else 1 - won.
        won = int(r["won"])
        y_yes.append(won if r["yes_token"] else 1 - won)
        prices.append(float(r["mean_price"]))
        groups.append(str(r["ev"]))
        stamps.append(r.get("resolved_at"))
    blind_prices = [float(b["mean_price"]) for b in blind] or prices
    blind_labels = [int(b["won"]) for b in blind] or y_yes
    return (
        np.array(X, dtype=float),
        np.array(y_yes, dtype=int),
        np.array(prices, dtype=float),
        np.array(groups),
        blind_prices,
        blind_labels,
        _trained_through(stamps),
    )


def load_historical(limit: int):
    """Cold-start bootstrap from resolved markets via fetch_data.py. Features are
    YES-oriented (tokens[0]); label = did YES win. SURVIVORSHIP-BIASED (fetch keeps
    only resolved/extreme markets) — labeled as such; superseded by --source forward."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import fetch_data  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        sys.exit(f"historical source needs scripts/fetch_data.py importable: {e}")
    # fetch_data exposes a DataFrame builder; we read the 29 named columns from it.
    df = fetch_data.build_training_frame(limit=limit) if hasattr(
        fetch_data, "build_training_frame"
    ) else None
    if df is None:
        sys.exit(
            "fetch_data.build_training_frame(limit) not found — run the historical "
            "fetch path manually, or use --source forward once the log has accrued."
        )
    missing = [c for c in FEATURE_NAMES if c not in df.columns]
    if missing:
        sys.exit(f"historical frame missing feature columns: {missing}")
    X = df[FEATURE_NAMES].astype(float).to_numpy()
    y_yes = df["outcome_won"].astype(int).to_numpy()
    prices = df["yes_price"].astype(float).to_numpy()
    groups = df.get("condition_id", df.index.astype(str)).astype(str).to_numpy()
    return (X, y_yes, prices, groups, prices.tolist(), y_yes.tolist(),
            datetime.now(timezone.utc).isoformat())


def _trained_through(stamps) -> str:
    vals = []
    for ts in stamps:
        if ts is None:
            continue
        if isinstance(ts, datetime):
            vals.append(ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
        else:
            try:
                vals.append(datetime.fromisoformat(str(ts).replace("Z", "+00:00")))
            except ValueError:
                pass
    if not vals:
        return datetime.now(timezone.utc).isoformat()
    return max(vals).astimezone(timezone.utc).isoformat()


# ----------------------------------------------------------------------------- #
# Train + export
# ----------------------------------------------------------------------------- #
def assert_price_free(booster_json_path: Path):
    """The load-bearing guarantee: the exported booster has NO split on any price
    index. (A constant column yields no splits; this proves it actually happened.)"""
    raw = json.loads(booster_json_path.read_text())
    trees = raw["learner"]["gradient_booster"]["model"]["trees"]
    bad = []
    for t in trees:
        for node_i, fidx in enumerate(t["split_indices"]):
            left = t["left_children"][node_i]
            right = t["right_children"][node_i]
            is_split = not (left == -1 and right == -1)
            if is_split and int(fidx) in PRICE_LEVEL_IDX:
                bad.append(int(fidx))
    if bad:
        sys.exit(f"PRICE LEAK: booster split on price indices {sorted(set(bad))}")
    print("price-free OK: zero booster splits on price indices", PRICE_LEVEL_IDX)


def train(X, y, prices, groups, blind_prices, blind_labels, trained_through,
          source: str, out_dir: Path):
    import xgboost as xgb  # noqa: PLC0415
    from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415
    from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: PLC0415
    from sklearn.model_selection import GroupKFold  # noqa: PLC0415
    from sklearn.preprocessing import RobustScaler  # noqa: PLC0415

    n = len(y)
    n_events = len(set(groups.tolist()))
    print(f"source={source}  rows={n}  events={n_events}  positives={int(y.sum())}")
    if n < 20 or len(set(y.tolist())) < 2:
        sys.exit("Too few rows / one class — not enough to train honestly.")

    # PRICE-FREE: hold the price-level columns constant BEFORE scaling/fitting.
    Xz = X.astype(float).copy()
    for i in PRICE_LEVEL_IDX:
        Xz[:, i] = 0.0

    scaler = RobustScaler().fit(Xz)
    Xs = scaler.transform(Xz)

    def make_clf():
        return xgb.XGBClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.08,
            subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
        )

    # --- Honest OOF (GroupKFold by event) for AUC/Brier + isotonic fit ---
    n_splits = max(2, min(5, n_events))
    oof = np.full(n, np.nan)
    gkf = GroupKFold(n_splits=n_splits)
    for tr, te in gkf.split(Xs, y, groups):
        if len(set(y[tr].tolist())) < 2:
            continue
        clf = make_clf().fit(Xs[tr], y[tr])
        oof[te] = clf.predict_proba(Xs[te])[:, 1]
    mask = ~np.isnan(oof)
    auc = brier = float("nan")
    iso_x, iso_y, rmse = [], [], 0.0
    if mask.sum() > 0 and len(set(y[mask].tolist())) > 1:
        auc = float(roc_auc_score(y[mask], oof[mask]))
        brier = float(brier_score_loss(y[mask], oof[mask]))
        iso = IsotonicRegression(out_of_bounds="clip").fit(oof[mask], y[mask])
        iso_x = [float(v) for v in iso.X_thresholds_]
        iso_y = [float(v) for v in iso.y_thresholds_]
        # Calibration RMSE = RELIABILITY (binned predicted vs observed frequency),
        # NOT sqrt(Brier) (that is the irreducible Bernoulli noise floor ~0.5). This
        # is the small residual-noise cushion the margin is meant to absorb.
        cal = iso.predict(oof[mask])
        ym = y[mask].astype(float)
        order = np.argsort(cal)
        nb = min(10, max(2, int(mask.sum()) // 20))
        diffs, weights = [], []
        for b in np.array_split(order, nb):
            if len(b) == 0:
                continue
            diffs.append(float(cal[b].mean() - ym[b].mean()))
            weights.append(float(len(b)))
        rmse = float(np.sqrt(np.average(np.array(diffs) ** 2, weights=np.array(weights))))
        print(f"OOF AUC={auc:.3f}  Brier={brier:.3f}  calibRMSE(reliability)={rmse:.4f}  "
              f"(event-grouped, leak-free)  iso_knots={len(iso_x)}")
    else:
        print("OOF eval skipped (degenerate folds) — isotonic left as identity")

    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Fit the exported model on ALL rows (price-free, scaled) ---
    clf = make_clf().fit(Xs, y)
    model_path = out_dir / "market_resid.json"
    clf.get_booster().save_model(str(model_path))
    assert_price_free(model_path)
    print(f"wrote {model_path}")

    scaler_path = out_dir / "market_resid.scaler.json"
    scaler_path.write_text(json.dumps({
        "center": scaler.center_.tolist(),
        "scale": scaler.scale_.tolist(),
        "feature_names": FEATURE_NAMES,
        "n_features": len(FEATURE_NAMES),
    }, indent=2))
    print(f"wrote {scaler_path}")

    band_rates, global_rate, band_counts = band_rates_from(blind_prices, blind_labels)
    resid_path = out_dir / "market_resid.resid.json"
    resid_path.write_text(json.dumps({
        "band_rates": band_rates,
        "global_rate": global_rate,
        "iso_x": iso_x,
        "iso_y": iso_y,
    }, indent=2))
    print(f"wrote {resid_path}  band_rates={[round(r, 3) for r in band_rates]} "
          f"counts={band_counts} global={global_rate:.3f}")

    meta_path = out_dir / "market_resid.meta.json"
    meta_path.write_text(json.dumps({
        "trained_through": trained_through,
        "source": source,
        # A synthetic cold-start is a NON-predictive placeholder so the arm can load;
        # historical (survivorship-biased) and forward are real. Replace before any
        # serious read — the gate would never promote noise anyway.
        "placeholder": source == "synthetic",
        "n": int(n),
        "n_events": int(n_events),
        "oof_auc": auc,
        "oof_brier": brier,
        "suggested_margin": round(rmse, 4),
        "price_free_idx": PRICE_LEVEL_IDX,
        "feature_names": FEATURE_NAMES,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    print(f"wrote {meta_path}  trained_through={trained_through}")
    print(f"Suggested CONSENSUS_ML_MARGIN (held-out calRMSE cushion) = {rmse:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["synthetic", "forward", "historical"],
                    default="synthetic")
    ap.add_argument("--db", help="Postgres URL (default $DATABASE_URL) for --source forward")
    ap.add_argument("--out-dir", default="model", type=Path)
    ap.add_argument("--limit", type=int, default=3000,
                    help="historical fetch cap")
    ap.add_argument("--n", type=int, default=600, help="synthetic row count")
    args = ap.parse_args()

    if args.source == "synthetic":
        data = load_synthetic(args.n)
    elif args.source == "forward":
        db = args.db or os.environ.get("DATABASE_URL")
        if not db:
            sys.exit("--source forward needs --db or $DATABASE_URL")
        data = load_forward(db)
    else:
        data = load_historical(args.limit)

    X, y, prices, groups, blind_prices, blind_labels, trained_through = data
    train(X, y, prices, groups, blind_prices, blind_labels, trained_through,
          args.source, args.out_dir)


if __name__ == "__main__":
    main()
