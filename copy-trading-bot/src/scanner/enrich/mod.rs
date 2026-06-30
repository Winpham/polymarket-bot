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
use polymarket_common::model::xgb::{ResidExtras, XgbModel};

pub mod bayes;
pub mod features;
pub mod market;
pub mod market_resid;
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
    /// Price-free residual model (the `market_resid` arm) + its baked extras.
    pub market_resid: Option<XgbModel>,
    pub market_resid_extras: Option<ResidExtras>,
    /// Forward-only training cutoff for `market_resid` (from its meta.json / env).
    pub market_resid_through: Option<DateTime<Utc>>,
    /// Whether the Bayesian-anchor arm is enabled (it needs no model file).
    pub bayes_enabled: bool,
    /// Whether to log the forward 29-feature vector for every strict-fired market
    /// (the `market_feature_log` accrual path — no arm, just durable capture).
    pub feature_log: bool,
}

impl EnrichModels {
    /// True if any arm needs per-market data pre-fetched (CLOB mid for bayes;
    /// CLOB mid + Gamma + price history for the market model / the feature log).
    pub fn needs_market_data(&self) -> bool {
        self.market_xgb.is_some()
            || self.market_resid.is_some()
            || self.bayes_enabled
            || self.feature_log
    }

    /// True if an arm needs the full [`MarketFeatures`] (Gamma + price history),
    /// not just the CLOB mid. The feature log needs the full vector too.
    pub fn needs_market_features(&self) -> bool {
        self.market_xgb.is_some() || self.market_resid.is_some() || self.feature_log
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

    if cfg.consensus_arm_resid {
        let p = Path::new(&cfg.market_resid_model_path);
        let sidecar = p.with_extension("resid.json");
        // Load the booster AND its extras, or neither — a missing/invalid sidecar
        // leaves the arm a no-op (we never fire without a band baseline).
        if p.exists() && sidecar.exists() {
            match (XgbModel::load(p), ResidExtras::load(&sidecar)) {
                (Ok(model), Ok(extras)) => {
                    m.market_resid = Some(model);
                    m.market_resid_extras = Some(extras);
                    m.market_resid_through =
                        resid_trained_through(p, &cfg.market_resid_trained_through);
                    tracing::info!(path = %p.display(), "Loaded market_resid model + extras");
                }
                (model, extras) => {
                    if let Err(e) = model {
                        tracing::warn!(err = %e, "market_resid model failed to load; arm off");
                    }
                    if let Err(e) = extras {
                        tracing::warn!(err = %e, "market_resid extras failed to load; arm off");
                    }
                }
            }
        } else {
            tracing::info!(path = %p.display(), "market_resid ON but model/sidecar absent; arm no-ops");
        }
    }

    m.bayes_enabled = cfg.consensus_arm_bayes;
    m.feature_log = cfg.market_feature_log;
    m
}

/// Resolve the `market_resid` forward cutoff: prefer the model's `.meta.json`
/// `trained_through`, else the `MARKET_RESID_TRAINED_THROUGH` override. `None`
/// (neither set / unparseable) ⇒ rely on structural forwardness.
fn resid_trained_through(model_path: &Path, env_override: &str) -> Option<DateTime<Utc>> {
    let from_meta = std::fs::read_to_string(model_path.with_extension("meta.json"))
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| {
            v.get("trained_through")
                .and_then(|t| t.as_str())
                .map(str::to_string)
        });
    let raw = from_meta.unwrap_or_default();
    let raw = if raw.trim().is_empty() {
        env_override.trim()
    } else {
        raw.trim()
    };
    if raw.is_empty() {
        return None;
    }
    match DateTime::parse_from_rfc3339(raw) {
        Ok(d) => Some(d.with_timezone(&Utc)),
        Err(e) => {
            tracing::warn!(err = %e, value = raw, "bad market_resid trained_through; no guard");
            None
        }
    }
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
    /// Live CLOB mid of the consensus outcome (the comparison anchor for the
    /// legacy `arm_market` and for CLV — NOT necessarily the YES-token mid).
    pub clob_mid: f64,
    /// Full market feature vector (Gamma + price history). Always describes the
    /// **YES (index-0) token** so an arm can convert `p_yes → p_consensus` via
    /// `outcome_index`. `None` if a fetch failed or features weren't needed.
    pub features: Option<MarketFeatures>,
    /// Which outcome the consensus picked. `0` means the consensus outcome IS the
    /// YES token (so `p_consensus == p_yes`); otherwise `p_consensus == 1 - p_yes`.
    pub outcome_index: i32,
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
        market_resid::arm_market_resid,
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
        "market_resid",
        "bayes_anchor",
        "trust_weighted",
        "trusted_only",
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

    // --- End-to-end (Phase 5): Python→Rust model compat + arm emit + scoreboard
    //     + family-split gate. `#[ignore]`d (needs the trained model dir + a live
    //     Postgres); run after `scripts/consensus_train.py` with:
    //
    //   CONSENSUS_MODEL_DIR=/tmp/cm \
    //   DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
    //     cargo test -p copy-trading-bot arm_pipeline_e2e -- --ignored --nocapture
    use crate::scanner::consensus::ConsensusSignal;

    fn strict_fixture() -> ConsensusSignal {
        ConsensusSignal {
            strategy: "strict".into(),
            condition_id: "0xfix".into(),
            outcome_index: 0,
            outcome_label: "Yes".into(),
            title: "t".into(),
            slug: "s".into(),
            event_slug: Some("evfix".into()),
            is_sports: false,
            backers: vec![],
            n_backers: 6,
            n_opposers: 0,
            net_count: 6,
            net_quality: 9.0,
            mean_price: 0.55,
            price_std: 0.02,
            recency_mins: 10,
            total_usd: 4000.0,
            best_backer_rank: Some(4),
            score: 1.0,
            tier: crate::scanner::consensus::Tier::Elite,
        }
    }

    #[tokio::test]
    #[ignore = "needs CONSENSUS_MODEL_DIR (consensus_train.py output) + DATABASE_URL"]
    async fn arm_pipeline_e2e() {
        use crate::scanner::promotion::{PromotionParams, promotion_verdict};
        use crate::storage::postgres::PgPortfolio;
        use std::path::Path;

        // (a) Python→Rust model-format compatibility.
        let dir = std::env::var("CONSENSUS_MODEL_DIR").expect("CONSENSUS_MODEL_DIR");
        let win = ConsensusWinModel::load(&Path::new(&dir).join("consensus_win.json"))
            .expect("consensus_win.json loads in Rust");
        let p = win.p_win(&super::features::consensus_feature_vec(&strict_fixture()));
        assert!((0.0..=1.0).contains(&p), "p_win in range: {p}");
        let ens = XgbModel::load(&Path::new(&dir).join("consensus_ens.json"))
            .expect("consensus_ens.json loads in Rust");
        assert!(ens.n_trees() > 0, "ensemble parsed trees");

        // (b) Arm emits a silent tagged row from the real loaded logit model.
        let models = EnrichModels {
            consensus_win: Some(win),
            ..Default::default()
        };
        let markets = HashMap::new();
        // margin -1 ⇒ p − price > −1 always true ⇒ guaranteed emit for the fixture.
        let ctx = EnrichCtx {
            now: Utc::now(),
            models: &models,
            margins: EnrichMargins {
                ml: -1.0,
                bayes: 0.0,
            },
            markets: &markets,
        };
        let emitted = enrich_all(vec![strict_fixture()], &ctx);
        assert!(
            emitted.iter().any(|s| s.strategy == "consensus_logit"),
            "consensus_logit arm emits"
        );

        // (c) Arm-tagged rows resolve → scoreboard → family-split gate verdict.
        let url = std::env::var("DATABASE_URL").unwrap();
        let pool = sqlx::PgPool::connect(&url).await.unwrap();
        let pf = PgPortfolio::new(pool.clone()).await.unwrap();
        // Clean any prior e2e rows.
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'e2e_%'")
            .execute(&pool)
            .await
            .unwrap();

        async fn ins(
            pool: &sqlx::PgPool,
            strat: &str,
            ev: i32,
            mean_price: f64,
            won: bool,
            mid: f64,
        ) {
            sqlx::query(
                "INSERT INTO consensus_signals \
                   (strategy, condition_id, outcome_index, outcome_label, title, slug, event_slug, \
                    is_sports, observed_votes, n_backers, n_opposers, net_count, net_quality, \
                    mean_price, price_std, recency_mins, total_usd, score, tier, backers, \
                    resolved, outcome_won, initial_market_price) \
                 VALUES ($1,$2,0,'Yes','t','s',$3,false,'[]',5,0,5,5.0,$4,0.02,10,2000,1,'WATCH','[]', \
                         true,$5,$6)",
            )
            .bind(strat)
            .bind(format!("e2e_{strat}_{ev}"))
            .bind(format!("e2e_ev_{strat}_{ev}"))
            .bind(mean_price)
            .bind(won)
            .bind(mid)
            .execute(pool)
            .await
            .unwrap();
        }

        // _blind baseline + one core (strict) + two experimental arms, each over
        // several distinct events with a captured mid (so CLV computes too).
        for e in 0..6 {
            let won = e % 2 == 0;
            ins(&pool, "_blind", e, 0.50, won, 0.48).await;
            ins(&pool, "strict", e, 0.55, won, 0.52).await;
            ins(&pool, "consensus_logit", e, 0.55, e % 3 != 0, 0.52).await;
            ins(&pool, "market_ml", e, 0.55, won, 0.52).await;
        }

        let rows = pf.consensus_scoreboard_by_strategy().await.unwrap();
        let names: Vec<&str> = rows.iter().map(|r| r.strategy.as_str()).collect();
        assert!(names.contains(&"strict"), "core strict present");
        assert!(
            names.contains(&"consensus_logit"),
            "experimental arm present"
        );
        assert!(names.contains(&"market_ml"), "experimental arm present");
        assert!(
            !names.contains(&"_blind"),
            "_blind is the baseline, not a row"
        );

        // CLV instrumentation populated for an arm row (mid was captured).
        let arm = rows
            .iter()
            .find(|r| r.strategy == "consensus_logit")
            .unwrap();
        assert!(arm.our_clv.is_some(), "CLV computed for arm rows");

        // Family split: per-family Bonferroni denominator (robust to whatever
        // other strategies already live in the DB).
        let mut fam_n: HashMap<&str, usize> = HashMap::new();
        for r in &rows {
            *fam_n.entry(family(&r.strategy)).or_default() += 1;
        }
        let exp_n = *fam_n.get("experimental").unwrap_or(&0);
        let core_n = *fam_n.get("core").unwrap_or(&0);
        assert_eq!(exp_n, 2, "exactly our two experimental arms are present");
        assert!(core_n >= 1, "at least the core strict strategy is present");
        assert_eq!(exp_n + core_n, rows.len(), "families partition the rows");
        // The arms are classified experimental (so they never raise core's bar).
        assert_eq!(family("consensus_logit"), "experimental");
        assert_eq!(family("market_ml"), "experimental");
        assert!(
            !rows
                .iter()
                .any(|r| family(&r.strategy) == "core" && r.strategy == "consensus_logit"),
            "consensus_logit must not be counted in the core family"
        );

        // The per-family denominator gives the arm a LOOSER (no-tighter) correction
        // than pooling all strategies would — the whole point of the family split.
        let pp = PromotionParams {
            min_events: 1,
            ..PromotionParams::default()
        };
        let split = promotion_verdict(arm.distinct_events, arm.surplus, arm.surplus_sd, exp_n, &pp);
        let pooled = promotion_verdict(
            arm.distinct_events,
            arm.surplus,
            arm.surplus_sd,
            rows.len(),
            &pp,
        );
        if let (Some(a), Some(b)) = (split.lower_bound, pooled.lower_bound) {
            assert!(a >= b, "per-family correction is no tighter than pooled");
        }

        // Cleanup.
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'e2e_%'")
            .execute(&pool)
            .await
            .unwrap();
        println!("arm_pipeline_e2e: model load + emit + scoreboard + family split all OK");
    }
}
