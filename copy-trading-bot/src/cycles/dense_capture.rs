//! Dense early-life price capture (execution-latency decay run, Phase 0).
//!
//! The 5-min housekeeping snapshots cannot resolve a 1–5 minute action window;
//! this tick records a ~45s-spaced mid + executable best-ask for the FIRST
//! minutes of fresh signals from the actionable strategies, into
//! `signal_price_trajectory` (migration 034). The decay analysis
//! (`scripts/decay_analysis.py`) turns those trajectories into a per-strategy
//! speed budget.
//!
//! Bounded by construction: candidates are deduped to one anchor per
//! (market, outcome), limited to `DENSE_WINDOW_MINS`-fresh unresolved signals,
//! capped at `DENSE_MAX_SIGNALS` per tick, throttled like housekeeping.
//! Flag-gated (`DENSE_CAPTURE`, default OFF): the loop is never spawned when
//! off, so the live path is byte-identical. Best-effort: any fetch/insert
//! failure skips that point — capture must never disturb the pipeline.

use std::time::Duration;

use chrono::Utc;

use crate::config::CopyTradingConfig;
use crate::data::models::{fetch_best_ask, fetch_clob_market};
use crate::storage::postgres::PgPortfolio;

/// One dense-capture pass: snapshot every eligible fresh signal once.
/// Returns the number of trajectory points written.
pub async fn dense_capture_tick(
    portfolio: &PgPortfolio,
    http: &reqwest::Client,
    cfg: &CopyTradingConfig,
) -> anyhow::Result<usize> {
    let strategies: Vec<String> = cfg
        .dense_strategies
        .split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();
    if strategies.is_empty() {
        return Ok(0);
    }
    let cands = portfolio
        .dense_capture_candidates(&strategies, cfg.dense_window_mins, cfg.dense_max_signals)
        .await?;
    let mut written = 0usize;
    for c in &cands {
        // Same per-fetch throttle as the housekeeping loop.
        tokio::time::sleep(Duration::from_millis(120)).await;
        let market = match fetch_clob_market(http, &c.condition_id).await {
            Ok(m) => m,
            Err(_) => continue, // transient — this point is simply missing
        };
        if market.closed {
            continue; // resolution owns closed markets; the trajectory ends here
        }
        let mid = market.outcome_price(c.outcome_index);
        let ask = match market.tokens.get(c.outcome_index as usize) {
            Some(t) if !t.token_id.is_empty() => {
                fetch_best_ask(http, &t.token_id).await.unwrap_or(None)
            }
            _ => None,
        };
        if mid.is_none() && ask.is_none() {
            continue;
        }
        let secs = (Utc::now() - c.first_detected_at).num_seconds().max(0) as i32;
        match portfolio
            .insert_trajectory_point(c.signal_id, secs, mid, ask, Some(c.n_backers))
            .await
        {
            Ok(()) => written += 1,
            Err(e) => {
                tracing::warn!(err = %e, signal_id = c.signal_id, "trajectory insert failed")
            }
        }
    }
    if written > 0 {
        tracing::debug!(
            points = written,
            candidates = cands.len(),
            "dense capture tick"
        );
    }
    Ok(written)
}
