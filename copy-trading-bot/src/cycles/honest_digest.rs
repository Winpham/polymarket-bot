//! Opt-in, minimal-noise honest-tracker phone digest. It is silent by default
//! (`HONEST_DIGEST=false`) and, when enabled, pushes to ntfy ONLY on a material
//! change — a strategy crossing INTO/OUT of pilot-ready, or a paper drawdown newly
//! breaching the floor. Never a heartbeat. Read-only: it only READS the honest
//! tables + ledger; it never touches selection, alerting, or betting.
//!
//! State (the previous per-strategy GO / drawdown-breach flags) lives in a process
//! static, so a restart re-baselines silently — the first post-restart observation
//! records state without pushing.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use polymarket_common::ntfy::Ntfy;

use crate::config::CopyTradingConfig;
use crate::scanner::honest::{DigestSnapshot, DigestState, digest_changes, verdicts_by_strategy};
use crate::storage::postgres::PgPortfolio;

fn state() -> &'static Mutex<HashMap<String, DigestState>> {
    static S: OnceLock<Mutex<HashMap<String, DigestState>>> = OnceLock::new();
    S.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Check for a material change and, if any, push a single minimal-noise digest.
/// No-op when the digest is disabled or no ntfy channel is configured.
pub async fn maybe_push(portfolio: &PgPortfolio, ntfy: Option<&Ntfy>, cfg: &CopyTradingConfig) {
    if !cfg.honest_digest {
        return;
    }
    let Some(ntfy) = ntfy else { return };

    let rows = match portfolio
        .honest_pnl_by_strategy(
            cfg.exec_haircut,
            cfg.fee_pct,
            cfg.realized_decision_lag_secs,
        )
        .await
    {
        Ok(r) => r,
        Err(e) => {
            tracing::warn!(err = %e, "honest digest: scoreboard query failed");
            return;
        }
    };
    let segs = portfolio
        .honest_pnl_segments(cfg.exec_haircut, cfg.fee_pct)
        .await
        .unwrap_or_default();
    let verdicts = verdicts_by_strategy(&rows, &segs, &cfg_thresholds(cfg));

    // Snapshot each strategy's material state (GO + paper drawdown).
    let mut snaps: Vec<DigestSnapshot> = Vec::new();
    for (strategy, sv) in &verdicts {
        let max_drawdown = portfolio
            .ledger_stats(strategy, cfg.fee_pct)
            .await
            .ok()
            .flatten()
            .map(|l| l.max_drawdown)
            .unwrap_or(0.0);
        snaps.push(DigestSnapshot {
            strategy: strategy.clone(),
            go: sv.verdict.go,
            max_drawdown,
        });
    }

    // Compare to the remembered state, update it, and collect any change messages.
    let msgs = {
        let mut guard = state().lock().unwrap_or_else(|p| p.into_inner());
        let (msgs, next) = digest_changes(&guard, &snaps, cfg.honest_max_drawdown_usd);
        *guard = next;
        msgs
    };
    if msgs.is_empty() {
        return; // nothing changed — stay silent (the whole point)
    }
    let body = format!(
        "{}\n\nPaper track record — promotion to real money is a deliberate human call. NO real money.",
        msgs.join("\n")
    );
    ntfy.push(
        "📊 Honest tracker update",
        &body,
        4,
        &["chart_with_upwards_trend"],
    )
    .await;
    tracing::info!(
        changes = msgs.len(),
        "honest digest pushed (material change)"
    );
}

fn cfg_thresholds(cfg: &CopyTradingConfig) -> crate::scanner::honest::PilotThresholds {
    crate::scanner::honest::PilotThresholds {
        min_pilot_roi: cfg.min_pilot_roi,
        min_events: cfg.pilot_min_events,
        min_regimes: cfg.pilot_min_regimes,
        regime_frac: cfg.regime_frac,
        min_liquidity_usd: cfg.min_liquidity_usd,
        alpha: crate::scanner::promotion::PromotionParams::default().alpha,
    }
}
