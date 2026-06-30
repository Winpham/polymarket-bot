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

    /// Edge margin the ML arms must clear (`p_win − price > margin`).
    #[config(env = "CONSENSUS_ML_MARGIN", default = 0.0)]
    pub consensus_ml_margin: f64,
    /// Edge margin the Bayesian-anchor arm must clear (`posterior − mid > margin`).
    #[config(env = "CONSENSUS_BAYES_MARGIN", default = 0.0)]
    pub consensus_bayes_margin: f64,

    // --- Betting ---
    /// Slippage assumption as a fraction (0.01 = 1%).
    #[config(env = "SLIPPAGE_PCT", default = 0.01)]
    pub slippage_pct: f64,

    /// Fee assumption as a fraction (0.02 = 2%).
    #[config(env = "FEE_PCT", default = 0.02)]
    pub fee_pct: f64,

    /// Port for the Prometheus metrics HTTP endpoint.
    #[config(env = "METRICS_PORT", default = 9001)]
    pub metrics_port: u16,
}

impl CopyTradingConfig {
    pub fn load() -> Result<Self, confique::Error> {
        Self::builder().env().load()
    }
}
