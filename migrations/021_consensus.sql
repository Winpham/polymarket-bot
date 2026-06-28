-- Consensus copy-trading engine (CONSENSUS-ENGINE-PLAN.md).
-- Adds: tracked-trader provenance, rich copy-trade event fields, and the
-- consensus_signals / consensus_alerts tables used for alerting + forward tracking.

-- 1. Tracked-trader provenance for auto-follow drop-grace logic.
ALTER TABLE followed_traders ADD COLUMN IF NOT EXISTS last_seen_on_lb TIMESTAMPTZ;
ALTER TABLE followed_traders ADD COLUMN IF NOT EXISTS periods TEXT;

-- 2. Richer copy-trade events so consensus can key on (condition_id, outcome_index).
ALTER TABLE copy_trade_events ADD COLUMN IF NOT EXISTS outcome_index INTEGER;
ALTER TABLE copy_trade_events ADD COLUMN IF NOT EXISTS outcome TEXT;
ALTER TABLE copy_trade_events ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE copy_trade_events ADD COLUMN IF NOT EXISTS event_slug TEXT;
ALTER TABLE copy_trade_events ADD COLUMN IF NOT EXISTS slug TEXT;
ALTER TABLE copy_trade_events ADD COLUMN IF NOT EXISTS ts TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_copy_events_cond_outcome
    ON copy_trade_events(condition_id, outcome_index);
CREATE INDEX IF NOT EXISTS idx_copy_events_ts ON copy_trade_events(ts);

-- 3. One row per detected consensus position (condition_id, outcome_index).
--    Upserted each cycle; resolution columns filled later by housekeeping
--    (forward edge tracking).
CREATE TABLE IF NOT EXISTS consensus_signals (
    id                SERIAL PRIMARY KEY,
    condition_id      TEXT NOT NULL,
    outcome_index     INTEGER NOT NULL,
    outcome_label     TEXT,
    title             TEXT,
    slug              TEXT,
    event_slug        TEXT,
    is_sports         BOOLEAN NOT NULL DEFAULT FALSE,
    n_backers         INTEGER NOT NULL,
    n_opposers        INTEGER NOT NULL,
    net_count         INTEGER NOT NULL,
    net_quality       DOUBLE PRECISION NOT NULL,
    mean_price        DOUBLE PRECISION NOT NULL,
    price_std         DOUBLE PRECISION NOT NULL,
    recency_mins      BIGINT NOT NULL,
    total_usd         DOUBLE PRECISION NOT NULL,
    best_backer_rank  INTEGER,
    score             DOUBLE PRECISION NOT NULL,
    tier              TEXT NOT NULL,
    backers           JSONB,            -- [{wallet,name,rank}]
    -- alert dedup state
    last_alert_tier   TEXT,
    last_alert_net    INTEGER,
    last_alerted_at   TIMESTAMPTZ,
    -- lifecycle
    first_detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- forward edge tracking (filled when the market resolves)
    market_id         TEXT,             -- Gamma numeric id once resolved
    resolved          BOOLEAN NOT NULL DEFAULT FALSE,
    outcome_won       BOOLEAN,          -- did the consensus outcome win?
    resolved_at       TIMESTAMPTZ,
    UNIQUE (condition_id, outcome_index)
);

CREATE INDEX IF NOT EXISTS idx_consensus_signals_tier ON consensus_signals(tier);
CREATE INDEX IF NOT EXISTS idx_consensus_signals_resolved ON consensus_signals(resolved);
CREATE INDEX IF NOT EXISTS idx_consensus_signals_detected ON consensus_signals(first_detected_at);

-- 4. Append-only log of every alert actually pushed (for audit + cooldown).
CREATE TABLE IF NOT EXISTS consensus_alerts (
    id          SERIAL PRIMARY KEY,
    signal_id   INTEGER NOT NULL REFERENCES consensus_signals(id) ON DELETE CASCADE,
    tier        TEXT NOT NULL,
    net_count   INTEGER NOT NULL,
    score       DOUBLE PRECISION NOT NULL,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consensus_alerts_signal ON consensus_alerts(signal_id);
