//! Survivorship capture fix (2026-07-04 capture-hardening, paper-only).
//!
//! Fill capture normally STOPS when a wallet drops off the leaderboard: the
//! consensus poll iterates `get_active_traders()` (active = TRUE), so a
//! deactivated wallet's new fills are never fetched. But the trader scorecard and
//! the best-trader benchmark read the durable `trader_fills` archive over a
//! trailing window — so every forward number is conditioned on the wallet staying
//! tracked, biased UP by an unknown amount (router_verify A4: 245 inactive
//! wallets, 0 fills after `last_seen_on_lb`).
//!
//! This tick keeps polling the fills of DEACTIVATED wallets the scorecard still
//! cares about (`scorecard_eligible_dropped_wallets`: ever in `router_followset`,
//! or ≥100 band 0.45–0.90 BUY fills in the trailing 365d). It writes ONLY the
//! durable archive (`insert_trader_fills`) — never consensus window votes — so a
//! dropped wallet cannot re-enter the live consensus book. Bounded: a slow loop
//! on the trust-refresh cadence, the poll fan-out capped by the SAME semaphore
//! (`consensus_max_concurrency`) the consensus poll uses so it can't burst the
//! data-api into 429s. Flag-gated (`CAPTURE_DROPPED`, default OFF): the loop is
//! never spawned when off, so the live path is byte-identical.

use std::sync::Arc;

use chrono::{DateTime, Utc};
use futures_util::future::join_all;
use tokio::sync::Semaphore;

use crate::config::CopyTradingConfig;
use crate::scanner::copy_trader::CopyTraderMonitor;
use crate::storage::postgres::PgPortfolio;

use super::consensus_cycle::trade_to_fill;

/// One capture-dropped pass: poll the deactivated-but-scorecard-eligible wallets
/// and archive any NEW fills. Returns the number of fill atoms inserted.
pub async fn capture_dropped_tick(
    portfolio: &PgPortfolio,
    monitor: &CopyTraderMonitor,
    cfg: &CopyTradingConfig,
) -> anyhow::Result<u64> {
    let wallets = portfolio.scorecard_eligible_dropped_wallets().await?;
    if wallets.is_empty() {
        return Ok(0);
    }

    // Bounded fan-out: the SAME semaphore bound the consensus poll uses, so this
    // background lane can never widen the concurrent data-api pressure beyond the
    // tuned 429 budget.
    let sem = Arc::new(Semaphore::new(cfg.consensus_max_concurrency.max(1)));
    let polls = wallets.iter().map(|(wallet, since)| {
        let wallet = wallet.clone();
        let since = *since;
        let sem = Arc::clone(&sem);
        async move {
            let _permit = sem.acquire_owned().await;
            let poll = monitor.poll_trader_activity(&wallet, since).await;
            (wallet, poll)
        }
    });
    let results: Vec<(String, _)> = join_all(polls).await;

    let now = Utc::now();
    let mut fills = Vec::new();
    let mut polled_ok: Vec<String> = Vec::new();
    for (wallet, poll) in results {
        let trades = match poll {
            Ok(r) => {
                polled_ok.push(wallet.clone());
                r.trades
            }
            // A failed poll (incl. 429) leaves the cursor where it is so the gap
            // is re-fetched next pass — never advance on failure.
            Err(e) => {
                tracing::debug!(wallet = %wallet, err = %e, "capture-dropped poll failed");
                continue;
            }
        };
        let wallet_lc = wallet.to_lowercase();
        for tr in &trades {
            if let Some(f) = trade_to_fill(&wallet_lc, tr) {
                fills.push(f);
            }
        }
    }

    // Durable archive only — dedup is the DB's job (`insert_trader_fills` ON
    // CONFLICT). NO window votes: a deactivated wallet must not vote in consensus.
    let inserted = portfolio.insert_trader_fills(&fills).await.unwrap_or_else(|e| {
        tracing::warn!(err = %e, "capture-dropped insert_trader_fills failed");
        0
    });

    // Advance the poll cursor for wallets that polled OK, so the next pass fetches
    // only the new tail (self-healing: a failed poll left its cursor untouched).
    if !polled_ok.is_empty() {
        let _: Result<(), _> = advance_cursor(portfolio, &polled_ok, now).await;
    }

    if inserted > 0 {
        tracing::info!(
            dropped_wallets = wallets.len(),
            polled_ok = polled_ok.len(),
            fills = fills.len(),
            inserted,
            "capture-dropped tick"
        );
    }
    Ok(inserted)
}

/// Stamp the consensus cursor for the polled dropped wallets (reuses the shared
/// per-wallet cursor column; `set_consensus_cursors` updates by wallet with no
/// `active` predicate, so it is correct for deactivated wallets too).
async fn advance_cursor(
    portfolio: &PgPortfolio,
    wallets: &[String],
    at: DateTime<Utc>,
) -> anyhow::Result<()> {
    if let Err(e) = portfolio.set_consensus_cursors(wallets, at).await {
        tracing::debug!(err = %e, "capture-dropped cursor advance failed");
    }
    Ok(())
}
