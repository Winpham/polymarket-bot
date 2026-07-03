//! One-time (re-runnable) full-history backfill + trader-type classification.
//!
//! Runs as a SEPARATE mode (`copy-trading-bot backfill`), never wired into the live
//! loop — the container's default no-arg invocation is unchanged. For every tracked
//! wallet it pages the trader's COMPLETE reachable history from the data-api
//! (`fetch_full_history`: correct `offset`/`limit=500` params — NOT the ignored
//! `startTs`) and persists via the SAME `trade_to_fill` → `insert_trader_fills`
//! pipeline the live poller uses, so backfilled rows are byte-identical (same frozen
//! `sport`/`bet_type`/`is_sports`) and de-duplicated by the existing `ON CONFLICT`.
//! Idempotent: re-running only fills genuinely-new rows.
//!
//! Then classifies each wallet as `bot` (high-frequency market-maker: thousands of
//! trades crammed into few days) vs `human`, so the specialist/selection layer can
//! profile people who *pick*, not liquidity bots (the winner's-curse work showed the
//! trade-count leaderboard is dominated by MM bots we don't want to tail).

use anyhow::Result;

use crate::cycles::consensus_cycle::trade_to_fill;
use crate::scanner::copy_trader::CopyTraderMonitor;
use crate::storage::postgres::PgPortfolio;

/// Backfill every active tracked wallet's full history, then classify trader types.
/// `only` restricts to a single wallet (test/verify mode) and skips classification
/// (which needs the whole fleet's fills).
pub async fn run(
    portfolio: &PgPortfolio,
    monitor: &CopyTraderMonitor,
    only: Option<&str>,
    dry_run: bool,
) -> Result<()> {
    let mut traders = portfolio.get_active_traders().await?;
    if let Some(w) = only {
        traders.retain(|t| t.proxy_wallet.eq_ignore_ascii_case(w));
        tracing::info!(wallet = %w, matched = traders.len(), "Backfill: single-wallet test mode");
    }
    tracing::info!(
        n = traders.len(),
        dry_run,
        "Backfill: full-history sync starting"
    );

    let mut total_fetched = 0usize;
    let mut total_inserted = 0u64;
    for (i, t) in traders.iter().enumerate() {
        let wallet_lc = t.proxy_wallet.to_lowercase();
        match monitor.fetch_full_history(&t.proxy_wallet).await {
            Ok(trades) => {
                let fills: Vec<_> = trades
                    .iter()
                    .filter_map(|tr| trade_to_fill(&wallet_lc, tr))
                    .collect();
                let fetched = trades.len();
                total_fetched += fetched;
                if dry_run {
                    // Verify mapping WITHOUT writing: log a few mapped fills so the
                    // frozen sport/bet_type/side/price can be eyeballed for correctness.
                    for f in fills.iter().take(4) {
                        tracing::info!(
                            wallet = %wallet_lc, side = %f.side, price = f.price,
                            sport = f.sport.as_deref().unwrap_or("-"),
                            bet_type = f.bet_type.as_deref().unwrap_or("-"),
                            title = %f.title, "  sample-fill (DRY, not inserted)"
                        );
                    }
                    tracing::info!(
                        wallet = %wallet_lc, fetched, mapped = fills.len(),
                        "backfilled (DRY — no writes)"
                    );
                } else {
                    // Insert in bounded batches so one wallet's history is a few
                    // round-trips, not a single giant UNNEST.
                    let mut inserted = 0u64;
                    for chunk in fills.chunks(1000) {
                        inserted += portfolio.insert_trader_fills(chunk).await.unwrap_or(0);
                    }
                    total_inserted += inserted;
                    tracing::info!(
                        i = i + 1, of = traders.len(), wallet = %wallet_lc,
                        fetched, new_rows = inserted, "backfilled"
                    );
                }
            }
            Err(e) => {
                // A single wallet's failure (429 exhaustion, transient) must not abort
                // the run — log and move on; the next run picks it up (idempotent).
                tracing::warn!(wallet = %wallet_lc, err = %e, "backfill: wallet failed, skipping");
            }
        }
        // Inter-wallet pacing: the live consensus bot polls the SAME data-api
        // concurrently, so keep the backfill's sustained rate low to avoid drawing
        // a throttle (403) that would also hurt live polling.
        tokio::time::sleep(std::time::Duration::from_millis(400)).await;
    }
    tracing::info!(
        wallets = traders.len(),
        total_fetched,
        total_new_rows = total_inserted,
        "Backfill: history sync complete"
    );

    // Classification needs the whole fleet's fills — skip in single-wallet/dry mode.
    if only.is_none() && !dry_run {
        classify_trader_types(portfolio).await?;
    }
    Ok(())
}

/// Label each tracked wallet `bot` | `human` in `followed_traders.trader_type` from
/// its captured fills. Heuristic: a market-maker bot crams a huge number of fills
/// into very few distinct days AND churns both sides in the same market. We flag as
/// `bot` when fills-per-active-day is extreme (≥ 400) — a human placing picks does
/// not fire hundreds of trades a day. Advisory only: nothing in the live path reads
/// `trader_type`; the selection layer filters on it. Read-then-UPDATE (idempotent).
pub async fn classify_trader_types(portfolio: &PgPortfolio) -> Result<()> {
    let n = portfolio.classify_trader_types().await?;
    tracing::info!(updated = n, "Backfill: trader_type classified");
    Ok(())
}
