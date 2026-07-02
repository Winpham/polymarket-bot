//! Auto-tracker: keeps the followed-trader universe in sync with the top-N of
//! the Polymarket leaderboard.
//!
//! Replaces the manual-`/follow`-only flow with an automatic universe: the union
//! of the top `TRACK_TOP_N` traders across the configured periods. Manually
//! followed traders (`source = 'manual'`) are never touched here.

use std::collections::HashMap;

use anyhow::Result;
use chrono::Utc;
use reqwest::Client;

use crate::config::CopyTradingConfig;
use crate::scanner::copy_trader::{LeaderboardRaw, fetch_leaderboard_n, fetch_leaderboard_paged};
use crate::storage::consensus::LeaderboardTraderUpsert;
use crate::storage::postgres::PgPortfolio;

/// Above this fetch depth the refresh paginates (offset 0,50,…) instead of a
/// single `limit`-capped call. Mirrors the server-side page size.
const PAGED_FETCH_THRESHOLD: usize = 50;

/// Union of a trader across periods, keeping the best (lowest) rank.
struct Merged {
    raw: LeaderboardRaw,
    periods: Vec<String>,
}

/// Refresh the tracked-trader universe from the leaderboard.
/// Returns `(upserted, deactivated)`.
pub async fn refresh_universe(
    http: &Client,
    portfolio: &PgPortfolio,
    cfg: &CopyTradingConfig,
) -> Result<(usize, u64)> {
    let periods: Vec<String> = cfg
        .track_periods
        .split(',')
        .map(|s| s.trim().to_uppercase())
        .filter(|s| !s.is_empty())
        .collect();

    // Effective capture depth: never shrink below the legacy `track_top_n` knob
    // (additive). `> 50` paginates; otherwise the single `limit`-capped call —
    // byte-identical to today when both default to 40.
    let depth = cfg.track_depth.max(cfg.track_top_n);

    let mut merged: HashMap<String, Merged> = HashMap::new();
    for period in &periods {
        let fetched = if depth > PAGED_FETCH_THRESHOLD {
            fetch_leaderboard_paged(http, period, depth).await
        } else {
            fetch_leaderboard_n(http, period, depth).await
        };
        match fetched {
            Ok(entries) => {
                for e in entries {
                    merged
                        .entry(e.wallet.clone())
                        .and_modify(|m| {
                            if e.rank < m.raw.rank {
                                m.raw.rank = e.rank;
                            }
                            // Prefer a non-empty username if we didn't have one.
                            if m.raw.username.is_none() && e.username.is_some() {
                                m.raw.username = e.username.clone();
                            }
                            m.periods.push(period.clone());
                        })
                        .or_insert_with(|| Merged {
                            periods: vec![period.clone()],
                            raw: e,
                        });
                }
            }
            Err(err) => {
                tracing::warn!(period = %period, err = %err, "Leaderboard fetch failed, skipping period");
            }
        }
    }

    if merged.is_empty() {
        tracing::warn!("Leaderboard refresh produced no traders — leaving universe untouched");
        return Ok((0, 0));
    }

    let mut upserted = 0usize;
    for m in merged.values() {
        // Belief-blind provenance: rank ≤ cutoff ⇒ votes in consensus; deeper ⇒
        // captured/profiled candidate only (consensus_eligible = FALSE).
        let consensus_eligible = m.raw.rank <= cfg.track_consensus_rank_cutoff;
        let up = LeaderboardTraderUpsert {
            wallet: m.raw.wallet.clone(),
            username: m.raw.username.clone(),
            rank: Some(m.raw.rank),
            pnl: Some(m.raw.pnl),
            volume: Some(m.raw.volume),
            periods: m.periods.join(","),
            consensus_eligible,
        };
        match portfolio.upsert_tracked_trader(&up).await {
            Ok(()) => upserted += 1,
            Err(e) => {
                tracing::warn!(wallet = %m.raw.wallet, err = %e, "upsert_tracked_trader failed")
            }
        }
    }

    // Drop-grace: deactivate auto-tracked traders unseen for grace*refresh minutes.
    let grace_mins = cfg.track_drop_grace.max(1) * cfg.track_refresh_mins.max(1) as i64;
    let cutoff = Utc::now() - chrono::Duration::minutes(grace_mins);
    let deactivated = portfolio
        .deactivate_stale_tracked(cutoff)
        .await
        .unwrap_or(0);

    if let Ok(active) = portfolio.count_tracked_traders().await {
        crate::metrics::record_tracked_traders(active as u64);
    }
    let (hot, deep) = portfolio.count_tracked_split().await.unwrap_or((0, 0));
    crate::metrics::record_tracked_split(hot as u64, deep as u64);

    tracing::info!(
        tracked = upserted,
        deactivated,
        hot,
        deep,
        periods = ?periods,
        depth,
        cutoff = cfg.track_consensus_rank_cutoff,
        "Leaderboard universe refreshed"
    );
    Ok((upserted, deactivated))
}
