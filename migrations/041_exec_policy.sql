-- Execution-policy shadow (PAPER-ONLY, prereg 2026-07-09T02:05Z): per-signal
-- fire-time top-of-book snapshot + frozen per-policy entries, evaluated ONCE
-- from the live CLOB tape (clob_price_tape, 72h retention) while it is fresh,
-- then booked into honest_paper_ledger at resolution under policy-suffixed
-- strategy labels (exec_fire:/exec_p15:/exec_mrest:<strategy>).
--
-- Durability rationale: the tape self-prunes at 72h — the fire-time book on a
-- signal is unrecoverable later, exactly like entry_ask (migration 032). This
-- table freezes it forever. Additive only: no existing table/row is touched;
-- with EXEC_POLICY_SHADOW=false (default) nothing writes here.
CREATE TABLE IF NOT EXISTS exec_policy_entries (
    signal_id      BIGINT PRIMARY KEY,          -- consensus_signals.id (no FK: decoupled, like the ledger)
    strategy       TEXT NOT NULL,
    condition_id   TEXT NOT NULL,
    outcome_index  INTEGER NOT NULL,
    fired_at       TIMESTAMPTZ NOT NULL,        -- consensus_signals.first_detected_at
    evaluated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Fire-time top of book: last tape inflection at recv_at <= fired_at,
    -- staleness <= 900s. NULLs = no fresh tape coverage (recorded, not retried).
    bid_fire       DOUBLE PRECISION,
    ask_fire       DOUBLE PRECISION,
    mid_fire       DOUBLE PRECISION,            -- (bid_fire + ask_fire) / 2, the P-MREST limit
    tape_at_fire   TIMESTAMPTZ,
    -- Patient taker: best_ask at fired_at + 15 min (same staleness rule).
    ask_p15        DOUBLE PRECISION,
    -- Resting maker BUY at mid_fire, cancel 30 min:
    maker_touch    BOOLEAN NOT NULL DEFAULT FALSE, -- OPTIMISTIC: best_ask <= limit (quote flicker; never booked)
    maker_print    BOOLEAN NOT NULL DEFAULT FALSE, -- REALISTIC: price_change PRINT at last_price <= limit, size > 0
    maker_fill_at  TIMESTAMPTZ,                 -- first REALISTIC print time, if any
    -- Ledger booking state: set TRUE once the signal resolved and the policy
    -- bets were appended (idempotently) to honest_paper_ledger.
    booked         BOOLEAN NOT NULL DEFAULT FALSE
);

-- The evaluator's two scans: unbooked rows awaiting resolution, and per-market lookups.
CREATE INDEX IF NOT EXISTS idx_exec_policy_unbooked
    ON exec_policy_entries (booked) WHERE NOT booked;
CREATE INDEX IF NOT EXISTS idx_exec_policy_cond
    ON exec_policy_entries (condition_id, outcome_index);
