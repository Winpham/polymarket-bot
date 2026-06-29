//! Enricher seam — silent, forward-tested cross-check arms.
//!
//! An *arm* looks at the cycle's already-scored signals and re-emits selected
//! `strict` picks cloned under a NEW strategy name (alerting = false). Those
//! tagged rows flow through the existing `to_new_signal → upsert_consensus_signal
//! → resolve → scoreboard → gate` path untouched, so the belief-blind promotion
//! gate judges every arm for free as forward data accrues — no arm is pre-judged.
//!
//! Each arm no-ops unless live.rs loaded its model/flag into [`EnrichModels`]
//! (default-OFF: a missing model file or disabled flag leaves the field
//! `None`/`false`). So with nothing enabled, `enrich_all` is a passthrough and the
//! live `strict` path + 14 core strategies are byte-identical.

use std::collections::HashMap;
use std::path::Path;

use chrono::{DateTime, Utc};

use crate::config::CopyTradingConfig;
use crate::scanner::consensus::{ConsensusSignal, Tier};
use polymarket_common::model::consensus_win::ConsensusWinModel;
use polymarket_common::model::features::MarketFeatures;
use polymarket_common::model::xgb::XgbModel;

pub mod bayes;
pub mod features;
pub mod market;
pub mod ml;

/// Loaded model handles + arm switches. A field stays `None`/`false` unless
/// live.rs both saw the arm's config flag ON and loaded its model file — so an
/// arm with no model (or a disabled flag) silently no-ops.
#[derive(Default)]
pub struct EnrichModels {
    /// Consensus-native logistic model (the `consensus_logit` arm).
    pub consensus_win: Option<ConsensusWinModel>,
    /// Consensus-native ensemble — pure-Rust XGBoost (the `consensus_ens` arm).
    pub consensus_ens: Option<XgbModel>,
    /// Shared resolution-time cutoff for BOTH consensus arms (from the logit JSON's
    /// `trained_through`). `None` → forward guard relies on structural forwardness.
    pub consensus_through: Option<DateTime<Utc>>,
    /// Imported market-outcome model (the `market_ml` / `market_veto` arms).
    pub market_xgb: Option<XgbModel>,
    /// Training cutoff for the imported market model (from config).
    pub market_through: Option<DateTime<Utc>>,
    /// Whether the Bayesian-anchor arm is enabled (it needs no model file).
    pub bayes_enabled: bool,
}

impl EnrichModels {
    /// True if any arm needs per-market data pre-fetched (CLOB mid for bayes;
    /// CLOB mid + Gamma + price history for the market model).
    pub fn needs_market_data(&self) -> bool {
        self.market_xgb.is_some() || self.bayes_enabled
    }

    /// True if an arm needs the full [`MarketFeatures`] (Gamma + price history),
    /// not just the CLOB mid.
    pub fn needs_market_features(&self) -> bool {
        self.market_xgb.is_some()
    }
}

/// Load the enabled arms' models from config. Each arm is gated by its flag AND
/// the presence/validity of its model file — a flag ON with a missing or invalid
/// file logs and leaves the arm a no-op (default-OFF, fail-silent).
pub fn load_models(cfg: &CopyTradingConfig) -> EnrichModels {
    let mut m = EnrichModels::default();

    if cfg.consensus_arm_logit {
        let p = Path::new(&cfg.consensus_win_model_path);
        if p.exists() {
            match ConsensusWinModel::load(p) {
                Ok(model) => {
                    m.consensus_through = Some(model.trained_through);
                    m.consensus_win = Some(model);
                    tracing::info!(path = %p.display(), "Loaded consensus_logit model");
                }
                Err(e) => tracing::warn!(err = %e, "consensus_logit model failed to load; arm off"),
            }
        } else {
            tracing::info!(path = %p.display(), "consensus_logit ON but model absent; arm no-ops");
        }
    }

    if cfg.consensus_arm_ens {
        let p = Path::new(&cfg.consensus_ens_model_path);
        if p.exists() {
            match XgbModel::load(p) {
                Ok(model) => {
                    m.consensus_ens = Some(model);
                    tracing::info!(path = %p.display(), "Loaded consensus_ens model");
                }
                Err(e) => tracing::warn!(err = %e, "consensus_ens model failed to load; arm off"),
            }
        } else {
            tracing::info!(path = %p.display(), "consensus_ens ON but model absent; arm no-ops");
        }
    }

    if cfg.consensus_arm_market {
        let p = Path::new(&cfg.market_model_path);
        if p.exists() {
            match XgbModel::load(p) {
                Ok(model) => {
                    m.market_xgb = Some(model);
                    tracing::info!(path = %p.display(), "Loaded market_ml model");
                }
                Err(e) => tracing::warn!(err = %e, "market_ml model failed to load; arm off"),
            }
        } else {
            tracing::info!(path = %p.display(), "market_ml ON but model absent; arm no-ops");
        }
        let through = cfg.market_ml_trained_through.trim();
        if !through.is_empty() {
            match DateTime::parse_from_rfc3339(through) {
                Ok(d) => m.market_through = Some(d.with_timezone(&Utc)),
                Err(e) => {
                    tracing::warn!(err = %e, value = through, "bad MARKET_ML_TRAINED_THROUGH; no guard")
                }
            }
        }
    }

    m.bayes_enabled = cfg.consensus_arm_bayes;
    m
}

/// Per-arm edge margin: surplus over the priced-in mid a pick must clear to be
/// re-emitted. Conservative defaults; wired to config in live.rs.
#[derive(Debug, Clone, Copy)]
pub struct EnrichMargins {
    /// Margin for the ML arms (`p_win − mean_price > ml`).
    pub ml: f64,
    /// Margin for the Bayesian-anchor arm (`posterior − mid > bayes`).
    pub bayes: f64,
}

impl Default for EnrichMargins {
    fn default() -> Self {
        Self {
            ml: 0.0,
            bayes: 0.0,
        }
    }
}

/// Pre-fetched per-market data for the market-dependent arms (built once per
/// cycle for the strict-fired markets, bounded + throttled).
pub struct MarketCtx {
    /// Live CLOB mid of the consensus outcome.
    pub clob_mid: f64,
    /// Full market feature vector (Gamma + price history); `None` if a fetch
    /// failed or features weren't needed this cycle.
    pub features: Option<MarketFeatures>,
}

/// Per-cycle context handed to every arm. An arm reads only what it needs.
pub struct EnrichCtx<'a> {
    /// The cycle's `now` (forward-only checks compare against `trained_through`).
    pub now: DateTime<Utc>,
    /// Loaded models + arm switches.
    pub models: &'a EnrichModels,
    /// Per-arm margins.
    pub margins: EnrichMargins,
    /// Pre-fetched market data keyed by `condition_id` (empty when no market-
    /// dependent arm is active).
    pub markets: &'a HashMap<String, MarketCtx>,
}

/// A pure enricher arm: given the cycle's scored signals + context, return the
/// NEW strategy-tagged signals to append. It must not mutate or drop the input.
pub type Enricher = fn(&[ConsensusSignal], &EnrichCtx) -> Vec<ConsensusSignal>;

/// The one merge list. Each arm no-ops unless its model/flag is present.
pub fn registry() -> &'static [Enricher] {
    &[
        ml::arm_consensus_logit,
        ml::arm_consensus_ens,
        market::arm_market,
        bayes::arm_bayes,
    ]
}

/// Run every registered arm and append their emitted signals to the originals.
/// The originals always pass through untouched — arms only ADD silent rows.
pub fn enrich_all(mut signals: Vec<ConsensusSignal>, ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    let mut extra = Vec::new();
    for arm in registry() {
        extra.extend(arm(&signals, ctx));
    }
    signals.extend(extra);
    signals
}

/// Clone a scored signal under a new strategy name as a silent (WATCH) row. Arms
/// use this so the only thing distinguishing an emitted pick is its `strategy`
/// tag — the gate then judges it on the same surplus footing as everything else.
pub fn re_emit(sig: &ConsensusSignal, strategy: &str) -> ConsensusSignal {
    let mut s = sig.clone();
    s.strategy = strategy.to_string();
    // Arms never alert; force WATCH so even an accidental alerting flag is inert.
    s.tier = Tier::Watch;
    s
}

/// Forward-only guard: the consensus's freshest backer fill must be at/after the
/// model's training cutoff. Conservative — it never lets a market that was active
/// (and may have resolved) during training into the arm's forward record. `None`
/// cutoff means rely on structural forwardness (live markets resolve in future).
pub fn forward_ok(
    sig: &ConsensusSignal,
    trained_through: Option<DateTime<Utc>>,
    now: DateTime<Utc>,
) -> bool {
    match trained_through {
        None => true,
        Some(cutoff) => {
            let freshest = now - chrono::Duration::minutes(sig.recency_mins);
            freshest >= cutoff
        }
    }
}

/// Strategy family for the Bonferroni split. Experimental arms are judged in
/// their own family so adding them never tightens the core portfolio's (incl.
/// live `strict`) promotion bar.
pub fn family(strategy: &str) -> &'static str {
    const EXPERIMENTAL: &[&str] = &[
        "consensus_ens",
        "consensus_logit",
        "market_ml",
        "market_veto",
        "bayes_anchor",
    ];
    if EXPERIMENTAL.contains(&strategy) {
        "experimental"
    } else {
        "core"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn family_splits_experimental_from_core() {
        assert_eq!(family("strict"), "core");
        assert_eq!(family("favorite_tail"), "core");
        assert_eq!(family("consensus_ens"), "experimental");
        assert_eq!(family("market_veto"), "experimental");
    }

    #[test]
    fn enrich_all_is_passthrough_when_nothing_enabled() {
        // Default models → every arm no-ops → signals returned unchanged.
        let models = EnrichModels::default();
        let markets = HashMap::new();
        let ctx = EnrichCtx {
            now: Utc::now(),
            models: &models,
            margins: EnrichMargins::default(),
            markets: &markets,
        };
        let out = enrich_all(Vec::new(), &ctx);
        assert!(out.is_empty());
        assert!(!models.needs_market_data());
    }
}
