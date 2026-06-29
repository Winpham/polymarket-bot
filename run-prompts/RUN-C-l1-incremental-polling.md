# RUN-C — L1 every-minute incremental polling (CONDITIONAL)

> ⚠️ **Build only if RUN-A's `capture_lag` is materially negative** (sharps paid better than the mid we first
> saw → entry timing matters). If RUN-A shows `capture_lag ≈ 0`, DO NOT build this — record why and stop.
> Paste as a fresh long-running session task. Read `FORGE_PLAN_LEVERS.md` (Item C). Follow README workflow.
> Land AFTER RUN-A and RUN-B have merged (this rewrites `consensus_cycle.rs` ingestion).

## Mission
Do the original copy-bot's "every minute" properly: poll each tracked trader only for NEW trades since a
per-trader cursor, persist into a rolling-window store, and rebuild consensus books from the store instead of
re-fetching the full 48h window every cycle. This makes 1-minute (or tighter) cadence cheap → fresher
consensus detection → better entry price/CLV before the line moves.

## Context (the bot)
Same as RUN-A/B. Current waste: `consensus_cycle.rs` computes `since = now − 48h` and re-fetches the entire
window for every trader every 2 min. The incremental primitive already exists — `poll_trader_activity(wallet,
since)` hits `/activity?...&startTs=since` — and `detect_new_trades` (copy_trader.rs) shows the cursor pattern
(`last_checked_at` + `update_trader_checked`) BUT it drops trades >5 min old and `copy_trade_events` lacks
`outcome_index/title/event_slug/ts`, so consensus needs its OWN store.

## Owned files
- NEW `migrations/025_consensus_levers.sql` (claim the next free number; verify `024` is current max first)
- `common/src/storage/consensus.rs` (new store methods — additive)
- `copy-trading-bot/src/scanner/copy_trader.rs` (a thin incremental-fetch alias — additive)
- SHARED: `copy-trading-bot/src/cycles/consensus_cycle.rs` (ingestion rewrite — the big change; you own this
  step since A/B already merged), `config.rs` (`consensus_incremental` default true), `.env.consensus`/compose
  (`CONSENSUS_INTERVAL_MINS=1`)

## Spec (exact schema + Rust in FORGE_PLAN_LEVERS.md Item C / Designer-A blueprint)
1. Migration 025: `followed_traders.consensus_polled_at TIMESTAMPTZ` + table `consensus_vote_window`
   (trader_wallet, name, rank, pnl, quality, condition_id, outcome_index, outcome, title, slug, event_slug,
   is_sports, price, size_usd, ts; `UNIQUE(trader_wallet,condition_id,outcome_index,ts,price)`; indexes on `ts`
   and `(condition_id,outcome_index)`). Idempotent.
2. Store methods: `insert_window_votes(&[NewWindowVote])` (UNNEST batch, ON CONFLICT DO NOTHING),
   `load_window_votes(since)`, `prune_window_votes(cutoff)`, `consensus_cursor`/`set_consensus_cursor`.
3. `consensus_cycle.rs` ingestion: poll each trader since `cursor.max(window_start)` (backfill on first run) →
   build `NewWindowVote`s from BUY fills with `outcome_index` → `insert_window_votes` → `set_consensus_cursor`
   (always, even if empty) → `prune_window_votes(window_start)` → **rebuild `MarketBook`s from
   `load_window_votes(window_start)`** (not from the poll) → unchanged from `atom_log` onward. Gate behind
   `cfg.consensus_incremental`.
4. Set cadence to 1 min. (Optional, only if `capture_lag` strongly negative: a crossing-alert when `net_count`
   first crosses `strong_net`.)

## Acceptance
- CI gate green.
- **Live verify against a throwaway Postgres**: migration applies; two cycles run; `consensus_vote_window`
  accumulates the delta (not 48h each time); `ON CONFLICT DO NOTHING` suppresses duplicate fills across
  overlapping polls; books rebuilt from the store reproduce the same signals as the legacy full-poll path
  (run both with `consensus_incremental` true/false and diff the resulting consensus_signals for a cycle).
- Confirm the `strict`/`_blind` strategy outputs are non-regressive vs the legacy path.

## Discipline
The store is the new source of truth for books — a failed poll must be self-healing (fills arrive next cycle).
Keep `consensus_incremental=false` working as the fallback. Don't change scoring; only ingestion.
