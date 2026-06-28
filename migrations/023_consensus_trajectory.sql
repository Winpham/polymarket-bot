-- Position trajectory: each consensus signal "works like a stock" — an entry
-- (initial position), a live price that moves every cycle, and a 0/1 resolution.
-- Capture the initial position + the full chart, so CLV / drift / consensus-growth
-- are measurable. Additive + idempotent.

-- Entry reference + latest live price on the signal (convenience for CLV queries).
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS initial_market_price DOUBLE PRECISION;
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS last_market_price    DOUBLE PRECISION;
-- Initial consensus state (set once, on first detection; never overwritten).
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS initial_net_count    INTEGER;
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS initial_n_backers    INTEGER;
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS initial_mean_price   DOUBLE PRECISION;

-- The time-series: one row per (signal, observation) — the price chart + how the
-- consensus itself evolves (backers piling in, net growing) over the signal's life.
CREATE TABLE IF NOT EXISTS consensus_snapshots (
    id           SERIAL PRIMARY KEY,
    signal_id    INTEGER NOT NULL REFERENCES consensus_signals(id) ON DELETE CASCADE,
    ts           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    net_count    INTEGER NOT NULL,
    n_backers    INTEGER NOT NULL,
    -- consensus entry price (avg backer entry) as re-scored at this time
    mean_entry   DOUBLE PRECISION NOT NULL,
    -- live CLOB price of the consensus outcome (the "stock price") at this time
    market_price DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_consensus_snapshots_signal ON consensus_snapshots(signal_id, ts);
