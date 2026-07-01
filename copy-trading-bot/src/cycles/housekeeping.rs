use anyhow::{Context, Result};
use std::time::Duration;

use crate::config::CopyTradingConfig;
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
    cfg: &CopyTradingConfig,
    ntfy: Option<&polymarket_common::ntfy::Ntfy>,
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

    // INDEPENDENT unresolved source (the survivorship fix): trader_fills on
    // markets that may never have triggered a consensus signal. Resolving only
    // consensus conditions would leave those fills perpetually unresolved and
    // bias every trust profile toward markets that happened to fire consensus.
    // UNION it into the cond set (deduped against the consensus conds), bounded
    // by a per-cycle cap and a min-age so very fresh markets aren't probed.
    let tf_conds = portfolio
        .trader_fill_unresolved_conditions(
            chrono::Duration::hours(6),
            cfg.trader_fills_resolve_per_cycle,
        )
        .await
        .unwrap_or_default();
    let mut all_conds: Vec<String> = by_cond.keys().map(|c| c.to_string()).collect();
    {
        let known: std::collections::HashSet<&str> = by_cond.keys().copied().collect();
        for c in &tf_conds {
            if !known.contains(c.as_str()) {
                all_conds.push(c.clone());
            }
        }
    }

    let mut consensus_resolved = 0usize;
    let mut snapshots = 0usize;
    let mut fills_resolved = 0u64;
    // Phase 2: bounded real book-ask capture (only when CAPTURE_ENTRY_ASK is on).
    let mut asks_captured = 0usize;
    // Phase 3: paper equity ledger scope (empty = every non-blind strategy) + count.
    let ledger_set: std::collections::HashSet<&str> = cfg
        .ledger_strategies
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();
    let should_ledger =
        |strat: &str| strat != "_blind" && (ledger_set.is_empty() || ledger_set.contains(strat));
    let mut ledger_appends = 0usize;
    for cond in &all_conds {
        tokio::time::sleep(Duration::from_millis(120)).await;
        let market = match crate::data::models::fetch_clob_market(http, cond).await {
            Ok(m) => m,
            Err(_) => continue, // transient — try next cycle
        };
        // 1. Consensus signals for this cond (if any) — existing behavior.
        if let Some(sigs) = by_cond.get(cond.as_str()) {
            for sig in sigs {
                let price = market.outcome_price(sig.outcome_index);
                match market.outcome_won(sig.outcome_index) {
                    Some(won) => {
                        match portfolio.resolve_consensus_signal(sig.id, won, cond).await {
                            Ok(()) => {
                                consensus_resolved += 1;
                                crate::metrics::record_consensus_resolution(
                                    &sig.strategy,
                                    won,
                                    sig.is_sports,
                                );
                                // Phase 3: append the PAPER equity-ledger bet at the
                                // realizable entry. Idempotent (ON CONFLICT DO NOTHING),
                                // so re-resolution never double-appends. PAPER only.
                                if should_ledger(&sig.strategy) {
                                    match portfolio
                                        .append_paper_bet(
                                            &sig.strategy,
                                            cond,
                                            sig.outcome_index,
                                            cfg.flat_stake,
                                            cfg.exec_haircut,
                                            cfg.fee_pct,
                                        )
                                        .await
                                    {
                                        Ok(true) => ledger_appends += 1,
                                        Ok(false) => {}
                                        Err(e) => tracing::warn!(
                                            err = %e, signal_id = sig.id, "append_paper_bet failed"
                                        ),
                                    }
                                }
                            }
                            Err(e) => {
                                tracing::warn!(err = %e, signal_id = sig.id, "resolve_consensus_signal failed")
                            }
                        }
                    }
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
                        // Phase 2: capture the REAL executable ask ONCE while open,
                        // so the honest tracker uses the market ask (not mid+haircut)
                        // where captured. Bounded per cycle; best-effort (a failure
                        // just leaves entry_ask NULL → the query falls back). Never
                        // touches the live path — pure honest-tracker instrumentation.
                        if cfg.capture_entry_ask
                            && sig.entry_ask.is_none()
                            && asks_captured < cfg.entry_ask_max_per_cycle
                            && let Some(tid) = market.outcome_token_id(sig.outcome_index)
                        {
                            tokio::time::sleep(Duration::from_millis(80)).await;
                            match crate::data::models::fetch_best_ask(http, tid).await {
                                Ok(Some(ask)) => match portfolio.set_entry_ask(sig.id, ask).await {
                                    Ok(true) => asks_captured += 1,
                                    Ok(false) => {}
                                    Err(e) => tracing::warn!(
                                        err = %e, signal_id = sig.id, "set_entry_ask failed"
                                    ),
                                },
                                Ok(None) => {} // empty book — retry next cycle
                                Err(e) => {
                                    tracing::warn!(err = %e, signal_id = sig.id, "fetch_best_ask failed")
                                }
                            }
                        }
                    }
                    None => {}
                }
            }
        }
        // 2. Durable trader-fill ledger — resolved INDEPENDENTLY of consensus.
        // `winner_index` is the winning token (multi-outcome correct). A closed
        // market with NO winner token (void/refund) is SKIPPED — we don't charge
        // every BUY a loss; those fills settle if/when the market gets a winner.
        if market.closed
            && let Some(idx) = market.tokens.iter().position(|t| t.winner)
        {
            match portfolio.resolve_trader_fills(cond, idx as i32).await {
                Ok(n) => fills_resolved += n,
                Err(e) => {
                    tracing::warn!(err = %e, cond = %cond, "resolve_trader_fills failed")
                }
            }
        }
    }
    if snapshots > 0 {
        tracing::info!(snapshots, "Consensus trajectory snapshots recorded");
    }
    if asks_captured > 0 {
        tracing::info!(asks_captured, "Honest tracker: real book-asks captured");
    }
    if ledger_appends > 0 {
        tracing::info!(
            ledger_appends,
            "Honest tracker: paper equity-ledger bets appended"
        );
    }
    if fills_resolved > 0 {
        tracing::info!(fills_resolved, "Trader fills resolved");
    }
    // Retention prune (default 0 = keep-all, the durable archive is the point).
    if cfg.trader_fills_retention_days > 0 {
        match portfolio
            .prune_trader_fills(cfg.trader_fills_retention_days)
            .await
        {
            Ok(n) if n > 0 => tracing::info!(pruned = n, "Trader fills pruned (retention)"),
            Ok(_) => {}
            Err(e) => tracing::warn!(err = %e, "prune_trader_fills failed"),
        }
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

    // Phase 4: opt-in minimal-noise honest-tracker digest (material change only;
    // silent by default). Read-only — never touches the live path.
    crate::cycles::honest_digest::maybe_push(portfolio, ntfy, cfg).await;

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
