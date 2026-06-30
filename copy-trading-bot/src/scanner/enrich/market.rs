//! Imported market-model arms: `market_ml` (the model CONFIRMS the consensus
//! outcome is underpriced) and `market_veto` (the model STRONGLY disagrees with
//! the consensus BUY). This is the trading-bot's own market-outcome XGBoost given
//! a full fair shot on the consensus path — a documented Foresight null elsewhere,
//! but the belief-blind gate (not our prior) decides its surplus here.
//!
//! Features come from [`super::MarketCtx`], pre-fetched once per strict-fired
//! market in `consensus_cycle` (1 Gamma + 1 CLOB mid + 1 price-history fetch,
//! deduped + throttled). An arm row never emits if that fetch was unavailable.

use super::{ConsensusSignal, EnrichCtx, forward_ok, re_emit};

/// `market_ml` (confirm) + `market_veto` (strong disagree). The imported model
/// predicts P(consensus outcome) from market features; we compare to the live
/// CLOB mid: a positive edge confirms, a negative edge vetoes.
pub fn arm_market(sigs: &[ConsensusSignal], ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    let Some(model) = &ctx.models.market_xgb else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for s in sigs {
        if s.strategy != "strict" {
            continue;
        }
        if !forward_ok(s, ctx.models.market_through, ctx.now) {
            continue;
        }
        let Some(mc) = ctx.markets.get(&s.condition_id) else {
            continue; // mid/features unavailable this cycle
        };
        let Some(feat) = &mc.features else {
            continue;
        };
        // Features are YES-oriented (always the index-0 token); convert the
        // model's `p_yes` to the consensus outcome's probability before comparing
        // to the consensus-outcome mid. A NO-side consensus pick is `1 - p_yes`.
        let p_yes = model.predict_prob(&feat.to_vec());
        let p_cons = if mc.outcome_index == 0 {
            p_yes
        } else {
            1.0 - p_yes
        };
        let edge = p_cons - mc.clob_mid;
        if edge > ctx.margins.ml {
            // Model agrees the consensus outcome is underpriced.
            out.push(re_emit(s, "market_ml"));
        } else if edge < -ctx.margins.ml {
            // Model strongly disagrees with the consensus BUY (overpriced).
            out.push(re_emit(s, "market_veto"));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scanner::consensus::Tier;
    use crate::scanner::enrich::{EnrichCtx, EnrichMargins, EnrichModels, MarketCtx};
    use polymarket_common::model::features::MarketFeatures;
    use polymarket_common::model::xgb::XgbModel;
    use std::collections::HashMap;

    /// A constant XgbModel: one single-leaf tree whose leaf value = `logit(p)` over
    /// base_score 0.5, so `predict_prob` returns `p` for ANY feature vector. Lets us
    /// test orientation independently of what the model learned.
    fn const_model(p: f64) -> XgbModel {
        let leaf = (p / (1.0 - p)).ln();
        let json = format!(
            "{{\"learner\":{{\"learner_model_param\":{{\"base_score\":\"0.5\"}},\
             \"gradient_booster\":{{\"model\":{{\"trees\":[{{\
             \"split_indices\":[0],\"split_conditions\":[{leaf}],\
             \"left_children\":[-1],\"right_children\":[-1],\"default_left\":[0]}}]}}}}}}}}"
        );
        let path = std::env::temp_dir().join(format!(
            "market_resid_const_model_{}.json",
            (p * 1e9) as i64
        ));
        std::fs::write(&path, json).unwrap();
        XgbModel::load(&path).unwrap()
    }

    fn zero_features() -> MarketFeatures {
        MarketFeatures {
            yes_price: 0.0,
            momentum_1h: 0.0,
            momentum_24h: 0.0,
            volatility_24h: 0.0,
            rsi: 0.0,
            log_volume: 0.0,
            days_to_expiry: 0.0,
            is_crypto: 0.0,
            price_change_1d: 0.0,
            price_change_1w: 0.0,
            days_since_created: 0.0,
            created_to_expiry_span: 0.0,
            is_sports: 0.0,
            q_length: 0.0,
            q_word_count: 0.0,
            q_avg_word_len: 0.0,
            q_word_diversity: 0.0,
            q_has_number: 0.0,
            q_has_year: 0.0,
            q_has_percent: 0.0,
            q_has_dollar: 0.0,
            q_has_date: 0.0,
            q_starts_will: 0.0,
            q_has_by: 0.0,
            q_has_before: 0.0,
            q_has_above: 0.0,
            q_sentiment_pos: 0.0,
            q_sentiment_neg: 0.0,
            q_certainty: 0.0,
        }
    }

    fn strict_sig(outcome_index: i32) -> ConsensusSignal {
        ConsensusSignal {
            strategy: "strict".into(),
            condition_id: "0xorient".into(),
            outcome_index,
            outcome_label: if outcome_index == 0 { "Yes" } else { "No" }.into(),
            title: "t".into(),
            slug: "s".into(),
            event_slug: Some("ev".into()),
            is_sports: false,
            backers: vec![],
            n_backers: 6,
            n_opposers: 0,
            net_count: 6,
            net_quality: 9.0,
            mean_price: 0.5,
            price_std: 0.02,
            recency_mins: 10,
            total_usd: 4000.0,
            best_backer_rank: Some(4),
            score: 1.0,
            tier: Tier::Elite,
        }
    }

    /// With a constant `p_yes = 0.8` and a consensus-outcome mid of 0.5, the YES
    /// pick (outcome_index 0) sees edge `+0.3` ⇒ `market_ml`, while the otherwise
    /// identical NO pick (outcome_index 1) must orient to `p_cons = 1 − 0.8 = 0.2`
    /// ⇒ edge `−0.3` ⇒ `market_veto`. A non-oriented arm would emit `market_ml`
    /// for BOTH (scoring the NO side against YES-token features — the GAP-3 bug).
    #[test]
    fn arm_market_orients_no_side() {
        let model = const_model(0.8);
        let models = EnrichModels {
            market_xgb: Some(model),
            ..Default::default()
        };
        let mk = |oi: i32| {
            let mut markets = HashMap::new();
            markets.insert(
                "0xorient".to_string(),
                MarketCtx {
                    clob_mid: 0.5,
                    features: Some(zero_features()),
                    outcome_index: oi,
                },
            );
            markets
        };

        // YES side: p_cons = 0.8, edge = +0.3 > 0 ⇒ market_ml.
        let markets_yes = mk(0);
        let ctx_yes = EnrichCtx {
            now: chrono::Utc::now(),
            models: &models,
            margins: EnrichMargins::default(),
            markets: &markets_yes,
        };
        let out_yes = arm_market(&[strict_sig(0)], &ctx_yes);
        assert_eq!(out_yes.len(), 1);
        assert_eq!(out_yes[0].strategy, "market_ml", "YES side underpriced");

        // NO side: p_cons = 1 - 0.8 = 0.2, edge = -0.3 < 0 ⇒ market_veto.
        let markets_no = mk(1);
        let ctx_no = EnrichCtx {
            now: chrono::Utc::now(),
            models: &models,
            margins: EnrichMargins::default(),
            markets: &markets_no,
        };
        let out_no = arm_market(&[strict_sig(1)], &ctx_no);
        assert_eq!(out_no.len(), 1);
        assert_eq!(
            out_no[0].strategy, "market_veto",
            "NO side oriented to 1 - p_yes"
        );
    }
}
