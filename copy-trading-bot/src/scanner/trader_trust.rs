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

use std::collections::HashMap;

use polymarket_common::storage::consensus::TraderSliceStat;

use crate::scanner::promotion::{PromotionParams, TrustParams, surplus_bounds};
use crate::storage::postgres::PgPortfolio;

/// Process-global TTL cache of the fleet's slice scores. `trader_slice_scores` is
/// a full-table aggregation over the unbounded-growth `trader_fills` archive; the
/// board re-renders every 30s and `/trustedtraders` lists the whole fleet, so
/// without a cache each request re-scans the entire archive. The inputs only
/// change as markets resolve (~daily), so a short TTL is ample. The refresh runs
/// under the lock so concurrent callers don't stampede the DB.
type SliceCache = tokio::sync::Mutex<Option<(std::time::Instant, Vec<TraderSliceStat>)>>;
static SLICE_CACHE: std::sync::OnceLock<SliceCache> = std::sync::OnceLock::new();

/// Fleet slice scores, served from a `ttl`-bounded process cache (refreshed on
/// miss). A DB error is **propagated** (not masked as empty) and does NOT poison
/// the cache — the prior good value and its timestamp are left intact, so callers
/// can surface the error honestly and a transient hiccup never silently renders
/// as "no data". A successful empty result IS cached (genuinely no fills yet).
pub async fn cached_slice_scores(
    pf: &PgPortfolio,
    ttl: std::time::Duration,
) -> anyhow::Result<Vec<TraderSliceStat>> {
    let cell = SLICE_CACHE.get_or_init(|| tokio::sync::Mutex::new(None));
    let mut g = cell.lock().await;
    if let Some((at, v)) = g.as_ref()
        && at.elapsed() < ttl
    {
        return Ok(v.clone());
    }
    let fresh = pf.trader_slice_scores().await?; // error → cache untouched
    *g = Some((std::time::Instant::now(), fresh.clone()));
    Ok(fresh)
}

/// Drop the process-global slice cache. Live test suites seed fresh fills and
/// render in ONE process — without this, a prior test's cached aggregation
/// (within the TTL) leaks into the next test's render. Test-only by design.
#[cfg(test)]
pub async fn invalidate_slice_cache() {
    if let Some(cell) = SLICE_CACHE.get() {
        *cell.lock().await = None;
    }
}

/// The earned-trust verdict for one wallet.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrustVerdict {
    /// Surplus lower bound clears the margin over ≥`min_events` events.
    Trusted,
    /// Not enough events, or the bound straddles the margin.
    Indeterminate,
    /// Surplus UPPER bound is below `0` — demonstrably worse than blind.
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

/// A per-cell trust verdict (e.g. per-sport) — the SAME machinery as
/// [`trust_verdict_with`], applied to ONE slice, cached for the pooled per-cell
/// vote weight (FORGE_PLAN Item 3). No new estimator.
#[derive(Debug, Clone)]
pub struct CellVerdict {
    pub verdict: TrustVerdict,
    pub lower_bound: f64,
    pub upper_bound: f64,
    pub n_events: i64,
}

/// `(slice_kind, slice_key)` → its verdict. Empty ⇒ today's wallet-level behavior
/// (a wallet with no populated cells pools to its overall multiplier).
pub type CellMap = HashMap<(String, String), CellVerdict>;

/// Verdict for a SINGLE slice/cell, reusing the exact bound machinery
/// (`surplus_bounds` + day-deflated `eff_n` + the wallet's Bonferroni
/// `n_comparisons`). A dataless or below-floor cell reads `Indeterminate` — small
/// N is not evidence. `n_comparisons` is the wallet's OWN slice count (the cells
/// are a large multiplicity surface; corrected the same way the headline is).
pub fn cell_verdict(
    cell: &TraderSliceStat,
    n_comparisons: usize,
    p: &PromotionParams,
) -> CellVerdict {
    let indet = |n| CellVerdict {
        verdict: TrustVerdict::Indeterminate,
        lower_bound: 0.0,
        upper_bound: 0.0,
        n_events: n,
    };
    let Some(surplus) = cell.surplus else {
        return indet(cell.n_events);
    };
    if cell.n_events < p.min_events {
        return indet(cell.n_events);
    }
    let eff_n = cell.n_days.clamp(1, cell.n_events.max(1));
    let (lo, hi) = surplus_bounds(eff_n, surplus, cell.surplus_sd, n_comparisons, p);
    let verdict = if lo > p.margin {
        TrustVerdict::Trusted
    } else if hi < 0.0 {
        TrustVerdict::Avoid
    } else {
        TrustVerdict::Indeterminate
    };
    CellVerdict {
        verdict,
        lower_bound: lo,
        upper_bound: hi,
        n_events: cell.n_events,
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
    /// Per-cell verdicts (populated by `compute_trust_map`; empty here). Consumed
    /// by the pooled per-cell vote weight (FORGE_PLAN Item 3). Empty ⇒ the vote
    /// weight is exactly the wallet-level `earned_quality` (byte-identical).
    pub cells: CellMap,
}

/// Compute one wallet's trust verdict from its slice stats, using the default
/// promotion thresholds (≥30 events, the capture-cost margin, α 0.05). `slices`
/// must all belong to the same wallet. "Trusted" now means the surplus lower
/// bound clears the real cost cushion (`DEFAULT_PROMOTION_MARGIN`), NOT a
/// literal-zero baseline — closing the "Trusted vs 0 baseline" false-promote.
pub fn trust_verdict(slices: &[TraderSliceStat]) -> TraderTrust {
    // Trust/specialist floor is 25 (FORGE_PLAN Item 1 / GAP-3) — a DISTINCT knob
    // from the real-money pilot floor (honest::PilotThresholds{min_events:50}),
    // which builds its own PromotionParams and is unaffected by this.
    trust_verdict_with(slices, &TrustParams::default().into_promotion())
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
            cells: CellMap::default(),
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
            cells: CellMap::default(),
        };
    }

    // Effective N deflates the event count to distinct fill-DAYS (within-day
    // correlation): a wallet whose events all fall on one correlated weekend
    // gets an SE keyed on ~1 day, not N independent events — so a single
    // clustered weekend can't certify. Clamp low ⇒ unknown/zero day count
    // degrades to 1 (fail-closed); clamp high ⇒ it can only DEFLATE N.
    let eff_n = o.n_days.clamp(1, o.n_events.max(1));

    // RAW event-clustered surplus + sd — no point shrinkage at the verdict.
    let (lo, hi) = surplus_bounds(eff_n, surplus, o.surplus_sd, n_comparisons, p);
    let verdict = if lo > p.margin {
        TrustVerdict::Trusted
    } else if hi < 0.0 {
        // Avoid: upper bound below ZERO (demonstrably worse than blind). Pinned
        // at 0, NOT −margin: raising the Trusted margin above 0 must never make
        // the Avoid warning RARER. With the old margin-0 default this was
        // `hi < -0` ≡ `hi < 0`, so this preserves today's Avoid behavior exactly.
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
        cells: CellMap::default(),
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
        // Default: one distinct day per event (no clustering deflation), so the
        // legacy tests exercise the event-level N. Cluster tests set n_days
        // explicitly via `slice_days`.
        slice_days(wallet, kind, key, n_events, n_events, surplus, sd)
    }

    #[allow(clippy::too_many_arguments)]
    fn slice_days(
        wallet: &str,
        kind: &str,
        key: &str,
        n_events: i64,
        n_days: i64,
        surplus: Option<f64>,
        sd: Option<f64>,
    ) -> TraderSliceStat {
        TraderSliceStat {
            wallet: wallet.into(),
            slice_kind: kind.into(),
            slice_key: key.into(),
            n_events,
            n_days,
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
    fn hairline_surplus_no_cost_cushion_is_not_trusted() {
        // margin-0.0 regression: overall +2% surplus, tight sd 1% over 60
        // events → lo ≈ +1.8% > 0 (the OLD margin-0 default would certify this
        // wallet "Trusted") but < the 3% capture cushion ⇒ INDETERMINATE now.
        let slices = vec![slice("w", "overall", "", 60, Some(0.02), Some(0.01))];
        let t = trust_verdict(&slices);
        assert!(
            t.lower_bound > 0.0,
            "beats blind by a hair: lo={}",
            t.lower_bound
        );
        assert_eq!(
            t.verdict,
            TrustVerdict::Indeterminate,
            "lo={}",
            t.lower_bound
        );
    }

    #[test]
    fn trust_floor_is_25_pilot_floor_still_50() {
        // The specialist/trust floor dropped 30→25 (FORGE_PLAN Item 1 / GAP-3),
        // but the real-money pilot floor is a physically DIFFERENT struct and
        // stays at 50 — the two floors are independent by construction.
        use crate::scanner::honest::PilotThresholds;
        use crate::scanner::promotion::TrustParams;
        assert_eq!(TrustParams::default().min_events, 25);
        assert_eq!(PilotThresholds::default().min_events, 50);
        // And trust_verdict now admits a 25-event slice that the old 30 floor
        // would have rejected on N alone: this wallet has a real (non-zero)
        // computed bound rather than the floored early-return's 0.0.
        let slices = vec![slice_days(
            "w",
            "overall",
            "",
            25,
            25,
            Some(0.10),
            Some(0.06),
        )];
        let t = trust_verdict(&slices);
        assert_ne!(t.lower_bound, 0.0, "25-event slice reached evaluation");
    }

    #[test]
    fn hairline_25_event_slice_reads_indeterminate() {
        // FORGE_PLAN Item 1 concrete verdict: exactly 25 distinct events, +0.04
        // surplus, sd 0.10, 12 distinct days, ~6 sibling cells (Bonferroni).
        // Floor-25 ADMITS it (a real bound is computed, not the floored 0.0),
        // but the widened CI (eff_n=12 ⇒ se≈0.029) leaves lo≈−0.036 < the 3%
        // margin ⇒ still Indeterminate. 25 widens *eligibility*, not *false trust*.
        let mut slices = vec![slice_days(
            "w",
            "overall",
            "",
            25,
            12,
            Some(0.04),
            Some(0.10),
        )];
        for s in ["nba", "mlb", "nfl", "soccer", "tennis"] {
            slices.push(slice_days("w", "sport", s, 25, 12, Some(0.02), Some(0.10)));
        }
        let t = trust_verdict(&slices);
        assert_eq!(t.n_events, 25);
        assert!(
            t.lower_bound < 0.0,
            "admitted + evaluated (not floored 0.0): lo={}",
            t.lower_bound
        );
        assert_eq!(
            t.verdict,
            TrustVerdict::Indeterminate,
            "lo={}",
            t.lower_bound
        );
    }

    #[test]
    fn clustered_weekend_is_not_trusted() {
        // A big apparent surplus (+10%) but every event on one correlated
        // weekend (2 distinct days) → effective N 2 blows up the SE ⇒ the
        // lower bound collapses below the margin ⇒ INDETERMINATE, not Trusted.
        let clustered = vec![slice_days(
            "w",
            "overall",
            "",
            60,
            2,
            Some(0.10),
            Some(0.10),
        )];
        assert_eq!(
            trust_verdict(&clustered).verdict,
            TrustVerdict::Indeterminate
        );
        // The IDENTICAL surplus/sd spread over 60 distinct days IS Trusted —
        // the deflation discriminates, it doesn't blanket-reject.
        let spread = vec![slice_days(
            "w",
            "overall",
            "",
            60,
            60,
            Some(0.10),
            Some(0.10),
        )];
        assert_eq!(trust_verdict(&spread).verdict, TrustVerdict::Trusted);
    }

    #[test]
    fn avoid_between_neg_margin_and_zero_is_preserved() {
        // Upper bound ≈ −1.2% — worse than blind, but NOT below −3%. Pinning
        // the Avoid test at 0 (not −margin) keeps this an Avoid even though the
        // Trusted margin rose to 3%; a wider Trusted band must never shrink the
        // Avoid warning.
        let slices = vec![slice("w", "overall", "", 60, Some(-0.033), Some(0.10))];
        let t = trust_verdict(&slices);
        assert!(
            t.upper_bound < 0.0 && t.upper_bound > -0.03,
            "hi in (−3%,0): {}",
            t.upper_bound
        );
        assert_eq!(t.verdict, TrustVerdict::Avoid);
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
        // SAFETY (code-enforced, not documented): this test seeds a controlled
        // `tt_*` population and its band-blind baseline assumes trader_fills holds
        // ONLY that. Refuse to run if ANY non-`tt_` fill exists — that makes it
        // impossible to wipe a populated / prod archive (which holds `0x…`
        // wallets). Run only against a throwaway DB, serially.
        let (foreign,): (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM trader_fills WHERE wallet NOT LIKE 'tt\\_%'")
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(
            foreign, 0,
            "refusing to run: trader_fills has {foreign} non-test rows — run against a throwaway DB"
        );
        // Scoped clean (never a bare table wipe).
        sqlx::query("DELETE FROM trader_fills WHERE wallet LIKE 'tt\\_%'")
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
            // Stamp each fill on its OWN day (ts = NOW() − i days) so distinct
            // events ⇒ distinct fill-days ⇒ the day-deflated effective N equals
            // the event N (no artificial clustering). Surplus math is
            // ts-independent and no test asserts on recency, so spreading the
            // timestamps is safe. Without this, all fills share one day and the
            // trust gate's within-day deflation would collapse effective N to 1.
            sqlx::query(
                "INSERT INTO trader_fills \
                   (wallet, tx_hash, condition_id, outcome_index, outcome, side, price, size_usd, \
                    title, slug, event_slug, is_sports, sport, ts, resolved, outcome_won, advantage, resolved_at) \
                 VALUES ($1,$2,$3,0,'Yes','BUY',$4,100,'t','s',$5,true,$6, \
                         NOW() - make_interval(days => $9) - INTERVAL '1 hour',true,$7,$8,NOW())",
            )
            .bind(wallet)
            .bind(format!("{cond}_tx"))
            .bind(&cond)
            .bind(price)
            .bind(&cond) // event_slug == condition ⇒ unique event per fill
            .bind(sport)
            .bind(won)
            .bind(adv)
            .bind(i as i32)
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

        sqlx::query("DELETE FROM trader_fills WHERE wallet LIKE 'tt\\_%'")
            .execute(&pool)
            .await
            .unwrap();
        println!(
            "trust_scores_e2e: skilled=Trusted, negative=Avoid, small-N=Indeterminate, FLB neutralized — OK"
        );
    }
}
