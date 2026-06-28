use confique::Config;

#[derive(Debug, Config)]
pub struct CopyTradingConfig {
    /// Postgres connection string.
    #[config(env = "DATABASE_URL")]
    pub database_url: String,

    // --- Telegram ---
    #[config(env = "TELEGRAM_BOT_TOKEN")]
    pub telegram_bot_token: String,

    #[config(env = "TELEGRAM_CHAT_ID")]
    pub telegram_chat_id: String,

    // --- Copy trading ---
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
