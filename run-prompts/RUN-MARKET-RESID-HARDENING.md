# Long Autonomous Run — Harden & sharpen the `market_resid` price-free consensus arm

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace + Python), in a dedicated git worktree off
`feat/consensus-engine`. Gate-green + commit after EVERY phase; at the end
`merge --no-ff` into `feat/consensus-engine` so the launchd auto-updater deploys it.
Companion reading (same house style): `run-prompts/RUN-TRADING-BOT-EXPLOIT.md` (the run
that BUILT `market_resid`), `model/README.md`, `.env.consensus.example`, `DATA-MODEL.md`.

---

## Philosophy — read first, it overrides everything
- **The generator is bold; rigor lives ONLY at the belief-blind gate.** `market_resid`
  already exists, is default-OFF + silent, and the forward feature log is accruing. This
  run does NOT chase a positive result — it **removes every way a FALSE positive could
  slip through the gate, and relabels every overclaim honestly.** Per
  [[feedback-edge-exists-prior]] the edge may exist; our job is to make sure that if the
  gate ever says "promotable," we can trust it.
- **An honest null is the expected, acceptable outcome.** Live scoreboard evidence (below)
  shows the consensus bot's real edge is concentrated in FAVORITENESS + freshness + elite
  backing (`elite_fresh_fav`: surplus ≈ +8.4%, z ≈ 4.3). `market_resid` is deliberately
  price-LEVEL-free — it strips out favoriteness to avoid the tautology — so it is hunting
  the residual *after* removing the one thing that demonstrably works. **Base-rate
  expectation: indeterminate/null.** That is a real verdict, not a failure. What would be
  unacceptable is a positive result we can't trust because price leaked through a
  price-*shape* feature or a mislabeled artifact.
- **Default-OFF, silent, non-regressive.** Every change keeps the arm default-OFF and the
  live `strict` path + all existing arms byte-identical when everything is OFF. Paper/
  alert-only, free public data, NO real money, no wallet.
- **Keep the Bonferroni family lean.** Still exactly ONE enabled experimental arm
  (`market_resid`). Do NOT add new enabled arms. New training *variants* (the ablation) are
  analysis artifacts, not live arms.

---

## The results that motivate this run (verified on the live prod DB)
Event-clustered surplus over the band-matched `_blind` baseline, one-sided 95% LB:

| strategy | events | surplus | z | LB(1s) | CLV |
|---|---|---|---|---|---|
| **elite_fresh_fav** | 29 | **+8.38%** | **4.35** | +5.21% | +8.85% |
| favorite | 53 | +5.98% | 1.53 | −0.47% | +7.71% |
| strict (alerting) | 130 | +3.88% | 1.39 | −0.70% | +3.84% |
| longshot | 55 | +4.66% | 0.96 | −3.29% | −0.07% |

Read: the money is in **fresh, elite-backed FAVORITES** (near-significant even
Bonferroni-corrected; only 1 event short of the 30 floor). `strict` is marginally positive
but noisy. **`market_resid` blinds itself to price level (favoriteness) by design**, so it
cannot see this signal — it tests a genuinely different, weaker hypothesis. `market_resid`
accrual so far: **23 resolved distinct events (floor 30), 123 feature rows.** No verdict yet.

This is WHY the hardening below matters: a `market_resid` surplus, if one ever appears, is
most likely to be a price-*shape* leak (momentum/rsi shadowing favoriteness) unless we prove
otherwise. Phase 3 makes that proof a precondition.

---

## The eight gaps this run closes (from the post-build audit)
1. **"Price-free" overstates it — it's price-LEVEL-free.** Only indices {0,8,9}
   (`yes_price`, `price_change_1d`, `price_change_1w`) are held constant. The price-*shape*
   features {1,2,3,4} (`momentum_1h`, `momentum_24h`, `volatility_24h`, `rsi`) remain — all
   price-derived. Momentum can't reconstruct the level, but it can shadow direction. **No
   ablation confirms a surplus isn't leaking through them.**
2. **The load-bearing guarantee lives only in Python.** Price-level-freeness at inference
   rests entirely on "the booster has no split on {0,8,9}", asserted in
   `train_market_resid.py::assert_price_free`. The `RobustScaler` does NOT neutralize price
   at inference (a zero-IQR column gets scale=1 → live price passes through). **Rust never
   checks the invariant** — swap the model or drop the assert and price leaks silently.
3. **Coverage: the binary-only guard drops ~half the strict population.** Multi-outcome
   markets are skipped (`token_ids.len() != 2` → `None`); `market_resid` never fires on
   them, and nothing surfaces the skipped count.
4. **Freshest-snapshot, not decision-time capture.** `log_market_features` re-logs each
   cycle (`ON CONFLICT DO UPDATE`), so the stored features drift to the last pre-resolution
   state, not the first-strict-fire decision point a real bettor would act on.
5. **The margin unit is subtle and the knob is shared.** `market_resid` reuses
   `CONSENSUS_ML_MARGIN` (also used by `market_ml` with `p − clob_mid` semantics). Its own
   residual is `p_cons − band_rate` — a different unit; it deserves its own knob.
6. **Placeholder foot-gun.** The committed `model/market_resid.*` is a `source=synthetic`,
   `"placeholder": true` noise model. Enabling `CONSENSUS_ARM_RESID=true` without retraining
   runs it (silent, gate holds — but it burns an experimental Bonferroni slot on noise).
   Nothing in code refuses to load a placeholder when the arm is enabled.
7. **Prefetch is sequential + unbounded; no observability.** Accrual added ~10s/cycle for
   ~67 strict markets (150ms throttle each). No cap, no parallelism, and no metric for
   accrual rate, arm emits, multi-outcome skips, or prefetch duration.
8. **The board shows no accrual progress.** No "N/30 resolved events" or scope line, so a
   human can't see how close `market_resid` is to its first honest gate read.

---

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a synthetic smoke run.
Live-verify DB-touching changes on a **throwaway Docker Postgres** (apply migrations via
`run_migrations`, exercise the path, inspect rows). **Migrations are append-only; next free
number is 029.** Env vars reach the container ONLY via the `environment:` allowlist in
`docker-compose.consensus.yml` (NOT `env_file`) — add every new tunable there as
`VAR: ${VAR:-default}`, and ALWAYS verify a config change reached the container after deploy.

---

## Context (extend, don't rebuild — verified `file:line`, current tree)
- `common/src/model/features.rs` — `MarketFeatures` (29 fields), `NAMES` (:71), `to_vec`
  (:104), derives `Serialize + Deserialize`. Price-LEVEL idx = {0,8,9}; price-SHAPE idx =
  {1,2,3,4} = momentum_1h/momentum_24h/volatility_24h/rsi.
- `common/src/model/xgb.rs` — `XgbModel::load` (:69, auto-loads `.scaler.json`),
  `predict_prob` (:109), positional traversal `features.get(idx)` (:137); `RawTree`
  {`split_indices`, `left_children`, `right_children`, …} (parsed in `parse_tree`);
  `ResidExtras` {`band_rates:[f64;5]`, `global_rate`, `iso_x`, `iso_y`} + `load`, `band_rate`,
  `apply_iso`; `pg_width_bucket5`. **The trees are the only place price could enter — a
  no-split-on-{0,8,9} check belongs here or in the arm's load path.**
- `copy-trading-bot/src/scanner/enrich/market_resid.rs` — `arm_market_resid`: reads
  `ctx.models.market_resid` + `market_resid_extras`, `apply_iso(predict_prob())`, orients by
  `mc.outcome_index`, fires on `p_cons − band_rate(mean_price) > ctx.margins.ml`.
- `copy-trading-bot/src/scanner/enrich/mod.rs` — `EnrichModels`
  {`market_resid`, `market_resid_extras`, `market_resid_through`, `feature_log`, …};
  `needs_market_data`/`needs_market_features` (true when resid or feature_log set);
  `load_models` resid block (loads booster+`.resid.json` or neither) + `resid_trained_through`
  (reads `.meta.json`); `EnrichMargins {ml, bayes}`; `MarketCtx {clob_mid, features,
  outcome_index}`; `registry()` (adds `market_resid::arm_market_resid`); `family()`
  EXPERIMENTAL list (includes `"market_resid"`).
- `copy-trading-bot/src/cycles/consensus_cycle.rs` — `prefetch_markets` (150ms throttle per
  distinct strict `condition_id`, `outcome_price(0)` yes_mid + `outcome_price(outcome_index)`
  clob_mid); `build_market_features` (YES token 0, **binary guard `token_ids.len()!=2 →
  None`**); the upsert loop's feature-log collection (`if models.feature_log && strategy=="strict"
  && let Some(mc)… && let Some(feat)=mc.features` → push `NewMarketFeatureLog`), flushed once
  via `log_market_features`. `crate::metrics::record_consensus_cycle` is called at cycle end.
- `common/src/storage/consensus.rs` — `NewMarketFeatureLog` {signal_id, condition_id,
  outcome_index, yes_token, clob_mid, features}; `log_market_features` (UNNEST batch, `ON
  CONFLICT (signal_id,condition_id,outcome_index) DO UPDATE SET features=…, clob_mid=…,
  captured_at=NOW()`). `consensus_signals` is NEVER pruned (housekeeping only prunes
  `trader_fills`/`vote_window`), so the log corpus is durable.
- `migrations/028_market_feature_log.sql` — `market_feature_log` (signal_id FK ON DELETE
  CASCADE; UNIQUE (signal_id,condition_id,outcome_index); `features` JSONB; `captured_at`).
- `scripts/train_market_resid.py` — `FEATURE_NAMES` (must equal `MarketFeatures::NAMES`),
  `PRICE_LEVEL_IDX=[0,8,9]`, `assert_price_free` (parses booster, fails on any split on price
  idx), `band_rates_from` (from `_blind`), GroupKFold(event) OOF, isotonic on OOF, `--source
  {synthetic,forward,historical}`, meta `{trained_through, source, placeholder, suggested_margin,…}`.
- `copy-trading-bot/src/config.rs` — `#[config(env=…, default=…)]` derive; existing
  `CONSENSUS_ARM_RESID`, `MARKET_RESID_MODEL_PATH`, `MARKET_RESID_TRAINED_THROUGH`,
  `MARKET_FEATURE_LOG`, `CONSENSUS_ML_MARGIN`.
- `copy-trading-bot/src/board.rs` — `render`: per-family Bonferroni denominator from
  rows-present; the HTML scoreboard table. `promotion_verdict` in
  `copy-trading-bot/src/scanner/promotion.rs` (min_events=30, alpha=0.05).
- `common/src/metrics.rs` — Prometheus registry + `record_consensus_cycle` /
  `record_consensus_alert`; add new counters/gauges here.
- `docker-compose.consensus.yml` — `copy-trading-bot.environment:` allowlist (already passes
  `MARKET_FEATURE_LOG`, `CONSENSUS_ARM_RESID`, `CONSENSUS_ML_MARGIN`, `MARKET_RESID_TRAINED_THROUGH`).

---

## Rejected approaches (do not build these)
- **Inference-time price masking / dropping price columns / re-indexing the model.** The
  29-wide positional layout is load-bearing. Keep price-freeness a TRAIN-time property; the
  Rust check (Phase 1) only VERIFIES the booster, never mutates the vector.
- **A second enabled arm** (price-shape-free live arm, favorite arm, per-segment cells).
  Every enabled experimental arm raises the family's Bonferroni denominator. The ablation is
  an OFFLINE analysis artifact, not a live arm.
- **Chasing the `elite_fresh_fav` favorite edge inside `market_resid`.** That edge is
  price-LEVEL + recency + backer-quality; it belongs to the core portfolio, not a price-free
  arm. Note it in the report; do not smuggle price level back in.
- **Deleting/overwriting the accruing forward log.** Any capture change must be ADDITIVE
  (new column/row), never destroy the freshest-snapshot data already accrued.

---

## Phase 0 — Honest relabel (docs/comments only; zero behavior change)
Rename the guarantee everywhere from "price-free" to **"price-LEVEL-free"** and document the
two verified nuances: (a) the `RobustScaler` does NOT neutralize price at inference — the
guarantee rests solely on the booster having no split on {0,8,9}; (b) price-*shape* features
{1,2,3,4} remain by design and are the closest residual proxies. Touch: `market_resid.rs`
module doc, `xgb.rs` `ResidExtras`/`pg_width_bucket5` docs, `train_market_resid.py` header,
`model/README.md`, `.env.consensus.example`. **No code logic changes.** Gate, commit.

## Phase 1 — Enforce the guarantee in Rust + refuse placeholders + own margin knob
**Goal:** make the price-level-free invariant a hard, Rust-enforced guarantee, and stop the
foot-guns.
- `common/src/model/xgb.rs`: expose the booster's used split feature indices (add
  `XgbModel::split_feature_indices() -> BTreeSet<usize>` walking the parsed trees' split
  nodes). Add `XgbModel::assert_no_splits_on(&self, forbidden: &[usize]) -> Result<()>`.
- `copy-trading-bot/src/scanner/enrich/mod.rs::load_models`: after loading the `market_resid`
  booster, call `assert_no_splits_on(&[0,8,9])`; on violation, log an ERROR and leave the arm
  OFF (`market_resid=None`) — a price-leaking artifact must NEVER go live. Also read the
  model's `.meta.json` `placeholder` flag; if `true`, log a WARN and leave the arm OFF
  (a placeholder must never be judged by the gate).
- Config: add `#[config(env="MARKET_RESID_MARGIN", default=0.0)] pub market_resid_margin: f64,`
  and a matching compose `environment:` passthrough `MARKET_RESID_MARGIN: ${MARKET_RESID_MARGIN:-0.0}`.
  Thread it so `arm_market_resid` uses `market_resid_margin` (via a new `EnrichMargins.resid`
  field) instead of `margins.ml`. Keep `CONSENSUS_ML_MARGIN` for the legacy market arms.
**Verify:** unit tests — a booster WITH a split on idx 0 is rejected by `assert_no_splits_on`
and the arm no-ops; a clean booster passes; a `placeholder:true` meta leaves the arm OFF even
with a valid booster; the resid margin gates emission independently of `ml`. Gate, commit.

## Phase 2 — Decision-time (first-fire) capture, additively
**Goal:** capture the features at the FIRST strict-fire (the decision point) in addition to
the freshest snapshot, without destroying accrued data.
- Migration `029_*.sql` (append-only): add `first_captured_at TIMESTAMPTZ` and `first_features
  JSONB` to `market_feature_log` (nullable; backfilled going forward only).
- `common/src/storage/consensus.rs::log_market_features`: on INSERT set `first_features =
  features`, `first_captured_at = NOW()`; on CONFLICT keep `first_*` UNCHANGED (COALESCE) and
  still refresh `features`/`clob_mid`/`captured_at`. So `first_*` = decision-time, `features`
  = freshest — both available to the trainer.
- `scripts/train_market_resid.py`: add `--capture {first,freshest}` (default `first`) selecting
  which JSON column the forward source reads. Report both AUCs when feasible.
**Verify:** throwaway-PG — first log sets `first_features`; a re-log updates `features` but
NOT `first_features`/`first_captured_at`; cascade still fires. Gate, commit.

## Phase 3 — The price-SHAPE ablation (offline; the believe-a-surplus precondition)
**Goal:** a pre-registered test that any `market_resid` surplus is NOT price-shape leakage.
- `scripts/train_market_resid.py`: add `--price-free-level {level,shape}`. `level` = current
  (constant {0,8,9}). `shape` = ALSO hold {1,2,3,4} constant (momentum/vol/rsi) → a fully
  price-blind model. `assert_price_free` checks the corresponding index set. Write meta
  `price_free_level` + the used constant-index set.
- Add a `compare_resid.py` (or a `--compare` mode) that trains BOTH on the same forward rows
  and reports OOF AUC/Brier and the would-be arm surplus for each, side by side.
- **Pre-registration (write it into `model/README.md`):** a `market_resid` (level) surplus is
  believable ONLY IF the `shape` model retains a materially similar surplus. If the surplus
  collapses when {1,2,3,4} are also held constant, it was price-shape leakage → report the
  null, do NOT promote, do NOT tune.
**Verify:** synthetic smoke for both levels writes valid artifacts; both pass their
`assert_price_free`; `--compare` prints two rows. Gate, commit.

## Phase 4 — Observability: metrics, board accrual line, bounded prefetch
**Goal:** make accrual + arm health legible and keep the cycle bounded.
- `common/src/metrics.rs`: add counters/gauges — `market_feature_log_rows_total`,
  `market_resid_emit_total`, `market_multi_outcome_skipped_total`, and a
  `consensus_prefetch_seconds` histogram. Increment from `consensus_cycle.rs`
  (feature-log flush count; multi-outcome skip in `build_market_features`; arm emit count;
  time the `prefetch_markets` call).
- `copy-trading-bot/src/cycles/consensus_cycle.rs::prefetch_markets`: add a bound —
  `MARKET_PREFETCH_MAX` (config, default e.g. 200) distinct strict markets per cycle, and/or
  a bounded-concurrency fetch (reuse the existing `Semaphore` pattern from the trader poll)
  so accrual can't blow past the cadence as strict-market count grows. `log()` when capped.
- `copy-trading-bot/src/board.rs`: add a small `market_resid` status line — resolved distinct
  events vs the 30 floor (from the same JOIN the trainer uses), rows logged, multi-outcome
  skipped, and (if a non-placeholder model is loaded) the arm's current `promotion_verdict`.
**Verify:** metrics endpoint exposes the new series; board renders the accrual line; a
throttled/capped prefetch still completes and logs the cap. Gate, commit.

## Phase 5 — Merge, deploy, verify accrual unbroken
- Final `merge --no-ff` into `feat/consensus-engine`. The launchd auto-updater
  (`scripts/consensus-autoupdate.sh`) rebuilds + redeploys local HEAD; do NOT `docker compose
  up -d` by hand (blocked as a prod deploy — run the autoupdater script, the sanctioned path).
- **Post-deploy VERIFY (do not skip):** the new env vars are in the container
  (`compose exec … env | grep MARKET_RESID`), migration 029 applied, `market_feature_log`
  still accruing (row count climbing, `first_features` now populated), the arm still OFF
  (`CONSENSUS_ARM_RESID=false`), 0 restarts, cycle time sane. Report the numbers.

---

## Acceptance
Every phase gate-green + committed; final `merge --no-ff`. Deliverables: honest
"price-LEVEL-free" relabel; a Rust-enforced no-split guarantee (arm refuses a price-leaking
OR placeholder artifact); a dedicated `MARKET_RESID_MARGIN`; additive decision-time capture
(`first_features`) with the log corpus intact; a pre-registered price-shape ablation +
`--compare` that gates believing any surplus; metrics + a board accrual line; a bounded
prefetch. Live `strict` + all existing arms byte-identical with everything OFF; the arm still
default-OFF; the belief-blind gate remains the sole judge. Paper-only, NO real money.

## Standing disciplines
Generator bold, rigor only at the belief-blind gate; price-LEVEL-free at TRAIN, VERIFIED in
Rust; compare to `band_rate`, never `clob_mid`; YES-oriented train+infer (label
`yes_won = won if yes_token else 1−won`); GroupKFold by event; forward-only (`trained_through`);
isotonic on OOF; default-OFF + silent + non-regressive; ONE enabled experimental arm (lean
Bonferroni family); SQL/pool in `common`, promotion math in the binary; migrations append-only
(next 029); every new tunable added to the compose `environment:` allowlist and verified in the
container; commit per phase; `merge --no-ff` at the end; NO real money.
