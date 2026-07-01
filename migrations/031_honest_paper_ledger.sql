-- Durable PAPER equity ledger for the honest P&L tracker (Phase 3).
--
-- One append-only row per resolved (strategy, market outcome) at the honest,
-- realizable entry (COALESCE(entry_ask, initial_market_price + haircut)). It is a
-- PAPER simulation only — this system NEVER places real money. The ledger is the
-- ongoing, self-updating track record: cumulative P&L, peak, drawdown, Sharpe.
--
-- Idempotent by construction: UNIQUE(strategy, condition_id, outcome_index) +
-- ON CONFLICT DO NOTHING at the append site, so re-running resolution (which
-- fires once per market) never double-counts. Read-only w.r.t. every live table.
CREATE TABLE IF NOT EXISTS honest_paper_ledger (
    id             SERIAL PRIMARY KEY,
    strategy       TEXT NOT NULL,
    condition_id   TEXT NOT NULL,
    outcome_index  INTEGER NOT NULL,
    resolved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stake          DOUBLE PRECISION NOT NULL,   -- paper $ staked
    entry          DOUBLE PRECISION NOT NULL,   -- realizable entry price paid
    outcome_won    BOOLEAN NOT NULL,            -- did the consensus outcome win?
    pnl            DOUBLE PRECISION NOT NULL,    -- stake × ((won − entry)/entry − fee)
    cum_equity     DOUBLE PRECISION NOT NULL,    -- running strategy equity at append time
    UNIQUE (strategy, condition_id, outcome_index)
);

CREATE INDEX IF NOT EXISTS idx_honest_ledger_strategy
    ON honest_paper_ledger(strategy, resolved_at, id);
