#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

// Thin re-exports of polymarket-common modules so that local code can use
// `crate::data`, `crate::storage`, etc. unchanged.
pub use polymarket_common::data;
pub use polymarket_common::format;
pub use polymarket_common::metrics;
pub use polymarket_common::model;
pub use polymarket_common::pricing;
pub use polymarket_common::signal;
pub use polymarket_common::storage;
// telegram is local so that the commands sub-module is accessible via crate::telegram
mod telegram;

mod board;
mod config;
mod cycles;
mod live;
// WS-D: unarmed pilot harness (default-OFF, places nothing, NOT wired into `live`). See pilot.rs.
mod pilot;
mod scanner;

use anyhow::Result;
use config::CopyTradingConfig;
use std::sync::Arc;

#[tokio::main]
async fn main() -> Result<()> {
    rustls::crypto::ring::default_provider()
        .install_default()
        .expect("failed to install rustls CryptoProvider");

    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("copy_trading_bot=info".parse()?),
        )
        .with_ansi(true)
        .with_target(true)
        .init();

    dotenvy::dotenv().ok();

    let cfg = CopyTradingConfig::load()?;

    // Separate one-shot modes, selected by arg. The container's default no-arg
    // invocation runs the live loop unchanged (deploy-safe). `backfill [0xWALLET]`
    // — an optional wallet arg restricts to a single wallet (verify mode).
    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|a| a == "backfill") {
        use crate::storage::postgres::PgPortfolio;
        // `backfill [dry] [0xWALLET]` — `dry` fetches + maps + logs but writes nothing
        // and runs no migrations; a `0x…` arg restricts to a single wallet.
        let dry = args.iter().any(|a| a == "dry");
        let only = args.iter().find(|a| a.starts_with("0x")).cloned();
        let pool = sqlx::PgPool::connect(&cfg.database_url).await?;
        let portfolio = PgPortfolio::new(pool).await?;
        if !dry {
            portfolio.run_migrations().await?;
        }
        let monitor = crate::scanner::copy_trader::CopyTraderMonitor::new(
            reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(15))
                .build()?,
        );
        return cycles::backfill::run(&portfolio, &monitor, only.as_deref(), dry).await;
    }

    live::run_live(Arc::new(cfg)).await
}
