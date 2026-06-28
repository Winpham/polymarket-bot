# 2026-06-28 · Entry 04 — Strategy portfolio SHIPPED & verified

Implemented `FORGE_PLAN.md` end-to-end (all 6 items). Branch `feat/consensus-engine`.

## What shipped
- **Scorer abstraction** (`scanner/consensus.rs`): enriched `ConsensusParams` with 4 no-op-default
  knobs (`require_elite`, `price_band`, `sports_mode`, `weight_mode`); `StrategyDef{name, params,
  alerting}`; `score_all_strategies` (loops the portfolio over the SAME books, tags each signal);
  `default_portfolio` (10 variants). +5 unit tests incl. a **non-regression** test (strict ==
  legacy default).
- **Atom log** (the no-backtest superpower): every signal stores `observed_votes` JSONB — raw vote
  vector — so strategies invented later can be replayed over data already collected.
- **DB** (`migration 022` + `storage/consensus.rs`): `strategy` column, composite unique
  `(strategy, condition_id, outcome_index)` (old unique dropped), backfill `strict`;
  `consensus_scoreboard_by_strategy` with **edge = AVG(outcome_won − mean_price)**.
- **Cycle**: one fetch → 10 strategies scored → per-strategy upsert; **only `strict` alerts**, the
  rest forward-track silently (zero new Telegram noise).
- **Resolution**: housekeeping now dedupes by slug (fetch each market once, not once per
  strategy-row) + per-strategy resolution metrics.
- **Reporting**: `/consensus` renders the per-strategy scoreboard; Prometheus metrics gain a
  `strategy` label; `CONSENSUS_STRATEGIES` env filters which run.

## Verified end-to-end (Docker PG + live Polymarket API)
- Migration 022 applied; **constraint swap proven** — the same (market, outcome) is stored under
  **7 strategies simultaneously** (old UNIQUE correctly dropped).
- One live cycle: 62 traders → **366 markets → 10 strategies → 25 signals** (was 1 with
  single-strict). Every row has `observed_votes` populated (14-vote sample).
- Per-strategy scoreboard SQL runs clean (0 resolved — markets still live).
- CI gate green: `fmt` + `clippy --workspace --all-targets -Dwarnings` + `test` (copy-bot 18,
  common 44, trading-bot 105).

## Deferred (Phase 2, atoms preserve the option)
`replay_strategy` job (score new strategies over the atom log), live `/strategy` registry command,
full parent/child normalization, smart-money PnL weighting.

## Next
Deploy with real Telegram creds + persistent Postgres → the 10 strategies accrue resolved outcomes
→ `/consensus` edge scoreboard ranks them. That is the forward verdict (needs days/weeks + market
closes). Then promote the winning variant (gated, not automatic).
