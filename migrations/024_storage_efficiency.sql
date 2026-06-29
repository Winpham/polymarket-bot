-- Storage efficiency + organization. Additive, idempotent.

-- Time index on the trajectory series — enables time-range queries and any
-- future retention pruning (`DELETE ... WHERE ts < now() - interval '...'`).
CREATE INDEX IF NOT EXISTS idx_consensus_snapshots_ts ON consensus_snapshots(ts);

-- Partial index for the hot housekeeping path: it scans only unresolved signals
-- and groups them by condition_id. A partial index over just the open rows stays
-- tiny and fast even as the resolved history grows large.
CREATE INDEX IF NOT EXISTS idx_consensus_signals_unresolved
    ON consensus_signals (condition_id) WHERE resolved = FALSE;
