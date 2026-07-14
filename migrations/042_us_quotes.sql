-- US-VENUE FORWARD QUOTE CAPTURE (Phase C/D spine).
--
-- WHY THIS TABLE HAS TO EXIST, AND WHY IT IS URGENT
-- ------------------------------------------------
-- The decisive question of the US-venue run is: "does the international consensus signal
-- still certify when priced at the US book, after the US fee?"
--
-- It CANNOT BE ANSWERED FROM HISTORY. Polymarket US publishes no price history at all:
-- /candles, /prices-history, /trades and every other timestamped endpoint 404, and /bbo on a
-- settled market returns bestBid=NULL, bestAsk=NULL — only a settlement price. There is no
-- US ask at any of our past fire times, anywhere, and no amount of re-analysis conjures one.
--
-- So the US basis can only ever be measured FORWARD. Every day this capture is off is a day
-- of realizable-edge truth that can never be recovered — the same irreversible clock as the
-- at-fire ask capture (migration 041), for the same reason.
--
-- WHAT IT HOLDS
-- Point-in-time quotes for the US instrument that our INTERNATIONAL signal maps onto, so the
-- basis (us_ask - intl_ask) can be computed at, and after, the moment the signal fires.
--
-- `capture_lag_s` is stored, not assumed. The whole D4 saga was a lagged capture masquerading
-- as a decision-time one, and the lag being invisible is what let it poison every gate for
-- weeks. Here it is a column, so any analysis can filter on it and no one has to trust a
-- comment.
--
-- The placebo arm is a FIRST-CLASS CITIZEN (`is_placebo`), not an afterthought. The retracted
-- "15 min = 8¢" latency finding collapsed to +2.05¢ ± 4.0¢ (p=0.36) the moment a matched
-- control was finally added — and the placebo median had drifted MORE than the treatment. A
-- basis study without a control arm is not evidence, and if the control is not captured in
-- the same table by the same code path at the same instants, it will not exist when it is
-- needed.

CREATE TABLE IF NOT EXISTS us_quotes (
    id              BIGSERIAL PRIMARY KEY,

    -- the INTL side (what we have a signal on)
    signal_id       INTEGER REFERENCES consensus_signals(id) ON DELETE CASCADE,
    condition_id    TEXT,
    outcome_index   INTEGER,

    -- the US side (what we could actually trade)
    us_slug         TEXT        NOT NULL,
    us_side         TEXT,                   -- the side_desc entry we would BUY ("Yes" / a name)
    us_side_index   INTEGER,                -- its index in side_desc == its index in outcomePrices

    -- the quote itself
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    best_bid        DOUBLE PRECISION,
    best_ask        DOUBLE PRECISION,
    bid_depth_usd   DOUBLE PRECISION,       -- $ resting at the touch
    ask_depth_usd   DOUBLE PRECISION,
    last_trade_px   DOUBLE PRECISION,
    shares_traded   DOUBLE PRECISION,

    -- honesty columns
    capture_lag_s   DOUBLE PRECISION,       -- ts - signal.first_detected_at. STORED, never assumed.
    mapper_conf     DOUBLE PRECISION,       -- the mapper's confidence for this pair
    is_placebo      BOOLEAN     NOT NULL DEFAULT FALSE  -- matched control, captured identically
);

CREATE INDEX IF NOT EXISTS idx_us_quotes_signal ON us_quotes (signal_id, ts);
CREATE INDEX IF NOT EXISTS idx_us_quotes_slug   ON us_quotes (us_slug, ts);
CREATE INDEX IF NOT EXISTS idx_us_quotes_ts     ON us_quotes (ts);

-- THE PRICE WE WOULD ACTUALLY PAY, for the side WE would actually buy.
--
-- `/bbo` quotes ONE side of the binary (side_index 0 — "Yes" on a proposition market). It does
-- NOT quote our side. When we are buying side 1 ("No"), our ask is the complement of THEIR
-- BID:   our_ask(1) = 1 - best_bid,   our_bid(1) = 1 - best_ask.
--
-- Reading `bestAsk` regardless of side is a SILENT PRICE INVERSION. The first capture sweep
-- did exactly that and produced a basis of -0.57 to -0.93 — a 90-cent "disagreement" between
-- two venues on the same event, which is impossible, and is what exposed the bug. These
-- columns exist so that no downstream query can reach for the side-blind quote by accident:
-- `our_ask` is the ONLY column a gate may price against.
ALTER TABLE us_quotes
    ADD COLUMN IF NOT EXISTS our_bid DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS our_ask DOUBLE PRECISION;
