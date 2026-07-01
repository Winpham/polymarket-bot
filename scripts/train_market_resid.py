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
# Indices held constant for price-LEVEL-freeness: yes_price, price_change_1d,
# price_change_1w. This is the LIVE arm's guarantee (also re-checked in Rust).
PRICE_LEVEL_IDX = [0, 8, 9]
# Price-SHAPE indices: momentum_1h, momentum_24h, volatility_24h, rsi. All
# price-derived — the closest residual proxies for direction. The `shape` ablation
# ALSO holds these constant to test whether a `level` surplus leaks through them.
PRICE_SHAPE_IDX = [1, 2, 3, 4]


def held_indices(price_free_level: str) -> list:
    """The feature indices held CONSTANT for a given price-free level.
      * 'level' → {0,8,9}                 (the live arm; price-LEVEL-free)
      * 'shape' → {0,8,9} ∪ {1,2,3,4}     (fully price-blind ablation)
    """
    if price_free_level == "level":
        return sorted(PRICE_LEVEL_IDX)
    if price_free_level == "shape":
        return sorted(set(PRICE_LEVEL_IDX) | set(PRICE_SHAPE_IDX))
    sys.exit(f"--price-free-level must be level|shape, got {price_free_level!r}")


def make_clf():
    """The one booster spec, shared by train + all ablation/compare paths."""
    import xgboost as xgb  # noqa: PLC0415

    return xgb.XGBClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
    )


def band_rate_lookup(p: float, band_rates, global_rate: float) -> float:
    """Mirror of the Rust `ResidExtras::band_rate` — the band's blind base rate."""
    b = pg_width_bucket5(float(p))
    return band_rates[b - 1] if 1 <= b <= 5 else global_rate


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


def load_forward(db: str, capture: str = "first"):
    """The bot's OWN strict-fired population. Features are YES-oriented; convert the
    consensus-outcome label to yes_won via yes_token. Band rates come from the
    resolved `_blind` rows (consensus-outcome space), exactly the gate's baseline.

    `capture` selects which snapshot column feeds training (migration 029):
      * 'first'    → the DECISION-TIME snapshot (first strict-fire), what a real
                     bettor would have acted on. Falls back to the freshest snapshot
                     for pre-029 rows whose `first_features` is NULL.
      * 'freshest' → the last pre-resolution snapshot (`features`).
    Reports an OOF AUC for BOTH captures when both are populated, so the drift
    between decision-time and freshest is visible before you pick one."""
    import psycopg2  # noqa: PLC0415
    import psycopg2.extras  # noqa: PLC0415

    if capture not in ("first", "freshest"):
        sys.exit(f"--capture must be first|freshest, got {capture!r}")
    conn = psycopg2.connect(db)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Pull BOTH snapshots so we can report each capture's AUC; train on `chosen`.
        cur.execute(
            """
            SELECT COALESCE(mfl.first_features, mfl.features) AS first_features,
                   mfl.features AS features, mfl.yes_token,
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
    X_first, X_fresh, y_yes, prices, groups, stamps = [], [], [], [], [], []
    for r in rows:
        X_first.append(_feat_row(r["first_features"]))
        X_fresh.append(_feat_row(r["features"]))
        # YES-orient the label: yes_won = won if yes_token else 1 - won.
        won = int(r["won"])
        y_yes.append(won if r["yes_token"] else 1 - won)
        prices.append(float(r["mean_price"]))
        groups.append(str(r["ev"]))
        stamps.append(r.get("resolved_at"))
    y_arr = np.array(y_yes, dtype=int)
    g_arr = np.array(groups)
    Xf_arr = np.array(X_first, dtype=float)
    Xr_arr = np.array(X_fresh, dtype=float)
    # Report each capture's leak-free OOF AUC so the decision-time vs freshest drift
    # is visible before training. Best-effort (needs 2 classes + enough events).
    for name, Xc in (("first(decision-time)", Xf_arr), ("freshest", Xr_arr)):
        try:
            a = quick_oof_auc(Xc, y_arr, g_arr)
            print(f"  capture={name:22s} OOF AUC={a}")
        except Exception as e:  # noqa: BLE001
            print(f"  capture={name:22s} OOF AUC unavailable ({e})")
    chosen = Xf_arr if capture == "first" else Xr_arr
    print(f"training on capture={capture!r}")
    blind_prices = [float(b["mean_price"]) for b in blind] or prices
    blind_labels = [int(b["won"]) for b in blind] or y_yes
    return (
        chosen,
        y_arr,
        np.array(prices, dtype=float),
        g_arr,
        blind_prices,
        blind_labels,
        _trained_through(stamps),
    )


def _feat_row(feats):
    """Parse one stored feature JSON object into the canonical positional vector."""
    if isinstance(feats, str):
        feats = json.loads(feats)
    return [float(feats[name]) for name in FEATURE_NAMES]


def _oof_calibrated(X, y, groups, held_idx):
    """Leak-free OOF calibrated predictions via the SAME zeroing + GroupKFold +
    isotonic pipeline the exported model uses. Returns (cal, mask) where `cal` is the
    isotonic-calibrated OOF probability (NaN outside `mask`). Not persisted."""
    from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415
    from sklearn.model_selection import GroupKFold  # noqa: PLC0415
    from sklearn.preprocessing import RobustScaler  # noqa: PLC0415

    Xz = X.astype(float).copy()
    for i in held_idx:
        Xz[:, i] = 0.0
    Xs = RobustScaler().fit_transform(Xz)
    n_events = len(set(groups.tolist()))
    n_splits = max(2, min(5, n_events))
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=n_splits).split(Xs, y, groups):
        if len(set(y[tr].tolist())) < 2:
            continue
        oof[te] = make_clf().fit(Xs[tr], y[tr]).predict_proba(Xs[te])[:, 1]
    mask = ~np.isnan(oof)
    cal = np.full(len(y), np.nan)
    if mask.sum() > 0 and len(set(y[mask].tolist())) > 1:
        iso = IsotonicRegression(out_of_bounds="clip").fit(oof[mask], y[mask])
        cal[mask] = iso.predict(oof[mask])
    return cal, mask


def quick_oof_auc(X, y, groups):
    """Leak-free OOF AUC (price-LEVEL-free pipeline) — for reporting capture drift.
    Returns a rounded float, or 'n/a' when folds are degenerate."""
    from sklearn.metrics import roc_auc_score  # noqa: PLC0415

    cal, mask = _oof_calibrated(X, y, groups, held_indices("level"))
    if mask.sum() == 0 or len(set(y[mask].tolist())) < 2:
        return "n/a"
    return round(float(roc_auc_score(y[mask], cal[mask])), 3)


def _event_surplus(y, band, groups):
    """Event-clustered would-be arm surplus: per-event mean of (won − band_rate),
    then averaged across events. Mirrors the gate's within-event clustering."""
    from collections import defaultdict  # noqa: PLC0415

    ev = defaultdict(list)
    for yi, bi, gi in zip(y, band, groups):
        ev[gi].append(float(yi) - float(bi))
    per = [float(np.mean(v)) for v in ev.values()]
    if not per:
        return float("nan"), 0, 0
    return float(np.mean(per)), int(len(y)), len(per)


def _ablation_stats(X, y, prices, groups, held_idx, band_rates, global_rate):
    """OOF AUC/Brier + the would-be arm surplus for one held-index set. The arm
    fires where calibrated p − band_rate(price) > 0; surplus is event-clustered over
    the fired rows (offline proxy of the gate's surplus-over-blind)."""
    from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: PLC0415

    cal, mask = _oof_calibrated(X, y, groups, held_idx)
    if mask.sum() == 0 or len(set(y[mask].tolist())) < 2:
        return dict(auc=float("nan"), brier=float("nan"),
                    surplus=float("nan"), n_fired=0, n_events_fired=0)
    ym = y[mask].astype(float)
    cm, pm, gm = cal[mask], prices[mask], groups[mask]
    auc = float(roc_auc_score(y[mask], cm))
    brier = float(brier_score_loss(y[mask], cm))
    band = np.array([band_rate_lookup(p, band_rates, global_rate) for p in pm])
    fired = (cm - band) > 0.0
    surplus, n_fired, n_ev = _event_surplus(ym[fired], band[fired], gm[fired])
    return dict(auc=auc, brier=brier, surplus=surplus,
                n_fired=n_fired, n_events_fired=n_ev)


def run_compare(X, y, prices, groups, blind_prices, blind_labels):
    """Train BOTH price-free levels (level, shape) on the SAME rows and print their
    OOF AUC/Brier + would-be arm surplus side by side. The pre-registered test: a
    `level` surplus is believable ONLY IF `shape` keeps a materially similar surplus
    (see model/README.md 'Believing a surplus'). No artifacts are written."""
    band_rates, global_rate, _ = band_rates_from(blind_prices, blind_labels)
    print("price-SHAPE ablation — BOTH levels on the same rows (offline; no artifacts):")
    print(f"{'level':6s} {'held_idx':24s} {'OOF_AUC':>8s} {'Brier':>7s} "
          f"{'wouldbe_surplus':>16s} {'fired':>6s} {'ev_fired':>9s}")
    out = {}
    for lvl in ("level", "shape"):
        hi = held_indices(lvl)
        st = _ablation_stats(X, y, prices, groups, hi, band_rates, global_rate)
        out[lvl] = st
        print(f"{lvl:6s} {str(hi):24s} {st['auc']:8.3f} {st['brier']:7.3f} "
              f"{st['surplus']:16.4f} {st['n_fired']:6d} {st['n_events_fired']:9d}")
    print("\nPRE-REGISTERED READ (model/README.md 'Believing a surplus'):")
    print("  A `level` surplus is believable ONLY IF `shape` retains a materially")
    print("  similar surplus. If it collapses when {1,2,3,4} are ALSO held constant,")
    print("  the level surplus was price-SHAPE leakage → report the null; do NOT")
    print("  promote, do NOT tune. The belief-blind gate remains the sole judge.")
    return out


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
def assert_price_free(booster_json_path: Path, held_idx):
    """The load-bearing guarantee: the exported booster has NO split on any of the
    HELD-constant indices. (A constant column yields no splits; this proves it
    actually happened.) `held_idx` = {0,8,9} for a `level` model, ∪ {1,2,3,4} for a
    `shape` ablation — mirrors the Rust `assert_no_splits_on` on the live subset."""
    held = set(int(i) for i in held_idx)
    raw = json.loads(booster_json_path.read_text())
    trees = raw["learner"]["gradient_booster"]["model"]["trees"]
    bad = []
    for t in trees:
        for node_i, fidx in enumerate(t["split_indices"]):
            left = t["left_children"][node_i]
            right = t["right_children"][node_i]
            is_split = not (left == -1 and right == -1)
            if is_split and int(fidx) in held:
                bad.append(int(fidx))
    if bad:
        sys.exit(f"PRICE LEAK: booster split on held indices {sorted(set(bad))}")
    print("price-free OK: zero booster splits on held indices", sorted(held))


def train(X, y, prices, groups, blind_prices, blind_labels, trained_through,
          source: str, out_dir: Path, price_free_level: str = "level"):
    from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415
    from sklearn.metrics import brier_score_loss, roc_auc_score  # noqa: PLC0415
    from sklearn.model_selection import GroupKFold  # noqa: PLC0415
    from sklearn.preprocessing import RobustScaler  # noqa: PLC0415

    n = len(y)
    n_events = len(set(groups.tolist()))
    held_idx = held_indices(price_free_level)
    print(f"source={source}  rows={n}  events={n_events}  positives={int(y.sum())}  "
          f"price_free_level={price_free_level}  held_idx={held_idx}")
    if n < 20 or len(set(y.tolist())) < 2:
        sys.exit("Too few rows / one class — not enough to train honestly.")

    # PRICE-FREE: hold the chosen price columns constant BEFORE scaling/fitting.
    Xz = X.astype(float).copy()
    for i in held_idx:
        Xz[:, i] = 0.0

    scaler = RobustScaler().fit(Xz)
    Xs = scaler.transform(Xz)

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
    assert_price_free(model_path, held_idx)
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
        "price_free_level": price_free_level,
        "price_free_idx": held_idx,
        "feature_names": FEATURE_NAMES,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    print(f"wrote {meta_path}  trained_through={trained_through}")
    print(f"Suggested MARKET_RESID_MARGIN (held-out calRMSE cushion) = {rmse:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["synthetic", "forward", "historical"],
                    default="synthetic")
    ap.add_argument("--db", help="Postgres URL (default $DATABASE_URL) for --source forward")
    ap.add_argument("--out-dir", default="model", type=Path)
    ap.add_argument("--limit", type=int, default=3000,
                    help="historical fetch cap")
    ap.add_argument("--n", type=int, default=600, help="synthetic row count")
    ap.add_argument("--capture", choices=["first", "freshest"], default="first",
                    help="forward source: which market_feature_log snapshot to train "
                         "on — 'first' (decision-time, default) or 'freshest'")
    ap.add_argument("--price-free-level", choices=["level", "shape"], default="level",
                    help="held-constant feature set: 'level' = {0,8,9} (the live arm; "
                         "price-LEVEL-free), 'shape' = also {1,2,3,4} (fully price-blind "
                         "ablation)")
    ap.add_argument("--compare", action="store_true",
                    help="train BOTH price-free levels on the same rows and print their "
                         "OOF AUC/Brier + would-be surplus side by side (no artifacts). "
                         "The pre-registered price-SHAPE-leakage test.")
    args = ap.parse_args()

    if args.source == "synthetic":
        data = load_synthetic(args.n)
    elif args.source == "forward":
        db = args.db or os.environ.get("DATABASE_URL")
        if not db:
            sys.exit("--source forward needs --db or $DATABASE_URL")
        data = load_forward(db, args.capture)
    else:
        data = load_historical(args.limit)

    X, y, prices, groups, blind_prices, blind_labels, trained_through = data
    if args.compare:
        run_compare(X, y, prices, groups, blind_prices, blind_labels)
        return
    train(X, y, prices, groups, blind_prices, blind_labels, trained_through,
          args.source, args.out_dir, args.price_free_level)


if __name__ == "__main__":
    main()
