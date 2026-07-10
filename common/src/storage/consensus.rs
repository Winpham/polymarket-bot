//! Consensus-engine database methods on [`PgPortfolio`].
//!
//! Sibling to `copy_trade.rs`. Handles the tracked-trader universe
//! (auto-followed leaderboard traders, with drop-grace) and the
//! `consensus_signals` / `consensus_alerts` tables used for alerting and
//! forward edge tracking.

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};

use super::postgres::PgPortfolio;

/// One tracked trader as it appears on the leaderboard right now.
#[derive(Debug, Clone)]
pub struct LeaderboardTraderUpsert {
    pub wallet: String,
    pub username: Option<String>,
    pub rank: Option<i32>,
    pub pnl: Option<f64>,
    pub volume: Option<f64>,
    pub periods: String,
    /// Whether this trader votes in consensus (rank ≤ cutoff). Deep traders
    /// (rank > cutoff) are captured/profiled but excluded from backer counts.
    pub consensus_eligible: bool,
}

/// Data needed to upsert one consensus signal.
#[derive(Debug, Clone)]
pub struct NewConsensusSignal {
    /// Owning strategy name (portfolio tag); part of the dedup key.
    pub strategy: String,
    pub condition_id: String,
    pub outcome_index: i32,
    pub outcome_label: String,
    pub title: String,
    pub slug: String,
    pub event_slug: Option<String>,
    pub is_sports: bool,
    /// Raw vote atoms for retroactive strategy replay (the no-backtest superpower).
    pub observed_votes: serde_json::Value,
    pub n_backers: i32,
    pub n_opposers: i32,
    pub net_count: i32,
    pub net_quality: f64,
    pub mean_price: f64,
    pub price_std: f64,
    pub recency_mins: i64,
    pub total_usd: f64,
    pub best_backer_rank: Option<i32>,
    pub score: f64,
    pub tier: String,
    pub backers_json: serde_json::Value,
}

/// One row for the forward 29-feature log (`market_feature_log`, migration 028).
/// Captured at strict-fire time, keyed to its `consensus_signals` row, so the
/// forward `market_resid` model trains on the bot's OWN survivorship-free
/// population. `features` is the YES-oriented [`MarketFeatures`] vector as JSON.
#[derive(Debug, Clone)]
pub struct NewMarketFeatureLog {
    pub signal_id: i64,
    pub condition_id: String,
    pub outcome_index: i32,
    /// Did the consensus outcome == the YES (index-0) token (`outcome_index == 0`).
    pub yes_token: bool,
    /// Consensus-outcome live mid at capture (audit only; NOT a model feature).
    pub clob_mid: Option<f64>,
    /// The 29-wide YES-oriented MarketFeatures vector, serialized.
    pub features: serde_json::Value,
}

/// Prior alert state of a signal (captured at upsert time, before any new alert).
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct ConsensusAlertState {
    pub id: i32,
    pub last_alert_tier: Option<String>,
    pub last_alert_net: Option<i32>,
}

/// One fill atom in the rolling consensus vote window (migration 025). Used both
/// as the insert payload (`insert_window_votes`) and the load result
/// (`load_window_votes`) — the in-memory legacy path builds these directly so the
/// incremental and legacy book-assembly produce identical books.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct WindowVote {
    pub trader_wallet: String,
    pub name: String,
    pub rank: Option<i32>,
    pub pnl: Option<f64>,
    pub quality: f64,
    pub condition_id: String,
    pub outcome_index: i32,
    pub outcome: String,
    pub title: String,
    pub slug: String,
    pub event_slug: Option<String>,
    pub is_sports: bool,
    pub price: f64,
    pub size_usd: f64,
    pub ts: DateTime<Utc>,
}

/// One durable fill atom for the `trader_fills` archive (Phase 0). Captured for
/// BOTH sides off the SAME poll the consensus window uses ("capture once, use
/// twice"). `sport` is the FROZEN slug-derived bucket (single source of truth);
/// resolution columns are filled later by housekeeping (Phase 1).
#[derive(Debug, Clone)]
pub struct NewTraderFill {
    pub wallet: String,
    pub tx_hash: Option<String>,
    pub condition_id: String,
    pub outcome_index: i32,
    pub outcome: String,
    pub side: String,
    pub price: f64,
    pub size_usd: f64,
    pub title: String,
    pub slug: String,
    pub event_slug: Option<String>,
    pub is_sports: bool,
    pub sport: Option<String>,
    /// FROZEN bet-structure bucket (`moneyline|spread|totals|prop|other`);
    /// `None` ⇒ read as `'other'`. Appended after `sport` (never reordered).
    pub bet_type: Option<String>,
    pub ts: DateTime<Utc>,
    /// Provenance (migration 040). `None` ⇒ poll spine (the ~3.0M-row default,
    /// binds to SQL NULL, byte-identical to pre-040 behaviour); `Some("live_onchain")`
    /// ⇒ F2 fast fill; `Some("backfill")` ⇒ historical replay. Appended, never reordered.
    pub source: Option<String>,
    /// Wall clock this process FIRST saw the fill on a live channel (migration 040);
    /// `None` for poll/backfill. Latency = live_seen_at − ts (derived at read).
    pub live_seen_at: Option<DateTime<Utc>>,
}

/// One raw CLOB price-tape tick (migration 040, `clob_price_tape`). Append-only
/// measurement substrate for the latency→drift curve — written ONLY by the
/// flag-gated `live_tape` task, never by the poller. `event_type` is `book`
/// (snapshot) or `price_change` (delta); `exch_ts` is the frame's ms-epoch
/// exchange clock (~100% present), `recv_at` the local WS receive instant.
#[derive(Debug, Clone)]
pub struct NewTapeTick {
    pub asset_id: String,
    pub condition_id: Option<String>,
    pub outcome_index: Option<i16>,
    pub event_type: String,
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
    pub last_price: Option<f64>,
    pub last_size: Option<f64>,
    pub side: Option<String>,
    pub exch_ts: Option<DateTime<Utc>>,
    pub recv_at: DateTime<Utc>,
}

/// A signal awaiting market resolution (forward edge tracking + trajectory).
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct UnresolvedConsensus {
    pub id: i32,
    pub strategy: String,
    pub condition_id: String,
    pub slug: String,
    pub outcome_index: i32,
    pub mean_price: f64,
    pub net_count: i32,
    pub n_backers: i32,
    pub is_sports: bool,
    /// Real executable ask already captured while open (Phase 2). `Some` ⇒ skip
    /// re-fetching the book for this signal.
    pub entry_ask: Option<f64>,
    /// When the signal was first detected — the decision-time anchor. Used to
    /// meter the capture lag (`entry_ask_at − first_detected_at`).
    pub first_detected_at: DateTime<Utc>,
}

impl PgPortfolio {
    // --- Tracked-trader universe (auto-follow) ---

    /// Upsert one leaderboard trader, marking it active and seen-now.
    /// Does not clobber a manually-followed row's `source`. Deliberately never
    /// mentions `earned_eligible` (migration 035): an EARNED promotion is durable
    /// across every leaderboard refresh and rank churn by construction.
    pub async fn upsert_tracked_trader(&self, t: &LeaderboardTraderUpsert) -> Result<()> {
        sqlx::query(
            "INSERT INTO followed_traders \
               (proxy_wallet, username, source, rank, pnl, volume, periods, \
                consensus_eligible, active, last_seen_on_lb) \
             VALUES ($1, $2, 'leaderboard', $3, $4, $5, $6, $7, TRUE, NOW()) \
             ON CONFLICT (proxy_wallet) DO UPDATE SET \
               username        = COALESCE(EXCLUDED.username, followed_traders.username), \
               rank            = EXCLUDED.rank, \
               pnl             = EXCLUDED.pnl, \
               volume          = EXCLUDED.volume, \
               periods         = EXCLUDED.periods, \
               consensus_eligible = CASE \
                 WHEN followed_traders.source = 'manual' \
                   THEN followed_traders.consensus_eligible \
                 ELSE EXCLUDED.consensus_eligible END, \
               active          = TRUE, \
               last_seen_on_lb = NOW()",
        )
        .bind(&t.wallet)
        .bind(&t.username)
        .bind(t.rank)
        .bind(t.pnl)
        .bind(t.volume)
        .bind(&t.periods)
        .bind(t.consensus_eligible)
        .execute(&self.pool)
        .await
        .context("upsert_tracked_trader")?;
        Ok(())
    }

    /// Deactivate auto-tracked traders not seen on the leaderboard since `cutoff`.
    /// Only touches `source = 'leaderboard'` rows — manual `/follow`s are untouched.
    /// Returns the number of traders deactivated.
    pub async fn deactivate_stale_tracked(&self, cutoff: DateTime<Utc>) -> Result<u64> {
        let res = sqlx::query(
            "UPDATE followed_traders SET active = FALSE \
             WHERE source = 'leaderboard' AND active = TRUE \
               AND (last_seen_on_lb IS NULL OR last_seen_on_lb < $1)",
        )
        .bind(cutoff)
        .execute(&self.pool)
        .await
        .context("deactivate_stale_tracked")?;
        Ok(res.rows_affected())
    }

    /// Count active auto-tracked (leaderboard) traders.
    pub async fn count_tracked_traders(&self) -> Result<i64> {
        let (n,): (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM followed_traders \
             WHERE active = TRUE AND source = 'leaderboard'",
        )
        .fetch_one(&self.pool)
        .await
        .context("count_tracked_traders")?;
        Ok(n)
    }

    /// Split the active leaderboard universe into `(hot, deep)` — consensus-eligible
    /// (rank ≤ cutoff, voting) vs deep candidates (captured/profiled, not voting).
    /// The headline for the depth-widening: how much candidate pool we carry vs how
    /// much of it actually feeds the engine.
    pub async fn count_tracked_split(&self) -> Result<(i64, i64)> {
        let row: (i64, i64) = sqlx::query_as(
            "SELECT \
               COUNT(*) FILTER (WHERE consensus_eligible) AS hot, \
               COUNT(*) FILTER (WHERE NOT consensus_eligible) AS deep \
             FROM followed_traders WHERE active = TRUE AND source = 'leaderboard'",
        )
        .fetch_one(&self.pool)
        .await
        .context("count_tracked_split")?;
        Ok(row)
    }

    // --- Consensus signals ---

    /// Upsert a consensus signal, returning its id and the alert state that was
    /// recorded *before* this upsert (so the caller can decide whether to alert).
    pub async fn upsert_consensus_signal(
        &self,
        s: &NewConsensusSignal,
    ) -> Result<ConsensusAlertState> {
        let state: ConsensusAlertState = sqlx::query_as(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, outcome_label, title, slug, event_slug, \
                is_sports, observed_votes, n_backers, n_opposers, net_count, net_quality, \
                mean_price, price_std, recency_mins, total_usd, best_backer_rank, score, tier, \
                backers, initial_n_backers, initial_net_count, initial_mean_price, \
                initial_price_std, initial_recency_mins, initial_total_usd, \
                initial_best_backer_rank, last_updated_at) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21, \
                     $10,$12,$14,$15,$16,$17,$18,NOW()) \
             ON CONFLICT (strategy, condition_id, outcome_index) DO UPDATE SET \
               outcome_label    = EXCLUDED.outcome_label, \
               title            = EXCLUDED.title, \
               slug             = EXCLUDED.slug, \
               event_slug       = EXCLUDED.event_slug, \
               is_sports        = EXCLUDED.is_sports, \
               observed_votes   = EXCLUDED.observed_votes, \
               n_backers        = EXCLUDED.n_backers, \
               n_opposers       = EXCLUDED.n_opposers, \
               net_count        = EXCLUDED.net_count, \
               net_quality      = EXCLUDED.net_quality, \
               mean_price       = EXCLUDED.mean_price, \
               price_std        = EXCLUDED.price_std, \
               recency_mins     = EXCLUDED.recency_mins, \
               total_usd        = EXCLUDED.total_usd, \
               best_backer_rank = EXCLUDED.best_backer_rank, \
               score            = EXCLUDED.score, \
               tier             = EXCLUDED.tier, \
               backers          = EXCLUDED.backers, \
               last_updated_at  = NOW() \
             RETURNING id, last_alert_tier, last_alert_net",
        )
        .bind(&s.strategy)
        .bind(&s.condition_id)
        .bind(s.outcome_index)
        .bind(&s.outcome_label)
        .bind(&s.title)
        .bind(&s.slug)
        .bind(&s.event_slug)
        .bind(s.is_sports)
        .bind(&s.observed_votes)
        .bind(s.n_backers)
        .bind(s.n_opposers)
        .bind(s.net_count)
        .bind(s.net_quality)
        .bind(s.mean_price)
        .bind(s.price_std)
        .bind(s.recency_mins)
        .bind(s.total_usd)
        .bind(s.best_backer_rank)
        .bind(s.score)
        .bind(&s.tier)
        .bind(&s.backers_json)
        .fetch_one(&self.pool)
        .await
        .context("upsert_consensus_signal")?;
        Ok(state)
    }

    /// Record that an alert was pushed for a signal: append to the log and stamp
    /// the dedup state on the signal row.
    pub async fn record_consensus_alert(
        &self,
        signal_id: i32,
        strategy: &str,
        tier: &str,
        net_count: i32,
        score: f64,
    ) -> Result<()> {
        sqlx::query(
            "UPDATE consensus_signals \
             SET last_alert_tier = $2, last_alert_net = $3, last_alerted_at = NOW() \
             WHERE id = $1",
        )
        .bind(signal_id)
        .bind(tier)
        .bind(net_count)
        .execute(&self.pool)
        .await
        .context("record_consensus_alert (update signal)")?;

        sqlx::query(
            "INSERT INTO consensus_alerts (signal_id, strategy, tier, net_count, score) \
             VALUES ($1, $2, $3, $4, $5)",
        )
        .bind(signal_id)
        .bind(strategy)
        .bind(tier)
        .bind(net_count)
        .bind(score)
        .execute(&self.pool)
        .await
        .context("record_consensus_alert (insert log)")?;
        Ok(())
    }

    /// Cross-STRATEGY alert dedup: has any OTHER strategy already pushed an
    /// alert for this (condition, outcome) within the last `mins` minutes?
    /// Same-strategy history is deliberately excluded so a strategy's own
    /// re-alert logic (tier upgrade / net delta) is untouched — with a single
    /// alerting strategy this can never fire, keeping the incumbent behavior
    /// byte-identical.
    pub async fn recent_alert_by_other_strategy(
        &self,
        condition_id: &str,
        outcome_index: i32,
        strategy: &str,
        mins: i64,
    ) -> Result<bool> {
        let (exists,): (bool,) = sqlx::query_as(
            "SELECT EXISTS ( \
                 SELECT 1 FROM consensus_alerts a \
                 JOIN consensus_signals s ON s.id = a.signal_id \
                 WHERE s.condition_id = $1 AND s.outcome_index = $2 \
                   AND a.strategy <> $3 \
                   AND a.sent_at > NOW() - make_interval(mins => $4::int) \
             )",
        )
        .bind(condition_id)
        .bind(outcome_index)
        .bind(strategy)
        .bind(mins as i32)
        .fetch_one(&self.pool)
        .await
        .context("recent_alert_by_other_strategy")?;
        Ok(exists)
    }

    /// Build a `/consensus` summary of the most recent strong/elite signals for
    /// one strategy (default the alerting `strict`, so the list reflects pushes).
    pub async fn consensus_summary(&self, strategy: &str, limit: i64) -> Result<String> {
        #[derive(sqlx::FromRow)]
        struct Row {
            title: String,
            outcome_label: String,
            tier: String,
            net_count: i32,
            n_backers: i32,
            n_opposers: i32,
            mean_price: f64,
            is_sports: bool,
            total_usd: f64,
        }
        let rows: Vec<Row> = sqlx::query_as(
            "SELECT title, outcome_label, tier, net_count, n_backers, n_opposers, \
                    mean_price, is_sports, total_usd \
             FROM consensus_signals \
             WHERE strategy = $1 AND tier IN ('STRONG','ELITE') \
               AND last_updated_at > NOW() - INTERVAL '24 hours' \
             ORDER BY score DESC LIMIT $2",
        )
        .bind(strategy)
        .bind(limit)
        .fetch_all(&self.pool)
        .await
        .context("consensus_summary")?;

        if rows.is_empty() {
            return Ok("🤝 *Consensus* — no strong consensus signals in the last 24h.".to_string());
        }
        let mut out = String::from("🤝 *Active Consensus Signals* (24h)\n");
        for r in rows {
            let tier_emoji = if r.tier == "ELITE" { "🔥" } else { "🟢" };
            let sport = if r.is_sports { "⚽ " } else { "" };
            out.push_str(&format!(
                "\n{tier_emoji} {sport}*{title}* → BUY *{outcome}*\n   \
                 {net:+} net ({back}v{opp}) @ ~{price:.0}¢ | ${usd:.0}k",
                title = truncate(&r.title, 50),
                outcome = r.outcome_label,
                net = r.net_count,
                back = r.n_backers,
                opp = r.n_opposers,
                price = r.mean_price * 100.0,
                usd = r.total_usd / 1000.0,
            ));
        }
        Ok(out)
    }

    // --- Forward edge tracking (resolution wired in Phase C) ---

    /// Signals that have not yet been resolved, for housekeeping to settle.
    pub async fn unresolved_consensus_signals(&self) -> Result<Vec<UnresolvedConsensus>> {
        let rows: Vec<UnresolvedConsensus> = sqlx::query_as(
            "SELECT id, strategy, condition_id, COALESCE(slug, '') AS slug, outcome_index, \
                    mean_price, net_count, n_backers, is_sports, entry_ask, first_detected_at \
             FROM consensus_signals WHERE resolved = FALSE",
        )
        .fetch_all(&self.pool)
        .await
        .context("unresolved_consensus_signals")?;
        Ok(rows)
    }

    /// Mark a consensus signal resolved and whether the consensus outcome won.
    pub async fn resolve_consensus_signal(
        &self,
        id: i32,
        outcome_won: bool,
        market_id: &str,
    ) -> Result<()> {
        sqlx::query(
            "UPDATE consensus_signals \
             SET resolved = TRUE, outcome_won = $2, market_id = $3, resolved_at = NOW() \
             WHERE id = $1",
        )
        .bind(id)
        .bind(outcome_won)
        .bind(market_id)
        .execute(&self.pool)
        .await
        .context("resolve_consensus_signal")?;
        Ok(())
    }

    /// Append a trajectory snapshot (the signal's "stock chart" point) and update
    /// the signal's latest + initial live price. `market_price` is the live CLOB
    /// price of the consensus outcome; `None` when it couldn't be fetched.
    ///
    /// **Change-only:** a new row is written only when the chart actually moves —
    /// the consensus state (net/backers) changed or the price moved ≥0.5¢ since
    /// the last snapshot. Stable markets don't accumulate identical rows, so the
    /// time-series stays compact while preserving every real move.
    ///
    /// Returns `true` iff this call FIRST-SET `initial_market_price` (the signal's
    /// decision-time mid) — i.e. this is the first live price the signal ever saw.
    /// The housekeeping capture uses it to tag a decision-time ask (paired with the
    /// same mid) vs a lagged fallback. `false` when the price was already set or
    /// `market_price` is `None`.
    pub async fn snapshot_consensus_signal(
        &self,
        signal_id: i32,
        net_count: i32,
        n_backers: i32,
        mean_entry: f64,
        market_price: Option<f64>,
    ) -> Result<bool> {
        sqlx::query(
            "INSERT INTO consensus_snapshots \
               (signal_id, net_count, n_backers, mean_entry, market_price) \
             SELECT $1, $2, $3, $4, $5 \
             WHERE NOT EXISTS ( \
               SELECT 1 FROM consensus_snapshots s \
               WHERE s.signal_id = $1 \
                 AND s.ts = (SELECT MAX(ts) FROM consensus_snapshots WHERE signal_id = $1) \
                 AND s.net_count = $2 AND s.n_backers = $3 \
                 AND ABS(COALESCE(s.market_price, -1) - COALESCE($5, -1)) < 0.005 \
             )",
        )
        .bind(signal_id)
        .bind(net_count)
        .bind(n_backers)
        .bind(mean_entry)
        .bind(market_price)
        .execute(&self.pool)
        .await
        .context("snapshot_consensus_signal (insert)")?;

        // Latest price always; initial price only the first time we see one. The
        // `before` CTE captures the pre-update value so we can report whether THIS
        // call first-set `initial_market_price` (the decision-time moment).
        let mut first_price = false;
        if let Some(price) = market_price {
            first_price = sqlx::query_scalar::<_, bool>(
                "WITH before AS ( \
                     SELECT initial_market_price AS prev FROM consensus_signals WHERE id = $1 \
                 ) \
                 UPDATE consensus_signals c \
                 SET last_market_price = $2, \
                     initial_market_price = COALESCE(c.initial_market_price, $2) \
                 FROM before \
                 WHERE c.id = $1 \
                 RETURNING (before.prev IS NULL)",
            )
            .bind(signal_id)
            .bind(price)
            .fetch_optional(&self.pool)
            .await
            .context("snapshot_consensus_signal (price)")?
            .unwrap_or(false);
        }
        Ok(first_price)
    }

    /// Capture the real executable best ASK for a signal ONCE while it is open
    /// (Phase 2). COALESCE-once + `resolved = FALSE`: never overwritten and never
    /// written post-resolution, exactly like `initial_market_price` — so it stays
    /// a genuinely pre-resolution executable price (leak-free). No-op if already
    /// set. Returns whether a value was newly written.
    pub async fn set_entry_ask(&self, signal_id: i32, ask: f64) -> Result<bool> {
        let res = sqlx::query(
            "UPDATE consensus_signals SET entry_ask = $2 \
             WHERE id = $1 AND entry_ask IS NULL AND resolved = FALSE",
        )
        .bind(signal_id)
        .bind(ask)
        .execute(&self.pool)
        .await
        .context("set_entry_ask")?;
        Ok(res.rows_affected() > 0)
    }

    /// Capture the real executable best ASK ONCE while open **together with its
    /// provenance** (Phase 1): `entry_ask_at = NOW()` (WHEN it was captured) and
    /// `entry_ask_mid = $mid` (the CLOB mid at the SAME instant). Same set-once +
    /// `resolved = FALSE` guard as [`set_entry_ask`] — never overwritten, never
    /// written post-resolution (leak-free). `mid` must be the mid observed in the
    /// same pass as `ask`, so `entry_ask − entry_ask_mid` is the real haircut and
    /// `entry_ask_at ≈ first_detected_at` proves a decision-time capture. Returns
    /// whether a value was newly written (no-op if already set). PAPER/measurement
    /// only — records what the market WAS asking; never places an order.
    pub async fn set_entry_ask_decision(&self, signal_id: i32, ask: f64, mid: f64) -> Result<bool> {
        let res = sqlx::query(
            "UPDATE consensus_signals \
             SET entry_ask = $2, entry_ask_at = NOW(), entry_ask_mid = $3 \
             WHERE id = $1 AND entry_ask IS NULL AND resolved = FALSE",
        )
        .bind(signal_id)
        .bind(ask)
        .bind(mid)
        .execute(&self.pool)
        .await
        .context("set_entry_ask_decision")?;
        Ok(res.rows_affected() > 0)
    }

    /// The full trajectory of a signal — its "stock chart": consensus state +
    /// live price over time. Used by `/signal` and CLV/drift analysis.
    pub async fn consensus_trajectory(&self, signal_id: i32) -> Result<Vec<ConsensusSnapshot>> {
        let rows: Vec<ConsensusSnapshot> = sqlx::query_as(
            "SELECT ts, net_count, n_backers, mean_entry, market_price \
             FROM consensus_snapshots WHERE signal_id = $1 ORDER BY ts",
        )
        .bind(signal_id)
        .fetch_all(&self.pool)
        .await
        .context("consensus_trajectory")?;
        Ok(rows)
    }

    /// Aggregate forward-tracking scoreboard: (resolved, won, hit_rate) overall
    /// and for non-sports, used by `/consensus` stats and validation.
    pub async fn consensus_scoreboard(&self) -> Result<(i64, i64, i64, i64)> {
        let (res, won): (Option<i64>, Option<i64>) = sqlx::query_as(
            "SELECT COUNT(*) FILTER (WHERE resolved), \
                    COUNT(*) FILTER (WHERE resolved AND outcome_won) \
             FROM consensus_signals",
        )
        .fetch_one(&self.pool)
        .await
        .context("consensus_scoreboard")?;
        let (res_ns, won_ns): (Option<i64>, Option<i64>) = sqlx::query_as(
            "SELECT COUNT(*) FILTER (WHERE resolved AND NOT is_sports), \
                    COUNT(*) FILTER (WHERE resolved AND outcome_won AND NOT is_sports) \
             FROM consensus_signals",
        )
        .fetch_one(&self.pool)
        .await
        .context("consensus_scoreboard (non-sports)")?;
        Ok((
            res.unwrap_or(0),
            won.unwrap_or(0),
            res_ns.unwrap_or(0),
            won_ns.unwrap_or(0),
        ))
    }

    /// Per-strategy forward-tracking scoreboard, best edge first. This is the
    /// instrument that ranks the portfolio: `edge = AVG(outcome_won − entry)`
    /// is the leak-free realized edge vs the AT-FIRE price each signal entered at.
    pub async fn consensus_scoreboard_by_strategy(&self) -> Result<Vec<StrategyScore>> {
        // The denominator (catalog #1). For each resolved signal, advantage
        // `a = outcome_won - entry`, where `entry` is the AT-FIRE consensus mean
        // (`initial_mean_price`, set once at insert and never updated — see
        // `upsert_consensus_signal`). `mean_price` is refreshed on every upsert
        // with the CURRENT window state, so it embeds post-fire information (avg
        // drift ≈ +1.2¢ on strict; ~29% of rows move >2¢) — judging on it both
        // leaks and, empirically, UNDERSTATES the at-fire edge the strategy spec
        // acts on (REFINED-STRATEGY rule 4: act at fire). The drifted `mean_price`
        // stays stored for capture/diagnostics but never judges. (2026-07-02 run;
        // COALESCE is belt-and-suspenders for any legacy row without the initial.)
        // The `_blind` arm captures EVERY observed outcome, so its per-price-band
        // average `a` is the blind baseline that favorite-longshot bias would
        // already earn — banded on the SAME at-fire entry for consistency. A
        // strategy's SURPLUS = AVG(a - blind_edge[band]) is what it adds beyond
        // blindly betting that band — the only edge number that isn't gamed by
        // loading favorites.
        // `distinct_events` is the honest (de-correlated) sample size — outcomes
        // of one event_slug are correlated (the within-match leak); the promotion
        // gate keys off distinct_events, not raw resolved count.
        // Surplus is computed CLUSTER-ROBUST: per-signal surplus is first averaged
        // to the EVENT level (event_slug), then across events — so correlated
        // outcomes of one event count once (the within-match leak fix). `surplus`
        // and `surplus_sd` are over events; `distinct_events` is the gate's N.
        // CLV instrumentation (same EVENT clustering, over resolved rows with a
        // captured `initial_market_price`): `our_clv = AVG_event(outcome_won −
        // initial_market_price)` is the edge if we'd entered at the first live mid
        // we saw; `capture_lag = AVG_event(initial_market_price − entry)` is the
        // gap between the mid when we *noticed* and the at-fire price the sharps
        // paid. A materially negative `capture_lag` means faster polling has value.
        let rows: Vec<StrategyScore> = sqlx::query_as(
            "WITH adv AS ( \
                 SELECT strategy, COALESCE(event_slug, condition_id) AS ev, resolved, outcome_won, \
                        width_bucket(COALESCE(initial_mean_price, mean_price), 0.0, 1.0, 5) AS band, \
                        (first_detected_at AT TIME ZONE 'UTC')::date AS day, \
                        (outcome_won::int)::double precision \
                          - COALESCE(initial_mean_price, mean_price) AS a \
                 FROM consensus_signals \
             ), \
             blind AS ( \
                 SELECT band, AVG(a) AS blind_edge \
                 FROM adv WHERE strategy = '_blind' AND resolved GROUP BY band \
             ), \
             sig AS ( \
                 SELECT v.strategy, v.ev, v.day, v.resolved, v.outcome_won, v.a, \
                        v.a - COALESCE(b.blind_edge, 0) AS surplus \
                 FROM adv v LEFT JOIN blind b USING (band) WHERE v.strategy <> '_blind' \
             ), \
             evt AS ( \
                 SELECT strategy, ev, AVG(surplus) AS ev_surplus, MIN(day) AS ev_day \
                 FROM sig WHERE resolved GROUP BY strategy, ev \
             ), \
             es AS ( \
                 SELECT strategy, COUNT(*) AS n_events, AVG(ev_surplus) AS surplus, \
                        STDDEV_SAMP(ev_surplus) AS surplus_sd, \
                        COUNT(DISTINCT ev_day) AS distinct_days FROM evt GROUP BY strategy \
             ), \
             clv_evt AS ( \
                 SELECT strategy, COALESCE(event_slug, condition_id) AS ev, \
                        AVG((outcome_won::int)::double precision - initial_market_price) AS ev_clv, \
                        AVG(initial_market_price - COALESCE(initial_mean_price, mean_price)) AS ev_lag \
                 FROM consensus_signals \
                 WHERE resolved AND initial_market_price IS NOT NULL AND strategy <> '_blind' \
                 GROUP BY strategy, ev \
             ), \
             clv AS ( \
                 SELECT strategy, AVG(ev_clv) AS our_clv, AVG(ev_lag) AS capture_lag \
                 FROM clv_evt GROUP BY strategy \
             ) \
             SELECT s.strategy, \
                    COUNT(*) FILTER (WHERE s.resolved)                   AS resolved, \
                    COALESCE(es.n_events, 0)                             AS distinct_events, \
                    COALESCE(es.distinct_days, 0)                        AS distinct_days, \
                    COUNT(*) FILTER (WHERE s.resolved AND s.outcome_won) AS won, \
                    AVG(s.a) FILTER (WHERE s.resolved)                   AS edge, \
                    es.surplus                                          AS surplus, \
                    es.surplus_sd                                       AS surplus_sd, \
                    clv.our_clv                                         AS our_clv, \
                    clv.capture_lag                                     AS capture_lag \
             FROM sig s LEFT JOIN es ON es.strategy = s.strategy \
                        LEFT JOIN clv ON clv.strategy = s.strategy \
             GROUP BY s.strategy, es.n_events, es.distinct_days, es.surplus, es.surplus_sd, clv.our_clv, clv.capture_lag \
             ORDER BY es.surplus DESC NULLS LAST",
        )
        .fetch_all(&self.pool)
        .await
        .context("consensus_scoreboard_by_strategy")?;
        Ok(rows)
    }

    /// The **honest, realizable** per-strategy P&L instrument (read-only). Unlike
    /// `consensus_scoreboard_by_strategy` (whose `edge` is vs `mean_price`, the
    /// SHARPS' average fill we cannot get), this measures the outcome against the
    /// **price we actually observed while the market was open** (`initial_market_price`
    /// = CLV), minus an explicit buy-side **execution haircut** — the edge we could
    /// realize. Everything is event-clustered at `COALESCE(event_slug, condition_id)`
    /// (the within-match leak fix) BEFORE aggregating across events.
    ///
    /// `exec_haircut` (price units) is added to the captured mid to get the
    /// executable entry (`entry = p0 + h`); `fee_pct` is a fractional fee on ROI.
    /// When Phase 2's real `entry_ask` is captured it is preferred over the mid+
    /// haircut heuristic. Leak-free by construction: `outcome_won` is read for
    /// scoring ONLY, always paired with a price captured strictly before resolution.
    /// SQL stays sums/means/stddev/percentiles — the corrected bound + GO/HOLD
    /// verdict live in the binary (`scanner::honest`).
    pub async fn honest_pnl_by_strategy(
        &self,
        exec_haircut: f64,
        fee_pct: f64,
        decision_lag_secs: f64,
    ) -> Result<Vec<HonestPnl>> {
        let rows: Vec<HonestPnl> = sqlx::query_as(
            "WITH base AS ( \
                 SELECT strategy, COALESCE(event_slug, condition_id) AS ev, \
                        (outcome_won::int)::double precision AS w, \
                        COALESCE(entry_ask, initial_market_price + $1) AS entry, \
                        initial_market_price AS p0, mean_price, total_usd \
                 FROM consensus_signals \
                 WHERE resolved AND initial_market_price IS NOT NULL AND strategy <> '_blind' \
             ), \
             sig AS ( \
                 SELECT strategy, ev, w, p0, mean_price, total_usd, entry, \
                        (w - p0) AS clv_share, \
                        (w - p0) / NULLIF(p0, 0) AS clv_roi, \
                        (w - entry) AS honest_edge_share, \
                        (w - entry) / NULLIF(entry, 0) - $2 AS honest_roi, \
                        (w - mean_price) AS sharp_adv \
                 FROM base \
             ), \
             evt AS ( \
                 SELECT strategy, ev, AVG(w) AS ev_hit, AVG(clv_share) AS ev_clv, \
                        AVG(clv_roi) AS ev_clvroi, AVG(honest_edge_share) AS ev_hedge, \
                        AVG(honest_roi) AS ev_hroi, AVG(sharp_adv) AS ev_sharp \
                 FROM sig GROUP BY strategy, ev \
             ), \
             agg AS ( \
                 SELECT strategy, COUNT(*) AS distinct_events, AVG(ev_hit) AS hit_rate, \
                        AVG(ev_clv) AS clv_share, AVG(ev_clvroi) AS clv_roi, \
                        AVG(ev_hedge) AS honest_edge_share, AVG(ev_hroi) AS honest_roi, \
                        STDDEV_SAMP(ev_hroi) AS honest_roi_sd, AVG(ev_sharp) AS sharp_edge \
                 FROM evt GROUP BY strategy \
             ), \
             liq AS ( \
                 SELECT strategy, COUNT(*) AS resolved, \
                        COUNT(*) FILTER (WHERE entry_ask IS NOT NULL) AS ask_rows, \
                        COUNT(*) FILTER (WHERE entry_ask IS NOT NULL AND entry_ask_at IS NOT NULL \
                            AND EXTRACT(EPOCH FROM (entry_ask_at - first_detected_at)) <= $3) AS decision_rows, \
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY (entry_ask - entry_ask_mid)) \
                            FILTER (WHERE entry_ask IS NOT NULL AND entry_ask_mid IS NOT NULL \
                                AND EXTRACT(EPOCH FROM (entry_ask_at - first_detected_at)) <= $3) AS median_haircut, \
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY total_usd) AS median_sharp_usd, \
                        AVG((EXTRACT(EPOCH FROM (resolved_at - first_detected_at)) / 3600.0)::double precision) AS avg_hours_to_resolve, \
                        GREATEST((EXTRACT(EPOCH FROM (MAX(resolved_at) - MIN(resolved_at))) / 86400.0)::double precision, 1.0) AS span_days \
                 FROM consensus_signals \
                 WHERE resolved AND initial_market_price IS NOT NULL AND strategy <> '_blind' \
                 GROUP BY strategy \
             ), \
             base_r AS ( \
                 SELECT strategy, COALESCE(event_slug, condition_id) AS ev, \
                        (outcome_won::int)::double precision AS w, entry_ask AS entry \
                 FROM consensus_signals \
                 WHERE resolved AND strategy <> '_blind' AND initial_market_price IS NOT NULL \
                   AND entry_ask IS NOT NULL AND entry_ask_at IS NOT NULL \
                   AND EXTRACT(EPOCH FROM (entry_ask_at - first_detected_at)) <= $3 \
             ), \
             evt_r AS ( \
                 SELECT strategy, ev, AVG((w - entry) / NULLIF(entry, 0) - $2) AS ev_rroi \
                 FROM base_r GROUP BY strategy, ev \
             ), \
             agg_r AS ( \
                 SELECT strategy, COUNT(*) AS realized_events, AVG(ev_rroi) AS realized_roi, \
                        STDDEV_SAMP(ev_rroi) AS realized_roi_sd \
                 FROM evt_r GROUP BY strategy \
             ) \
             SELECT a.strategy, l.resolved, a.distinct_events, a.hit_rate, \
                    a.clv_share, a.clv_roi, a.honest_edge_share, a.honest_roi, a.honest_roi_sd, \
                    l.median_sharp_usd, l.avg_hours_to_resolve, \
                    (a.distinct_events::double precision / l.span_days) AS bets_per_day, \
                    a.sharp_edge, \
                    (l.ask_rows::double precision / NULLIF(l.resolved, 0)) AS ask_coverage, \
                    (l.decision_rows::double precision / NULLIF(l.resolved, 0)) AS decision_coverage, \
                    l.median_haircut, \
                    r.realized_events, r.realized_roi, r.realized_roi_sd \
             FROM agg a JOIN liq l USING (strategy) LEFT JOIN agg_r r USING (strategy) \
             ORDER BY a.honest_roi DESC NULLS LAST",
        )
        .bind(exec_haircut)
        .bind(fee_pct)
        .bind(decision_lag_secs)
        .fetch_all(&self.pool)
        .await
        .context("honest_pnl_by_strategy")?;
        Ok(rows)
    }

    /// Per (strategy × segment) honest-ROI + event count for the regime/band/
    /// horizon breakdown (read-only). Segments: `day` (day-regime = the persistence
    /// axis the pilot verdict keys on), `band` (`width_bucket(p0)`), `horizon`
    /// (`same_day` if resolved <24h after first detection else `multi_day`), and
    /// `sport` (the true disjointness axis — event_slug prefix → crypto/tennis/
    /// soccer/mlb/cs2/other; this mapping deliberately mirrors
    /// `scripts/selection_null.py::REGIMES` — change both together). Same
    /// event-clustering + leak-free discipline as `honest_pnl_by_strategy`.
    pub async fn honest_pnl_segments(
        &self,
        exec_haircut: f64,
        fee_pct: f64,
    ) -> Result<Vec<HonestSegment>> {
        let rows: Vec<HonestSegment> = sqlx::query_as(
            "WITH base AS ( \
                 SELECT strategy, COALESCE(event_slug, condition_id) AS ev, \
                        (outcome_won::int)::double precision AS w, \
                        COALESCE(entry_ask, initial_market_price + $1) AS entry, \
                        initial_market_price AS p0, resolved_at, event_slug, \
                        EXTRACT(EPOCH FROM (resolved_at - first_detected_at)) / 3600.0 AS hrs \
                 FROM consensus_signals \
                 WHERE resolved AND initial_market_price IS NOT NULL AND strategy <> '_blind' \
             ), \
             sig AS ( \
                 SELECT strategy, ev, \
                        (w - entry) / NULLIF(entry, 0) - $2 AS honest_roi, \
                        to_char(date_trunc('day', resolved_at), 'YYYY-MM-DD') AS day_key, \
                        width_bucket(p0, 0.0, 1.0, 5)::text AS band_key, \
                        CASE WHEN hrs < 24 THEN 'same_day' ELSE 'multi_day' END AS horizon_key, \
                        CASE WHEN event_slug ~ '^(btc|eth|sol|xrp|bnb|doge|hype|bitcoin|ethereum)' THEN 'crypto' \
                             WHEN event_slug ~ '^(atp|wta|itf)' THEN 'tennis' \
                             WHEN event_slug LIKE 'fifwc%' THEN 'soccer' \
                             WHEN event_slug LIKE 'mlb%' THEN 'mlb' \
                             WHEN event_slug LIKE 'cs%' THEN 'cs2' \
                             ELSE 'other' END AS sport_key \
                 FROM base \
             ), \
             u AS ( \
                 SELECT strategy, 'day'  AS seg_kind, day_key     AS seg_key, ev, honest_roi FROM sig \
                 UNION ALL \
                 SELECT strategy, 'band' AS seg_kind, band_key    AS seg_key, ev, honest_roi FROM sig \
                 UNION ALL \
                 SELECT strategy, 'horizon' AS seg_kind, horizon_key AS seg_key, ev, honest_roi FROM sig \
                 UNION ALL \
                 SELECT strategy, 'sport' AS seg_kind, sport_key   AS seg_key, ev, honest_roi FROM sig \
             ), \
             evt AS ( \
                 SELECT strategy, seg_kind, seg_key, ev, AVG(honest_roi) AS ev_hroi \
                 FROM u GROUP BY strategy, seg_kind, seg_key, ev \
             ) \
             SELECT strategy, seg_kind, seg_key, COUNT(*) AS n_events, AVG(ev_hroi) AS honest_roi \
             FROM evt GROUP BY strategy, seg_kind, seg_key \
             ORDER BY strategy, seg_kind, seg_key",
        )
        .bind(exec_haircut)
        .bind(fee_pct)
        .fetch_all(&self.pool)
        .await
        .context("honest_pnl_segments")?;
        Ok(rows)
    }

    /// Append ONE paper bet to the honest equity ledger for a just-resolved
    /// (strategy, condition, outcome) — the ongoing PAPER track record (Phase 3).
    /// Entry is the realizable `COALESCE(entry_ask, initial_market_price + haircut)`;
    /// `pnl = stake × ((won − entry)/entry − fee)`; `cum_equity` is the running
    /// strategy equity at append time. Idempotent: `ON CONFLICT DO NOTHING`, so
    /// re-running resolution never double-appends. Skips rows without a captured
    /// pre-resolution price (entry undefined). Returns whether a row was appended.
    /// PAPER only — this NEVER places real money.
    pub async fn append_paper_bet(
        &self,
        strategy: &str,
        condition_id: &str,
        outcome_index: i32,
        flat_stake: f64,
        exec_haircut: f64,
        fee_pct: f64,
    ) -> Result<bool> {
        let res = sqlx::query(
            "WITH src AS ( \
                 SELECT strategy, condition_id, outcome_index, \
                        COALESCE(resolved_at, NOW()) AS rat, \
                        COALESCE(entry_ask, initial_market_price + $5) AS entry, \
                        outcome_won \
                 FROM consensus_signals \
                 WHERE condition_id = $2 AND outcome_index = $3 AND strategy = $1 \
                   AND resolved AND outcome_won IS NOT NULL AND initial_market_price IS NOT NULL \
             ), \
             calc AS ( \
                 SELECT strategy, condition_id, outcome_index, rat, entry, outcome_won, \
                        $4 * (((outcome_won::int)::double precision - entry) / NULLIF(entry, 0) - $6) AS pnl \
                 FROM src \
             ) \
             INSERT INTO honest_paper_ledger \
                 (strategy, condition_id, outcome_index, resolved_at, stake, entry, outcome_won, pnl, cum_equity) \
             SELECT c.strategy, c.condition_id, c.outcome_index, c.rat, $4, c.entry, c.outcome_won, c.pnl, \
                    COALESCE((SELECT SUM(pnl) FROM honest_paper_ledger WHERE strategy = c.strategy), 0) + c.pnl \
             FROM calc c \
             ON CONFLICT (strategy, condition_id, outcome_index) DO NOTHING",
        )
        .bind(strategy)
        .bind(condition_id)
        .bind(outcome_index)
        .bind(flat_stake)
        .bind(exec_haircut)
        .bind(fee_pct)
        .execute(&self.pool)
        .await
        .context("append_paper_bet")?;
        Ok(res.rows_affected() > 0)
    }

    /// The paper equity curve for a strategy: cumulative P&L over time, recomputed
    /// authoritatively as a running sum ordered by resolution (robust to any
    /// out-of-order appends). Points are `(resolved_at, cumulative_equity)`.
    pub async fn equity_curve(&self, strategy: &str) -> Result<Vec<(DateTime<Utc>, f64)>> {
        let rows: Vec<(DateTime<Utc>, f64)> = sqlx::query_as(
            "SELECT resolved_at, \
                    SUM(pnl) OVER (ORDER BY resolved_at, id)::double precision AS cum \
             FROM honest_paper_ledger WHERE strategy = $1 ORDER BY resolved_at, id",
        )
        .bind(strategy)
        .fetch_all(&self.pool)
        .await
        .context("equity_curve")?;
        Ok(rows)
    }

    /// Ledger statistics for a strategy: cumulative P&L, peak, max drawdown, a
    /// daily-returns Sharpe-like ratio, win rate, bet count, and ROI on turnover.
    /// Computed in Rust from the ordered ledger so the SQL stays a plain fetch.
    /// `None` if the strategy has no paper bets yet.
    pub async fn ledger_stats(&self, strategy: &str, fee_pct: f64) -> Result<Option<LedgerStats>> {
        let rows: Vec<(DateTime<Utc>, f64, f64, bool, f64)> = sqlx::query_as(
            "SELECT resolved_at, stake, pnl, outcome_won, entry \
             FROM honest_paper_ledger WHERE strategy = $1 ORDER BY resolved_at, id",
        )
        .bind(strategy)
        .fetch_all(&self.pool)
        .await
        .context("ledger_stats")?;
        if rows.is_empty() {
            return Ok(None);
        }
        Ok(Some(LedgerStats::from_rows(&rows, fee_pct)))
    }

    // --- Dense early-life trajectory (migration 034, decay run Phase 0) ---

    /// Fresh, still-open (market, outcome) pairs eligible for dense early-life
    /// capture: fired within the last `window_mins` by one of `strategies`,
    /// deduped to ONE anchor signal per (condition, outcome) (the earliest-
    /// fired row, so `secs_after_fire` is measured from the true first fire),
    /// capped at `cap`. Read every dense tick; bounded by construction.
    pub async fn dense_capture_candidates(
        &self,
        strategies: &[String],
        window_mins: i64,
        cap: i64,
    ) -> Result<Vec<DenseCandidate>> {
        let rows: Vec<DenseCandidate> = sqlx::query_as(
            "SELECT DISTINCT ON (condition_id, outcome_index) \
                    id AS signal_id, condition_id, outcome_index, \
                    first_detected_at, n_backers \
             FROM consensus_signals \
             WHERE resolved = FALSE \
               AND strategy = ANY($1) \
               AND first_detected_at > NOW() - make_interval(mins => $2::int) \
             ORDER BY condition_id, outcome_index, first_detected_at, id \
             LIMIT $3",
        )
        .bind(strategies)
        .bind(window_mins as i32)
        .bind(cap)
        .fetch_all(&self.pool)
        .await
        .context("dense_capture_candidates")?;
        Ok(rows)
    }

    /// Append one dense trajectory point. Best-effort; the caller treats a
    /// failure as a skipped tick, never as a cycle error.
    pub async fn insert_trajectory_point(
        &self,
        signal_id: i32,
        secs_after_fire: i32,
        mid: Option<f64>,
        ask: Option<f64>,
        n_backers: Option<i32>,
    ) -> Result<()> {
        sqlx::query(
            "INSERT INTO signal_price_trajectory \
                 (signal_id, secs_after_fire, mid, ask, n_backers) \
             VALUES ($1, $2, $3, $4, $5)",
        )
        .bind(signal_id)
        .bind(secs_after_fire)
        .bind(mid)
        .bind(ask)
        .bind(n_backers)
        .execute(&self.pool)
        .await
        .context("insert_trajectory_point")?;
        Ok(())
    }

    // --- L1: incremental polling vote-window store (migration 025) ---

    /// Per-trader consensus cursors (`followed_traders.consensus_polled_at`) for
    /// the active universe, as a `wallet -> last-polled` map. Traders never polled
    /// for consensus are absent (the caller backfills from the window start).
    pub async fn consensus_cursors(
        &self,
    ) -> Result<std::collections::HashMap<String, DateTime<Utc>>> {
        let rows: Vec<(String, DateTime<Utc>)> = sqlx::query_as(
            "SELECT proxy_wallet, consensus_polled_at FROM followed_traders \
             WHERE active = TRUE AND consensus_polled_at IS NOT NULL",
        )
        .fetch_all(&self.pool)
        .await
        .context("consensus_cursors")?;
        Ok(rows.into_iter().collect())
    }

    /// Stamp the consensus cursor for the given wallets to `at` (one batch UPDATE).
    /// Called every cycle for traders that polled OK, so a transient poll failure
    /// just leaves the cursor where it was and the next cycle re-fetches the gap.
    pub async fn set_consensus_cursors(&self, wallets: &[String], at: DateTime<Utc>) -> Result<()> {
        if wallets.is_empty() {
            return Ok(());
        }
        sqlx::query(
            "UPDATE followed_traders SET consensus_polled_at = $2 \
             WHERE proxy_wallet = ANY($1)",
        )
        .bind(wallets)
        .bind(at)
        .execute(&self.pool)
        .await
        .context("set_consensus_cursors")?;
        Ok(())
    }

    /// Append a batch of fill atoms to the rolling window (UNNEST batch insert).
    /// Re-seen atoms (same trader+market+outcome+ts+price) are dropped.
    pub async fn insert_window_votes(&self, votes: &[WindowVote]) -> Result<u64> {
        if votes.is_empty() {
            return Ok(0);
        }
        let trader_wallet: Vec<&str> = votes.iter().map(|v| v.trader_wallet.as_str()).collect();
        let name: Vec<&str> = votes.iter().map(|v| v.name.as_str()).collect();
        let rank: Vec<Option<i32>> = votes.iter().map(|v| v.rank).collect();
        let pnl: Vec<Option<f64>> = votes.iter().map(|v| v.pnl).collect();
        let quality: Vec<f64> = votes.iter().map(|v| v.quality).collect();
        let condition_id: Vec<&str> = votes.iter().map(|v| v.condition_id.as_str()).collect();
        let outcome_index: Vec<i32> = votes.iter().map(|v| v.outcome_index).collect();
        let outcome: Vec<&str> = votes.iter().map(|v| v.outcome.as_str()).collect();
        let title: Vec<&str> = votes.iter().map(|v| v.title.as_str()).collect();
        let slug: Vec<&str> = votes.iter().map(|v| v.slug.as_str()).collect();
        let event_slug: Vec<Option<&str>> = votes.iter().map(|v| v.event_slug.as_deref()).collect();
        let is_sports: Vec<bool> = votes.iter().map(|v| v.is_sports).collect();
        let price: Vec<f64> = votes.iter().map(|v| v.price).collect();
        let size_usd: Vec<f64> = votes.iter().map(|v| v.size_usd).collect();
        let ts: Vec<DateTime<Utc>> = votes.iter().map(|v| v.ts).collect();

        let res = sqlx::query(
            "INSERT INTO consensus_vote_window \
               (trader_wallet, name, rank, pnl, quality, condition_id, outcome_index, \
                outcome, title, slug, event_slug, is_sports, price, size_usd, ts) \
             SELECT * FROM UNNEST( \
               $1::text[], $2::text[], $3::int4[], $4::float8[], $5::float8[], \
               $6::text[], $7::int4[], $8::text[], $9::text[], $10::text[], \
               $11::text[], $12::bool[], $13::float8[], $14::float8[], $15::timestamptz[]) \
             ON CONFLICT (trader_wallet, condition_id, outcome_index, ts, price) DO NOTHING",
        )
        .bind(&trader_wallet)
        .bind(&name)
        .bind(&rank)
        .bind(&pnl)
        .bind(&quality)
        .bind(&condition_id)
        .bind(&outcome_index)
        .bind(&outcome)
        .bind(&title)
        .bind(&slug)
        .bind(&event_slug)
        .bind(&is_sports)
        .bind(&price)
        .bind(&size_usd)
        .bind(&ts)
        .execute(&self.pool)
        .await
        .context("insert_window_votes")?;
        Ok(res.rows_affected())
    }

    /// Append a batch of forward 29-feature snapshots (`market_feature_log`,
    /// migrations 028 + 029) in one UNNEST insert.
    ///
    /// Two snapshots per (signal, condition, outcome) are preserved additively:
    /// * `features` / `captured_at` = the FRESHEST snapshot — re-logging the same
    ///   key updates them (the cycle re-upserts a strict signal as consensus
    ///   strengthens), so they drift to the last pre-resolution state.
    /// * `first_features` / `first_captured_at` = the DECISION-TIME snapshot — set
    ///   on the first INSERT and then held UNCHANGED (`COALESCE(existing, …)`), so a
    ///   re-log never overwrites the first-strict-fire capture. A pre-029 row with a
    ///   NULL `first_features` is opportunistically backfilled from the current
    ///   snapshot the next time it re-logs (going-forward only; its true first snap
    ///   is unrecoverable). Both columns are readable by the trainer's `--capture`.
    ///
    /// Best-effort: the caller logs a failure and never blocks the cycle on it.
    pub async fn log_market_features(&self, rows: &[NewMarketFeatureLog]) -> Result<u64> {
        if rows.is_empty() {
            return Ok(0);
        }
        let signal_id: Vec<i64> = rows.iter().map(|r| r.signal_id).collect();
        let condition_id: Vec<&str> = rows.iter().map(|r| r.condition_id.as_str()).collect();
        let outcome_index: Vec<i32> = rows.iter().map(|r| r.outcome_index).collect();
        let yes_token: Vec<bool> = rows.iter().map(|r| r.yes_token).collect();
        let clob_mid: Vec<Option<f64>> = rows.iter().map(|r| r.clob_mid).collect();
        let features: Vec<serde_json::Value> = rows.iter().map(|r| r.features.clone()).collect();

        let res = sqlx::query(
            "INSERT INTO market_feature_log \
               (signal_id, condition_id, outcome_index, yes_token, clob_mid, features, \
                first_features, first_captured_at) \
             SELECT signal_id, condition_id, outcome_index, yes_token, clob_mid, features, \
                    features, NOW() \
             FROM UNNEST( \
               $1::int8[], $2::text[], $3::int4[], $4::bool[], $5::float8[], $6::jsonb[]) \
               AS t(signal_id, condition_id, outcome_index, yes_token, clob_mid, features) \
             ON CONFLICT (signal_id, condition_id, outcome_index) DO UPDATE SET \
               features          = EXCLUDED.features, \
               clob_mid          = EXCLUDED.clob_mid, \
               captured_at       = NOW(), \
               first_features    = COALESCE(market_feature_log.first_features, EXCLUDED.first_features), \
               first_captured_at = COALESCE(market_feature_log.first_captured_at, EXCLUDED.first_captured_at)",
        )
        .bind(&signal_id)
        .bind(&condition_id)
        .bind(&outcome_index)
        .bind(&yes_token)
        .bind(&clob_mid)
        .bind(&features)
        .execute(&self.pool)
        .await
        .context("log_market_features")?;
        Ok(res.rows_affected())
    }

    /// Accrual progress for the `market_resid` forward log: `(distinct resolved
    /// strict events with a logged feature row, total feature rows logged)`. The
    /// event count mirrors the trainer's `--source forward` population exactly
    /// (resolved strict signals with a known outcome, joined to their feature row),
    /// so the board can show how close the arm is to its ≥30-event first gate read.
    pub async fn market_feature_log_accrual(&self) -> Result<(i64, i64)> {
        let (events, rows): (i64, i64) = sqlx::query_as(
            "SELECT \
               (SELECT COUNT(DISTINCT COALESCE(cs.event_slug, cs.condition_id)) \
                  FROM market_feature_log mfl \
                  JOIN consensus_signals cs ON cs.id = mfl.signal_id \
                 WHERE cs.strategy = 'strict' AND cs.resolved AND cs.outcome_won IS NOT NULL), \
               (SELECT COUNT(*) FROM market_feature_log)",
        )
        .fetch_one(&self.pool)
        .await
        .context("market_feature_log_accrual")?;
        Ok((events, rows))
    }

    /// Load all window fill atoms at or after `since` (the trailing window) for
    /// rebuilding MarketBooks off the indexed DB read instead of the network.
    pub async fn load_window_votes(&self, since: DateTime<Utc>) -> Result<Vec<WindowVote>> {
        // Consensus non-regression seam: only eligible traders' votes enter the
        // book — rank-derived (`consensus_eligible`) OR deliberately EARNED at the
        // belief-blind gate (`earned_eligible`, migration 035; default FALSE makes
        // the OR a no-op until a promotion is recorded). Deep (ineligible) captured
        // votes are still stored in the window (for the shadow study) but excluded
        // from backer/opposer counts. COALESCE default TRUE ⇒ a wallet absent from
        // followed_traders still counts exactly as before, so at the top-40 default
        // (no ineligible rows) this filter is a no-op and the emitted signals are
        // byte-for-byte unchanged.
        let rows: Vec<WindowVote> = sqlx::query_as(
            "SELECT cw.trader_wallet, cw.name, cw.rank, cw.pnl, cw.quality, cw.condition_id, \
                    cw.outcome_index, cw.outcome, cw.title, cw.slug, cw.event_slug, \
                    cw.is_sports, cw.price, cw.size_usd, cw.ts \
             FROM consensus_vote_window cw \
             LEFT JOIN followed_traders ft ON LOWER(ft.proxy_wallet) = cw.trader_wallet \
             WHERE cw.ts >= $1 \
               AND COALESCE(ft.consensus_eligible OR ft.earned_eligible, TRUE) = TRUE",
        )
        .bind(since)
        .fetch_all(&self.pool)
        .await
        .context("load_window_votes")?;
        Ok(rows)
    }

    /// Load the window fill atoms at or after `since` from traders the eligibility
    /// gate currently EXCLUDES (tracked, but neither rank-eligible nor earned).
    /// This is the read-only SHADOW feed: everything a certified deep sharp WOULD
    /// contribute if earned in, kept strictly out of the live book source above.
    /// Complementary by construction — a vote is returned by exactly one of
    /// `load_window_votes` / this (untracked wallets count as eligible there).
    pub async fn load_excluded_window_votes(
        &self,
        since: DateTime<Utc>,
    ) -> Result<Vec<WindowVote>> {
        let rows: Vec<WindowVote> = sqlx::query_as(
            "SELECT cw.trader_wallet, cw.name, cw.rank, cw.pnl, cw.quality, cw.condition_id, \
                    cw.outcome_index, cw.outcome, cw.title, cw.slug, cw.event_slug, \
                    cw.is_sports, cw.price, cw.size_usd, cw.ts \
             FROM consensus_vote_window cw \
             JOIN followed_traders ft ON LOWER(ft.proxy_wallet) = cw.trader_wallet \
             WHERE cw.ts >= $1 \
               AND NOT (ft.consensus_eligible OR ft.earned_eligible)",
        )
        .bind(since)
        .fetch_all(&self.pool)
        .await
        .context("load_excluded_window_votes")?;
        Ok(rows)
    }

    /// Load window fill atoms for the SOFT-MARKET arm (Soft-Market Edge Hunt,
    /// 2026-07-09): ESPORTS markets only, from tracked traders admitted under a WIDER
    /// eligibility rank cutoff (`ft.rank <= cutoff`) OR the standard
    /// consensus_eligible/earned set. This recovers the esports sharps the global
    /// rank-40 `consensus_eligible` gate excludes — the diagnosed dominant conversion
    /// cause (reports/ESPORTS-CONVERSION-GAP.json) — WITHOUT touching the live feed:
    /// `load_window_votes` is unchanged, so every incumbent arm's book stays
    /// byte-identical. Esports isolation is by the documented discipline slug-prefix
    /// set (mirrors the diagnosis classifier); non-esports markets are never returned.
    /// Called ONLY when `CONSENSUS_SOFT_MARKET_ARM` is on.
    pub async fn load_soft_window_votes(
        &self,
        since: DateTime<Utc>,
        rank_cutoff: i32,
    ) -> Result<Vec<WindowVote>> {
        let rows: Vec<WindowVote> = sqlx::query_as(
            "SELECT cw.trader_wallet, cw.name, cw.rank, cw.pnl, cw.quality, cw.condition_id, \
                    cw.outcome_index, cw.outcome, cw.title, cw.slug, cw.event_slug, \
                    cw.is_sports, cw.price, cw.size_usd, cw.ts \
             FROM consensus_vote_window cw \
             JOIN followed_traders ft ON LOWER(ft.proxy_wallet) = cw.trader_wallet \
             WHERE cw.ts >= $1 \
               AND cw.event_slug ~ '^(lol|cs2|csgo|dota|dota2|val|valorant)' \
               AND (ft.rank <= $2 OR ft.consensus_eligible OR ft.earned_eligible)",
        )
        .bind(since)
        .bind(rank_cutoff)
        .fetch_all(&self.pool)
        .await
        .context("load_soft_window_votes")?;
        Ok(rows)
    }

    /// Record an EARNED promotion: flip `earned_eligible` on for the given tracked
    /// wallets (exact `proxy_wallet` match). Idempotent — already-earned rows are
    /// untouched; returns how many rows newly flipped. Called only by the
    /// flag-gated (EARN_DEEP_SHARPS) promotion pass for gate-Trusted deep traders;
    /// never from the leaderboard refresh. There is deliberately NO automatic
    /// un-earn — revocation is a manual act.
    pub async fn set_earned_eligible(&self, wallets: &[String]) -> Result<u64> {
        if wallets.is_empty() {
            return Ok(0);
        }
        let res = sqlx::query(
            "UPDATE followed_traders SET earned_eligible = TRUE \
             WHERE proxy_wallet = ANY($1) AND NOT earned_eligible",
        )
        .bind(wallets)
        .execute(&self.pool)
        .await
        .context("set_earned_eligible")?;
        Ok(res.rows_affected())
    }

    /// Drop window atoms older than `cutoff`. Returns the number pruned.
    pub async fn prune_window_votes(&self, cutoff: DateTime<Utc>) -> Result<u64> {
        let res = sqlx::query("DELETE FROM consensus_vote_window WHERE ts < $1")
            .bind(cutoff)
            .execute(&self.pool)
            .await
            .context("prune_window_votes")?;
        Ok(res.rows_affected())
    }

    // --- Durable trader-fill archive (migration 026) ---

    /// Append a batch of trader fills (both sides) to the durable archive. ONE
    /// UNNEST insert with a **bare `ON CONFLICT DO NOTHING`** (no conflict
    /// target): Postgres arbitrates each row against whichever partial unique
    /// index applies (`trader_fills_tx_uniq` when `tx_hash` is present,
    /// `trader_fills_content_uniq` when it's null) AND dedups intra-batch — so a
    /// re-seen tx and a content-duplicate null-tx row are both dropped. Returns
    /// the number of rows actually inserted.
    pub async fn insert_trader_fills(&self, fills: &[NewTraderFill]) -> Result<u64> {
        if fills.is_empty() {
            return Ok(0);
        }
        let wallet: Vec<&str> = fills.iter().map(|f| f.wallet.as_str()).collect();
        let tx_hash: Vec<Option<&str>> = fills.iter().map(|f| f.tx_hash.as_deref()).collect();
        let condition_id: Vec<&str> = fills.iter().map(|f| f.condition_id.as_str()).collect();
        let outcome_index: Vec<i32> = fills.iter().map(|f| f.outcome_index).collect();
        let outcome: Vec<&str> = fills.iter().map(|f| f.outcome.as_str()).collect();
        let side: Vec<&str> = fills.iter().map(|f| f.side.as_str()).collect();
        let price: Vec<f64> = fills.iter().map(|f| f.price).collect();
        let size_usd: Vec<f64> = fills.iter().map(|f| f.size_usd).collect();
        let title: Vec<&str> = fills.iter().map(|f| f.title.as_str()).collect();
        let slug: Vec<&str> = fills.iter().map(|f| f.slug.as_str()).collect();
        let event_slug: Vec<Option<&str>> = fills.iter().map(|f| f.event_slug.as_deref()).collect();
        let is_sports: Vec<bool> = fills.iter().map(|f| f.is_sports).collect();
        let sport: Vec<Option<&str>> = fills.iter().map(|f| f.sport.as_deref()).collect();
        let bet_type: Vec<Option<&str>> = fills.iter().map(|f| f.bet_type.as_deref()).collect();
        let ts: Vec<DateTime<Utc>> = fills.iter().map(|f| f.ts).collect();
        // Provenance (migration 040), appended. Poller passes None → NULL, so the
        // conflict arbitration (partial unique indexes, none of which reference
        // `source`) and the inserted values are byte-identical to pre-040.
        let source: Vec<Option<&str>> = fills.iter().map(|f| f.source.as_deref()).collect();
        let live_seen_at: Vec<Option<DateTime<Utc>>> =
            fills.iter().map(|f| f.live_seen_at).collect();

        let res = sqlx::query(
            "INSERT INTO trader_fills \
               (wallet, tx_hash, condition_id, outcome_index, outcome, side, price, \
                size_usd, title, slug, event_slug, is_sports, sport, bet_type, ts, \
                source, live_seen_at) \
             SELECT * FROM UNNEST( \
               $1::text[], $2::text[], $3::text[], $4::int4[], $5::text[], $6::text[], \
               $7::float8[], $8::float8[], $9::text[], $10::text[], $11::text[], \
               $12::bool[], $13::text[], $14::text[], $15::timestamptz[], \
               $16::text[], $17::timestamptz[]) \
             ON CONFLICT DO NOTHING",
        )
        .bind(&wallet)
        .bind(&tx_hash)
        .bind(&condition_id)
        .bind(&outcome_index)
        .bind(&outcome)
        .bind(&side)
        .bind(&price)
        .bind(&size_usd)
        .bind(&title)
        .bind(&slug)
        .bind(&event_slug)
        .bind(&is_sports)
        .bind(&sport)
        .bind(&bet_type)
        .bind(&ts)
        .bind(&source)
        .bind(&live_seen_at)
        .execute(&self.pool)
        .await
        .context("insert_trader_fills")?;
        Ok(res.rows_affected())
    }

    /// Append a batch of raw CLOB price-tape ticks (migration 040). ONE UNNEST
    /// insert into the append-only `clob_price_tape`; no `ON CONFLICT` (an
    /// append-only log — offline dedup is by `id`). Written ONLY by the
    /// flag-gated `live_tape` task. Returns rows inserted.
    pub async fn insert_tape_ticks(&self, ticks: &[NewTapeTick]) -> Result<u64> {
        if ticks.is_empty() {
            return Ok(0);
        }
        let asset_id: Vec<&str> = ticks.iter().map(|t| t.asset_id.as_str()).collect();
        let condition_id: Vec<Option<&str>> =
            ticks.iter().map(|t| t.condition_id.as_deref()).collect();
        let outcome_index: Vec<Option<i16>> = ticks.iter().map(|t| t.outcome_index).collect();
        let event_type: Vec<&str> = ticks.iter().map(|t| t.event_type.as_str()).collect();
        let best_bid: Vec<Option<f64>> = ticks.iter().map(|t| t.best_bid).collect();
        let best_ask: Vec<Option<f64>> = ticks.iter().map(|t| t.best_ask).collect();
        let last_price: Vec<Option<f64>> = ticks.iter().map(|t| t.last_price).collect();
        let last_size: Vec<Option<f64>> = ticks.iter().map(|t| t.last_size).collect();
        let side: Vec<Option<&str>> = ticks.iter().map(|t| t.side.as_deref()).collect();
        let exch_ts: Vec<Option<DateTime<Utc>>> = ticks.iter().map(|t| t.exch_ts).collect();
        let recv_at: Vec<DateTime<Utc>> = ticks.iter().map(|t| t.recv_at).collect();

        let res = sqlx::query(
            "INSERT INTO clob_price_tape \
               (asset_id, condition_id, outcome_index, event_type, best_bid, best_ask, \
                last_price, last_size, side, exch_ts, recv_at) \
             SELECT * FROM UNNEST( \
               $1::text[], $2::text[], $3::int2[], $4::text[], $5::float8[], $6::float8[], \
               $7::float8[], $8::float8[], $9::text[], $10::timestamptz[], $11::timestamptz[])",
        )
        .bind(&asset_id)
        .bind(&condition_id)
        .bind(&outcome_index)
        .bind(&event_type)
        .bind(&best_bid)
        .bind(&best_ask)
        .bind(&last_price)
        .bind(&last_size)
        .bind(&side)
        .bind(&exch_ts)
        .bind(&recv_at)
        .execute(&self.pool)
        .await
        .context("insert_tape_ticks")?;
        Ok(res.rows_affected())
    }

    /// Prune tape rows older than `retention_hours` (migration 040). Bounds the
    /// append-only `clob_price_tape` — called periodically by the `live_tape` task.
    /// Returns rows deleted.
    pub async fn prune_tape(&self, retention_hours: i64) -> Result<u64> {
        let res = sqlx::query(
            "DELETE FROM clob_price_tape \
             WHERE recv_at < now() - ($1::text || ' hours')::interval",
        )
        .bind(retention_hours.to_string())
        .execute(&self.pool)
        .await
        .context("prune_tape")?;
        Ok(res.rows_affected())
    }

    /// Compact the tape (migration 040): drop rows whose top-of-book
    /// (best_bid, best_ask) is IDENTICAL to the immediately-preceding row for the
    /// same asset — pure redundancy the step-function curve already implies. The
    /// on-change ingest filter already skips these in-stream; this sweep cleans the
    /// residual left at reconnect/reshard boundaries (a fresh stream re-sends a
    /// `book` snapshot of the unchanged top-of-book). LOSSLESS for the curve: every
    /// inflection (a real (bid,ask) change) is kept; only implied repeats are removed.
    /// Only touches rows older than `keep_recent_secs` so it never races the live
    /// writer's just-inserted tail. Returns rows removed.
    pub async fn compact_tape(&self, keep_recent_secs: i64) -> Result<u64> {
        // Order by (recv_at, id) — the local WRITE order, which is always present
        // (recv_at NOT NULL) and monotonic within a connection. NOT exch_ts: it is
        // NULL on `book` snapshots and can be stale, which would mis-sort a real
        // inflection to the partition tail and delete it as a false duplicate
        // (adversarial review D1). recv_at is the order rows actually arrived, so a
        // reconnect snapshot re-sending an unchanged top-of-book correctly compares
        // against the last-arrived row and collapses.
        let res = sqlx::query(
            "WITH ranked AS ( \
               SELECT id, \
                 (best_bid IS NOT DISTINCT FROM \
                    lag(best_bid) OVER w \
                  AND best_ask IS NOT DISTINCT FROM \
                    lag(best_ask) OVER w) AS redundant \
               FROM clob_price_tape \
               WHERE recv_at < now() - ($1::text || ' seconds')::interval \
               WINDOW w AS (PARTITION BY asset_id ORDER BY recv_at, id) \
             ) \
             DELETE FROM clob_price_tape t USING ranked r \
             WHERE t.id = r.id AND r.redundant",
        )
        .bind(keep_recent_secs.to_string())
        .execute(&self.pool)
        .await
        .context("compact_tape")?;
        Ok(res.rows_affected())
    }

    /// The tracked-only subscription universe: DISTINCT (condition_id, outcome_index)
    /// that a *followed* trader has filled a sports pick on within `lookback_hours`.
    /// The `live_tape` refresh loop resolves each to a CLOB token_id and subscribes.
    /// Sized for the full follow-set (1000+ wallets → ~1.6k tokens at 6h).
    pub async fn tracked_tape_assets(
        &self,
        lookback_hours: i64,
    ) -> Result<Vec<(String, i32)>> {
        let rows: Vec<(String, i32)> = sqlx::query_as(
            "SELECT DISTINCT condition_id, outcome_index \
               FROM trader_fills \
              WHERE ts > now() - ($1::text || ' hours')::interval \
                AND is_sports AND condition_id IS NOT NULL \
                AND wallet IN (SELECT lower(proxy_wallet) FROM followed_traders)",
        )
        .bind(lookback_hours.to_string())
        .fetch_all(&self.pool)
        .await
        .context("tracked_tape_assets")?;
        Ok(rows)
    }

    /// F2 live-fills dedup (migration 040). The lowercased proxy wallets of all
    /// followed traders — the in-process filter for OrderFilled maker/taker.
    pub async fn tracked_wallets_for_live(&self) -> Result<Vec<String>> {
        let rows: Vec<(String,)> =
            sqlx::query_as("SELECT DISTINCT lower(proxy_wallet) FROM followed_traders")
                .fetch_all(&self.pool)
                .await
                .context("tracked_wallets_for_live")?;
        Ok(rows.into_iter().map(|(w,)| w).collect())
    }

    /// F2 dedup LAYER 2 (live-vs-poll pre-check). Given candidate live fills'
    /// `(tx_hash, condition_id, outcome_index, side)` keys, return the subset the
    /// poller ALREADY holds (source IS NULL). The caller skips those live rows so a
    /// full-precision-VWAP poll row is never shadowed by a reconstructed live twin.
    /// `keys`: parallel arrays. Returns the set of keys (as "tx|cond|oidx|side") present.
    pub async fn filter_existing_txkey(
        &self,
        tx: &[String],
        cond: &[String],
        oidx: &[i32],
        side: &[String],
    ) -> Result<std::collections::HashSet<String>> {
        if tx.is_empty() {
            return Ok(std::collections::HashSet::new());
        }
        let rows: Vec<(String, String, i32, String)> = sqlx::query_as(
            "SELECT tx_hash, condition_id, outcome_index, side FROM trader_fills \
             WHERE source IS NULL AND tx_hash = ANY($1) \
               AND (tx_hash, condition_id, outcome_index, side) IN ( \
                   SELECT * FROM UNNEST($1::text[], $2::text[], $3::int4[], $4::text[]))",
        )
        .bind(tx)
        .bind(cond)
        .bind(oidx)
        .bind(side)
        .fetch_all(&self.pool)
        .await
        .context("filter_existing_txkey")?;
        Ok(rows
            .into_iter()
            .map(|(t, c, o, s)| format!("{t}|{c}|{o}|{s}"))
            .collect())
    }

    /// F2 dedup LAYER 3 (poll-over-live collapse, migration 040). Idempotent sweep:
    /// drop any `live_onchain` row whose canonical poll twin (source NULL, same
    /// tx/cond/outcome/side) has since arrived. Run periodically inside the
    /// reconciliation window. Returns rows collapsed.
    pub async fn collapse_live_over_poll(&self) -> Result<u64> {
        let res = sqlx::query(
            "DELETE FROM trader_fills live USING trader_fills poll \
             WHERE live.source='live_onchain' AND poll.source IS NULL \
               AND live.tx_hash=poll.tx_hash AND live.condition_id=poll.condition_id \
               AND live.outcome_index=poll.outcome_index AND live.side=poll.side",
        )
        .execute(&self.pool)
        .await
        .context("collapse_live_over_poll")?;
        Ok(res.rows_affected())
    }

    /// Classify each tracked wallet as `bot` | `human` in
    /// `followed_traders.trader_type`, from its captured fills. A market-maker bot
    /// fires hundreds of fills per active day; a human placing picks does not. Flag
    /// `bot` iff `fills / distinct_active_days >= 400`. Returns rows updated.
    /// Advisory — nothing in the live alert path reads `trader_type`; the selection
    /// layer filters on it. Idempotent (a plain UPDATE from a fresh aggregate).
    pub async fn classify_trader_types(&self) -> Result<u64> {
        let res = sqlx::query(
            "WITH s AS ( \
                SELECT wallet, \
                       count(*)::float8 \
                         / GREATEST(count(DISTINCT (ts AT TIME ZONE 'UTC')::date), 1) AS fpd \
                FROM trader_fills GROUP BY wallet \
             ) \
             UPDATE followed_traders ft \
                SET trader_type = CASE WHEN s.fpd >= 400 THEN 'bot' ELSE 'human' END \
             FROM s \
             WHERE lower(ft.proxy_wallet) = s.wallet",
        )
        .execute(&self.pool)
        .await
        .context("classify_trader_types")?;
        Ok(res.rows_affected())
    }

    /// Stamp capture bookkeeping for one wallet after a poll. `min_ts`/`max_ts`
    /// are the oldest/newest fill timestamps in this poll; `raw_count` is the
    /// raw page length. A **gap** is counted iff the page was full (`raw_count
    /// >= 100`) AND its oldest row is newer than everything we'd seen before
    /// (`min_ts > last_capture_newest_ts`) — i.e. the trader traded faster than
    /// our cadence and the in-between trades fell off the newest 100-row page.
    /// The first poll (`last_capture_newest_ts IS NULL`) never counts a gap.
    pub async fn record_capture(
        &self,
        wallet: &str,
        min_ts: DateTime<Utc>,
        max_ts: DateTime<Utc>,
        raw_count: usize,
    ) -> Result<()> {
        sqlx::query(
            "UPDATE followed_traders SET \
               capture_gap_count = capture_gap_count \
                   + CASE WHEN $4 >= 100 AND last_capture_newest_ts IS NOT NULL \
                               AND $2 > last_capture_newest_ts \
                          THEN 1 ELSE 0 END, \
               last_capture_newest_ts = GREATEST(COALESCE(last_capture_newest_ts, $3), $3), \
               capture_started_at     = COALESCE(capture_started_at, NOW()) \
             WHERE proxy_wallet = $1",
        )
        .bind(wallet)
        .bind(min_ts)
        .bind(max_ts)
        .bind(raw_count as i32)
        .execute(&self.pool)
        .await
        .context("record_capture")?;
        Ok(())
    }

    /// Build consensus window votes from the durable `trader_fills` archive
    /// (the `CONSENSUS_BOOKS_FROM_FILLS=true` source) instead of
    /// `consensus_vote_window`. Selects BUY fills in-window and re-derives the
    /// `quality` weight from the trader's CURRENT leaderboard rank at load time
    /// (vs the window path which freezes `quality` at capture). Returns the same
    /// [`WindowVote`] shape so `books_from_window_votes` is reused unchanged.
    ///
    /// The `quality` SQL mirrors `scanner::consensus::quality_weight` exactly —
    /// rank 1 ≈ 2.0, rank ≥ 50 / unranked / unknown ≈ 1.0. Kept in sync with
    /// that function (it is a bounded display/ranking weight, not a statistic).
    pub async fn load_buy_fills_since(&self, since: DateTime<Utc>) -> Result<Vec<WindowVote>> {
        let rows: Vec<WindowVote> = sqlx::query_as(
            "SELECT tf.wallet AS trader_wallet, \
                    COALESCE(ft.username, LEFT(tf.wallet, 8)) AS name, \
                    ft.rank AS rank, ft.pnl AS pnl, \
                    CASE WHEN ft.rank >= 1 \
                         THEN 1.0 + GREATEST(0, 50 - LEAST(ft.rank, 50))::float8 / 50.0 \
                         ELSE 1.0 END AS quality, \
                    tf.condition_id, tf.outcome_index, tf.outcome, tf.title, tf.slug, \
                    tf.event_slug, tf.is_sports, tf.price, tf.size_usd, tf.ts \
             FROM trader_fills tf \
             LEFT JOIN followed_traders ft ON LOWER(ft.proxy_wallet) = tf.wallet \
             WHERE tf.side = 'BUY' AND tf.ts >= $1 \
               AND COALESCE(ft.consensus_eligible OR ft.earned_eligible, TRUE) = TRUE",
        )
        .bind(since)
        .fetch_all(&self.pool)
        .await
        .context("load_buy_fills_since")?;
        Ok(rows)
    }

    // --- Resolution ledger (Phase 1) ---

    /// Distinct `condition_id`s with unresolved BUY fills older than `min_age`,
    /// oldest-first, capped at `cap`. This is the INDEPENDENT unresolved source:
    /// it surfaces markets a trader bet that may never have triggered a consensus
    /// signal, so resolving only consensus conditions would never settle them and
    /// profiles would be biased toward markets that happened to fire consensus
    /// (survivorship). Housekeeping UNIONs this into its resolution set.
    pub async fn trader_fill_unresolved_conditions(
        &self,
        min_age: chrono::Duration,
        cap: i64,
    ) -> Result<Vec<String>> {
        let rows: Vec<(String,)> = sqlx::query_as(
            "SELECT condition_id FROM trader_fills \
             WHERE resolved = FALSE AND side = 'BUY' \
               AND ts < NOW() - make_interval(secs => $1) \
             GROUP BY condition_id ORDER BY MIN(ts) LIMIT $2",
        )
        .bind(min_age.num_seconds() as f64)
        .bind(cap)
        .fetch_all(&self.pool)
        .await
        .context("trader_fill_unresolved_conditions")?;
        Ok(rows.into_iter().map(|(c,)| c).collect())
    }

    /// Resolve every unresolved fill on `condition_id` against the winning token
    /// index. Multi-outcome correct: `outcome_won = (outcome_index = winner)`.
    /// `advantage = won::int − price` for BUY (mirrors the consensus gate's
    /// `edge = won − entry_price`); NULL for SELL (round-trip PnL is a v2
    /// enhancement). Both sides are marked resolved so they stop reappearing in
    /// the unresolved source. Returns the number of rows resolved.
    pub async fn resolve_trader_fills(&self, condition_id: &str, winner_index: i32) -> Result<u64> {
        let res = sqlx::query(
            "UPDATE trader_fills SET \
               resolved    = TRUE, \
               outcome_won = (outcome_index = $2), \
               advantage   = CASE WHEN side = 'BUY' \
                                  THEN ((outcome_index = $2)::int)::double precision - price \
                                  ELSE NULL END, \
               resolved_at = NOW() \
             WHERE condition_id = $1 AND resolved = FALSE",
        )
        .bind(condition_id)
        .bind(winner_index)
        .execute(&self.pool)
        .await
        .context("resolve_trader_fills")?;
        Ok(res.rows_affected())
    }

    // --- Earned-trust slice scores (Phase 2) ---

    /// Per-(wallet × slice) earned-trust statistics over resolved BUY fills —
    /// numbers only; the verdict (gate reuse) lives in the binary
    /// (`scanner::trader_trust`). This mirrors `consensus_scoreboard_by_strategy`
    /// exactly but keyed by wallet/slice with a **trader_fills-native band-blind
    /// baseline**: the *tracked fleet's* per-band average advantage neutralizes
    /// favorite-longshot loading natively, so `surplus = AVG_event(a − blind[band])`
    /// is the only edge that isn't gamed by loading favorites.
    ///
    /// HONEST NOTE on the baseline (audited 2026-06-29): the blind is the average
    /// over EVERY tracked wallet's fills in that band, INCLUDING the scored
    /// wallet's own. So `surplus` measures "beats the average tracked sharp in
    /// that band," not "beats the open market," and a wallet that dominates a
    /// thinly-populated band partly cancels its own surplus. Both effects are
    /// CONSERVATIVE (they pull toward INDETERMINATE — never manufacture a false
    /// `Trusted`) and the self-share of the fleet-wide `overall` blind is tiny, so
    /// the headline verdict is unaffected in practice. A leave-one-out baseline is
    /// a candidate refinement if a single wallet ever dominates the fleet.
    ///
    /// Everything is **event-clustered**: per-fill advantage is averaged to the
    /// `COALESCE(event_slug, condition_id)` level first, then across events — so
    /// correlated outcomes of one event count once (the within-match leak fix).
    /// `n_events` is the gate's N; `surplus_sd` is the std-dev over events.
    /// Slices: `overall`, `sport`, `band` (b1..b5), `bettype`
    /// (`moneyline|spread|totals|prop|other`), `recency7d`, `recency30d`.
    ///
    /// The blind baseline is a **favorite-residual cell-blind** (FORGE_PLAN Item 2):
    /// surplus = advantage − `AVG(advantage)` over the fleet in the SAME `(sport,
    /// band)` cell, cascading to the incumbent per-`band` blind then 0 when a
    /// `(sport,band)` cell is thin/absent. Because `favorite` IS the band region
    /// 0.65–0.98, blinding within `(sport,band)` subtracts favorite-loading AT the
    /// verdict — a wallet that merely rides a sport's favorites reads ≈0 surplus.
    pub async fn trader_slice_scores(&self) -> Result<Vec<TraderSliceStat>> {
        let rows: Vec<TraderSliceStat> = sqlx::query_as(
            "WITH adv AS ( \
                 SELECT wallet, COALESCE(event_slug, condition_id) AS ev, \
                        width_bucket(price, 0.0, 1.0, 5) AS band, \
                        (outcome_won::int)::double precision - price AS a, \
                        (outcome_won::int)::double precision AS won, \
                        COALESCE(sport, 'other') AS sport, \
                        COALESCE(bet_type, 'other') AS bettype, ts \
                 FROM trader_fills \
                 WHERE resolved AND side = 'BUY' AND outcome_won IS NOT NULL \
             ), \
             blind_cell AS ( SELECT sport, band, AVG(a) AS blind_edge FROM adv GROUP BY sport, band ), \
             blind_band AS ( SELECT band, AVG(a) AS blind_edge FROM adv GROUP BY band ), \
             surp AS ( SELECT v.wallet, v.ev, v.band, v.a, v.won, v.sport, v.bettype, v.ts, \
                              v.a - COALESCE(bc.blind_edge, bb.blind_edge, 0) AS s \
                       FROM adv v \
                       LEFT JOIN blind_cell bc USING (sport, band) \
                       LEFT JOIN blind_band bb USING (band) ), \
             tagged AS ( \
                 SELECT wallet, 'overall'::text AS slice_kind, ''::text AS slice_key, ev, a, s, won, ts FROM surp \
                 UNION ALL \
                 SELECT wallet, 'sport', sport, ev, a, s, won, ts FROM surp \
                 UNION ALL \
                 SELECT wallet, 'band', 'b' || band::text, ev, a, s, won, ts FROM surp \
                 UNION ALL \
                 SELECT wallet, 'bettype', bettype, ev, a, s, won, ts FROM surp \
                 UNION ALL \
                 SELECT wallet, 'recency7d', '7d', ev, a, s, won, ts FROM surp \
                   WHERE ts >= NOW() - INTERVAL '7 days' \
                 UNION ALL \
                 SELECT wallet, 'recency30d', '30d', ev, a, s, won, ts FROM surp \
                   WHERE ts >= NOW() - INTERVAL '30 days' \
             ), \
             evl AS ( \
                 SELECT wallet, slice_kind, slice_key, ev, \
                        AVG(s) AS ev_surplus, AVG(a) AS ev_adv, AVG(won) AS ev_hit, \
                        COUNT(*) AS ev_rows, MIN((ts AT TIME ZONE 'UTC')::date) AS ev_day \
                 FROM tagged GROUP BY wallet, slice_kind, slice_key, ev \
             ) \
             SELECT wallet, slice_kind, slice_key, \
                    COUNT(DISTINCT ev)        AS n_events, \
                    COUNT(DISTINCT ev_day)    AS n_days, \
                    SUM(ev_rows)::bigint      AS n_resolved, \
                    AVG(ev_surplus)           AS surplus, \
                    STDDEV_SAMP(ev_surplus)   AS surplus_sd, \
                    AVG(ev_adv)               AS mean_adv, \
                    AVG(ev_hit)               AS hit_rate \
             FROM evl GROUP BY wallet, slice_kind, slice_key",
        )
        .fetch_all(&self.pool)
        .await
        .context("trader_slice_scores")?;
        Ok(rows)
    }

    /// Re-score the proven-trader router follow-set and append the new batch to
    /// `router_followset` (migration 039). Returns the qualifying wallets — the
    /// caller publishes EXACTLY this set to the live `proven_router` arm, so an
    /// honest empty re-score empties the live set even though an empty batch
    /// writes no rows (a `scored_at` gap in the table ⇒ empty-or-down; either
    /// way the arm wasn't firing, so as-of reconstruction treating a gap as ∅
    /// is conservative and correct).
    ///
    /// Every constant is FROZEN by `reports/PREREG_2026-07-04T094304Z_proven_router.md`:
    /// - universe: trailing-365d resolved BUY fills, entry band 0.45 ≤ price < 0.90;
    /// - reprice at OUR entry: `price + 0.013 (follower tax) + band_spread` where
    ///   band_spread = pooled decision-time (≤900s) `entry_ask − entry_ask_mid`
    ///   clamped ≥0 per row (copyability.py conventions, width_bucket bands);
    /// - `copy_return = (won − our_entry)/our_entry − 0.02 (fee)`, event-clustered
    ///   at `COALESCE(event_slug, condition_id)`;
    /// - membership: ≥100 fills, ≥15 distinct UTC days, copy_return ≥ +0.10, and
    ///   NOT market-maker-shaped — the UNION of two detectors (router_verify A4
    ///   found they disagree on 51/161 wallets, so both are enforced):
    ///   position-grain microstructure screens (round_trip_rate < 0.30 AND
    ///   two_sided_rate < 0.25 AND sell_buy_ratio < 0.50) AND NOT flagged
    ///   `followed_traders.trader_type = 'bot'` (classify_trader_types, fpd ≥ 400);
    ///   interim pending FORGE_PLAN_MM_FILTER's calibrated verdict;
    /// - `lower_bound` is a one-sided-95% day-deflated DIAGNOSTIC, never the gate.
    pub async fn refresh_router_followset(&self) -> Result<Vec<String>> {
        let rows: Vec<(String,)> = sqlx::query_as(
            "WITH spreads AS ( \
                 SELECT width_bucket(initial_mean_price, 0.0, 1.0, 5) AS band, \
                        AVG(GREATEST(entry_ask - entry_ask_mid, 0)) AS spread \
                 FROM consensus_signals \
                 WHERE entry_ask IS NOT NULL AND entry_ask_mid IS NOT NULL \
                   AND entry_ask_at IS NOT NULL \
                   AND EXTRACT(EPOCH FROM (entry_ask_at - first_detected_at)) <= 900 \
                 GROUP BY 1 \
             ), \
             pos AS ( \
                 SELECT wallet, condition_id, outcome_index, \
                        COALESCE(SUM(size_usd) FILTER (WHERE side = 'BUY'), 0)  AS buy_usd, \
                        COALESCE(SUM(size_usd) FILTER (WHERE side = 'SELL'), 0) AS sell_usd, \
                        COUNT(*) FILTER (WHERE side = 'BUY')  AS n_buy, \
                        COUNT(*) FILTER (WHERE side = 'SELL') AS n_sell \
                 FROM trader_fills GROUP BY 1, 2, 3 \
             ), \
             sided AS ( \
                 SELECT wallet, condition_id, COUNT(*) FILTER (WHERE n_buy > 0) AS n_out_held \
                 FROM pos GROUP BY 1, 2 \
             ), \
             two AS ( \
                 SELECT wallet, AVG((n_out_held >= 2)::int)::float8 AS two_sided_rate \
                 FROM sided GROUP BY 1 \
             ), \
             micro AS ( \
                 SELECT p.wallet, \
                        AVG((p.n_sell > 0 AND p.n_buy > 0)::int)::float8 AS round_trip_rate, \
                        (SUM(LEAST(p.sell_usd, p.buy_usd)) / NULLIF(SUM(p.buy_usd), 0))::float8 AS sell_buy_ratio, \
                        t.two_sided_rate \
                 FROM pos p JOIN two t USING (wallet) \
                 GROUP BY p.wallet, t.two_sided_rate \
             ), \
             fills AS ( \
                 SELECT f.wallet, \
                        COALESCE(f.event_slug, f.condition_id) AS ev, \
                        (f.ts AT TIME ZONE 'UTC')::date AS day, \
                        ((f.outcome_won::int)::float8 - (f.price + 0.013 + COALESCE(s.spread, 0))) \
                          / (f.price + 0.013 + COALESCE(s.spread, 0)) - 0.02 AS ret \
                 FROM trader_fills f \
                 LEFT JOIN spreads s ON s.band = width_bucket(f.price, 0.0, 1.0, 5) \
                 WHERE f.side = 'BUY' AND f.resolved AND f.outcome_won IS NOT NULL \
                   AND f.price >= 0.45 AND f.price < 0.90 \
                   AND f.ts >= NOW() - INTERVAL '365 days' \
             ), \
             evl AS ( \
                 SELECT wallet, ev, AVG(ret) AS ev_ret, COUNT(*) AS n_fills \
                 FROM fills GROUP BY 1, 2 \
             ), \
             days AS ( SELECT wallet, COUNT(DISTINCT day) AS n_days FROM fills GROUP BY 1 ), \
             scored AS ( \
                 SELECT e.wallet, \
                        AVG(e.ev_ret)          AS copy_return, \
                        STDDEV_SAMP(e.ev_ret)  AS sd, \
                        COUNT(*)               AS n_events, \
                        SUM(e.n_fills)::bigint AS n_fills, \
                        d.n_days \
                 FROM evl e JOIN days d USING (wallet) \
                 GROUP BY e.wallet, d.n_days \
             ) \
             INSERT INTO router_followset \
                 (scored_at, wallet, copy_return, n_fills, n_events, n_days, lower_bound, \
                  round_trip_rate, two_sided_rate, sell_buy_ratio) \
             SELECT NOW(), lower(s.wallet), s.copy_return, s.n_fills, s.n_events, s.n_days, \
                    s.copy_return - 1.6449 * s.sd / sqrt(LEAST(s.n_days, s.n_events)::float8), \
                    m.round_trip_rate, m.two_sided_rate, m.sell_buy_ratio \
             FROM scored s \
             LEFT JOIN micro m USING (wallet) \
             WHERE s.n_fills >= 100 \
               AND s.n_days >= 15 \
               AND s.copy_return >= 0.10 \
               AND COALESCE(m.round_trip_rate, 0) < 0.30 \
               AND COALESCE(m.two_sided_rate, 0) < 0.25 \
               AND COALESCE(m.sell_buy_ratio, 0) < 0.50 \
               AND NOT EXISTS ( \
                   SELECT 1 FROM followed_traders ft \
                   WHERE lower(ft.proxy_wallet) = lower(s.wallet) \
                     AND ft.trader_type = 'bot') \
             RETURNING wallet",
        )
        .fetch_all(&self.pool)
        .await
        .context("refresh_router_followset")?;
        Ok(rows.into_iter().map(|r| r.0).collect())
    }

    /// Survivorship capture fix (2026-07-04 capture-hardening): the DEACTIVATED
    /// wallets the scorecard still cares about, so the hardened loop can keep
    /// polling their fills after they drop off the leaderboard. Without this the
    /// forward scorecard/benchmark is conditioned on staying tracked (upward bias;
    /// router_verify A4 measured 245 inactive wallets with 0 fills after
    /// `last_seen_on_lb`).
    ///
    /// A wallet qualifies when it is `active = FALSE` AND scorecard-eligible — the
    /// pool the scorecard reads: it has EVER appeared in `router_followset`, OR it
    /// holds ≥100 BUY fills in the entry band 0.45 ≤ price < 0.90 over the trailing
    /// 365 days (the `n_fills ≥ 100` floor the scorecard applies). Returns
    /// `(proxy_wallet, since)` where `since` is the last point we captured
    /// (`consensus_polled_at`, else `last_seen_on_lb`, else 2 days back) — used only
    /// to advance the poll cursor and for logging (the data-api returns the newest
    /// page regardless of `startTs`; dedup is the DB's job).
    pub async fn scorecard_eligible_dropped_wallets(
        &self,
    ) -> Result<Vec<(String, DateTime<Utc>)>> {
        let rows: Vec<(String, DateTime<Utc>)> = sqlx::query_as(
            "WITH band_fills AS ( \
                 SELECT wallet FROM trader_fills \
                 WHERE side = 'BUY' AND price >= 0.45 AND price < 0.90 \
                   AND ts >= NOW() - INTERVAL '365 days' \
                 GROUP BY wallet HAVING COUNT(*) >= 100 \
             ), \
             eligible AS ( \
                 SELECT wallet FROM router_followset \
                 UNION SELECT wallet FROM band_fills \
             ) \
             SELECT ft.proxy_wallet, \
                    COALESCE(ft.consensus_polled_at, ft.last_seen_on_lb, \
                             NOW() - INTERVAL '2 days') AS since \
             FROM followed_traders ft \
             JOIN eligible e ON e.wallet = lower(ft.proxy_wallet) \
             WHERE ft.active = FALSE",
        )
        .fetch_all(&self.pool)
        .await
        .context("scorecard_eligible_dropped_wallets")?;
        Ok(rows)
    }

    /// Leak-free **as-of** clone of `trader_slice_scores`: every wallet's per-slice
    /// event-clustered surplus computed using ONLY fills resolved strictly before
    /// `cut`. The `resolved_at < $1` predicate lives in the `adv` CTE, so BOTH the
    /// per-slice surplus AND the fleet band-blind are bounded by the cut — a signal
    /// timestamped ≥ `cut` cannot be weighted with its own (future) resolved outcome
    /// (charter H2 / blueprint Item 6). This is the hard prerequisite for any arm that
    /// FITS or MINES on history (edge-pool temperature, coalition mining).
    ///
    /// The `recency7d`/`recency30d` slices are intentionally dropped — "7d before the
    /// cut" is ambiguous under a walk-forward split; only `overall`/`sport`/`band`/
    /// `bettype` (the slices arms consume) are emitted. The favorite-residual
    /// cell-blind cascade (`(sport,band)` → `band` → 0) is applied here too, bounded
    /// by the `resolved_at < cut` predicate so the blind itself is leak-free.
    ///
    /// NOTE (DECISIONS.md D1): on the *current backfilled archive*, `resolved_at` is a
    /// bulk-ingest stamp (all in 2026-06/07), so `resolved_at < cut` is degenerate for
    /// retrospective analysis of that archive — use the slug-parsed event-date harness
    /// (`scripts/asof_preflight.py`) there. This query is correct for FORWARD data,
    /// where `resolved_at` is populated in real time as markets close.
    pub async fn trader_slice_scores_asof(
        &self,
        cut: DateTime<Utc>,
    ) -> Result<Vec<TraderSliceStat>> {
        let rows: Vec<TraderSliceStat> = sqlx::query_as(
            "WITH adv AS ( \
                 SELECT wallet, COALESCE(event_slug, condition_id) AS ev, \
                        width_bucket(price, 0.0, 1.0, 5) AS band, \
                        (outcome_won::int)::double precision - price AS a, \
                        (outcome_won::int)::double precision AS won, \
                        COALESCE(sport, 'other') AS sport, \
                        COALESCE(bet_type, 'other') AS bettype, ts \
                 FROM trader_fills \
                 WHERE resolved AND side = 'BUY' AND outcome_won IS NOT NULL \
                   AND resolved_at IS NOT NULL AND resolved_at < $1 \
             ), \
             blind_cell AS ( SELECT sport, band, AVG(a) AS blind_edge FROM adv GROUP BY sport, band ), \
             blind_band AS ( SELECT band, AVG(a) AS blind_edge FROM adv GROUP BY band ), \
             surp AS ( SELECT v.wallet, v.ev, v.band, v.a, v.won, v.sport, v.bettype, v.ts, \
                              v.a - COALESCE(bc.blind_edge, bb.blind_edge, 0) AS s \
                       FROM adv v \
                       LEFT JOIN blind_cell bc USING (sport, band) \
                       LEFT JOIN blind_band bb USING (band) ), \
             tagged AS ( \
                 SELECT wallet, 'overall'::text AS slice_kind, ''::text AS slice_key, ev, a, s, won, ts FROM surp \
                 UNION ALL \
                 SELECT wallet, 'sport', sport, ev, a, s, won, ts FROM surp \
                 UNION ALL \
                 SELECT wallet, 'band', 'b' || band::text, ev, a, s, won, ts FROM surp \
                 UNION ALL \
                 SELECT wallet, 'bettype', bettype, ev, a, s, won, ts FROM surp \
             ), \
             evl AS ( \
                 SELECT wallet, slice_kind, slice_key, ev, \
                        AVG(s) AS ev_surplus, AVG(a) AS ev_adv, AVG(won) AS ev_hit, \
                        COUNT(*) AS ev_rows, MIN((ts AT TIME ZONE 'UTC')::date) AS ev_day \
                 FROM tagged GROUP BY wallet, slice_kind, slice_key, ev \
             ) \
             SELECT wallet, slice_kind, slice_key, \
                    COUNT(DISTINCT ev)        AS n_events, \
                    COUNT(DISTINCT ev_day)    AS n_days, \
                    SUM(ev_rows)::bigint      AS n_resolved, \
                    AVG(ev_surplus)           AS surplus, \
                    STDDEV_SAMP(ev_surplus)   AS surplus_sd, \
                    AVG(ev_adv)               AS mean_adv, \
                    AVG(ev_hit)               AS hit_rate \
             FROM evl GROUP BY wallet, slice_kind, slice_key",
        )
        .bind(cut)
        .fetch_all(&self.pool)
        .await
        .context("trader_slice_scores_asof")?;
        Ok(rows)
    }

    /// One wallet's slice scores (filtered from the fleet query so the band-blind
    /// baseline stays fleet-wide) plus its `capture_gap_count` (so the surface can
    /// flag "⚠ partial capture"). `wallet` is matched case-insensitively against
    /// the lower-cased `trader_fills.wallet`.
    pub async fn trader_profile(&self, wallet: &str) -> Result<(Vec<TraderSliceStat>, i32)> {
        let w = wallet.to_lowercase();
        let slices: Vec<TraderSliceStat> = self
            .trader_slice_scores()
            .await?
            .into_iter()
            .filter(|s| s.wallet == w)
            .collect();
        let gap: Option<(i32,)> = sqlx::query_as(
            "SELECT capture_gap_count FROM followed_traders WHERE LOWER(proxy_wallet) = $1",
        )
        .bind(&w)
        .fetch_optional(&self.pool)
        .await
        .context("trader_profile (gap)")?;
        Ok((slices, gap.map(|(g,)| g).unwrap_or(0)))
    }

    /// Prune resolved-or-not trader fills older than `retention_days`. Default
    /// retention is 0 (keep-all) — the durable archive is the whole point — so
    /// this only deletes when a positive retention is configured. Durability is
    /// the existing daily pg_dump (`scripts/consensus-backup.sh`). Returns rows
    /// pruned.
    pub async fn prune_trader_fills(&self, retention_days: i64) -> Result<u64> {
        if retention_days <= 0 {
            return Ok(0);
        }
        let res =
            sqlx::query("DELETE FROM trader_fills WHERE ts < NOW() - make_interval(days => $1)")
                .bind(retention_days as i32)
                .execute(&self.pool)
                .await
                .context("prune_trader_fills")?;
        Ok(res.rows_affected())
    }

    /// Map of lower-cased wallet → `capture_gap_count` for traders that have
    /// captured at least one poll. Used by the board to flag partial capture.
    pub async fn capture_gaps(&self) -> Result<std::collections::HashMap<String, i32>> {
        let rows: Vec<(String, i32)> = sqlx::query_as(
            "SELECT LOWER(proxy_wallet), capture_gap_count FROM followed_traders \
             WHERE capture_started_at IS NOT NULL",
        )
        .fetch_all(&self.pool)
        .await
        .context("capture_gaps")?;
        Ok(rows.into_iter().collect())
    }
}

/// One point on a signal's trajectory ("stock chart").
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct ConsensusSnapshot {
    pub ts: DateTime<Utc>,
    pub net_count: i32,
    pub n_backers: i32,
    pub mean_entry: f64,
    pub market_price: Option<f64>,
}

/// One strategy's forward-tracking scoreboard row.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct StrategyScore {
    pub strategy: String,
    /// Resolved signals for this strategy.
    pub resolved: i64,
    /// Distinct resolved EVENTS — the honest (de-correlated) sample size.
    pub distinct_events: i64,
    /// Distinct resolved event-DAYS (UTC date of first detection) — the
    /// within-day-correlation deflator for the promotion gate's effective N.
    /// A correlated same-weekend cluster of events collapses to few days, so a
    /// single World-Cup weekend can no longer clear the bar on its own. A NULL
    /// `first_detected_at` counts toward fewer days ⇒ effective N degrades
    /// toward 1 (fail-closed).
    pub distinct_days: i64,
    /// Resolved signals whose consensus outcome won.
    pub won: i64,
    /// Mean realized edge vs the AT-FIRE entry:
    /// `AVG(outcome_won::int - COALESCE(initial_mean_price, mean_price))`.
    /// `None` when nothing has resolved yet.
    pub edge: Option<f64>,
    /// Surplus over the band-matched `_blind` baseline — the favorite-longshot-
    /// neutralized edge. This (not `edge`) is what a promotion gate should judge.
    pub surplus: Option<f64>,
    /// Std-dev of per-EVENT surplus — feeds the promotion gate's confidence bound.
    pub surplus_sd: Option<f64>,
    /// Event-clustered CLV vs the first live mid we captured:
    /// `AVG_event(outcome_won::int − initial_market_price)`. `None` until some
    /// resolved row has a captured `initial_market_price`.
    pub our_clv: Option<f64>,
    /// Event-clustered capture lag `AVG_event(initial_market_price − mean_price)`:
    /// the gap between the mid when we noticed and the sharps' entry price.
    /// Materially negative → faster polling has real value.
    pub capture_lag: Option<f64>,
}

/// One strategy's **honest, realizable** P&L row (CLV-based, execution-haircut,
/// event-clustered). This is the read-only instrument the pilot go/no-go keys off:
/// every float is measured against the price we OBSERVED while the market was open
/// (`initial_market_price`), net of the buy-side haircut — realizable, not flattering.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct HonestPnl {
    pub strategy: String,
    /// Resolved signals (rows) with a captured pre-resolution price.
    pub resolved: i64,
    /// Distinct resolved EVENTS — the de-correlated sample size (the gate's N).
    pub distinct_events: i64,
    /// Event-clustered hit-rate `AVG_event(outcome_won)`.
    pub hit_rate: Option<f64>,
    /// Event-clustered CLV in price units `AVG_event(w − p0)` — realizable edge/$ share.
    pub clv_share: Option<f64>,
    /// Event-clustered CLV ROI `AVG_event((w − p0)/p0)` (gross of haircut/fee).
    pub clv_roi: Option<f64>,
    /// Event-clustered honest edge share `AVG_event(w − entry)` (net of haircut).
    pub honest_edge_share: Option<f64>,
    /// Event-clustered honest ROI per $ staked `AVG_event((w − entry)/entry − fee)`.
    /// This is the headline realizable number; the pilot verdict keys off it.
    pub honest_roi: Option<f64>,
    /// Std-dev of per-EVENT honest ROI — feeds the corrected confidence bound.
    pub honest_roi_sd: Option<f64>,
    /// Median `total_usd` (liquidity proxy) — the capacity + liquidity-floor input.
    pub median_sharp_usd: Option<f64>,
    /// Mean hours from first detection to resolution (working-capital horizon).
    pub avg_hours_to_resolve: Option<f64>,
    /// Distinct events per day over the record's span (throughput for capacity).
    pub bets_per_day: Option<f64>,
    /// The OLD sharp benchmark `AVG_event(w − mean_price)` — shown for reference only.
    pub sharp_edge: Option<f64>,
    /// Fraction of resolved rows with a REAL captured `entry_ask` (Phase 2). The
    /// rest fall back to the mid+haircut heuristic; `None`/0 = all heuristic.
    pub ask_coverage: Option<f64>,
    /// Fraction of resolved rows with a DECISION-TIME real ask (`entry_ask_at −
    /// first_detected_at ≤ decision_lag`). The REALIZED ROI rests on these.
    pub decision_coverage: Option<f64>,
    /// Median REAL execution haircut `entry_ask − entry_ask_mid` over the
    /// DECISION-TIME cohort only (same rows as `realized_roi`) — the measured spread
    /// that replaces the assumed `EXEC_HAIRCUT`, per-strategy. `None` if no
    /// decision-time ask captured yet. (Lagged captures are excluded so the spread
    /// isn't measured against an hours-late mid.)
    pub median_haircut: Option<f64>,
    /// Distinct EVENTS with a decision-time real ask — the realized sample size (the
    /// N the realized corrected bound uses). `None`/0 ⇒ no realized ROI yet.
    pub realized_events: Option<i64>,
    /// Event-clustered honest ROI using ONLY decision-time real asks (`entry =
    /// entry_ask`) — the MEASURED realizable ROI, vs the MODELED `honest_roi`.
    pub realized_roi: Option<f64>,
    /// Std-dev of per-EVENT realized ROI — feeds the realized corrected lower bound.
    pub realized_roi_sd: Option<f64>,
}

/// One (strategy × segment) honest-ROI cell for the regime/band/horizon breakdown.
/// `seg_kind` ∈ {`day`, `band`, `horizon`}; `honest_roi` is event-clustered within
/// the segment. The day-regime cells drive the pilot verdict's persistence check.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct HonestSegment {
    pub strategy: String,
    pub seg_kind: String,
    pub seg_key: String,
    pub n_events: i64,
    pub honest_roi: Option<f64>,
}

/// Paper-ledger track record for one strategy — the ongoing realization of the
/// honest edge (Phase 3). All PAPER; this system never places real money.
#[derive(Debug, Clone, Default)]
pub struct LedgerStats {
    /// Number of paper bets.
    pub bets: i64,
    /// Cumulative paper P&L (= final equity).
    pub total_pnl: f64,
    /// Total staked (turnover).
    pub turnover: f64,
    /// P&L per $ turned over.
    pub roi_on_turnover: f64,
    /// Fraction of paper bets that won.
    pub win_rate: f64,
    /// Highest equity reached.
    pub peak_equity: f64,
    /// Largest peak-to-trough equity drop (absolute $, ≥ 0).
    pub max_drawdown: f64,
    /// Daily-returns Sharpe-like ratio (mean/sd of per-day P&L; 0 if <2 days or sd=0).
    pub sharpe: f64,
    /// Cumulative-equity points for the sparkline (in resolution order).
    pub curve: Vec<f64>,
    /// Cumulative P&L under FLAT-SHARES sizing (stake number read as a share
    /// count): `Σ stake×(won − entry) − fee×stake×entry`. REFINED-STRATEGY
    /// rule 3: flat-$ over-exposes to longshots and can flip a winning
    /// strategy's sign; showing both makes the sizing discipline visible.
    pub total_pnl_shares: f64,
}

impl LedgerStats {
    /// Compute the track record from ledger rows ordered by resolution
    /// `(resolved_at, stake, pnl, outcome_won)`.
    fn from_rows(rows: &[(DateTime<Utc>, f64, f64, bool, f64)], fee_pct: f64) -> Self {
        let bets = rows.len() as i64;
        let turnover: f64 = rows.iter().map(|r| r.1).sum();
        let total_pnl: f64 = rows.iter().map(|r| r.2).sum();
        let wins = rows.iter().filter(|r| r.3).count() as f64;
        // FLAT-SHARES track: the stake number read as a SHARE count, so a $100
        // flat-$ bet becomes 100 shares. Same fills, same entries — only the
        // sizing discipline differs (REFINED-STRATEGY rule 3).
        let total_pnl_shares: f64 = rows
            .iter()
            .map(|(_, stake, _, won, entry)| {
                stake * ((*won as i32) as f64 - entry) - fee_pct * stake * entry
            })
            .sum();
        // Running equity → curve, peak, max drawdown.
        let mut equity = 0.0;
        let mut peak = f64::NEG_INFINITY;
        let mut max_drawdown = 0.0;
        let mut curve = Vec::with_capacity(rows.len());
        for r in rows {
            equity += r.2;
            curve.push(equity);
            if equity > peak {
                peak = equity;
            }
            let dd = peak - equity;
            if dd > max_drawdown {
                max_drawdown = dd;
            }
        }
        // Sharpe-like ratio over per-DAY P&L (de-correlates within-day bets).
        let mut by_day: std::collections::BTreeMap<i64, f64> = std::collections::BTreeMap::new();
        for r in rows {
            let day = r.0.timestamp().div_euclid(86_400);
            *by_day.entry(day).or_insert(0.0) += r.2;
        }
        let daily: Vec<f64> = by_day.values().copied().collect();
        let sharpe = if daily.len() >= 2 {
            let n = daily.len() as f64;
            let mean = daily.iter().sum::<f64>() / n;
            let var = daily.iter().map(|d| (d - mean).powi(2)).sum::<f64>() / (n - 1.0);
            let sd = var.sqrt();
            if sd > 0.0 { mean / sd } else { 0.0 }
        } else {
            0.0
        };
        Self {
            bets,
            total_pnl,
            turnover,
            roi_on_turnover: if turnover > 0.0 {
                total_pnl / turnover
            } else {
                0.0
            },
            win_rate: if bets > 0 { wins / bets as f64 } else { 0.0 },
            peak_equity: if peak.is_finite() { peak.max(0.0) } else { 0.0 },
            max_drawdown,
            sharpe,
            curve,
            total_pnl_shares,
        }
    }
}

/// One fresh (market, outcome) anchor row for dense early-life capture
/// (migration 034). `signal_id` is the EARLIEST-fired signal for the pair, so
/// `secs_after_fire` measures from the true first fire.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct DenseCandidate {
    pub signal_id: i32,
    pub condition_id: String,
    pub outcome_index: i32,
    pub first_detected_at: DateTime<Utc>,
    pub n_backers: i32,
}

/// One (wallet × slice) earned-trust statistic over resolved BUY fills. Numbers
/// only — the verdict (gate reuse) is computed in the binary's
/// `scanner::trader_trust`. Surplus + sd are EVENT-clustered; `n_events` is the
/// gate's N. Mirrors [`StrategyScore`]'s shape for the wallet-keyed scoreboard.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct TraderSliceStat {
    pub wallet: String,
    /// 'overall' | 'sport' | 'band' | 'bettype' | 'recency7d' | 'recency30d'.
    pub slice_kind: String,
    /// '' | 'nba' | 'b3' | '7d' …
    pub slice_key: String,
    /// Distinct `COALESCE(event_slug, condition_id)` — the gate's de-correlated N.
    pub n_events: i64,
    /// Distinct fill-DAYS (UTC date of `ts`) in this slice — the within-day-
    /// correlation deflator for the trust gate's effective N (so one correlated
    /// weekend of fills can't clear the bar). Fewer days ⇒ effective N degrades
    /// toward 1 (fail-closed).
    pub n_days: i64,
    /// Resolved BUY fills in this slice (rows, not events).
    pub n_resolved: i64,
    /// Event-clustered AVG of `(advantage − band_blind)` — the favorite-longshot-
    /// neutralized edge. `None` if nothing resolved in the slice.
    pub surplus: Option<f64>,
    /// Std-dev of per-EVENT surplus (feeds the one-sided bound). `None` with <2 events.
    pub surplus_sd: Option<f64>,
    /// Event-clustered mean raw advantage `AVG_event(won::int − price)`.
    pub mean_adv: Option<f64>,
    /// Event-clustered hit-rate `AVG_event(won)`.
    pub hit_rate: Option<f64>,
}

/// Local truncate helper (avoids a cross-crate format dependency).
fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let t: String = s.chars().take(max.saturating_sub(1)).collect();
        format!("{t}…")
    }
}

#[cfg(test)]
mod window_store_it {
    //! Live-DB integration test for the L1 vote-window store + cursors. `#[ignore]`d
    //! so the normal gate stays DB-free; run it against a throwaway Postgres (schema
    //! migrated) with:
    //!
    //! ```text
    //! DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
    //!   cargo test -p polymarket-common window_store_it -- --ignored --nocapture
    //! ```
    use super::*;

    fn vote(wallet: &str, cond: &str, oidx: i32, price: f64, ts: DateTime<Utc>) -> WindowVote {
        WindowVote {
            trader_wallet: wallet.into(),
            name: wallet.into(),
            rank: Some(7),
            pnl: None, // exercises a NULL element in the float8[] UNNEST array
            quality: 1.5,
            condition_id: cond.into(),
            outcome_index: oidx,
            outcome: "Yes".into(),
            title: "t".into(),
            slug: "s".into(),
            event_slug: None, // exercises a NULL element in the text[] UNNEST array
            is_sports: false,
            price,
            size_usd: 1000.0,
            ts,
        }
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn insert_dedup_load_prune_cursors() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");

        let w = "0xtestwallet_window";
        // Clean any prior run.
        sqlx::query("DELETE FROM consensus_vote_window WHERE trader_wallet = $1")
            .bind(w)
            .execute(&pf.pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet = $1")
            .bind(w)
            .execute(&pf.pool)
            .await
            .unwrap();

        let t0 = Utc::now() - chrono::Duration::hours(10);
        let t1 = Utc::now() - chrono::Duration::hours(1);
        let a = vote(w, "0xc1", 0, 0.50, t0);
        let b = vote(w, "0xc2", 1, 0.30, t1);
        let dup = a.clone(); // same (wallet,cond,outcome,ts,price) → must dedup

        // First insert: 2 distinct atoms land, the dup is dropped.
        let n = pf.insert_window_votes(&[a, b, dup]).await.unwrap();
        assert_eq!(n, 2, "dup atom must be dropped by ON CONFLICT");
        // Re-insert the same set: everything already present → 0 new rows.
        let again = pf
            .insert_window_votes(&[vote(w, "0xc1", 0, 0.50, t0), vote(w, "0xc2", 1, 0.30, t1)])
            .await
            .unwrap();
        assert_eq!(again, 0, "re-seen atoms append nothing (self-healing safe)");

        // Load the trailing window: both atoms present; NULLs round-trip.
        let win = pf
            .load_window_votes(Utc::now() - chrono::Duration::hours(48))
            .await
            .unwrap();
        let mine: Vec<_> = win.iter().filter(|v| v.trader_wallet == w).collect();
        assert_eq!(mine.len(), 2);
        assert!(
            mine.iter()
                .all(|v| v.pnl.is_none() && v.event_slug.is_none())
        );

        // `since` cutoff excludes older atoms.
        let recent = pf
            .load_window_votes(Utc::now() - chrono::Duration::hours(2))
            .await
            .unwrap();
        assert_eq!(
            recent.iter().filter(|v| v.trader_wallet == w).count(),
            1,
            "only the 1h-old atom is within a 2h window"
        );

        // Prune older than 5h: drops the 10h-old atom, keeps the 1h-old one.
        let pruned = pf
            .prune_window_votes(Utc::now() - chrono::Duration::hours(5))
            .await
            .unwrap();
        assert!(pruned >= 1, "the 10h-old atom should be pruned");
        let after = pf
            .load_window_votes(Utc::now() - chrono::Duration::hours(48))
            .await
            .unwrap();
        assert_eq!(after.iter().filter(|v| v.trader_wallet == w).count(), 1);

        // Cursors: create the trader, stamp + read back the consensus cursor.
        pf.upsert_tracked_trader(&LeaderboardTraderUpsert {
            wallet: w.into(),
            username: Some("wtest".into()),
            rank: Some(7),
            pnl: None,
            volume: None,
            periods: "WEEK".into(),
            consensus_eligible: true,
        })
        .await
        .unwrap();
        let stamp = Utc::now();
        pf.set_consensus_cursors(&[w.to_string()], stamp)
            .await
            .unwrap();
        let cursors = pf.consensus_cursors().await.unwrap();
        let got = cursors.get(w).expect("cursor present after stamp");
        assert!(
            (*got - stamp).num_seconds().abs() <= 1,
            "cursor round-trips"
        );

        // Cleanup.
        sqlx::query("DELETE FROM consensus_vote_window WHERE trader_wallet = $1")
            .bind(w)
            .execute(&pf.pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet = $1")
            .bind(w)
            .execute(&pf.pool)
            .await
            .unwrap();
        println!("window_store_it: insert/dedup/load/prune/cursors all OK");
    }
}

#[cfg(test)]
mod trader_fills_it {
    //! Live-DB integration test for the durable trader-fill archive (Phase 0):
    //! dedup (tx + null-tx content), gap detection, and re-derived-quality book
    //! source. `#[ignore]`d like its sibling; run against a throwaway Postgres:
    //!
    //! ```text
    //! DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
    //!   cargo test -p polymarket-common trader_fills_it -- --ignored --nocapture
    //! ```
    use super::*;

    fn fill(
        wallet: &str,
        tx: Option<&str>,
        cond: &str,
        oidx: i32,
        price: f64,
        side: &str,
    ) -> NewTraderFill {
        NewTraderFill {
            wallet: wallet.into(),
            tx_hash: tx.map(|s| s.into()),
            condition_id: cond.into(),
            outcome_index: oidx,
            outcome: "Yes".into(),
            side: side.into(),
            price,
            size_usd: 1000.0,
            title: "t".into(),
            slug: "nba-x".into(),
            event_slug: Some("nba-x".into()),
            is_sports: true,
            sport: Some("nba".into()),
            bet_type: Some("spread".into()),
            ts: Utc::now() - chrono::Duration::hours(1),
            source: None,
            live_seen_at: None,
        }
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn deep_universe_eligibility_split() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations()
            .await
            .expect("migrations (incl. 033 consensus_eligible)");

        // Isolate: clear any synthetic rows from a prior run.
        sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet LIKE '0xdeep\\_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        let cutoff = 50i32;
        let depth = 200usize;
        let upsert = |i: usize, eligible: bool, periods: &'static str| {
            let pf = &pf;
            async move {
                pf.upsert_tracked_trader(&LeaderboardTraderUpsert {
                    wallet: format!("0xdeep_{i:04}"),
                    username: Some(format!("deep{i}")),
                    rank: Some(i as i32),
                    pnl: Some((depth - i) as f64),
                    volume: Some(0.0),
                    periods: periods.into(),
                    consensus_eligible: eligible,
                })
                .await
                .unwrap();
            }
        };

        const SPLIT_SQL: &str = "SELECT COUNT(*) FILTER (WHERE consensus_eligible), \
                    COUNT(*) FILTER (WHERE NOT consensus_eligible) \
             FROM followed_traders WHERE proxy_wallet LIKE '0xdeep\\_%' AND active = TRUE";

        // Upsert a synthetic depth-200 universe: rank i, eligible = rank ≤ cutoff.
        for i in 1..=depth {
            upsert(i, (i as i32) <= cutoff, "WEEK").await;
        }
        let (hot, deep): (i64, i64) = sqlx::query_as(SPLIT_SQL).fetch_one(&pf.pool).await.unwrap();
        assert_eq!(
            hot, cutoff as i64,
            "exactly cutoff traders vote in consensus"
        );
        assert_eq!(
            deep,
            depth as i64 - cutoff as i64,
            "the deep pool is captured but not voting"
        );

        // Idempotent: re-running the refresh yields the same split (ON CONFLICT).
        for i in 1..=depth {
            upsert(i, (i as i32) <= cutoff, "WEEK,MONTH").await;
        }
        let split2: (i64, i64) = sqlx::query_as(SPLIT_SQL).fetch_one(&pf.pool).await.unwrap();
        assert_eq!(split2, (hot, deep), "refresh is idempotent");

        // Non-monotonic under rank churn: a trader dropping past the cutoff loses
        // its vote (required for the byte-for-byte non-regression proof).
        upsert(1, false, "WEEK").await; // rank re-supplied deep, eligible=false
        let elig: bool = sqlx::query_scalar(
            "SELECT consensus_eligible FROM followed_traders WHERE proxy_wallet = '0xdeep_0001'",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert!(!elig, "leaderboard trader past cutoff is de-eligibled");

        // Manual follows are NEVER de-eligibled by a deep leaderboard sighting.
        sqlx::query(
            "INSERT INTO followed_traders (proxy_wallet, source, active, consensus_eligible) \
             VALUES ('0xdeep_manual', 'manual', TRUE, TRUE)",
        )
        .execute(&pf.pool)
        .await
        .unwrap();
        pf.upsert_tracked_trader(&LeaderboardTraderUpsert {
            wallet: "0xdeep_manual".into(),
            username: None,
            rank: Some(180),
            pnl: Some(1.0),
            volume: Some(0.0),
            periods: "WEEK".into(),
            consensus_eligible: false,
        })
        .await
        .unwrap();
        let (src, elig_m): (String, bool) = sqlx::query_as(
            "SELECT source, consensus_eligible FROM followed_traders \
             WHERE proxy_wallet = '0xdeep_manual'",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert_eq!(src, "manual", "manual source preserved");
        assert!(elig_m, "manual follow stays eligible despite a deep rank");

        sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet LIKE '0xdeep\\_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
    }

    /// PHASE 3 NON-REGRESSION (storage level): `load_window_votes` and
    /// `load_buy_fills_since` — the two book sources — return ONLY eligible traders'
    /// votes, while every vote (deep included) stays captured in the window/archive.
    /// Because book-building is a deterministic function of the loaded votes, an
    /// identical loaded set ⇒ identical books ⇒ identical emitted signals; so
    /// widening the tracked universe changes nothing the engine acts on until a deep
    /// trader is earned in. The signal-level half is proven in
    /// `copy_trading_bot::…::deep_pool_excluded_from_signals_shadow_differs`.
    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn eligibility_gate_load_is_byte_for_byte() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations (incl. 033)");

        let elig = ["0xelig_a", "0xelig_b", "0xelig_c"];
        let deep = ["0xdeepv_a", "0xdeepv_b", "0xdeepv_c"];
        let cond = "0xgatecond";
        for w in elig.iter().chain(deep.iter()) {
            sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet = $1")
                .bind(w)
                .execute(&pf.pool)
                .await
                .unwrap();
        }
        sqlx::query("DELETE FROM consensus_vote_window WHERE condition_id = $1")
            .bind(cond)
            .execute(&pf.pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM trader_fills WHERE condition_id = $1")
            .bind(cond)
            .execute(&pf.pool)
            .await
            .unwrap();

        // Wallets stored lowercased to match window/fill casing (LOWER-join).
        for (i, w) in elig.iter().enumerate() {
            pf.upsert_tracked_trader(&LeaderboardTraderUpsert {
                wallet: (*w).into(),
                username: None,
                rank: Some(i as i32 + 5),
                pnl: None,
                volume: None,
                periods: "WEEK".into(),
                consensus_eligible: true,
            })
            .await
            .unwrap();
        }
        for (i, w) in deep.iter().enumerate() {
            pf.upsert_tracked_trader(&LeaderboardTraderUpsert {
                wallet: (*w).into(),
                username: None,
                rank: Some(i as i32 + 120),
                pnl: None,
                volume: None,
                periods: "WEEK".into(),
                consensus_eligible: false,
            })
            .await
            .unwrap();
        }

        let now = Utc::now();
        let ts = now - chrono::Duration::minutes(10);
        let mkv = |w: &str| WindowVote {
            trader_wallet: w.into(),
            name: w.into(),
            rank: Some(9),
            pnl: None,
            quality: 1.0,
            condition_id: cond.into(),
            outcome_index: 0,
            outcome: "Yes".into(),
            title: "t".into(),
            slug: "s".into(),
            event_slug: None,
            is_sports: false,
            price: 0.5,
            size_usd: 1000.0,
            ts,
        };
        let votes: Vec<WindowVote> = elig.iter().chain(deep.iter()).map(|w| mkv(w)).collect();
        pf.insert_window_votes(&votes).await.unwrap();

        let since = now - chrono::Duration::hours(1);
        let mut loaded: Vec<String> = pf
            .load_window_votes(since)
            .await
            .unwrap()
            .into_iter()
            .filter(|v| v.condition_id == cond)
            .map(|v| v.trader_wallet)
            .collect();
        loaded.sort();
        assert_eq!(
            loaded, elig,
            "window book source returns eligible votes only; deep is filtered"
        );

        // All 6 votes ARE captured — the gate is at load (voting), not at capture.
        let (total,): (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM consensus_vote_window WHERE condition_id = $1")
                .bind(cond)
                .fetch_one(&pf.pool)
                .await
                .unwrap();
        assert_eq!(
            total, 6,
            "deep votes stay captured for the shadow/profile pass"
        );

        // The non-default fills book source filters identically.
        let mkf = |w: &str| NewTraderFill {
            wallet: w.into(),
            tx_hash: Some(format!("0x{w}buy")),
            condition_id: cond.into(),
            outcome_index: 0,
            outcome: "Yes".into(),
            side: "BUY".into(),
            price: 0.5,
            size_usd: 1000.0,
            title: "t".into(),
            slug: "s".into(),
            event_slug: None,
            is_sports: false,
            sport: None,
            bet_type: None,
            ts,
            source: None,
            live_seen_at: None,
        };
        let fills: Vec<NewTraderFill> = elig.iter().chain(deep.iter()).map(|w| mkf(w)).collect();
        pf.insert_trader_fills(&fills).await.unwrap();
        let mut floaded: Vec<String> = pf
            .load_buy_fills_since(since)
            .await
            .unwrap()
            .into_iter()
            .filter(|v| v.condition_id == cond)
            .map(|v| v.trader_wallet)
            .collect();
        floaded.sort();
        assert_eq!(floaded, elig, "fills book source also excludes deep");

        // --- EARNED eligibility (migration 035): the deliberate promotion path ---
        // The shadow feed returns exactly the excluded (deep, unearned) votes.
        let mut shadowed: Vec<String> = pf
            .load_excluded_window_votes(since)
            .await
            .unwrap()
            .into_iter()
            .filter(|v| v.condition_id == cond)
            .map(|v| v.trader_wallet)
            .collect();
        shadowed.sort();
        assert_eq!(shadowed, deep, "shadow feed = the complementary deep votes");

        // Earn ONE deep trader in. Idempotent: second call flips nothing.
        let flipped = pf
            .set_earned_eligible(&["0xdeepv_a".to_string()])
            .await
            .unwrap();
        assert_eq!(flipped, 1, "one row newly earned");
        let again = pf
            .set_earned_eligible(&["0xdeepv_a".to_string()])
            .await
            .unwrap();
        assert_eq!(again, 0, "earn is idempotent");

        // Both book sources now count the earned trader; the other deep stay out.
        let expect_earned = ["0xdeepv_a", "0xelig_a", "0xelig_b", "0xelig_c"];
        let mut loaded2: Vec<String> = pf
            .load_window_votes(since)
            .await
            .unwrap()
            .into_iter()
            .filter(|v| v.condition_id == cond)
            .map(|v| v.trader_wallet)
            .collect();
        loaded2.sort();
        assert_eq!(loaded2, expect_earned, "earned deep trader votes (window)");
        let mut floaded2: Vec<String> = pf
            .load_buy_fills_since(since)
            .await
            .unwrap()
            .into_iter()
            .filter(|v| v.condition_id == cond)
            .map(|v| v.trader_wallet)
            .collect();
        floaded2.sort();
        assert_eq!(floaded2, expect_earned, "earned deep trader votes (fills)");
        // …and it left the shadow feed (complementary by construction).
        let shadowed2: Vec<String> = pf
            .load_excluded_window_votes(since)
            .await
            .unwrap()
            .into_iter()
            .filter(|v| v.condition_id == cond)
            .map(|v| v.trader_wallet)
            .collect();
        assert!(
            !shadowed2.contains(&"0xdeepv_a".to_string()),
            "earned trader is no longer excluded"
        );

        // DURABILITY: a leaderboard refresh (rank churn, still deep) must NOT
        // clobber the earned promotion — the upsert never touches the column.
        pf.upsert_tracked_trader(&LeaderboardTraderUpsert {
            wallet: "0xdeepv_a".into(),
            username: None,
            rank: Some(199),
            pnl: None,
            volume: None,
            periods: "WEEK,MONTH".into(),
            consensus_eligible: false,
        })
        .await
        .unwrap();
        let (ce, ee): (bool, bool) = sqlx::query_as(
            "SELECT consensus_eligible, earned_eligible FROM followed_traders \
             WHERE proxy_wallet = '0xdeepv_a'",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert!(!ce, "rank-derived flag still FALSE (rank 199 > cutoff)");
        assert!(ee, "EARNED flag survives the leaderboard refresh");
        let mut loaded3: Vec<String> = pf
            .load_window_votes(since)
            .await
            .unwrap()
            .into_iter()
            .filter(|v| v.condition_id == cond)
            .map(|v| v.trader_wallet)
            .collect();
        loaded3.sort();
        assert_eq!(loaded3, expect_earned, "still voting after rank churn");

        // Cleanup.
        sqlx::query("DELETE FROM consensus_vote_window WHERE condition_id = $1")
            .bind(cond)
            .execute(&pf.pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM trader_fills WHERE condition_id = $1")
            .bind(cond)
            .execute(&pf.pool)
            .await
            .unwrap();
        for w in elig.iter().chain(deep.iter()) {
            sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet = $1")
                .bind(w)
                .execute(&pf.pool)
                .await
                .unwrap();
        }
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn insert_dedup_capture_loadfills() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");

        // followed_traders row is mixed-case to prove the case-robust join.
        let w_mixed = "0xTFtestWALLET01";
        let w_lc = w_mixed.to_lowercase();
        for t in [&w_lc, &w_mixed.to_string()] {
            sqlx::query("DELETE FROM trader_fills WHERE wallet = $1")
                .bind(t)
                .execute(&pf.pool)
                .await
                .unwrap();
        }
        sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet = $1")
            .bind(w_mixed)
            .execute(&pf.pool)
            .await
            .unwrap();

        // --- dedup: tx-level + intra-batch + null-tx content ---
        let a = fill(&w_lc, Some("0xtx1"), "0xc1", 0, 0.50, "BUY");
        let b = fill(&w_lc, Some("0xtx2"), "0xc2", 1, 0.30, "SELL");
        let dup_a = a.clone(); // same tx → dropped
        let n = pf
            .insert_trader_fills(&[a.clone(), b.clone(), dup_a])
            .await
            .unwrap();
        assert_eq!(n, 2, "intra-batch tx dup dropped");
        let again = pf.insert_trader_fills(&[a, b]).await.unwrap();
        assert_eq!(again, 0, "re-seen tx rows append nothing");

        // null-tx content dedup: identical content → 1; different price → 2.
        let n0 = fill(&w_lc, None, "0xc3", 0, 0.40, "BUY");
        let n0b = n0.clone();
        let n1 = fill(&w_lc, None, "0xc3", 0, 0.41, "BUY");
        let nn = pf.insert_trader_fills(&[n0, n0b, n1]).await.unwrap();
        assert_eq!(nn, 2, "null-tx content dup collapses; distinct price kept");

        // --- gap detection via record_capture ---
        pf.upsert_tracked_trader(&LeaderboardTraderUpsert {
            wallet: w_mixed.into(),
            username: Some("tfwtest".into()),
            rank: Some(1), // rank 1 → quality ≈ 2.0
            pnl: None,
            volume: None,
            periods: "WEEK".into(),
            consensus_eligible: true,
        })
        .await
        .unwrap();
        let gap = |pf: &PgPortfolio, w: &str| {
            let w = w.to_string();
            let pool = pf.pool.clone();
            async move {
                let (g,): (i32,) = sqlx::query_as(
                    "SELECT capture_gap_count FROM followed_traders WHERE proxy_wallet = $1",
                )
                .bind(&w)
                .fetch_one(&pool)
                .await
                .unwrap();
                g
            }
        };
        let t0 = Utc::now() - chrono::Duration::hours(3);
        let t1 = Utc::now() - chrono::Duration::hours(2);
        // First poll: full page but last_newest was NULL → never a gap.
        pf.record_capture(w_mixed, t0, t1, 100).await.unwrap();
        assert_eq!(gap(&pf, w_mixed).await, 0, "first poll never counts a gap");
        // Next poll: full page whose oldest row is newer than last_newest(=t1) → gap.
        let t2 = Utc::now() - chrono::Duration::minutes(30);
        let t3 = Utc::now() - chrono::Duration::minutes(10);
        pf.record_capture(w_mixed, t2, t3, 100).await.unwrap();
        assert_eq!(gap(&pf, w_mixed).await, 1, "full page + no overlap = gap");
        // Partial page: never a gap regardless of timing.
        let t4 = Utc::now();
        pf.record_capture(w_mixed, t4, t4, 50).await.unwrap();
        assert_eq!(gap(&pf, w_mixed).await, 1, "partial page never adds a gap");

        // --- load_buy_fills_since: BUY only, re-derived quality via case-robust join ---
        let since = Utc::now() - chrono::Duration::hours(48);
        let votes = pf.load_buy_fills_since(since).await.unwrap();
        let mine: Vec<_> = votes.iter().filter(|v| v.trader_wallet == w_lc).collect();
        assert!(mine.iter().all(|v| v.price > 0.0), "loaded BUY fills");
        // quality_weight(Some(1)) = 1.0 + (50-1)/50 = 1.98 — the SQL must match
        // the Rust formula exactly (this asserts they stay in sync).
        assert!(
            mine.iter().all(|v| (v.quality - 1.98).abs() < 1e-9),
            "rank-1 trader's quality re-derived to 1.98 via the LOWER() join (got {:?})",
            mine.iter().map(|v| v.quality).collect::<Vec<_>>()
        );
        // SELL fill (0xc2) must be excluded from the BUY book source.
        assert!(
            !mine.iter().any(|v| v.condition_id == "0xc2"),
            "SELL excluded"
        );

        // Cleanup.
        sqlx::query("DELETE FROM trader_fills WHERE wallet = $1")
            .bind(&w_lc)
            .execute(&pf.pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet = $1")
            .bind(w_mixed)
            .execute(&pf.pool)
            .await
            .unwrap();
        println!("trader_fills_it: dedup/gap/capture/load_buy_fills all OK");
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn resolve_multi_outcome_and_void() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");

        let w = "0xtfresolve";
        let (c_win, c_void) = ("0xcond_resolved", "0xcond_void");
        for c in [c_win, c_void] {
            sqlx::query("DELETE FROM trader_fills WHERE condition_id = $1")
                .bind(c)
                .execute(&pf.pool)
                .await
                .unwrap();
        }

        // Multi-outcome market: BUY on the winner (idx 1), BUY on a loser (idx 0),
        // SELL on idx 2 — all at price 0.40. A separate (to-be-void) market.
        let rows = [
            fill(w, Some("0xr1"), c_win, 1, 0.40, "BUY"),
            fill(w, Some("0xr2"), c_win, 0, 0.40, "BUY"),
            fill(w, Some("0xr3"), c_win, 2, 0.40, "SELL"),
            fill(w, Some("0xv1"), c_void, 0, 0.40, "BUY"),
        ];
        pf.insert_trader_fills(&rows).await.unwrap();

        // Both conds appear in the independent unresolved source (min_age 0).
        let conds = pf
            .trader_fill_unresolved_conditions(chrono::Duration::zero(), 100)
            .await
            .unwrap();
        assert!(conds.contains(&c_win.to_string()) && conds.contains(&c_void.to_string()));

        // Resolve c_win with winner index 1; c_void is SKIPPED (housekeeping's
        // void branch) — its fills must stay unresolved.
        let n = pf.resolve_trader_fills(c_win, 1).await.unwrap();
        assert_eq!(n, 3, "all 3 fills on the resolved market settle");

        #[derive(sqlx::FromRow)]
        struct FillRow {
            #[allow(dead_code)]
            outcome_index: i32,
            side: String,
            outcome_won: Option<bool>,
            advantage: Option<f64>,
            resolved: bool,
        }
        let got: Vec<FillRow> = sqlx::query_as(
            "SELECT outcome_index, side, outcome_won, advantage, resolved \
             FROM trader_fills WHERE condition_id = $1 ORDER BY outcome_index",
        )
        .bind(c_win)
        .fetch_all(&pf.pool)
        .await
        .unwrap();
        // idx 0 (BUY loser): won=false, advantage = 0 - 0.40 = -0.40.
        assert_eq!(got[0].outcome_won, Some(false));
        assert!((got[0].advantage.unwrap() + 0.40).abs() < 1e-9);
        // idx 1 (BUY winner): won=true, advantage = 1 - 0.40 = 0.60.
        assert_eq!(got[1].outcome_won, Some(true));
        assert!((got[1].advantage.unwrap() - 0.60).abs() < 1e-9);
        // idx 2 (SELL): won marked, advantage NULL (round-trip PnL is v2).
        assert_eq!(got[2].side, "SELL");
        assert_eq!(got[2].outcome_won, Some(false));
        assert!(got[2].advantage.is_none(), "SELL advantage is NULL");
        assert!(got.iter().all(|r| r.resolved), "all marked resolved");

        // Void market: never resolved → still in the unresolved source.
        let still: Vec<String> = pf
            .trader_fill_unresolved_conditions(chrono::Duration::zero(), 100)
            .await
            .unwrap();
        assert!(
            still.contains(&c_void.to_string()),
            "void market stays unresolved"
        );
        assert!(
            !still.contains(&c_win.to_string()),
            "resolved market dropped from source"
        );

        for c in [c_win, c_void] {
            sqlx::query("DELETE FROM trader_fills WHERE condition_id = $1")
                .bind(c)
                .execute(&pf.pool)
                .await
                .unwrap();
        }
        println!("trader_fills_it: multi-outcome resolve + void-skip all OK");
    }

    /// SURVIVORSHIP CAPTURE FIX (capture-hardening Item 1): a DEACTIVATED wallet
    /// that is still scorecard-eligible is returned by
    /// `scorecard_eligible_dropped_wallets`, and its new fills LAND in the archive
    /// through the ordinary `insert_trader_fills` path — while an active or
    /// ineligible wallet is NOT returned. This is the query the hardened loop keys
    /// on; the acceptance ("deactivated-wallet fills appear in trader_fills").
    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn capture_dropped_selects_deactivated_scorecard_eligible() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");

        // Three synthetic wallets — the fills join is lower-cased, so store lower.
        let dropped = "0xcd_dropped_elig"; // active=false + ≥100 band fills → RETURNED
        let active = "0xcd_active_elig"; // active=true  + ≥100 band fills → NOT returned
        let thin = "0xcd_dropped_thin"; // active=false + too few fills   → NOT returned
        for w in [dropped, active, thin] {
            sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet = $1")
                .bind(w)
                .execute(&pf.pool)
                .await
                .unwrap();
            sqlx::query("DELETE FROM trader_fills WHERE wallet = $1")
                .bind(w)
                .execute(&pf.pool)
                .await
                .unwrap();
        }

        // Row helper: a BUY fill in the 0.45–0.90 band, unique tx so no dedup.
        let bandfill = |w: &str, i: usize| NewTraderFill {
            wallet: w.into(),
            tx_hash: Some(format!("0xcd_{w}_{i}")),
            condition_id: format!("0xcd_cond_{i}"),
            outcome_index: 0,
            outcome: "Yes".into(),
            side: "BUY".into(),
            price: 0.60,
            size_usd: 100.0,
            title: "t".into(),
            slug: "nba-x".into(),
            event_slug: Some(format!("ev-{i}")),
            is_sports: true,
            sport: Some("nba".into()),
            bet_type: Some("spread".into()),
            ts: Utc::now() - chrono::Duration::days(1),
            source: None,
            live_seen_at: None,
        };

        // Eligible pool = ≥100 band fills; give `dropped` and `active` 100, `thin` 3.
        let mut fills = Vec::new();
        for i in 0..100 {
            fills.push(bandfill(dropped, i));
            fills.push(bandfill(active, 1_000 + i));
        }
        for i in 0..3 {
            fills.push(bandfill(thin, 2_000 + i));
        }
        pf.insert_trader_fills(&fills).await.unwrap();

        // followed_traders rows: `dropped` + `thin` deactivated, `active` active.
        for (w, is_active) in [(dropped, false), (active, true), (thin, false)] {
            sqlx::query(
                "INSERT INTO followed_traders \
                   (proxy_wallet, source, active, consensus_eligible, last_seen_on_lb) \
                 VALUES ($1, 'leaderboard', $2, TRUE, NOW() - INTERVAL '3 days') \
                 ON CONFLICT (proxy_wallet) DO UPDATE SET active = EXCLUDED.active",
            )
            .bind(w)
            .bind(is_active)
            .execute(&pf.pool)
            .await
            .unwrap();
        }

        let got = pf.scorecard_eligible_dropped_wallets().await.unwrap();
        let names: std::collections::HashSet<String> =
            got.iter().map(|(w, _)| w.clone()).collect();
        assert!(
            names.contains(dropped),
            "deactivated + scorecard-eligible wallet is selected"
        );
        assert!(
            !names.contains(active),
            "an ACTIVE wallet is polled by the main loop — not the dropped lane"
        );
        assert!(
            !names.contains(thin),
            "a deactivated wallet below the ≥100-fill floor is not scorecard-eligible"
        );

        // The archive path itself: a NEW fill for the dropped wallet lands (dedup
        // never drops a genuinely new tx). This is the acceptance condition.
        let before: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM trader_fills WHERE wallet = $1")
                .bind(dropped)
                .fetch_one(&pf.pool)
                .await
                .unwrap();
        let n = pf
            .insert_trader_fills(&[bandfill(dropped, 9_999)])
            .await
            .unwrap();
        assert_eq!(n, 1, "a new deactivated-wallet fill is inserted");
        let after: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM trader_fills WHERE wallet = $1")
                .bind(dropped)
                .fetch_one(&pf.pool)
                .await
                .unwrap();
        assert_eq!(after, before + 1, "deactivated-wallet fills land in the archive");

        for w in [dropped, active, thin] {
            sqlx::query("DELETE FROM trader_fills WHERE wallet = $1")
                .bind(w)
                .execute(&pf.pool)
                .await
                .unwrap();
            sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet = $1")
                .bind(w)
                .execute(&pf.pool)
                .await
                .unwrap();
        }
        println!("trader_fills_it: capture-dropped selection + archive-land OK");
    }
}

#[cfg(test)]
mod market_feature_log_it {
    //! Live-DB integration test for the forward 29-feature log (Phase 1).
    //! Self-contained (runs migrations itself). `#[ignore]`d; run against a
    //! throwaway Postgres:
    //!
    //! ```text
    //! DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
    //!   cargo test -p polymarket-common market_feature_log_it -- --ignored --nocapture
    //! ```
    use super::*;
    use crate::model::features::MarketFeatures;

    fn zero_feat(yes_price: f64) -> MarketFeatures {
        MarketFeatures {
            yes_price,
            momentum_1h: 0.0,
            momentum_24h: 0.0,
            volatility_24h: 0.0,
            rsi: 0.0,
            log_volume: 0.0,
            days_to_expiry: 0.0,
            is_crypto: 0.0,
            price_change_1d: 0.0,
            price_change_1w: 0.0,
            days_since_created: 0.0,
            created_to_expiry_span: 0.0,
            is_sports: 0.0,
            q_length: 0.0,
            q_word_count: 0.0,
            q_avg_word_len: 0.0,
            q_word_diversity: 0.0,
            q_has_number: 0.0,
            q_has_year: 0.0,
            q_has_percent: 0.0,
            q_has_dollar: 0.0,
            q_has_date: 0.0,
            q_starts_will: 0.0,
            q_has_by: 0.0,
            q_has_before: 0.0,
            q_has_above: 0.0,
            q_sentiment_pos: 0.0,
            q_sentiment_neg: 0.0,
            q_certainty: 0.0,
        }
    }

    async fn insert_strict_signal(pf: &PgPortfolio, cond: &str) -> i64 {
        let (id,): (i32,) = sqlx::query_as(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, n_backers, n_opposers, net_count, \
                net_quality, mean_price, price_std, recency_mins, total_usd, score, tier) \
             VALUES ('strict', $1, 0, 5, 0, 5, 5.0, 0.5, 0.02, 10, 2000, 1.0, 'WATCH') \
             RETURNING id",
        )
        .bind(cond)
        .fetch_one(&pf.pool)
        .await
        .expect("insert strict signal");
        id as i64
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL"]
    async fn log_roundtrip_conflict_cascade() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations (incl. 028)");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'mfl_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // Empty batch is a no-op.
        assert_eq!(pf.log_market_features(&[]).await.unwrap(), 0);

        // Insert a strict signal + log its YES-oriented 29-feature vector.
        let sid = insert_strict_signal(&pf, "mfl_cond1").await;
        let row = NewMarketFeatureLog {
            signal_id: sid,
            condition_id: "mfl_cond1".into(),
            outcome_index: 0,
            yes_token: true,
            clob_mid: Some(0.44),
            features: serde_json::to_value(zero_feat(0.42)).unwrap(),
        };
        assert_eq!(
            pf.log_market_features(std::slice::from_ref(&row))
                .await
                .unwrap(),
            1
        );

        // Read back: right signal_id, captured mid, a 29-named-field JSON object.
        // Phase 2: the first INSERT also populates first_features/first_captured_at.
        let (got_sid, feats, mid, first_feats, first_cap): (
            i64,
            serde_json::Value,
            Option<f64>,
            serde_json::Value,
            DateTime<Utc>,
        ) = sqlx::query_as(
            "SELECT signal_id, features, clob_mid, first_features, first_captured_at \
             FROM market_feature_log WHERE condition_id = 'mfl_cond1'",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert_eq!(got_sid, sid, "feature log keyed to its signal");
        assert_eq!(mid, Some(0.44));
        let obj = feats.as_object().expect("features stored as a JSON object");
        assert_eq!(
            obj.len(),
            MarketFeatures::NAMES.len(),
            "all 29 named features present"
        );
        assert!(obj.contains_key("yes_price") && obj.contains_key("q_certainty"));
        assert_eq!(obj["yes_price"].as_f64().unwrap(), 0.42);
        // Decision-time snapshot == the freshest on the first insert.
        assert_eq!(
            first_feats["yes_price"].as_f64().unwrap(),
            0.42,
            "first_features set to the decision-time snapshot on INSERT"
        );

        // Re-log the same (signal, condition, outcome): updates in place, no dup.
        let row2 = NewMarketFeatureLog {
            features: serde_json::to_value(zero_feat(0.99)).unwrap(),
            clob_mid: Some(0.61),
            ..row.clone()
        };
        assert_eq!(
            pf.log_market_features(std::slice::from_ref(&row2))
                .await
                .unwrap(),
            1
        );
        let (cnt, mid2, yp): (i64, Option<f64>, f64) = sqlx::query_as(
            "SELECT COUNT(*)::int8, MAX(clob_mid), MAX((features->>'yes_price')::float8) \
             FROM market_feature_log WHERE condition_id = 'mfl_cond1'",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert_eq!(cnt, 1, "re-log updates in place (no duplicate row)");
        assert_eq!(mid2, Some(0.61), "conflict updated clob_mid");
        assert_eq!(yp, 0.99, "conflict updated the features snapshot");

        // Phase 2: the re-log refreshed `features` (→0.99) but the DECISION-TIME
        // snapshot is held UNCHANGED — first_features stays 0.42 and
        // first_captured_at is byte-identical to the first insert's timestamp.
        let (first_yp, first_cap2): (f64, DateTime<Utc>) = sqlx::query_as(
            "SELECT (first_features->>'yes_price')::float8, first_captured_at \
             FROM market_feature_log WHERE condition_id = 'mfl_cond1'",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert_eq!(first_yp, 0.42, "re-log must NOT overwrite first_features");
        assert_eq!(
            first_cap2, first_cap,
            "re-log must NOT touch first_captured_at"
        );

        // Cascade: deleting the signal removes its feature-log row.
        sqlx::query("DELETE FROM consensus_signals WHERE id = $1")
            .bind(sid as i32)
            .execute(&pf.pool)
            .await
            .unwrap();
        let (after,): (i64,) = sqlx::query_as(
            "SELECT COUNT(*)::int8 FROM market_feature_log WHERE condition_id = 'mfl_cond1'",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert_eq!(after, 0, "ON DELETE CASCADE removed the log row");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'mfl_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!("market_feature_log_it: roundtrip + conflict-update + cascade all OK");
    }
}

/// Live-DB integration test for the honest, realizable P&L instrument (Phase 0).
/// `#[ignore]`d so the normal gate stays DB-free; run against a throwaway Postgres
/// (schema migrated):
///
/// ```text
/// DATABASE_URL=postgres://bot:bot@localhost:55499/polymarket \
///   cargo test -p polymarket-common honest_pnl_it -- --ignored --nocapture
/// ```
#[cfg(test)]
mod honest_pnl_it {
    use super::*;

    /// Insert a resolved consensus signal with a captured pre-resolution mid.
    #[allow(clippy::too_many_arguments)]
    async fn seed(
        pf: &PgPortfolio,
        strategy: &str,
        cond: &str,
        event_slug: &str,
        p0: f64,
        mean_price: f64,
        total_usd: f64,
        won: bool,
    ) {
        sqlx::query(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                score, tier, initial_market_price, resolved, outcome_won, \
                first_detected_at, resolved_at) \
             VALUES ($1,$2,0,$3,5,0,5,5.0,$5,0.02,10,$6,1.0,'WATCH',$4,TRUE,$7, \
                     NOW() - INTERVAL '2 hours', NOW())",
        )
        .bind(strategy)
        .bind(cond)
        .bind(event_slug)
        .bind(p0)
        .bind(mean_price)
        .bind(total_usd)
        .bind(won)
        .execute(&pf.pool)
        .await
        .expect("seed consensus_signal");
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn honest_roi_event_clustered_and_blind_excluded() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hp_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // Strategy 'hp_a': two events. ev1 has TWO signals (varied bands) to
        // exercise the within-event collapse; ev2 has one.
        //   S1: ev1 p0=0.40 won   → honest_roi = 0.59/0.41 − 0.02 =  1.41902
        //   S2: ev1 p0=0.60 lost  → honest_roi = −0.61/0.61 − 0.02 = −1.02000
        //   S3: ev2 p0=0.50 won   → honest_roi = 0.49/0.51 − 0.02 =  0.94078
        // ev1 = mean(S1,S2) = 0.19951 ; ev2 = 0.94078
        // honest_roi (across 2 events) = 0.570145
        seed(&pf, "hp_a", "hp_c1", "hp_ev1", 0.40, 0.45, 3000.0, true).await;
        seed(&pf, "hp_a", "hp_c2", "hp_ev1", 0.60, 0.55, 1000.0, false).await;
        seed(&pf, "hp_a", "hp_c3", "hp_ev2", 0.50, 0.50, 2000.0, true).await;
        // A `_blind` row that MUST be excluded from the instrument.
        seed(&pf, "_blind", "hp_c4", "hp_ev3", 0.30, 0.30, 5000.0, true).await;

        let rows = pf.honest_pnl_by_strategy(0.01, 0.02, 900.0).await.unwrap();
        assert!(
            rows.iter().all(|r| r.strategy != "_blind"),
            "the blind baseline is never a tracked strategy"
        );
        let a = rows
            .iter()
            .find(|r| r.strategy == "hp_a")
            .expect("hp_a present");

        assert_eq!(a.distinct_events, 2, "two distinct events");
        assert_eq!(a.resolved, 3, "three resolved rows");
        let approx = |got: Option<f64>, want: f64, what: &str| {
            let g = got.unwrap_or(f64::NAN);
            assert!((g - want).abs() < 1e-4, "{what}: got {g}, want {want}");
        };
        // Event-clustered honest ROI — the hand-computed 0.570145.
        approx(a.honest_roi, 0.570_145, "honest_roi");
        // clv_share event-clustered: ev1 mean(0.60,−0.60)=0, ev2 0.50 → 0.25.
        approx(a.clv_share, 0.25, "clv_share");
        // honest_edge_share: ev1 mean(0.59,−0.61)=−0.01, ev2 0.49 → 0.24.
        approx(a.honest_edge_share, 0.24, "honest_edge_share");
        // sharp_edge: ev1 mean(0.55,−0.55)=0, ev2 0.50 → 0.25.
        approx(a.sharp_edge, 0.25, "sharp_edge");
        // hit-rate event-clustered: ev1 0.5, ev2 1.0 → 0.75.
        approx(a.hit_rate, 0.75, "hit_rate");
        // median liquidity proxy over the 3 resolved rows: median(3000,1000,2000).
        approx(a.median_sharp_usd, 2000.0, "median_sharp_usd");

        // Segment breakdown: day / band / horizon cells all render, event-clustered.
        let segs = pf.honest_pnl_segments(0.01, 0.02).await.unwrap();
        let a_segs: Vec<_> = segs.iter().filter(|s| s.strategy == "hp_a").collect();
        assert!(!a_segs.is_empty(), "hp_a has segment cells");
        // All rows resolved NOW() → exactly ONE day-regime.
        let days: Vec<_> = a_segs.iter().filter(|s| s.seg_kind == "day").collect();
        assert_eq!(days.len(), 1, "one day-regime");
        assert_eq!(days[0].n_events, 2, "both events in the single day-regime");
        // Horizon: first_detected_at = NOW()-2h → same_day for every row.
        let hz: Vec<_> = a_segs.iter().filter(|s| s.seg_kind == "horizon").collect();
        assert_eq!(hz.len(), 1, "one horizon bucket");
        assert_eq!(hz[0].seg_key, "same_day", "resolved <24h ⇒ same_day");
        // Bands: p0 0.40 & 0.50 → band 3; 0.60 → band 4 (two distinct bands).
        let bands: Vec<_> = a_segs.iter().filter(|s| s.seg_kind == "band").collect();
        assert_eq!(bands.len(), 2, "two price bands");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hp_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!(
            "honest_pnl_it: honest_roi={:?} (want 0.570145), event-clustered, _blind excluded — OK",
            a.honest_roi
        );
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn entry_ask_set_once_and_preferred_over_heuristic() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hpask_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // An OPEN signal (resolved=false) with a captured mid but no ask yet.
        let (id,): (i32,) = sqlx::query_as(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                score, tier, initial_market_price, resolved, first_detected_at) \
             VALUES ('hp_ask','hpask_c1',0,'hpask_ev',5,0,5,5.0,0.50,0.02,10,2000,1.0,'WATCH', \
                     0.50, FALSE, NOW() - INTERVAL '2 hours') RETURNING id",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();

        // COALESCE-once: the first ask sticks; a later capture is a no-op.
        assert!(
            pf.set_entry_ask(id, 0.55).await.unwrap(),
            "first ask written"
        );
        assert!(
            !pf.set_entry_ask(id, 0.99).await.unwrap(),
            "second capture never overwrites"
        );
        let (ask,): (Option<f64>,) =
            sqlx::query_as("SELECT entry_ask FROM consensus_signals WHERE id = $1")
                .bind(id)
                .fetch_one(&pf.pool)
                .await
                .unwrap();
        assert_eq!(ask, Some(0.55), "entry_ask is the first captured value");

        // Now the signal resolves (won). Post-resolution the ask cannot change.
        sqlx::query(
            "UPDATE consensus_signals SET resolved = TRUE, outcome_won = TRUE, resolved_at = NOW() \
             WHERE id = $1",
        )
        .bind(id)
        .execute(&pf.pool)
        .await
        .unwrap();
        assert!(
            !pf.set_entry_ask(id, 0.10).await.unwrap(),
            "resolved rows are never touched (leak-free)"
        );

        // The honest query PREFERS the real ask: entry = 0.55 (not mid+haircut 0.51).
        // honest_roi = (1 − 0.55)/0.55 − 0.02 = 0.79818 ; ask_coverage = 100%.
        let rows = pf.honest_pnl_by_strategy(0.01, 0.02, 900.0).await.unwrap();
        let r = rows.iter().find(|r| r.strategy == "hp_ask").unwrap();
        assert!(
            (r.honest_roi.unwrap() - 0.798_18).abs() < 1e-3,
            "entry_ask preferred: honest_roi={:?} (want ~0.79818, NOT the heuristic 0.94078)",
            r.honest_roi
        );
        assert!(
            (r.ask_coverage.unwrap() - 1.0).abs() < 1e-9,
            "100% real-ask coverage"
        );

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hpask_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!("entry_ask_it: set-once + resolved-guard + query-prefers-ask — OK");
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn set_entry_ask_decision_records_provenance_once() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hpdec_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // OPEN signal, no ask yet, detected 2h ago.
        let (id,): (i32,) = sqlx::query_as(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                score, tier, initial_market_price, resolved, first_detected_at) \
             VALUES ('hp_dec','hpdec_c1',0,'hpdec_ev',5,0,5,5.0,0.50,0.02,10,2000,1.0,'WATCH', \
                     0.90, FALSE, NOW() - INTERVAL '2 hours') RETURNING id",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();

        // First decision capture writes ask + at + mid together.
        assert!(
            pf.set_entry_ask_decision(id, 0.92, 0.90).await.unwrap(),
            "first decision capture written"
        );
        // Set-once: a later capture (even different values) is a no-op.
        assert!(
            !pf.set_entry_ask_decision(id, 0.99, 0.95).await.unwrap(),
            "second capture never overwrites the decision-time provenance"
        );
        let (ask, mid, has_at): (Option<f64>, Option<f64>, bool) = sqlx::query_as(
            "SELECT entry_ask, entry_ask_mid, (entry_ask_at IS NOT NULL) \
             FROM consensus_signals WHERE id = $1",
        )
        .bind(id)
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert_eq!(ask, Some(0.92), "entry_ask is the first captured ask");
        assert_eq!(mid, Some(0.90), "entry_ask_mid is the paired mid");
        assert!(has_at, "entry_ask_at stamped at capture");

        // Post-resolution the decision capture is refused (leak-free).
        sqlx::query(
            "UPDATE consensus_signals SET resolved = TRUE, outcome_won = TRUE, resolved_at = NOW() \
             WHERE id = $1",
        )
        .bind(id)
        .execute(&pf.pool)
        .await
        .unwrap();
        // A fresh open row proves resolved-guard is what blocks (not just set-once).
        let (id2,): (i32,) = sqlx::query_as(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                score, tier, initial_market_price, resolved, outcome_won, first_detected_at, resolved_at) \
             VALUES ('hp_dec','hpdec_c2',0,'hpdec_ev2',5,0,5,5.0,0.50,0.02,10,2000,1.0,'WATCH', \
                     0.90, TRUE, TRUE, NOW() - INTERVAL '2 hours', NOW()) RETURNING id",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert!(
            !pf.set_entry_ask_decision(id2, 0.10, 0.11).await.unwrap(),
            "resolved rows are never touched (leak-free)"
        );

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hpdec_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!("set_entry_ask_decision_it: ask+at+mid set-once + resolved-guard — OK");
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn snapshot_reports_first_price_exactly_once() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hpfp_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // OPEN signal with NO initial_market_price yet.
        let (id,): (i32,) = sqlx::query_as(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                score, tier, resolved, first_detected_at) \
             VALUES ('hp_fp','hpfp_c1',0,'hpfp_ev',5,0,5,5.0,0.50,0.02,10,2000,1.0,'WATCH', \
                     FALSE, NOW()) RETURNING id",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();

        // First price seen → first_price = true (this is the decision-time moment).
        assert!(
            pf.snapshot_consensus_signal(id, 5, 5, 0.50, Some(0.90))
                .await
                .unwrap(),
            "first live price first-sets initial_market_price (decision-time)"
        );
        // Later prices → false (initial_market_price already frozen).
        assert!(
            !pf.snapshot_consensus_signal(id, 6, 6, 0.50, Some(0.93))
                .await
                .unwrap(),
            "a later price does not re-set initial_market_price"
        );
        // No price → false (nothing to set).
        assert!(
            !pf.snapshot_consensus_signal(id, 7, 7, 0.50, None)
                .await
                .unwrap(),
            "no market price ⇒ not a first-price event"
        );

        // initial_market_price stuck at the FIRST value; last_market_price moved.
        let (ip, lp): (Option<f64>, Option<f64>) = sqlx::query_as(
            "SELECT initial_market_price, last_market_price FROM consensus_signals WHERE id = $1",
        )
        .bind(id)
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert_eq!(ip, Some(0.90), "initial_market_price frozen at first price");
        assert_eq!(lp, Some(0.93), "last_market_price follows the latest price");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hpfp_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!("snapshot_first_price_it: first_price true once, then false — OK");
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn realized_vs_modeled_split_and_haircut() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hprz_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // 3 resolved WINS, all p0=0.90. Real asks captured with different lags:
        //   ev1: ask 0.94, +60s  → decision-time
        //   ev2: ask 0.92, +120s → decision-time
        //   ev3: ask 0.99, +2h   → LAGGED (excluded from realized, counts in coverage)
        for (i, ask, lag_secs) in [(1, 0.94, 60i64), (2, 0.92, 120), (3, 0.99, 7200)] {
            sqlx::query(
                "INSERT INTO consensus_signals \
                   (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                    net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                    score, tier, initial_market_price, resolved, outcome_won, \
                    first_detected_at, resolved_at, entry_ask, entry_ask_mid, entry_ask_at) \
                 VALUES ('rz', $1, 0, $2, 5,0,5,5.0,0.80,0.02,10,2000,1.0,'WATCH', \
                         0.90, TRUE, TRUE, NOW() - INTERVAL '1 day', NOW() - INTERVAL '20 hours', \
                         $3, 0.90, (NOW() - INTERVAL '1 day') + ($4 || ' seconds')::interval)",
            )
            .bind(format!("hprz_c{i}"))
            .bind(format!("hprz_ev{i}"))
            .bind(ask)
            .bind(lag_secs.to_string())
            .execute(&pf.pool)
            .await
            .unwrap();
        }

        // decision_lag = 900s ⇒ ev1+ev2 are decision-time, ev3 is lagged.
        let rows = pf.honest_pnl_by_strategy(0.01, 0.02, 900.0).await.unwrap();
        let r = rows.iter().find(|r| r.strategy == "rz").unwrap();

        assert_eq!(r.resolved, 3, "3 resolved rows");
        assert!(
            (r.ask_coverage.unwrap() - 1.0).abs() < 1e-9,
            "all 3 have a real ask ⇒ 100% ask coverage"
        );
        assert!(
            (r.decision_coverage.unwrap() - 2.0 / 3.0).abs() < 1e-6,
            "2/3 decision-time (ev3 lagged): {:?}",
            r.decision_coverage
        );
        assert_eq!(
            r.realized_events,
            Some(2),
            "realized uses 2 decision events"
        );
        // realized_roi = mean of ev1,ev2: ((1-.94)/.94-.02 + (1-.92)/.92-.02)/2
        let want_rz = (((1.0 - 0.94) / 0.94 - 0.02) + ((1.0 - 0.92) / 0.92 - 0.02)) / 2.0;
        assert!(
            (r.realized_roi.unwrap() - want_rz).abs() < 1e-6,
            "realized_roi={:?} want {:.6} (decision-time asks only)",
            r.realized_roi,
            want_rz
        );
        // median real haircut over the DECISION-TIME cohort only (ev1=0.04, ev2=0.02;
        // ev3=0.09 is LAGGED → excluded) → median{0.04,0.02} = 0.03. (Audit #6: the
        // haircut must match the realized cohort, not blend in hours-late spreads.)
        assert!(
            (r.median_haircut.unwrap() - 0.03).abs() < 1e-6,
            "decision-time median haircut {:?} want 0.03 (vs assumed 0.01)",
            r.median_haircut
        );
        // Modeled honest_roi uses COALESCE(entry_ask,…) = the ask on ALL 3 (incl. the
        // lagged ev3), so it differs from the decision-time-only realized number.
        let want_modeled = (((1.0 - 0.94) / 0.94 - 0.02)
            + ((1.0 - 0.92) / 0.92 - 0.02)
            + ((1.0 - 0.99) / 0.99 - 0.02))
            / 3.0;
        assert!(
            (r.honest_roi.unwrap() - want_modeled).abs() < 1e-6,
            "modeled honest_roi={:?} want {:.6}",
            r.honest_roi,
            want_modeled
        );
        assert!(
            r.realized_roi.unwrap() > r.honest_roi.unwrap(),
            "here decision-time realized ({:.4}) beats the ask-blended modeled ({:.4}) \
             because the lagged ev3 ask (0.99) drags the modeled down",
            r.realized_roi.unwrap(),
            r.honest_roi.unwrap()
        );

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hprz_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!(
            "realized_vs_modeled_it: realized={:.4} modeled={:.4} decision_cov={:.2} haircut={:.3} — OK",
            r.realized_roi.unwrap(),
            r.honest_roi.unwrap(),
            r.decision_coverage.unwrap(),
            r.median_haircut.unwrap(),
        );
    }

    /// Insert a RESOLVED consensus signal with an explicit resolution day-offset.
    async fn seed_resolved_dayoffset(
        pf: &PgPortfolio,
        strategy: &str,
        cond: &str,
        p0: f64,
        won: bool,
        days_ago: i64,
    ) {
        sqlx::query(&format!(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, n_backers, n_opposers, net_count, \
                net_quality, mean_price, price_std, recency_mins, total_usd, score, tier, \
                initial_market_price, resolved, outcome_won, first_detected_at, resolved_at) \
             VALUES ($1,$2,0,5,0,5,5.0,$3,0.02,10,2000,1.0,'WATCH',$3,TRUE,$4, \
                     NOW() - INTERVAL '{days_ago} days 2 hours', NOW() - INTERVAL '{days_ago} days')"
        ))
        .bind(strategy)
        .bind(cond)
        .bind(p0)
        .bind(won)
        .execute(&pf.pool)
        .await
        .expect("seed resolved signal");
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn paper_ledger_appends_idempotently_with_stats() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hpled_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM honest_paper_ledger WHERE strategy = 'hp_led'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // 3 resolved signals over 2 days, stake 100, haircut 1¢, fee 2% → entry 0.51.
        //   L1 won  (day -1) pnl = 100×(0.49/0.51 − 0.02) =  +94.078
        //   L2 lost (day -1) pnl = 100×(−0.51/0.51 − 0.02) = −102.000
        //   L3 won  (day  0) pnl =  +94.078
        seed_resolved_dayoffset(&pf, "hp_led", "hpled_1", 0.50, true, 1).await;
        seed_resolved_dayoffset(&pf, "hp_led", "hpled_2", 0.50, false, 1).await;
        seed_resolved_dayoffset(&pf, "hp_led", "hpled_3", 0.50, true, 0).await;

        for c in ["hpled_1", "hpled_2", "hpled_3"] {
            assert!(
                pf.append_paper_bet("hp_led", c, 0, 100.0, 0.01, 0.02)
                    .await
                    .unwrap(),
                "first append writes a ledger row for {c}"
            );
        }
        // Idempotent: re-running resolution appends NOTHING.
        for c in ["hpled_1", "hpled_2", "hpled_3"] {
            assert!(
                !pf.append_paper_bet("hp_led", c, 0, 100.0, 0.01, 0.02)
                    .await
                    .unwrap(),
                "second append is a no-op for {c}"
            );
        }

        let curve = pf.equity_curve("hp_led").await.unwrap();
        assert_eq!(curve.len(), 3, "one curve point per bet");
        // Running equity: +94.078, −7.922, +86.156.
        assert!((curve[0].1 - 94.078).abs() < 0.01);
        assert!((curve[1].1 - (-7.922)).abs() < 0.01);
        assert!((curve[2].1 - 86.156).abs() < 0.01);

        let s = pf
            .ledger_stats("hp_led", 0.02)
            .await
            .unwrap()
            .expect("stats");
        assert_eq!(s.bets, 3);
        assert!((s.total_pnl - 86.156).abs() < 0.01, "final equity");
        assert!(
            s.total_pnl_shares.is_finite() && s.total_pnl_shares != 0.0,
            "flat-shares track computed: {}",
            s.total_pnl_shares
        );
        assert!((s.turnover - 300.0).abs() < 1e-6);
        assert!((s.win_rate - 2.0 / 3.0).abs() < 1e-6);
        // Peak +94.078 then trough −7.922 → max drawdown 102.0.
        assert!((s.max_drawdown - 102.0).abs() < 0.01, "peak-to-trough $");
        // Two distinct days ⇒ a finite Sharpe-like ratio.
        assert!(
            s.sharpe.is_finite() && s.sharpe > 0.0,
            "sharpe {}",
            s.sharpe
        );

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'hpled_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM honest_paper_ledger WHERE strategy = 'hp_led'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!(
            "ledger_it: 3 appends, idempotent re-run, equity/drawdown ${:.1}/${:.1}, sharpe {:.3} — OK",
            s.total_pnl, s.max_drawdown, s.sharpe
        );
    }
}

// Live-DB integration test for the AT-FIRE scoreboard entry (2026-07-02 run):
// the gate must judge on `initial_mean_price` (set once at insert) even when the
// per-cycle upsert has drifted `mean_price` afterwards. Run with:
//
//   DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
//     cargo test -p polymarket-common scoreboard_at_fire -- --ignored --nocapture
#[cfg(test)]
mod scoreboard_at_fire_it {
    use super::*;

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn scoreboard_uses_at_fire_entry_not_drifted_mean() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'af_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // One resolved WON signal whose consensus mean drifted after fire:
        // at-fire entry 0.50, drifted final mean 0.90. The honest advantage is
        // +0.50; judging the drifted mean would report +0.10.
        sqlx::query(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                score, tier, initial_mean_price, resolved, outcome_won, \
                first_detected_at, resolved_at) \
             VALUES ('af_str','af_c1',0,'af_ev1',5,0,5,5.0,0.90,0.02,10,2000,1.0,'WATCH', \
                     0.50,TRUE,TRUE, NOW() - INTERVAL '2 hours', NOW())",
        )
        .execute(&pf.pool)
        .await
        .unwrap();

        let rows = pf
            .consensus_scoreboard_by_strategy()
            .await
            .expect("scoreboard");
        let r = rows
            .iter()
            .find(|r| r.strategy == "af_str")
            .expect("af_str row present");
        let edge = r.edge.expect("edge computed");
        assert!(
            (edge - 0.50).abs() < 1e-9,
            "edge judged at-fire (want +0.50, got {edge:+.4}); drifted mean would give +0.10"
        );

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'af_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!(
            "scoreboard_at_fire_it: edge {edge:+.2} uses initial_mean_price despite drifted mean_price — OK"
        );
    }
}

// Live-DB test for the AT-FIRE consensus-shape capture (slice study, migration 036):
// σ / recency / liquidity / best-rank must be set ONCE at first insert and survive a
// drifted re-upsert untouched, while the current columns keep following the window.
//
//   DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
//     cargo test -p polymarket-common atfire_shape -- --ignored --nocapture
#[cfg(test)]
mod atfire_shape_it {
    use super::*;

    fn sig(price_std: f64, recency: i64, usd: f64, rank: Option<i32>) -> NewConsensusSignal {
        NewConsensusSignal {
            strategy: "afs_str".into(),
            condition_id: "afs_c1".into(),
            outcome_index: 0,
            outcome_label: "Yes".into(),
            title: "AFS test".into(),
            slug: "afs-test".into(),
            event_slug: Some("afs_ev1".into()),
            is_sports: true,
            observed_votes: serde_json::json!([]),
            n_backers: 3,
            n_opposers: 0,
            net_count: 3,
            net_quality: 3.0,
            mean_price: 0.70,
            price_std,
            recency_mins: recency,
            total_usd: usd,
            best_backer_rank: rank,
            score: 1.0,
            tier: "WATCH".into(),
            backers_json: serde_json::json!([]),
        }
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn initial_shape_is_set_once_and_upsert_proof() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id = 'afs_c1'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // Fire: σ 0.03, recency 12m, $1,500, best rank 7 — then a drifted re-upsert.
        pf.upsert_consensus_signal(&sig(0.03, 12, 1500.0, Some(7)))
            .await
            .expect("first upsert");
        pf.upsert_consensus_signal(&sig(0.09, 240, 9000.0, Some(31)))
            .await
            .expect("second upsert");

        let (i_std, i_rec, i_usd, i_rank, c_std, c_rec, c_usd, c_rank): (
            f64,
            i64,
            f64,
            i32,
            f64,
            i64,
            f64,
            i32,
        ) = sqlx::query_as(
            "SELECT initial_price_std, initial_recency_mins, initial_total_usd, \
                    initial_best_backer_rank, price_std, recency_mins, total_usd, \
                    best_backer_rank \
             FROM consensus_signals WHERE condition_id = 'afs_c1'",
        )
        .fetch_one(&pf.pool)
        .await
        .expect("row back");

        assert!(
            (i_std - 0.03).abs() < 1e-9 && i_rec == 12 && (i_usd - 1500.0).abs() < 1e-9,
            "initial shape must keep the AT-FIRE values (got σ {i_std}, rec {i_rec}, usd {i_usd})"
        );
        assert_eq!(i_rank, 7, "initial best rank must keep the at-fire value");
        assert!(
            (c_std - 0.09).abs() < 1e-9 && c_rec == 240 && (c_usd - 9000.0).abs() < 1e-9,
            "current shape must follow the drifted window"
        );
        assert_eq!(
            c_rank, 31,
            "current best rank must follow the drifted window"
        );

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id = 'afs_c1'")
            .execute(&pf.pool)
            .await
            .unwrap();
        println!(
            "atfire_shape_it: initial σ/recency/usd/rank {i_std}/{i_rec}/{i_usd}/{i_rank} \
             survived a drifted re-upsert ({c_std}/{c_rec}/{c_usd}/{c_rank}) — OK"
        );
    }
}

// Live-DB test for the dense-capture storage path (decay run Phase 0): fresh
// signals are candidates (deduped per (cond, outcome), earliest anchor), stale/
// resolved ones aren't, points insert, and the FK cascade removes them.
//
//   DATABASE_URL=postgres://bot:bot@localhost:55499/polymarket \
//     cargo test -p polymarket-common dense_capture -- --ignored --nocapture
#[cfg(test)]
mod dense_capture_it {
    use super::*;

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn candidates_dedupe_insert_and_cascade() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'dc_%'")
            .execute(&pf.pool)
            .await
            .unwrap();

        // Two strategies fire the SAME (cond, outcome) — favorite first (the
        // anchor); one stale strict fire outside the window; one resolved row.
        let seed = |strategy: &str, cond: &str, mins_ago: i32, resolved: bool| {
            let q = format!(
                "INSERT INTO consensus_signals \
                   (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                    net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                    score, tier, resolved, outcome_won, first_detected_at) \
                 VALUES ($1, $2, 0, 'dc_ev', 3, 0, 3, 3.0, 0.9, 0.02, 5, 1000, 1.0, 'WATCH', \
                         $3, CASE WHEN $3 THEN TRUE ELSE NULL END, \
                         NOW() - make_interval(mins => {mins_ago}))"
            );
            let pool = pf.pool.clone();
            let (s, c) = (strategy.to_string(), cond.to_string());
            async move {
                sqlx::query(&q)
                    .bind(s)
                    .bind(c)
                    .bind(resolved)
                    .execute(&pool)
                    .await
                    .unwrap();
            }
        };
        seed("favorite", "dc_c1", 5, false).await; // anchor (earliest = 5 min ago)
        seed("elite_fresh_fav", "dc_c1", 3, false).await; // same pair, later
        seed("strict", "dc_c2", 60, false).await; // outside 15-min window
        seed("favorite", "dc_c3", 2, true).await; // resolved — ineligible

        let strategies: Vec<String> = ["strict", "favorite", "elite_fresh_fav"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let cands = pf
            .dense_capture_candidates(&strategies, 15, 40)
            .await
            .expect("candidates");
        let dc: Vec<_> = cands
            .iter()
            .filter(|c| c.condition_id.starts_with("dc_"))
            .collect();
        assert_eq!(dc.len(), 1, "one fresh unresolved pair, deduped: {dc:?}");
        assert_eq!(dc[0].condition_id, "dc_c1");

        // Insert a point; verify; then cascade-delete via the parent signal.
        pf.insert_trajectory_point(dc[0].signal_id, 300, Some(0.91), Some(0.93), Some(3))
            .await
            .expect("insert point");
        let (n,): (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM signal_price_trajectory WHERE signal_id = $1")
                .bind(dc[0].signal_id)
                .fetch_one(&pf.pool)
                .await
                .unwrap();
        assert_eq!(n, 1, "trajectory point landed");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'dc_%'")
            .execute(&pf.pool)
            .await
            .unwrap();
        let (n2,): (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM signal_price_trajectory WHERE signal_id = $1")
                .bind(dc[0].signal_id)
                .fetch_one(&pf.pool)
                .await
                .unwrap();
        assert_eq!(n2, 0, "FK cascade removed the trajectory");
        println!("dense_capture_it: candidates dedupe + insert + cascade — OK");
    }
}
