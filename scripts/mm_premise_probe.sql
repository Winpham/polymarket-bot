-- mm_premise_probe.sql — reproducible probe of the "top wallets are market-makers" thesis.
--
-- WHY THIS FILE EXISTS: the original argument (two-leg sum 1.05-1.22, 36-44% locked,
-- -4.4%/-2.8% resolution holds, $36.6M churn) was produced in an ad-hoc console session
-- and never saved. This file persists the queries so the finding is reproducible.
--
-- Run:  docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket -P pager=off -f - < scripts/mm_premise_probe.sql
-- Data caveats (do NOT over-claim): trader_fills has NO maker/taker flag; SELLs are ~11% of
-- fills and backfill is capped at 10k offset/wallet (clips the very highest-churn bots); ts on
-- backfilled rows are crawl stamps (bad for within-market ordering); liquidity-REWARD income is
-- off-chain and NOT in this table, so we can only measure the resolution-hold leg, never total P&L.

-- (1) MM-signature scan: top wallets by volume. Look for sell_frac≈0 + high twosided_frac (buy-both-hold)
--     or high sell_frac (round-trip spread capture), plus fills-per-day in the thousands (bot).
WITH w AS (
  SELECT wallet, sum(size_usd) vol, count(*) fills,
         count(*) FILTER (WHERE side='SELL')::float / NULLIF(count(*),0) sell_frac,
         count(DISTINCT condition_id) mkts, count(DISTINCT ts::date) active_days
  FROM trader_fills GROUP BY wallet),
twosided AS (
  SELECT wallet, count(*) FILTER (WHERE n_sides>=2)::float / NULLIF(count(*),0) twosided_frac
  FROM (SELECT wallet, condition_id, count(DISTINCT outcome_index) n_sides
        FROM trader_fills WHERE side='BUY' GROUP BY wallet, condition_id) s GROUP BY wallet)
SELECT substr(w.wallet,1,8) wallet, round(w.vol::numeric,0) vol_usd, w.fills,
       round((w.fills::numeric/NULLIF(w.active_days,0)),0) fills_per_day,
       round(w.sell_frac::numeric,3) sell_frac,
       round(t.twosided_frac::numeric,3) twosided_frac, w.mkts
FROM w JOIN twosided t USING(wallet) ORDER BY w.vol DESC LIMIT 15;

-- (2) Buy-both-hold cohort: true two-leg price sum + realized resolution-hold ROI.
--     sum<1 = locked (risk-free); sum>1 = pays a premium it must earn back via rewards.
--     Negative resolution ROI on a rational high-churn bot ⇒ rewards are the real profit engine.
WITH cohort(wallet) AS (VALUES ('0x204f72')),  -- flagship $38M wallet; extend VALUES to add peers
legs AS (
  SELECT tf.condition_id, tf.outcome_index,
         sum(tf.size_usd) usd, sum(tf.size_usd/NULLIF(tf.price,0)) shares,
         bool_or(tf.outcome_won) won_side,
         sum(tf.size_usd)/NULLIF(sum(tf.size_usd/NULLIF(tf.price,0)),0) leg_price
  FROM trader_fills tf JOIN cohort c ON left(tf.wallet,8)=c.wallet
  WHERE tf.side='BUY' AND tf.resolved GROUP BY tf.condition_id, tf.outcome_index),
mkt AS (
  SELECT condition_id, count(*) n_sides, sum(usd) total_cost,
         sum(shares) FILTER (WHERE won_side) shares_won, sum(leg_price) two_leg_sum
  FROM legs GROUP BY condition_id HAVING count(*)=2)
SELECT count(*) paired_mkts,
       round(avg(two_leg_sum)::numeric,4) avg_two_leg_sum,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY two_leg_sum)::numeric,4) median_sum,
       round((count(*) FILTER (WHERE two_leg_sum<1.0))::numeric/count(*),3) frac_locked_sub1,
       round(sum(COALESCE(shares_won,0)-total_cost)::numeric,0) net_resolution_pnl_usd,
       round((sum(COALESCE(shares_won,0)-total_cost)/NULLIF(sum(total_cost),0)*100)::numeric,2) resolution_roi_pct
FROM mkt;

-- (3) Round-trip spread capture: for a wallet with real SELLs, did it buy low & sell high on the
--     SAME token? Positive avg(sell_price - buy_price) = captured bid-ask spread.
WITH rt AS (
  SELECT condition_id, outcome_index,
         sum(size_usd/NULLIF(price,0)) FILTER (WHERE side='BUY')  buy_sh,
         sum(size_usd/NULLIF(price,0)) FILTER (WHERE side='SELL') sell_sh,
         sum(size_usd) FILTER (WHERE side='BUY')  buy_usd,
         sum(size_usd) FILTER (WHERE side='SELL') sell_usd
  FROM trader_fills WHERE left(wallet,8)='0xe9076a' GROUP BY condition_id, outcome_index)
SELECT count(*) FILTER (WHERE buy_sh>0 AND sell_sh>0) tokens_roundtripped,
       round(avg(sell_usd/NULLIF(sell_sh,0) - buy_usd/NULLIF(buy_sh,0))
             FILTER (WHERE buy_sh>0 AND sell_sh>0)::numeric,4) avg_sell_minus_buy_price
FROM rt;
