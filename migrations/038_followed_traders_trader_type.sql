-- 038_followed_traders_trader_type.sql — advisory classification of tracked wallets
-- as high-frequency market-maker 'bot' vs 'human' picker, derived from captured
-- fills (see cycles/backfill.rs::classify_trader_types). Nullable, no default, no
-- backfill: NULL = unclassified. Nothing in the live alert path reads it; the
-- specialist/selection layer filters on it so it profiles humans who pick, not
-- liquidity bots. Additive column (metadata-only, no table rewrite).
ALTER TABLE followed_traders ADD COLUMN IF NOT EXISTS trader_type TEXT;
