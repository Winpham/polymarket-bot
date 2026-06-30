-- Forward, survivorship-free 29-feature log for the bot's OWN strict-fired
-- markets. One row per (signal, condition, outcome); the `features` JSONB is the
-- YES-oriented MarketFeatures vector captured at strict-fire time. Joined to
-- consensus_signals at train time for the leak-free, forward `market_resid`
-- model. Additive + default-OFF (written only when MARKET_FEATURE_LOG=true).
CREATE TABLE IF NOT EXISTS market_feature_log (
    id            BIGSERIAL PRIMARY KEY,
    signal_id     BIGINT NOT NULL REFERENCES consensus_signals(id) ON DELETE CASCADE,
    condition_id  TEXT   NOT NULL,
    outcome_index INTEGER NOT NULL,
    yes_token     BOOLEAN NOT NULL,           -- did the consensus outcome == the YES (index-0) token
    clob_mid      DOUBLE PRECISION,           -- consensus-outcome live mid at capture (audit only)
    features      JSONB  NOT NULL,            -- the 29-wide YES-oriented MarketFeatures vector
    captured_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (signal_id, condition_id, outcome_index)
);
CREATE INDEX IF NOT EXISTS idx_mfl_condition ON market_feature_log (condition_id);
