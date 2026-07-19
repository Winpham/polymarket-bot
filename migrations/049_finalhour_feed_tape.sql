-- FINAL-HOUR FEED TAPE — the paired (game-state x book) series. READ-ONLY capture. Never trades.
--
-- WHY THIS EXISTS, AND WHY IT RECORDS EVERYTHING
-- ----------------------------------------------
-- The final-hour edge is MATURITY-ANCHORED: it was located retrospectively by a timestamp that is
-- only knowable after the fact, and every live-knowable PRICE anchor is negative. So the entire
-- thesis rests on one untested proposition -- that a live game-state feed locates the same window
-- that hindsight locates. Nothing in any archive can answer that, because ESPN's scoreboard is a
-- SNAPSHOT api: it reports the state right now and never again. Tennis has no commentary/plays
-- resource, so within-match timing cannot be reconstructed after the fact at any price.
--
-- The joint (game-state x book) series is therefore PERISHABLE. It exists only while something is
-- polling. Every hour nothing polls is an hour that can never be recovered.
--
-- THREE reasons this records every in-progress match rather than only the ones that fire:
--
--   1. LATENCY -- the number the thesis actually turns on. lambda is 0.44 (LB 0.22) at -30min but
--      0.10 (LB 0.00) at -45min, so the edge is gone ~15 minutes early. If the US book re-rates
--      BEFORE ESPN publishes the score change, we are late by construction and there is no trade.
--      That is only measurable by holding both series side by side and asking which moved first.
--      No amount of analysis on either source alone can produce it.
--
--   2. THE PLACEBO, FOR FREE. Non-near-decided matches in the same band, carried through the
--      identical cost path, are the control arm. Any misspecification of fee, spread, slippage or
--      fill hits both arms equally, so the DIFFERENCE survives a wrong cost model. Two of this
--      project's four retractions reversed sign the moment a control was finally added; the
--      cheapest possible insurance against repeating that is to record the control from day one.
--
--   3. TRIGGER RE-SPECIFICATION WITHOUT RESETTING THE CLOCK. If only fires are logged, every future
--      refinement of the trigger costs a new PREREG and restarts the count from zero. The trigger
--      has ALREADY had to change once (v1's "serving for the match" is unobservable -- ESPN exposes
--      no server/possession or point-level field). Logging raw state lets the frozen trigger be
--      evaluated live for the gate while alternatives are assessed as clearly-labelled exploratory
--      analysis, without contaminating it.
--
-- APPEND-ONLY. No order path. No API key. Writing here can never place a trade.

CREATE TABLE IF NOT EXISTS finalhour_feed_tape (
    id              BIGSERIAL PRIMARY KEY,
    poll_ts         TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when WE observed it
    fetch_ms        DOUBLE PRECISION,                    -- how long the ESPN fetch took

    -- ESPN side
    feed_src        TEXT NOT NULL,                       -- 'espn_atp' | 'espn_wta'
    espn_comp_id    TEXT NOT NULL,                       -- competition (match) id
    tournament      TEXT,
    is_bo5          BOOLEAN NOT NULL DEFAULT FALSE,
    player_a        TEXT NOT NULL,
    player_b        TEXT NOT NULL,
    linescore_a     TEXT NOT NULL,                       -- JSON array of per-set games
    linescore_b     TEXT NOT NULL,
    period          INTEGER,
    near_decided    BOOLEAN NOT NULL,                    -- the FROZEN trigger's verdict
    leader_name     TEXT,
    feed_state      TEXT,                                -- e.g. 'sets 1-0, cur +3'

    -- mapping to the US venue (NULL when unmapped -- itself a measurement)
    us_slug         TEXT,
    yes_player      TEXT,                                -- outcomes[i] where side_long[i]
    leader_is_yes   BOOLEAN,                             -- orientation: is the leader the YES side?

    -- book side, as of the most recent quote at poll time
    best_bid        DOUBLE PRECISION,
    best_ask        DOUBLE PRECISION,
    mid             DOUBLE PRECISION,
    spread          DOUBLE PRECISION,
    best_ask_qty    DOUBLE PRECISION,                    -- depth AT the touch (shares)
    ask_qty_1c      DOUBLE PRECISION,                    -- depth within 1c -- walk-the-book input
    quote_recv_at   TIMESTAMPTZ,
    quote_age_s     DOUBLE PRECISION,                    -- poll_ts - quote_recv_at: book staleness

    -- what the FROZEN trigger would have done, without doing it
    would_fire      BOOLEAN NOT NULL DEFAULT FALSE,      -- near_decided AND in-band AND orientation OK
    fire_block      TEXT                                 -- why not: 'not_near'|'no_slug'|'no_quote'
                                                         --   |'band'|'orientation'|'stale_quote'
);

CREATE INDEX IF NOT EXISTS fht_poll     ON finalhour_feed_tape (poll_ts DESC);
CREATE INDEX IF NOT EXISTS fht_comp     ON finalhour_feed_tape (espn_comp_id, poll_ts);
CREATE INDEX IF NOT EXISTS fht_slug     ON finalhour_feed_tape (us_slug, poll_ts);
CREATE INDEX IF NOT EXISTS fht_fire     ON finalhour_feed_tape (would_fire) WHERE would_fire;
