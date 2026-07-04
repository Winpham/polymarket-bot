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
use std::sync::Arc;

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
    /// EARNED quality weight (Phase 4): a trust-regularized multiplier from the
    /// cached trust map, or `quality_weight(rank)` when the trader is untracked /
    /// INDETERMINATE (never 0). Only `WeightMode::TrustWeighted` reads this, so it
    /// defaults to `quality` and leaves every other mode byte-identical.
    pub earned_quality: f64,
    /// Per-CELL earned quality (FORGE_PLAN Item 3): `earned_quality` shrunk toward
    /// the trader's cell-specific multiplier for THIS market's sport by
    /// `N_cell/(N_cell+K)`. Only `WeightMode::CellPooled` reads it; defaults to
    /// `earned_quality` (⇒ `CellPooled` == `TrustWeighted` when pooling is off or
    /// the trader has no cell data), leaving every other mode byte-identical.
    pub cell_earned_quality: f64,
    /// Whether this trader is gate-Trusted (Phase 4). Only `trusted_only`
    /// strategies read it; defaults to `true` so it drops nothing elsewhere.
    /// NB: deliberately lenient — an UNPROFILED/untracked trader counts `true`
    /// (so `trusted_only` never drops brand-new traders).
    pub trusted: bool,
    /// STRICT certification (deep-pool edge run, Phase 3): `true` ONLY for a
    /// trader whose `trust_verdict` is Trusted — an unprofiled/untracked trader
    /// is `false` (fail-closed), unlike `trusted`. Read only by
    /// `certified_only` strategies (the tail-the-sharp arms), so everything
    /// else is byte-identical regardless of its value.
    pub certified: bool,
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
    /// Rank by summed EARNED-trust quality of the backers (Phase 4). Tiering
    /// still keys on `net_count`, so this changes only the composite ranking.
    TrustWeighted,
    /// Rank by summed POOLED per-cell earned quality of the backers (FORGE_PLAN
    /// Item 3): each vote weighted by the trader's edge in THIS market's sport
    /// cell, partial-pooled toward their overall multiplier. Tiering still keys on
    /// `net_count`. With `cell_earned_quality == earned_quality` (pooling off) this
    /// is identical to `TrustWeighted`.
    CellPooled,
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
    /// Count only gate-Trusted backers/opposers (Phase 4). Default `false` =
    /// every vote counts (incumbent). With default `TraderVote.trusted == true`,
    /// this drops nothing, so it's a no-op until the trust map marks traders.
    pub trusted_only: bool,
    /// Cross-cohort conviction gate (deep-pool edge run, Phase 2): with
    /// `Some(cutoff)`, a signal fires only when its backers include BOTH a
    /// whale (rank ≤ cutoff) AND a certified deep sharp (gate-Trusted with
    /// rank > cutoff). Deep sharps enter live books only once EARNED in, so
    /// this arm emits nothing until then — silent by construction. Default
    /// `None` = no-op (incumbent behavior).
    pub cross_cohort_cutoff: Option<i32>,
    /// Count only STRICTLY certified backers/opposers (Phase 3 tail arms):
    /// unlike `trusted_only`, an unprofiled trader does NOT count. Default
    /// `false` = no-op (the field is never read).
    pub certified_only: bool,
    /// Proven-trader router follow-set (PREREG 2026-07-04, paper-only): with
    /// `Some(set)`, ONLY votes from these (lower-cased) wallets count — the
    /// scorecard-proven wallets from `router_followset`. FAIL-CLOSED: an empty
    /// set counts nothing (the arm fires nothing until a re-score qualifies
    /// wallets). Default `None` = no-op for every other strategy.
    pub router_set: Option<Arc<HashSet<String>>>,
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
            trusted_only: false,
            cross_cohort_cutoff: None,
            certified_only: false,
            router_set: None,
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

    // `trusted_only` strategies count only gate-Trusted votes. Filter them out up
    // front so two-sided detection, backers, opposers, and the price/size/recency
    // aggregation all see a consistent trusted-only view. With default votes
    // (`trusted == true`) this drops nothing.
    let keep = |v: &TraderVote| {
        (!params.trusted_only || v.trusted)
            && (!params.certified_only || v.certified)
            // Router membership: votes are lower-cased at book assembly, and the
            // follow-set is lower-cased at publish, so `contains` is exact.
            && params
                .router_set
                .as_deref()
                .is_none_or(|s| s.contains(v.wallet.as_str()))
    };

    // Identify two-sided wallets (present on >1 outcome) — dropped as MMs.
    let mut wallet_outcomes: HashMap<&str, HashSet<i32>> = HashMap::new();
    for (oidx, votes) in &book.votes {
        for v in votes {
            if !keep(v) {
                continue;
            }
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
            if two_sided.contains(v.wallet.as_str()) || !keep(v) {
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
            .filter(|v| !two_sided.contains(v.wallet.as_str()) && keep(v))
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

        // Cross-cohort conviction gate (cross_cohort variant): a whale AND a
        // certified deep sharp must both back. `trusted` rides on the vote (from
        // the trust map); a deep backer can only be in a live book if earned in.
        if let Some(cut) = params.cross_cohort_cutoff {
            let has_whale = backers.values().filter_map(|v| v.rank).any(|r| r <= cut);
            let has_deep_sharp = backers
                .values()
                .any(|v| v.certified && v.rank.is_some_and(|r| r > cut));
            if !(has_whale && has_deep_sharp) {
                continue;
            }
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
            // Summed earned-trust quality of the (one-sided) backers. With default
            // votes (earned_quality == quality_weight(rank)) this equals the raw
            // backer quality; tiering still keys on net_count.
            WeightMode::TrustWeighted => backers.values().map(|v| v.earned_quality).sum(),
            // Summed POOLED per-cell earned quality (FORGE_PLAN Item 3). Equals
            // TrustWeighted when cell_earned_quality defaults to earned_quality.
            WeightMode::CellPooled => backers.values().map(|v| v.cell_earned_quality).sum(),
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

/// Phase-4 earned-trust arms — silent (`alerting: false`), judged by the gate in
/// the EXPERIMENTAL family (see [`crate::scanner::enrich::family`]) so they never
/// tighten core's Bonferroni bar. Appended to the portfolio ONLY when
/// `CONSENSUS_TRUST_ARMS` is on; when off they aren't registered, so the live
/// portfolio is byte-identical. They derive from `base` like every other variant.
/// `cohort_cutoff` is the voting rank cutoff (`TRACK_CONSENSUS_RANK_CUTOFF`) the
/// cross-cohort conviction arm splits whales from deep sharps on.
pub fn trust_arms(base: &ConsensusParams, cohort_cutoff: i32) -> Vec<StrategyDef> {
    vec![
        // Rank by summed earned-trust quality of the backers.
        StrategyDef {
            name: "trust_weighted",
            params: ConsensusParams {
                weight_mode: WeightMode::TrustWeighted,
                ..base.clone()
            },
            alerting: false,
        },
        // Count only gate-Trusted backers (drops untrusted/Avoid) — the
        // "sharp_only" conviction arm across ALL cohorts.
        StrategyDef {
            name: "trusted_only",
            params: ConsensusParams {
                trusted_only: true,
                ..base.clone()
            },
            alerting: false,
        },
        // Cross-cohort conviction (deep-pool edge run, Phase 2): fires only when
        // a whale AND a certified deep sharp back the same outcome. Emits nothing
        // until a deep sharp is EARNED into the voter set — silent + inert today,
        // forward-tracked from the moment promotion happens.
        StrategyDef {
            name: "cross_cohort",
            params: ConsensusParams {
                cross_cohort_cutoff: Some(cohort_cutoff),
                ..base.clone()
            },
            alerting: false,
        },
        // Tail-the-sharp (deep-pool edge run, Phase 3): one CERTIFIED trader's
        // entry is itself a signal. min_backers 1 + strictly-certified votes only
        // (`certified_only` — unprofiled traders never count, unlike
        // `trusted_only`); the opposer/price-coherence gates are meaningless for
        // a single-trader follow, so they're wide open. The signal upsert stamps
        // decision-time (`first_detected_at` + captured mid/ask), so the honest
        // panel measures the FOLLOWER's realizable ROI/CLV/capture-lag, and the
        // backers field records WHICH sharp — the per-trader executable track
        // record (scripts/tail_records.py). Two horizons, same selection:
        //  - sharp_tail_fresh: entries ≤3h old — the actionable follow; its CLV
        //    vs the arm below measures the freshness premium;
        //  - sharp_tail: the full-window lagged follow (the control).
        StrategyDef {
            name: "sharp_tail_fresh",
            params: ConsensusParams {
                min_backers: 1,
                max_opposers: usize::MAX,
                max_price_std: 1.0,
                max_age_mins: 180,
                certified_only: true,
                ..base.clone()
            },
            alerting: false,
        },
        StrategyDef {
            name: "sharp_tail",
            params: ConsensusParams {
                min_backers: 1,
                max_opposers: usize::MAX,
                max_price_std: 1.0,
                certified_only: true,
                ..base.clone()
            },
            alerting: false,
        },
    ]
}

/// The pooled per-cell specialist arm (FORGE_PLAN Item 3): rank by summed POOLED
/// per-cell earned quality (`WeightMode::CellPooled`) — each vote weighted by the
/// trader's edge in THIS market's sport cell, partial-pooled toward their overall
/// multiplier. Silent, EXPERIMENTAL, registered only when `SLICE_POOLED` is on.
/// With pooling off it never registers; with it on but no cell data it reproduces
/// `trust_weighted` (fail-closed) — the arm is ONE hypothesis (does pooled per-cell
/// weighting beat wallet-level forward), never a per-cell selection.
pub fn slice_sport_tail(base: &ConsensusParams) -> StrategyDef {
    StrategyDef {
        name: "slice_sport_tail",
        params: ConsensusParams {
            weight_mode: WeightMode::CellPooled,
            ..base.clone()
        },
        alerting: false,
    }
}

/// The proven-trader router arm (PREREG_2026-07-04T094304Z, paper-only): ONE
/// scorecard-proven wallet's fresh BUY in the favorite band 0.45–0.90 is itself
/// a signal — ROUTE to who is buying, not how many agree. Construction mirrors
/// `sharp_tail_fresh` (single-trader follow ⇒ opposer/coherence gates wide
/// open), but selection is the ROLLING SCORECARD (`router_followset`: ≥100
/// repriced fills, ≥15 days, event-clustered copy-return ≥ +10%, MM-screened),
/// NOT the cert gate (whose follow-set is empty today). Silent, EXPERIMENTAL
/// family, judged only by the standing gate; registered only when
/// `PROVEN_ROUTER` is on AND a follow-set has been published — with an empty
/// set it fires nothing (fail-closed).
pub fn proven_router_arm(base: &ConsensusParams, set: Arc<HashSet<String>>) -> StrategyDef {
    StrategyDef {
        name: "proven_router",
        params: ConsensusParams {
            min_backers: 1,
            max_opposers: usize::MAX,
            max_price_std: 1.0,
            max_age_mins: 180,
            price_band: Some((0.45, 0.90)),
            router_set: Some(set),
            ..base.clone()
        },
        alerting: false,
    }
}

/// Score ONLY the `proven_router` arm over the given books — the hot lane's
/// scoped scoring pass (capture-hardening Item 2). Pure and deterministic: it
/// emits EXACTLY what the slow portfolio pass emits for the `proven_router`
/// strategy over the same books, so the fast lane and the 1-min cycle converge on
/// the identical signal — it only arrives sooner (≲30s vs 1.5–3 min). No other
/// arm is ever scored here, so the hot lane cannot perturb `strict` (or any
/// other) emissions.
pub fn score_router_only(
    books: &[MarketBook],
    now: DateTime<Utc>,
    base: &ConsensusParams,
    set: Arc<HashSet<String>>,
) -> Vec<ConsensusSignal> {
    let def = proven_router_arm(base, set);
    let mut sigs = score_all(books, now, &def.params);
    for s in &mut sigs {
        s.strategy = def.name.to_string();
    }
    sigs
}

/// Parse the `CONSENSUS_RETUNED` spec — `"min_backers,strong_net,elite_net"` —
/// into the re-tuned threshold triple. Empty/garbage ⇒ `None` (arm not
/// registered; live portfolio unchanged). The re-tune exists because a WIDER
/// eligible voter set inflates `net_count`: with more voters, today's absolute
/// thresholds fire more, so selectivity must be re-chosen deliberately — as a
/// silent VARIANT, never by moving `strict` itself.
pub fn parse_retuned(spec: &str) -> Option<(usize, i64, i64)> {
    let parts: Vec<i64> = spec
        .split(',')
        .map(|s| s.trim().parse::<i64>())
        .collect::<Result<_, _>>()
        .ok()?;
    let &[min_backers, strong_net, elite_net] = parts.as_slice() else {
        return None;
    };
    (min_backers >= 1 && strong_net >= min_backers && elite_net >= strong_net).then_some((
        min_backers as usize,
        strong_net,
        elite_net,
    ))
}

/// The re-tuned `strict` variant from a parsed [`parse_retuned`] spec: identical
/// to `strict` except the absolute count thresholds. Silent — measured against
/// `strict` on the scoreboard/honest panel like every other candidate.
pub fn retuned_arm(base: &ConsensusParams, t: (usize, i64, i64)) -> StrategyDef {
    let (min_backers, strong_net, elite_net) = t;
    StrategyDef {
        name: "strict_retuned",
        params: ConsensusParams {
            min_backers,
            strong_net,
            elite_net,
            ..base.clone()
        },
        alerting: false,
    }
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
            earned_quality: quality_weight(rank),
            cell_earned_quality: quality_weight(rank),
            trusted: true,
            certified: true,
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

    // --- capture-hardening Item 2: the hot lane's scoped scorer ---

    #[test]
    fn score_router_only_scores_router_arm_and_nothing_else() {
        let now = Utc::now();
        // Two fresh backers on Yes at 0.50 (in the 0.45–0.90 band): `wa` is a
        // follow-set wallet, `wb` is not.
        let b = book_with(
            now,
            vec![(0, "wa", Some(5), 0.50, 5), (0, "wb", Some(20), 0.51, 5)],
        );
        let base = ConsensusParams::default();

        // Only `wa` is routed ⇒ exactly one proven_router signal, counting ONLY
        // the router member (net_count = 1, `wb` filtered out by router_set).
        let set: Arc<HashSet<String>> = Arc::new(["wa".to_string()].into_iter().collect());
        let sigs = score_router_only(&[b.clone()], now, &base, set);
        assert_eq!(sigs.len(), 1, "one market, one routed backer ⇒ one signal");
        assert!(
            sigs.iter().all(|s| s.strategy == "proven_router"),
            "the scoped pass tags ONLY proven_router — never strict/loose/etc."
        );
        assert_eq!(sigs[0].net_count, 1, "only the routed wallet is counted");
        assert!(
            sigs[0].backers.iter().all(|bk| bk.wallet == "wa"),
            "non-router wallet `wb` must not appear as a backer"
        );

        // Fail-closed: an empty follow-set counts nothing (mirrors the arm's
        // published-but-empty state).
        let empty: Arc<HashSet<String>> = Arc::new(HashSet::new());
        assert!(
            score_router_only(&[b.clone()], now, &base, empty).is_empty(),
            "empty follow-set ⇒ no signals (fail-closed)"
        );

        // A follow-set that matches no wallet in the book ⇒ no signal.
        let miss: Arc<HashSet<String>> = Arc::new(["zz".to_string()].into_iter().collect());
        assert!(
            score_router_only(&[b], now, &base, miss).is_empty(),
            "no routed wallet present ⇒ no signal"
        );
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

    // --- Phase 4: earned-trust arms are silent + non-regressive ---

    #[test]
    fn trust_arms_registered_separately_and_silent() {
        let base = ConsensusParams::default();
        // The trust arms are NOT in the default portfolio — they're appended only
        // when CONSENSUS_TRUST_ARMS is on, so the live portfolio stays identical.
        let core = default_portfolio(&base);
        assert!(
            !core.iter().any(|d| {
                d.name == "trust_weighted" || d.name == "trusted_only" || d.name == "cross_cohort"
            }),
            "trust arms must NOT be in the default portfolio"
        );
        let arms = trust_arms(&base, 40);
        assert_eq!(arms.len(), 5);
        assert!(arms.iter().all(|d| !d.alerting), "trust arms never alert");
        assert!(arms.iter().any(|d| d.name == "trust_weighted"));
        assert!(arms.iter().any(|d| d.name == "trusted_only"));
        let cc = arms.iter().find(|d| d.name == "cross_cohort").unwrap();
        assert_eq!(cc.params.cross_cohort_cutoff, Some(40));
        // Phase 3 tail arms: single-certified-backer follows, strictly gated.
        for name in ["sharp_tail_fresh", "sharp_tail"] {
            let t = arms.iter().find(|d| d.name == name).unwrap();
            assert_eq!(t.params.min_backers, 1);
            assert!(t.params.certified_only);
        }
        assert_eq!(
            arms.iter()
                .find(|d| d.name == "sharp_tail_fresh")
                .unwrap()
                .params
                .max_age_mins,
            180
        );
    }

    #[test]
    fn slice_arm_registered_separately_and_silent() {
        // FORGE_PLAN Item 3: the pooled per-cell arm is NOT in the default
        // portfolio (appended only when SLICE_POOLED is on), is silent, and ranks
        // by the pooled per-cell weight.
        let base = ConsensusParams::default();
        assert!(
            !default_portfolio(&base)
                .iter()
                .any(|d| d.name == "slice_sport_tail"),
            "slice arm must NOT be in the default portfolio"
        );
        let arm = slice_sport_tail(&base);
        assert_eq!(arm.name, "slice_sport_tail");
        assert!(!arm.alerting, "the slice arm never alerts");
        assert_eq!(arm.params.weight_mode, WeightMode::CellPooled);
    }

    #[test]
    fn cellpooled_equals_trustweighted_when_cell_eq_defaults() {
        // With default votes (cell_earned_quality == earned_quality), CellPooled
        // and TrustWeighted produce the identical score — the byte-identical
        // fail-closed property (FORGE_PLAN Item 3).
        let now = Utc::now();
        let b = book_with(
            now,
            vec![
                (0, "wa", Some(5), 0.50, 10),
                (0, "wb", Some(20), 0.51, 20),
                (0, "wc", Some(30), 0.49, 30),
            ],
        );
        let base = ConsensusParams::default();
        let tw = ConsensusParams {
            weight_mode: WeightMode::TrustWeighted,
            ..base.clone()
        };
        let cp = ConsensusParams {
            weight_mode: WeightMode::CellPooled,
            ..base.clone()
        };
        let a = score_market(&b, now, &tw);
        let c = score_market(&b, now, &cp);
        assert_eq!(a.len(), c.len());
        assert!((a[0].score - c[0].score).abs() < 1e-12);
    }

    // --- Phase 3 (deep-pool edge run): tail-the-sharp ---

    #[test]
    fn certified_only_counts_strictly_certified_backers() {
        let now = Utc::now();
        let mk = |w: &str, trusted: bool, certified: bool| TraderVote {
            wallet: w.into(),
            name: w.into(),
            rank: Some(120),
            pnl: None,
            quality: 1.0,
            earned_quality: 1.0,
            cell_earned_quality: 1.0,
            trusted,
            certified,
            price: 0.50,
            size_usd: 1000.0,
            ts: now - Duration::minutes(30),
        };
        let base = ConsensusParams::default();
        let tail = trust_arms(&base, 40)
            .into_iter()
            .find(|d| d.name == "sharp_tail_fresh")
            .unwrap()
            .params;

        // One CERTIFIED sharp's entry fires the tail arm.
        let mut b = MarketBook::new("0xc", "t", "s", None, false);
        b.add_vote(0, "Yes", mk("cert", true, true));
        let sigs = score_market(&b, now, &tail);
        assert_eq!(sigs.len(), 1, "a single certified entry is a tail signal");
        assert_eq!(sigs[0].n_backers, 1);

        // An UNPROFILED trader (trusted defaults true, certified false) does NOT
        // fire the tail arm — the exact hole `trusted_only` leaves open.
        let mut b2 = MarketBook::new("0xc2", "t", "s", None, false);
        b2.add_vote(0, "Yes", mk("newbie", true, false));
        assert!(
            score_market(&b2, now, &tail).is_empty(),
            "unprofiled traders never fire a tail signal"
        );
        // …but the same book under plain trusted_only WOULD count it (min_backers
        // permitting) — proving certified_only is the strictly tighter gate.
        let loose = ConsensusParams {
            min_backers: 1,
            trusted_only: true,
            ..ConsensusParams::default()
        };
        assert_eq!(score_market(&b2, now, &loose).len(), 1);

        // Default params never read `certified`: identical books, one with all
        // votes certified and one with none, score byte-identically.
        let mut c1 = MarketBook::new("0xc3", "t", "s", None, false);
        let mut c2 = MarketBook::new("0xc3", "t", "s", None, false);
        for w in ["wa", "wb", "wc"] {
            c1.add_vote(0, "Yes", mk(w, true, true));
            c2.add_vote(0, "Yes", mk(w, true, false));
        }
        let s1 = score_market(&c1, now, &ConsensusParams::default());
        let s2 = score_market(&c2, now, &ConsensusParams::default());
        assert_eq!(s1.len(), s2.len());
        assert_eq!(s1[0].net_count, s2[0].net_count);
        assert!((s1[0].score - s2[0].score).abs() < 1e-12);
    }

    #[test]
    fn proven_router_counts_only_followset_wallets_and_fails_closed() {
        let now = Utc::now();
        let mk = |w: &str, price: f64| TraderVote {
            wallet: w.into(),
            name: w.into(),
            rank: Some(120),
            pnl: None,
            quality: 1.0,
            earned_quality: 1.0,
            cell_earned_quality: 1.0,
            trusted: true,
            certified: false,
            price,
            size_usd: 1000.0,
            ts: now - Duration::minutes(30),
        };
        let base = ConsensusParams::default();
        let set: Arc<HashSet<String>> = Arc::new(["proven".to_string()].into_iter().collect());
        let arm = proven_router_arm(&base, Arc::clone(&set)).params;

        // A follow-set wallet's single in-band BUY fires the router.
        let mut b = MarketBook::new("0xr", "t", "s", None, false);
        b.add_vote(0, "Yes", mk("proven", 0.70));
        let sigs = score_market(&b, now, &arm);
        assert_eq!(sigs.len(), 1, "a proven wallet's in-band entry is a signal");
        assert_eq!(sigs[0].n_backers, 1);

        // A wallet OUTSIDE the follow-set never fires, however sharp its rank.
        let mut b2 = MarketBook::new("0xr2", "t", "s", None, false);
        b2.add_vote(0, "Yes", mk("stranger", 0.70));
        assert!(
            score_market(&b2, now, &arm).is_empty(),
            "non-followset wallets never fire the router"
        );

        // Out-of-band entries are skipped even for proven wallets (longshot block).
        let mut b3 = MarketBook::new("0xr3", "t", "s", None, false);
        b3.add_vote(0, "Yes", mk("proven", 0.30));
        assert!(
            score_market(&b3, now, &arm).is_empty(),
            "sub-0.45 longshots are blocked by the price band"
        );

        // FAIL-CLOSED: an EMPTY follow-set (no re-score published yet, or an
        // honest empty re-score) fires nothing at all.
        let empty = proven_router_arm(&base, Arc::new(HashSet::new())).params;
        assert!(
            score_market(&b, now, &empty).is_empty(),
            "empty follow-set counts no votes"
        );

        // Default params (`router_set: None`) never read the set: books score
        // identically with or without follow-set membership.
        let plain = ConsensusParams::default();
        let mut c1 = MarketBook::new("0xr4", "t", "s", None, false);
        for w in ["wa", "wb", "wc"] {
            c1.add_vote(0, "Yes", mk(w, 0.70));
        }
        let s = score_market(&c1, now, &plain);
        assert_eq!(s.len(), 1);
        assert_eq!(s[0].n_backers, 3);
    }

    #[test]
    fn tail_arms_ignore_opposers_and_dispersion() {
        // A single-trader follow must not be vetoed by market disagreement gates:
        // 3 certified opposers + wild price spread still leave the tail signal up.
        let now = Utc::now();
        let mk = |w: &str, _oidx: i32, price: f64| TraderVote {
            wallet: w.into(),
            name: w.into(),
            rank: Some(120),
            pnl: None,
            quality: 1.0,
            earned_quality: 1.0,
            cell_earned_quality: 1.0,
            trusted: true,
            certified: true,
            price,
            size_usd: 1000.0,
            ts: now - Duration::minutes(10),
        };
        let base = ConsensusParams::default();
        let tail = trust_arms(&base, 40)
            .into_iter()
            .find(|d| d.name == "sharp_tail")
            .unwrap()
            .params;
        let mut b = MarketBook::new("0xc", "t", "s", None, false);
        b.add_vote(0, "Yes", mk("sharp", 0, 0.50));
        for (w, p) in [("o1", 0.20), ("o2", 0.55), ("o3", 0.90)] {
            b.add_vote(1, "No", mk(w, 1, p));
        }
        let sigs = score_market(&b, now, &tail);
        // BOTH sides fire as tail signals (each is a certified follow) — the
        // strict default would have rejected the No side for dispersion and both
        // for opposer count.
        assert_eq!(sigs.len(), 2, "{sigs:?}");
        assert!(score_market(&b, now, &base).is_empty());
    }

    // --- Phase 2 (deep-pool edge run): cross-cohort conviction + re-tune ---

    #[test]
    fn cross_cohort_requires_whale_and_certified_deep_sharp() {
        let now = Utc::now();
        let mk = |w: &str, rank: Option<i32>, trusted: bool| TraderVote {
            wallet: w.into(),
            name: w.into(),
            rank,
            pnl: None,
            quality: quality_weight(rank),
            earned_quality: quality_weight(rank),
            cell_earned_quality: quality_weight(rank),
            trusted,
            certified: trusted,
            price: 0.50,
            size_usd: 1000.0,
            ts: now - Duration::minutes(5),
        };
        let cc = ConsensusParams {
            cross_cohort_cutoff: Some(40),
            ..ConsensusParams::default()
        };
        let book = |votes: Vec<TraderVote>| {
            let mut b = MarketBook::new("0xc", "t", "s", None, false);
            for v in votes {
                b.add_vote(0, "Yes", v);
            }
            b
        };

        // Whales only (3 backers, no certified deep) → cross_cohort silent,
        // strict-equivalent default still fires.
        let whales_only = book(vec![
            mk("w1", Some(5), true),
            mk("w2", Some(12), true),
            mk("w3", Some(30), true),
        ]);
        assert_eq!(
            score_market(&whales_only, now, &ConsensusParams::default()).len(),
            1
        );
        assert!(score_market(&whales_only, now, &cc).is_empty());

        // Whales + an EARNED certified deep sharp (rank 120, trusted) → fires.
        let cross = book(vec![
            mk("w1", Some(5), true),
            mk("w2", Some(12), true),
            mk("d1", Some(120), true),
        ]);
        assert_eq!(score_market(&cross, now, &cc).len(), 1);

        // Deep backer present but NOT certified (trusted=false) → silent.
        let uncert = book(vec![
            mk("w1", Some(5), true),
            mk("w2", Some(12), true),
            mk("d1", Some(120), false),
        ]);
        assert!(score_market(&uncert, now, &cc).is_empty());

        // Certified deep sharps only (no whale) → silent: it's a CROSS-cohort
        // conviction signal, not a deep-only one.
        let deep_only = book(vec![
            mk("d1", Some(120), true),
            mk("d2", Some(150), true),
            mk("d3", Some(200), true),
        ]);
        assert!(score_market(&deep_only, now, &cc).is_empty());
    }

    #[test]
    fn parse_retuned_accepts_valid_rejects_garbage() {
        assert_eq!(parse_retuned("4,5,8"), Some((4, 5, 8)));
        assert_eq!(parse_retuned(" 3 , 4 , 6 "), Some((3, 4, 6)));
        // Empty (the default) and garbage never register the arm.
        assert_eq!(parse_retuned(""), None);
        assert_eq!(parse_retuned("4,5"), None);
        assert_eq!(parse_retuned("a,b,c"), None);
        // Ordering must be sane: min_backers ≤ strong ≤ elite, all ≥ 1.
        assert_eq!(parse_retuned("0,5,8"), None);
        assert_eq!(parse_retuned("5,4,8"), None);
        assert_eq!(parse_retuned("4,8,5"), None);
    }

    #[test]
    fn retuned_arm_only_moves_the_count_thresholds() {
        let base = ConsensusParams::default();
        let arm = retuned_arm(&base, (4, 5, 8));
        assert_eq!(arm.name, "strict_retuned");
        assert!(!arm.alerting, "the re-tune variant is silent");
        assert_eq!(arm.params.min_backers, 4);
        assert_eq!(arm.params.strong_net, 5);
        assert_eq!(arm.params.elite_net, 8);
        // Everything else identical to strict's base.
        assert_eq!(arm.params.max_opposers, base.max_opposers);
        assert_eq!(arm.params.max_price_std, base.max_price_std);
        assert_eq!(arm.params.max_age_mins, base.max_age_mins);
        // Selectivity holds: a 3-backer book fires strict but not the re-tune.
        let now = Utc::now();
        let mut b = MarketBook::new("0xc", "t", "s", None, false);
        for w in ["wa", "wb", "wc"] {
            b.add_vote(
                0,
                "Yes",
                TraderVote {
                    wallet: w.into(),
                    name: w.into(),
                    rank: Some(10),
                    pnl: None,
                    quality: 1.5,
                    earned_quality: 1.5,
                    cell_earned_quality: 1.5,
                    trusted: true,
                    certified: true,
                    price: 0.5,
                    size_usd: 1000.0,
                    ts: now,
                },
            );
        }
        assert_eq!(score_market(&b, now, &base).len(), 1);
        assert!(score_market(&b, now, &arm.params).is_empty());
    }

    #[test]
    fn trust_weighted_tier_matches_quality_with_default_votes() {
        // With default votes (earned_quality == quality_weight, trusted == true),
        // TrustWeighted keeps the SAME tier + net_count as Quality — tiering is
        // net_count-based, so the live `strict` alert tier can't move.
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
        let q = score_market(&b, now, &ConsensusParams::default());
        let tw = score_market(
            &b,
            now,
            &ConsensusParams {
                weight_mode: WeightMode::TrustWeighted,
                ..ConsensusParams::default()
            },
        );
        assert_eq!(q[0].tier, tw[0].tier);
        assert_eq!(q[0].net_count, tw[0].net_count);
    }

    #[test]
    fn trusted_only_drops_untrusted_but_no_op_when_all_trusted() {
        let now = Utc::now();
        let mk = |w: &str, trusted: bool| TraderVote {
            wallet: w.into(),
            name: w.into(),
            rank: None,
            pnl: None,
            quality: 1.0,
            earned_quality: 1.0,
            cell_earned_quality: 1.0,
            trusted,
            certified: trusted,
            price: 0.50,
            size_usd: 1000.0,
            ts: now,
        };
        let mut b = MarketBook::new("0xc", "t", "s", Some("e".into()), false);
        b.add_vote(0, "Yes", mk("wa", true));
        b.add_vote(0, "Yes", mk("wb", true));
        b.add_vote(0, "Yes", mk("wc", true));
        b.add_vote(0, "Yes", mk("wd", false)); // untrusted

        let trusted_only = ConsensusParams {
            trusted_only: true,
            ..ConsensusParams::default()
        };
        let sigs = score_market(&b, now, &trusted_only);
        assert_eq!(
            sigs[0].n_backers, 3,
            "untrusted backer dropped under trusted_only"
        );
        // Default (trusted_only = false) counts every backer — no-op proof.
        let all = score_market(&b, now, &ConsensusParams::default());
        assert_eq!(all[0].n_backers, 4, "default counts all backers");
    }
}
