//! Consensus detection cycle: poll the tracked-trader universe, build per-market
//! books, score them, and push tiered alerts on fresh strong/elite consensus.
//!
//! This is additive to the existing per-trader copy cycle — it reads the same
//! `followed_traders` but never places bets; it only alerts and records signals
//! for forward edge tracking.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use chrono::{DateTime, Utc};
use futures_util::future::join_all;
use tokio::sync::Semaphore;

use crate::config::CopyTradingConfig;
use crate::data::models::{fetch_clob_market, fetch_market_by_slug, fetch_price_history};
use crate::live::broadcast;
use crate::scanner::consensus::{
    BackerInfo, ConsensusParams, ConsensusSignal, MarketBook, StrategyDef, Tier, TraderVote,
    default_portfolio, quality_weight, score_all_strategies, trust_arms,
};
use crate::scanner::copy_trader::{CopyTraderMonitor, PollResult, TraderTrade};
use crate::scanner::enrich::{EnrichCtx, EnrichMargins, EnrichModels, MarketCtx, enrich_all};
use crate::scanner::trader_trust::{TraderTrust, TrustVerdict};
use crate::storage::consensus::{
    NewConsensusSignal, NewMarketFeatureLog, NewTraderFill, WindowVote,
};
use crate::storage::postgres::{FollowedTrader, PgPortfolio};
use crate::telegram::notifier::TelegramNotifier;
use polymarket_common::model::features::MarketFeatures;
use polymarket_common::ntfy::Ntfy;

/// Build [`ConsensusParams`] from runtime config.
fn params_from_cfg(cfg: &CopyTradingConfig) -> ConsensusParams {
    ConsensusParams {
        min_backers: cfg.min_backers,
        max_opposers: cfg.max_opposers,
        max_price_std: cfg.max_price_std,
        max_age_mins: cfg.max_age_mins,
        strong_net: cfg.strong_net,
        elite_net: cfg.elite_net,
        elite_rank: cfg.elite_rank,
        // Incumbent `strict` knobs: sports treatment mirrors the legacy global flag;
        // the other portfolio knobs are no-ops for strict.
        require_elite: false,
        price_band: None,
        sports_mode: if cfg.consensus_include_sports {
            crate::scanner::consensus::SportsMode::Include
        } else {
            crate::scanner::consensus::SportsMode::Exclude
        },
        weight_mode: crate::scanner::consensus::WeightMode::Quality,
        trusted_only: false,
        cross_cohort_cutoff: None,
    }
}

/// Per-vote earned quality + trust flag from the cached trust map. Untracked /
/// INDETERMINATE ⇒ `quality_weight(rank)` fallback (never 0) so trust-weighting
/// can't silently zero a new trader; `trusted` defaults true when untracked so
/// `trusted_only` doesn't drop brand-new traders. Shrink-toward-0 lives HERE
/// (regularizing the continuous multiplier), never at the verdict.
fn earned_quality(trust: &TrustMap, wallet: &str, rank: Option<i32>) -> (f64, bool) {
    let qw = quality_weight(rank);
    match trust.get(wallet) {
        Some(t) => {
            let n = t.n_events as f64;
            let damp = n / (n + 20.0); // shrink toward the prior for low N
            let earned = match t.verdict {
                TrustVerdict::Trusted => (1.0 + t.lower_bound * damp).clamp(0.5, 2.0),
                TrustVerdict::Avoid => (1.0 + t.upper_bound * damp).clamp(0.5, 1.0),
                TrustVerdict::Indeterminate => qw,
            };
            (earned, matches!(t.verdict, TrustVerdict::Trusted))
        }
        None => (qw, true),
    }
}

/// Cached earned-trust map: lower-cased wallet → its verdict. Refreshed slowly
/// (markets resolve ~daily), NOT recomputed every 1-min cycle.
pub type TrustMap = std::collections::HashMap<String, TraderTrust>;

/// Recompute the earned-trust map from the resolved fill archive: one
/// `trader_slice_scores` query → a `trust_verdict` per wallet. Called by the
/// slow refresh task in `live.rs`; empty on any DB error (fallback = incumbent
/// behavior). Cheap relative to its ~hourly cadence.
pub async fn compute_trust_map(portfolio: &PgPortfolio) -> TrustMap {
    let scores = portfolio.trader_slice_scores().await.unwrap_or_default();
    let mut by: HashMap<String, Vec<_>> = HashMap::new();
    for s in scores {
        by.entry(s.wallet.clone()).or_default().push(s);
    }
    by.into_iter()
        .map(|(w, slices)| (w, crate::scanner::trader_trust::trust_verdict(&slices)))
        .collect()
}

/// Local sports/esports heuristic on the activity title + slug (avoids a Gamma
/// round-trip per market). Mirrors `GammaMarket::is_sports_or_esports`.
fn is_sports(title: &str, slug: &str) -> bool {
    let t = title.to_lowercase();
    let s = slug.to_lowercase();
    const SLUG_PATS: &[&str] = &[
        "nba-", "nfl-", "mlb-", "nhl-", "fifwc", "ucl-", "epl-", "laliga", "-cs2-", "lol-", "dota",
        "soccer", "atp-", "wta-", "ufc-",
    ];
    const TITLE_PATS: &[&str] = &[
        " vs. ",
        " vs ",
        "spread:",
        "o/u ",
        "over/under",
        "win on 20",
        " fc ",
        "moneyline",
    ];
    SLUG_PATS.iter().any(|p| s.contains(p)) || TITLE_PATS.iter().any(|p| t.contains(p))
}

/// FROZEN slug/title-derived sport (or domain) bucket, the single source of
/// truth for `trader_fills.sport`. Computed once at capture so every query site
/// shares one classification (no SQL slug-CASE drift). Buckets cover the active
/// leaderboard universe; anything unrecognized is `other`. A finer Gamma
/// `category` would require a per-market fetch — deferred (cost-zero).
fn sport_bucket(title: &str, slug: &str) -> String {
    let s = slug.to_lowercase();
    let t = title.to_lowercase();
    let has = |pats: &[&str]| pats.iter().any(|p| s.contains(p) || t.contains(p));
    // Specific sports/esports first (slug prefixes are the reliable signal).
    if has(&["nba-", "nba "]) {
        "nba"
    } else if has(&["nfl-", "nfl "]) {
        "nfl"
    } else if has(&["mlb-", "mlb "]) {
        "mlb"
    } else if has(&["nhl-", "nhl "]) {
        "nhl"
    } else if has(&["-cs2-", "cs2", "counter-strike"]) {
        "cs2"
    } else if has(&["lol-", "-lol-", "league-of-legends"]) {
        // NB: keep these slug-scoped — bare league abbreviations like "lec"
        // collide with common words ("e-lec-tion"), so we don't use them.
        "lol"
    } else if has(&["dota", "dota2"]) {
        "dota"
    } else if has(&["atp-", "wta-", "tennis"]) {
        "tennis"
    } else if has(&["ufc-", "ufc ", "mma"]) {
        "ufc"
    } else if has(&[
        "fifwc",
        "ucl-",
        "epl-",
        "laliga",
        "soccer",
        "fifa",
        "-fc-",
        " fc ",
        "bundesliga",
        "serie-a",
        "ligue",
    ]) {
        "soccer"
    } else if has(&[
        "bitcoin", "ethereum", "-btc-", "-eth-", "crypto", "solana", "-sol-", "dogecoin",
    ]) {
        "crypto"
    } else if has(&[
        "election",
        "president",
        "trump",
        "biden",
        "senate",
        "congress",
        "politic",
        "governor",
        "parliament",
    ]) {
        "politics"
    } else {
        "other"
    }
    .to_string()
}

/// Convert one polled trade into a durable archive fill (BOTH sides). `None`
/// drops trades we can't key (missing outcome index) or whose price is
/// degenerate. `wallet_lc` is the lower-cased wallet (matches the window path's
/// distinctness convention and `load_buy_fills_since`'s join). `sport`/`is_sports`
/// are frozen here — the single source of truth for the trust slices (P2).
fn trade_to_fill(wallet_lc: &str, tr: &TraderTrade) -> Option<NewTraderFill> {
    let oidx = tr.outcome_index?;
    if !(tr.price > 0.0 && tr.price < 1.0) {
        return None;
    }
    if tr.side != "BUY" && tr.side != "SELL" {
        return None;
    }
    let title = tr.title.clone().unwrap_or_else(|| tr.slug.clone());
    let is_sports = is_sports(&title, &tr.slug);
    let sport = sport_bucket(&title, &tr.slug);
    Some(NewTraderFill {
        wallet: wallet_lc.to_string(),
        tx_hash: tr.tx_hash.clone(),
        condition_id: tr.condition_id.clone(),
        outcome_index: oidx,
        outcome: tr.outcome.clone().unwrap_or_else(|| oidx.to_string()),
        side: tr.side.clone(),
        price: tr.price,
        size_usd: tr.size_usd,
        title,
        slug: tr.slug.clone(),
        event_slug: tr.event_slug.clone(),
        is_sports,
        sport: Some(sport),
        ts: tr.timestamp,
    })
}

#[allow(clippy::too_many_arguments)]
pub async fn consensus_cycle(
    portfolio: &PgPortfolio,
    notifier: &TelegramNotifier,
    monitor: &CopyTraderMonitor,
    cfg: &CopyTradingConfig,
    ntfy: Option<&Ntfy>,
    http: &reqwest::Client,
    models: &EnrichModels,
    trust: &TrustMap,
) -> Result<()> {
    let traders = portfolio.get_active_traders().await?;
    if traders.is_empty() {
        tracing::debug!("Consensus: no active tracked traders yet");
        return Ok(());
    }

    let now = Utc::now();
    let window_start = now - chrono::Duration::hours(cfg.consensus_window_hours);

    // L1: incremental delta ingestion + off-network book assembly (default), or
    // the legacy poll-the-whole-window path. Both assemble identical books via
    // `books_from_window_votes`, so the live `strict` behavior is non-regressive.
    let t_ingest = std::time::Instant::now();
    let (book_vec, polled_ok) = if cfg.consensus_incremental {
        ingest_incremental(portfolio, monitor, &traders, now, window_start, cfg, trust).await?
    } else {
        ingest_legacy(monitor, &traders, window_start, cfg, trust).await
    };
    // Poll-cadence budget: record the fan-out size + wall-clock so the scale gate
    // can see whether widening the universe keeps 429 rate ≈ 0 and latency inside
    // the cycle (the semaphore-bounded fan-out is the regression surface).
    crate::metrics::record_consensus_poll(polled_ok as u64, t_ingest.elapsed());

    // Serialize the raw vote atoms ONCE per (market, outcome) — strategy-agnostic.
    // Stored on every signal so a strategy invented later can be replayed over it.
    let atoms = atom_log(&book_vec);

    let strategies = active_portfolio(cfg);
    let (alerting, watch_for) = alert_sets(
        &cfg.consensus_alert_strategies,
        &cfg.consensus_alert_watch_for,
        &strategies,
    );
    // Config-typo guard: an alert-set name that matches no ACTIVE strategy can
    // never push — with an override set, one typo would silently kill all
    // alerts. Warn loudly every cycle rather than fail (alerts are best-effort).
    {
        let known: std::collections::HashSet<&str> = strategies.iter().map(|d| d.name).collect();
        for name in alerting.iter().chain(watch_for.iter()) {
            if !known.contains(name.as_str()) {
                tracing::warn!(
                    strategy = %name,
                    "alert config names an unknown/inactive strategy — it will NEVER push (typo?)"
                );
            }
        }
    }
    let signals = score_all_strategies(&book_vec, now, &strategies);

    // Enricher seam: silent cross-check arms re-emit `strict` picks under new
    // strategy names; the originals pass through untouched, so `strict` alerting
    // is non-regressive. Market-dependent arms need per-market data fetched once
    // for the strict-fired markets (bounded + throttled), only when enabled.
    let markets = if models.needs_market_data() {
        let t0 = std::time::Instant::now();
        let m = prefetch_markets(
            http,
            &signals,
            models.needs_market_features(),
            cfg.market_prefetch_max,
        )
        .await;
        crate::metrics::record_consensus_prefetch(t0.elapsed());
        m
    } else {
        HashMap::new()
    };
    let signals = enrich_all(
        signals,
        &EnrichCtx {
            now,
            models,
            margins: EnrichMargins {
                ml: cfg.consensus_ml_margin,
                bayes: cfg.consensus_bayes_margin,
                resid: cfg.market_resid_margin,
            },
            markets: &markets,
        },
    );

    // Silent `market_resid` arm emissions this cycle (0 unless the arm is loaded).
    let resid_emits = signals
        .iter()
        .filter(|s| s.strategy == "market_resid")
        .count() as u64;
    crate::metrics::record_market_resid_emits(resid_emits);

    let mut alerts_sent = 0usize;
    // Forward 29-feature snapshots for every strict-fired market (default-OFF; the
    // `market_resid` training source). Collected inside the loop, flushed once.
    let mut feature_logs: Vec<NewMarketFeatureLog> = Vec::new();
    for sig in &signals {
        // Upsert EVERY strategy's signal for forward edge tracking.
        let new = to_new_signal(sig, &atoms);
        let state = match portfolio.upsert_consensus_signal(&new).await {
            Ok(s) => s,
            Err(e) => {
                tracing::warn!(err = %e, cond = %sig.condition_id, strat = %sig.strategy, "upsert_consensus_signal failed");
                continue;
            }
        };

        // Durable feature capture (forward, survivorship-free) — strict rows only,
        // when enabled and the YES-oriented features were pre-fetched this cycle.
        if models.feature_log
            && sig.strategy == "strict"
            && let Some(mc) = markets.get(&sig.condition_id)
            && let Some(feat) = mc.features.as_ref()
        {
            match serde_json::to_value(feat) {
                Ok(features) => feature_logs.push(NewMarketFeatureLog {
                    signal_id: state.id as i64,
                    condition_id: sig.condition_id.clone(),
                    outcome_index: sig.outcome_index,
                    yes_token: sig.outcome_index == 0,
                    clob_mid: Some(mc.clob_mid),
                    features,
                }),
                Err(e) => tracing::warn!(err = %e, "serialize MarketFeatures for feature log"),
            }
        }

        // Only the alerting strategy(ies) push; STRONG/ELITE always qualify,
        // WATCH only for strategies in the watch_for allowlist (the certified
        // winners fire mostly at net=3 = WATCH; see DECISIONS D10).
        if !alerting.contains(sig.strategy.as_str())
            || (sig.tier == Tier::Watch && !watch_for.contains(sig.strategy.as_str()))
        {
            continue;
        }

        let prev_tier = state.last_alert_tier.as_deref().and_then(Tier::from_str);
        let prev_net = state.last_alert_net.unwrap_or(i32::MIN);
        let should_alert = match prev_tier {
            None => true, // never alerted
            Some(pt) => {
                sig.tier.level() > pt.level()
                    || (sig.net_count as i32) >= prev_net + cfg.consensus_realert_net_delta as i32
            }
        };
        if !should_alert {
            continue;
        }

        // Cross-STRATEGY dedup: overlapping winners (e.g. favorite ∩
        // elite_fresh_fav ∩ strict) produce ONE push per (market, outcome).
        // Same-strategy re-alerts are exempt (the helper excludes them), so a
        // single-alerting-strategy config behaves exactly as before. Fail-open:
        // a DB error never suppresses an alert.
        if cfg.consensus_alert_cross_dedup_mins > 0
            && portfolio
                .recent_alert_by_other_strategy(
                    &sig.condition_id,
                    sig.outcome_index,
                    &sig.strategy,
                    cfg.consensus_alert_cross_dedup_mins,
                )
                .await
                .unwrap_or(false)
        {
            tracing::debug!(
                strategy = %sig.strategy,
                cond = %sig.condition_id,
                "alert suppressed: another strategy already pushed this market"
            );
            continue;
        }

        // Tag which strategy fired on non-strict pushes; strict's message stays
        // byte-identical to the incumbent format.
        let mut msg = format_consensus_alert(sig);
        if sig.strategy != "strict" {
            msg.push_str(&format!("\nstrategy: {}", sig.strategy));
        }
        broadcast(notifier, portfolio, &msg).await;
        // Phone push via the user's brainstem ntfy channel. WATCH-tier winner
        // pushes ride at a lower priority than STRONG/ELITE.
        if let Some(n) = ntfy {
            let (priority, tag) = match sig.tier {
                Tier::Elite => (5u8, "fire"),
                Tier::Strong => (4u8, "green_circle"),
                Tier::Watch => (3u8, "large_blue_circle"),
            };
            let title = format!(
                "{} {} consensus — BUY {}",
                sig.tier.emoji(),
                sig.tier.as_str(),
                sig.outcome_label
            );
            n.push(&title, &msg, priority, &[tag]).await;
        }
        if let Err(e) = portfolio
            .record_consensus_alert(
                state.id,
                &sig.strategy,
                sig.tier.as_str(),
                sig.net_count as i32,
                sig.score,
            )
            .await
        {
            tracing::warn!(err = %e, "record_consensus_alert failed");
        }
        crate::metrics::record_consensus_alert(&sig.strategy, sig.tier.as_str());
        alerts_sent += 1;
    }

    // Best-effort flush of the forward feature log (never blocks the cycle).
    if !feature_logs.is_empty() {
        match portfolio.log_market_features(&feature_logs).await {
            Ok(n) => {
                crate::metrics::record_market_feature_log_rows(n);
                tracing::debug!(rows = n, "Logged forward market features");
            }
            Err(e) => tracing::warn!(err = %e, "log_market_features failed (non-blocking)"),
        }
    }

    crate::metrics::record_consensus_cycle(book_vec.len() as u64, signals.len() as u64);

    tracing::info!(
        traders_polled = polled_ok,
        markets = book_vec.len(),
        strategies = strategies.len(),
        signals = signals.len(),
        alerts_sent,
        "Consensus cycle complete"
    );
    Ok(())
}

/// Display name for a trader (username, else short wallet) — matches the legacy
/// book-assembly naming exactly.
fn trader_name(t: &FollowedTrader) -> String {
    t.username
        .clone()
        .unwrap_or_else(|| t.proxy_wallet[..8.min(t.proxy_wallet.len())].to_string())
}

/// Convert one polled trade into a window fill atom, applying the same BUY /
/// outcome-index / price-validity filters the legacy book assembly used. `None`
/// drops the trade. `is_sports` is computed once here from the title + slug.
fn trade_to_window_vote(
    trader: &FollowedTrader,
    name: &str,
    quality: f64,
    tr: &TraderTrade,
) -> Option<WindowVote> {
    if tr.side != "BUY" {
        return None;
    }
    let oidx = tr.outcome_index?;
    if !(tr.price > 0.0 && tr.price < 1.0) {
        return None;
    }
    let title = tr.title.clone().unwrap_or_else(|| tr.slug.clone());
    let is_sports = is_sports(&title, &tr.slug);
    Some(WindowVote {
        trader_wallet: trader.proxy_wallet.to_lowercase(),
        name: name.to_string(),
        rank: trader.rank,
        pnl: trader.pnl,
        quality,
        condition_id: tr.condition_id.clone(),
        outcome_index: oidx,
        outcome: tr.outcome.clone().unwrap_or_else(|| oidx.to_string()),
        title,
        slug: tr.slug.clone(),
        event_slug: tr.event_slug.clone(),
        is_sports,
        price: tr.price,
        size_usd: tr.size_usd,
        ts: tr.timestamp,
    })
}

/// Assemble per-market books from window fill atoms. The SINGLE book builder,
/// shared by both ingestion paths so they produce identical books. Mirrors the
/// legacy assembly: wallet lower-cased for distinctness, label/title/sport set by
/// the first atom seen for a `(condition, outcome)`. `pub(crate)` so the
/// read-only shadow study (`scanner::earned`, board) builds its A/B books with
/// the IDENTICAL assembly rather than a parallel one.
pub(crate) fn books_from_window_votes(votes: &[WindowVote], trust: &TrustMap) -> Vec<MarketBook> {
    let mut books: HashMap<String, MarketBook> = HashMap::new();
    for v in votes {
        let book = books.entry(v.condition_id.clone()).or_insert_with(|| {
            MarketBook::new(
                v.condition_id.clone(),
                v.title.clone(),
                v.slug.clone(),
                v.event_slug.clone(),
                v.is_sports,
            )
        });
        // Earned trust rides on the vote (cached map). Defaults preserve incumbent
        // behavior: an empty/absent map ⇒ earned_quality == quality_weight(rank),
        // trusted == true, so every non-trust strategy is byte-identical.
        let (eq, trusted) = earned_quality(trust, &v.trader_wallet, v.rank);
        book.add_vote(
            v.outcome_index,
            v.outcome.clone(),
            TraderVote {
                wallet: v.trader_wallet.clone(),
                name: v.name.clone(),
                rank: v.rank,
                pnl: v.pnl,
                quality: v.quality,
                earned_quality: eq,
                trusted,
                price: v.price,
                size_usd: v.size_usd,
                ts: v.ts,
            },
        );
    }
    books.into_values().collect()
}

/// Legacy ingestion: poll each trader's whole `window_start..now` activity and
/// assemble books straight from the poll (no DB window). Kept as a fallback when
/// `CONSENSUS_INCREMENTAL=false`. Returns `(books, traders_polled_ok)`.
async fn ingest_legacy(
    monitor: &CopyTraderMonitor,
    traders: &[FollowedTrader],
    window_start: DateTime<Utc>,
    cfg: &CopyTradingConfig,
    trust: &TrustMap,
) -> (Vec<MarketBook>, usize) {
    let sem = Arc::new(Semaphore::new(cfg.consensus_max_concurrency.max(1)));
    let polls = traders.iter().map(|t| {
        let wallet = t.proxy_wallet.clone();
        let sem = Arc::clone(&sem);
        async move {
            let _permit = sem.acquire_owned().await;
            (t, monitor.poll_trader_activity(&wallet, window_start).await)
        }
    });
    let results = join_all(polls).await;

    let mut votes = Vec::new();
    let mut polled_ok = 0usize;
    for (trader, poll) in results {
        let trades = match poll {
            Ok(r) => {
                polled_ok += 1;
                r.trades
            }
            Err(e) => {
                tracing::debug!(wallet = %trader.proxy_wallet, err = %e, "Consensus poll failed");
                continue;
            }
        };
        let name = trader_name(trader);
        let quality = quality_weight(trader.rank);
        for tr in &trades {
            if let Some(v) = trade_to_window_vote(trader, &name, quality, tr) {
                votes.push(v);
            }
        }
    }
    (books_from_window_votes(&votes, trust), polled_ok)
}

/// L1 incremental ingestion: poll only the delta since each trader's cursor
/// (`max(cursor, window_start)`, backfilling the whole window on first run),
/// append it to the rolling window store (dedup), stamp the cursor, prune older
/// than the window, then rebuild books from the stored trailing window — book
/// assembly off the network onto an indexed DB read. Self-healing: a failed poll
/// or insert simply leaves the cursor where it was, so the gap is re-fetched next
/// cycle. Returns `(books, traders_polled_ok)`.
async fn ingest_incremental(
    portfolio: &PgPortfolio,
    monitor: &CopyTraderMonitor,
    traders: &[FollowedTrader],
    now: DateTime<Utc>,
    window_start: DateTime<Utc>,
    cfg: &CopyTradingConfig,
    trust: &TrustMap,
) -> Result<(Vec<MarketBook>, usize)> {
    let cursors = portfolio.consensus_cursors().await.unwrap_or_default();

    // Bounded fan-out: a Semaphore caps concurrent data-api polls so widening
    // the tracked universe can't burst the API into 429s.
    let sem = Arc::new(Semaphore::new(cfg.consensus_max_concurrency.max(1)));
    let polls = traders.iter().map(|t| {
        let wallet = t.proxy_wallet.clone();
        let since = cursors
            .get(&t.proxy_wallet)
            .copied()
            .map(|c| c.max(window_start))
            .unwrap_or(window_start);
        let sem = Arc::clone(&sem);
        async move {
            let _permit = sem.acquire_owned().await;
            (t, monitor.poll_trader_activity(&wallet, since).await)
        }
    });
    let results = join_all(polls).await;

    let mut delta = Vec::new();
    let mut fills = Vec::new();
    // Per-wallet capture bookkeeping: (proxy_wallet, min_ts, max_ts, raw_count).
    let mut captures: Vec<(String, DateTime<Utc>, DateTime<Utc>, usize)> = Vec::new();
    let mut polled_ok_wallets: Vec<String> = Vec::new();
    for (trader, poll) in results {
        let PollResult { trades, raw_count } = match poll {
            Ok(r) => r,
            Err(e) => {
                tracing::debug!(wallet = %trader.proxy_wallet, err = %e, "Consensus poll failed");
                continue;
            }
        };
        polled_ok_wallets.push(trader.proxy_wallet.clone());
        let name = trader_name(trader);
        let quality = quality_weight(trader.rank);
        let wallet_lc = trader.proxy_wallet.to_lowercase();
        // Capture once, use twice: the SAME poll feeds the consensus window
        // (BUY-only votes) and the durable archive (both sides).
        let mut min_ts: Option<DateTime<Utc>> = None;
        let mut max_ts: Option<DateTime<Utc>> = None;
        for tr in &trades {
            min_ts = Some(min_ts.map_or(tr.timestamp, |m| m.min(tr.timestamp)));
            max_ts = Some(max_ts.map_or(tr.timestamp, |m| m.max(tr.timestamp)));
            if let Some(v) = trade_to_window_vote(trader, &name, quality, tr) {
                delta.push(v);
            }
            if let Some(f) = trade_to_fill(&wallet_lc, tr) {
                fills.push(f);
            }
        }
        if let (Some(mn), Some(mx)) = (min_ts, max_ts) {
            captures.push((trader.proxy_wallet.clone(), mn, mx, raw_count));
        }
    }

    // Durable archive: persist BOTH sides (best-effort; failure never blocks the
    // consensus window). This is what makes the trader-trust profiles possible.
    let fills_inserted = match portfolio.insert_trader_fills(&fills).await {
        Ok(n) => n,
        Err(e) => {
            tracing::warn!(err = %e, "insert_trader_fills failed");
            0
        }
    };
    for (wallet, mn, mx, rc) in &captures {
        if let Err(e) = portfolio.record_capture(wallet, *mn, *mx, *rc).await {
            tracing::debug!(wallet = %wallet, err = %e, "record_capture failed");
        }
    }

    // Append the delta, and only advance cursors if it persisted (self-healing).
    match portfolio.insert_window_votes(&delta).await {
        Ok(inserted) => {
            portfolio
                .set_consensus_cursors(&polled_ok_wallets, now)
                .await
                .ok();
            tracing::debug!(
                delta = delta.len(),
                inserted,
                "Consensus window delta appended"
            );
        }
        Err(e) => {
            tracing::warn!(err = %e, "insert_window_votes failed; cursors not advanced");
        }
    }
    let pruned = portfolio
        .prune_window_votes(window_start)
        .await
        .unwrap_or(0);

    // Book source (flagged cutover, dual-write above): default = the rolling
    // `consensus_vote_window`; when CONSENSUS_BOOKS_FROM_FILLS=true, the durable
    // archive (re-derived quality). Both return the WindowVote shape so the
    // single book builder is reused — and tiering keys on net_count, so live
    // `strict` alerts are non-regressive under either source.
    let window = if cfg.consensus_books_from_fills {
        portfolio
            .load_buy_fills_since(window_start)
            .await
            .unwrap_or_default()
    } else {
        portfolio
            .load_window_votes(window_start)
            .await
            .unwrap_or_default()
    };

    tracing::info!(
        delta = delta.len(),
        fills = fills.len(),
        fills_inserted,
        pruned,
        window = window.len(),
        books_from_fills = cfg.consensus_books_from_fills,
        "Consensus incremental ingest"
    );
    Ok((
        books_from_window_votes(&window, trust),
        polled_ok_wallets.len(),
    ))
}

/// Pre-fetch per-market data for the market-dependent arms (`market_ml`,
/// `bayes_anchor`). Bounded to the strict-fired markets, deduped by condition_id,
/// throttled like housekeeping. Always grabs the live CLOB mid (1 call); fetches
/// the Gamma market + price history for full [`MarketFeatures`] only when needed.
/// All fetches are free; a failed fetch just omits that market (arm no-ops for it).
async fn prefetch_markets(
    http: &reqwest::Client,
    signals: &[ConsensusSignal],
    need_features: bool,
    max: usize,
) -> HashMap<String, MarketCtx> {
    // Distinct strict markets this cycle (bounded): the sequential 150ms-throttled
    // fetch could otherwise blow past the cadence as the strict count grows.
    let distinct: usize = {
        let mut d: HashSet<&str> = HashSet::new();
        signals
            .iter()
            .filter(|s| s.strategy == "strict")
            .for_each(|s| {
                d.insert(s.condition_id.as_str());
            });
        d.len()
    };
    let cap = max.max(1);
    if distinct > cap {
        tracing::warn!(
            distinct,
            cap,
            "prefetch_markets capped; excess strict markets fetched on later cycles"
        );
    }
    let mut seen: HashSet<&str> = HashSet::new();
    let mut map = HashMap::new();
    for s in signals.iter().filter(|s| s.strategy == "strict") {
        if !seen.insert(s.condition_id.as_str()) {
            continue;
        }
        if seen.len() > cap {
            break; // bound reached — remaining distinct markets settle next cycle
        }
        tokio::time::sleep(Duration::from_millis(150)).await;
        let clob = match fetch_clob_market(http, &s.condition_id).await {
            Ok(m) => m,
            Err(e) => {
                tracing::debug!(cond = %s.condition_id, err = %e, "prefetch CLOB failed");
                continue;
            }
        };
        let Some(mid) = clob.outcome_price(s.outcome_index) else {
            continue;
        };
        // Features are YES-oriented: `yes_price` = the index-0 (YES) mid, so an arm
        // converts `p_yes → p_consensus` via `outcome_index`. `clob_mid` stays the
        // consensus-outcome mid (the legacy arm + CLV anchor). For a binary market
        // and outcome_index==0 the two mids coincide; the unwrap_or is a safe guard.
        let features = if need_features {
            let yes_mid = clob.outcome_price(0).unwrap_or(mid);
            build_market_features(http, s, yes_mid).await
        } else {
            None
        };
        map.insert(
            s.condition_id.clone(),
            MarketCtx {
                clob_mid: mid,
                features,
                outcome_index: s.outcome_index,
            },
        );
    }
    tracing::debug!(
        markets = map.len(),
        need_features,
        "Prefetched market data for arms"
    );
    map
}

/// Build the [`MarketFeatures`] vector for one strict-fired market's consensus
/// outcome: 1 Gamma fetch (question/dates/category) + 1 price-history fetch for
/// the outcome's CLOB token. `None` if any fetch / token lookup fails.
async fn build_market_features(
    http: &reqwest::Client,
    s: &ConsensusSignal,
    yes_mid: f64,
) -> Option<MarketFeatures> {
    let gamma = fetch_market_by_slug(http, &s.slug).await.ok()?;
    let token_ids: Vec<String> = gamma
        .clob_token_ids
        .as_ref()
        .and_then(|j| serde_json::from_str(j).ok())?;
    // Binary markets only: YES-oriented features describe the index-0 token, and
    // an arm recovers `p_consensus` from `p_yes` via `outcome_index`. A non-binary
    // market has no single complementary YES side, so we skip it (arm no-ops). The
    // skip is surfaced (metric + board line) so this ~half-population gap is visible.
    if token_ids.len() != 2 {
        crate::metrics::record_market_multi_outcome_skipped(1);
        return None;
    }
    let token = token_ids.first()?;
    let history = fetch_price_history(http, token).await.unwrap_or_default();
    Some(MarketFeatures::from_market_and_history(
        &gamma, yes_mid, &history,
    ))
}

/// The active strategy portfolio: the full default set, optionally narrowed by
/// the `CONSENSUS_STRATEGIES` allowlist (empty = all). `pub(crate)` so the
/// board's read-only shadow study scores the IDENTICAL portfolio the cycle runs.
pub(crate) fn active_portfolio(cfg: &CopyTradingConfig) -> Vec<StrategyDef> {
    let base = params_from_cfg(cfg);
    let mut all = default_portfolio(&base);
    // Earned-trust arms are registered ONLY when CONSENSUS_TRUST_ARMS is on;
    // off ⇒ not appended ⇒ the portfolio is byte-identical to today.
    if cfg.consensus_trust_arms {
        all.extend(trust_arms(&base, cfg.track_consensus_rank_cutoff));
    }
    // Re-tuned strict-thresholds variant (Phase 2): registered only when the
    // CONSENSUS_RETUNED spec parses; silent; empty default = not registered.
    if let Some(t) = crate::scanner::consensus::parse_retuned(&cfg.consensus_retuned) {
        all.push(crate::scanner::consensus::retuned_arm(&base, t));
    }
    let filter = cfg.consensus_strategies.trim();
    if filter.is_empty() {
        return all;
    }
    let allow: std::collections::HashSet<&str> = filter
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();
    all.into_iter().filter(|d| allow.contains(d.name)).collect()
}

/// The alert sets: (strategies that push, strategies whose WATCH-tier fires
/// also push). `CONSENSUS_ALERT_STRATEGIES` overrides the portfolio's built-in
/// alerting flags when non-empty; `CONSENSUS_ALERT_WATCH_FOR` opts strategies
/// into WATCH-tier pushes. Both empty ⇒ byte-identical to the incumbent
/// behavior (`strict` only, STRONG/ELITE only).
fn alert_sets(
    alert_override_csv: &str,
    watch_for_csv: &str,
    defs: &[StrategyDef],
) -> (
    std::collections::HashSet<String>,
    std::collections::HashSet<String>,
) {
    let csv = |s: &str| -> std::collections::HashSet<String> {
        s.split(',')
            .map(|x| x.trim().to_string())
            .filter(|x| !x.is_empty())
            .collect()
    };
    let overridden = csv(alert_override_csv);
    let alerting = if overridden.is_empty() {
        defs.iter()
            .filter(|d| d.alerting)
            .map(|d| d.name.to_string())
            .collect()
    } else {
        overridden
    };
    (alerting, csv(watch_for_csv))
}

/// Serialize the raw vote atoms for every observed `(condition_id, outcome_index)`.
/// Strategy-agnostic, computed once per cycle, reused across all strategies.
fn atom_log(books: &[MarketBook]) -> std::collections::HashMap<(String, i32), serde_json::Value> {
    let mut map = std::collections::HashMap::new();
    for book in books {
        for (&oidx, votes) in &book.votes {
            let arr = serde_json::Value::Array(
                votes
                    .iter()
                    .map(|v| {
                        serde_json::json!({
                            "wallet": v.wallet,
                            "name": v.name,
                            "rank": v.rank,
                            "pnl": v.pnl,
                            "price": v.price,
                            "size_usd": v.size_usd,
                            "ts": v.ts.timestamp(),
                        })
                    })
                    .collect(),
            );
            map.insert((book.condition_id.clone(), oidx), arr);
        }
    }
    map
}

/// Convert a scored signal into its DB upsert payload (atoms attached).
fn to_new_signal(
    sig: &ConsensusSignal,
    atoms: &std::collections::HashMap<(String, i32), serde_json::Value>,
) -> NewConsensusSignal {
    let backers_json = serde_json::Value::Array(
        sig.backers
            .iter()
            .map(|b: &BackerInfo| {
                serde_json::json!({ "wallet": b.wallet, "name": b.name, "rank": b.rank })
            })
            .collect(),
    );
    let observed_votes = atoms
        .get(&(sig.condition_id.clone(), sig.outcome_index))
        .cloned()
        .unwrap_or(serde_json::Value::Null);
    NewConsensusSignal {
        strategy: sig.strategy.clone(),
        observed_votes,
        condition_id: sig.condition_id.clone(),
        outcome_index: sig.outcome_index,
        outcome_label: sig.outcome_label.clone(),
        title: sig.title.clone(),
        slug: sig.slug.clone(),
        event_slug: sig.event_slug.clone(),
        is_sports: sig.is_sports,
        n_backers: sig.n_backers as i32,
        n_opposers: sig.n_opposers as i32,
        net_count: sig.net_count as i32,
        net_quality: sig.net_quality,
        mean_price: sig.mean_price,
        price_std: sig.price_std,
        recency_mins: sig.recency_mins,
        total_usd: sig.total_usd,
        best_backer_rank: sig.best_backer_rank,
        score: sig.score,
        tier: sig.tier.as_str().to_string(),
        backers_json,
    }
}

/// Rich Telegram alert for a consensus signal.
fn format_consensus_alert(sig: &ConsensusSignal) -> String {
    let url = match &sig.event_slug {
        Some(ev) => format!("https://polymarket.com/event/{ev}"),
        None => format!("https://polymarket.com/event/{}", sig.slug),
    };
    let sport_tag = if sig.is_sports { " ⚽" } else { "" };
    let names: Vec<String> = sig
        .backers
        .iter()
        .take(8)
        .map(|b| match b.rank {
            Some(r) => format!("{} (#{r})", b.name),
            None => b.name.clone(),
        })
        .collect();
    let more = if sig.backers.len() > 8 {
        format!(" +{} more", sig.backers.len() - 8)
    } else {
        String::new()
    };

    format!(
        "{emoji} *{tier} CONSENSUS*{sport}\n\n\
         📋 *{title}*\n\
         🎯 BUY *{outcome}*  ({net:+} net — {back} backing, {opp} opposing)\n\
         💵 Avg entry `{price:.0}¢` (σ {std:.0}¢) | ${usd:.0}k total\n\
         ⏱ Freshest fill {age}\n\
         👥 {names}{more}\n\
         🔗 {url}",
        emoji = sig.tier.emoji(),
        tier = sig.tier.as_str(),
        sport = sport_tag,
        title = truncate(&sig.title, 80),
        outcome = sig.outcome_label,
        net = sig.net_count,
        back = sig.n_backers,
        opp = sig.n_opposers,
        price = sig.mean_price * 100.0,
        std = sig.price_std * 100.0,
        usd = sig.total_usd / 1000.0,
        age = humanize_mins(sig.recency_mins),
        names = names.join(", "),
        more = more,
        url = url,
    )
}

fn humanize_mins(m: i64) -> String {
    if m < 60 {
        format!("{m}m ago")
    } else if m < 1440 {
        format!("{}h ago", m / 60)
    } else {
        format!("{}d ago", m / 1440)
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let t: String = s.chars().take(max.saturating_sub(1)).collect();
        format!("{t}…")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn alert_sets_default_is_builtin_flags_and_no_watch() {
        let base = crate::scanner::consensus::ConsensusParams::default();
        let defs = crate::scanner::consensus::default_portfolio(&base);
        let (alerting, watch) = alert_sets("", "", &defs);
        // Byte-identical incumbent behavior: strict only, WATCH never pushes.
        assert_eq!(alerting.len(), 1, "only one built-in alerting strategy");
        assert!(alerting.contains("strict"));
        assert!(watch.is_empty());
    }

    #[test]
    fn alert_sets_override_and_watch_allowlist() {
        let base = crate::scanner::consensus::ConsensusParams::default();
        let defs = crate::scanner::consensus::default_portfolio(&base);
        let (alerting, watch) = alert_sets(
            "strict, favorite, elite_fresh_fav",
            "favorite,elite_fresh_fav",
            &defs,
        );
        assert_eq!(alerting.len(), 3);
        assert!(alerting.contains("favorite") && alerting.contains("elite_fresh_fav"));
        assert!(watch.contains("favorite") && !watch.contains("strict"));
    }

    #[test]
    fn sport_bucket_classifies_known_domains() {
        assert_eq!(
            sport_bucket("Spread: Bucks (-6.5)", "nba-ind-mil-2026-03-15-spread"),
            "nba"
        );
        assert_eq!(
            sport_bucket("CS2: NAVI vs FaZe", "esports-cs2-navi-faze"),
            "cs2"
        );
        assert_eq!(
            sport_bucket("Will Trump win?", "presidential-election-2028"),
            "politics"
        );
        assert_eq!(
            sport_bucket("Bitcoin above 100k?", "bitcoin-100k-2026"),
            "crypto"
        );
        // Unrecognized → the explicit catch-all, never a silent empty string.
        assert_eq!(
            sport_bucket("Random question", "random-market-slug"),
            "other"
        );
    }

    #[test]
    fn trade_to_fill_keeps_both_sides_and_drops_unkeyable() {
        let mk = |side: &str, oidx: Option<i32>, price: f64| TraderTrade {
            slug: "nba-x".into(),
            condition_id: "0xc".into(),
            side: side.into(),
            price,
            size_usd: 100.0,
            tx_hash: Some("0xtx".into()),
            timestamp: Utc::now(),
            outcome_index: oidx,
            outcome: Some("Yes".into()),
            title: Some("Spread: x".into()),
            event_slug: Some("nba-x".into()),
        };
        // BUY and SELL both captured for the durable ledger.
        assert!(trade_to_fill("0xw", &mk("BUY", Some(0), 0.5)).is_some());
        let sell = trade_to_fill("0xw", &mk("SELL", Some(1), 0.5)).unwrap();
        assert_eq!(sell.side, "SELL");
        assert_eq!(sell.wallet, "0xw");
        assert_eq!(sell.sport.as_deref(), Some("nba"));
        // Missing outcome index ⇒ can't key ⇒ dropped.
        assert!(trade_to_fill("0xw", &mk("BUY", None, 0.5)).is_none());
        // Degenerate price ⇒ dropped.
        assert!(trade_to_fill("0xw", &mk("BUY", Some(0), 1.0)).is_none());
    }

    fn wvote(wallet: &str, oidx: i32, price: f64, rank: Option<i32>) -> WindowVote {
        WindowVote {
            trader_wallet: wallet.into(),
            name: wallet.into(),
            rank,
            pnl: None,
            quality: crate::scanner::consensus::quality_weight(rank),
            condition_id: "0xcond".into(),
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

    /// PHASE 3 NON-REGRESSION (signal level): the consensus engine scores only the
    /// eligible votes that `load_window_votes` returns (deep votes are filtered at
    /// load — proven separately in `polymarket_common::…::eligibility_gate_*`). This
    /// test proves the downstream half: the gated book (eligible only) is what fires,
    /// and it is byte-for-byte identical to a world with NO deep traders — while the
    /// shadow (if deep DID vote) would change net_count and tier, proving the gate is
    /// load-bearing rather than cosmetic.
    #[test]
    fn deep_pool_excluded_from_signals_shadow_differs() {
        let trust = TrustMap::new();
        let base = crate::scanner::consensus::ConsensusParams::default(); // min_backers=3
        let portfolio = crate::scanner::consensus::default_portfolio(&base);
        let now = Utc::now();

        // 3 eligible (rank ≤ cutoff) backers on outcome 0 → a strict signal fires.
        let eligible = [
            wvote("0xe1", 0, 0.40, Some(5)),
            wvote("0xe2", 0, 0.42, Some(12)),
            wvote("0xe3", 0, 0.41, Some(30)),
        ];
        // Deep (ineligible) backers on the SAME outcome — the rows the load filter
        // strips. If they voted they'd pile onto net_count.
        let deep = [
            wvote("0xd1", 0, 0.43, Some(120)),
            wvote("0xd2", 0, 0.44, Some(230)),
            wvote("0xd3", 0, 0.45, Some(410)),
        ];

        let strict_net = |votes: &[WindowVote]| {
            score_all_strategies(&books_from_window_votes(votes, &trust), now, &portfolio)
                .into_iter()
                .find(|s| s.strategy == "strict" && s.condition_id == "0xcond")
                .map(|s| s.net_count)
        };

        // GATED = what the engine actually scores (eligible only, as the DB returns).
        // Identical to a universe that never captured the deep pool at all.
        let gated = strict_net(&eligible);
        assert_eq!(gated, Some(3), "gated: only the 3 eligible backers count");

        // SHADOW = if the deep pool voted. net_count would jump 3 → 6 (crossing the
        // elite_net gate) — concrete proof the gate changes emitted signals, so
        // excluding deep from voting is a real non-regression, not a no-op.
        let all: Vec<WindowVote> = eligible.iter().chain(deep.iter()).cloned().collect();
        let shadow = strict_net(&all);
        assert_eq!(shadow, Some(6), "shadow: deep pool would double net_count");
        assert_ne!(
            gated, shadow,
            "gate is load-bearing: deep would change signals"
        );
    }
}
