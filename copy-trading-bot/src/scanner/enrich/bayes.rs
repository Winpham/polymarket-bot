//! Bayesian-anchor arm (`bayes_anchor`). Prior = the live CLOB mid (it encodes
//! all public info); evidence = the consensus conviction as a likelihood ratio
//! (plus the consensus-logit LR when that model is loaded), composed via the
//! moved `bayesian_update`. Emits when the posterior beats the mid by a margin.
//! Needs no model file — only a live CLOB mid (pre-fetched in `MarketCtx`).

use super::features::consensus_feature_vec;
use super::{ConsensusSignal, EnrichCtx, re_emit};
use polymarket_common::model::bayesian::{self, AgentAssessment};

/// Map consensus conviction (net trader count) to a likelihood ratio favoring the
/// consensus outcome; bounded so a big net can't blow up the posterior.
fn consensus_lr(net_count: i64) -> f64 {
    (1.0 + 0.15 * net_count.max(0) as f64).min(8.0)
}

pub fn arm_bayes(sigs: &[ConsensusSignal], ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    if !ctx.models.bayes_enabled {
        return Vec::new();
    }
    let mut out = Vec::new();
    for s in sigs {
        if s.strategy != "strict" {
            continue;
        }
        let Some(mc) = ctx.markets.get(&s.condition_id) else {
            continue;
        };
        let prior = mc.clob_mid;
        if !(prior > 0.0 && prior < 1.0) {
            continue;
        }

        let mut assessments = vec![AgentAssessment {
            role: "consensus".into(),
            likelihood_ratio: consensus_lr(s.net_count),
            // Tighter backer entries → more confident in the conviction LR.
            confidence: (1.0 - (s.price_std / 0.10).clamp(0.0, 1.0)).clamp(0.1, 1.0),
            reasoning: String::new(),
        }];

        // Optional ML evidence: turn the consensus-logit probability into an LR
        // against the mid prior (same idiom the trading bot uses).
        if let Some(model) = &ctx.models.consensus_win {
            let p = model.p_win(&consensus_feature_vec(s)).clamp(0.001, 0.999);
            let ml_lr = bayesian::prob_to_odds(p) / bayesian::prob_to_odds(prior);
            assessments.push(AgentAssessment {
                role: "ml".into(),
                likelihood_ratio: ml_lr,
                confidence: 0.5,
                reasoning: String::new(),
            });
        }

        let est = bayesian::bayesian_update(prior, &assessments);
        if est.posterior - prior > ctx.margins.bayes {
            out.push(re_emit(s, "bayes_anchor"));
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
    fn lr_is_monotone_and_bounded() {
        assert!((consensus_lr(0) - 1.0).abs() < 1e-9);
        assert!(consensus_lr(4) > consensus_lr(0));
        assert!(consensus_lr(1000) <= 8.0, "LR is capped");
    }

    #[test]
    fn emits_when_conviction_lifts_posterior_above_mid() {
        let models = EnrichModels {
            bayes_enabled: true,
            ..Default::default()
        };
        let mut markets = HashMap::new();
        markets.insert(
            "0xc".into(),
            MarketCtx {
                clob_mid: 0.5,
                features: None,
            },
        );
        // net 4 → LR 1.6 → posterior > 0.5 mid → emit a silent bayes_anchor row.
        let out = arm_bayes(&[strict_sig()], &ctx(&models, &markets));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].strategy, "bayes_anchor");
        assert_eq!(out[0].tier, Tier::Watch);
    }

    #[test]
    fn noops_when_disabled_or_no_mid() {
        // Disabled.
        let off = EnrichModels::default();
        let mut markets = HashMap::new();
        markets.insert(
            "0xc".into(),
            MarketCtx {
                clob_mid: 0.5,
                features: None,
            },
        );
        assert!(arm_bayes(&[strict_sig()], &ctx(&off, &markets)).is_empty());
        // Enabled but no pre-fetched mid for the market → no-op.
        let on = EnrichModels {
            bayes_enabled: true,
            ..Default::default()
        };
        let empty = HashMap::new();
        assert!(arm_bayes(&[strict_sig()], &ctx(&on, &empty)).is_empty());
    }
}
