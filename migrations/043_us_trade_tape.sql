-- 043: US-VENUE LIVE TRADE TAPE, WITH PER-TRADER IDENTITY.
--
-- WHY THIS TABLE EXISTS, AND WHY IT IS THE ONE THAT OVERTURNS THE PRIOR
-- --------------------------------------------------------------------
-- The standing belief (see [[project-polymarket-us-venue]]) was: "Polymarket US is a KYC'd
-- fiat DCM; trader identity is never emitted to any client; the copy signal is UNOBSERVABLE
-- there." That was inferred from four REST 404s (/trades /leaderboard /activity /positions),
-- all of which are real. But it was WRONG about identity.
--
-- The retail app streams a live trade tape WITH persistent per-trader usernames from an
-- UNDOCUMENTED, UNAUTHENTICATED WebSocket it uses itself:
--     wss://gateway-ws-markets.polymarket.us/v1/ws/subscriptions
-- (the DOCUMENTED api.polymarket.us/v1/ws/markets is the one that 401s; this gateway host,
-- pulled from the polymarket.us Next.js bundle env NEXT_PUBLIC_US_WS_URL, is public.) A
-- venue-wide subscription (empty marketSlugs) delivers EVERY trade on the exchange from one
-- connection. Measured on n=400 live prints: taker.username present 100%, maker.username 46%,
-- 242 distinct persistent handles in ~90s. The docs' own trade example omits `username`
-- entirely, which is why a docs-only search never found it.
--
-- So the same copy signal we believed lived only on the intl on-chain book is ALSO observable
-- here — as usernames on the aggressor of (almost) every trade. There is no public per-username
-- HISTORY endpoint, so we build that history OURSELVES by ingesting this tape continuously.
-- That makes the clock irreversible in the same way as 041/042: the tape is live-only, so
-- every hour this ingester is off is per-trader history that can never be recovered.
--
-- SHAPE OF THE SOURCE MESSAGE (verified)
--   trade.marketSlug, trade.price{value,currency}, trade.quantity{value,currency},
--   trade.tradeTime (exchange clock, ns precision, UTC),
--   trade.taker{username?, side, intent, outcomeSide}, trade.maker{username?, side, intent, outcomeSide}
--   side   ∈ ORDER_SIDE_BUY | ORDER_SIDE_SELL
--   intent ∈ ORDER_INTENT_{BUY_LONG,BUY_SHORT,SELL_LONG,SELL_SHORT,UNDEFINED}
--   outcome∈ OUTCOME_SIDE_{YES,NO,UNSPECIFIED}
--
-- CONVENTIONS INHERITED (from 040/042, deliberately)
--   * Additive & idempotent (CREATE ... IF NOT EXISTS); safe to apply once, NEVER edit after
--     (an edited applied migration crash-loops sqlx — see [[feedback-applied-migrations-immutable]]).
--   * TWO clocks, never a precomputed lag: `trade_time` is the venue's exchange clock; `recv_at`
--     is local WS receive. Ingest latency = recv_at - trade_time is DERIVED at read against the
--     clean exchange clock, never baked in (the 040 rationale; the D4 saga was a hidden lag).
--   * `source` records the rung the datum came from, so no downstream query has to trust a
--     comment about where a byte originated. 'gateway_ws' == the undocumented public WS (Rung 2).

CREATE TABLE IF NOT EXISTS us_trade_tape (
    id              BIGSERIAL PRIMARY KEY,

    us_slug         TEXT             NOT NULL,   -- US instrument slug (joins us_quotes.us_slug / mapper)
    price           DOUBLE PRECISION NOT NULL,   -- execution price = implied probability, USD
    quantity        DOUBLE PRECISION NOT NULL,   -- size in CONTRACTS (shares)

    -- aggressor (taker): identity present ~100% of prints
    taker_username  TEXT,
    taker_side      TEXT,                        -- ORDER_SIDE_BUY | ORDER_SIDE_SELL
    taker_intent    TEXT,                        -- ORDER_INTENT_BUY_LONG | ...
    taker_outcome   TEXT,                        -- OUTCOME_SIDE_YES | OUTCOME_SIDE_NO

    -- passive (maker): identity present ~46% (resting side is often anonymized by the venue)
    maker_username  TEXT,
    maker_side      TEXT,
    maker_intent    TEXT,
    maker_outcome   TEXT,

    -- clocks (see header): exchange clock + local receive. Latency derived at read.
    trade_time      TIMESTAMPTZ      NOT NULL,   -- venue exchange clock (ns truncated to µs by pg)
    recv_at         TIMESTAMPTZ      NOT NULL DEFAULT now(),

    -- provenance / source quality
    source          TEXT             NOT NULL DEFAULT 'gateway_ws'
);

-- Dedup: survive reconnect/replay. ns-precision trade_time makes genuine collisions ~impossible,
-- but a reconnect can re-deliver a just-seen print. NULLs are COALESCE'd because a UNIQUE index
-- treats raw NULLs as distinct (which would DEFEAT dedup on the 54% of prints with no maker id).
CREATE UNIQUE INDEX IF NOT EXISTS us_trade_tape_dedup ON us_trade_tape
    (us_slug, trade_time, price, quantity,
     COALESCE(taker_username, ''), COALESCE(maker_username, ''), COALESCE(taker_side, ''));

-- Per-trader history (the whole point): "everything <username> ever did", newest first.
CREATE INDEX IF NOT EXISTS idx_us_tape_taker ON us_trade_tape (taker_username, trade_time)
    WHERE taker_username IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_us_tape_maker ON us_trade_tape (maker_username, trade_time)
    WHERE maker_username IS NOT NULL;
-- Per-market tape + venue-wide time scans.
CREATE INDEX IF NOT EXISTS idx_us_tape_slug ON us_trade_tape (us_slug, trade_time);
CREATE INDEX IF NOT EXISTS idx_us_tape_time ON us_trade_tape (trade_time);
