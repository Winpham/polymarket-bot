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
    pub ts: DateTime<Utc>,
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
}

impl PgPortfolio {
    // --- Tracked-trader universe (auto-follow) ---

    /// Upsert one leaderboard trader, marking it active and seen-now.
    /// Does not clobber a manually-followed row's `source`.
    pub async fn upsert_tracked_trader(&self, t: &LeaderboardTraderUpsert) -> Result<()> {
        sqlx::query(
            "INSERT INTO followed_traders \
               (proxy_wallet, username, source, rank, pnl, volume, periods, \
                active, last_seen_on_lb) \
             VALUES ($1, $2, 'leaderboard', $3, $4, $5, $6, TRUE, NOW()) \
             ON CONFLICT (proxy_wallet) DO UPDATE SET \
               username        = COALESCE(EXCLUDED.username, followed_traders.username), \
               rank            = EXCLUDED.rank, \
               pnl             = EXCLUDED.pnl, \
               volume          = EXCLUDED.volume, \
               periods         = EXCLUDED.periods, \
               active          = TRUE, \
               last_seen_on_lb = NOW()",
        )
        .bind(&t.wallet)
        .bind(&t.username)
        .bind(t.rank)
        .bind(t.pnl)
        .bind(t.volume)
        .bind(&t.periods)
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
                backers, initial_n_backers, initial_net_count, initial_mean_price, last_updated_at) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21, \
                     $10,$12,$14,NOW()) \
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
                    mean_price, net_count, n_backers, is_sports \
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
    pub async fn snapshot_consensus_signal(
        &self,
        signal_id: i32,
        net_count: i32,
        n_backers: i32,
        mean_entry: f64,
        market_price: Option<f64>,
    ) -> Result<()> {
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

        // Latest price always; initial price only the first time we see one.
        if let Some(price) = market_price {
            sqlx::query(
                "UPDATE consensus_signals \
                 SET last_market_price = $2, \
                     initial_market_price = COALESCE(initial_market_price, $2) \
                 WHERE id = $1",
            )
            .bind(signal_id)
            .bind(price)
            .execute(&self.pool)
            .await
            .context("snapshot_consensus_signal (price)")?;
        }
        Ok(())
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
    /// instrument that ranks the portfolio: `edge = AVG(outcome_won − mean_price)`
    /// is the leak-free realized edge vs the price each signal entered at.
    pub async fn consensus_scoreboard_by_strategy(&self) -> Result<Vec<StrategyScore>> {
        // The denominator (catalog #1). For each resolved signal, advantage
        // `a = outcome_won - mean_price`. The `_blind` arm captures EVERY observed
        // outcome, so its per-price-band average `a` is the blind baseline that
        // favorite-longshot bias would already earn. A strategy's SURPLUS =
        // AVG(a - blind_edge[band]) is what it adds beyond blindly betting that
        // band — the only edge number that isn't gamed by loading favorites.
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
        // we saw; `capture_lag = AVG_event(initial_market_price − mean_price)` is
        // the gap between the mid when we *noticed* and the price the sharps paid.
        // A materially negative `capture_lag` means faster polling has real value.
        let rows: Vec<StrategyScore> = sqlx::query_as(
            "WITH adv AS ( \
                 SELECT strategy, COALESCE(event_slug, condition_id) AS ev, resolved, outcome_won, \
                        width_bucket(mean_price, 0.0, 1.0, 5) AS band, \
                        (outcome_won::int)::double precision - mean_price AS a \
                 FROM consensus_signals \
             ), \
             blind AS ( \
                 SELECT band, AVG(a) AS blind_edge \
                 FROM adv WHERE strategy = '_blind' AND resolved GROUP BY band \
             ), \
             sig AS ( \
                 SELECT v.strategy, v.ev, v.resolved, v.outcome_won, v.a, \
                        v.a - COALESCE(b.blind_edge, 0) AS surplus \
                 FROM adv v LEFT JOIN blind b USING (band) WHERE v.strategy <> '_blind' \
             ), \
             evt AS ( \
                 SELECT strategy, ev, AVG(surplus) AS ev_surplus \
                 FROM sig WHERE resolved GROUP BY strategy, ev \
             ), \
             es AS ( \
                 SELECT strategy, COUNT(*) AS n_events, AVG(ev_surplus) AS surplus, \
                        STDDEV_SAMP(ev_surplus) AS surplus_sd FROM evt GROUP BY strategy \
             ), \
             clv_evt AS ( \
                 SELECT strategy, COALESCE(event_slug, condition_id) AS ev, \
                        AVG((outcome_won::int)::double precision - initial_market_price) AS ev_clv, \
                        AVG(initial_market_price - mean_price) AS ev_lag \
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
                    COUNT(*) FILTER (WHERE s.resolved AND s.outcome_won) AS won, \
                    AVG(s.a) FILTER (WHERE s.resolved)                   AS edge, \
                    es.surplus                                          AS surplus, \
                    es.surplus_sd                                       AS surplus_sd, \
                    clv.our_clv                                         AS our_clv, \
                    clv.capture_lag                                     AS capture_lag \
             FROM sig s LEFT JOIN es ON es.strategy = s.strategy \
                        LEFT JOIN clv ON clv.strategy = s.strategy \
             GROUP BY s.strategy, es.n_events, es.surplus, es.surplus_sd, clv.our_clv, clv.capture_lag \
             ORDER BY es.surplus DESC NULLS LAST",
        )
        .fetch_all(&self.pool)
        .await
        .context("consensus_scoreboard_by_strategy")?;
        Ok(rows)
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

    /// Load all window fill atoms at or after `since` (the trailing window) for
    /// rebuilding MarketBooks off the indexed DB read instead of the network.
    pub async fn load_window_votes(&self, since: DateTime<Utc>) -> Result<Vec<WindowVote>> {
        let rows: Vec<WindowVote> = sqlx::query_as(
            "SELECT trader_wallet, name, rank, pnl, quality, condition_id, outcome_index, \
                    outcome, title, slug, event_slug, is_sports, price, size_usd, ts \
             FROM consensus_vote_window WHERE ts >= $1",
        )
        .bind(since)
        .fetch_all(&self.pool)
        .await
        .context("load_window_votes")?;
        Ok(rows)
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
        let ts: Vec<DateTime<Utc>> = fills.iter().map(|f| f.ts).collect();

        let res = sqlx::query(
            "INSERT INTO trader_fills \
               (wallet, tx_hash, condition_id, outcome_index, outcome, side, price, \
                size_usd, title, slug, event_slug, is_sports, sport, ts) \
             SELECT * FROM UNNEST( \
               $1::text[], $2::text[], $3::text[], $4::int4[], $5::text[], $6::text[], \
               $7::float8[], $8::float8[], $9::text[], $10::text[], $11::text[], \
               $12::bool[], $13::text[], $14::timestamptz[]) \
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
        .bind(&ts)
        .execute(&self.pool)
        .await
        .context("insert_trader_fills")?;
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
             WHERE tf.side = 'BUY' AND tf.ts >= $1",
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
    /// Slices: `overall`, `sport`, `band` (b1..b5), `recency7d`, `recency30d`.
    pub async fn trader_slice_scores(&self) -> Result<Vec<TraderSliceStat>> {
        let rows: Vec<TraderSliceStat> = sqlx::query_as(
            "WITH adv AS ( \
                 SELECT wallet, COALESCE(event_slug, condition_id) AS ev, \
                        width_bucket(price, 0.0, 1.0, 5) AS band, \
                        (outcome_won::int)::double precision - price AS a, \
                        (outcome_won::int)::double precision AS won, \
                        COALESCE(sport, 'other') AS sport, ts \
                 FROM trader_fills \
                 WHERE resolved AND side = 'BUY' AND outcome_won IS NOT NULL \
             ), \
             blind AS ( SELECT band, AVG(a) AS blind_edge FROM adv GROUP BY band ), \
             surp AS ( SELECT v.wallet, v.ev, v.band, v.a, v.won, v.sport, v.ts, \
                              v.a - COALESCE(b.blind_edge, 0) AS s \
                       FROM adv v LEFT JOIN blind b USING (band) ), \
             tagged AS ( \
                 SELECT wallet, 'overall'::text AS slice_kind, ''::text AS slice_key, ev, a, s, won FROM surp \
                 UNION ALL \
                 SELECT wallet, 'sport', sport, ev, a, s, won FROM surp \
                 UNION ALL \
                 SELECT wallet, 'band', 'b' || band::text, ev, a, s, won FROM surp \
                 UNION ALL \
                 SELECT wallet, 'recency7d', '7d', ev, a, s, won FROM surp \
                   WHERE ts >= NOW() - INTERVAL '7 days' \
                 UNION ALL \
                 SELECT wallet, 'recency30d', '30d', ev, a, s, won FROM surp \
                   WHERE ts >= NOW() - INTERVAL '30 days' \
             ), \
             evl AS ( \
                 SELECT wallet, slice_kind, slice_key, ev, \
                        AVG(s) AS ev_surplus, AVG(a) AS ev_adv, AVG(won) AS ev_hit, \
                        COUNT(*) AS ev_rows \
                 FROM tagged GROUP BY wallet, slice_kind, slice_key, ev \
             ) \
             SELECT wallet, slice_kind, slice_key, \
                    COUNT(DISTINCT ev)        AS n_events, \
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
    /// Resolved signals whose consensus outcome won.
    pub won: i64,
    /// Mean realized edge vs entry: `AVG(outcome_won::int - mean_price)`.
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

/// One (wallet × slice) earned-trust statistic over resolved BUY fills. Numbers
/// only — the verdict (gate reuse) is computed in the binary's
/// `scanner::trader_trust`. Surplus + sd are EVENT-clustered; `n_events` is the
/// gate's N. Mirrors [`StrategyScore`]'s shape for the wallet-keyed scoreboard.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct TraderSliceStat {
    pub wallet: String,
    /// 'overall' | 'sport' | 'band' | 'recency7d' | 'recency30d'.
    pub slice_kind: String,
    /// '' | 'nba' | 'b3' | '7d' …
    pub slice_key: String,
    /// Distinct `COALESCE(event_slug, condition_id)` — the gate's de-correlated N.
    pub n_events: i64,
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
            ts: Utc::now() - chrono::Duration::hours(1),
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
