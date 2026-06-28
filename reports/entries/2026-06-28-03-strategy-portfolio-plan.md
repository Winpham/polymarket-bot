# 2026-06-28 · Entry 03 — Strategy portfolio: Forge-validated plan

## Why
No backtest is possible (entry 02), so we cannot rank strategies offline. The right move:
**run many strategy variants forward, simultaneously, and let real resolved outcomes decide.**

## Process
Ran the **Forge** blueprint pipeline (diagnostician + 2 parallel designers, all Opus) on the
question "best architecture for N simultaneous forward-tested consensus strategies?" Full
blueprint: `../FORGE_PLAN.md`.

## Verdict
**Multi-strategy-forward is the right call** — both independent designers agreed. The expensive
work (polling traders, building books) is already paid once per cycle, so each extra strategy is a
free pure-function pass + a DB upsert. Alert-spam risk is contained by a **single-alerter** flag
(only `strict` pushes Telegram; the rest forward-track silently).

## The synthesis (Direct spine + Rethink's key graft)
- **Spine (Direct):** enrich `ConsensusParams` with 4 no-op-default fields (`require_elite`,
  `price_band`, `sports_mode`, `weight_mode`); `StrategyDef{name, params, alerting}`;
  `score_all_strategies` loop; migration 022 (`strategy` column + composite unique, backfill
  `strict`); per-strategy scoreboard with **edge = AVG(outcome_won − mean_price)**.
- **Graft (Rethink):** **log raw vote atoms (`observed_votes` JSONB) from day one** — the single
  most valuable idea for a no-backtest world: any strategy invented *later* can be replayed over
  data already collected. Plus dedupe resolution by slug (fetch each market once, not per row).
- **Deferred to Phase 2** (atoms preserve the option): the `replay_strategy` job, full
  parent/child normalization, a live `/strategy` registry command, smart-money PnL weighting.

## Initial portfolio (10, factorial probe — each isolates one lever)
`strict`(alert) · `loose` · `fresh2h` · `longshot` · `favorite` · `sports_only` · `nonsports` ·
`elite_gated` · `whales` · `count`. `CONSENSUS_STRATEGIES` env filters which run.

## Discipline (carried from the Foresight arc)
`edge>0` on a few resolved signals is **indeterminate by power**. Show N prominently;
**never auto-promote** a strategy to alerting — that stays a gated human decision.

## Status → implementing now (see entry 04).
