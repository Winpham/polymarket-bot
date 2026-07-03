//! Earned deep-sharp promotion pass + shadow consensus impact (deep-pool edge
//! run, Phase 0).
//!
//! Two pure halves, both reusing the existing belief-blind machinery — NO new
//! gate, baseline, or statistic:
//!  - [`promotable_deep_sharps`]: which tracked DEEP traders (rank past the
//!    consensus cutoff, not yet voting) have a gate-Trusted `trust_verdict`
//!    (surplus lower bound > capture margin over ≥30 distinct resolved events,
//!    Bonferroni-corrected, day-deflated). These are the "⤴ promotable" leads.
//!  - [`shadow_impact`]: what the live strategies WOULD emit right now if the
//!    certified deep sharps voted — scored over the same trailing window with
//!    the same scorer, diffed against the live (eligible-only) result. Purely
//!    a measurement: nothing here alerts, upserts, or mutates eligibility.
//!
//! The only thing that ever changes live behavior is the flag-gated
//! (`EARN_DEEP_SHARPS`) flip of `followed_traders.earned_eligible` in the slow
//! trust-refresh task — and that flips ONLY wallets this pass certifies.

use std::collections::{HashMap, HashSet};

use chrono::{DateTime, Utc};

use crate::cycles::consensus_cycle::TrustMap;
use crate::scanner::consensus::{ConsensusSignal, MarketBook, StrategyDef, Tier};
use crate::scanner::trader_trust::{TraderTrust, TrustVerdict};
use crate::storage::postgres::FollowedTrader;

/// One deep trader's promotion-pass record: its earned-trust verdict joined with
/// its tracking provenance (rank + current eligibility flags).
#[derive(Debug, Clone)]
pub struct DeepSharp {
    pub wallet: String,
    pub rank: Option<i32>,
    /// Already earned in (durable flag set) — surfaced, never re-flipped.
    pub earned: bool,
    pub trust: TraderTrust,
}

/// The promotion pass: every tracked DEEP leaderboard trader (not rank-eligible)
/// with a resolved profile, its verdict, and whether it clears the gate. Pure:
/// the caller supplies the active traders and the trust map (both already
/// maintained elsewhere). Wallet join is lower-cased — `trader_fills` (and so
/// the trust map) key on lower-cased wallets while `followed_traders` preserves
/// the API casing. Sorted: gate-clearers first (by lower bound), then by
/// events accrued (closest to the floor first).
pub fn deep_sharp_pass(traders: &[FollowedTrader], trust: &TrustMap) -> Vec<DeepSharp> {
    let mut out: Vec<DeepSharp> = traders
        .iter()
        .filter(|t| t.active && t.source == "leaderboard" && !t.consensus_eligible)
        .filter_map(|t| {
            let trust = trust.get(&t.proxy_wallet.to_lowercase())?;
            (trust.n_events > 0).then(|| DeepSharp {
                wallet: t.proxy_wallet.clone(),
                rank: t.rank,
                earned: t.earned_eligible,
                trust: trust.clone(),
            })
        })
        .collect();
    out.sort_by(|a, b| {
        let key = |d: &DeepSharp| match d.trust.verdict {
            TrustVerdict::Trusted => (0, -d.trust.lower_bound),
            TrustVerdict::Indeterminate => (1, -(d.trust.n_events as f64)),
            TrustVerdict::Avoid => (2, -d.trust.upper_bound),
        };
        key(a)
            .partial_cmp(&key(b))
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    out
}

/// The gate-clearing subset of [`deep_sharp_pass`] — the wallets the flag-gated
/// earn job may flip (and the shadow study votes in).
pub fn promotable_deep_sharps(pass: &[DeepSharp]) -> Vec<&DeepSharp> {
    pass.iter()
        .filter(|d| matches!(d.trust.verdict, TrustVerdict::Trusted))
        .collect()
}

/// Per-strategy shadow diff: live (eligible-only) vs shadow (eligible +
/// certified deep sharps) over the identical window and scorer.
#[derive(Debug, Clone, Default)]
pub struct StrategyShadow {
    pub strategy: String,
    /// (watch, strong, elite) counts in the LIVE scoring.
    pub live_tiers: (usize, usize, usize),
    /// (watch, strong, elite) counts in the SHADOW scoring.
    pub shadow_tiers: (usize, usize, usize),
    /// (market, outcome) pairs that fire in shadow but not live.
    pub new_signals: usize,
    /// Fired-in-both pairs whose tier rose in shadow.
    pub tier_upgrades: usize,
    /// Sum of net_count deltas over fired-in-both pairs (shadow − live).
    pub net_count_delta: i64,
}

/// The whole shadow measurement for one render: which certified deep sharps
/// voted, how many of their window votes were added, and the per-strategy diff.
#[derive(Debug, Clone, Default)]
pub struct ShadowImpact {
    /// Lower-cased wallets whose excluded votes were let into the shadow book.
    pub voters: usize,
    /// Window vote atoms those voters added.
    pub votes_added: usize,
    pub strategies: Vec<StrategyShadow>,
}

fn tier_counts(sigs: &[&ConsensusSignal]) -> (usize, usize, usize) {
    let c = |t: Tier| sigs.iter().filter(|s| s.tier == t).count();
    (c(Tier::Watch), c(Tier::Strong), c(Tier::Elite))
}

/// Compute the shadow impact. `live_books` are the books the engine actually
/// scores (eligible votes only); `shadow_books` are the same votes PLUS the
/// certified deep sharps' currently-excluded votes (the caller builds both with
/// the one shared book builder so this stays a controlled A/B). Both sides are
/// scored with the identical portfolio + `now`; the diff keys on
/// `(strategy, condition_id, outcome_index)`.
pub fn shadow_impact(
    live_books: &[MarketBook],
    shadow_books: &[MarketBook],
    portfolio: &[StrategyDef],
    now: DateTime<Utc>,
    voters: usize,
    votes_added: usize,
) -> ShadowImpact {
    let live = crate::scanner::consensus::score_all_strategies(live_books, now, portfolio);
    let shadow = crate::scanner::consensus::score_all_strategies(shadow_books, now, portfolio);

    let mut strategies = Vec::new();
    for def in portfolio {
        let l: Vec<&ConsensusSignal> = live.iter().filter(|s| s.strategy == def.name).collect();
        let s: Vec<&ConsensusSignal> = shadow.iter().filter(|s| s.strategy == def.name).collect();
        let lk: HashMap<(&str, i32), &ConsensusSignal> = l
            .iter()
            .map(|x| ((x.condition_id.as_str(), x.outcome_index), *x))
            .collect();
        let sk: HashSet<(&str, i32)> = s
            .iter()
            .map(|x| (x.condition_id.as_str(), x.outcome_index))
            .collect();

        let mut new_signals = 0usize;
        let mut tier_upgrades = 0usize;
        let mut net_count_delta = 0i64;
        for sig in &s {
            match lk.get(&(sig.condition_id.as_str(), sig.outcome_index)) {
                None => new_signals += 1,
                Some(lv) => {
                    if sig.tier.level() > lv.tier.level() {
                        tier_upgrades += 1;
                    }
                    net_count_delta += sig.net_count - lv.net_count;
                }
            }
        }
        // A live signal DISAPPEARING in shadow is possible too (a deep sharp on
        // the other side pushes opposers past the cap) — fold it in as a negative
        // "new" count would be confusing, so it rides in net_count_delta only via
        // the pairs that fired in both; the tier counts show the aggregate move.
        let _ = &sk;

        strategies.push(StrategyShadow {
            strategy: def.name.to_string(),
            live_tiers: tier_counts(&l),
            shadow_tiers: tier_counts(&s),
            new_signals,
            tier_upgrades,
            net_count_delta,
        });
    }

    ShadowImpact {
        voters,
        votes_added,
        strategies,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scanner::consensus::{ConsensusParams, default_portfolio};
    use crate::storage::consensus::WindowVote;

    fn trader(wallet: &str, rank: i32, eligible: bool, earned: bool) -> FollowedTrader {
        FollowedTrader {
            id: 0,
            proxy_wallet: wallet.to_string(),
            username: None,
            source: "leaderboard".into(),
            rank: Some(rank),
            pnl: None,
            volume: None,
            win_rate: None,
            added_at: Utc::now(),
            last_checked_at: None,
            active: true,
            consensus_eligible: eligible,
            earned_eligible: earned,
        }
    }

    fn trust_entry(wallet: &str, verdict: TrustVerdict, n_events: i64, lb: f64) -> TraderTrust {
        TraderTrust {
            wallet: wallet.to_string(),
            verdict,
            n_events,
            lower_bound: lb,
            upper_bound: lb + 0.10,
            surplus: lb + 0.05,
            best_slices: vec![],
            worst_slices: vec![],
            cells: Default::default(),
        }
    }

    #[test]
    fn pass_selects_deep_only_and_ranks_gate_clearers_first() {
        // Mixed-case wallet proves the lower-cased trust-map join.
        let traders = vec![
            trader("0xHot", 5, true, false),      // eligible — never in the pass
            trader("0xDeepA", 120, false, false), // certified
            trader("0xdeepb", 180, false, false), // indeterminate
            trader("0xdeepc", 90, false, true),   // certified + already earned
            trader("0xdeepd", 300, false, false), // no profile → dropped
        ];
        let mut trust = TrustMap::new();
        trust.insert(
            "0xhot".into(),
            trust_entry("0xhot", TrustVerdict::Trusted, 90, 0.09),
        );
        trust.insert(
            "0xdeepa".into(),
            trust_entry("0xdeepa", TrustVerdict::Trusted, 40, 0.06),
        );
        trust.insert(
            "0xdeepb".into(),
            trust_entry("0xdeepb", TrustVerdict::Indeterminate, 21, 0.0),
        );
        trust.insert(
            "0xdeepc".into(),
            trust_entry("0xdeepc", TrustVerdict::Trusted, 55, 0.08),
        );

        let pass = deep_sharp_pass(&traders, &trust);
        assert_eq!(pass.len(), 3, "deep + profiled only: {pass:?}");
        // Gate-clearers first, best lower bound first.
        assert_eq!(pass[0].wallet, "0xdeepc");
        assert!(pass[0].earned, "already-earned flag rides along");
        assert_eq!(pass[1].wallet, "0xDeepA");
        assert_eq!(pass[2].wallet, "0xdeepb");

        let promo = promotable_deep_sharps(&pass);
        assert_eq!(promo.len(), 2, "only Trusted verdicts are promotable");
        // The earn job flips only NOT-yet-earned clearers.
        let to_earn: Vec<&str> = promo
            .iter()
            .filter(|d| !d.earned)
            .map(|d| d.wallet.as_str())
            .collect();
        assert_eq!(to_earn, vec!["0xDeepA"]);
    }

    fn wvote(wallet: &str, cond: &str, oidx: i32, price: f64, rank: Option<i32>) -> WindowVote {
        WindowVote {
            trader_wallet: wallet.into(),
            name: wallet.into(),
            rank,
            pnl: None,
            quality: crate::scanner::consensus::quality_weight(rank),
            condition_id: cond.into(),
            outcome_index: oidx,
            outcome: "Yes".into(),
            title: "Team A vs Team B".into(),
            slug: "nba-a-b-2026".into(),
            event_slug: None,
            is_sports: true,
            price,
            size_usd: 1000.0,
            ts: Utc::now() - chrono::Duration::minutes(10),
        }
    }

    #[test]
    fn shadow_impact_measures_deltas_without_touching_live() {
        let now = Utc::now();
        let trust = TrustMap::new();
        let portfolio = default_portfolio(&ConsensusParams::default());

        // Live: 3 eligible backers on market m1 (strict fires WATCH, net 3) and
        // only 2 on m2 (strict does NOT fire).
        let live_votes = vec![
            wvote("0xe1", "m1", 0, 0.50, Some(5)),
            wvote("0xe2", "m1", 0, 0.51, Some(12)),
            wvote("0xe3", "m1", 0, 0.49, Some(30)),
            wvote("0xe1", "m2", 0, 0.60, Some(5)),
            wvote("0xe2", "m2", 0, 0.61, Some(12)),
        ];
        // Certified deep sharps add: 3 more on m1 (WATCH → net 6 = ELITE) and a
        // 3rd backer on m2 (a brand-new strict signal).
        let deep_votes = [
            wvote("0xd1", "m1", 0, 0.52, Some(120)),
            wvote("0xd2", "m1", 0, 0.50, Some(150)),
            wvote("0xd3", "m1", 0, 0.51, Some(200)),
            wvote("0xd1", "m2", 0, 0.62, Some(120)),
        ];
        let shadow_votes: Vec<WindowVote> = live_votes
            .iter()
            .chain(deep_votes.iter())
            .cloned()
            .collect();

        let live_books =
            crate::cycles::consensus_cycle::books_from_window_votes(&live_votes, &trust);
        let shadow_books =
            crate::cycles::consensus_cycle::books_from_window_votes(&shadow_votes, &trust);

        let impact = shadow_impact(&live_books, &shadow_books, &portfolio, now, 3, 4);
        assert_eq!((impact.voters, impact.votes_added), (3, 4));
        let strict = impact
            .strategies
            .iter()
            .find(|s| s.strategy == "strict")
            .unwrap();
        assert_eq!(strict.live_tiers, (1, 0, 0), "live: one WATCH on m1");
        assert_eq!(
            strict.shadow_tiers,
            (1, 0, 1),
            "shadow: m1 ELITE + m2 new WATCH"
        );
        assert_eq!(strict.new_signals, 1, "m2 appears only in shadow");
        assert_eq!(strict.tier_upgrades, 1, "m1 WATCH → ELITE");
        assert_eq!(strict.net_count_delta, 3, "m1 net 3 → 6");
    }

    #[test]
    fn shadow_impact_is_zero_when_no_deep_votes() {
        // The controlled A/B degenerates correctly: identical inputs ⇒ zero diff
        // (this is the always-on live case while EARN_DEEP_SHARPS is off and no
        // certified sharp exists).
        let now = Utc::now();
        let trust = TrustMap::new();
        let portfolio = default_portfolio(&ConsensusParams::default());
        let votes = vec![
            wvote("0xe1", "m1", 0, 0.50, Some(5)),
            wvote("0xe2", "m1", 0, 0.51, Some(12)),
            wvote("0xe3", "m1", 0, 0.49, Some(30)),
        ];
        let books = crate::cycles::consensus_cycle::books_from_window_votes(&votes, &trust);
        let impact = shadow_impact(&books, &books, &portfolio, now, 0, 0);
        for s in &impact.strategies {
            assert_eq!(s.live_tiers, s.shadow_tiers, "{}", s.strategy);
            assert_eq!(s.new_signals, 0);
            assert_eq!(s.tier_upgrades, 0);
            assert_eq!(s.net_count_delta, 0);
        }
    }

    // --- Report harness: run the REAL promotion pass + shadow study over a DB
    //     snapshot and print it. Read-only; `#[ignore]`d. Point $DATABASE_URL at
    //     a RESTORED BACKUP (never prod):
    //
    //   DATABASE_URL=postgres://bot:bot@localhost:55498/polymarket \
    //     cargo test -p copy-trading-bot report_deep_sharp_pass -- --ignored --nocapture
    #[tokio::test]
    #[ignore = "report harness: run against a restored snapshot at $DATABASE_URL"]
    async fn report_deep_sharp_pass() {
        use crate::storage::postgres::PgPortfolio;

        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL");
        let pool = sqlx::PgPool::connect(&url).await.unwrap();
        let pf = PgPortfolio::new(pool).await.unwrap();

        let trust = crate::cycles::consensus_cycle::compute_trust_map(&pf, false).await;
        let traders = pf.get_active_traders().await.unwrap();
        let pass = deep_sharp_pass(&traders, &trust);
        println!("=== deep-sharp promotion pass: {} profiled ===", pass.len());
        for d in &pass {
            println!(
                "{} rank={:>4} N={:>4} surplus={:+.3} lb={:+.3} ub={:+.3} {}{}",
                d.trust.verdict.marker(),
                d.rank.map(|r| r.to_string()).unwrap_or("—".into()),
                d.trust.n_events,
                d.trust.surplus,
                d.trust.lower_bound,
                d.trust.upper_bound,
                d.wallet.chars().take(14).collect::<String>(),
                if d.earned { " [earned]" } else { "" },
            );
        }
        let promo = promotable_deep_sharps(&pass);
        println!(
            "promotable: {} · earned: {}",
            promo.iter().filter(|d| !d.earned).count(),
            pass.iter().filter(|d| d.earned).count()
        );

        // Shadow study over the snapshot's current window (48h default).
        let voters: std::collections::HashSet<String> = promo
            .iter()
            .filter(|d| !d.earned)
            .map(|d| d.wallet.to_lowercase())
            .collect();
        if voters.is_empty() {
            println!("shadow: no certified-but-unearned sharps — zero impact.");
            return;
        }
        let since = Utc::now() - chrono::Duration::hours(48);
        let live = pf.load_window_votes(since).await.unwrap();
        let excl = pf.load_excluded_window_votes(since).await.unwrap();
        let added: Vec<_> = excl
            .into_iter()
            .filter(|v| voters.contains(&v.trader_wallet))
            .collect();
        let all: Vec<_> = live.iter().chain(added.iter()).cloned().collect();
        let lb = crate::cycles::consensus_cycle::books_from_window_votes(&live, &trust);
        let sb = crate::cycles::consensus_cycle::books_from_window_votes(&all, &trust);
        let portfolio = default_portfolio(&ConsensusParams::default());
        let impact = shadow_impact(&lb, &sb, &portfolio, Utc::now(), voters.len(), added.len());
        println!(
            "=== shadow: {} voter(s), {} votes added ===",
            impact.voters, impact.votes_added
        );
        for s in &impact.strategies {
            if s.strategy == "strict"
                || s.new_signals > 0
                || s.tier_upgrades > 0
                || s.net_count_delta != 0
            {
                println!(
                    "{:<16} live W/S/E {}/{}/{} → shadow {}/{}/{} · new={} upg={} Δnet={:+}",
                    s.strategy,
                    s.live_tiers.0,
                    s.live_tiers.1,
                    s.live_tiers.2,
                    s.shadow_tiers.0,
                    s.shadow_tiers.1,
                    s.shadow_tiers.2,
                    s.new_signals,
                    s.tier_upgrades,
                    s.net_count_delta,
                );
            }
        }
    }
}
