-- 047: US-VENUE MID TAPE — the true-mid series that makes an HONEST markout possible.
--
-- WHY THIS TABLE EXISTS (and why the trade tape alone is NOT enough)
-- ------------------------------------------------------------------
-- The crux question of the US-venue economics run is: what does it COST to be the resting
-- (maker) side on this venue? That cost is adverse selection — the resting quote fills exactly
-- when informed flow runs it over — and it is measured as a MARKOUT: how far the fair value
-- moves against the maker in the N seconds after their fill.
--
-- 043 (us_trade_tape) gives us the fills, WITH maker identity on ~48% of prints. It is tempting
-- to compute the markout from subsequent TRADE PRICES in the same market. THAT WOULD BE WRONG,
-- and wrong in the direction that manufactures a fake edge:
--
--   Prints alternate between the bid and the ask (bid-ask bounce). A maker who BUYS at the bid
--   will see subsequent prints average ABOVE their fill — roughly at the mid — for no reason
--   other than the bounce. A trade-price markout therefore reports the HALF-SPREAD AS PROFIT and
--   makes every maker look profitable, regardless of how badly they are being picked off.
--
-- That is precisely the error class behind the retracted "+4.8% maker-copy" result (two bugs,
-- corrected to EDGE~=0) and the reason the market-making thesis needs a REAL measurement rather
-- than a plausible one. An honest markout must be measured against the MID, which cancels the
-- bounce. So we need a mid series at trade-time resolution. This table is that series.
--
-- SOURCE / SCOPE
-- --------------
-- Venue-wide MARKET_DATA on the same undocumented public WS as 043
--   {"subscribe":{"subscriptionType":"SUBSCRIPTION_TYPE_MARKET_DATA","marketSlugs":[]}}
-- delivers the FULL book (bids/offers) per market, pushed on update, with an exchange clock
-- (transactTime, ns). Measured venue-wide: ~733 msg/s, of which ~241/s actually change the BBO
-- (~21M rows/day) across 8,682 markets. Persisting that whole firehose is pointless: a markout
-- only needs a mid for markets that actually TRADE (measured: only ~180 distinct markets trade
-- in a 5-minute window), and the liquidity-reward model only needs depth in the INCENTIVE-POOL
-- families. So the writer is scoped to exactly those two sets (see us_mid_tape.py) — which is
-- also why this table stays small enough to query fast.
--
-- WHAT ELSE IT CARRIES (and why)
-- ------------------------------
-- Depth NEAR THE TOUCH (size within 1c/2c/5c of mid, each side) is not decoration: the venue's
-- Liquidity Incentive Program scores a resting order by price-proximity x size and splits the
-- pool PRO-RATA against every other resting order. So our reward share is
--     our_size_score / (our_size_score + COMPETITORS' size_score)
-- and the competitors' term IS this depth. Without it, any reward estimate is a nominal number
-- read off the published schedule rather than a realized one — the exact overclaim the run brief
-- forbids (a published pool is a schedule, not income).
--
-- CONVENTIONS INHERITED (040/042/043, deliberately)
--   * Additive & idempotent; NEVER edit after apply (an edited applied migration crash-loops
--     sqlx -- see [[feedback-applied-migrations-immutable]]).
--   * TWO clocks, never a precomputed lag: `transact_time` (venue exchange clock) + `recv_at`
--     (local). Any latency is DERIVED at read.
--   * `source` records the rung ('gateway_ws' == undocumented public WS, Rung 2).

CREATE TABLE IF NOT EXISTS us_mid_tape (
    id              BIGSERIAL PRIMARY KEY,

    us_slug         TEXT             NOT NULL,   -- joins us_trade_tape.us_slug / us_quotes.us_slug

    -- top of book. NULL on a one-sided book (which is itself decision-relevant: you cannot
    -- compute a mid, and a maker resting there has no counterparty reference).
    best_bid        DOUBLE PRECISION,
    best_bid_qty    DOUBLE PRECISION,
    best_ask        DOUBLE PRECISION,
    best_ask_qty    DOUBLE PRECISION,
    mid             DOUBLE PRECISION,            -- (bid+ask)/2, NULL if one-sided
    spread          DOUBLE PRECISION,            -- ask-bid, NULL if one-sided

    -- depth near the touch -> the PRO-RATA DENOMINATOR of the liquidity-reward model
    bid_qty_1c      DOUBLE PRECISION,            -- resting size within 1c of mid, bid side
    bid_qty_2c      DOUBLE PRECISION,
    bid_qty_5c      DOUBLE PRECISION,
    ask_qty_1c      DOUBLE PRECISION,
    ask_qty_2c      DOUBLE PRECISION,
    ask_qty_5c      DOUBLE PRECISION,
    bid_qty_total   DOUBLE PRECISION,
    ask_qty_total   DOUBLE PRECISION,

    -- venue stats carried on every book message (free; sizes the market for capacity/pool work)
    open_interest   DOUBLE PRECISION,
    shares_traded   DOUBLE PRECISION,
    notional_traded DOUBLE PRECISION,
    last_trade_px   DOUBLE PRECISION,
    state           TEXT,                        -- MARKET_STATE_OPEN | ...

    -- why this slug is being tracked: 'traded' (in the rolling active set -> markout universe)
    -- or 'pool' (an incentive-pool family we track even when idle, because the liquidity reward
    -- pays for RESTING, not for filling).
    track_reason    TEXT,

    -- clocks (see header)
    transact_time   TIMESTAMPTZ      NOT NULL,   -- venue exchange clock (ns truncated to us by pg)
    recv_at         TIMESTAMPTZ      NOT NULL DEFAULT now(),

    source          TEXT             NOT NULL DEFAULT 'gateway_ws'
);

-- Dedup across reconnects (a reconnect re-snapshots every market).
CREATE UNIQUE INDEX IF NOT EXISTS us_mid_tape_dedup ON us_mid_tape
    (us_slug, transact_time, COALESCE(best_bid, -1), COALESCE(best_ask, -1),
     COALESCE(best_bid_qty, -1), COALESCE(best_ask_qty, -1));

-- THE markout access path: "the mid for slug S as of time T" (asof join from each fill).
CREATE INDEX IF NOT EXISTS idx_us_mid_slug_time ON us_mid_tape (us_slug, transact_time);
CREATE INDEX IF NOT EXISTS idx_us_mid_time ON us_mid_tape (transact_time);
