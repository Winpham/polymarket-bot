//! Earned trader-trust verdict — "who to actually follow".
//!
//! A trader's edge is a pseudo-strategy: we reuse the belief-blind gate's exact
//! machinery (`surplus_bounds` / `promotion_verdict`) and add ZERO new
//! statistics. Trust is EARNED, leak-free, event-clustered, sample-floored:
//!  - surplus is over the trader's-own-band blind baseline (favorite-longshot-
//!    neutralized) at the distinct-EVENT level (computed in SQL, `common`),
//!  - judged on a one-sided confidence bound after a **Bonferroni** correction
//!    across that wallet's slices,
//!  - with a **≥30 distinct-event floor ⇒ INDETERMINATE**.
//!
//! One conservatism at the gate, not two: the verdict uses the RAW
//! event-clustered surplus + sd. We do NOT shrink the point estimate here — the
//! blind baseline + one-sided bound + event floor are the rigor; shrinking too
//! would double-penalize N. (Shrink-toward-0 lives only on the continuous
//! `earned_quality` weight in Phase 4, where it regularizes a multiplier.)

use polymarket_common::storage::consensus::TraderSliceStat;

use crate::scanner::promotion::{PromotionParams, surplus_bounds};

/// The earned-trust verdict for one wallet.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrustVerdict {
    /// Surplus lower bound clears the margin over ≥`min_events` events.
    Trusted,
    /// Not enough events, or the bound straddles the margin.
    Indeterminate,
    /// Surplus UPPER bound is below `−margin` — demonstrably worse than blind.
    Avoid,
}

impl TrustVerdict {
    pub fn as_str(&self) -> &'static str {
        match self {
            TrustVerdict::Trusted => "TRUSTED",
            TrustVerdict::Indeterminate => "INDETERMINATE",
            TrustVerdict::Avoid => "AVOID",
        }
    }

    /// Glanceable marker mirroring the board's gate convention.
    pub fn marker(&self) -> &'static str {
        match self {
            TrustVerdict::Trusted => "✅",
            TrustVerdict::Indeterminate => "⏸",
            TrustVerdict::Avoid => "⛔",
        }
    }
}

/// The full trust picture for one wallet: the headline verdict + the slices that
/// most help (best) and hurt (worst), for surfacing "with what games".
#[derive(Debug, Clone)]
pub struct TraderTrust {
    pub wallet: String,
    pub verdict: TrustVerdict,
    /// Distinct resolved events behind the `overall` headline.
    pub n_events: i64,
    /// Bonferroni-corrected one-sided lower bound on the overall surplus.
    pub lower_bound: f64,
    /// Symmetric upper bound (the Avoid test).
    pub upper_bound: f64,
    /// Overall event-clustered surplus (raw point estimate, for display).
    pub surplus: f64,
    /// `(slice_kind, slice_key, surplus)` best-first (non-overall slices).
    pub best_slices: Vec<(String, String, f64)>,
    /// `(slice_kind, slice_key, surplus)` worst-first (non-overall slices).
    pub worst_slices: Vec<(String, String, f64)>,
}

/// Compute one wallet's trust verdict from its slice stats, using the default
/// promotion thresholds (≥30 events, margin 0, α 0.05). `slices` must all belong
/// to the same wallet.
pub fn trust_verdict(slices: &[TraderSliceStat]) -> TraderTrust {
    trust_verdict_with(slices, &PromotionParams::default())
}

/// As [`trust_verdict`] but with explicit thresholds (used by tests).
pub fn trust_verdict_with(slices: &[TraderSliceStat], p: &PromotionParams) -> TraderTrust {
    let wallet = slices.first().map(|s| s.wallet.clone()).unwrap_or_default();

    // Bonferroni denominator = the number of this wallet's slices that actually
    // have resolved data (a surplus). Correcting across the wallet's own slices
    // stops "best of 12 slices" from looking significant by chance.
    let n_comparisons = slices.iter().filter(|s| s.surplus.is_some()).count().max(1);

    let overall = slices.iter().find(|s| s.slice_kind == "overall");

    // best/worst NON-overall slices by surplus (only slices with data).
    let mut graded: Vec<(String, String, f64)> = slices
        .iter()
        .filter(|s| s.slice_kind != "overall")
        .filter_map(|s| {
            s.surplus
                .map(|v| (s.slice_kind.clone(), s.slice_key.clone(), v))
        })
        .collect();
    graded.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));
    let best_slices: Vec<_> = graded.iter().take(3).cloned().collect();
    let worst_slices: Vec<_> = graded.iter().rev().take(3).cloned().collect();

    // No overall data, or below the event floor ⇒ INDETERMINATE regardless of
    // the point estimate (small N is not evidence).
    let Some(o) = overall else {
        return TraderTrust {
            wallet,
            verdict: TrustVerdict::Indeterminate,
            n_events: 0,
            lower_bound: 0.0,
            upper_bound: 0.0,
            surplus: 0.0,
            best_slices,
            worst_slices,
        };
    };
    let surplus = o.surplus.unwrap_or(0.0);
    if o.n_events < p.min_events || o.surplus.is_none() {
        return TraderTrust {
            wallet,
            verdict: TrustVerdict::Indeterminate,
            n_events: o.n_events,
            lower_bound: 0.0,
            upper_bound: 0.0,
            surplus,
            best_slices,
            worst_slices,
        };
    }

    // RAW event-clustered surplus + sd — no point shrinkage at the verdict.
    let (lo, hi) = surplus_bounds(o.n_events, surplus, o.surplus_sd, n_comparisons, p);
    let verdict = if lo > p.margin {
        TrustVerdict::Trusted
    } else if hi < -p.margin {
        TrustVerdict::Avoid
    } else {
        TrustVerdict::Indeterminate
    };

    TraderTrust {
        wallet,
        verdict,
        n_events: o.n_events,
        lower_bound: lo,
        upper_bound: hi,
        surplus,
        best_slices,
        worst_slices,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn slice(
        wallet: &str,
        kind: &str,
        key: &str,
        n_events: i64,
        surplus: Option<f64>,
        sd: Option<f64>,
    ) -> TraderSliceStat {
        TraderSliceStat {
            wallet: wallet.into(),
            slice_kind: kind.into(),
            slice_key: key.into(),
            n_events,
            n_resolved: n_events,
            surplus,
            surplus_sd: sd,
            mean_adv: surplus,
            hit_rate: Some(0.5),
        }
    }

    #[test]
    fn high_n_skilled_wallet_is_trusted() {
        let slices = vec![
            slice("w", "overall", "", 60, Some(0.10), Some(0.10)),
            slice("w", "sport", "nba", 30, Some(0.12), Some(0.12)),
        ];
        let t = trust_verdict(&slices);
        assert_eq!(t.verdict, TrustVerdict::Trusted, "lo={}", t.lower_bound);
        assert!(t.lower_bound > 0.0);
    }

    #[test]
    fn high_n_negative_wallet_is_avoid() {
        let slices = vec![slice("w", "overall", "", 60, Some(-0.12), Some(0.10))];
        let t = trust_verdict(&slices);
        assert_eq!(t.verdict, TrustVerdict::Avoid);
        assert!(t.upper_bound < 0.0);
    }

    #[test]
    fn small_n_is_indeterminate_regardless_of_point_estimate() {
        // Only 10 events but a huge apparent surplus + zero noise — still must
        // be INDETERMINATE (the event floor dominates, no false trust on 10 fills).
        let slices = vec![slice("w", "overall", "", 10, Some(0.50), Some(0.001))];
        let t = trust_verdict(&slices);
        assert_eq!(t.verdict, TrustVerdict::Indeterminate);
        assert_eq!(t.n_events, 10);
    }

    #[test]
    fn favorite_loader_collapses_to_zero_surplus() {
        // A wallet that only "looks good" by loading favorites has surplus ≈ 0
        // (the band-blind baseline neutralizes it) ⇒ not Trusted even at high N.
        let slices = vec![slice("w", "overall", "", 80, Some(0.0), Some(0.08))];
        let t = trust_verdict(&slices);
        assert_eq!(t.verdict, TrustVerdict::Indeterminate);
    }

    #[test]
    fn best_and_worst_slices_ranked() {
        let slices = vec![
            slice("w", "overall", "", 60, Some(0.05), Some(0.10)),
            slice("w", "sport", "nba", 30, Some(0.20), Some(0.10)),
            slice("w", "sport", "soccer", 30, Some(-0.15), Some(0.10)),
            slice("w", "band", "b4", 20, Some(0.02), Some(0.10)),
        ];
        let t = trust_verdict(&slices);
        assert_eq!(t.best_slices[0].1, "nba", "best slice first");
        assert_eq!(t.worst_slices[0].1, "soccer", "worst slice first");
    }

    // --- Live: trader_slice_scores SQL + verdict end-to-end. `#[ignore]`d; run
    //     against a throwaway Postgres (schema migrated):
    //
    //   DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
    //     cargo test -p copy-trading-bot trust_scores_e2e -- --ignored --nocapture
    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn trust_scores_e2e() {
        use crate::storage::postgres::PgPortfolio;
        use std::collections::HashMap;

        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL");
        let pool = sqlx::PgPool::connect(&url).await.unwrap();
        let pf = PgPortfolio::new(pool.clone()).await.unwrap();
        // Deterministic blind baseline: this test owns the whole table (throwaway DB).
        sqlx::query("DELETE FROM trader_fills")
            .execute(&pool)
            .await
            .unwrap();

        // Insert one resolved BUY fill on a UNIQUE event (so each = a distinct
        // event), with resolution columns set directly (we're seeding a resolved
        // population; advantage mirrors resolve_trader_fills' BUY formula).
        async fn ins(
            pool: &sqlx::PgPool,
            wallet: &str,
            sport: &str,
            price: f64,
            won: bool,
            i: usize,
        ) {
            let adv = (won as i32) as f64 - price;
            let cond = format!("{wallet}_c{i}");
            sqlx::query(
                "INSERT INTO trader_fills \
                   (wallet, tx_hash, condition_id, outcome_index, outcome, side, price, size_usd, \
                    title, slug, event_slug, is_sports, sport, ts, resolved, outcome_won, advantage, resolved_at) \
                 VALUES ($1,$2,$3,0,'Yes','BUY',$4,100,'t','s',$5,true,$6,NOW()-INTERVAL '1 hour',true,$7,$8,NOW())",
            )
            .bind(wallet)
            .bind(format!("{cond}_tx"))
            .bind(&cond)
            .bind(price)
            .bind(&cond) // event_slug == condition ⇒ unique event per fill
            .bind(sport)
            .bind(won)
            .bind(adv)
            .execute(pool)
            .await
            .unwrap();
        }
        // Seed N fills at `price` with `wins` winners.
        async fn seed(
            pool: &sqlx::PgPool,
            wallet: &str,
            sport: &str,
            price: f64,
            n: usize,
            wins: usize,
        ) {
            for i in 0..n {
                ins(pool, wallet, sport, price, i < wins, i).await;
            }
        }

        // Baseline population sets the per-band blind:
        //  - band b3 (price 0.50): 200 fills @ 50% ⇒ blind_b3 ≈ 0.
        //  - band b5 (price 0.85): 200 fills @ 90% ⇒ blind_b5 ≈ +0.05 (the FLB).
        seed(&pool, "tt_base3", "other", 0.50, 200, 100).await;
        seed(&pool, "tt_base5", "other", 0.85, 200, 180).await;
        // Skilled: 80 nba fills @ 0.50, 75% win ⇒ raw adv +0.25, surplus ≈ +0.25.
        seed(&pool, "tt_skilled", "nba", 0.50, 80, 60).await;
        // Negative: 80 nba fills @ 0.50, 25% win ⇒ surplus ≈ −0.25.
        seed(&pool, "tt_negative", "nba", 0.50, 80, 20).await;
        // Small-N skilled: only 10 events, but +0.40 raw ⇒ must stay INDETERMINATE.
        seed(&pool, "tt_smalln", "nba", 0.50, 10, 9).await;
        // Favorite-loader: 80 fills @ 0.85, 90% win ⇒ raw adv +0.05, BUT the b5
        // blind is also +0.05 ⇒ surplus ≈ 0 (the bias is neutralized).
        seed(&pool, "tt_favloader", "soccer", 0.85, 80, 72).await;

        let scores = pf.trader_slice_scores().await.unwrap();
        let mut by_wallet: HashMap<String, Vec<_>> = HashMap::new();
        for s in scores {
            by_wallet.entry(s.wallet.clone()).or_default().push(s);
        }
        let verdict = |w: &str| trust_verdict(by_wallet.get(w).unwrap());

        let skilled = verdict("tt_skilled");
        assert_eq!(
            skilled.verdict,
            TrustVerdict::Trusted,
            "skilled: {:?}",
            skilled
        );
        assert!(
            skilled.surplus > 0.15,
            "skilled surplus {}",
            skilled.surplus
        );

        let negative = verdict("tt_negative");
        assert_eq!(
            negative.verdict,
            TrustVerdict::Avoid,
            "negative: {:?}",
            negative
        );

        let smalln = verdict("tt_smalln");
        assert_eq!(
            smalln.verdict,
            TrustVerdict::Indeterminate,
            "small-N floored"
        );
        assert_eq!(smalln.n_events, 10);

        let fav = verdict("tt_favloader");
        assert!(
            fav.surplus.abs() < 0.04,
            "favorite-loader surplus neutralized to ~0 (got {})",
            fav.surplus
        );
        assert_ne!(
            fav.verdict,
            TrustVerdict::Trusted,
            "FLB loader is not Trusted"
        );

        sqlx::query("DELETE FROM trader_fills WHERE wallet LIKE 'tt_%'")
            .execute(&pool)
            .await
            .unwrap();
        println!(
            "trust_scores_e2e: skilled=Trusted, negative=Avoid, small-N=Indeterminate, FLB neutralized — OK"
        );
    }
}
