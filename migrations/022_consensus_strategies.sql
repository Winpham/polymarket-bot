-- Generalize consensus from a single definition into a forward-tracked PORTFOLIO
-- of named strategy variants (all scoring the same per-cycle fetched data).
-- Additive + idempotent. Never edits 021. (FORGE_PLAN.md items 2 & 3.)

-- 1. Strategy identity. DEFAULT 'strict' backfills all existing rows in-place to
--    the incumbent strategy (no data-migration step needed).
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS strategy TEXT NOT NULL DEFAULT 'strict';

-- 2. Atom log: the full raw vote vector for each observed (market, outcome), so a
--    strategy invented LATER can be replayed over data already collected — the
--    no-backtest superpower. Shape: [{wallet,name,rank,quality,pnl,price,size_usd,ts}].
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS observed_votes JSONB;

-- 3. Swap the dedup key from (condition_id, outcome_index) to
--    (strategy, condition_id, outcome_index) so two strategies can both claim the
--    same market/outcome without colliding. The 021 inline UNIQUE created an
--    implicit constraint named conventionally; drop it if present, then add the
--    composite UNIQUE INDEX (a unique index is a valid ON CONFLICT arbiter).
ALTER TABLE consensus_signals
    DROP CONSTRAINT IF EXISTS consensus_signals_condition_id_outcome_index_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_consensus_signals_strategy_cond_outcome
    ON consensus_signals (strategy, condition_id, outcome_index);

CREATE INDEX IF NOT EXISTS idx_consensus_signals_strategy ON consensus_signals (strategy);

-- 4. Tag the alert log with the strategy that fired it (denormalized for cheap
--    per-strategy alert-rate queries; the FK already reaches strategy via signal_id).
ALTER TABLE consensus_alerts ADD COLUMN IF NOT EXISTS strategy TEXT NOT NULL DEFAULT 'strict';
