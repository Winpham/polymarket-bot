-- Forward paper ledger for the collapse-risk model (pre-registered forward test).
-- Append-only, isolated from the live bot's tables. One signal per (us_slug) — the FIRST time a
-- market crosses >=0.80 AND passes the model's EV>0.00 gate — matching the one-DP-per-market
-- pre-registration (PREREG_20260715_collapse_model.md). EV is stored so EV>0.01/0.03 thresholds
-- are evaluated at analysis time. Settlement is filled FORWARD when the market matures, so none of
-- the retrospective T&S settlement artifacts can occur.

CREATE TABLE IF NOT EXISTS collapse_paper_signals (
    id            BIGSERIAL PRIMARY KEY,
    us_slug       TEXT NOT NULL,
    niche         TEXT NOT NULL,
    event_key     TEXT NOT NULL,
    signal_ts     TIMESTAMPTZ NOT NULL,          -- when we detected the crossing
    entry_ask     DOUBLE PRECISION NOT NULL,      -- the ask we would pay as a taker
    entry_mid     DOUBLE PRECISION NOT NULL,      -- fair mid at signal time
    model_pwin    DOUBLE PRECISION NOT NULL,      -- frozen model P(win)
    ev            DOUBLE PRECISION NOT NULL,      -- pwin - entry_ask - fee(ask)
    features      JSONB NOT NULL,                 -- the 14 features, for audit
    model_sha     TEXT NOT NULL,                  -- frozen-model hash (provenance)
    -- settlement, filled forward:
    settled       BOOLEAN NOT NULL DEFAULT FALSE,
    outcome       DOUBLE PRECISION,               -- 0.0 / 1.0
    settle_ts     TIMESTAMPTZ,
    settle_src    TEXT,                           -- 'state_expired' | 'dmr' | 'terminal_px'
    net           DOUBLE PRECISION,               -- outcome - entry_ask - fee(ask)
    -- warm-up: caught mid-life during the initial backfill scan (feed had <1 day of history, so the
    -- >=0.80 crossing predates observation and the feature path is truncated). The CLEAN forward
    -- test uses warmup=FALSE only — markets whose crossing we witnessed live.
    warmup        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (us_slug)                              -- one signal per market (first qualifying cross)
);

CREATE INDEX IF NOT EXISTS idx_cps_unsettled ON collapse_paper_signals (settled) WHERE NOT settled;
CREATE INDEX IF NOT EXISTS idx_cps_niche ON collapse_paper_signals (niche);
CREATE INDEX IF NOT EXISTS idx_cps_event ON collapse_paper_signals (event_key);
