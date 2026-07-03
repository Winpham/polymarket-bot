-- 037_trader_fills_bettype.sql — freeze a market bet-structure bucket at capture,
-- mirroring the nullable `sport` column (migration 026). NULL ⇒ 'other' at read
-- (COALESCE in the slice CTEs); no backfill — historical rows read 'other' until
-- re-captured, exactly how `sport` degrades. Adding a nullable column with a
-- default of NULL is metadata-only (no table rewrite). See FORGE_PLAN Item 2 / GAP-2.
ALTER TABLE trader_fills ADD COLUMN IF NOT EXISTS bet_type TEXT;
