//! Market-side discovery: find the traders the leaderboard structurally cannot show us.
//!
//! # Why this lane exists
//!
//! Every wallet the bot has ever known came from the Polymarket leaderboard, which ranks by
//! ABSOLUTE PnL. That is a bankroll-and-volume sort, not a skill sort: a trader making $200
//! on $200k of volume (0.1% ROI) outranks one making $200 on $2k (10% ROI) — and the second
//! is the one worth copying. Measured on our own pool (2026-07-13):
//!
//!   corr(rank, ROI)    = -0.05   <- rank says essentially NOTHING about efficiency
//!   corr(rank, volume) dominates; mean volume falls $11.2M (top-40) -> $321k (rank 501-1000)
//!
//! So an efficient low-volume specialist may not appear on the leaderboard at ANY depth, and
//! widening the rank cutoff cannot reach them. The evidence is blunt: of the **4,341 wallets
//! that traded recent weather markets, our depth-1000 leaderboard pool contained 50 (1.2%)**.
//! Going deeper on a volume sort is brute force that still misses 98.8% of the population.
//!
//! # The inversion
//!
//! Enumerate from the MARKET side instead. `/trades?market=<condition_id>` returns every
//! participant in a market we care about, and their fills in exactly that market — which is
//! precisely the evidence the skill test needs. It costs **O(markets), not O(wallets)**: one
//! sweep of the ~450 daily weather+esports markets reaches the whole population, whereas
//! polling those 4 000+ wallets individually would need ~167 req/s — four times the measured
//! API ceiling. Wide discovery is CHEAPER than the narrow one, not more expensive.
//!
//! Markets are enumerated from the fills we ALREADY have: our ranked whales act as scouts
//! that reveal WHICH markets exist, and the harvest then recovers everyone else trading in
//! them. That is the part the leaderboard was hiding.
//!
//! # What this lane deliberately does NOT do
//!
//! Discovery is not trust. A harvested wallet is written `active = FALSE, consensus_eligible
//! = FALSE`: it is never polled wallet-side (that is the 167 req/s trap) and it never backs a
//! signal by merely existing. It is profiled from its market-side fills and must EARN its way
//! in through the copyability gate — surplus over the cell-blind favorite, net of the follower
//! tax, at OUR price, on independent clusters, under BH-FDR. Widening the net is exactly why
//! the filter has to stay strict.

use std::sync::Arc;

use anyhow::Result;
use chrono::{Duration, Utc};
use futures_util::future::join_all;
use tokio::sync::Semaphore;

use crate::config::CopyTradingConfig;
use crate::cycles::consensus_cycle::trade_to_fill;
use crate::scanner::copy_trader::CopyTraderMonitor;
use crate::storage::postgres::PgPortfolio;

/// One harvest sweep: enumerate the family markets seen recently, harvest every trade in
/// each, persist the fills, and register the wallets we had never heard of.
/// Returns `(markets_swept, fills_inserted, new_wallets)`.
pub async fn harvest_tick(
    portfolio: &PgPortfolio,
    monitor: &CopyTraderMonitor,
    cfg: &CopyTradingConfig,
) -> Result<(usize, u64, u64)> {
    let since = Utc::now() - Duration::hours(cfg.market_harvest_lookback_hours);
    let markets = portfolio
        .recent_family_markets(&cfg.market_harvest_slug_regex, since, cfg.market_harvest_max_markets)
        .await?;
    if markets.is_empty() {
        tracing::debug!("Market harvest: no family markets in the lookback window");
        return Ok((0, 0, 0));
    }

    // Bounded fan-out, same discipline (and the same measured ceiling) as the consensus poll.
    let sem = Arc::new(Semaphore::new(cfg.consensus_max_concurrency.max(1)));
    let sweeps = markets.iter().map(|cid| {
        let sem = Arc::clone(&sem);
        async move {
            let _permit = sem.acquire_owned().await;
            (cid.clone(), monitor.harvest_market_trades(cid).await)
        }
    });
    let results = join_all(sweeps).await;

    let mut fills = Vec::new();
    let mut wallets: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut failed = 0usize;
    for (cid, res) in results {
        match res {
            Ok(trades) => {
                for h in trades {
                    if let Some(f) = trade_to_fill(&h.wallet, &h.trade) {
                        fills.push(f);
                    }
                    wallets.insert(h.wallet);
                }
            }
            Err(e) => {
                failed += 1;
                tracing::debug!(condition_id = %cid, err = %e, "Market harvest sweep failed");
            }
        }
    }

    // Same path as every other fill: dedup is the DB's job (ON CONFLICT), so a trade we
    // already captured wallet-side simply collapses onto itself.
    let fills_inserted = portfolio.insert_trader_fills(&fills).await.unwrap_or(0);
    let new_wallets = portfolio
        .upsert_harvested_wallets(&wallets.iter().cloned().collect::<Vec<_>>())
        .await
        .unwrap_or(0);

    tracing::info!(
        markets = markets.len(),
        failed,
        trades = fills.len(),
        fills_inserted,
        wallets_seen = wallets.len(),
        new_wallets,
        "Market harvest sweep"
    );
    crate::metrics::record_market_harvest(markets.len() as u64, new_wallets, wallets.len() as u64);
    Ok((markets.len(), fills_inserted, new_wallets))
}
