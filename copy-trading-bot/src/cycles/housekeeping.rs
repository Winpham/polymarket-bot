use anyhow::{Context, Result};
use std::time::Duration;

use crate::data::models::GammaMarket;
use crate::live::broadcast;
use crate::storage::portfolio::BetSide;
use crate::storage::postgres::PgPortfolio;
use crate::telegram::notifier::TelegramNotifier;

const GAMMA_API: &str = "https://gamma-api.polymarket.com";

pub async fn housekeeping_cycle(
    portfolio: &PgPortfolio,
    notifier: &TelegramNotifier,
    http: &reqwest::Client,
) -> Result<()> {
    let open_ids = portfolio.open_copy_bet_market_ids().await?;

    for market_id in &open_ids {
        tokio::time::sleep(Duration::from_millis(200)).await;
        match check_market_resolution(http, market_id).await {
            Ok(Some(yes_won)) => {
                if let Some(r) = portfolio.resolve_bet(market_id, yes_won).await? {
                    let emoji = if r.won { "✅" } else { "❌" };
                    let result_label = if r.won { "WON" } else { "LOST" };
                    let side_emoji = match r.side {
                        BetSide::Yes => "🟢 YES",
                        BetSide::No => "🔴 NO",
                    };
                    let roi = bet_roi(r.pnl, r.cost, r.entry_fee);
                    let msg = format!(
                        "{emoji} *Copy Bet {result_label}* ({strat})\n\n\
                         📋 _{question}_\n\
                         🎲 Side: *{side}* — {shares:.1} shares @ `{price:.1}¢`\n\
                         💵 Stake: `€{cost:.2}` → PnL: `€{pnl:+.2}` ({roi:+.0}%)\n\n\
                         💰 Strategy bankroll: `€{bankroll:.2}`\n\
                         📊 Strategy: {sw}W/{sl}L `€{sp:+.2}` | All: {wins}W/{losses}L `€{total_pnl:+.2}`",
                        strat = r.strategy,
                        question = r.question,
                        side = side_emoji,
                        shares = r.shares,
                        price = r.entry_price * 100.0,
                        cost = r.cost,
                        pnl = r.pnl,
                        bankroll = r.bankroll,
                        sw = r.strat_wins,
                        sl = r.strat_losses,
                        sp = r.strat_pnl,
                        wins = r.total_wins,
                        losses = r.total_losses,
                        total_pnl = r.total_pnl,
                    );
                    broadcast(notifier, portfolio, &msg).await;
                    tracing::info!(
                        market = %market_id,
                        strategy = %r.strategy,
                        result = result_label,
                        pnl = format_args!("€{:+.2}", r.pnl),
                        bankroll = format_args!("€{:.2}", r.bankroll),
                        "Copy bet resolved"
                    );
                }
            }
            Ok(None) => {} // still open
            Err(e) => {
                tracing::warn!(market = %market_id, err = %e, "Copy resolution check failed");
            }
        }
    }

    // --- Consensus forward edge tracking + trajectory ("works like a stock") ---
    // Resolve via the CLOB by condition_id — the canonical path that works for
    // EVERY market (incl. sports markets whose slug is absent from Gamma), and
    // gives the live per-outcome price for the trajectory in the SAME call. We
    // dedupe by condition_id so each market is fetched once per cycle.
    let unresolved = portfolio
        .unresolved_consensus_signals()
        .await
        .unwrap_or_default();

    let mut by_cond: std::collections::HashMap<&str, Vec<&_>> = std::collections::HashMap::new();
    for sig in &unresolved {
        if !sig.condition_id.is_empty() {
            by_cond
                .entry(sig.condition_id.as_str())
                .or_default()
                .push(sig);
        }
    }

    let mut consensus_resolved = 0usize;
    let mut snapshots = 0usize;
    for (cond, sigs) in &by_cond {
        tokio::time::sleep(Duration::from_millis(120)).await;
        let market = match crate::data::models::fetch_clob_market(http, cond).await {
            Ok(m) => m,
            Err(_) => continue, // transient — try next cycle
        };
        for sig in sigs {
            let price = market.outcome_price(sig.outcome_index);
            match market.outcome_won(sig.outcome_index) {
                Some(won) => match portfolio.resolve_consensus_signal(sig.id, won, cond).await {
                    Ok(()) => {
                        consensus_resolved += 1;
                        crate::metrics::record_consensus_resolution(
                            &sig.strategy,
                            won,
                            sig.is_sports,
                        );
                    }
                    Err(e) => {
                        tracing::warn!(err = %e, signal_id = sig.id, "resolve_consensus_signal failed")
                    }
                },
                // Still open → record a trajectory snapshot (the price chart).
                // Skip the `_blind` benchmark population (we only need its
                // resolution, not a per-signal chart) to bound snapshot volume.
                None if sig.strategy != "_blind" => {
                    if let Err(e) = portfolio
                        .snapshot_consensus_signal(
                            sig.id,
                            sig.net_count,
                            sig.n_backers,
                            sig.mean_price,
                            price,
                        )
                        .await
                    {
                        tracing::warn!(err = %e, signal_id = sig.id, "snapshot failed");
                    } else {
                        snapshots += 1;
                    }
                }
                None => {}
            }
        }
    }
    if snapshots > 0 {
        tracing::info!(snapshots, "Consensus trajectory snapshots recorded");
    }
    if consensus_resolved > 0
        && let Ok((res, won, _, _)) = portfolio.consensus_scoreboard().await
    {
        tracing::info!(
            newly_resolved = consensus_resolved,
            total_resolved = res,
            total_won = won,
            "Consensus signals resolved"
        );
    }

    tracing::info!(
        open_copy_bets = open_ids.len(),
        consensus_unresolved = unresolved.len(),
        "Copy housekeeping cycle complete"
    );
    Ok(())
}

async fn check_market_resolution(http: &reqwest::Client, market_id: &str) -> Result<Option<bool>> {
    let url = format!("{GAMMA_API}/markets/{market_id}");
    let resp = http.get(&url).send().await?;
    let text = resp.text().await?;
    let market: GammaMarket = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse market {market_id}"))?;
    Ok(market.resolved_yes())
}

fn bet_roi(pnl: f64, cost: f64, entry_fee: f64) -> f64 {
    let total_invested = cost + entry_fee;
    if total_invested > 0.0 {
        pnl / total_invested * 100.0
    } else {
        0.0
    }
}
