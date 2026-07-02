-- At-fire consensus SHAPE capture (slice study, 2026-07-02 — reports/entries/10).
-- The upsert overwrites price_std / recency_mins / total_usd / best_backer_rank every
-- 2-min cycle, so the slice study's shape/freshness/liquidity/backer dimensions could
-- only be defined on last-observed (drifted) values — not knowable at fire, hence
-- †-capped verdicts. These mirror initial_mean_price: set ONCE at first insert, never
-- updated. Backfill is impossible (the at-fire values are gone); every day without
-- capture is unrecoverable, same argument as CAPTURE_ENTRY_ASK (D5).
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS initial_price_std DOUBLE PRECISION;
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS initial_recency_mins BIGINT;
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS initial_total_usd DOUBLE PRECISION;
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS initial_best_backer_rank INTEGER;
