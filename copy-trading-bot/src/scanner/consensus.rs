//! Consensus scoring engine — the heart of the consensus-alert product.
//!
//! Given the recent BUY activity of the tracked top-N leaderboard traders,
//! organised per market, this module decides when those traders have
//! **converged** on a single directional position strongly enough to be worth
//! an alert.
//!
//! ## Why naive consensus is noise (the design pivot, see CONSENSUS-ENGINE-PLAN.md)
//!
//! "≥2 top traders bought the same outcome" is dominated by confounds:
//!  - top traders sit on *both* sides of popular markets (market-makers),
//!  - the same outcome is entered across a wild price range (0.03–0.99),
//!  - one wallet laddering many fills looks like many traders.
//!
//! So this engine measures **NET directional** consensus among *distinct,
//! one-sided* wallets, and only when their entries are **price-coherent** and
//! **fresh**. Two-sided wallets (those with votes on more than one outcome of
//! the same market within the window) are treated as market-makers and dropped
//! entirely from that market's tally.
//!
//! This module is **pure** — no DB, no network, no clock side effects (the
//! caller passes `now`). That makes the scoring fully unit-testable.

use std::collections::{HashMap, HashSet};

use chrono::{DateTime, Utc};

/// One trader's BUY into a specific `(market, outcome)`.
#[derive(Debug, Clone)]
pub struct TraderVote {
    /// Lower-cased proxy wallet — the identity used for distinctness.
    pub wallet: String,
    /// Display name (username or short wallet).
    pub name: String,
    /// Leaderboard rank (1 = best), or `None` if unranked. Used for the elite check.
    pub rank: Option<i32>,
    /// Realized leaderboard PnL (USD), if known. Reserved for smart-money weighting.
    pub pnl: Option<f64>,
    /// Quality weight `w_q` derived from leaderboard standing (see [`quality_weight`]).
    pub quality: f64,
    /// Entry price the trader paid for this outcome, in (0,1).
    pub price: f64,
    /// USD size of the fill (`usdcSize`).
    pub size_usd: f64,
    /// Timestamp of the fill.
    pub ts: DateTime<Utc>,
}

/// All tracked-trader BUY votes for one market, grouped by outcome index.
#[derive(Debug, Clone)]
pub struct MarketBook {
    pub condition_id: String,
    pub title: String,
    pub slug: String,
    pub event_slug: Option<String>,
    pub is_sports: bool,
    /// outcome_index -> human label ("Yes"/"No"/team name).
    pub outcome_labels: HashMap<i32, String>,
    /// outcome_index -> votes.
    pub votes: HashMap<i32, Vec<TraderVote>>,
}

impl MarketBook {
    pub fn new(
        condition_id: impl Into<String>,
        title: impl Into<String>,
        slug: impl Into<String>,
        event_slug: Option<String>,
        is_sports: bool,
    ) -> Self {
        Self {
            condition_id: condition_id.into(),
            title: title.into(),
            slug: slug.into(),
            event_slug,
            is_sports,
            outcome_labels: HashMap::new(),
            votes: HashMap::new(),
        }
    }

    pub fn add_vote(&mut self, outcome_index: i32, label: impl Into<String>, vote: TraderVote) {
        self.outcome_labels
            .entry(outcome_index)
            .or_insert_with(|| label.into());
        self.votes.entry(outcome_index).or_default().push(vote);
    }
}

/// How a strategy treats sports/esports markets.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SportsMode {
    /// Score both sports and non-sports (incumbent behavior).
    Include,
    /// Only sports/esports markets.
    Only,
    /// Drop sports/esports markets.
    Exclude,
}

/// Which aggregate drives the composite ranking `score`. Tiering stays
/// `net_count`-based for ALL modes so STRONG/ELITE remain comparable across the
/// portfolio — only the *ranking* basis changes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WeightMode {
    /// Rank by plain net trader count.
    Count,
    /// Rank by rank-derived `net_quality` (incumbent).
    Quality,
    /// Rank by log-$ committed (whale-weighted).
    Dollars,
}

/// Tunable thresholds for the scorer. Defaults mirror `CONSENSUS-ENGINE-PLAN.md`.
/// The last four fields are additive portfolio knobs whose defaults are no-ops,
/// so `ConsensusParams::default()` is behaviorally identical to the original.
#[derive(Debug, Clone)]
pub struct ConsensusParams {
    /// Minimum number of distinct one-sided backers required.
    pub min_backers: usize,
    /// Maximum number of distinct one-sided opposers tolerated.
    pub max_opposers: usize,
    /// Maximum population std-dev of backer entry prices (price coherence).
    pub max_price_std: f64,
    /// Maximum age (minutes) of the *most recent* backer fill.
    pub max_age_mins: i64,
    /// Net-trader count (`backers − opposers`) for the STRONG tier.
    pub strong_net: i64,
    /// Net-trader count for the ELITE tier.
    pub elite_net: i64,
    /// A backer with leaderboard rank ≤ this counts as "elite" for tiering.
    pub elite_rank: i32,

    // --- additive portfolio knobs (all default to no-op) ---
    /// Require ≥1 backer with rank ≤ `elite_rank`, else drop the signal.
    pub require_elite: bool,
    /// Keep only signals whose mean entry price ∈ [lo, hi]. `None` = no band.
    pub price_band: Option<(f64, f64)>,
    /// Sports/esports treatment for this strategy.
    pub sports_mode: SportsMode,
    /// Ranking basis for the composite `score`.
    pub weight_mode: WeightMode,
}

impl Default for ConsensusParams {
    fn default() -> Self {
        Self {
            min_backers: 3,
            max_opposers: 1,
            max_price_std: 0.10,
            max_age_mins: 2880, // 48h
            strong_net: 4,
            elite_net: 6,
            elite_rank: 10,
            // no-op defaults → Default() is behaviorally unchanged
            require_elite: false,
            price_band: None,
            sports_mode: SportsMode::Include,
            weight_mode: WeightMode::Quality,
        }
    }
}

/// A named strategy: a parameter-set scored against the shared per-cycle books.
#[derive(Debug, Clone)]
pub struct StrategyDef {
    /// Stable identifier — also the DB `strategy` value and Prometheus label.
    pub name: &'static str,
    pub params: ConsensusParams,
    /// If true, STRONG/ELITE signals push Telegram. Keep exactly one strategy
    /// (the incumbent `strict`) alerting to preserve the current alert UX.
    pub alerting: bool,
}

/// Alert tier, ascending in conviction.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tier {
    /// Forming — digest only, no push.
    Watch,
    /// Push alert.
    Strong,
    /// Priority push.
    Elite,
}

impl Tier {
    pub fn as_str(&self) -> &'static str {
        match self {
            Tier::Watch => "WATCH",
            Tier::Strong => "STRONG",
            Tier::Elite => "ELITE",
        }
    }

    pub fn emoji(&self) -> &'static str {
        match self {
            Tier::Watch => "👀",
            Tier::Strong => "🟢",
            Tier::Elite => "🔥",
        }
    }

    /// Ascending conviction level (Watch=0, Strong=1, Elite=2).
    pub fn level(&self) -> u8 {
        match self {
            Tier::Watch => 0,
            Tier::Strong => 1,
            Tier::Elite => 2,
        }
    }

    /// Parse a stored tier string back into a [`Tier`] for dedup comparisons.
    pub fn from_str(s: &str) -> Option<Tier> {
        match s {
            "WATCH" => Some(Tier::Watch),
            "STRONG" => Some(Tier::Strong),
            "ELITE" => Some(Tier::Elite),
            _ => None,
        }
    }
}

/// One distinct backer of a consensus signal.
#[derive(Debug, Clone)]
pub struct BackerInfo {
    pub wallet: String,
    pub name: String,
    pub rank: Option<i32>,
}

/// A scored consensus signal for one `(market, outcome)`.
#[derive(Debug, Clone)]
pub struct ConsensusSignal {
    /// Owning strategy name. Set by [`score_all_strategies`]; [`score_market`]
    /// leaves it empty (single-definition callers / tests don't care).
    pub strategy: String,
    pub condition_id: String,
    pub outcome_index: i32,
    pub outcome_label: String,
    pub title: String,
    pub slug: String,
    pub event_slug: Option<String>,
    pub is_sports: bool,
    /// Distinct one-sided backers, sorted best-rank-first then by name.
    pub backers: Vec<BackerInfo>,
    pub n_backers: usize,
    pub n_opposers: usize,
    /// `n_backers - n_opposers` — the interpretable headline number.
    pub net_count: i64,
    /// Quality-weighted net: `Σ w_q(backers) − Σ w_q(opposers)`.
    pub net_quality: f64,
    pub mean_price: f64,
    pub price_std: f64,
    /// Age (minutes) of the most recent backer fill, relative to `now`.
    pub recency_mins: i64,
    pub total_usd: f64,
    pub best_backer_rank: Option<i32>,
    /// Composite ranking score (higher = stronger). Not a probability.
    pub score: f64,
    pub tier: Tier,
}

/// Map a leaderboard rank (1 = best) to a quality weight in roughly [1.0, 2.0].
///
/// Rank 1 ≈ 2.0, rank 50 ≈ 1.0, unranked ≈ 1.0. Kept bounded so that
/// `net_count` (a plain trader count) stays the interpretable headline while
/// `net_quality` only breaks ties / sorts.
pub fn quality_weight(rank: Option<i32>) -> f64 {
    match rank {
        Some(r) if r >= 1 => 1.0 + (50 - r.min(50)).max(0) as f64 / 50.0,
        _ => 1.0,
    }
}

fn mean_std(prices: &[f64]) -> (f64, f64) {
    if prices.is_empty() {
        return (0.0, 0.0);
    }
    let n = prices.len() as f64;
    let mean = prices.iter().sum::<f64>() / n;
    let var = prices.iter().map(|p| (p - mean).powi(2)).sum::<f64>() / n;
    (mean, var.sqrt())
}

/// Score a single market's book and return any signals at or above the WATCH gate.
///
/// `now` is injected for deterministic testing.
pub fn score_market(
    book: &MarketBook,
    now: DateTime<Utc>,
    params: &ConsensusParams,
) -> Vec<ConsensusSignal> {
    // Market-level sports gate (cheap early-out) — replaces the old cycle-level filter.
    match params.sports_mode {
        SportsMode::Include => {}
        SportsMode::Only => {
            if !book.is_sports {
                return Vec::new();
            }
        }
        SportsMode::Exclude => {
            if book.is_sports {
                return Vec::new();
            }
        }
    }

    // Identify two-sided wallets (present on >1 outcome) — dropped as MMs.
    let mut wallet_outcomes: HashMap<&str, HashSet<i32>> = HashMap::new();
    for (oidx, votes) in &book.votes {
        for v in votes {
            wallet_outcomes
                .entry(v.wallet.as_str())
                .or_default()
                .insert(*oidx);
        }
    }
    let two_sided: HashSet<&str> = wallet_outcomes
        .iter()
        .filter(|(_, outs)| outs.len() > 1)
        .map(|(w, _)| *w)
        .collect();

    // Per-outcome one-sided quality sum (and a representative vote set).
    // outcome -> (distinct wallet -> (quality, best representative vote))
    let mut clean: HashMap<i32, HashMap<&str, &TraderVote>> = HashMap::new();
    for (oidx, votes) in &book.votes {
        let entry = clean.entry(*oidx).or_default();
        for v in votes {
            if two_sided.contains(v.wallet.as_str()) {
                continue;
            }
            // Keep the *latest* fill as the representative for recency/price.
            entry
                .entry(v.wallet.as_str())
                .and_modify(|cur| {
                    if v.ts > cur.ts {
                        *cur = v;
                    }
                })
                .or_insert(v);
        }
    }

    let mut signals = Vec::new();
    for (&oidx, backers) in &clean {
        if backers.is_empty() {
            continue;
        }
        // Opposers = distinct one-sided wallets on any *other* outcome.
        let mut opposer_wallets: HashSet<&str> = HashSet::new();
        let mut opposer_quality = 0.0;
        for (&o2, b2) in &clean {
            if o2 == oidx {
                continue;
            }
            for (w, v) in b2 {
                if opposer_wallets.insert(*w) {
                    opposer_quality += v.quality;
                }
            }
        }

        let n_backers = backers.len();
        let n_opposers = opposer_wallets.len();
        let backer_quality: f64 = backers.values().map(|v| v.quality).sum();
        let net_quality = backer_quality - opposer_quality;
        let net_count = n_backers as i64 - n_opposers as i64;

        // All backer fills (not just representative) for price/size/recency.
        let all_backer_fills: Vec<&TraderVote> = book.votes[&oidx]
            .iter()
            .filter(|v| !two_sided.contains(v.wallet.as_str()))
            .collect();
        let prices: Vec<f64> = all_backer_fills.iter().map(|v| v.price).collect();
        let (mean_price, price_std) = mean_std(&prices);
        let total_usd: f64 = all_backer_fills.iter().map(|v| v.size_usd).sum();
        let latest_ts = all_backer_fills.iter().map(|v| v.ts).max().unwrap_or(now);
        let recency_mins = (now - latest_ts).num_minutes().max(0);
        let best_backer_rank = backers.values().filter_map(|v| v.rank).min();

        // --- Hard gates ---
        if n_backers < params.min_backers
            || n_opposers > params.max_opposers
            || price_std > params.max_price_std
            || recency_mins > params.max_age_mins
        {
            continue;
        }

        // Price-band predicate (longshot / favorite variants).
        if let Some((lo, hi)) = params.price_band
            && (mean_price < lo || mean_price > hi)
        {
            continue;
        }

        // Elite-required gate (elite_gated variant).
        let has_elite = backers
            .values()
            .filter_map(|v| v.rank)
            .any(|r| r <= params.elite_rank);
        if params.require_elite && !has_elite {
            continue;
        }

        // --- Composite score (ranking only) ---
        let coherence = 1.0 - (price_std / params.max_price_std).clamp(0.0, 1.0); // [0,1]
        let freshness = 1.0 - (recency_mins as f64 / params.max_age_mins as f64).clamp(0.0, 1.0); // [0,1]
        // Money factor: log-scaled, lightly weighted, capped.
        let money = (1.0 + total_usd.max(0.0)).ln();
        // Ranking base term — selectable per strategy; tiering stays net_count-based.
        let base = match params.weight_mode {
            WeightMode::Count => net_count.max(0) as f64,
            WeightMode::Quality => net_quality.max(0.0),
            WeightMode::Dollars => money,
        };
        let score = base * (0.5 + 0.5 * coherence) * (0.6 + 0.4 * freshness) * (1.0 + 0.02 * money);

        // --- Tier ---
        let tier = if net_count >= params.elite_net || (net_count >= params.strong_net && has_elite)
        {
            Tier::Elite
        } else if net_count >= params.strong_net {
            Tier::Strong
        } else {
            Tier::Watch
        };

        let mut backer_infos: Vec<BackerInfo> = backers
            .iter()
            .map(|(w, v)| BackerInfo {
                wallet: w.to_string(),
                name: v.name.clone(),
                rank: v.rank,
            })
            .collect();
        // Best (lowest) rank first; unranked last; tie-break by name.
        backer_infos.sort_by(|a, b| {
            a.rank
                .unwrap_or(i32::MAX)
                .cmp(&b.rank.unwrap_or(i32::MAX))
                .then_with(|| a.name.cmp(&b.name))
        });

        signals.push(ConsensusSignal {
            strategy: String::new(),
            condition_id: book.condition_id.clone(),
            outcome_index: oidx,
            outcome_label: book
                .outcome_labels
                .get(&oidx)
                .cloned()
                .unwrap_or_else(|| oidx.to_string()),
            title: book.title.clone(),
            slug: book.slug.clone(),
            event_slug: book.event_slug.clone(),
            is_sports: book.is_sports,
            backers: backer_infos,
            n_backers,
            n_opposers,
            net_count,
            net_quality,
            mean_price,
            price_std,
            recency_mins,
            total_usd,
            best_backer_rank,
            score,
            tier,
        });
    }

    signals
}

/// Score every market and return all signals at/above the WATCH gate, sorted by
/// descending composite score.
pub fn score_all(
    books: &[MarketBook],
    now: DateTime<Utc>,
    params: &ConsensusParams,
) -> Vec<ConsensusSignal> {
    let mut all: Vec<ConsensusSignal> = books
        .iter()
        .flat_map(|b| score_market(b, now, params))
        .collect();
    all.sort_by(|a, b| {
        b.score
            .partial_cmp(&a.score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    all
}

/// Score the SAME books under every strategy in the portfolio, tagging each
/// emitted signal with its owning strategy name. The expensive per-cycle fetch
/// and book assembly happen once upstream; this is a pure pass per strategy.
pub fn score_all_strategies(
    books: &[MarketBook],
    now: DateTime<Utc>,
    portfolio: &[StrategyDef],
) -> Vec<ConsensusSignal> {
    let mut out = Vec::new();
    for def in portfolio {
        let mut sigs = score_all(books, now, &def.params);
        for s in &mut sigs {
            s.strategy = def.name.to_string();
        }
        out.extend(sigs);
    }
    out
}

/// The recommended initial portfolio — a factorial probe where each variant
/// isolates ONE lever. Every variant derives from `base` (the incumbent
/// `strict` params from config) so global env tuning moves the whole portfolio
/// coherently. Only `strict` alerts; the rest forward-track silently.
pub fn default_portfolio(base: &ConsensusParams) -> Vec<StrategyDef> {
    vec![
        StrategyDef {
            name: "strict",
            params: base.clone(),
            alerting: true,
        },
        StrategyDef {
            name: "loose",
            params: ConsensusParams {
                min_backers: 2,
                max_opposers: 2,
                max_price_std: 0.15,
                strong_net: 3,
                elite_net: 5,
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "fresh2h",
            params: ConsensusParams {
                max_age_mins: 120,
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "longshot",
            params: ConsensusParams {
                price_band: Some((0.02, 0.35)),
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "favorite",
            params: ConsensusParams {
                price_band: Some((0.65, 0.98)),
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "sports_only",
            params: ConsensusParams {
                sports_mode: SportsMode::Only,
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "nonsports",
            params: ConsensusParams {
                sports_mode: SportsMode::Exclude,
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "elite_gated",
            params: ConsensusParams {
                require_elite: true,
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "whales",
            params: ConsensusParams {
                weight_mode: WeightMode::Dollars,
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "count",
            params: ConsensusParams {
                weight_mode: WeightMode::Count,
                ..base.clone()
            },
            alerting: false,
        },
        // --- blind-band benchmark (catalog #1): permissive capture-all arm ---
        // Records EVERY observed (market,outcome) with >=1 one-sided backer — the
        // full population, independent of any consensus gate — so the scoreboard
        // can compute surplus-over-blind per price band and neutralize the
        // favorite-longshot bias that games raw AVG(won - entry). Never alerts.
        StrategyDef {
            name: "_blind",
            params: ConsensusParams {
                min_backers: 1,
                max_opposers: usize::MAX,
                max_price_std: 1.0,
                max_age_mins: i64::MAX,
                strong_net: i64::MAX,
                elite_net: i64::MAX,
                require_elite: false,
                price_band: None,
                sports_mode: SportsMode::Include,
                weight_mode: WeightMode::Count,
                ..base.clone()
            },
            alerting: false,
        },
        // --- strategy-foundry quick-wins (2026-06-28 catalog, pre-registered) ---
        // Denser, tighter-agreeing sharp cluster than `strict` tolerates.
        StrategyDef {
            name: "tight_cluster",
            params: ConsensusParams {
                min_backers: 4,
                max_opposers: 0,
                max_price_std: 0.04,
                max_age_mins: 720,
                ..base.clone()
            },
            alerting: false,
        },
        // Fresh elite-sharp entry in the favorite tail (the one FLB region with
        // documented positive net returns). Decisive control = beat blind-favorite-band.
        StrategyDef {
            name: "elite_fresh_fav",
            params: ConsensusParams {
                require_elite: true,
                price_band: Some((0.80, 0.97)),
                max_age_mins: 180,
                ..base.clone()
            },
            alerting: false,
        },
        // Favorite-tail FLB MEASUREMENT probe (non-sports). Expected to collapse to
        // blind-by-band — kept as an instrument, NOT a promotable edge.
        StrategyDef {
            name: "favorite_tail",
            params: ConsensusParams {
                price_band: Some((0.85, 0.96)),
                sports_mode: SportsMode::Exclude,
                ..base.clone()
            },
            alerting: false,
        },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Duration;

    fn vote(
        wallet: &str,
        rank: Option<i32>,
        price: f64,
        age_mins: i64,
        now: DateTime<Utc>,
    ) -> TraderVote {
        TraderVote {
            wallet: wallet.to_string(),
            name: wallet.to_string(),
            rank,
            pnl: None,
            quality: quality_weight(rank),
            price,
            size_usd: 1000.0,
            ts: now - Duration::minutes(age_mins),
        }
    }

    fn book_with(now: DateTime<Utc>, votes: Vec<(i32, &str, Option<i32>, f64, i64)>) -> MarketBook {
        let mut b = MarketBook::new(
            "0xcond",
            "Will X happen?",
            "x-slug",
            Some("x-event".into()),
            false,
        );
        for (oidx, w, rank, price, age) in votes {
            let label = if oidx == 0 { "Yes" } else { "No" };
            b.add_vote(oidx, label, vote(w, rank, price, age, now));
        }
        b
    }

    #[test]
    fn clean_consensus_fires_strong() {
        let now = Utc::now();
        // 4 distinct one-sided backers on Yes, tight prices, fresh, no opposers.
        let b = book_with(
            now,
            vec![
                (0, "wa", Some(5), 0.50, 10),
                (0, "wb", Some(20), 0.51, 20),
                (0, "wc", Some(30), 0.49, 30),
                (0, "wd", Some(40), 0.52, 40),
            ],
        );
        let sigs = score_market(&b, now, &ConsensusParams::default());
        assert_eq!(sigs.len(), 1);
        let s = &sigs[0];
        assert_eq!(s.n_backers, 4);
        assert_eq!(s.n_opposers, 0);
        assert_eq!(s.net_count, 4);
        // rank 5 backer present, net>=strong → elite via has_elite path? elite_rank=10, rank5<=10
        assert_eq!(s.tier, Tier::Elite);
        assert!(s.price_std <= 0.10);
    }

    #[test]
    fn below_min_backers_is_rejected() {
        let now = Utc::now();
        let b = book_with(
            now,
            vec![(0, "wa", Some(5), 0.5, 10), (0, "wb", Some(6), 0.5, 10)],
        );
        let sigs = score_market(&b, now, &ConsensusParams::default());
        assert!(sigs.is_empty(), "2 backers < min_backers(3) must reject");
    }

    #[test]
    fn opposers_over_cap_reject() {
        let now = Utc::now();
        // 3 on Yes, 2 distinct one-sided on No → opposers=2 > max_opposers(1).
        let b = book_with(
            now,
            vec![
                (0, "wa", None, 0.5, 5),
                (0, "wb", None, 0.5, 5),
                (0, "wc", None, 0.5, 5),
                (1, "wx", None, 0.5, 5),
                (1, "wy", None, 0.5, 5),
            ],
        );
        let sigs = score_market(&b, now, &ConsensusParams::default());
        // Yes side has 2 opposers → rejected. No side has 3 opposers → rejected.
        assert!(sigs.is_empty());
    }

    #[test]
    fn two_sided_wallet_is_dropped_as_mm() {
        let now = Utc::now();
        // wm trades BOTH sides → dropped everywhere.
        // Real one-sided backers on Yes: wa, wb, wc (3). Opposers: none (wm dropped).
        let mut b = book_with(
            now,
            vec![
                (0, "wa", None, 0.5, 5),
                (0, "wb", None, 0.5, 5),
                (0, "wc", None, 0.5, 5),
                (0, "wm", None, 0.5, 5),
                (1, "wm", None, 0.5, 5),
            ],
        );
        let _ = &mut b;
        let sigs = score_market(&b, now, &ConsensusParams::default());
        assert_eq!(sigs.len(), 1, "Yes should fire; wm excluded both sides");
        assert_eq!(sigs[0].n_backers, 3);
        assert_eq!(sigs[0].n_opposers, 0);
    }

    #[test]
    fn price_dispersion_rejects() {
        let now = Utc::now();
        let b = book_with(
            now,
            vec![
                (0, "wa", None, 0.20, 5),
                (0, "wb", None, 0.50, 5),
                (0, "wc", None, 0.90, 5),
            ],
        );
        let sigs = score_market(&b, now, &ConsensusParams::default());
        assert!(sigs.is_empty(), "wide price std must reject");
    }

    #[test]
    fn stale_rejects() {
        let now = Utc::now();
        let b = book_with(
            now,
            vec![
                (0, "wa", None, 0.5, 5000),
                (0, "wb", None, 0.5, 5000),
                (0, "wc", None, 0.5, 5000),
            ],
        );
        let sigs = score_market(&b, now, &ConsensusParams::default());
        assert!(sigs.is_empty(), "all fills >48h old must reject");
    }

    #[test]
    fn laddering_one_wallet_counts_once() {
        let now = Utc::now();
        // wa fills 5x on Yes; wb, wc once. Distinct backers = 3, not 7.
        let b = book_with(
            now,
            vec![
                (0, "wa", None, 0.50, 5),
                (0, "wa", None, 0.51, 6),
                (0, "wa", None, 0.49, 7),
                (0, "wa", None, 0.50, 8),
                (0, "wa", None, 0.50, 9),
                (0, "wb", None, 0.50, 5),
                (0, "wc", None, 0.50, 5),
            ],
        );
        let sigs = score_market(&b, now, &ConsensusParams::default());
        assert_eq!(sigs.len(), 1);
        assert_eq!(sigs[0].n_backers, 3, "one wallet's many fills = one backer");
    }

    #[test]
    fn quality_weight_monotonic() {
        assert!(quality_weight(Some(1)) > quality_weight(Some(10)));
        assert!(quality_weight(Some(10)) > quality_weight(Some(50)));
        assert_eq!(quality_weight(Some(60)), quality_weight(None));
    }

    #[test]
    fn elite_tier_requires_elite_rank_or_high_net() {
        let now = Utc::now();
        // 4 backers all unranked → net 4 = strong, but no elite rank → STRONG not ELITE.
        let b = book_with(
            now,
            vec![
                (0, "wa", None, 0.50, 5),
                (0, "wb", None, 0.51, 5),
                (0, "wc", None, 0.49, 5),
                (0, "wd", None, 0.50, 5),
            ],
        );
        let sigs = score_market(&b, now, &ConsensusParams::default());
        assert_eq!(sigs[0].tier, Tier::Strong);

        // Same but 6 backers → net 6 >= elite_net → ELITE even without elite rank.
        let b2 = book_with(
            now,
            vec![
                (0, "wa", None, 0.50, 5),
                (0, "wb", None, 0.51, 5),
                (0, "wc", None, 0.49, 5),
                (0, "wd", None, 0.50, 5),
                (0, "we", None, 0.50, 5),
                (0, "wf", None, 0.50, 5),
            ],
        );
        let sigs2 = score_market(&b2, now, &ConsensusParams::default());
        assert_eq!(sigs2[0].tier, Tier::Elite);
    }

    // --- strategy-portfolio knobs ---

    #[test]
    fn price_band_gates_on_mean_price() {
        let now = Utc::now();
        // 3 backers at ~0.80 → favorite-band passes, longshot-band rejects.
        let b = book_with(
            now,
            vec![
                (0, "wa", None, 0.80, 5),
                (0, "wb", None, 0.81, 5),
                (0, "wc", None, 0.79, 5),
            ],
        );
        let favorite = ConsensusParams {
            price_band: Some((0.65, 0.98)),
            ..ConsensusParams::default()
        };
        let longshot = ConsensusParams {
            price_band: Some((0.02, 0.35)),
            ..ConsensusParams::default()
        };
        assert_eq!(
            score_market(&b, now, &favorite).len(),
            1,
            "0.80 ∈ favorite band"
        );
        assert!(
            score_market(&b, now, &longshot).is_empty(),
            "0.80 ∉ longshot band"
        );
    }

    #[test]
    fn require_elite_gate() {
        let now = Utc::now();
        // 3 unranked backers — fine for default, rejected when require_elite.
        let b = book_with(
            now,
            vec![
                (0, "wa", None, 0.50, 5),
                (0, "wb", None, 0.50, 5),
                (0, "wc", None, 0.50, 5),
            ],
        );
        assert_eq!(score_market(&b, now, &ConsensusParams::default()).len(), 1);
        let elite = ConsensusParams {
            require_elite: true,
            ..ConsensusParams::default()
        };
        assert!(score_market(&b, now, &elite).is_empty());
        // Add a top-10 ranked backer → passes require_elite.
        let b2 = book_with(
            now,
            vec![
                (0, "wa", Some(3), 0.50, 5),
                (0, "wb", None, 0.50, 5),
                (0, "wc", None, 0.50, 5),
            ],
        );
        assert_eq!(score_market(&b2, now, &elite).len(), 1);
    }

    #[test]
    fn sports_mode_filters_market() {
        let now = Utc::now();
        let mut sportsbook = book_with(
            now,
            vec![
                (0, "wa", None, 0.50, 5),
                (0, "wb", None, 0.50, 5),
                (0, "wc", None, 0.50, 5),
            ],
        );
        sportsbook.is_sports = true;
        let only = ConsensusParams {
            sports_mode: SportsMode::Only,
            ..ConsensusParams::default()
        };
        let exclude = ConsensusParams {
            sports_mode: SportsMode::Exclude,
            ..ConsensusParams::default()
        };
        assert_eq!(
            score_market(&sportsbook, now, &only).len(),
            1,
            "sports market kept by Only"
        );
        assert!(
            score_market(&sportsbook, now, &exclude).is_empty(),
            "sports market dropped by Exclude"
        );
    }

    #[test]
    fn score_all_strategies_tags_and_runs_portfolio() {
        let now = Utc::now();
        let b = book_with(
            now,
            vec![
                (0, "wa", Some(5), 0.50, 5),
                (0, "wb", Some(20), 0.51, 5),
                (0, "wc", Some(30), 0.49, 5),
                (0, "wd", Some(40), 0.50, 5),
            ],
        );
        let portfolio = default_portfolio(&ConsensusParams::default());
        let sigs = score_all_strategies(&[b], now, &portfolio);
        // strict + loose + fresh2h + favorite(0.50∉) ... at least strict & loose fire.
        assert!(sigs.iter().any(|s| s.strategy == "strict"));
        assert!(
            sigs.iter().all(|s| !s.strategy.is_empty()),
            "every signal tagged"
        );
        // longshot (band 0.02-0.35) must NOT fire on a 0.50 market.
        assert!(!sigs.iter().any(|s| s.strategy == "longshot"));
    }

    #[test]
    fn default_strict_is_non_regressive() {
        // The portfolio's `strict` params must equal ConsensusParams::default-derived base,
        // i.e. score identically to the pre-portfolio scorer on a representative book.
        let now = Utc::now();
        let b = book_with(
            now,
            vec![
                (0, "wa", Some(5), 0.50, 10),
                (0, "wb", Some(20), 0.51, 20),
                (0, "wc", Some(30), 0.49, 30),
                (0, "wd", Some(40), 0.52, 40),
            ],
        );
        let base = ConsensusParams::default();
        let strict = &default_portfolio(&base)[0];
        assert_eq!(strict.name, "strict");
        assert!(strict.alerting, "strict is the sole alerter");
        let a = score_market(&b, now, &base);
        let c = score_market(&b, now, &strict.params);
        assert_eq!(a.len(), c.len());
        assert_eq!(a[0].tier, c[0].tier);
        assert_eq!(a[0].net_count, c[0].net_count);
        assert!((a[0].score - c[0].score).abs() < 1e-12);
    }
}
