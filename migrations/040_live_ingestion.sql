-- 040: live-ingestion provenance + raw CLOB price tape.
--
-- Additive & idempotent; touches NOTHING in 001-039 (sqlx checksums are immutable,
-- and editing an applied migration crash-loops the app — this file is safe to apply
-- exactly once and never edit thereafter). Everything here is forward-only and
-- flag-gated: with LIVE_TAPE / LIVE_FILLS OFF (the defaults) no writer touches these
-- objects and the poller path is byte-identical.
--
-- WHY provenance is a TIMESTAMP not a duration: we store `live_seen_at` (wall clock
-- of first live sight) rather than a precomputed lag, so latency = live_seen_at - ts
-- is derived at read against the clean exchange clock `ts` (trade_to_fill sets
-- ts = tr.timestamp). A mis-defended clock can then be re-derived, not baked in.
-- `ingested_at` is LEFT UNTOUCHED (still "write time") and simply no longer used as
-- a clock: 5.5% of 24h rows carry >1h ingest lag, so it never was an honest one.

-- (a) Provenance on the durable archive.
--     source: NULL == the existing poller spine (~3.0M rows read as poll, back-compat);
--             'live_onchain' == F2 fast fills (Item 5); 'backfill' == historical replays.
--     live_seen_at: wall clock this process FIRST saw the fill on a live channel;
--                   NULL for poll/backfill.
ALTER TABLE trader_fills
    ADD COLUMN IF NOT EXISTS source        TEXT,
    ADD COLUMN IF NOT EXISTS live_seen_at  TIMESTAMPTZ;

-- (b) Raw CLOB price tape — the measurement substrate for the latency->drift curve.
--     Append-only; anchor OFFLINE by joining a sharp fill's `ts` (exchange clock) to
--     (asset_id, exch_ts). We keep BOTH clocks: exch_ts (top-level ms-epoch `timestamp`
--     on every book/price_change frame — measured 100% present) and recv_at (local WS
--     receive). The curve anchors on exch_ts (same domain as ts -> ~zero skew); recv_at
--     is retained so clock skew (recv_at - exch_ts) is auditable.
--
--     Event types under custom_feature_enabled=true (reports/PROTOCOL_FINDINGS.md):
--       'book'         -> snapshot; best_bid=max(bids.price), best_ask=min(asks.price),
--                         last_price=last_trade_price.
--       'price_change' -> per-change delta; carries best_bid, best_ask, price(last),
--                         size(last), side directly.
CREATE TABLE IF NOT EXISTS clob_price_tape (
    id            BIGSERIAL PRIMARY KEY,
    asset_id      TEXT             NOT NULL,   -- CLOB token_id (one YES/NO leg)
    condition_id  TEXT,                        -- carried from the subscription map (no 2nd CLOB call)
    outcome_index SMALLINT,
    event_type    TEXT             NOT NULL,   -- 'book' | 'price_change'
    best_bid      DOUBLE PRECISION,
    best_ask      DOUBLE PRECISION,            -- the executable BUY price (curve reads this)
    last_price    DOUBLE PRECISION,            -- last_trade_price (book) / trade price (price_change)
    last_size     DOUBLE PRECISION,            -- trade size in SHARES (price_change only)
    side          TEXT,                        -- BUY/SELL of the delta (price_change only)
    exch_ts       TIMESTAMPTZ,                 -- exchange clock (ms-epoch `timestamp`), ~100% present
    recv_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tape_asset_recv ON clob_price_tape (asset_id, recv_at);
CREATE INDEX IF NOT EXISTS idx_tape_asset_exch ON clob_price_tape (asset_id, exch_ts)
    WHERE exch_ts IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tape_cond_recv  ON clob_price_tape (condition_id, recv_at)
    WHERE condition_id IS NOT NULL;

-- (c) Live-vs-live dedup for F2 (Item 5). Constrains ONLY live rows among themselves,
--     so it CANNOT conflict with the full-precision poller rows (source IS NULL excluded).
--     Collapses reconnect/getLogs-range REPLAYS of the same on-chain OrderFilled (which
--     reconstruct to an identical price → same key), while KEEPING genuinely distinct
--     legs of a multi-level sweep (N OrderFilled logs, same tx/cond/outcome/side, DIFFERENT
--     price → different key). `price` is included for exactly the reason migration 027's
--     tx index includes it: a taker sweeping several maker orders in one tx is N partial
--     fills, and collapsing them would undercount size_usd. (Adversarial review D1.)
--     NOTE: cross-source dedup (live-vs-poll) is NOT done here — the poller stores a
--     full-precision VWAP price and the widened index (027) includes `price`, so an
--     on-chain-reconstructed f64 would not collide; that is handled by the app pre-check
--     + poll-over-live collapse.
CREATE UNIQUE INDEX IF NOT EXISTS trader_fills_live_txkey
    ON trader_fills (tx_hash, condition_id, outcome_index, side, price)
    WHERE source = 'live_onchain' AND tx_hash IS NOT NULL;

-- (d) Cheap source/ts index for reconciliation + the poll-over-live collapse sweep.
CREATE INDEX IF NOT EXISTS idx_tf_source_ts ON trader_fills (source, ts) WHERE source IS NOT NULL;
