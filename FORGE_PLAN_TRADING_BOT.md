# FORGE_PLAN_TRADING_BOT — Implementation blueprint: exploit the market-prediction ML (`market_resid`)

The implementation blueprint backing `run-prompts/RUN-TRADING-BOT-EXPLOIT.md`. Per-item:
Before/After, Implementation (real code/signatures), Integration points (`file:line`),
Source (direct | rethink | hybrid | refined + rationale). Synthesis of Designer A (Direct) and
Designer B (Rethink) after verification against the real code. Does NOT replace `FORGE_PLAN.md` or
`FORGE_PLAN_LEVERS.md`.

## Verification summary (what the real code says)
- `XgbModel` is **already in `common/src/model/xgb.rs`** (RUN-D's "move" prereq is done). It is
  **positional**: scaler-by-index (`scale==0⇒0.0` guard, xgb.rs:56-60), tree traversal
  `features.get(feature_idx)` (xgb.rs:137). JSON schema at xgb.rs:161-194 verified exact. No
  calibration field today (raw sigmoid, :116).
- Feature indices verified from `to_vec()` (features.rs:104-136): `yes_price`=0, `momentum_1h`=1,
  `momentum_24h`=2, `volatility_24h`=3, `rsi`=4, `log_volume`=5, `days_to_expiry`=6, `is_crypto`=7,
  `price_change_1d`=8, `price_change_1w`=9, `days_since_created`=10, `created_to_expiry_span`=11,
  `is_sports`=12, NLP=13..28. **29 features.** Designer B's `is_sports=#12 / rsi=#4 / is_crypto=#7`
  claims are CORRECT. Price-LEVEL features = {0, 8, 9}.
- `pg_width_bucket5` mirrors `width_bucket(mean_price,0,1,5)` (consensus.rs:489): verified
  algebraically (`p<0→0`, `p≥1→6`, else `floor(p*5)+1`). Float-boundary caveat → mitigated by a
  Postgres-parity unit test.
- The gate subtracts `blind_edge[band]=AVG_{_blind}(won−mean_price)` (consensus.rs:493-500), NOT
  `band_rate=AVG_{_blind}(won)`. **B's "surplus EQUALS the model's target by construction" is
  overstated** — they are *aligned* (both reward beating the band), not identical. Kept the residual
  target; corrected the framing.
- **B's `predict_prob_pricefree` + `price_free_idx` masking is risky and unnecessary.** Against a
  positional model, training on a *dropped*-column dataframe re-indexes to 27-wide and silently
  mis-aligns the 29-length inference vector. Adopted A's **constant-column at train** mechanism
  instead → no split nodes on price indices → stock `predict_prob` is price-free with zero new
  inference primitive. (This is the single biggest design change from B.)
- `board.rs:154-179` computes the Bonferroni denominator from **rows-present per family**, so an
  OFF arm costs nothing but an *enabled* `market_ml` control would tighten `market_resid`'s bar.
  ⇒ `market_ml` stays defined + default-OFF, NOT enabled.
- GAP-3 confirmed: `build_market_features` (consensus_cycle.rs:680-695) uses
  `token_ids.get(outcome_index)` + `outcome_price(outcome_index)`; training is YES-only
  (`fetch_data.py:158 tokens[0]`). GAP-5 confirmed: `train_model.py` fits isotonic (:553) but
  `export_xgboost_model` (:608) ships only the raw booster + scaler ⇒ Rust gets uncalibrated.
  GAP-7 confirmed: `TimeSeriesSplit` (:320) with `market_ids` already threaded (:539) ⇒ trivial
  GroupKFold swap. Next migration number = **028** (026/027 exist).
- Designer A's `file:line` refs (build_market_features :680-695, get_yes_token :151-160) check out.

## Synthesis decision (the spine)
**HYBRID, B-spine + A-bootstrap + A-price-mechanism.**
- **Spine (B):** predict the price-free RESIDUAL; compare to baked `band_rate[band]`, not `clob_mid`;
  build a forward 29-feature `market_feature_log` (migration 028) and forward-calibrate on it. ONE
  new arm: `market_resid`.
- **Price-freeness (A, refined):** hold the 3 price columns constant at TRAIN time; drop B's
  inference masking. Only new Rust inference = `band_rate` + `apply_iso` + `pg_width_bucket5`.
- **Cold-start (A):** a `--source historical` bootstrap artifact (price-free, GroupKFold) so the arm
  can score during the weeks the forward log accrues — labeled `source=historical` in `meta.json`,
  superseded by the `--source forward` model at ≥30 events.
- **`market_ml`:** kept in code, default-OFF, NOT enabled (the tautology is documented analytically,
  not paid for with a Bonferroni slot). Enabled experimental arm count this run = **1**.

---

## Item 1 — GAP-3 YES-orientation (Phase 0)
**Before:** `build_market_features` builds features from the `outcome_index` token and mid; `arm_market`
compares `p_model` (P of the outcome_index token) to `clob_mid`. Trained YES-only ⇒ NO-side picks
score the wrong object.
**After:** features always describe the YES (index-0) token + YES mid; `MarketCtx` carries
`outcome_index`; arms convert `p_yes → p_cons` by `outcome_index`.
**Implementation:**
- `prefetch_markets` (consensus_cycle.rs:634-675): add `let yes_mid = clob.outcome_price(0).unwrap_or(mid);`
  keep `clob_mid = clob.outcome_price(s.outcome_index)`; `MarketCtx { clob_mid: mid, features,
  outcome_index: s.outcome_index }`.
- `build_market_features` (consensus_cycle.rs:680-695): `let token = token_ids.first()?;` pass
  `yes_mid`; binary guard `if token_ids.len() != 2 { return None; }`.
- `MarketCtx` (mod.rs:150-156): `pub outcome_index: i32`.
- `arm_market` (market.rs:34): `let p_yes = model.predict_prob(&feat.to_vec()); let p_cons =
  if mc.outcome_index == 0 { p_yes } else { 1.0 - p_yes }; let edge = p_cons - mc.clob_mid;`
**Integration points:** consensus_cycle.rs:653, :680-695; mod.rs:150-156, :634-668; market.rs:16-45.
**Source:** hybrid (A's mid-anchor + B's binary guard). Both designers converged; merged the cleaner
halves. **Non-regressive** (all market arms OFF).

## Item 2 — Forward feature log (Phase 1)
**Before:** forward rows store only the 10 consensus-native features; the 29-feature market model is
only trainable from the survivorship-biased historical fetch.
**After:** every strict-fired market's YES-oriented 29-feature vector is logged, keyed to its
`consensus_signals` row — a forward, survivorship-free training population.
**Implementation:** migration `028_market_feature_log.sql` (table + FK
`signal_id REFERENCES consensus_signals(id) ON DELETE CASCADE` + `UNIQUE(signal_id,condition_id,
outcome_index)`; see run prompt for the exact DDL). `common/src/storage/consensus.rs`:
`NewMarketFeatureLog` + `log_market_features(&[…]) -> Result<u64>` (UNNEST batch,
`ON CONFLICT … DO UPDATE`, mirror `insert_window_votes` :559). `EnrichModels.feature_log: bool`;
`needs_market_data`/`needs_market_features` true when set. `consensus_cycle.rs` upsert loop
(:284-293): after `upsert_consensus_signal` returns `state`, for a `strict` row with
`markets.get(cond).features`, collect a `NewMarketFeatureLog { signal_id: state.id, … }`; flush once
after the loop (best-effort).
**Integration points:** migrations/028; consensus.rs:559 (template), upsert path; mod.rs:34,:53-61,:67;
consensus_cycle.rs:284-293.
**Source:** direct from B (its "no-backtest superpower", the `observed_votes` analogue). Verified FK +
`state.id` availability (consensus_cycle.rs:287) + the needs-data gating. **Default-OFF.**

## Item 3 — Price-free + calibration primitives (Phase 2)
**Before:** `XgbModel` is raw sigmoid, no calibration, no band baseline.
**After:** a `ResidExtras` companion (`band_rates[5]`, `global_rate`, `iso_x/iso_y`) + `band_rate()`
+ `apply_iso()` + free `pg_width_bucket5()`. The `XgbModel` itself is untouched.
**Implementation:** see run prompt Phase 2 for the struct + fn bodies. `ResidExtras::load` reads
`<model>.resid.json`. `apply_iso` = clamp + piecewise-linear interp; identity if `iso_x.len()<2`.
`band_rate(p)` = `band_rates[pg_width_bucket5(p)-1]` with `global_rate` fallback.
**Integration points:** common/src/model/xgb.rs (new pub items alongside `XgbModel`).
**Source:** refined from B — kept `band_rate`/`apply_iso`/`pg_width_bucket5`/`band_rates`; **dropped**
`predict_prob_pricefree` and `price_free_idx` (unnecessary + index-fragile; see Verification).
Tests: `pg_width_bucket5` boundary table + Postgres-parity sweep on throwaway PG; `apply_iso`
monotone + identity-when-absent.

## Item 4 — `market_resid` arm + training script (Phase 3)
**Before:** no price-free arm; the only market arm is the tautological `arm_market`.
**After:** one silent default-OFF arm firing on `p_cons − band_rate(mean_price) > margin`, scored by
the gate; one `train_market_resid.py` (historical OR forward source).
**Implementation:** `scanner/enrich/market_resid.rs::arm_market_resid` (full body in run prompt).
`EnrichModels`: `market_resid: Option<XgbModel>`, `market_resid_extras: Option<ResidExtras>`,
`market_resid_through: Option<DateTime<Utc>>`. `load_models` (mod.rs:101-123 pattern): under
`cfg.consensus_arm_resid`, load model + `.resid.json` (both-or-neither); `trained_through` from
`.meta.json`/env. `registry()` (mod.rs:176) += `arm_market_resid`; `family()` EXPERIMENTAL
(mod.rs:229-237) += `"market_resid"`. Config: `CONSENSUS_ARM_RESID`, `MARKET_RESID_MODEL_PATH`
(default `model/market_resid.json`), `MARKET_RESID_TRAINED_THROUGH`; reuse `CONSENSUS_ML_MARGIN`.
`scripts/train_market_resid.py`: `--source historical|forward`; price-free by holding cols {0,8,9}
constant before `RobustScaler.fit`; full 29-col order = `MarketFeatures::NAMES`; GroupKFold(event)
OOF; `band_rates` from `_blind` rows; isotonic on OOF preds; export
`market_resid.json/.scaler.json/.resid.json/.meta.json`.
**Integration points:** new market_resid.rs; mod.rs:34,:101-123,:176,:229-237; config.rs (~:182-191);
scripts/; model/; mod.rs:307 (extend `arm_pipeline_e2e`).
**Source:** hybrid — B's arm semantics (residual-over-band, no market_ml), A's training-pipeline
mechanics (fetch_data→train, GroupKFold swap, scaler/booster export, `.calib`/`.meta` companions),
A's price-free-via-constant.

## Item 5 — Forward retrain + enable (Phase 4)
**Before:** cold-start (survivorship-biased) artifact only.
**After:** forward-trained artifact supersedes it once ≥30 distinct forward strict-fired events
accrue; arm enabled silently; gate reads it in the experimental family.
**Implementation:** ship Phase 1 to prod (`MARKET_FEATURE_LOG=true`); when the distinct-event count
clears ~30, `train_market_resid.py --source forward`, commit `source=forward` artifact, set
`CONSENSUS_ARM_RESID=true`. Read `promotion_verdict` on the board.
**Source:** direct from B (its Phase 4). The gate is the sole judge.

---

## Execution order
0. GAP-3 YES-orientation (no config) → 1. Feature log (ship first, accrue) → 2. Rust primitives →
3. Arm + cold-start training (bake bootstrap artifact) → 4. Forward retrain + enable. Each phase
ends gate-green + committed; final `merge --no-ff`.

## Open questions
- **Momentum/vol/rsi (indices 1-4) as residual price proxies.** They're price-*shape*, not level, so
  kept. If a clean surplus appears, run an ablation that also constants {1,2,3,4} to confirm the edge
  isn't leaking recent direction. (Documented in the run's leakage checklist + report.)
- **band_rate population.** Baked from `_blind` rows (what the gate subtracts) for alignment, while
  the model trains on strict-fired rows. This is the intended asymmetry (model selects among strict
  picks; baseline = the blind band rate). Re-confirm on real data that `_blind` band coverage is
  non-empty for the bands strict picks land in; else fall back to `global_rate`.
- **Cold-start vs forward distribution gap.** Historical (general, survivorship-filtered) vs forward
  (strict-fired) populations differ; the bootstrap is explicitly labeled and superseded. Watch the
  OOF AUC/Brier delta between the two sources in `meta.json`.

## Rejected approaches
- Price-anchored `p_model − clob_mid` (shipped `arm_market`): ≈0 by construction; the source of the
  old false "null." Left default-OFF, not enabled.
- `market_ml`/`market_veto` as an enabled control: burns an experimental Bonferroni slot for no
  information (board.rs counts rows-present). Documented analytically instead.
- Segment-arm fleet (`market_nlp`/`market_nlp_nonsports`/per-band): inflates the family-wide
  correction; the GBM conditions on `is_sports`/`is_crypto`/`rsi` internally. At most ONE pre-
  registered `market_resid_nonsport`, built later only if data shows surplus left on the table.
- Inference-time `price_free_idx` masking / dropping price columns at train: index-fragile against
  the positional `XgbModel`; replaced by training-time constant columns.
