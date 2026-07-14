-- 044: US-VENUE DAILY MARKET REPORT (the historical fundamentals spine).
--
-- WHAT & WHY
-- ----------
-- Polymarket US, as a CFTC-regulated DCM, publishes a public Daily Market Report — an EOD
-- contract summary — at https://www.polymarketexchange.com/files/daily-market-report/ . 257
-- daily files back to 2025-10-30, ~8,850 contracts/day. It is the ONLY historical fundamentals
-- source the venue offers (per-market REST history 404s; see 042's header). This is a REGULATORY
-- surface: a statutory publication obligation, so it is far more durable than any private
-- endpoint — it cannot be silently removed the way an undocumented route can.
--
-- It carries what we otherwise cannot reconstruct on the US book: daily OPEN INTEREST, volume
-- (decomposed by trade type), the day's bid/offer/trade price ranges, and — decisively — the
-- official SETTLEMENT price, which is the ground truth every backtest resolves against.
--
-- WHY THIS GOES IN POSTGRES BUT THE RAW TAPE DOES NOT
-- --------------------------------------------------
-- This table is small (~2.3M rows for the full history) and structured — a hot fundamentals
-- store. The companion Time & Sales tape (~1.9M prints/day, ~5.4GB, ~500M rows) is COLD by
-- design and lands in the parquet archive, not here, honoring the hot/cold split the storage
-- layer just adopted ("stop using Postgres as an archive"). Aggregates of the raw tape (volume,
-- ranges) already live in THIS report, so nothing is lost by keeping the tape cold.
--
-- Additive/idempotent; safe to apply once, never edit.

CREATE TABLE IF NOT EXISTS us_daily_market_report (
    business_date       DATE             NOT NULL,   -- trading date the row applies to
    symbol              TEXT             NOT NULL,    -- contract identifier (== us_slug family)
    report_id           TEXT,                        -- internal row id (not stable across days)
    maturity_date       DATE,
    maturity_time       TEXT,                        -- kept as text (venue emits tz-offset strings)
    strike_price        DOUBLE PRECISION,
    description         TEXT,

    open_interest       DOUBLE PRECISION,            -- outstanding open contracts (EOD)
    trade_volume        DOUBLE PRECISION,            -- total traded volume for the day
    block_volume        DOUBLE PRECISION,
    efp_volume          DOUBLE PRECISION,            -- exchange-for-physical
    efr_volume          DOUBLE PRECISION,            -- exchange-for-risk
    threshold_volume    DOUBLE PRECISION,
    other_volume        DOUBLE PRECISION,

    low_bid_price       DOUBLE PRECISION,
    high_bid_price      DOUBLE PRECISION,
    low_offer_price     DOUBLE PRECISION,
    high_offer_price    DOUBLE PRECISION,
    low_trade_price     DOUBLE PRECISION,
    high_trade_price    DOUBLE PRECISION,
    settlement_price    DOUBLE PRECISION,            -- OFFICIAL settlement — backtest ground truth

    loaded_at           TIMESTAMPTZ      NOT NULL DEFAULT now(),
    source              TEXT             NOT NULL DEFAULT 'regulatory_dmr',

    PRIMARY KEY (business_date, symbol)              -- idempotent reload = ON CONFLICT DO NOTHING
);

CREATE INDEX IF NOT EXISTS idx_us_dmr_symbol ON us_daily_market_report (symbol, business_date);
CREATE INDEX IF NOT EXISTS idx_us_dmr_date   ON us_daily_market_report (business_date);
