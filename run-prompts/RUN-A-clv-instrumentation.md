# RUN-A — CLV instrumentation (the decision metric)

> Paste as a fresh long-running session task. Self-contained. Read `FORGE_PLAN_LEVERS.md` (Item A) and
> `DATA-MODEL.md` in the repo for full context. Follow `run-prompts/README.md` §"Shared workflow".

## Mission
Add two event-clustered CLV columns to the per-strategy scoreboard, computed from rows the bot ALREADY
stores. The headline output — **`capture_lag`** — decides whether the team builds fast/incremental polling
(RUN-C). Ship this first; it's cheap, zero-risk, and gates the most expensive lever.

## Context (the bot)
`~/polymarket-bot`, branch `feat/consensus-engine` (Rust workspace: `common` + `copy-trading-bot`). The
consensus engine auto-tracks top-N Polymarket leaderboard traders, detects net-directional consensus, scores a
14-strategy forward portfolio (incl `_blind` capture-all benchmark), resolves via CLOB, and reports a
per-strategy scoreboard with surplus-over-blind + a belief-blind promotion gate. Alert/paper-only. Deployed &
auto-updating (commits to `feat/consensus-engine` auto-deploy — so work in a worktree, see README).

`consensus_signals` already stores per signal: `mean_price` (avg trader ENTRY price), `initial_market_price`
(the live CLOB mid the first time housekeeping saw the market — captured in `housekeeping.rs`), `outcome_won`
(filled on resolution), `event_slug`/`condition_id` (the cluster key), `resolved`.

## Owned files (stay in your lane)
- `common/src/storage/consensus.rs` (the `consensus_scoreboard_by_strategy` query + `StrategyScore` struct)
- `copy-trading-bot/src/telegram/commands.rs` (the `/consensus` board text) and/or
  `copy-trading-bot/src/board.rs` (the web scoreboard render)

## Spec
1. Extend `consensus_scoreboard_by_strategy` (the existing CTE that already computes cluster-robust
   surplus at the EVENT level) to ALSO compute, over resolved rows where `initial_market_price IS NOT NULL`,
   averaged the SAME event-clustered way as surplus:
   - `our_clv   = AVG_event( outcome_won::int − initial_market_price )`  — edge if we'd entered at first-seen mid.
   - `capture_lag = AVG_event( initial_market_price − mean_price )`      — (first mid we saw) − (price sharps paid).
2. Add `our_clv: Option<f64>` and `capture_lag: Option<f64>` to `StrategyScore` (sqlx::FromRow).
3. Render both in the `/consensus` text and the `:9002` board, next to `surplus` (reuse the existing
   `fmt_pct` helper; label them clearly; one-line legend: "capture_lag<0 ⇒ sharps paid better than the mid we
   first saw ⇒ faster polling would help").
4. Interpretation note in your final report: **if `capture_lag` for `strict`/`_blind` is materially negative
   (e.g. ≲ −1¢) with a non-trivial resolved N, RUN-C (fast polling) is worth building; if ≈0, skip it.**

## Acceptance
- CI gate green (README §3).
- Verify the new SQL executes against a live throwaway Postgres with the current schema (it must handle
  `initial_market_price IS NULL` rows gracefully → `None`).
- `/consensus` and the board show the two columns.
- Final report states the **current `capture_lag` value** read from the live/running DB (or notes "insufficient
  resolved N yet" with the count), and the go/no-go recommendation for RUN-C.

## Discipline
Pure read-side instrumentation — do not change any scoring/alerting behavior. Event-cluster the averages
(don't average raw signal rows — that re-introduces the within-match leak).
