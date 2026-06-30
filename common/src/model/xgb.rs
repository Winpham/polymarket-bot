#![allow(dead_code)]

use anyhow::{Context, Result};
use serde::Deserialize;
use std::path::Path;

/// Pure-Rust XGBoost inference from exported JSON model.
/// Traverses decision trees without any native XGBoost dependency.
#[derive(Debug)]
pub struct XgbModel {
    trees: Vec<Tree>,
    base_score: f64,
    scaler: Option<Scaler>,
}

#[derive(Debug)]
struct Tree {
    nodes: Vec<Node>,
}

#[derive(Debug)]
enum Node {
    Split {
        feature_idx: usize,
        threshold: f64,
        yes: usize,
        no: usize,
        missing: usize,
    },
    Leaf {
        value: f64,
    },
}

#[derive(Debug, Clone, Deserialize)]
pub struct Scaler {
    pub center: Vec<f64>,
    pub scale: Vec<f64>,
    pub feature_names: Vec<String>,
}

impl Scaler {
    pub fn load(path: &Path) -> Result<Self> {
        let data = std::fs::read_to_string(path)
            .with_context(|| format!("reading scaler from {}", path.display()))?;
        serde_json::from_str(&data).context("parsing scaler JSON")
    }

    pub fn transform(&self, features: &[f64]) -> Vec<f64> {
        features
            .iter()
            .enumerate()
            .map(|(i, &v)| {
                let center = self.center.get(i).copied().unwrap_or(0.0);
                let scale = self.scale.get(i).copied().unwrap_or(1.0);
                if scale == 0.0 {
                    0.0
                } else {
                    (v - center) / scale
                }
            })
            .collect()
    }
}

impl XgbModel {
    /// Load model from XGBoost's JSON export format.
    /// Optionally loads a companion scaler file (same path with .scaler.json suffix).
    pub fn load(model_path: &Path) -> Result<Self> {
        let data = std::fs::read_to_string(model_path)
            .with_context(|| format!("reading model from {}", model_path.display()))?;
        let raw: RawModel = serde_json::from_str(&data).context("parsing XGBoost JSON")?;

        let base_score = raw
            .learner
            .learner_model_param
            .base_score
            .parse::<f64>()
            .unwrap_or(0.5);

        let mut trees = Vec::new();
        for raw_tree in &raw.learner.gradient_booster.model.trees {
            trees.push(parse_tree(raw_tree)?);
        }

        // Try loading scaler
        let scaler_path = model_path.with_extension("scaler.json");
        let scaler = if scaler_path.exists() {
            Some(Scaler::load(&scaler_path)?)
        } else {
            None
        };

        tracing::info!(
            n_trees = trees.len(),
            base_score,
            has_scaler = scaler.is_some(),
            "Loaded XGBoost model"
        );

        Ok(Self {
            trees,
            base_score,
            scaler,
        })
    }

    /// Predict probability of YES outcome.
    pub fn predict_prob(&self, features: &[f64]) -> f64 {
        let scaled = match &self.scaler {
            Some(s) => s.transform(features),
            None => features.to_vec(),
        };

        let raw: f64 = self.trees.iter().map(|t| t.predict(&scaled)).sum();
        sigmoid(raw + logit(self.base_score))
    }

    pub fn n_trees(&self) -> usize {
        self.trees.len()
    }
}

impl Tree {
    fn predict(&self, features: &[f64]) -> f64 {
        let mut node_idx = 0;
        loop {
            match &self.nodes[node_idx] {
                Node::Leaf { value } => return *value,
                Node::Split {
                    feature_idx,
                    threshold,
                    yes,
                    no,
                    missing,
                } => {
                    let val = features.get(*feature_idx).copied();
                    node_idx = match val {
                        None => *missing,
                        Some(v) if v.is_nan() => *missing,
                        Some(v) if v < *threshold => *yes,
                        Some(_) => *no,
                    };
                }
            }
        }
    }
}

fn sigmoid(x: f64) -> f64 {
    1.0 / (1.0 + (-x).exp())
}

fn logit(p: f64) -> f64 {
    let p = p.clamp(1e-7, 1.0 - 1e-7);
    (p / (1.0 - p)).ln()
}

/// Companion calibration + band-baseline extras for the price-free `market_resid`
/// arm, loaded from a `<model>.resid.json` sidecar. Kept entirely separate from
/// [`XgbModel`] so the booster artifact stays untouched; the Python trainer bakes
/// every field and the Rust side only looks up + interpolates.
#[derive(Debug, Clone, Deserialize)]
pub struct ResidExtras {
    /// `_blind` base rate `P(won)` per Postgres `width_bucket(p,0,1,5)` band 1..=5.
    pub band_rates: [f64; 5],
    /// Fallback base rate when a band is empty / the price is out of range.
    pub global_rate: f64,
    /// Isotonic calibration thresholds (ascending), paired with `iso_y`.
    pub iso_x: Vec<f64>,
    /// Isotonic calibrated outputs (ascending), paired with `iso_x`.
    pub iso_y: Vec<f64>,
}

impl ResidExtras {
    /// Load from the `<model>.resid.json` sidecar.
    pub fn load(path: &Path) -> Result<Self> {
        let data = std::fs::read_to_string(path)
            .with_context(|| format!("reading resid extras from {}", path.display()))?;
        serde_json::from_str(&data).context("parsing resid extras JSON")
    }

    /// The `_blind` base rate for the band containing `p`. The gate keys its blind
    /// baseline off `width_bucket(mean_price,0,1,5)`, so the arm compares against
    /// the SAME band's base rate (not the live mid). Out-of-range ⇒ `global_rate`.
    pub fn band_rate(&self, p: f64) -> f64 {
        let b = pg_width_bucket5(p);
        if (1..=5).contains(&b) {
            self.band_rates[(b - 1) as usize]
        } else {
            self.global_rate
        }
    }

    /// Piecewise-linear isotonic interpolation of the calibrated probability for a
    /// raw model output `p`. Identity when fewer than two knots are baked (or the
    /// arrays are mismatched). Clamps to the fitted knot range — isotonic is only
    /// defined on its support, and the endpoints are its extreme calibrated values.
    pub fn apply_iso(&self, p: f64) -> f64 {
        let n = self.iso_x.len();
        if n < 2 || self.iso_y.len() != n {
            return p;
        }
        if p <= self.iso_x[0] {
            return self.iso_y[0];
        }
        if p >= self.iso_x[n - 1] {
            return self.iso_y[n - 1];
        }
        // First knot strictly above `p` (in 1..n, since p < iso_x[n-1]).
        let hi = self.iso_x.partition_point(|&x| x <= p);
        let lo = hi - 1;
        let (x0, x1) = (self.iso_x[lo], self.iso_x[hi]);
        let (y0, y1) = (self.iso_y[lo], self.iso_y[hi]);
        if x1 <= x0 {
            return y0;
        }
        y0 + (y1 - y0) * (p - x0) / (x1 - x0)
    }
}

/// Mirror Postgres `width_bucket(p, 0.0, 1.0, 5)`: `p < 0 → 0`, `p >= 1 → 6`, else
/// `floor(p*5) + 1`. The consensus scoreboard buckets `mean_price` with exactly
/// this call, so the arm must too (verified against Postgres in `width_bucket_parity`).
pub fn pg_width_bucket5(p: f64) -> i32 {
    if p < 0.0 {
        0
    } else if p >= 1.0 {
        6
    } else {
        (p * 5.0).floor() as i32 + 1
    }
}

// ---- JSON parsing for XGBoost's native export format ----

#[derive(Deserialize)]
struct RawModel {
    learner: RawLearner,
}

#[derive(Deserialize)]
struct RawLearner {
    learner_model_param: RawModelParam,
    gradient_booster: RawBooster,
}

#[derive(Deserialize)]
struct RawModelParam {
    base_score: String,
}

#[derive(Deserialize)]
struct RawBooster {
    model: RawGBTree,
}

#[derive(Deserialize)]
struct RawGBTree {
    trees: Vec<RawTree>,
}

#[derive(Deserialize)]
struct RawTree {
    split_indices: Vec<usize>,
    split_conditions: Vec<f64>,
    left_children: Vec<i64>,
    right_children: Vec<i64>,
    default_left: Vec<u8>,
}

fn parse_tree(raw: &RawTree) -> Result<Tree> {
    let n = raw.split_indices.len();
    let mut nodes = Vec::with_capacity(n);

    for i in 0..n {
        let left = raw.left_children[i];
        let right = raw.right_children[i];

        if left == -1 && right == -1 {
            // Leaf node — split_conditions holds the leaf value
            nodes.push(Node::Leaf {
                value: raw.split_conditions[i],
            });
        } else {
            let yes = left as usize;
            let no = right as usize;
            let missing = if raw.default_left.get(i).copied().unwrap_or(0) == 1 {
                yes
            } else {
                no
            };
            nodes.push(Node::Split {
                feature_idx: raw.split_indices[i],
                threshold: raw.split_conditions[i],
                yes,
                no,
                missing,
            });
        }
    }

    Ok(Tree { nodes })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sigmoid() {
        assert!((sigmoid(0.0) - 0.5).abs() < 1e-10);
        assert!(sigmoid(10.0) > 0.99);
        assert!(sigmoid(-10.0) < 0.01);
    }

    #[test]
    fn test_logit_roundtrip() {
        for p in [0.1, 0.3, 0.5, 0.7, 0.9] {
            let roundtrip = sigmoid(logit(p));
            assert!(
                (roundtrip - p).abs() < 1e-10,
                "logit/sigmoid roundtrip failed for {p}"
            );
        }
    }

    #[test]
    fn test_scaler_transform() {
        let scaler = Scaler {
            center: vec![10.0, 20.0],
            scale: vec![2.0, 5.0],
            feature_names: vec!["a".into(), "b".into()],
        };
        let result = scaler.transform(&[12.0, 30.0]);
        assert!((result[0] - 1.0).abs() < 1e-10); // (12-10)/2 = 1
        assert!((result[1] - 2.0).abs() < 1e-10); // (30-20)/5 = 2
    }

    #[test]
    fn test_scaler_zero_scale() {
        let scaler = Scaler {
            center: vec![5.0],
            scale: vec![0.0],
            feature_names: vec!["a".into()],
        };
        let result = scaler.transform(&[10.0]);
        assert!((result[0]).abs() < 1e-10); // Should return 0 for zero scale
    }

    #[test]
    fn test_load_real_model() {
        let model_path = std::path::Path::new("model/xgb_model.json");
        if !model_path.exists() {
            eprintln!(
                "Skipping: model/xgb_model.json not found (run scripts/train_model.py first)"
            );
            return;
        }
        let model = XgbModel::load(model_path).expect("Failed to load model");
        assert!(model.n_trees() > 0, "Model should have trees");

        // Test prediction with a typical market feature vector matching MarketFeatures::NAMES:
        // [yes_price, momentum_1h, momentum_24h, volatility_24h, rsi,
        //  log_volume, days_to_expiry, is_crypto,
        //  price_change_1d, price_change_1w, days_since_created, created_to_expiry_span]
        let features = vec![
            0.55, 0.02, -0.05, 0.03, 0.6, 12.0, 15.0, 1.0, 0.03, -0.02, 20.0, 30.0,
        ];
        let prob = model.predict_prob(&features);
        assert!(
            (0.0..=1.0).contains(&prob),
            "Probability must be in [0,1]: {prob}"
        );

        println!("Model: {} trees, prob={prob:.4}", model.n_trees());
    }

    #[test]
    fn pg_width_bucket5_boundaries() {
        // Matches Postgres width_bucket(p,0,1,5) at the documented boundaries.
        assert_eq!(pg_width_bucket5(-0.1), 0);
        assert_eq!(pg_width_bucket5(0.0), 1);
        assert_eq!(pg_width_bucket5(0.19), 1);
        assert_eq!(pg_width_bucket5(0.2), 2);
        assert_eq!(pg_width_bucket5(0.4), 3);
        assert_eq!(pg_width_bucket5(0.6), 4);
        assert_eq!(pg_width_bucket5(0.8), 5);
        assert_eq!(pg_width_bucket5(0.999), 5);
        assert_eq!(pg_width_bucket5(1.0), 6);
        assert_eq!(pg_width_bucket5(1.5), 6);
    }

    fn extras(iso_x: Vec<f64>, iso_y: Vec<f64>) -> ResidExtras {
        ResidExtras {
            band_rates: [0.10, 0.30, 0.50, 0.70, 0.90],
            global_rate: 0.42,
            iso_x,
            iso_y,
        }
    }

    #[test]
    fn band_rate_picks_the_blind_baseline() {
        let ex = extras(vec![], vec![]);
        assert_eq!(ex.band_rate(0.05), 0.10); // band 1
        assert_eq!(ex.band_rate(0.25), 0.30); // band 2
        assert_eq!(ex.band_rate(0.55), 0.50); // band 3
        assert_eq!(ex.band_rate(0.75), 0.70); // band 4
        assert_eq!(ex.band_rate(0.95), 0.90); // band 5
        // Out of range (p>=1 or p<0) falls back to the global rate.
        assert_eq!(ex.band_rate(1.0), 0.42);
        assert_eq!(ex.band_rate(-0.2), 0.42);
    }

    #[test]
    fn apply_iso_is_identity_without_knots() {
        let ex = extras(vec![], vec![]);
        for p in [0.0, 0.25, 0.5, 0.75, 1.0] {
            assert_eq!(ex.apply_iso(p), p, "identity when no knots");
        }
        // A single knot is still insufficient ⇒ identity.
        let one = extras(vec![0.5], vec![0.6]);
        assert_eq!(one.apply_iso(0.3), 0.3);
    }

    #[test]
    fn apply_iso_interpolates_and_is_monotone() {
        // Knots: (0.2->0.1), (0.5->0.4), (0.8->0.9). Non-decreasing in y.
        let ex = extras(vec![0.2, 0.5, 0.8], vec![0.1, 0.4, 0.9]);
        // Clamp below / above the support to the endpoint y-values.
        assert_eq!(ex.apply_iso(0.0), 0.1);
        assert_eq!(ex.apply_iso(1.0), 0.9);
        assert_eq!(ex.apply_iso(0.2), 0.1);
        assert_eq!(ex.apply_iso(0.8), 0.9);
        // Midpoint of the first segment: halfway in x ⇒ halfway in y.
        assert!((ex.apply_iso(0.35) - 0.25).abs() < 1e-12);
        // Midpoint of the second segment.
        assert!((ex.apply_iso(0.65) - 0.65).abs() < 1e-12);
        // Monotone non-decreasing across a fine sweep.
        let mut prev = f64::NEG_INFINITY;
        for i in 0..=100 {
            let p = i as f64 / 100.0;
            let y = ex.apply_iso(p);
            assert!(y >= prev - 1e-12, "isotonic output must not decrease");
            prev = y;
        }
    }

    // Postgres-parity for `pg_width_bucket5`: a fine 0..1 sweep + the exact band
    // edges must match `SELECT width_bucket(p,0,1,5)` (float-boundary safety).
    // `#[ignore]`d (needs a live DB); run with:
    //   DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
    //     cargo test -p polymarket-common width_bucket_parity -- --ignored --nocapture
    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL"]
    async fn width_bucket_parity() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let mut probes: Vec<f64> = (0..=1000).map(|i| i as f64 / 1000.0).collect();
        // Exact band edges + a few out-of-range values.
        probes.extend([0.2, 0.4, 0.6, 0.8, -0.1, -0.0001, 1.0, 1.0001]);
        let mut mismatches = 0usize;
        for p in probes {
            let (pg,): (i32,) = sqlx::query_as("SELECT width_bucket($1::float8, 0.0, 1.0, 5)")
                .bind(p)
                .fetch_one(&pool)
                .await
                .unwrap();
            let ours = pg_width_bucket5(p);
            if ours != pg {
                mismatches += 1;
                eprintln!("MISMATCH p={p}: ours={ours} pg={pg}");
            }
        }
        assert_eq!(
            mismatches, 0,
            "pg_width_bucket5 must match Postgres exactly"
        );
        println!("width_bucket_parity: pg_width_bucket5 matches Postgres on the full sweep");
    }
}
