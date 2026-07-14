-- 045: US-VENUE BOOK-DEPTH TAPE (time-of-day depth series for our arms' families).
--
-- WHY THIS TABLE, AND WHY IT IS NOT A FIREHOSE
-- --------------------------------------------
-- The decisive capacity question is "can the US book fill a $50 (and $250) clip in the families
-- we actually trade — sports favorites and weather?" A single late-ET snapshot already answered
-- it directionally (favorites deep at ~0¢ slip; weather thin at the touch, ~$8), but a snapshot
-- has no time-of-day control, and depth near settlement is exactly when it matters. This table
-- is that control: periodic depth summaries across the trading day.
--
-- It is deliberately NOT the venue-wide BBO firehose (LITE streams ~1,100 ticks/s across ~8,500
-- markets → ~100M rows/day of markets we will never trade). Bloat is a cost, not a feature
-- ([[feedback-focus-discipline]]). We sample the FULL book only for currently-active markets in
-- our families, on a cadence, and store the DECISION-RELEVANT summary: BBO, spread, touch depth,
-- full-book depth, and the fill/slip outcome for a $50 and $250 clip — computed at capture from
-- the real resting levels, so a downstream gate reads the number it needs without re-walking a book.
--
-- Source = 'gateway_rest' (public /v1/markets/{slug}/book, unauthenticated). recv_at is the local
-- capture clock; the venue does not stamp book snapshots, so there is no exchange clock to keep
-- here (unlike the trade tape 043) — this is a sampled snapshot, honestly labeled as such.
--
-- Additive/idempotent; safe to apply once, never edit (sqlx checksum immutability).

CREATE TABLE IF NOT EXISTS us_book_tape (
    id              BIGSERIAL PRIMARY KEY,
    us_slug         TEXT             NOT NULL,
    family          TEXT,                        -- 'favorite' | 'weather' | 'other' (why this row was sampled)
    state           TEXT,                        -- MARKET_STATE_OPEN | ...

    best_bid        DOUBLE PRECISION,
    best_ask        DOUBLE PRECISION,
    mid             DOUBLE PRECISION,
    spread_c        DOUBLE PRECISION,            -- (ask-bid)*100, cents
    n_bid_levels    INTEGER,
    n_ask_levels    INTEGER,
    touch_bid_usd   DOUBLE PRECISION,            -- $ resting at best bid
    touch_ask_usd   DOUBLE PRECISION,            -- $ resting at best ask
    full_bid_usd    DOUBLE PRECISION,            -- $ across all bid levels
    full_ask_usd    DOUBLE PRECISION,            -- $ across all ask levels

    -- decision outcomes: does a market BUY clip of this size fully fill on resting asks, and at
    -- what VWAP slippage over the best ask (cents)? NULL slip when the clip exhausts the book.
    fill50_ok       BOOLEAN,
    slip50_c        DOUBLE PRECISION,
    fill250_ok      BOOLEAN,
    slip250_c       DOUBLE PRECISION,

    last_trade_px   DOUBLE PRECISION,
    shares_traded   DOUBLE PRECISION,
    open_interest   DOUBLE PRECISION,

    recv_at         TIMESTAMPTZ      NOT NULL DEFAULT now(),
    source          TEXT             NOT NULL DEFAULT 'gateway_rest'
);

CREATE INDEX IF NOT EXISTS idx_us_book_slug   ON us_book_tape (us_slug, recv_at);
CREATE INDEX IF NOT EXISTS idx_us_book_family ON us_book_tape (family, recv_at);
CREATE INDEX IF NOT EXISTS idx_us_book_recv   ON us_book_tape (recv_at);
