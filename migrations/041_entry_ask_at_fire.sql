-- At-fire executable ASK capture (STRATEGY-HANDOFF §4 — "the highest-value change
-- in the whole project").
--
-- WHY THIS EXISTS. `entry_ask` (mig 030/032) is captured on the first HOUSEKEEPING
-- pass that reaches an open signal — ~10-15 min after it fired. Markets that resolve
-- fast (obvious chalk -> winners) resolve BEFORE that pass and get no ask at all;
-- only slow, contested (loss-prone) markets get one. The ask-priced sample is
-- therefore selection-biased toward losers: win rate 85% among captured vs 98% among
-- uncaptured. Every "realizable" number computed on `entry_ask` is biased PESSIMISTIC
-- by ~7 points. That single bias is why the champion reads +1.30% realizable while
-- the (optimistic) mid basis reads +8.0% — and why neither is yet the truth.
--
-- These columns capture the ask at the INSTANT the signal fires, inside the consensus
-- cycle, so fast- and slow-resolving picks BOTH get a representative price.
--
-- Deliberately SEPARATE from `entry_ask` rather than overwriting it: keeping both lets
-- us MEASURE the bias directly (fire-ask vs housekeeping-ask on the same signal) and
-- prove the fix works before any number is re-based on it. Non-regressive by
-- construction — every existing query still reads `entry_ask` and is untouched.
--
-- `entry_ask_fire_mid` is a TRUE CLOB mid (bid+ask)/2 from ONE /book response
-- (common::data::models::BookTop). It is NOT the consensus vote-mean. Capture-defect
-- D2 was exactly that confusion — the historical "at-fire mid" was the vote-mean, which
-- understated real copier cost by ~1.65c. The execution haircut is then honestly
-- MEASURED as `entry_ask_fire - entry_ask_fire_mid`, both from the same instant.
--
-- BACKFILL IS IMPOSSIBLE. The at-fire book is gone the moment it moves; clob_price_tape
-- (mig 040) only starts 2026-07-09 and only covers subscribed markets — it holds a
-- fire-time ask for just 21 of 395 historical favorite signals. Every day without this
-- capture is a day whose true realizable edge can never be known. Same argument as
-- mig 036 and CAPTURE_ENTRY_ASK (D5).
--
-- Set-once, resolved-guarded, best-effort (see set_entry_ask_fire): a failure just
-- leaves the column NULL and every existing query falls back exactly as before.
--
-- (Numbered 042, not 041: migration 041 is reserved by the unmerged feat/exec-policy
-- branch. Version gaps are fine; a duplicate number is not.)
ALTER TABLE consensus_signals
    ADD COLUMN IF NOT EXISTS entry_ask_fire     DOUBLE PRECISION,  -- executable best ask AT FIRE
    ADD COLUMN IF NOT EXISTS entry_ask_fire_at  TIMESTAMPTZ,       -- when that ask was captured
    ADD COLUMN IF NOT EXISTS entry_ask_fire_mid DOUBLE PRECISION;  -- TRUE (bid+ask)/2 at that instant

-- Lets the honest queries find the at-fire-priced population without a seq scan.
CREATE INDEX IF NOT EXISTS idx_signals_entry_ask_fire
    ON consensus_signals (strategy, first_detected_at)
    WHERE entry_ask_fire IS NOT NULL;
