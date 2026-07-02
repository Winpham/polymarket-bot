-- Dense early-life price trajectory for fresh consensus signals (execution-
-- latency decay run, Phase 0). The 5-min housekeeping snapshots are too coarse
-- to resolve a 1-5 minute action window; this table records a ~45s-spaced
-- mid + executable best-ask for the first minutes of a signal's life.
-- Forward-only, flag-gated (DENSE_CAPTURE, default OFF), bounded.
CREATE TABLE IF NOT EXISTS signal_price_trajectory (
    id              BIGSERIAL PRIMARY KEY,
    signal_id       INTEGER NOT NULL REFERENCES consensus_signals(id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    secs_after_fire INTEGER NOT NULL,
    mid             DOUBLE PRECISION,
    ask             DOUBLE PRECISION,
    n_backers       INTEGER
);

CREATE INDEX IF NOT EXISTS idx_spt_signal_secs
    ON signal_price_trajectory(signal_id, secs_after_fire);
