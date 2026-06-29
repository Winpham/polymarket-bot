//! Consensus-native ML arms: a logistic baseline (`consensus_logit`) and a
//! pure-Rust XGBoost ensemble (`consensus_ens`), both trained on our OWN consensus
//! signal features → `outcome_won`. Each keeps the `strict` picks where the
//! model's win probability beats the entry price by a margin, re-emitting them
//! under its strategy tag for the belief-blind gate to judge. Zero fetches.

use super::features::consensus_feature_vec;
use super::{ConsensusSignal, EnrichCtx, forward_ok, re_emit};

/// `consensus_logit`: keep strict picks where `p_win − mean_price > margin`.
pub fn arm_consensus_logit(sigs: &[ConsensusSignal], ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    let Some(model) = &ctx.models.consensus_win else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for s in sigs {
        if s.strategy != "strict" {
            continue;
        }
        if !forward_ok(s, ctx.models.consensus_through, ctx.now) {
            continue;
        }
        let p = model.p_win(&consensus_feature_vec(s));
        if p - s.mean_price > ctx.margins.ml {
            out.push(re_emit(s, "consensus_logit"));
        }
    }
    out
}

/// `consensus_ens`: same selection but with the pure-Rust XGBoost ensemble.
pub fn arm_consensus_ens(sigs: &[ConsensusSignal], ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    let Some(model) = &ctx.models.consensus_ens else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for s in sigs {
        if s.strategy != "strict" {
            continue;
        }
        if !forward_ok(s, ctx.models.consensus_through, ctx.now) {
            continue;
        }
        let p = model.predict_prob(&consensus_feature_vec(s));
        if p - s.mean_price > ctx.margins.ml {
            out.push(re_emit(s, "consensus_ens"));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scanner::consensus::Tier;
    use crate::scanner::enrich::{EnrichMargins, EnrichModels, MarketCtx};
    use chrono::Utc;
    use polymarket_common::model::consensus_win::{CONSENSUS_FEATURE_NAMES, ConsensusWinModel};
    use std::collections::HashMap;

    fn strict_sig() -> ConsensusSignal {
        ConsensusSignal {
            strategy: "strict".into(),
            condition_id: "0xc".into(),
            outcome_index: 0,
            outcome_label: "Yes".into(),
            title: "t".into(),
            slug: "s".into(),
            event_slug: None,
            is_sports: false,
            backers: vec![],
            n_backers: 4,
            n_opposers: 0,
            net_count: 4,
            net_quality: 5.0,
            mean_price: 0.5,
            price_std: 0.02,
            recency_mins: 10,
            total_usd: 3000.0,
            best_backer_rank: Some(5),
            score: 1.0,
            tier: Tier::Strong,
        }
    }

    /// All-zero-weight logistic with the given bias → constant p_win = sigmoid(bias).
    fn const_model(bias: f64) -> ConsensusWinModel {
        let n = CONSENSUS_FEATURE_NAMES.len();
        ConsensusWinModel {
            feature_names: CONSENSUS_FEATURE_NAMES
                .iter()
                .map(|s| s.to_string())
                .collect(),
            center: vec![0.0; n],
            scale: vec![1.0; n],
            weights: vec![0.0; n],
            bias,
            trained_through: Utc::now() - chrono::Duration::days(365),
        }
    }

    fn ctx<'a>(models: &'a EnrichModels, markets: &'a HashMap<String, MarketCtx>) -> EnrichCtx<'a> {
        EnrichCtx {
            now: Utc::now(),
            models,
            margins: EnrichMargins {
                ml: 0.0,
                bayes: 0.0,
            },
            markets,
        }
    }

    #[test]
    fn logit_emits_silent_row_when_pwin_beats_price() {
        let models = EnrichModels {
            consensus_win: Some(const_model(5.0)), // p_win ≈ 0.993 > 0.5
            ..Default::default()
        };
        let markets = HashMap::new();
        let out = arm_consensus_logit(&[strict_sig()], &ctx(&models, &markets));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].strategy, "consensus_logit");
        assert_eq!(out[0].tier, Tier::Watch, "arms must be silent");
        // The pick itself (price/outcome) is unchanged — only the tag differs.
        assert_eq!(out[0].mean_price, 0.5);
        assert_eq!(out[0].condition_id, "0xc");
    }

    #[test]
    fn logit_skips_when_pwin_below_price() {
        let models = EnrichModels {
            consensus_win: Some(const_model(-5.0)), // p_win ≈ 0.007 < 0.5
            ..Default::default()
        };
        let markets = HashMap::new();
        assert!(arm_consensus_logit(&[strict_sig()], &ctx(&models, &markets)).is_empty());
    }

    #[test]
    fn logit_noops_without_model_or_on_non_strict() {
        let markets = HashMap::new();
        // No model → no-op.
        let none = EnrichModels::default();
        assert!(arm_consensus_logit(&[strict_sig()], &ctx(&none, &markets)).is_empty());
        // Model present but only strict picks are considered.
        let models = EnrichModels {
            consensus_win: Some(const_model(5.0)),
            ..Default::default()
        };
        let mut loose = strict_sig();
        loose.strategy = "loose".into();
        assert!(arm_consensus_logit(&[loose], &ctx(&models, &markets)).is_empty());
    }

    #[test]
    fn forward_guard_skips_stale_consensus() {
        // Model trained "through" the future → a fill 10 min ago is pre-cutoff → skip.
        let models = EnrichModels {
            consensus_win: Some(const_model(5.0)),
            consensus_through: Some(Utc::now() + chrono::Duration::days(1)),
            ..Default::default()
        };
        let markets = HashMap::new();
        assert!(arm_consensus_logit(&[strict_sig()], &ctx(&models, &markets)).is_empty());
    }
}
