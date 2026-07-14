-- 048: US-VENUE INCENTIVE PROGRAMS — the REAL, per-market reward parameters.
--
-- WHY THIS TABLE EXISTS
-- ---------------------
-- The US venue pays a Liquidity Incentive Program: resting orders are scored EVERY SECOND by
-- price-proximity x size, and the market's reward pool is split PRO-RATA among all resting
-- traders — whether their orders fill or not. That fill-independent subsidy is the one economic
-- object that did not exist on the international book, and it is the only reason the KILLED
-- market-making thesis ([[project-polymarket-market-making]], $0-falsified at 13x hazard/reward)
-- is worth reopening on US at all.
--
-- So the reward number must be REAL, not quoted. The run brief carried figures like
-- "World Cup $75k/game, MLB $12.5k/game, Climate $1k/day" — those are NOT what the venue
-- actually publishes per market, and paying ourselves the wrong number is how a subsidy turns
-- into a phantom edge. The truth is a public, unauthenticated endpoint:
--
--     GET https://api.prod.polymarketexchange.com/v1/incentives?statuses=active
--
-- which returns, PER MARKET SLUG, the actual `rewardPool` (USD), `targetSize` (max contracts per
-- side that count toward scoring), `discountFactor` (how hard orders away from the touch are
-- penalized), `period`, and `status`. Measured 2026-07-14: 2,400 active markets / 3,976 program
-- rows / $5,734,000 total — but a MEDIAN pool of $500 per market and a MAX of $14,000. The
-- headline "$75k/game" is the sum across ALL of a game's markets; the reward is split per market.
-- We rest per market, so the per-market pool is the number that pays us. This table stores it.
--
-- Rewards are pro-rata, and we do NOT observe our competitors' identities — only their resting
-- SIZE (us_mid_tape near-touch depth). So a pool here is a CEILING on what the market pays out
-- in total, never our income. Any claim of realized reward must divide it by an observed
-- denominator; a bare pool figure is a published schedule, not money (run brief, hard rule 6).
--
-- SNAPSHOTTED, NOT UPSERTED
-- -------------------------
-- Pools and parameters CHANGE (a market moves from 'pending' to 'active' to 'closed'; pools are
-- re-funded per period). We append a snapshot per fetch rather than overwrite, so the reward
-- model can be evaluated against the parameters that were true AT THE TIME a fill happened,
-- rather than against today's. Same discipline as the two-clock rule: never destroy the past to
-- make the present tidy.
--
-- CONVENTIONS: additive & idempotent; NEVER edit after apply ([[feedback-applied-migrations-immutable]]).

CREATE TABLE IF NOT EXISTS us_incentive_program (
    id               BIGSERIAL PRIMARY KEY,

    us_slug          TEXT             NOT NULL,   -- joins us_trade_tape / us_mid_tape / us_quotes
    program_id       TEXT,
    program_type     TEXT,                        -- 'liquidityProgram' (the only type seen live)

    reward_pool      DOUBLE PRECISION,            -- USD for the market over the period (a CEILING)
    target_size      DOUBLE PRECISION,            -- max contracts PER SIDE that count for scoring
    discount_factor  DOUBLE PRECISION,            -- penalty on orders away from the best price
    period           TEXT,                        -- 'live' | 'day_of' | ...
    status           TEXT,                        -- 'active' | 'pending' | 'closed'

    starts_at        TIMESTAMPTZ,
    ends_at          TIMESTAMPTZ,
    created_at_venue TIMESTAMPTZ,

    fetched_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),   -- our snapshot clock
    source           TEXT             NOT NULL DEFAULT 'incentives_api'
);

-- One row per (program, parameter-set) per fetch: a re-fetch with UNCHANGED parameters collapses,
-- while any real change to the pool/target/discount/status appends a new row. That gives a
-- parameter HISTORY without the tape growing on every poll.
CREATE UNIQUE INDEX IF NOT EXISTS us_incentive_program_dedup ON us_incentive_program
    (us_slug, COALESCE(program_id, ''), COALESCE(reward_pool, -1), COALESCE(target_size, -1),
     COALESCE(discount_factor, -1), COALESCE(status, ''), COALESCE(period, ''));

CREATE INDEX IF NOT EXISTS idx_us_incentive_slug ON us_incentive_program (us_slug, fetched_at);
CREATE INDEX IF NOT EXISTS idx_us_incentive_pool ON us_incentive_program (reward_pool DESC)
    WHERE status = 'active';
