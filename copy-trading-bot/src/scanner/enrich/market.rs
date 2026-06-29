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
        let p_model = model.predict_prob(&feat.to_vec());
        let edge = p_model - mc.clob_mid;
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
