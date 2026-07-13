-- 043 — size-aware executable entry (the forward proof substrate).
--
-- WHY: `entry_ask` stores only the BEST ASK, and `honest_paper_ledger` books every paper bet at it —
-- i.e. it assumes we get the touch at ANY stake. The live-book slippage walk falsifies that beyond
-- ~$50: the cert-band weather book holds a median ~$54 within 1c of the touch, so a real stake WALKS
-- the ladder and pays a VWAP. A forward record booked at the touch would OVERSTATE P&L at any size we
-- would actually trade.
--
-- These columns record what a taker of a REAL, CONFIGURED stake would actually have paid, captured at
-- DECISION TIME from the same /book call that already produces `entry_ask`. Purely additive + nullable:
-- every incumbent read path (which uses `entry_ask` / `initial_market_price`) is untouched and
-- byte-identical. Measurement only — this arms nothing and books nothing.
ALTER TABLE consensus_signals
  ADD COLUMN IF NOT EXISTS entry_vwap             DOUBLE PRECISION,  -- VWAP walking the real ask ladder
  ADD COLUMN IF NOT EXISTS entry_vwap_stake       DOUBLE PRECISION,  -- the $ stake that VWAP prices
  ADD COLUMN IF NOT EXISTS entry_vwap_filled      DOUBLE PRECISION,  -- $ actually fillable (< stake ⇒ thin)
  ADD COLUMN IF NOT EXISTS entry_book_depth_1c    DOUBLE PRECISION;  -- $ resting within 1c of the touch
