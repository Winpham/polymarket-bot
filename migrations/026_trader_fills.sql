-- 026: Durable, never-stop trader-fill archive + capture bookkeeping.
--
-- The data-api `/activity` endpoint returns a hard 100-row newest page and
-- ignores `startTs`, so trader history can only be reconstructed by polling
-- frequently and ACCUMULATING fills into one durable, deduped table. This is the
-- "capture all the data" spine: `trader_fills` grows every cycle off the SAME
-- poll the consensus window already does (capture once, use twice). Resolution
-- columns are filled in Phase 1; the trust profile (Phase 2) is a wallet/slice
-- clone of the consensus surplus-over-blind scoreboard over these rows.
--
-- Durability = the existing daily `scripts/consensus-backup.sh` pg_dump (this DB
-- is included automatically). `trader_fills` is kept forever by default; a
-- retention knob (`TRADER_FILLS_RETENTION_DAYS`, Phase 5) prunes only when set.

CREATE TABLE IF NOT EXISTS trader_fills (
    id            BIGSERIAL PRIMARY KEY,
    wallet        TEXT             NOT NULL,
    tx_hash       TEXT,                         -- dedup key when present
    condition_id  TEXT             NOT NULL,
    outcome_index INTEGER          NOT NULL,
    outcome       TEXT             NOT NULL,
    side          TEXT             NOT NULL,     -- 'BUY' | 'SELL'
    price         DOUBLE PRECISION NOT NULL,
    size_usd      DOUBLE PRECISION NOT NULL,
    title         TEXT             NOT NULL,
    slug          TEXT             NOT NULL,
    event_slug    TEXT,
    is_sports     BOOLEAN          NOT NULL DEFAULT FALSE,
    sport         TEXT,                          -- FROZEN slug-derived bucket (single source of truth)
    ts            TIMESTAMPTZ      NOT NULL,
    ingested_at   TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    -- resolution (filled in Phase 1)
    resolved      BOOLEAN          NOT NULL DEFAULT FALSE,
    outcome_won   BOOLEAN,
    advantage     DOUBLE PRECISION,              -- BUY: won::int - price ; SELL: NULL
    resolved_at   TIMESTAMPTZ
);

-- Two PARTIAL unique indexes: tx-level dedup when tx_hash present, content dedup
-- when it's null. A bare `ON CONFLICT DO NOTHING` insert arbitrates against
-- whichever partial index applies (and dedups intra-batch).
CREATE UNIQUE INDEX IF NOT EXISTS trader_fills_tx_uniq
    ON trader_fills (tx_hash, condition_id, outcome_index) WHERE tx_hash IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS trader_fills_content_uniq
    ON trader_fills (wallet, condition_id, outcome_index, ts, price, side) WHERE tx_hash IS NULL;
CREATE INDEX IF NOT EXISTS idx_tf_wallet        ON trader_fills (wallet);
CREATE INDEX IF NOT EXISTS idx_tf_cond_outcome  ON trader_fills (condition_id, outcome_index);
CREATE INDEX IF NOT EXISTS idx_tf_ts            ON trader_fills (ts);
CREATE INDEX IF NOT EXISTS idx_tf_unresolved    ON trader_fills (resolved) WHERE resolved = FALSE;

-- Per-trader capture bookkeeping: newest fill ts we've seen (gap detection),
-- a count of detected capture gaps (full page with no overlap = lost trades),
-- and when we first started capturing this trader.
ALTER TABLE followed_traders
    ADD COLUMN IF NOT EXISTS last_capture_newest_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS capture_gap_count      INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS capture_started_at     TIMESTAMPTZ;
