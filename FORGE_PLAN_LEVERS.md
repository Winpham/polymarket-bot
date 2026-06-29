# Implementation Blueprint: Highest-use of the repo's unused assets (ML + "every-minute")

After this lands, the consensus engine (a) **measures CLV** so we *know* whether faster polling helps before
building it, (b) runs a **consensus-native ML arm** — a tiny model trained on our *own* signal features →
resolution, forward-tested as a silent strategy variant — and (c) optionally does **every-minute incremental
polling** if the CLV data says entry-timing matters. Bayesian anchoring and importing the market-prediction
model are deferred behind a clean seam.

> Produced by the Forge (diagnostician + Direct + Rethink designers, all Opus). **Both designers independently
> converged**: do NOT import the market-outcome model (known-null, needs absent artifact + per-market fetches);
> train on the consensus features we already store; make variants post-score annotations the existing gate
> judges for free. Provenance noted per item.

## REFINEMENT (2026-06-29, de-biased — overrides the pessimism below)
The first pass let the Foresight CS2-prediction result bias the *generator*: it "killed" the imported-market
model, made L1 conditional, and pre-declared the ML "expected to collapse." **That was wrong.** This is a
DIFFERENT domain (Polymarket leaderboard-consensus); prior failure elsewhere is not evidence here. Corrected
stance, per [[feedback-edge-exists-prior]]: **the generator stays bold — build every path and give it a fair
forward test; rigor/skepticism lives ONLY at the belief-blind promotion gate.** Concretely this changes the
plan to:
- **Build ALL ML arms, none "killed":** consensus-native **ensemble** (XGBoost/LightGBM on our features — the
  asset, used fully) AND a consensus-native **logistic** baseline AND the **imported-market** model (its own
  features, with the per-market fetches it needs, trained artifact and all). The gate ranks them; we do not
  pre-decide which works.
- **Build L1 unconditionally** (incremental every-minute polling is better engineering on its own; CLV just
  measures the bonus — it is not a go/no-go gate).
- **Build the Bayesian-anchor arm** as a real variant, not "deferred."
- **Build the Bonferroni family split** so experimental arms are judged in their own family and never tighten
  the live `strict` strategy's promotion bar.
- Everything still SILENT (alerting=false), default-OFF until enabled, forward-tested, surplus-over-blind,
  forward-only. The gate — not our prior — decides.
The single chained execution brief is `run-prompts/RUN-CHAINED.md`.

## The verdict on "can we do these in parallel?"
**Partially — and that's the right shape.** The honest decomposition:
- **Parallel now (2 disjoint worktrees):** [A] CLV instrumentation, [B] consensus-native ML arm + enricher seam.
  They share only one line in `consensus_cycle.rs` (the `enrich_all` call, which only B adds).
- **Sequenced + conditional:** [C] L1 incremental polling — **build only if [A]'s `capture_lag` shows timing
  matters.** It rewrites `consensus_cycle.rs` ingestion, so it must land after B's one-line add (or rebase).
- **Deferred behind the seam (one registry line each, when warranted):** Bayesian-anchor arm; the
  import-market-model "collapse-probe."
- **Killed:** importing `MarketFeatures`/market-outcome XGBoost into the consensus path (cost>0, surplus≈0,
  needs a nonexistent artifact, re-derives a documented Foresight null).

Key enabling fact (diagnostician): `copy-trading-bot` depends only on `common`. The consensus-native path needs
**no crate move** (logistic model is a new tiny `common` module); only the deferred import-model path would need
to move `xgb.rs`/`bayesian.rs` into `common`.

---

## Item A — CLV instrumentation (ship FIRST; decides whether L1 is worth building)  · source: Rethink
**Before:** the scoreboard shows surplus/edge but nothing about entry timing.
**After:** two new per-strategy, event-clustered columns, computed from rows we ALREADY store:
- `our_clv = AVG_event(outcome_won::int − initial_market_price)` — edge if we'd entered at the first mid we saw.
- `capture_lag = AVG_event(initial_market_price − mean_price)` — gap between the mid when we *noticed* and the
  price the sharps actually paid. **If materially negative → fast polling has real value (build L1). If ≈0 → skip L1.**

Implementation: extend the `consensus_scoreboard_by_strategy` CTE in `common/src/storage/consensus.rs` to also
average (at the event level, matching the existing surplus clustering) `outcome_won − initial_market_price` and
`initial_market_price − mean_price` over resolved rows where `initial_market_price IS NOT NULL`; add
`our_clv: Option<f64>` + `capture_lag: Option<f64>` to `StrategyScore`; render both in `board.rs` and the
`/consensus` text. Pure SQL + struct fields + render. **0 API calls, ~½ day, zero risk.** Its output is the
go/no-go signal for Item C.

## Item B — Consensus-native ML arm + enricher seam (parallel with A)  · source: Rethink core + Direct's wiring
**Before:** no learned model anywhere in the consensus path.
**After:** a tiny model learns *which consensus signals resolve* from features we already store, emitted as a
silent forward-tested variant `ml_top`, judged by the existing belief-blind gate. No fetches, no crate move.

1. **`common/src/model/consensus_features.rs`** — `ConsensusFeatures` from a `ConsensusSignal` (mean_price,
   price_std, net_count, net_quality, n_backers, n_opposers, ln(1+total_usd), recency_mins, best_backer_rank→999
   sentinel, is_sports) + `NAMES` + `to_vec()` (fixed order).
2. **`common/src/model/consensus_win.rs`** — `ConsensusWinModel{feature_names,center,scale,weights,bias,
   trained_through}` (serde JSON) + `load(path)` + `p_win(&[f64])` (RobustScaler then logistic sigmoid).
   *Logistic, not XGBoost* — honest at N≈tens, no overfit, no sidecar. (If N ever grows, `XgbModel` swaps in
   behind the same `p_win` interface — deferred.)
3. **Enricher seam** `copy-trading-bot/src/scanner/enrich/{mod,ml}.rs`:
   `EnrichCtx{now, ml: Option<&ConsensusWinModel>, margin}`, `type Enricher = fn(&[ConsensusSignal], &EnrichCtx)
   -> Vec<ConsensusSignal>`, `registry() -> &[Enricher]` (the one merge line), `enrich_all(signals, ctx)`.
   `ml::arm` keeps `strict` picks where `p_win(features) − mean_price > margin`, re-emits them tagged `ml_top`
   (clone the signal, change `strategy`, skip if `first_detected_at < trained_through` for forward-only honesty).
4. **`consensus_cycle.rs`** — exactly one added call after `score_all_strategies`:
   `let signals = enrich_all(signals, &EnrichCtx{ now, ml: ml_model.as_deref(), margin: cfg.ml_margin });`
   The `ml_top` rows flow through the existing `to_new_signal` → `upsert_consensus_signal` → resolve → scoreboard
   → gate untouched. `live.rs` loads `Option<ConsensusWinModel>` from `cfg.ml_model_path` (None → arm no-ops).
5. **`scripts/consensus_train.py`** — leak-free export from data we already store:
   `SELECT COALESCE(event_slug,condition_id) ev, outcome_won::int label, <the features> FROM consensus_signals
   WHERE strategy='_blind' AND resolved ORDER BY resolved_at` → **GroupKFold(groups=ev)** logistic + RobustScaler
   + Platt/isotonic calibration → dump `model/consensus_win.json`. No fetches, reuses `train_model.py` imports.
**Cost:** 0 API calls at inference (features are on the row). Cold start until enough `_blind` rows resolve
(silent anyway). Default off (no model file → no-op).

## Item C — L1 every-minute incremental polling (CONDITIONAL on Item A)  · source: Direct
**Build only if Item A's `capture_lag` is materially negative.** Then:
- **migration `025_consensus_levers.sql`**: `followed_traders.consensus_polled_at` (separate cursor from the copy
  path) + `consensus_vote_window` table (one row per trader×market×outcome×fill: wallet/name/rank/pnl/quality/
  condition_id/outcome_index/outcome/title/slug/event_slug/is_sports/price/size_usd/ts; `UNIQUE(trader_wallet,
  condition_id,outcome_index,ts,price)`; indexes on ts and (condition_id,outcome_index)).
- **Store methods** (`common/src/storage/consensus.rs`): `insert_window_votes` (UNNEST batch, ON CONFLICT DO
  NOTHING), `load_window_votes(since)`, `prune_window_votes(cutoff)`, `consensus_cursor`/`set_consensus_cursor`.
- **`consensus_cycle.rs` ingestion rewrite**: poll each trader since its cursor (backfill window on first run) →
  append delta to the store → stamp cursor → prune → **rebuild books from the stored trailing window** (not the
  poll). Gate behind `cfg.consensus_incremental` (default true once shipped). Set `CONSENSUS_INTERVAL_MINS=1`.
- Optional **crossing-alert**: alert the moment `net_count` crosses `strong_net` (captures `initial_market_price`
  nearer true entry) — the real payoff of minute cadence.
**Cost:** ~1 free data-api call/trader/cycle (~40/min), each a tiny 1-min delta instead of a 48h page; book
assembly moves off the network onto an indexed DB read. Self-healing (a failed poll's fills arrive next cycle).

## Deferred behind the seam (one registry line each, when warranted)
- **Bayesian-anchor arm** (`scanner/enrich/bayes.rs`, `bayes_top`): prior = live CLOB mid (already fetched in
  housekeeping; or fetch once per fired market), evidence = consensus LR (from net_quality) [+ ML LR if present]
  → `bayesian_update` → keep picks beating the mid by a margin. Needs `bayesian.rs` moved to `common`. Source: both.
- **Import-market collapse-probe** (`cml_*`): only if cheap to stand up; a clearly-labelled second silent probe
  to confirm the Foresight null on this data. Needs `xgb.rs` moved + a trained `xgb_model.json`. Source: Direct, as a probe.

## Cross-cutting: Bonferroni family split (both designers flagged)
Every silent variant raises `n_strategies = rows.len()` in the gate, tightening the bar for *all* strategies incl.
live `strict`. Fine for 3–4 variants. If the count grows, split the gate denominator into families (core portfolio
vs experimental arms) — a one-line change to how `n` is computed where `promotion_verdict` is called.

## Execution order
1. **A (CLV)** + **B (ML arm)** in parallel → both merge to `feat/consensus-engine`. A's `capture_lag` is the
   decision metric.
2. Read `capture_lag`. **If negative → build C (L1).** Else skip C, note why.
3. Defer Bayesian + import-probe until A/B have forward data and a reason.

## Existing infrastructure leveraged
The belief-blind `promotion_verdict` + cluster-robust `consensus_scoreboard_by_strategy` (judges any new
strategy-tagged variant for free); `to_new_signal`/`upsert_consensus_signal` keyed by strategy; housekeeping's
CLOB mid capture (`initial_market_price`) → CLV is half-built; the `_blind` band baseline (neutralizes
favorite-longshot in surplus); the 14-strategy portfolio mechanism.

## Rejected
- Importing `MarketFeatures` + market-outcome XGBoost as the primary ML (known-null, per-market fetches, absent artifact).
- XGBoost/ensemble as the consensus-native model at current N (overfit; logistic is the honest choice; XGB swaps in later).
- Treating ml/bayes as `ConsensusParams` knobs (the scorer is pure-threshold; they must be post-score annotations).
