-- Real executable book-ask capture for the honest P&L tracker (Phase 2).
--
-- CLV is measured against `initial_market_price` (the first live MID we saw while
-- the market was open), and the honest edge subtracts a heuristic execution
-- haircut on top. But we actually BUY at the ASK, not the mid. This column stores
-- the real best ASK captured ONCE while the market was still open — the price a
-- follower could truly have paid — so the honest query can prefer it over the
-- mid+haircut heuristic where captured.
--
-- Additive + non-destructive: a single nullable column, written COALESCE-once
-- (never overwritten) and only while OPEN, exactly like `initial_market_price`.
-- When NULL (capture off, or the /book fetch failed, or a pre-existing row) the
-- honest query falls back to `initial_market_price + EXEC_HAIRCUT`. No backfill.
ALTER TABLE consensus_signals
    ADD COLUMN IF NOT EXISTS entry_ask DOUBLE PRECISION;  -- executable best ask captured once while open
