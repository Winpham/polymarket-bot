-- 025_consensus_levers.sql
-- L1: every-minute incremental polling done right.
--
-- Instead of re-polling each tracked trader's full 48h activity page every cycle
-- and assembling MarketBooks from that poll, we keep a per-trader cursor and a
-- rolling vote-window store. Each cycle polls only the delta since the cursor,
-- appends it (dedup via the atom UNIQUE), prunes anything older than the window,
-- and rebuilds the books from the stored trailing window — so book assembly moves
-- off the network onto an indexed DB read and minute-cadence polling is cheap and
-- self-healing (a failed poll's fills simply arrive next cycle).
--
-- Append-only + idempotent (IF NOT EXISTS), per the migration discipline.

-- Per-trader consensus cursor, separate from the copy path's last_checked_at.
ALTER TABLE followed_traders
    ADD COLUMN IF NOT EXISTS consensus_polled_at TIMESTAMPTZ;

-- One row per (trader × market × outcome × fill) seen in the trailing window.
CREATE TABLE IF NOT EXISTS consensus_vote_window (
    id             BIGSERIAL PRIMARY KEY,
    trader_wallet  TEXT             NOT NULL,
    name           TEXT             NOT NULL,
    rank           INTEGER,
    pnl            DOUBLE PRECISION,
    quality        DOUBLE PRECISION NOT NULL,
    condition_id   TEXT             NOT NULL,
    outcome_index  INTEGER          NOT NULL,
    outcome        TEXT             NOT NULL,
    title          TEXT             NOT NULL,
    slug           TEXT             NOT NULL,
    event_slug     TEXT,
    is_sports      BOOLEAN          NOT NULL DEFAULT FALSE,
    price          DOUBLE PRECISION NOT NULL,
    size_usd       DOUBLE PRECISION NOT NULL,
    ts             TIMESTAMPTZ      NOT NULL,
    -- A fill atom is identified by trader+market+outcome+timestamp+price; the same
    -- atom re-seen across overlapping polls is dropped (ON CONFLICT DO NOTHING).
    CONSTRAINT consensus_vote_window_atom_uniq
        UNIQUE (trader_wallet, condition_id, outcome_index, ts, price)
);

-- Prune scans by ts; book assembly scans by (condition_id, outcome_index).
CREATE INDEX IF NOT EXISTS idx_cvw_ts ON consensus_vote_window (ts);
CREATE INDEX IF NOT EXISTS idx_cvw_cond_outcome
    ON consensus_vote_window (condition_id, outcome_index);
