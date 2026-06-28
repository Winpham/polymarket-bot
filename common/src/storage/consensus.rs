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
    pub condition_id: String,
    pub outcome_index: i32,
    pub outcome_label: String,
    pub title: String,
    pub slug: String,
    pub event_slug: Option<String>,
    pub is_sports: bool,
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

/// Prior alert state of a signal (captured at upsert time, before any new alert).
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct ConsensusAlertState {
    pub id: i32,
    pub last_alert_tier: Option<String>,
    pub last_alert_net: Option<i32>,
}

/// A signal awaiting market resolution (forward edge tracking).
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct UnresolvedConsensus {
    pub id: i32,
    pub slug: String,
    pub outcome_index: i32,
    pub mean_price: f64,
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
               (condition_id, outcome_index, outcome_label, title, slug, event_slug, \
                is_sports, n_backers, n_opposers, net_count, net_quality, mean_price, \
                price_std, recency_mins, total_usd, best_backer_rank, score, tier, \
                backers, last_updated_at) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,NOW()) \
             ON CONFLICT (condition_id, outcome_index) DO UPDATE SET \
               outcome_label    = EXCLUDED.outcome_label, \
               title            = EXCLUDED.title, \
               slug             = EXCLUDED.slug, \
               event_slug       = EXCLUDED.event_slug, \
               is_sports        = EXCLUDED.is_sports, \
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
        .bind(&s.condition_id)
        .bind(s.outcome_index)
        .bind(&s.outcome_label)
        .bind(&s.title)
        .bind(&s.slug)
        .bind(&s.event_slug)
        .bind(s.is_sports)
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
            "INSERT INTO consensus_alerts (signal_id, tier, net_count, score) \
             VALUES ($1, $2, $3, $4)",
        )
        .bind(signal_id)
        .bind(tier)
        .bind(net_count)
        .bind(score)
        .execute(&self.pool)
        .await
        .context("record_consensus_alert (insert log)")?;
        Ok(())
    }

    /// Build a `/consensus` summary of the most recent strong/elite signals.
    pub async fn consensus_summary(&self, limit: i64) -> Result<String> {
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
             WHERE tier IN ('STRONG','ELITE') \
               AND last_updated_at > NOW() - INTERVAL '24 hours' \
             ORDER BY score DESC LIMIT $1",
        )
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
            "SELECT id, COALESCE(slug, '') AS slug, outcome_index, mean_price \
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
