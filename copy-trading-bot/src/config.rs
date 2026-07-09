use confique::Config;

#[derive(Debug, Config)]
pub struct CopyTradingConfig {
    /// Postgres connection string.
    #[config(env = "DATABASE_URL")]
    pub database_url: String,

    // --- Telegram (optional: leave empty to run ntfy-only / headless) ---
    #[config(env = "TELEGRAM_BOT_TOKEN", default = "")]
    pub telegram_bot_token: String,

    #[config(env = "TELEGRAM_CHAT_ID", default = "")]
    pub telegram_chat_id: String,

    // --- ntfy phone push (reuses the brainstem channel) ---
    /// ntfy server base. Default ntfy.sh (matches brainstem's default).
    #[config(env = "NTFY_SERVER", default = "https://ntfy.sh")]
    pub ntfy_server: String,

    /// ntfy topic (your brainstem topic). Empty = ntfy push disabled.
    #[config(env = "NTFY_TOPIC", default = "")]
    pub ntfy_topic: String,

    /// Port for the read-only web scoreboard (surplus + promotion gate).
    #[config(env = "BOARD_PORT", default = 9002)]
    pub board_port: u16,

    // --- Copy trading ---
    /// Enable the LEGACY per-trader copy loop (places a paper bet per followed
    /// trader's new BUY). Off by default — the consensus engine is the product;
    /// with auto-tracking on, this would paper-copy all top-N traders individually.
    #[config(env = "COPY_TRADE_ENABLED", default = false)]
    pub copy_trade_enabled: bool,

    /// Copy trading poll interval in minutes.
    #[config(env = "COPY_TRADE_INTERVAL_MINS", default = 1)]
    pub copy_trade_interval_mins: u64,

    // --- Consensus engine (auto-track top-N + consensus alerts) ---
    /// Master switch for auto-tracking the leaderboard + consensus detection.
    #[config(env = "TRACK_ENABLED", default = true)]
    pub track_enabled: bool,

    /// How many top traders per period to track.
    #[config(env = "TRACK_TOP_N", default = 40)]
    pub track_top_n: usize,

    /// Deep-universe capture depth. `> 50` switches the refresh onto the paginated
    /// leaderboard fetch (offset 0,50,…) so ranks 51..depth are CAPTURED + profiled
    /// as candidates. Defaults to `track_top_n` (40) — today's exact top-40 behavior
    /// — so widening is opt-in. Ranks past `track_consensus_rank_cutoff` are stored
    /// `consensus_eligible = FALSE`: polled + archived, but never voting in consensus
    /// until they clear the belief-blind earned-trust gate.
    #[config(env = "TRACK_DEPTH", default = 40)]
    pub track_depth: usize,

    /// Rank cutoff at/under which a tracked trader is `consensus_eligible` (votes in
    /// consensus). Deep traders (rank > cutoff) are captured but excluded from
    /// backer/opposer counts — depth is a candidate pool, not automatic trust.
    /// Defaults to `track_top_n` (40) = today's exact voter set, so flipping ONLY
    /// TRACK_DEPTH widens CAPTURE without changing a single consensus signal (the
    /// byte-for-byte non-regression contract). Raise it only to deliberately admit
    /// more voters.
    #[config(env = "TRACK_CONSENSUS_RANK_CUTOFF", default = 40)]
    pub track_consensus_rank_cutoff: i32,

    /// Comma-separated inclusive upper rank bounds defining the cohort BANDS the
    /// deep-pool observatory slices/groups by (see `scanner::cohort`). The first
    /// band is the trusted top cohort — keep its bound aligned with
    /// `track_consensus_rank_cutoff` (40). Deeper bands are experimental candidates.
    /// Display/filter only; never affects capture, voting, or alerting.
    #[config(env = "TRACK_COHORT_BANDS", default = "40,100,250,500")]
    pub track_cohort_bands: String,

    /// Comma-separated leaderboard periods to union (DAY,WEEK,MONTH,ALL).
    #[config(env = "TRACK_PERIODS", default = "WEEK,MONTH")]
    pub track_periods: String,

    /// How often to refresh the tracked-trader universe from the leaderboard.
    #[config(env = "TRACK_REFRESH_MINS", default = 60)]
    pub track_refresh_mins: u64,

    /// How many refresh cycles a trader can be absent from the leaderboard
    /// before being deactivated (drop-grace, avoids thrash).
    #[config(env = "TRACK_DROP_GRACE", default = 6)]
    pub track_drop_grace: i64,

    /// How often to run the consensus detection cycle.
    #[config(env = "CONSENSUS_INTERVAL_MINS", default = 2)]
    pub consensus_interval_mins: u64,

    /// Rolling window (hours) of trader activity considered for consensus.
    #[config(env = "CONSENSUS_WINDOW_HOURS", default = 48)]
    pub consensus_window_hours: i64,

    /// Minimum distinct one-sided backers.
    #[config(env = "MIN_BACKERS", default = 3)]
    pub min_backers: usize,

    /// Maximum distinct one-sided opposers tolerated.
    #[config(env = "MAX_OPPOSERS", default = 1)]
    pub max_opposers: usize,

    /// Maximum population std-dev of backer entry prices.
    #[config(env = "MAX_PRICE_STD", default = 0.10)]
    pub max_price_std: f64,

    /// Maximum age (minutes) of the most recent backer fill.
    #[config(env = "MAX_AGE_MINS", default = 2880)]
    pub max_age_mins: i64,

    /// Net-trader count for the STRONG tier.
    #[config(env = "STRONG_NET", default = 4)]
    pub strong_net: i64,

    /// Net-trader count for the ELITE tier.
    #[config(env = "ELITE_NET", default = 6)]
    pub elite_net: i64,

    /// Leaderboard rank at or above which a backer counts as "elite".
    #[config(env = "ELITE_RANK", default = 10)]
    pub elite_rank: i32,

    /// Include sports/esports markets in consensus alerts.
    #[config(env = "CONSENSUS_INCLUDE_SPORTS", default = true)]
    pub consensus_include_sports: bool,

    /// Re-alert the same market only after net grows by at least this many traders.
    #[config(env = "CONSENSUS_REALERT_NET_DELTA", default = 2)]
    pub consensus_realert_net_delta: i64,

    /// Comma-separated strategy names to activate from the portfolio (empty = all).
    /// e.g. "strict,whales,nonsports". See scanner::consensus::default_portfolio.
    #[config(env = "CONSENSUS_STRATEGIES", default = "")]
    pub consensus_strategies: String,

    /// Comma list overriding WHICH strategies push alerts, e.g.
    /// "strict,favorite,elite_fresh_fav". Empty = the portfolio's built-in
    /// alerting flags (today: `strict` only) — byte-identical default.
    #[config(env = "CONSENSUS_ALERT_STRATEGIES", default = "")]
    pub consensus_alert_strategies: String,

    /// Comma list of strategies whose WATCH-tier fires ALSO push. The certified
    /// winners' edge lives at net=3 (WATCH), which the tier gate otherwise
    /// drops. Empty = WATCH never pushes (today's behavior).
    #[config(env = "CONSENSUS_ALERT_WATCH_FOR", default = "")]
    pub consensus_alert_watch_for: String,

    /// Cross-STRATEGY alert dedup window (minutes): skip a push when a
    /// DIFFERENT strategy already alerted the same (market, outcome) within
    /// this window, so overlapping winners produce one push per market. Same-
    /// strategy re-alerts (tier upgrade / net delta) are exempt, preserving
    /// `strict`'s incumbent behavior exactly. 0 disables.
    #[config(env = "CONSENSUS_ALERT_CROSS_DEDUP_MINS", default = 60)]
    pub consensus_alert_cross_dedup_mins: i64,

    /// Dense early-life capture (decay run Phase 0): record a ~45s-spaced mid
    /// and executable best-ask for the first minutes of fresh signals so the
    /// latency-decay analysis can resolve a 1-5 minute action window. OFF by
    /// default — the loop is never spawned; live path byte-identical.
    #[config(env = "DENSE_CAPTURE", default = false)]
    pub dense_capture: bool,

    /// Seconds between dense-capture ticks.
    #[config(env = "DENSE_INTERVAL_SECS", default = 45)]
    pub dense_interval_secs: u64,

    /// A signal is dense-tracked while `first_detected_at` is within this many
    /// minutes (its early life).
    #[config(env = "DENSE_WINDOW_MINS", default = 15)]
    pub dense_window_mins: i64,

    /// Cap on (market, outcome) pairs snapshotted per tick (API budget).
    #[config(env = "DENSE_MAX_SIGNALS", default = 40)]
    pub dense_max_signals: i64,

    /// Strategies whose fresh fires are dense-tracked (the actionable set).
    #[config(env = "DENSE_STRATEGIES", default = "strict,favorite,elite_fresh_fav")]
    pub dense_strategies: String,

    // --- F1 live CLOB price tape (migration 040) ---------------------------
    /// Record the executable book for every tracked-market asset into
    /// `clob_price_tape` (measurement substrate for the latency→edge curve).
    /// OFF by default — the task is never spawned; live path byte-identical.
    #[config(env = "LIVE_TAPE", default = false)]
    pub live_tape: bool,

    /// Max token subscriptions per WS connection. P0-A escalation measured 500
    /// safe (99.6% coverage, 0 disconnects); 200 is the conservative ws.rs constant.
    #[config(env = "LIVE_TAPE_MAX_SUBS", default = 500)]
    pub live_tape_max_subs: usize,

    /// Connection-pool size. 8 × 500 = 4000 tokens headroom (future 1000-user
    /// universe is ~1.6k). If the universe exceeds pool×max_subs, tail tokens are
    /// uncovered and a warning is logged (no silent cap).
    #[config(env = "LIVE_TAPE_MAX_CONNS", default = 8)]
    pub live_tape_max_conns: usize,

    /// Subscribe to conditions a followed trader filled within this many hours.
    #[config(env = "LIVE_TAPE_LOOKBACK_HOURS", default = 6)]
    pub live_tape_lookback_hours: i64,

    /// Seconds between subscription-universe refreshes (picks up new conditions).
    #[config(env = "LIVE_TAPE_REFRESH_SECS", default = 300)]
    pub live_tape_refresh_secs: u64,

    /// Retention for `clob_price_tape` — pruned hourly to bound growth.
    #[config(env = "TAPE_RETENTION_HOURS", default = 72)]
    pub tape_retention_hours: i64,

    /// Tape coalesce window (ms): at most one row per asset per this window, keeping
    /// the SETTLED (last) top-of-book. 1000 = 1 Hz. Smaller = finer, more rows.
    #[config(env = "TAPE_COALESCE_MS", default = 1000)]
    pub tape_coalesce_ms: i64,

    /// How often (hours) to run the tape compaction sweep (drops reconnect-boundary
    /// duplicate top-of-book rows the ingest filter couldn't catch across streams).
    #[config(env = "TAPE_COMPACT_HOURS", default = 6)]
    pub tape_compact_hours: i64,

    // --- F2 optional on-chain fast fills (migration 040, gated on P0-B) -----
    /// Observe OrderFilled logs on-chain for ~1–5s fill→row latency. OFF by
    /// default AND only built if the P0-B ingestion gate passed.
    #[config(env = "LIVE_FILLS", default = false)]
    pub live_fills: bool,

    /// Free Polygon RPC HTTP endpoint for newHeads + eth_getLogs (P0-B selects one).
    #[config(env = "LIVE_FILLS_RPC_HTTP", default = "")]
    pub live_fills_rpc_http: String,

    /// CTF-Exchange contract address(es), comma-separated (P0-verified constants).
    #[config(env = "LIVE_CTF_ADDRS", default = "")]
    pub live_ctf_addrs: String,

    /// OrderFilled event topic0 (P0-verified constant).
    #[config(env = "LIVE_ORDERFILLED_TOPIC0", default = "")]
    pub live_orderfilled_topic0: String,

    /// Run the live-vs-poll dedup pre-check before writing live rows (P0-B sets).
    #[config(env = "LIVE_DEDUP_PRECHECK", default = false)]
    pub live_dedup_precheck: bool,

    /// Feed live BUY fills into consensus (doubly-gated: F2 built AND P3 positive).
    /// The P4 wiring is intentionally NOT shipped until the latency curve returns a
    /// positive verdict (needs multi-day tape accrual); until then this flag is inert.
    #[allow(dead_code)]
    #[config(env = "LIVE_FILLS_TO_CONSENSUS", default = false)]
    pub live_fills_to_consensus: bool,

    /// L1: use incremental vote-window ingestion — poll only the delta since each
    /// trader's cursor and rebuild books from the stored trailing window, instead
    /// of re-polling the full window every cycle. Verified-equivalent to the legacy
    /// path; makes minute-cadence polling cheap. Set false to use the legacy path.
    #[config(env = "CONSENSUS_INCREMENTAL", default = true)]
    pub consensus_incremental: bool,

    /// Max concurrent data-api `/activity` polls in the consensus fan-out. The
    /// poll fan-out is otherwise an unbounded `join_all` burst; this Semaphore
    /// caps it so widening the tracked universe can't spike the data-api into
    /// 429s. Raise only after the 429 rate (Phase 5 board metric) stays ≈ 0.
    #[config(env = "CONSENSUS_MAX_CONCURRENCY", default = 8)]
    pub consensus_max_concurrency: usize,

    /// Build consensus books from the durable `trader_fills` archive instead of
    /// the `consensus_vote_window` table. Default false (byte-identical legacy
    /// path). When true, `quality` is re-derived from each trader's CURRENT rank
    /// at load — this can shift the *ranking* `score` slightly, but live `strict`
    /// alerts are unaffected because tiering keys on `net_count`. Both tables are
    /// dual-written this release for instant rollback.
    #[config(env = "CONSENSUS_BOOKS_FROM_FILLS", default = false)]
    pub consensus_books_from_fills: bool,

    /// Max distinct `trader_fills` conditions to resolve per housekeeping cycle
    /// via the independent unresolved source (bounds the per-cycle CLOB fetch
    /// load; markets that don't fit settle on later cycles).
    #[config(env = "TRADER_FILLS_RESOLVE_PER_CYCLE", default = 200)]
    pub trader_fills_resolve_per_cycle: i64,

    /// Retention (days) for the durable `trader_fills` archive. Default 0 =
    /// keep-all (the archive is the point); set > 0 to prune older fills. The
    /// daily pg_dump backup covers durability regardless.
    #[config(env = "TRADER_FILLS_RETENTION_DAYS", default = 0)]
    pub trader_fills_retention_days: i64,

    // --- Silent cross-check arms (Phase 4). All default OFF: an arm runs only
    //     when its flag is ON *and* its model file loads; emitted rows are silent
    //     (never alert) and judged by the belief-blind gate in the experimental
    //     family. With everything off, the consensus path is byte-identical. ---
    /// Enable the consensus-native logistic arm (`consensus_logit`).
    #[config(env = "CONSENSUS_ARM_LOGIT", default = false)]
    pub consensus_arm_logit: bool,
    /// Enable the consensus-native ensemble arm (`consensus_ens`).
    #[config(env = "CONSENSUS_ARM_ENS", default = false)]
    pub consensus_arm_ens: bool,
    /// Enable the imported market-model arms (`market_ml` / `market_veto`).
    #[config(env = "CONSENSUS_ARM_MARKET", default = false)]
    pub consensus_arm_market: bool,
    /// Enable the Bayesian-anchor arm (`bayes_anchor`).
    #[config(env = "CONSENSUS_ARM_BAYES", default = false)]
    pub consensus_arm_bayes: bool,
    /// Enable the price-free residual arm (`market_resid`). Default OFF: silent,
    /// judged in the experimental family; live `strict` stays byte-identical.
    #[config(env = "CONSENSUS_ARM_RESID", default = false)]
    pub consensus_arm_resid: bool,

    /// Enable the earned-trust consensus arms (`trust_weighted`, `trusted_only`,
    /// `cross_cohort`). Default OFF: when off they aren't registered (portfolio
    /// byte-identical) and the trust-map refresh task is skipped. They're silent +
    /// judged in the experimental family; live `strict` is non-regressive
    /// (tiering = net_count).
    #[config(env = "CONSENSUS_TRUST_ARMS", default = false)]
    pub consensus_trust_arms: bool,

    /// Wide-consensus arms (FABLE wide-pool run, paper-only). When on, each Nth
    /// consensus cycle (`CONSENSUS_WIDE_EVERY`) additionally loads the WIDE vote
    /// window (eligible ∪ tracked deep non-bot wallets — the sensor-array widening;
    /// `load_wide_window_votes`), rebuilds books from it, and scores the silent
    /// EXPERIMENTAL `favorite_wide` / `favorite_wide_anchored` / `_blind_wide` arms
    /// on those books only. The eligible-book portfolio, its books, and its atoms
    /// are untouched — champion path byte-identical. Default OFF ⇒ no extra query,
    /// no arms, nothing emitted.
    #[config(env = "CONSENSUS_WIDE_ARMS", default = false)]
    pub consensus_wide_arms: bool,

    /// Cycle stride for the wide-consensus scoring pass: score wide arms on every
    /// Nth consensus cycle (1 = every cycle; 0 is clamped to 1). The wide window
    /// is a full trailing-window read (~2-3x the eligible book's rows), so at
    /// minute cadence a stride of 5 keeps the extra DB load negligible while
    /// costing ~nothing in freshness (max_age is hours; entries are decision-
    /// time-captured on first detection).
    #[config(env = "CONSENSUS_WIDE_EVERY", default = 5)]
    pub consensus_wide_every: u64,

    /// Pooled per-cell specialist weighting (FORGE_PLAN Item 3). When on, registers
    /// the silent EXPERIMENTAL `slice_sport_tail` arm (WeightMode::CellPooled) and
    /// populates per-sport cell verdicts so each vote is weighted by the trader's
    /// edge in THIS market's sport, partial-pooled toward their overall multiplier.
    /// Default OFF ⇒ no arm registered, cells empty, every book byte-identical.
    #[config(env = "SLICE_POOLED", default = false)]
    pub slice_pooled: bool,

    /// Proven-trader router arm (PREREG_2026-07-04T094304Z, paper-only). When on:
    /// (a) the follow-set re-scorer runs on the trust-refresh cadence, appending
    /// each batch to `router_followset` (migration 039); (b) the silent
    /// EXPERIMENTAL `proven_router` arm is registered, firing on a scorecard-
    /// proven wallet's fresh BUY in the 0.45–0.90 favorite band. Fail-closed:
    /// until the first re-score publishes (or when it publishes ∅) the arm counts
    /// nothing. Default OFF ⇒ no arm, no re-scorer, portfolio byte-identical.
    #[config(env = "PROVEN_ROUTER", default = false)]
    pub proven_router: bool,

    /// Survivorship capture fix (2026-07-04 capture-hardening, paper-only). When
    /// on, a bounded slow loop keeps polling the fills of DEACTIVATED wallets the
    /// scorecard still cares about (dropped off the leaderboard but scorecard-
    /// eligible: ever in `router_followset`, or ≥100 band 0.45–0.90 BUY fills in
    /// trailing 365d). Without it, capture STOPS at deactivation (router_verify A4:
    /// 245 inactive wallets, 0 fills after last_seen_on_lb) ⇒ every forward
    /// scorecard/benchmark read is conditioned on staying tracked = biased UP. Only
    /// the durable `trader_fills` archive is written (NOT consensus window votes),
    /// so the live consensus book is byte-identical whether the flag is on or off.
    /// Default OFF ⇒ the task isn't spawned ⇒ byte-identical.
    #[config(env = "CAPTURE_DROPPED", default = false)]
    pub capture_dropped: bool,

    /// Hot-lane fast poll for the router follow-set (2026-07-04 capture-hardening,
    /// paper-only). When on (AND `PROVEN_ROUTER` on, so a follow-set exists), a
    /// task polls ONLY the current follow-set wallets every `HOT_POLL_SECS`,
    /// ingests through the SAME window-vote + fills path (dedup), then runs a
    /// SCOPED scoring pass for the affected markets only — building each book with
    /// `books_from_window_votes` and scoring ONLY the `proven_router` arm. This
    /// collapses fill→signal latency from ~1.5–3 min to ≲30s for the front-loaded
    /// router edge. It never touches the main cycle cadence and never polls the
    /// whole universe faster (the API 429 budget). Default OFF ⇒ no task ⇒
    /// byte-identical.
    #[config(env = "HOT_LANE", default = false)]
    pub hot_lane: bool,

    /// Hot-lane poll interval (seconds) for the follow-set. Only read when
    /// `HOT_LANE` is on. Floored at 5s in code to protect the 429 budget.
    #[config(env = "HOT_POLL_SECS", default = 12)]
    pub hot_poll_secs: u64,

    /// Re-tuned `strict` thresholds variant, `"min_backers,strong_net,elite_net"`
    /// (e.g. "4,5,8"). Deep-pool edge run, Phase 2: a WIDER eligible voter set
    /// inflates net_count, so selectivity must be re-chosen — as a SILENT
    /// forward-tracked arm (`strict_retuned`), never by moving `strict` itself.
    /// Empty (default) or unparseable ⇒ the arm isn't registered; portfolio
    /// byte-identical to today.
    #[config(env = "CONSENSUS_RETUNED", default = "")]
    pub consensus_retuned: String,

    /// How often (minutes) to refresh the cached earned-trust map. Trust inputs
    /// change ~daily as markets resolve, so this is slow — NOT per 1-min cycle.
    #[config(env = "TRUST_REFRESH_MINS", default = 60)]
    pub trust_refresh_mins: u64,

    /// EARN deep sharps into consensus (deep-pool edge run, Phase 0). Default OFF:
    /// the promotion pass only REPORTS (board: "⤴ promotable" + shadow impact) and
    /// no eligibility changes. When ON, the slow trust-refresh task durably flips
    /// `followed_traders.earned_eligible = TRUE` for deep (rank > cutoff) traders
    /// whose belief-blind `trust_verdict` is Trusted — the ONLY path by which a
    /// deep trader starts voting. Flipping the flag back off stops NEW promotions
    /// but does not revoke recorded ones (revocation is a deliberate manual act).
    #[config(env = "EARN_DEEP_SHARPS", default = false)]
    pub earn_deep_sharps: bool,

    /// Path to the consensus logistic model JSON (consensus_train.py output).
    #[config(env = "CONSENSUS_WIN_MODEL_PATH", default = "model/consensus_win.json")]
    pub consensus_win_model_path: String,
    /// Path to the consensus ensemble model JSON (XGBoost export).
    #[config(env = "CONSENSUS_ENS_MODEL_PATH", default = "model/consensus_ens.json")]
    pub consensus_ens_model_path: String,
    /// Path to the imported market-outcome XGBoost model JSON.
    #[config(env = "MARKET_MODEL_PATH", default = "model/xgb_model.json")]
    pub market_model_path: String,
    /// Training-data resolution cutoff for the imported market model (RFC3339);
    /// empty = no forward-only guard (rely on live forwardness).
    #[config(env = "MARKET_ML_TRAINED_THROUGH", default = "")]
    pub market_ml_trained_through: String,
    /// Path to the price-free residual model JSON (train_market_resid.py output).
    /// Its `.resid.json`, `.scaler.json`, and `.meta.json` siblings load alongside.
    #[config(env = "MARKET_RESID_MODEL_PATH", default = "model/market_resid.json")]
    pub market_resid_model_path: String,
    /// Forward cutoff override for `market_resid` (RFC3339); empty ⇒ use the
    /// model's `.meta.json` `trained_through`, else rely on live forwardness.
    #[config(env = "MARKET_RESID_TRAINED_THROUGH", default = "")]
    pub market_resid_trained_through: String,

    /// Log the forward 29-feature vector for every strict-fired market into
    /// `market_feature_log` (the survivorship-free training source for the
    /// `market_resid` arm). Default OFF: when off, no per-market data is fetched
    /// for it and the cycle path is byte-identical.
    #[config(env = "MARKET_FEATURE_LOG", default = false)]
    pub market_feature_log: bool,

    /// Max distinct strict markets `prefetch_markets` fetches per cycle. The
    /// prefetch is sequential + throttled (150ms each), so as the strict-market
    /// count grows it could otherwise blow past the cadence; this caps it (excess
    /// markets are logged + fetched on later cycles). Only matters when a
    /// market-dependent arm or the feature log is enabled.
    #[config(env = "MARKET_PREFETCH_MAX", default = 200)]
    pub market_prefetch_max: usize,

    /// Edge margin the legacy ML arms must clear (`p_win − price > margin`).
    #[config(env = "CONSENSUS_ML_MARGIN", default = 0.0)]
    pub consensus_ml_margin: f64,
    /// Edge margin the Bayesian-anchor arm must clear (`posterior − mid > margin`).
    #[config(env = "CONSENSUS_BAYES_MARGIN", default = 0.0)]
    pub consensus_bayes_margin: f64,
    /// Dedicated edge margin for the `market_resid` arm: `p_cons − band_rate >
    /// margin`. Its unit is a residual over the band's BLIND base rate — distinct
    /// from `CONSENSUS_ML_MARGIN`'s surplus-over-mid — so it gets its own knob
    /// (set it to the model's suggested calRMSE cushion from its `.meta.json`).
    #[config(env = "MARKET_RESID_MARGIN", default = 0.0)]
    pub market_resid_margin: f64,

    // --- Betting ---
    /// Slippage assumption as a fraction (0.01 = 1%).
    #[config(env = "SLIPPAGE_PCT", default = 0.01)]
    pub slippage_pct: f64,

    /// Fee assumption as a fraction (0.02 = 2%).
    #[config(env = "FEE_PCT", default = 0.02)]
    pub fee_pct: f64,

    // --- Honest P&L tracker (read-only; CLV-based, execution-haircut, multi-regime) ---
    // These knobs never touch selection/alerting/betting: they only parameterize the
    // read-only `honest_pnl_by_strategy` instrument + the conservative pilot verdict.
    /// Buy-side execution haircut in PRICE units (0.01 = 1¢) added to the captured
    /// mid to get the executable entry price when no real book-ask was captured.
    /// The honest realizable edge is measured net of this.
    #[config(env = "EXEC_HAIRCUT", default = 0.01)]
    pub exec_haircut: f64,

    /// Flat paper stake ($) per bet — the capacity ceiling and ledger default.
    #[config(env = "FLAT_STAKE", default = 100.0)]
    pub flat_stake: f64,

    /// Fraction of a market's liquidity proxy (median sharp $) usable as a stake
    /// before the edge erodes: `suggested_stake = min(FLAT_STAKE, frac × median $)`.
    #[config(env = "CAPACITY_FRAC", default = 0.05)]
    pub capacity_frac: f64,

    /// Minimum corrected honest-ROI lower bound a strategy must clear to be
    /// pilot-ready (execution-aware GO threshold). A false GO risks real money.
    #[config(env = "MIN_PILOT_ROI", default = 0.02)]
    pub min_pilot_roi: f64,

    /// Distinct-EVENT floor before a pilot verdict is even considered.
    #[config(env = "PILOT_MIN_EVENTS", default = 50)]
    pub pilot_min_events: i64,

    /// Minimum number of distinct positive day-regimes required for a GO.
    #[config(env = "PILOT_MIN_REGIMES", default = 5)]
    pub pilot_min_regimes: i64,

    /// Fraction of day-regimes that must be positive for a GO (with the floor above).
    #[config(env = "REGIME_FRAC", default = 0.7)]
    pub regime_frac: f64,

    /// Market-liquidity floor (median sharp $) required to place a stake for a GO.
    #[config(env = "MIN_LIQUIDITY_USD", default = 2000.0)]
    pub min_liquidity_usd: f64,

    /// Capture the REAL executable best ask (CLOB `/book`) once per open tracked
    /// signal, so the honest edge uses the market ask instead of the mid+haircut
    /// heuristic. Default OFF: an extra bounded book fetch per newly-open signal;
    /// with it off the honest query falls back to the heuristic (byte-identical).
    #[config(env = "CAPTURE_ENTRY_ASK", default = false)]
    pub capture_entry_ask: bool,

    /// Max LAGGED book-ask captures per housekeeping cycle (bounds the extra
    /// `/book` fetch load for the already-open backlog; uncaptured signals settle
    /// on later cycles).
    #[config(env = "ENTRY_ASK_MAX_PER_CYCLE", default = 40)]
    pub entry_ask_max_per_cycle: usize,

    /// Max DECISION-TIME book-ask captures per housekeeping cycle — signals whose
    /// decision-time mid was first set THIS pass. A separate budget so a lagged
    /// backlog can never starve the decision-time captures (the ones the headline
    /// realized ROI rests on). New signals/cycle is small, so this rarely binds.
    #[config(env = "ENTRY_ASK_DECISION_MAX_PER_CYCLE", default = 40)]
    pub entry_ask_decision_max_per_cycle: usize,

    /// Max seconds between first detection and ask capture for a capture to count
    /// toward the REALIZED (vs blended) honest ROI (`entry_ask_at − first_detected_at
    /// ≤ this`). A housekeeping pass over the whole open backlog is ~10-15 min (120ms/
    /// condition), so 900s (15 min) admits roughly the first pass and excludes hours-
    /// late backlog captures. This wall-clock cutoff is a proxy for the code's
    /// `first_price` provenance and can diverge from it near the edge (audit #2 —
    /// keying the realized cohort off provenance is the cleaner fix, deferred). Tune
    /// from the `consensus_entry_ask_capture_lag_seconds` histogram (e.g. p95 of
    /// first-price captures) rather than assuming.
    #[config(env = "REALIZED_DECISION_LAG_SECS", default = 900.0)]
    pub realized_decision_lag_secs: f64,

    /// Comma-separated strategies the PAPER equity ledger tracks. Empty = every
    /// non-`_blind` strategy (the whole tracked family). Appends one paper bet at
    /// each resolution; PAPER only, this system NEVER places real money.
    #[config(env = "LEDGER_STRATEGIES", default = "")]
    pub ledger_strategies: String,

    /// Opt-in minimal-noise honest-tracker phone digest. Default OFF: when off, no
    /// digest is computed or pushed (silent). When on, it pushes to ntfy ONLY on a
    /// material change — a strategy crossing INTO/OUT of pilot-ready, or a paper
    /// drawdown newly breaching the floor — never a heartbeat.
    #[config(env = "HONEST_DIGEST", default = false)]
    pub honest_digest: bool,

    /// Paper-drawdown floor ($) whose first breach triggers a digest push.
    #[config(env = "HONEST_MAX_DRAWDOWN_USD", default = 500.0)]
    pub honest_max_drawdown_usd: f64,

    /// Port for the Prometheus metrics HTTP endpoint.
    #[config(env = "METRICS_PORT", default = 9001)]
    pub metrics_port: u16,
}

impl CopyTradingConfig {
    pub fn load() -> Result<Self, confique::Error> {
        Self::builder().env().load()
    }
}
