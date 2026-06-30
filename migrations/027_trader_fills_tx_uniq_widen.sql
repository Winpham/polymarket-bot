-- 027: Widen the tx-present dedup index so legitimately-distinct same-tx fills
-- are NOT silently collapsed (mission pillar #1 = capture ALL the data).
--
-- 026's `trader_fills_tx_uniq (tx_hash, condition_id, outcome_index)` deduped on
-- transaction alone, so two fills sharing a `transactionHash` on the same
-- (condition, outcome) but differing in side/price — e.g. a market order swept
-- across price levels reported as one event per partial fill — collapsed to a
-- single row, undercounting `size_usd`, losing price diversity, and diverging
-- from the `consensus_vote_window` key (which includes `price`). Add `side` and
-- `price` to match the null-tx content index's discriminators. Re-seen identical
-- fills still dedup (same tx+cond+outcome+side+price). The new index is strictly
-- looser, so it can't conflict with any rows the old one already admitted.
DROP INDEX IF EXISTS trader_fills_tx_uniq;
CREATE UNIQUE INDEX IF NOT EXISTS trader_fills_tx_uniq
    ON trader_fills (tx_hash, condition_id, outcome_index, side, price)
    WHERE tx_hash IS NOT NULL;
