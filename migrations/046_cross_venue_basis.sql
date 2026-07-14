-- 046: CROSS-VENUE BASIS & ARBITRAGE (the two-book payoff).
--
-- WHAT THIS IS
-- -----------
-- Tue now has legal access to BOTH books: Polymarket US (KYC'd, fee-paying) and the
-- international CLOB (via a family member abroad). They are SEPARATE exchanges with SEPARATE
-- liquidity ([[project-polymarket-us-venue]]) — so the same real-world outcome can trade at two
-- different prices at the same instant. This table records that price gap, per mapped contract,
-- and whether it is a RISK-FREE arbitrage after fees.
--
-- THE ARB STRUCTURE (why it can be risk-free)
-- -------------------------------------------
-- A binary event pays exactly $1 to the winning side. If you buy outcome O on the venue where O
-- is cheap AND buy the COMPLEMENT (¬O) on the venue where ¬O is cheap, you hold both sides of the
-- same event for a combined cost C. At settlement one side pays $1. If C < $1 − fees, the
-- difference is locked in regardless of outcome. This is only valid if the two contracts settle
-- to the SAME event — which is exactly what the mapper certifies (406/406 resolution agreement),
-- and why every row carries `mapper_conf` and only conf ≥ 0.90 matches are scanned.
--
-- SIDE-CORRECTNESS IS LOAD-BEARING (inherited from 042)
-- ----------------------------------------------------
-- US /bbo quotes ONLY side_index 0; buying side 1 means our_ask(1) = 1 − best_bid(0). Reading
-- bestAsk side-blind is a SILENT PRICE INVERSION that produced a phantom 90¢ basis once. This
-- scanner reuses us_quote_capture.our_side_quote() by IMPORT, so the vetted complement logic is
-- not reimplemented here. intl legs come straight from clob_price_tape (best_ask of the leg for
-- outcome_index O is, directly, the price to buy O on intl).
--
-- HONESTY (the evidence rule)
-- --------------------------
-- * A control arm (`is_placebo`) — matched non-signal markets scanned identically — because a
--   basis without a control is not evidence (the retracted 15-min=8¢ finding).
-- * Both capture clocks + `intl_age_s`: the US quote is fetched live; the intl leg is the freshest
--   clob_price_tape row, which has an age. A stale intl leg FAILS CLOSED (is_actionable=false),
--   never silently prices an order.
-- Additive/idempotent; safe to apply once, never edit.

CREATE TABLE IF NOT EXISTS cross_venue_basis (
    id              BIGSERIAL PRIMARY KEY,

    signal_id       INTEGER,
    condition_id    TEXT,
    outcome_index   INTEGER,                     -- the intl leg O (our outcome)
    us_slug         TEXT        NOT NULL,
    us_side_index   INTEGER,                     -- US side that == outcome O
    mapper_conf     DOUBLE PRECISION,

    -- prices to BUY, side-aligned, for outcome O and its complement ¬O, on each venue
    us_ask_o        DOUBLE PRECISION,
    us_ask_comp     DOUBLE PRECISION,
    intl_ask_o      DOUBLE PRECISION,
    intl_ask_comp   DOUBLE PRECISION,

    -- same-outcome price gap (routing/execution signal, not arb): >0 ⇒ US dearer for O
    basis_o         DOUBLE PRECISION,            -- us_ask_o − intl_ask_o

    -- the two risk-free legs; cost to own BOTH sides of the event
    arb_us_intl     DOUBLE PRECISION,            -- buy O on US + ¬O on intl
    arb_intl_us     DOUBLE PRECISION,            -- buy O on intl + ¬O on US
    best_arb_cost   DOUBLE PRECISION,            -- min of the two (NULL if a leg missing)
    fee_total       DOUBLE PRECISION,            -- US taker fee on the US leg (intl assumed 0)
    arb_edge        DOUBLE PRECISION,            -- 1 − best_arb_cost − fee_total  (>0 ⇒ profit)
    is_actionable   BOOLEAN     NOT NULL DEFAULT FALSE,   -- arb_edge>0 AND fresh AND both legs present

    -- honesty
    intl_age_s      DOUBLE PRECISION,            -- age of the intl clob leg used (staleness)
    is_placebo      BOOLEAN     NOT NULL DEFAULT FALSE,
    us_ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    recv_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_xvenue_actionable ON cross_venue_basis (is_actionable, recv_at)
    WHERE is_actionable;
CREATE INDEX IF NOT EXISTS idx_xvenue_slug ON cross_venue_basis (us_slug, recv_at);
CREATE INDEX IF NOT EXISTS idx_xvenue_recv ON cross_venue_basis (recv_at);
