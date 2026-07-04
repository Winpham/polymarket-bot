//! Hot-lane fast poll for the router follow-set (2026-07-04 capture-hardening,
//! paper-only).
//!
//! The main consensus cycle ticks at minute cadence and polls the whole tracked
//! universe, so fill→signal latency is ~1.5–3 min (measured: fill→ingestion
//! median 66s / p90 124s, plus up to a 60s cycle tick). The router edge is
//! FRONT-LOADED — only 28–36% of signals ever retrace to the sharp's price — so
//! that latency erodes it.
//!
//! This lane polls ONLY the current follow-set wallets (~6) every `HOT_POLL_SECS`
//! (default 12), ingests through the SAME window-vote + durable-fill path (dedup
//! is the DB's job), then runs a SCOPED scoring pass for the affected markets
//! only: it rebuilds each affected market's book with `books_from_window_votes`
//! and scores ONLY the `proven_router` arm (`score_router_only` — pure), upserting
//! via the idempotent `upsert_consensus_signal`. It NEVER touches the main cycle
//! cadence and NEVER polls the whole universe faster (protecting the API 429
//! budget). Flag-gated (`HOT_LANE`, default OFF, and requires `PROVEN_ROUTER` so a
//! follow-set exists): off ⇒ the task is never spawned ⇒ byte-identical.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use chrono::{DateTime, Duration, Utc};
use futures_util::future::join_all;
use tokio::sync::Semaphore;

use crate::config::CopyTradingConfig;
use crate::scanner::consensus::{quality_weight, score_router_only};
use crate::scanner::copy_trader::CopyTraderMonitor;
use crate::storage::postgres::{FollowedTrader, PgPortfolio};

use super::consensus_cycle::{
    atom_log, books_from_window_votes, params_from_cfg, to_new_signal, trade_to_fill,
    trade_to_window_vote, trader_name,
};

/// One hot-lane pass over `set` (the currently-published follow-set). `cursors`
/// holds the in-memory per-wallet poll watermark across passes (first sight
/// backfills the consensus window). Returns the number of `proven_router` signals
/// upserted this pass.
pub async fn hot_lane_tick(
    portfolio: &PgPortfolio,
    monitor: &CopyTraderMonitor,
    cfg: &CopyTradingConfig,
    set: Arc<HashSet<String>>,
    cursors: &mut HashMap<String, DateTime<Utc>>,
) -> anyhow::Result<usize> {
    if set.is_empty() {
        return Ok(0); // fail-closed: nothing to route to
    }
    let now = Utc::now();
    let n_set = set.len();
    let window_start = now - Duration::hours(cfg.consensus_window_hours);
    let wallets: Vec<String> = set.iter().cloned().collect();

    // Poll ONLY the follow-set, semaphore-capped like the consensus fan-out so the
    // fast cadence can't burst the data-api into 429s.
    let sem = Arc::new(Semaphore::new(cfg.consensus_max_concurrency.max(1)));
    let polls = wallets.iter().map(|wallet| {
        let wallet = wallet.clone();
        // Backfill the window on first sight; otherwise poll only the new tail.
        let since = cursors.get(&wallet).copied().unwrap_or(window_start);
        let sem = Arc::clone(&sem);
        async move {
            let _permit = sem.acquire_owned().await;
            let poll = monitor.poll_trader_activity(&wallet, since).await;
            (wallet, poll)
        }
    });
    let results: Vec<(String, _)> = join_all(polls).await;

    // Attach real rank/pnl to the follow-set wallets' votes (a routed wallet may
    // have dropped off the leaderboard, so we look up regardless of active status).
    let meta = portfolio.traders_by_wallets(&wallets).await.unwrap_or_default();
    let by_wallet: HashMap<String, FollowedTrader> = meta
        .into_iter()
        .map(|t| (t.proxy_wallet.to_lowercase(), t))
        .collect();

    let mut votes = Vec::new();
    let mut fills = Vec::new();
    let mut polled_ok: Vec<String> = Vec::new();
    for (wallet, poll) in results {
        let trades = match poll {
            Ok(r) => {
                polled_ok.push(wallet.clone());
                r.trades
            }
            Err(e) => {
                tracing::debug!(wallet = %wallet, err = %e, "hot-lane poll failed");
                continue;
            }
        };
        let wallet_lc = wallet.to_lowercase();
        let trader = by_wallet
            .get(&wallet_lc)
            .cloned()
            .unwrap_or_else(|| synth_trader(&wallet_lc));
        let name = trader_name(&trader);
        let quality = quality_weight(trader.rank);
        for tr in &trades {
            if let Some(v) = trade_to_window_vote(&trader, &name, quality, tr) {
                votes.push(v);
            }
            if let Some(f) = trade_to_fill(&wallet_lc, tr) {
                fills.push(f);
            }
        }
    }

    // Persist through the SAME dedup path the slow cycle uses — one shared store,
    // no divergence. Best-effort: a failed insert just means the slow cycle picks
    // it up next minute.
    if let Err(e) = portfolio.insert_window_votes(&votes).await {
        tracing::warn!(err = %e, "hot-lane insert_window_votes failed");
    }
    if let Err(e) = portfolio.insert_trader_fills(&fills).await {
        tracing::warn!(err = %e, "hot-lane insert_trader_fills failed");
    }

    // Advance the in-memory poll cursor for wallets that polled OK.
    for w in &polled_ok {
        cursors.insert(w.clone(), now);
    }

    // Affected markets this pass: the distinct conditions the fresh votes touched.
    let affected: HashSet<String> = votes.iter().map(|v| v.condition_id.clone()).collect();
    if affected.is_empty() {
        return Ok(0);
    }

    // SCOPED scoring pass: rebuild ONLY the affected markets' books from the shared
    // window store (so multi-wallet net_count is correct, not just this tick's
    // trades) and score ONLY the proven_router arm. An empty trust map is
    // byte-identical for this arm (it consults no trust). Other arms are never
    // touched — the slow cycle still owns them.
    let window = portfolio
        .load_window_votes(window_start)
        .await
        .unwrap_or_default();
    let scoped: Vec<_> = window
        .into_iter()
        .filter(|v| affected.contains(&v.condition_id))
        .collect();
    if scoped.is_empty() {
        return Ok(0);
    }
    let trust = Default::default();
    let books = books_from_window_votes(&scoped, &trust);
    let base = params_from_cfg(cfg);
    let signals = score_router_only(&books, now, &base, set);
    let atoms = atom_log(&books);

    let mut upserted = 0usize;
    for sig in &signals {
        let new = to_new_signal(sig, &atoms);
        match portfolio.upsert_consensus_signal(&new).await {
            Ok(_) => upserted += 1,
            Err(e) => tracing::warn!(
                err = %e, cond = %sig.condition_id, "hot-lane upsert_consensus_signal failed"
            ),
        }
    }
    if upserted > 0 {
        tracing::info!(
            follow_set = n_set,
            polled_ok = polled_ok.len(),
            affected = affected.len(),
            signals = upserted,
            "hot-lane scoped scoring pass"
        );
    }
    Ok(upserted)
}

/// A minimal followed-trader stand-in for a follow-set wallet that isn't in
/// `followed_traders` (defensive — the follow-set is derived from captured fills,
/// so this is normally unreachable). rank/pnl unknown ⇒ `quality_weight` = 1.0,
/// which does not affect proven_router firing (keyed on net_count).
fn synth_trader(wallet_lc: &str) -> FollowedTrader {
    FollowedTrader {
        id: 0,
        proxy_wallet: wallet_lc.to_string(),
        username: None,
        source: "router".to_string(),
        rank: None,
        pnl: None,
        volume: None,
        win_rate: None,
        added_at: Utc::now(),
        last_checked_at: None,
        active: false,
        consensus_eligible: false,
        earned_eligible: false,
    }
}
