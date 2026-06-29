# RUN-B — Consensus-native ML arm + enricher seam

> Paste as a fresh long-running session task. Self-contained. Read `FORGE_PLAN_LEVERS.md` (Item B) for full
> spec. Follow `run-prompts/README.md` §"Shared workflow". Runs in PARALLEL with RUN-A.

## Mission
Make highest use of the repo's ML assets WITHOUT importing its market-prediction model (a known Foresight
null that needs data we don't have + an artifact that doesn't exist). Instead: train a tiny **calibrated
logistic** model on the consensus signals' OWN features → `outcome_won` (data already on the row, leak-free),
and emit its picks as a SILENT forward-tested variant `ml_top` that the existing belief-blind gate judges for
free. Also land a clean **enricher seam** so future arms (Bayesian, etc.) are a one-line addition.

## Context (the bot)
Same as RUN-A. Key facts: `copy-trading-bot` depends only on `common` (so this needs NO crate move). The
pure scorer `scanner/consensus.rs` is threshold-only and CANNOT hold an ML probability → the ML arm must be a
**post-score annotation** that re-emits picks under a new `strategy` name. The existing path
`to_new_signal` → `upsert_consensus_signal` (keyed by `(strategy, condition_id, outcome_index)`) →
`resolve_consensus_signal` → `consensus_scoreboard_by_strategy` → `promotion_verdict` judges any
strategy-tagged row automatically. `consensus_signals` stores: mean_price, price_std, net_count, net_quality,
n_backers, n_opposers, total_usd, recency_mins, best_backer_rank, is_sports, outcome_won (label), event_slug,
first_detected_at.

## Owned files
- NEW `common/src/model/consensus_features.rs`, `common/src/model/consensus_win.rs` (+ `pub mod` lines in
  `common/src/model/mod.rs`)
- NEW `copy-trading-bot/src/scanner/enrich/mod.rs`, `copy-trading-bot/src/scanner/enrich/ml.rs`
  (+ `pub mod enrich;` in `scanner/mod.rs`)
- NEW `scripts/consensus_train.py`
- SHARED, minimal additive only: `copy-trading-bot/src/cycles/consensus_cycle.rs` (ONE `enrich_all(...)` call
  after `score_all_strategies`), `copy-trading-bot/src/live.rs` (load `Option<ConsensusWinModel>` from cfg, pass
  into the consensus loop), `copy-trading-bot/src/config.rs` (append `ml_model_path` default "", `ml_margin`
  default 0.0), `Dockerfile.consensus` (COPY the `model/` dir if present)

## Spec (see FORGE_PLAN_LEVERS.md Item B for the exact Rust)
1. `ConsensusFeatures::from_signal(&ConsensusSignal)` → fixed-order `to_vec()` (best_backer_rank None→999;
   log_total_usd = ln(1+total_usd)); `NAMES` array.
2. `ConsensusWinModel{feature_names, center, scale, weights, bias, trained_through}` + `load(path)` (serde_json)
   + `p_win(&[f64])` = RobustScaler then logistic sigmoid. **Logistic, not XGBoost** (honest at small N; no
   sidecar). Structure so a tree model could swap in behind `p_win` later — but do NOT build that now.
3. Enricher seam: `EnrichCtx{now, ml: Option<&ConsensusWinModel>, margin}`,
   `type Enricher = fn(&[ConsensusSignal], &EnrichCtx)->Vec<ConsensusSignal>`, `registry()` (the merge line),
   `enrich_all(signals, ctx)`. `ml::arm`: for `strict`, tier≥Strong picks where `p_win(features) − mean_price >
   margin` AND `first_detected_at >= trained_through`, clone + retag `strategy="ml_top"`, `alerting=false`.
4. `consensus_cycle.rs`: one line — `let signals = enrich_all(signals, &EnrichCtx{...});` after
   `score_all_strategies`. `live.rs`: load model (None if file absent → arm no-ops), pass `as_deref()` in.
5. `scripts/consensus_train.py`: `SELECT COALESCE(event_slug,condition_id) ev, outcome_won::int label, <the
   ConsensusFeatures columns> FROM consensus_signals WHERE strategy='_blind' AND resolved ORDER BY resolved_at`
   → **GroupKFold(groups=ev)** logistic + RobustScaler + Platt/isotonic calibration → dump
   `model/consensus_win.json` with `trained_through = max(resolved_at)`. No fetches. Reuse `train_model.py` imports.

## Acceptance
- CI gate green; unit tests for `ConsensusWinModel::p_win` (monotone, sigmoid bounds) and `ConsensusFeatures`
  ordering; `py_compile` + a smoke train on a tiny synthetic fixture (the live DB likely lacks enough resolved
  `_blind` rows yet — that's fine; the arm no-ops with no model file, and trains once data accrues).
- With NO model file present, live behavior is byte-identical (arm no-ops). Verify against a throwaway Postgres.
- `ml_top` rows appear in the scoreboard once a model exists (demo with a hand-crafted tiny model JSON if needed).

## Discipline
`ml_top` is SILENT (never alerts) and judged ONLY on surplus-over-blind by the gate — expected outcome is
honestly unknown; do not tune to make it look good. Forward-only: the `first_detected_at >= trained_through`
guard is mandatory (no training on signals the model has already "seen").
