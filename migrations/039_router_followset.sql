-- Proven-trader router follow-set (PREREG_2026-07-04T094304Z_proven_router.md, paper-only).
--
-- Append-only membership snapshots: each hourly re-score inserts one batch keyed by
-- `scored_at`; the `proven_router` arm reads ONLY the latest batch, and the full history
-- is preserved so forward evaluation can reconstruct membership as-of any time (who was
-- in the follow-set when a signal fired — required for an honest out-of-sample read).
--
-- Membership criteria are FROZEN in the pre-registration and implemented in
-- `refresh_router_followset` (common/src/storage/consensus.rs): trailing-365d BUY fills,
-- entry band 0.45–0.90, repriced at OUR entry (+1.3¢ follower tax + pooled band spread),
-- event-clustered copy-return ≥ +10% over ≥100 resolved fills and ≥15 distinct days,
-- market-maker-shaped wallets excluded by position-grain microstructure.
CREATE TABLE IF NOT EXISTS router_followset (
    scored_at       TIMESTAMPTZ      NOT NULL,
    wallet          TEXT             NOT NULL,
    copy_return     DOUBLE PRECISION NOT NULL,  -- event-clustered modeled copy-return, trailing window
    n_fills         BIGINT           NOT NULL,  -- resolved scored fills in the window
    n_events        BIGINT           NOT NULL,  -- distinct COALESCE(event_slug, condition_id) clusters
    n_days          BIGINT           NOT NULL,  -- distinct UTC fill-days (the day-deflation N)
    lower_bound     DOUBLE PRECISION,           -- diagnostic 95% day-deflated LB (NOT the gate)
    round_trip_rate DOUBLE PRECISION,           -- microstructure audit trail (MM screen inputs)
    two_sided_rate  DOUBLE PRECISION,
    sell_buy_ratio  DOUBLE PRECISION,
    PRIMARY KEY (scored_at, wallet)
);

CREATE INDEX IF NOT EXISTS idx_router_followset_scored_at ON router_followset (scored_at DESC);
