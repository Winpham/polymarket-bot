-- Additive decision-time (first-fire) capture for market_feature_log.
--
-- The existing upsert (migration 028 + log_market_features) re-logs each cycle
-- with ON CONFLICT DO UPDATE, so `features` drifts to the LAST pre-resolution
-- snapshot (freshest), not the first-strict-fire decision point a real bettor
-- would act on. These two columns preserve the FIRST snapshot alongside the
-- freshest one, so the forward market_resid trainer can read either.
--
-- Additive + non-destructive: nullable columns, backfilled GOING FORWARD only
-- (pre-existing rows keep NULL first_features until they are re-logged, at which
-- point the COALESCE upsert opportunistically backfills them). The accrued
-- `features`/`clob_mid` snapshots are untouched.
ALTER TABLE market_feature_log
    ADD COLUMN IF NOT EXISTS first_features    JSONB,        -- YES-oriented vector at first strict-fire (decision-time)
    ADD COLUMN IF NOT EXISTS first_captured_at TIMESTAMPTZ;  -- when that first snapshot was captured
