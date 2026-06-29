//! Consensus feature extraction for the consensus-native arms.
//!
//! Builds the fixed-order feature vector from a scored [`ConsensusSignal`] — the
//! SAME columns already stored on the `consensus_signals` row, so inference needs
//! zero fetches. The order MUST match
//! [`polymarket_common::model::consensus_win::CONSENSUS_FEATURE_NAMES`] and the
//! Python trainer; a unit test pins the length to that contract.

use crate::scanner::consensus::ConsensusSignal;

/// Feature vector in `CONSENSUS_FEATURE_NAMES` order.
pub fn consensus_feature_vec(s: &ConsensusSignal) -> Vec<f64> {
    vec![
        s.mean_price,
        s.price_std,
        s.net_count as f64,
        s.net_quality,
        s.n_backers as f64,
        s.n_opposers as f64,
        (1.0 + s.total_usd.max(0.0)).ln(),
        s.recency_mins as f64,
        // 999 sentinel for "unranked" (mirrors the trainer's fillna).
        s.best_backer_rank.map(|r| r as f64).unwrap_or(999.0),
        if s.is_sports { 1.0 } else { 0.0 },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use polymarket_common::model::consensus_win::CONSENSUS_FEATURE_NAMES;

    fn sig() -> ConsensusSignal {
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
            tier: crate::scanner::consensus::Tier::Strong,
        }
    }

    #[test]
    fn vector_matches_contract_length() {
        assert_eq!(
            consensus_feature_vec(&sig()).len(),
            CONSENSUS_FEATURE_NAMES.len()
        );
    }

    #[test]
    fn unranked_uses_sentinel() {
        let mut s = sig();
        s.best_backer_rank = None;
        let v = consensus_feature_vec(&s);
        assert_eq!(v[8], 999.0);
    }
}
