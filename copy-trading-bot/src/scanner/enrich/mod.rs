//! Enricher seam — silent, forward-tested cross-check arms.
//!
//! An *arm* looks at the cycle's already-scored signals and re-emits selected
//! picks cloned under a NEW strategy name (alerting = false). Those tagged rows
//! flow through the existing `to_new_signal → upsert_consensus_signal → resolve →
//! scoreboard → gate` path untouched, so the belief-blind promotion gate judges
//! every arm for free as forward data accrues — no arm is pre-judged here.
//!
//! Phase 3 lands the seam itself (one merge point in `consensus_cycle`, an empty
//! registry, and the Bonferroni `family` split). Phase 4 registers the actual
//! arms and populates [`EnrichCtx`]'s models. The `#![allow(dead_code)]` covers
//! the context fields the arms will read in Phase 4; it is removed once they do.
#![allow(dead_code)]

use chrono::{DateTime, Utc};

use crate::scanner::consensus::{ConsensusSignal, Tier};

/// Loaded model handles for the arms. Every handle is optional, so an arm whose
/// model file is absent simply no-ops (default-OFF). Phase 4 adds the fields
/// (consensus logistic, consensus ensemble, imported market XGBoost, …).
#[derive(Default)]
pub struct EnrichModels {}

/// Per-arm edge margin: surplus over the priced-in mid a pick must clear to be
/// re-emitted. Conservative defaults; wired to config per-arm in Phase 4.
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

/// Per-cycle context handed to every arm. An arm reads only what it needs and
/// no-ops when that input is absent.
pub struct EnrichCtx<'a> {
    /// The cycle's `now` (forward-only checks compare against `trained_through`).
    pub now: DateTime<Utc>,
    /// Loaded models (all optional).
    pub models: &'a EnrichModels,
    /// Per-arm margins.
    pub margins: EnrichMargins,
}

/// A pure enricher arm: given the cycle's scored signals + context, return the
/// NEW strategy-tagged signals to append. It must not mutate or drop the input.
pub type Enricher = fn(&[ConsensusSignal], &EnrichCtx) -> Vec<ConsensusSignal>;

/// The one merge list. Phase 4 registers the arms here.
pub fn registry() -> &'static [Enricher] {
    &[]
}

/// Run every registered arm and append their emitted signals to the originals.
/// The originals always pass through untouched — the live `strict` path and the
/// 14 core strategies are non-regressive; arms only ADD silent rows.
pub fn enrich_all(mut signals: Vec<ConsensusSignal>, ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    let mut extra = Vec::new();
    for arm in registry() {
        extra.extend(arm(&signals, ctx));
    }
    signals.extend(extra);
    signals
}

/// Clone a scored signal under a new strategy name as a silent (WATCH) row. Arms
/// use this so the only thing that distinguishes an emitted pick is its
/// `strategy` tag — the gate then judges it on the same surplus footing.
pub fn re_emit(sig: &ConsensusSignal, strategy: &str) -> ConsensusSignal {
    let mut s = sig.clone();
    s.strategy = strategy.to_string();
    // Arms never alert; force WATCH so even an accidental alerting flag is inert.
    s.tier = Tier::Watch;
    s
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
    fn enrich_all_is_passthrough_with_empty_registry() {
        // No arms registered → signals returned unchanged (non-regressive).
        let models = EnrichModels::default();
        let ctx = EnrichCtx {
            now: Utc::now(),
            models: &models,
            margins: EnrichMargins::default(),
        };
        let out = enrich_all(Vec::new(), &ctx);
        assert!(out.is_empty());
    }
}
