//! Consensus detection cycle: poll the tracked-trader universe, build per-market
//! books, score them, and push tiered alerts on fresh strong/elite consensus.
//!
//! This is additive to the existing per-trader copy cycle — it reads the same
//! `followed_traders` but never places bets; it only alerts and records signals
//! for forward edge tracking.

use std::collections::HashMap;

use anyhow::Result;
use chrono::Utc;
use futures_util::future::join_all;

use crate::config::CopyTradingConfig;
use crate::live::broadcast;
use crate::scanner::consensus::{
    BackerInfo, ConsensusParams, ConsensusSignal, MarketBook, StrategyDef, Tier, TraderVote,
    default_portfolio, quality_weight, score_all_strategies,
};
use crate::scanner::copy_trader::CopyTraderMonitor;
use crate::storage::consensus::NewConsensusSignal;
use crate::storage::postgres::PgPortfolio;
use crate::telegram::notifier::TelegramNotifier;
use polymarket_common::ntfy::Ntfy;

/// Build [`ConsensusParams`] from runtime config.
fn params_from_cfg(cfg: &CopyTradingConfig) -> ConsensusParams {
    ConsensusParams {
        min_backers: cfg.min_backers,
        max_opposers: cfg.max_opposers,
        max_price_std: cfg.max_price_std,
        max_age_mins: cfg.max_age_mins,
        strong_net: cfg.strong_net,
        elite_net: cfg.elite_net,
        elite_rank: cfg.elite_rank,
        // Incumbent `strict` knobs: sports treatment mirrors the legacy global flag;
        // the other portfolio knobs are no-ops for strict.
        require_elite: false,
        price_band: None,
        sports_mode: if cfg.consensus_include_sports {
            crate::scanner::consensus::SportsMode::Include
        } else {
            crate::scanner::consensus::SportsMode::Exclude
        },
        weight_mode: crate::scanner::consensus::WeightMode::Quality,
    }
}

/// Local sports/esports heuristic on the activity title + slug (avoids a Gamma
/// round-trip per market). Mirrors `GammaMarket::is_sports_or_esports`.
fn is_sports(title: &str, slug: &str) -> bool {
    let t = title.to_lowercase();
    let s = slug.to_lowercase();
    const SLUG_PATS: &[&str] = &[
        "nba-", "nfl-", "mlb-", "nhl-", "fifwc", "ucl-", "epl-", "laliga", "-cs2-", "lol-", "dota",
        "soccer", "atp-", "wta-", "ufc-",
    ];
    const TITLE_PATS: &[&str] = &[
        " vs. ",
        " vs ",
        "spread:",
        "o/u ",
        "over/under",
        "win on 20",
        " fc ",
        "moneyline",
    ];
    SLUG_PATS.iter().any(|p| s.contains(p)) || TITLE_PATS.iter().any(|p| t.contains(p))
}

pub async fn consensus_cycle(
    portfolio: &PgPortfolio,
    notifier: &TelegramNotifier,
    monitor: &CopyTraderMonitor,
    cfg: &CopyTradingConfig,
    ntfy: Option<&Ntfy>,
) -> Result<()> {
    let traders = portfolio.get_active_traders().await?;
    if traders.is_empty() {
        tracing::debug!("Consensus: no active tracked traders yet");
        return Ok(());
    }

    let since = Utc::now() - chrono::Duration::hours(cfg.consensus_window_hours);

    // Poll all tracked traders' recent activity concurrently.
    let polls = traders.iter().map(|t| {
        let wallet = t.proxy_wallet.clone();
        async move {
            let trades = monitor.poll_trader_activity(&wallet, since).await;
            (t, trades)
        }
    });
    let results = join_all(polls).await;

    // Assemble per-market books.
    let mut books: HashMap<String, MarketBook> = HashMap::new();
    let mut polled_ok = 0usize;
    for (trader, trades) in results {
        let trades = match trades {
            Ok(t) => {
                polled_ok += 1;
                t
            }
            Err(e) => {
                tracing::debug!(wallet = %trader.proxy_wallet, err = %e, "Consensus poll failed");
                continue;
            }
        };
        let name = trader
            .username
            .clone()
            .unwrap_or_else(|| trader.proxy_wallet[..8.min(trader.proxy_wallet.len())].to_string());
        let quality = quality_weight(trader.rank);

        for tr in trades {
            if tr.side != "BUY" {
                continue;
            }
            let Some(oidx) = tr.outcome_index else {
                continue;
            };
            if !(tr.price > 0.0 && tr.price < 1.0) {
                continue;
            }
            let title = tr.title.clone().unwrap_or_else(|| tr.slug.clone());
            let sport = is_sports(&title, &tr.slug);
            let book = books.entry(tr.condition_id.clone()).or_insert_with(|| {
                MarketBook::new(
                    tr.condition_id.clone(),
                    title.clone(),
                    tr.slug.clone(),
                    tr.event_slug.clone(),
                    sport,
                )
            });
            book.add_vote(
                oidx,
                tr.outcome.clone().unwrap_or_else(|| oidx.to_string()),
                TraderVote {
                    wallet: trader.proxy_wallet.to_lowercase(),
                    name: name.clone(),
                    rank: trader.rank,
                    pnl: trader.pnl,
                    quality,
                    price: tr.price,
                    size_usd: tr.size_usd,
                    ts: tr.timestamp,
                },
            );
        }
    }

    let book_vec: Vec<MarketBook> = books.into_values().collect();

    // Serialize the raw vote atoms ONCE per (market, outcome) — strategy-agnostic.
    // Stored on every signal so a strategy invented later can be replayed over it.
    let atoms = atom_log(&book_vec);

    let strategies = active_portfolio(cfg);
    let alerting: std::collections::HashSet<&str> = strategies
        .iter()
        .filter(|d| d.alerting)
        .map(|d| d.name)
        .collect();
    let signals = score_all_strategies(&book_vec, Utc::now(), &strategies);

    let mut alerts_sent = 0usize;
    for sig in &signals {
        // Upsert EVERY strategy's signal for forward edge tracking.
        let new = to_new_signal(sig, &atoms);
        let state = match portfolio.upsert_consensus_signal(&new).await {
            Ok(s) => s,
            Err(e) => {
                tracing::warn!(err = %e, cond = %sig.condition_id, strat = %sig.strategy, "upsert_consensus_signal failed");
                continue;
            }
        };

        // Only the alerting strategy(ies) push Telegram; only STRONG / ELITE.
        if !alerting.contains(sig.strategy.as_str()) || sig.tier == Tier::Watch {
            continue;
        }

        let prev_tier = state.last_alert_tier.as_deref().and_then(Tier::from_str);
        let prev_net = state.last_alert_net.unwrap_or(i32::MIN);
        let should_alert = match prev_tier {
            None => true, // never alerted
            Some(pt) => {
                sig.tier.level() > pt.level()
                    || (sig.net_count as i32) >= prev_net + cfg.consensus_realert_net_delta as i32
            }
        };
        if !should_alert {
            continue;
        }

        let msg = format_consensus_alert(sig);
        broadcast(notifier, portfolio, &msg).await;
        // Phone push via the user's brainstem ntfy channel.
        if let Some(n) = ntfy {
            let (priority, tag) = match sig.tier {
                Tier::Elite => (5u8, "fire"),
                _ => (4u8, "green_circle"),
            };
            let title = format!(
                "{} {} consensus — BUY {}",
                sig.tier.emoji(),
                sig.tier.as_str(),
                sig.outcome_label
            );
            n.push(&title, &msg, priority, &[tag]).await;
        }
        if let Err(e) = portfolio
            .record_consensus_alert(
                state.id,
                &sig.strategy,
                sig.tier.as_str(),
                sig.net_count as i32,
                sig.score,
            )
            .await
        {
            tracing::warn!(err = %e, "record_consensus_alert failed");
        }
        crate::metrics::record_consensus_alert(&sig.strategy, sig.tier.as_str());
        alerts_sent += 1;
    }

    crate::metrics::record_consensus_cycle(book_vec.len() as u64, signals.len() as u64);

    tracing::info!(
        traders_polled = polled_ok,
        markets = book_vec.len(),
        strategies = strategies.len(),
        signals = signals.len(),
        alerts_sent,
        "Consensus cycle complete"
    );
    Ok(())
}

/// The active strategy portfolio: the full default set, optionally narrowed by
/// the `CONSENSUS_STRATEGIES` allowlist (empty = all).
fn active_portfolio(cfg: &CopyTradingConfig) -> Vec<StrategyDef> {
    let base = params_from_cfg(cfg);
    let all = default_portfolio(&base);
    let filter = cfg.consensus_strategies.trim();
    if filter.is_empty() {
        return all;
    }
    let allow: std::collections::HashSet<&str> = filter
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();
    all.into_iter().filter(|d| allow.contains(d.name)).collect()
}

/// Serialize the raw vote atoms for every observed `(condition_id, outcome_index)`.
/// Strategy-agnostic, computed once per cycle, reused across all strategies.
fn atom_log(books: &[MarketBook]) -> std::collections::HashMap<(String, i32), serde_json::Value> {
    let mut map = std::collections::HashMap::new();
    for book in books {
        for (&oidx, votes) in &book.votes {
            let arr = serde_json::Value::Array(
                votes
                    .iter()
                    .map(|v| {
                        serde_json::json!({
                            "wallet": v.wallet,
                            "name": v.name,
                            "rank": v.rank,
                            "pnl": v.pnl,
                            "price": v.price,
                            "size_usd": v.size_usd,
                            "ts": v.ts.timestamp(),
                        })
                    })
                    .collect(),
            );
            map.insert((book.condition_id.clone(), oidx), arr);
        }
    }
    map
}

/// Convert a scored signal into its DB upsert payload (atoms attached).
fn to_new_signal(
    sig: &ConsensusSignal,
    atoms: &std::collections::HashMap<(String, i32), serde_json::Value>,
) -> NewConsensusSignal {
    let backers_json = serde_json::Value::Array(
        sig.backers
            .iter()
            .map(|b: &BackerInfo| {
                serde_json::json!({ "wallet": b.wallet, "name": b.name, "rank": b.rank })
            })
            .collect(),
    );
    let observed_votes = atoms
        .get(&(sig.condition_id.clone(), sig.outcome_index))
        .cloned()
        .unwrap_or(serde_json::Value::Null);
    NewConsensusSignal {
        strategy: sig.strategy.clone(),
        observed_votes,
        condition_id: sig.condition_id.clone(),
        outcome_index: sig.outcome_index,
        outcome_label: sig.outcome_label.clone(),
        title: sig.title.clone(),
        slug: sig.slug.clone(),
        event_slug: sig.event_slug.clone(),
        is_sports: sig.is_sports,
        n_backers: sig.n_backers as i32,
        n_opposers: sig.n_opposers as i32,
        net_count: sig.net_count as i32,
        net_quality: sig.net_quality,
        mean_price: sig.mean_price,
        price_std: sig.price_std,
        recency_mins: sig.recency_mins,
        total_usd: sig.total_usd,
        best_backer_rank: sig.best_backer_rank,
        score: sig.score,
        tier: sig.tier.as_str().to_string(),
        backers_json,
    }
}

/// Rich Telegram alert for a consensus signal.
fn format_consensus_alert(sig: &ConsensusSignal) -> String {
    let url = match &sig.event_slug {
        Some(ev) => format!("https://polymarket.com/event/{ev}"),
        None => format!("https://polymarket.com/event/{}", sig.slug),
    };
    let sport_tag = if sig.is_sports { " ⚽" } else { "" };
    let names: Vec<String> = sig
        .backers
        .iter()
        .take(8)
        .map(|b| match b.rank {
            Some(r) => format!("{} (#{r})", b.name),
            None => b.name.clone(),
        })
        .collect();
    let more = if sig.backers.len() > 8 {
        format!(" +{} more", sig.backers.len() - 8)
    } else {
        String::new()
    };

    format!(
        "{emoji} *{tier} CONSENSUS*{sport}\n\n\
         📋 *{title}*\n\
         🎯 BUY *{outcome}*  ({net:+} net — {back} backing, {opp} opposing)\n\
         💵 Avg entry `{price:.0}¢` (σ {std:.0}¢) | ${usd:.0}k total\n\
         ⏱ Freshest fill {age}\n\
         👥 {names}{more}\n\
         🔗 {url}",
        emoji = sig.tier.emoji(),
        tier = sig.tier.as_str(),
        sport = sport_tag,
        title = truncate(&sig.title, 80),
        outcome = sig.outcome_label,
        net = sig.net_count,
        back = sig.n_backers,
        opp = sig.n_opposers,
        price = sig.mean_price * 100.0,
        std = sig.price_std * 100.0,
        usd = sig.total_usd / 1000.0,
        age = humanize_mins(sig.recency_mins),
        names = names.join(", "),
        more = more,
        url = url,
    )
}

fn humanize_mins(m: i64) -> String {
    if m < 60 {
        format!("{m}m ago")
    } else if m < 1440 {
        format!("{}h ago", m / 60)
    } else {
        format!("{}d ago", m / 1440)
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let t: String = s.chars().take(max.saturating_sub(1)).collect();
        format!("{t}…")
    }
}
