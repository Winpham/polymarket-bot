-- Decision-time provenance for the executable entry ask (Phase 1).
--
-- `entry_ask` (mig 030) stores the real best ASK captured once while a market was
-- open, so the honest P&L can use the price a follower could truly have paid
-- instead of the `initial_market_price + EXEC_HAIRCUT` heuristic. But a bare ask
-- can't tell us WHEN it was captured or whether the assumed 1¢ haircut was right.
--
-- These two columns pair the ask with its moment:
--   * `entry_ask_at`  — when the ask was captured. Compared to `first_detected_at`
--     it PROVES the capture was decision-time (seconds/minutes) vs lagged (hours),
--     so the realized ROI can filter to decision-time-only rows.
--   * `entry_ask_mid` — the CLOB mid at the SAME instant the ask was captured. The
--     real execution haircut is then MEASURED as `entry_ask − entry_ask_mid`,
--     replacing the guessed `EXEC_HAIRCUT`. On a decision-time capture this equals
--     the `initial_market_price` frozen in the same housekeeping pass.
--
-- Additive + non-destructive: two nullable columns, written set-once alongside
-- `entry_ask` (COALESCE-once, `resolved = FALSE`) — never overwritten, never
-- written post-resolution (leak-free). Pre-032 / uncaptured rows leave them NULL
-- and the honest query falls back to the mid+haircut heuristic. No backfill.
ALTER TABLE consensus_signals
    ADD COLUMN IF NOT EXISTS entry_ask_at  TIMESTAMPTZ,       -- when the ask was captured
    ADD COLUMN IF NOT EXISTS entry_ask_mid DOUBLE PRECISION;  -- CLOB mid at that same instant
