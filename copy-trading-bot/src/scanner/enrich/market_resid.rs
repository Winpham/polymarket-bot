//! Price-FREE residual arm (`market_resid`): the trading-bot's market-outcome
//! model given a fair, tautology-free shot on the consensus path.
//!
//! The shipped `arm_market` fires on `p_model - clob_mid`, which scores ~0 by
//! construction: the scoreboard already subtracts the band-matched `_blind`
//! baseline (the favorite-longshot residual that `p_model` tracks). That measures
//! the price feature, it does not test the model. Instead this arm:
//!   1. predicts `p_yes` from NON-price features (the booster has no split on the
//!      price indices — trained on constant price columns), then orients to the
//!      consensus outcome (`1 - p_yes` for a NO-side pick);
//!   2. compares to the band's OWN `_blind` base rate (`band_rate`), NOT the live
//!      mid — aligning the selection target with the gate's surplus-over-blind.
//! The belief-blind gate still independently judges every re-emitted row; the
//! alignment removes the tautology, it does not hand the model a free pass.

use super::{ConsensusSignal, EnrichCtx, forward_ok, re_emit};

/// Re-emit `strict` picks the price-free residual model rates above the band's
/// blind base rate by more than the margin. No-ops unless both the model and its
/// `.resid.json` extras loaded (default-OFF).
pub fn arm_market_resid(sigs: &[ConsensusSignal], ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    let (Some(model), Some(ex)) = (&ctx.models.market_resid, &ctx.models.market_resid_extras)
    else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for s in sigs {
        if s.strategy != "strict" {
            continue;
        }
        if !forward_ok(s, ctx.models.market_resid_through, ctx.now) {
            continue;
        }
        let Some(mc) = ctx.markets.get(&s.condition_id) else {
            continue; // features unavailable this cycle
        };
        let Some(feat) = &mc.features else {
            continue;
        };
        // Features are YES-oriented; calibrate p_yes, then orient to the consensus
        // outcome and residual against the band's blind base rate (not the mid).
        let p_yes = ex.apply_iso(model.predict_prob(&feat.to_vec()));
        let p_cons = if mc.outcome_index == 0 {
            p_yes
        } else {
            1.0 - p_yes
        };
        let resid = p_cons - ex.band_rate(s.mean_price);
        if resid > ctx.margins.ml {
            out.push(re_emit(s, "market_resid"));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scanner::consensus::Tier;
    use crate::scanner::enrich::{EnrichMargins, EnrichModels, MarketCtx};
    use polymarket_common::model::features::MarketFeatures;
    use polymarket_common::model::xgb::{ResidExtras, XgbModel};
    use std::collections::HashMap;

    fn const_model(p: f64) -> XgbModel {
        use std::sync::atomic::{AtomicU64, Ordering};
        static NONCE: AtomicU64 = AtomicU64::new(0);
        let leaf = (p / (1.0 - p)).ln();
        let json = format!(
            "{{\"learner\":{{\"learner_model_param\":{{\"base_score\":\"0.5\"}},\
             \"gradient_booster\":{{\"model\":{{\"trees\":[{{\
             \"split_indices\":[0],\"split_conditions\":[{leaf}],\
             \"left_children\":[-1],\"right_children\":[-1],\"default_left\":[0]}}]}}}}}}}}"
        );
        // Unique per call so concurrent tests never race on a shared temp path.
        let n = NONCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "market_resid_arm_const_{}_{}.json",
            std::process::id(),
            n
        ));
        std::fs::write(&path, json).unwrap();
        XgbModel::load(&path).unwrap()
    }

    fn extras() -> ResidExtras {
        // band 3 (mean_price 0.55) blind base rate = 0.50.
        ResidExtras {
            band_rates: [0.10, 0.30, 0.50, 0.70, 0.90],
            global_rate: 0.5,
            iso_x: vec![],
            iso_y: vec![],
        }
    }

    fn zero_features() -> MarketFeatures {
        // All zero; the const model ignores features anyway.
        serde_json::from_value(serde_json::json!({
            "yes_price":0.0,"momentum_1h":0.0,"momentum_24h":0.0,"volatility_24h":0.0,
            "rsi":0.0,"log_volume":0.0,"days_to_expiry":0.0,"is_crypto":0.0,
            "price_change_1d":0.0,"price_change_1w":0.0,"days_since_created":0.0,
            "created_to_expiry_span":0.0,"is_sports":0.0,"q_length":0.0,"q_word_count":0.0,
            "q_avg_word_len":0.0,"q_word_diversity":0.0,"q_has_number":0.0,"q_has_year":0.0,
            "q_has_percent":0.0,"q_has_dollar":0.0,"q_has_date":0.0,"q_starts_will":0.0,
            "q_has_by":0.0,"q_has_before":0.0,"q_has_above":0.0,"q_sentiment_pos":0.0,
            "q_sentiment_neg":0.0,"q_certainty":0.0
        }))
        .unwrap()
    }

    fn strict_sig(outcome_index: i32) -> ConsensusSignal {
        ConsensusSignal {
            strategy: "strict".into(),
            condition_id: "0xr".into(),
            outcome_index,
            outcome_label: "Yes".into(),
            title: "t".into(),
            slug: "s".into(),
            event_slug: Some("ev".into()),
            is_sports: false,
            backers: vec![],
            n_backers: 6,
            n_opposers: 0,
            net_count: 6,
            net_quality: 9.0,
            mean_price: 0.55, // band 3 -> blind rate 0.50
            price_std: 0.02,
            recency_mins: 10,
            total_usd: 4000.0,
            best_backer_rank: Some(4),
            score: 1.0,
            tier: Tier::Elite,
        }
    }

    fn ctx_with<'a>(
        models: &'a EnrichModels,
        markets: &'a HashMap<String, MarketCtx>,
    ) -> EnrichCtx<'a> {
        EnrichCtx {
            now: chrono::Utc::now(),
            models,
            margins: EnrichMargins::default(), // ml = 0.0
            markets,
        }
    }

    fn one_market(outcome_index: i32) -> HashMap<String, MarketCtx> {
        let mut m = HashMap::new();
        m.insert(
            "0xr".to_string(),
            MarketCtx {
                clob_mid: 0.99, // deliberately != band_rate, to prove we DON'T use it
                features: Some(zero_features()),
                outcome_index,
            },
        );
        m
    }

    #[test]
    fn noops_without_model_or_extras() {
        let markets = one_market(0);
        // Model present but extras missing -> no-op.
        let only_model = EnrichModels {
            market_resid: Some(const_model(0.8)),
            ..Default::default()
        };
        assert!(arm_market_resid(&[strict_sig(0)], &ctx_with(&only_model, &markets)).is_empty());
        // Both absent -> no-op.
        let none = EnrichModels::default();
        assert!(arm_market_resid(&[strict_sig(0)], &ctx_with(&none, &markets)).is_empty());
    }

    #[test]
    fn fires_on_residual_over_band_not_mid() {
        // p_yes = 0.80, band_rate(0.55) = 0.50 -> resid = +0.30 > 0 -> emit.
        // If the arm wrongly used clob_mid (0.99), resid would be -0.19 -> no emit;
        // emitting proves we compare to the band rate, not the live mid.
        let models = EnrichModels {
            market_resid: Some(const_model(0.80)),
            market_resid_extras: Some(extras()),
            ..Default::default()
        };
        let markets = one_market(0);
        let out = arm_market_resid(&[strict_sig(0)], &ctx_with(&models, &markets));
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].strategy, "market_resid");
        assert_eq!(out[0].tier, Tier::Watch, "silent (never alerts)");
    }

    #[test]
    fn orients_no_side_then_residuals() {
        // NO-side pick: p_cons = 1 - 0.80 = 0.20, band_rate 0.50 -> resid -0.30 < 0
        // -> no emit. (The YES-side identical model emits; see above.)
        let models = EnrichModels {
            market_resid: Some(const_model(0.80)),
            market_resid_extras: Some(extras()),
            ..Default::default()
        };
        let markets = one_market(1);
        assert!(arm_market_resid(&[strict_sig(1)], &ctx_with(&models, &markets)).is_empty());
    }

    // Python -> Rust format compat: load the real train_market_resid.py artifacts
    // and run the arm end-to-end. `#[ignore]`d (needs the trained dir); run with:
    //   MARKET_RESID_MODEL_DIR=/tmp/mr_smoke \
    //     cargo test -p copy-trading-bot market_resid_artifacts -- --ignored --nocapture
    #[test]
    #[ignore = "needs MARKET_RESID_MODEL_DIR (train_market_resid.py output)"]
    fn market_resid_artifacts_load_and_emit() {
        use std::path::Path;
        let dir = std::env::var("MARKET_RESID_MODEL_DIR").expect("MARKET_RESID_MODEL_DIR");
        let model = XgbModel::load(&Path::new(&dir).join("market_resid.json"))
            .expect("market_resid.json loads in Rust");
        assert!(model.n_trees() > 0, "booster parsed trees");
        let extras = ResidExtras::load(&Path::new(&dir).join("market_resid.resid.json"))
            .expect("market_resid.resid.json loads into ResidExtras");
        // apply_iso must stay in range; band_rate must return a probability.
        let p = extras.apply_iso(model.predict_prob(&zero_features().to_vec()));
        assert!((0.0..=1.0).contains(&p), "calibrated p in range: {p}");
        assert!((0.0..=1.0).contains(&extras.band_rate(0.55)));

        let models = EnrichModels {
            market_resid: Some(model),
            market_resid_extras: Some(extras),
            ..Default::default()
        };
        let markets = one_market(0);
        // Margin -1 ⇒ resid > -1 always true ⇒ guaranteed emit for the fixture, so
        // this exercises the full load→predict→orient→re_emit path deterministically.
        let ctx = EnrichCtx {
            now: chrono::Utc::now(),
            models: &models,
            margins: EnrichMargins {
                ml: -1.0,
                bayes: 0.0,
            },
            markets: &markets,
        };
        let out = arm_market_resid(&[strict_sig(0)], &ctx);
        assert_eq!(out.len(), 1, "arm emits from the real artifacts");
        assert_eq!(out[0].strategy, "market_resid");
        assert_eq!(out[0].tier, Tier::Watch);
        assert_eq!(
            crate::scanner::enrich::family("market_resid"),
            "experimental",
            "judged in the experimental family"
        );
        println!("market_resid_artifacts: load + predict + emit + family-split all OK");
    }

    #[test]
    fn skips_non_strict() {
        let models = EnrichModels {
            market_resid: Some(const_model(0.99)),
            market_resid_extras: Some(extras()),
            ..Default::default()
        };
        let markets = one_market(0);
        let mut other = strict_sig(0);
        other.strategy = "favorite_tail".into();
        assert!(arm_market_resid(&[other], &ctx_with(&models, &markets)).is_empty());
    }
}
