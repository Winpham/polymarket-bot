-- Forward paper ledger for the FINAL-HOUR FAVOURITE late-convergence test
-- (PREREG_20260715_final_hour_favourite.md). Append-only, isolated from the live bot's tables.
-- One signal per (us_slug): the FIRST time a live game-state feed reports the market's favourite is
-- NEAR-DECIDED while the US book prices it in [0.65,0.92]. Settlement is filled FORWARD (official DMR
-- when available, else terminal market state), so no retrospective settlement artifact can occur.
-- This test proves/kills what a backtest structurally cannot: a live, out-of-sample, realizable-price
-- edge on a live-knowable trigger.

CREATE TABLE IF NOT EXISTS finalhour_paper_signals (
    id            BIGSERIAL PRIMARY KEY,
    us_slug       TEXT NOT NULL,
    sport         TEXT NOT NULL,                  -- 'tennis_atp' | 'tennis_wta' | 'esports_cs2' ...
    event_key     TEXT NOT NULL,
    signal_ts     TIMESTAMPTZ NOT NULL,           -- when the near-decided trigger fired
    entry_ask     DOUBLE PRECISION NOT NULL,      -- the real US ask we would pay as a taker
    entry_mid     DOUBLE PRECISION NOT NULL,      -- fair mid at signal time
    entry_spread  DOUBLE PRECISION,               -- best_ask - best_bid at fire (realized-cost audit)
    feed_state    TEXT NOT NULL,                  -- the near-decided evidence, e.g. 'sets 2-0; 3rd 4-2'
    feed_src      TEXT NOT NULL,                  -- 'espn_atp' | 'espn_wta' | 'bo3gg' ...
    -- settlement, filled forward:
    settled       BOOLEAN NOT NULL DEFAULT FALSE,
    outcome       DOUBLE PRECISION,               -- 0.0 / 1.0 (favourite side)
    settle_ts     TIMESTAMPTZ,
    settle_src    TEXT,                           -- 'dmr' | 'state_expired' | 'terminal_px'
    net           DOUBLE PRECISION,               -- outcome - entry_ask - fee(entry_ask)
    clv_close     DOUBLE PRECISION,               -- last non-degenerate mid after entry (for lambda)
    -- warm-up: the feed/book had <30 min of history at fire time, so the trigger context is truncated;
    -- excluded from the pre-registered gate (clean = warmup=FALSE only).
    warmup        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (us_slug)
);

CREATE INDEX IF NOT EXISTS idx_fhps_unsettled ON finalhour_paper_signals (settled) WHERE NOT settled;
CREATE INDEX IF NOT EXISTS idx_fhps_sport ON finalhour_paper_signals (sport);
CREATE INDEX IF NOT EXISTS idx_fhps_event ON finalhour_paper_signals (event_key);
