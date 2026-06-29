# Long Autonomous Run (chained) — ML cross-checks + every-minute polling for the Polymarket consensus engine

> Paste this whole file as the task for a fresh long-running session. Self-contained. One consecutive run that
> chains all phases in order. Companion detail: `FORGE_PLAN_LEVERS.md` (read its "REFINEMENT" section first),
> `DATA-MODEL.md`, `CONSENSUS-ENGINE-PLAN.md` in the repo.

## Philosophy — read first, it overrides everything
- **Build every path; do NOT pre-judge that any ML approach "can't work."** A prior failure in a *different*
  project (CS2 player-prop *prediction*) is **not** evidence about *this* domain (Polymarket leaderboard-
  *consensus*). The generator stays bold and exhaustive. Do not refuse to build a path, and do not tune a
  variant to look good.
- **The ONLY place skepticism/rigor lives is the belief-blind promotion gate** (`scanner/promotion.rs`:
  surplus-over-blind, cluster-robust at the distinct-EVENT level, Bonferroni, ≥30-event floor). Every new
  model/variant is built, runs **silently** (`alerting=false`), and is judged there. The gate — not your prior
  — decides what has edge.
- Paper/alert-only. **Free public data only.** Forward-test everything (no backtest is possible). Every change
  must leave the live `strict` alerting behavior **byte-identical until explicitly enabled** (default-OFF).

## What you're building (the goal)
Make highest + fullest use of the repo's two unused assets, integrated into the existing consensus engine and
forward-tested by the existing gate: (1) the ML ensemble (XGBoost/LightGBM + the pure-Rust `XgbModel`) and
Bayesian anchoring — as multiple independent silent cross-check arms; (2) "every-minute" polling done right via
incremental ingestion. Plus CLV instrumentation and a gate "family" split so experiments don't penalize the
live strategy.

## Context (the system)
`~/polymarket-bot`, Rust workspace: `common` (lib) + `copy-trading-bot` (the running consensus bot) +
`trading-bot` (the ML bot, source of the unused assets). Branch `feat/consensus-engine`. The bot auto-tracks
top-N Polymarket leaderboard traders (`data-api`), detects net-directional price-coherent consensus
(`scanner/consensus.rs`, pure scorer, drops two-sided MM wallets), scores a 14-strategy forward portfolio
(incl. `_blind` capture-all benchmark), resolves via CLOB (`fetch_clob_market`), snapshots trajectories, and
reports a per-strategy scoreboard (`consensus_scoreboard_by_strategy`) + the belief-blind gate
(`promotion_verdict`), surfaced via `/consensus` (ntfy-only) + a web board on `:9002`. It's deployed and
auto-updates (a launchd agent rebuilds + redeploys on each code commit to `feat/consensus-engine`).

Crucial facts (verified): `copy-trading-bot` depends ONLY on `common` (so ML code from `trading-bot` must be
moved to `common`). The pure threshold scorer can't hold an ML probability → ML/Bayes outputs must be
**post-score annotations** that re-emit a pick under a new `strategy` name; the existing
`to_new_signal`→`upsert_consensus_signal`→`resolve_consensus_signal`→scoreboard→gate path then judges any
strategy-tagged row for free. `consensus_signals` already stores per signal: mean_price, price_std, net_count,
net_quality, n_backers, n_opposers, total_usd, recency_mins, best_backer_rank, is_sports, outcome_won (label),
initial_market_price (live CLOB mid first seen, from housekeeping), event_slug/condition_id, first_detected_at.
The consensus path itself has only data-api activity (entry prices, title) — NO Gamma question / price history
/ live mid; those come from `fetch_market_by_slug`, `fetch_clob_market`, and a `prices-history` endpoint.
Migrations are append-only via `sqlx::migrate!`; next free number is **025**.

## Workflow & gate (mandatory)
- Work on a branch off `feat/consensus-engine` (e.g. `lever/ml-fastpoll`); **gate-green + commit after EVERY
  phase**, then at the end merge `--no-ff` into `feat/consensus-engine` (rebase → gate → merge) so the
  auto-updater deploys it. (Committing per phase means a later failure never loses earlier phases.)
- The gate, run before every commit:
  `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
  Python scripts: `python3 -m py_compile <f>` + a smoke run on a tiny synthetic fixture.
- Verify live where it matters: spin a throwaway Docker Postgres, apply migrations, exercise the path, inspect
  rows (the established pattern — see DATA-MODEL.md). Confirm non-regression of the existing 14 strategies.
- Every new arm: `alerting=false`, gated behind a config flag defaulting OFF/empty, no-op when its model file
  is absent.

---

## Phase 0 — CLV instrumentation (measurement)
Add two event-clustered columns to `consensus_scoreboard_by_strategy` (same EVENT clustering as surplus), over
resolved rows with `initial_market_price IS NOT NULL`:
`our_clv = AVG_event(outcome_won::int − initial_market_price)`,
`capture_lag = AVG_event(initial_market_price − mean_price)`.
Add `our_clv`/`capture_lag: Option<f64>` to `StrategyScore`; render in `/consensus` + the `:9002` board.
This is pure instrumentation (no behavior change) and lets us *watch* whether faster polling (Phase 2) helps —
but Phase 2 is built regardless. **Gate, commit.**

## Phase 1 — Enabling refactor: move ML code into `common`
`git mv trading-bot/src/model/xgb.rs common/src/model/xgb.rs` and
`git mv trading-bot/src/bayesian.rs common/src/model/bayesian.rs`; add `pub mod xgb; pub mod bayesian;` to
`common/src/model/mod.rs`; in `trading-bot` replace the local modules with re-exports
(`pub use polymarket_common::model::{xgb, bayesian};`) so the trading bot still compiles unchanged. These are
pure (serde/anyhow/std + math) — no new deps. Tests move with them. **Gate (the whole workspace, incl
trading-bot), commit.**

## Phase 2 — L1: every-minute incremental polling (build unconditionally)
Migration `025_consensus_levers.sql`: `followed_traders.consensus_polled_at TIMESTAMPTZ` + table
`consensus_vote_window` (trader_wallet, name, rank, pnl, quality, condition_id, outcome_index, outcome, title,
slug, event_slug, is_sports, price, size_usd, ts; `UNIQUE(trader_wallet,condition_id,outcome_index,ts,price)`;
indexes on `ts` and `(condition_id,outcome_index)`).
Store methods in `common/src/storage/consensus.rs`: `insert_window_votes(&[NewWindowVote])` (UNNEST batch, ON
CONFLICT DO NOTHING), `load_window_votes(since)`, `prune_window_votes(cutoff)`,
`consensus_cursor`/`set_consensus_cursor`.
Rewrite `consensus_cycle.rs` ingestion: poll each trader since `cursor.max(window_start)` (backfill on first
run) → append delta to the store → stamp cursor (always) → prune older than `window_start` → **rebuild
`MarketBook`s from `load_window_votes(window_start)`** (not from the poll). Gate behind `cfg.consensus_incremental`
(default true). Set `CONSENSUS_INTERVAL_MINS=1` in `.env.consensus`/compose. Optional crossing-alert: alert the
moment `net_count` first crosses `strong_net`. **Verify live (window accumulates the delta, dedup works, books
reproduce the legacy path). Gate, commit.**

## Phase 3 — Enricher seam + Bonferroni family split
- `copy-trading-bot/src/scanner/enrich/mod.rs`: `EnrichCtx{ now, models, cfg-derived margins }`,
  `type Enricher = fn(&[ConsensusSignal], &EnrichCtx)->Vec<ConsensusSignal>`, `registry()` (the one merge list),
  `enrich_all(signals, ctx)`. In `consensus_cycle.rs`, ONE line after `score_all_strategies`:
  `let signals = enrich_all(signals, &ctx);`. Each arm re-emits a pick cloned under a new `strategy` name,
  `alerting=false`, skipping signals with `first_detected_at < model.trained_through` (forward-only).
- **Family split:** tag each strategy as `core` (the 14 portfolio strategies incl `_blind`/`strict`) vs
  `experimental` (the new arms). Where `promotion_verdict` is called (commands.rs + board.rs), compute the
  Bonferroni denominator `n` **per family**, so adding experimental arms never tightens `strict`'s bar. (A small
  helper `fn family(strategy:&str)->&str` + grouping the rows before the verdict.) **Gate, commit.**

## Phase 4 — The arms (build ALL; each silent, forward-tested; the gate decides)
Add, each as its own `scanner/enrich/<arm>.rs` registered in `registry()`:
1. **`consensus_ens` — consensus-native ensemble.** Use the moved pure-Rust `XgbModel` (and/or the Python
   sidecar `serve_model.py` if you want the full LightGBM/stacking ensemble) trained on the consensus signals'
   OWN features → `outcome_won`. Feature vector built directly from the `ConsensusSignal` (no fetches). Emit
   `consensus_ens` for `strict` picks the model keeps (p_win − mean_price > margin).
2. **`consensus_logit` — consensus-native logistic baseline.** A tiny `ConsensusWinModel` (RobustScaler +
   logistic) loaded from a small JSON. Same features, same emit pattern. (A baseline to compare the ensemble
   against; the gate ranks them.)
3. **`market_ml` — imported market model (full fair shot).** The trading-bot's actual model: build
   `MarketFeatures::from_market_and_history` per `strict`-fired market via 1 Gamma fetch + 1 CLOB mid + 1
   `prices-history` fetch (dedupe by condition + 150ms throttle, like housekeeping; bounded by # fired markets,
   all free). Run `XgbModel` (artifact from Phase 5). Emit `market_ml` (confirm) and `market_veto` (strong
   disagree) variants.
4. **`bayes_anchor` — Bayesian anchoring.** Prior = live CLOB mid; evidence = consensus conviction → LR (+ ML
   LR if available); `bayesian_update` → posterior; emit when posterior beats the mid by a margin. Reuse the
   moved `bayesian.rs` verbatim.
Wire model loading in `live.rs` (each `Option<…>`; None when the artifact is absent → arm no-ops); pass an
`http` client + the models into `consensus_cycle`. Config flags per arm (default OFF). **Gate, commit.**

## Phase 5 — Training pipelines + end-to-end verify + report
- `scripts/consensus_train.py`: read resolved `_blind` rows from Postgres (the features + `outcome_won`,
  grouped by `COALESCE(event_slug,condition_id)`); train BOTH the ensemble (export `model/consensus_ens.json`
  in the `XgbModel` format, or via serve_model.py) and the logistic (`model/consensus_win.json`), with
  **GroupKFold(groups=event)** + calibration; stamp `trained_through = max(resolved_at)`. No fetches.
- For `market_ml`: stand up `scripts/fetch_data.py` + `scripts/train_model.py` to export `model/xgb_model.json`
  (+ scaler). Bake `model/` into `Dockerfile.consensus`.
- End-to-end: with a throwaway Postgres + tiny hand-made model JSONs, confirm each arm emits its
  strategy-tagged rows, they resolve, and appear in the scoreboard with surplus + the family-split gate verdict.
  Confirm `strict` alerting + the 14 core strategies are byte-identical with all arms OFF.
- Final report: what each arm does, how to enable it (config), and the honest note that the gate (not us) will
  decide each arm's surplus as forward data accrues — **no arm pre-judged**.

## Acceptance (overall)
- Every phase gate-green and committed; final merge to `feat/consensus-engine` (auto-deploys).
- All four+ arms exist, silent, default-OFF, judged in their own gate family; live `strict` non-regressive.
- L1 incremental polling live-verified; CLV columns visible; training scripts run on a fixture.
- A short report; nothing tuned-to-look-good; the belief-blind gate is the sole arbiter.

## Standing disciplines
Generator bold, rigor only at the gate; surplus-over-blind at distinct-EVENT N; forward-only (respect
`trained_through`); free data; paper/alert-only; default-OFF + silent + non-regressive; commit per phase.
