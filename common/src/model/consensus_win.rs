//! Consensus-native logistic win model.
//!
//! Trained on our OWN consensus-signal features → `outcome_won` (see
//! `scripts/consensus_train.py`), this is the honest small-N choice: a logistic
//! regression on a RobustScaler-standardised feature vector — no trees, no
//! overfit at N≈tens, no sidecar. The pure-Rust [`super::xgb::XgbModel`] swaps in
//! behind the same `p_win` shape once N grows (the `consensus_ens` arm).
//!
//! Inference is leak-free by construction: the features are exactly the columns
//! already stored on each `consensus_signals` row, and `trained_through` lets the
//! caller enforce forward-only honesty.

use anyhow::{Context, Result, ensure};
use chrono::{DateTime, Utc};
use serde::Deserialize;
use std::path::Path;

/// Feature order shared by the consensus-native arms (logit + ensemble) and the
/// Python trainer. Rust inference and `consensus_train.py` MUST agree on this
/// order; `ConsensusWinModel::load` asserts the model's `feature_names` match.
pub const CONSENSUS_FEATURE_NAMES: &[&str] = &[
    "mean_price",
    "price_std",
    "net_count",
    "net_quality",
    "n_backers",
    "n_opposers",
    "ln_total_usd",
    "recency_mins",
    "best_backer_rank",
    "is_sports",
];

/// A RobustScaler + logistic model over [`CONSENSUS_FEATURE_NAMES`], loaded from
/// a small JSON exported by the trainer.
#[derive(Debug, Clone, Deserialize)]
pub struct ConsensusWinModel {
    /// Feature names, in order — must equal [`CONSENSUS_FEATURE_NAMES`].
    pub feature_names: Vec<String>,
    /// RobustScaler center (median) per feature.
    pub center: Vec<f64>,
    /// RobustScaler scale (IQR) per feature.
    pub scale: Vec<f64>,
    /// Logistic coefficients (applied to the scaled features).
    pub weights: Vec<f64>,
    /// Logistic intercept.
    pub bias: f64,
    /// Resolution-time cutoff of the training data (forward-only honesty).
    pub trained_through: DateTime<Utc>,
}

impl ConsensusWinModel {
    /// Load + validate the model JSON. Errors if the feature order or dimensions
    /// don't match the shared contract (a mismatched model is never silently used).
    pub fn load(path: &Path) -> Result<Self> {
        let data = std::fs::read_to_string(path)
            .with_context(|| format!("reading consensus_win model from {}", path.display()))?;
        let m: Self = serde_json::from_str(&data).context("parsing consensus_win JSON")?;
        ensure!(
            m.feature_names
                .iter()
                .map(String::as_str)
                .eq(CONSENSUS_FEATURE_NAMES.iter().copied()),
            "consensus_win feature_names mismatch (got {:?})",
            m.feature_names
        );
        let n = CONSENSUS_FEATURE_NAMES.len();
        ensure!(
            m.center.len() == n && m.scale.len() == n && m.weights.len() == n,
            "consensus_win dimension mismatch: center {}, scale {}, weights {}, expected {}",
            m.center.len(),
            m.scale.len(),
            m.weights.len(),
            n
        );
        Ok(m)
    }

    /// P(outcome wins) from a fixed-order feature vector: RobustScaler then a
    /// logistic sigmoid. Missing trailing features are treated as 0 (post-scale).
    pub fn p_win(&self, features: &[f64]) -> f64 {
        let mut z = self.bias;
        for i in 0..self.weights.len() {
            let v = features.get(i).copied().unwrap_or(0.0);
            let c = self.center.get(i).copied().unwrap_or(0.0);
            let s = self.scale.get(i).copied().unwrap_or(1.0);
            let scaled = if s == 0.0 { 0.0 } else { (v - c) / s };
            z += self.weights[i] * scaled;
        }
        1.0 / (1.0 + (-z).exp())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn model() -> ConsensusWinModel {
        // 10 features; only net_count (idx 2) has weight → monotone in net_count.
        let n = CONSENSUS_FEATURE_NAMES.len();
        ConsensusWinModel {
            feature_names: CONSENSUS_FEATURE_NAMES
                .iter()
                .map(|s| s.to_string())
                .collect(),
            center: vec![0.0; n],
            scale: vec![1.0; n],
            weights: {
                let mut w = vec![0.0; n];
                w[2] = 1.0; // net_count
                w
            },
            bias: 0.0,
            trained_through: DateTime::parse_from_rfc3339("2026-01-01T00:00:00Z")
                .unwrap()
                .with_timezone(&Utc),
        }
    }

    #[test]
    fn sigmoid_centered_at_zero() {
        let m = model();
        let mut f = vec![0.0; CONSENSUS_FEATURE_NAMES.len()];
        f[2] = 0.0;
        assert!((m.p_win(&f) - 0.5).abs() < 1e-9);
    }

    #[test]
    fn monotone_in_weighted_feature() {
        let m = model();
        let mut lo = vec![0.0; CONSENSUS_FEATURE_NAMES.len()];
        let mut hi = vec![0.0; CONSENSUS_FEATURE_NAMES.len()];
        lo[2] = -2.0;
        hi[2] = 3.0;
        assert!(m.p_win(&hi) > m.p_win(&lo));
        assert!(m.p_win(&hi) > 0.9);
        assert!(m.p_win(&lo) < 0.2);
    }

    #[test]
    fn zero_scale_is_safe() {
        let mut m = model();
        m.scale[2] = 0.0; // degenerate feature → contributes 0, no NaN/inf
        let mut f = vec![0.0; CONSENSUS_FEATURE_NAMES.len()];
        f[2] = 5.0;
        let p = m.p_win(&f);
        assert!((0.0..=1.0).contains(&p));
        assert!((p - 0.5).abs() < 1e-9);
    }
}
