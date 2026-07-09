//! Execution-policy shadow ledger (PAPER-ONLY, prereg 2026-07-09T02:05Z).
//!
//! The champion's honest ROI is measured at entries captured ~10-20 min after
//! fire (housekeeping cadence) — implicitly a PATIENT-taker number. The live
//! tape shows the executable ask decaying from ~mid+3.4¢ at fire to ~mid at
//! +30 min on `favorite` (outcome-blind structural read). This module freezes,
//! per signal, the three frozen execution policies and books them side by side
//! into `honest_paper_ledger` so the existing honest-P&L machinery judges them:
//!
//! - `exec_fire:<strat>`  — taker at the fire-time ask (what a naive copier pays)
//! - `exec_p15:<strat>`   — taker at the ask 15 min after fire (the ledger's implicit policy)
//! - `exec_mrest:<strat>` — resting maker BUY at fire-time mid, cancel 30 min,
//!   filled only on a REALISTIC print (`price_change` at `last_price ≤ limit`
//!   with size); quote-flicker touch is recorded but NEVER booked. Unfilled ⇒
//!   abstain (no ledger row; the abstention stays visible in
//!   `exec_policy_entries.maker_print = false`).
//!
//! Clock discipline: every tape lookup orders by `recv_at` (never `exch_ts` —
//! the D1-E tape-clock lesson). No look-ahead: the fire-time quote may not read
//! any tape row with `recv_at > fired_at`. All writes are additive; with
//! `EXEC_POLICY_SHADOW=false` (default) nothing here runs.

use anyhow::{Context, Result};
use chrono::{DateTime, Duration, Utc};

use super::postgres::PgPortfolio;

/// Evaluate a signal only once its maker window is complete (35 min > 30 min
/// cancel) — no partially-observed windows.
pub const EXEC_EVAL_MIN_AGE_SECS: f64 = 35.0 * 60.0;
/// Never evaluate signals older than this: the tape retains ~72 h; 60 h leaves
/// slack so a lookup never silently reads a pruned (biased) window.
pub const EXEC_EVAL_MAX_AGE_SECS: f64 = 60.0 * 3600.0;
/// A quote is usable only if the last tape inflection is at most this stale.
pub const EXEC_QUOTE_MAX_STALE_SECS: f64 = 900.0;
/// Patient-taker delay (frozen policy P-P15).
pub const EXEC_PATIENT_DELAY_SECS: i64 = 15 * 60;
/// Resting maker cancel-after (frozen policy P-MREST).
pub const EXEC_MAKER_CANCEL_SECS: i64 = 30 * 60;

/// A flagged-strategy signal that has no `exec_policy_entries` row yet and
/// whose evaluation window is complete.
#[derive(Debug, sqlx::FromRow)]
pub struct ExecPolicyPending {
    pub signal_id: i64,
    pub strategy: String,
    pub condition_id: String,
    pub outcome_index: i32,
    pub fired_at: DateTime<Utc>,
}

/// Top-of-book read from the tape at (or just before) a moment in time.
#[derive(Debug, sqlx::FromRow)]
pub struct TapeQuote {
    pub best_bid: Option<f64>,
    pub best_ask: f64,
    pub recv_at: DateTime<Utc>,
}

/// The frozen per-signal policy entries, written exactly once.
#[derive(Debug)]
pub struct NewExecPolicyEntry {
    pub signal_id: i64,
    pub strategy: String,
    pub condition_id: String,
    pub outcome_index: i32,
    pub fired_at: DateTime<Utc>,
    pub bid_fire: Option<f64>,
    pub ask_fire: Option<f64>,
    pub mid_fire: Option<f64>,
    pub tape_at_fire: Option<DateTime<Utc>>,
    pub ask_p15: Option<f64>,
    pub maker_touch: bool,
    pub maker_print: bool,
    pub maker_fill_at: Option<DateTime<Utc>>,
}

/// An evaluated entry whose signal has resolved and whose policy bets are not
/// yet booked into the paper ledger.
#[derive(Debug, sqlx::FromRow)]
pub struct ExecPolicyBooking {
    pub signal_id: i64,
    pub strategy: String,
    pub condition_id: String,
    pub outcome_index: i32,
    pub ask_fire: Option<f64>,
    pub ask_p15: Option<f64>,
    pub mid_fire: Option<f64>,
    pub maker_print: bool,
    pub outcome_won: bool,
}

impl PgPortfolio {
    /// Flagged-strategy signals awaiting a one-shot policy evaluation: fired
    /// long enough ago that every policy window is complete, recent enough
    /// that the tape window is guaranteed un-pruned, and not yet evaluated.
    pub async fn exec_policy_pending(
        &self,
        strategies: &[String],
        limit: i64,
    ) -> Result<Vec<ExecPolicyPending>> {
        let rows: Vec<ExecPolicyPending> = sqlx::query_as(
            "SELECT s.id::bigint AS signal_id, s.strategy, s.condition_id, \
                    s.outcome_index, s.first_detected_at AS fired_at \
             FROM consensus_signals s \
             LEFT JOIN exec_policy_entries e ON e.signal_id = s.id \
             WHERE e.signal_id IS NULL \
               AND s.strategy = ANY($1) \
               AND s.condition_id IS NOT NULL \
               AND s.first_detected_at <= NOW() - make_interval(secs => $2) \
               AND s.first_detected_at >  NOW() - make_interval(secs => $3) \
             ORDER BY s.first_detected_at \
             LIMIT $4",
        )
        .bind(strategies)
        .bind(EXEC_EVAL_MIN_AGE_SECS)
        .bind(EXEC_EVAL_MAX_AGE_SECS)
        .bind(limit)
        .fetch_all(&self.pool)
        .await
        .context("exec_policy_pending")?;
        Ok(rows)
    }

    /// Last tape inflection for a leg at `recv_at ≤ at`, no staler than
    /// `max_stale_secs`. No look-ahead by construction; `recv_at` ordering only.
    pub async fn tape_quote_at(
        &self,
        condition_id: &str,
        outcome_index: i32,
        at: DateTime<Utc>,
        max_stale_secs: f64,
    ) -> Result<Option<TapeQuote>> {
        let row: Option<TapeQuote> = sqlx::query_as(
            "SELECT best_bid, best_ask, recv_at \
             FROM clob_price_tape \
             WHERE condition_id = $1 AND outcome_index = $2 \
               AND recv_at <= $3 \
               AND recv_at >= $3 - make_interval(secs => $4) \
               AND best_ask IS NOT NULL AND best_ask > 0 AND best_ask < 1 \
             ORDER BY recv_at DESC \
             LIMIT 1",
        )
        .bind(condition_id)
        .bind(outcome_index)
        .bind(at)
        .bind(max_stale_secs)
        .fetch_optional(&self.pool)
        .await
        .context("tape_quote_at")?;
        Ok(row)
    }

    /// Would a resting BUY at `limit_price` have filled in `[from, to]`?
    /// Returns `(first_print_at, first_touch_at)`:
    /// - print (REALISTIC, the only one ever booked): a `price_change` row
    ///   trading at `last_price ≤ limit` with real size — flow actually crossed.
    /// - touch (OPTIMISTIC bound): `best_ask ≤ limit` at any row — a quote
    ///   flicker that assumes 100% queue capture.
    pub async fn tape_maker_fill(
        &self,
        condition_id: &str,
        outcome_index: i32,
        from: DateTime<Utc>,
        to: DateTime<Utc>,
        limit_price: f64,
    ) -> Result<(Option<DateTime<Utc>>, Option<DateTime<Utc>>)> {
        let (print_at, touch_at): (Option<DateTime<Utc>>, Option<DateTime<Utc>>) = sqlx::query_as(
            "SELECT \
                   MIN(recv_at) FILTER (WHERE event_type = 'price_change' \
                       AND last_price IS NOT NULL AND last_price > 0 \
                       AND last_price <= $5 AND COALESCE(last_size, 0) > 0) AS print_at, \
                   MIN(recv_at) FILTER (WHERE best_ask IS NOT NULL \
                       AND best_ask > 0 AND best_ask <= $5) AS touch_at \
                 FROM clob_price_tape \
                 WHERE condition_id = $1 AND outcome_index = $2 \
                   AND recv_at >= $3 AND recv_at <= $4",
        )
        .bind(condition_id)
        .bind(outcome_index)
        .bind(from)
        .bind(to)
        .bind(limit_price)
        .fetch_one(&self.pool)
        .await
        .context("tape_maker_fill")?;
        Ok((print_at, touch_at))
    }

    /// Freeze a signal's policy entries. Set-once (`ON CONFLICT DO NOTHING`);
    /// returns whether a row was written.
    pub async fn insert_exec_policy_entry(&self, e: &NewExecPolicyEntry) -> Result<bool> {
        let res = sqlx::query(
            "INSERT INTO exec_policy_entries \
                 (signal_id, strategy, condition_id, outcome_index, fired_at, \
                  bid_fire, ask_fire, mid_fire, tape_at_fire, ask_p15, \
                  maker_touch, maker_print, maker_fill_at) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) \
             ON CONFLICT (signal_id) DO NOTHING",
        )
        .bind(e.signal_id)
        .bind(&e.strategy)
        .bind(&e.condition_id)
        .bind(e.outcome_index)
        .bind(e.fired_at)
        .bind(e.bid_fire)
        .bind(e.ask_fire)
        .bind(e.mid_fire)
        .bind(e.tape_at_fire)
        .bind(e.ask_p15)
        .bind(e.maker_touch)
        .bind(e.maker_print)
        .bind(e.maker_fill_at)
        .execute(&self.pool)
        .await
        .context("insert_exec_policy_entry")?;
        Ok(res.rows_affected() > 0)
    }

    /// Evaluated entries whose signal has since resolved but whose policy bets
    /// are not yet in the paper ledger.
    pub async fn exec_policy_unbooked_resolved(
        &self,
        limit: i64,
    ) -> Result<Vec<ExecPolicyBooking>> {
        let rows: Vec<ExecPolicyBooking> = sqlx::query_as(
            "SELECT e.signal_id, e.strategy, e.condition_id, e.outcome_index, \
                    e.ask_fire, e.ask_p15, e.mid_fire, e.maker_print, s.outcome_won \
             FROM exec_policy_entries e \
             JOIN consensus_signals s ON s.id = e.signal_id \
             WHERE NOT e.booked AND s.resolved AND s.outcome_won IS NOT NULL \
             ORDER BY e.signal_id \
             LIMIT $1",
        )
        .bind(limit)
        .fetch_all(&self.pool)
        .await
        .context("exec_policy_unbooked_resolved")?;
        Ok(rows)
    }

    /// Append one PAPER ledger bet at an EXPLICIT entry price (the policy
    /// arms' entries are frozen in `exec_policy_entries`, not derived from the
    /// signal row like `append_paper_bet`). Same idempotency contract:
    /// `ON CONFLICT (strategy, condition_id, outcome_index) DO NOTHING`.
    /// Entries outside (0, 1) are refused. PAPER only — never places money.
    #[allow(clippy::too_many_arguments)]
    pub async fn append_paper_bet_at(
        &self,
        strategy_label: &str,
        condition_id: &str,
        outcome_index: i32,
        stake: f64,
        entry: f64,
        outcome_won: bool,
        fee_pct: f64,
    ) -> Result<bool> {
        if !(entry > 0.0 && entry < 1.0) {
            return Ok(false);
        }
        let res = sqlx::query(
            "INSERT INTO honest_paper_ledger \
                 (strategy, condition_id, outcome_index, resolved_at, stake, entry, \
                  outcome_won, pnl, cum_equity) \
             SELECT $1, $2, $3, NOW(), $4, $5, $6, \
                    $4 * ((($6::int)::double precision - $5) / NULLIF($5, 0) - $7), \
                    COALESCE((SELECT SUM(pnl) FROM honest_paper_ledger WHERE strategy = $1), 0) \
                      + $4 * ((($6::int)::double precision - $5) / NULLIF($5, 0) - $7) \
             ON CONFLICT (strategy, condition_id, outcome_index) DO NOTHING",
        )
        .bind(strategy_label)
        .bind(condition_id)
        .bind(outcome_index)
        .bind(stake)
        .bind(entry)
        .bind(outcome_won)
        .bind(fee_pct)
        .execute(&self.pool)
        .await
        .context("append_paper_bet_at")?;
        Ok(res.rows_affected() > 0)
    }

    /// Mark an entry's policy bets booked (kept out of the pending scan).
    pub async fn mark_exec_policy_booked(&self, signal_id: i64) -> Result<()> {
        sqlx::query("UPDATE exec_policy_entries SET booked = TRUE WHERE signal_id = $1")
            .bind(signal_id)
            .execute(&self.pool)
            .await
            .context("mark_exec_policy_booked")?;
        Ok(())
    }

    /// Evaluate ONE pending signal against the tape: freeze the fire-time
    /// book, the patient ask, and the maker fill verdict. Pure measurement —
    /// reads the tape, writes only `exec_policy_entries`.
    pub async fn evaluate_exec_policy(&self, p: &ExecPolicyPending) -> Result<bool> {
        let fire = self
            .tape_quote_at(
                &p.condition_id,
                p.outcome_index,
                p.fired_at,
                EXEC_QUOTE_MAX_STALE_SECS,
            )
            .await?;
        let patient_at = p.fired_at + Duration::seconds(EXEC_PATIENT_DELAY_SECS);
        let p15 = self
            .tape_quote_at(
                &p.condition_id,
                p.outcome_index,
                patient_at,
                EXEC_QUOTE_MAX_STALE_SECS,
            )
            .await?;

        // The maker limit needs BOTH sides of the fire-time book for a mid.
        let (bid_fire, ask_fire, tape_at_fire) = match &fire {
            Some(q) => (q.best_bid, Some(q.best_ask), Some(q.recv_at)),
            None => (None, None, None),
        };
        let mid_fire = match (bid_fire, ask_fire) {
            (Some(b), Some(a)) if b > 0.0 && a > b => Some((b + a) / 2.0),
            _ => None,
        };
        let (maker_print_at, maker_touch_at) = match mid_fire {
            Some(limit) => {
                let cancel_at = p.fired_at + Duration::seconds(EXEC_MAKER_CANCEL_SECS);
                self.tape_maker_fill(
                    &p.condition_id,
                    p.outcome_index,
                    p.fired_at,
                    cancel_at,
                    limit,
                )
                .await?
            }
            None => (None, None),
        };

        self.insert_exec_policy_entry(&NewExecPolicyEntry {
            signal_id: p.signal_id,
            strategy: p.strategy.clone(),
            condition_id: p.condition_id.clone(),
            outcome_index: p.outcome_index,
            fired_at: p.fired_at,
            bid_fire,
            ask_fire,
            mid_fire,
            tape_at_fire,
            ask_p15: p15.map(|q| q.best_ask),
            maker_touch: maker_touch_at.is_some(),
            maker_print: maker_print_at.is_some(),
            maker_fill_at: maker_print_at,
        })
        .await
    }

    /// Book one resolved entry's policy bets into the paper ledger, then mark
    /// it booked. An arm with no frozen entry (no tape coverage / maker
    /// abstained) books nothing — the gap stays visible in
    /// `exec_policy_entries`. Idempotent end to end.
    pub async fn book_exec_policy_entry(
        &self,
        b: &ExecPolicyBooking,
        stake: f64,
        fee_pct: f64,
    ) -> Result<usize> {
        let mut booked = 0usize;
        if let Some(ask) = b.ask_fire {
            let label = format!("exec_fire:{}", b.strategy);
            if self
                .append_paper_bet_at(
                    &label,
                    &b.condition_id,
                    b.outcome_index,
                    stake,
                    ask,
                    b.outcome_won,
                    fee_pct,
                )
                .await?
            {
                booked += 1;
            }
        }
        if let Some(ask) = b.ask_p15 {
            let label = format!("exec_p15:{}", b.strategy);
            if self
                .append_paper_bet_at(
                    &label,
                    &b.condition_id,
                    b.outcome_index,
                    stake,
                    ask,
                    b.outcome_won,
                    fee_pct,
                )
                .await?
            {
                booked += 1;
            }
        }
        // Maker: booked ONLY on a realistic print; fee 0 (makers pay zero, no
        // rebate modeled — conservative).
        if b.maker_print
            && let Some(mid) = b.mid_fire
        {
            let label = format!("exec_mrest:{}", b.strategy);
            if self
                .append_paper_bet_at(
                    &label,
                    &b.condition_id,
                    b.outcome_index,
                    stake,
                    mid,
                    b.outcome_won,
                    0.0,
                )
                .await?
            {
                booked += 1;
            }
        }
        self.mark_exec_policy_booked(b.signal_id).await?;
        Ok(booked)
    }
}

#[cfg(test)]
mod tests {
    //! DB integration tests (repo pattern): need a live Postgres with
    //! migrations applied, e.g.
    //! DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
    //!   cargo test -p polymarket-common exec_policy -- --ignored --test-threads=1
    //! Every fixture row uses the `ep_` / `epc_` prefix; cleanup deletes ONLY
    //! those rows (code-enforced test-data guard style).

    use super::*;
    use chrono::Duration;

    async fn pf() -> PgPortfolio {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
        let pool = sqlx::PgPool::connect(&url).await.expect("connect");
        let pf = PgPortfolio::new(pool).await.expect("portfolio");
        pf.run_migrations().await.expect("migrations");
        pf
    }

    async fn clean(pf: &PgPortfolio) {
        for q in [
            "DELETE FROM clob_price_tape WHERE condition_id LIKE 'epc_%'",
            "DELETE FROM exec_policy_entries WHERE condition_id LIKE 'epc_%'",
            "DELETE FROM honest_paper_ledger WHERE condition_id LIKE 'epc_%'",
            "DELETE FROM consensus_signals WHERE condition_id LIKE 'epc_%'",
        ] {
            sqlx::query(q).execute(&pf.pool).await.unwrap();
        }
    }

    #[allow(clippy::too_many_arguments)]
    async fn tape_row(
        pf: &PgPortfolio,
        cond: &str,
        event_type: &str,
        best_bid: Option<f64>,
        best_ask: Option<f64>,
        last_price: Option<f64>,
        last_size: Option<f64>,
        recv_at: DateTime<Utc>,
    ) {
        sqlx::query(
            "INSERT INTO clob_price_tape \
               (asset_id, condition_id, outcome_index, event_type, best_bid, best_ask, \
                last_price, last_size, recv_at) \
             VALUES ('ep_asset', $1, 0, $2, $3, $4, $5, $6, $7)",
        )
        .bind(cond)
        .bind(event_type)
        .bind(best_bid)
        .bind(best_ask)
        .bind(last_price)
        .bind(last_size)
        .bind(recv_at)
        .execute(&pf.pool)
        .await
        .unwrap();
    }

    async fn signal(pf: &PgPortfolio, cond: &str, strategy: &str, fired_at: DateTime<Utc>) -> i64 {
        let (id,): (i32,) = sqlx::query_as(
            "INSERT INTO consensus_signals \
               (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                score, tier, initial_market_price, resolved, first_detected_at) \
             VALUES ($1, $2, 0, $2, 4, 0, 4, 4.0, 0.80, 0.02, 10, 2000, 1.0, 'WATCH', \
                     0.80, FALSE, $3) RETURNING id",
        )
        .bind(strategy)
        .bind(cond)
        .bind(fired_at)
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        id as i64
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn quote_at_no_lookahead_and_staleness() {
        let pf = pf().await;
        clean(&pf).await;
        let t = Utc::now() - Duration::hours(1);
        // Stale row (20 min before), fresh row (10 s before), FUTURE row (5 s after).
        tape_row(
            &pf,
            "epc_q",
            "book",
            Some(0.78),
            Some(0.90),
            None,
            None,
            t - Duration::minutes(20),
        )
        .await;
        tape_row(
            &pf,
            "epc_q",
            "book",
            Some(0.78),
            Some(0.83),
            None,
            None,
            t - Duration::seconds(10),
        )
        .await;
        tape_row(
            &pf,
            "epc_q",
            "book",
            Some(0.78),
            Some(0.70),
            None,
            None,
            t + Duration::seconds(5),
        )
        .await;

        // The fresh pre-fire row wins; the cheaper FUTURE ask must never leak in.
        let q = pf
            .tape_quote_at("epc_q", 0, t, 900.0)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            q.best_ask, 0.83,
            "no look-ahead: pre-fire row, not the future one"
        );

        // With a 5 s staleness budget nothing qualifies at t (row is 10 s old).
        let none = pf.tape_quote_at("epc_q", 0, t, 5.0).await.unwrap();
        assert!(
            none.is_none(),
            "stale quotes are refused, not silently used"
        );
        clean(&pf).await;
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn maker_fill_print_vs_touch() {
        let pf = pf().await;
        clean(&pf).await;
        let t = Utc::now() - Duration::hours(2);
        let limit = 0.80;
        // A quote flicker touches the limit (best_ask 0.79) but NO print.
        tape_row(
            &pf,
            "epc_m",
            "book",
            Some(0.77),
            Some(0.79),
            None,
            None,
            t + Duration::minutes(2),
        )
        .await;
        // A real print at/below the limit 8 minutes in.
        tape_row(
            &pf,
            "epc_m",
            "price_change",
            Some(0.77),
            Some(0.82),
            Some(0.80),
            Some(50.0),
            t + Duration::minutes(8),
        )
        .await;
        // A print AFTER the cancel window must not count.
        tape_row(
            &pf,
            "epc_m",
            "price_change",
            Some(0.70),
            Some(0.75),
            Some(0.70),
            Some(50.0),
            t + Duration::minutes(40),
        )
        .await;

        let (print_at, touch_at) = pf
            .tape_maker_fill(
                "epc_m",
                0,
                t,
                t + Duration::seconds(EXEC_MAKER_CANCEL_SECS),
                limit,
            )
            .await
            .unwrap();
        let touch = touch_at.expect("flicker touch recorded");
        let print = print_at.expect("real print recorded");
        assert!(touch < print, "touch (2 min) precedes print (8 min)");
        assert!(
            (print - t).num_minutes() == 8,
            "the post-cancel print is excluded; fill is the in-window print"
        );

        // Size-less print (quote-derived last_price with no size) is NOT a fill.
        clean(&pf).await;
        tape_row(
            &pf,
            "epc_m",
            "price_change",
            Some(0.77),
            Some(0.82),
            Some(0.80),
            None,
            t + Duration::minutes(3),
        )
        .await;
        let (print_at, _) = pf
            .tape_maker_fill(
                "epc_m",
                0,
                t,
                t + Duration::seconds(EXEC_MAKER_CANCEL_SECS),
                limit,
            )
            .await
            .unwrap();
        assert!(
            print_at.is_none(),
            "a print needs real size, not a quote echo"
        );
        clean(&pf).await;
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn evaluate_and_book_end_to_end() {
        let pf = pf().await;
        clean(&pf).await;
        let fired = Utc::now() - Duration::hours(1);

        // Signal A: fire book 0.78/0.84 (mid 0.81); ask relaxes to 0.815 by +15m;
        // a real print at 0.80 ≤ mid fills the resting maker bid.
        let sig_a = signal(&pf, "epc_a", "ep_fav", fired).await;
        tape_row(
            &pf,
            "epc_a",
            "book",
            Some(0.78),
            Some(0.84),
            None,
            None,
            fired - Duration::seconds(30),
        )
        .await;
        tape_row(
            &pf,
            "epc_a",
            "price_change",
            Some(0.79),
            Some(0.83),
            Some(0.80),
            Some(120.0),
            fired + Duration::minutes(9),
        )
        .await;
        tape_row(
            &pf,
            "epc_a",
            "book",
            Some(0.80),
            Some(0.815),
            None,
            None,
            fired + Duration::minutes(14),
        )
        .await;

        // Signal B: runaway winner — ask only rises; the maker bid NEVER fills.
        let sig_b = signal(&pf, "epc_b", "ep_fav", fired).await;
        tape_row(
            &pf,
            "epc_b",
            "book",
            Some(0.80),
            Some(0.86),
            None,
            None,
            fired - Duration::seconds(20),
        )
        .await;
        tape_row(
            &pf,
            "epc_b",
            "book",
            Some(0.86),
            Some(0.90),
            None,
            None,
            fired + Duration::minutes(10),
        )
        .await;

        // The pending scan sees both (fired 1 h ago > 35 min floor).
        let pending = pf
            .exec_policy_pending(&["ep_fav".to_string()], 10)
            .await
            .unwrap();
        assert_eq!(pending.len(), 2, "both signals pending");
        for p in &pending {
            assert!(
                pf.evaluate_exec_policy(p).await.unwrap(),
                "entry frozen once"
            );
        }
        // Set-once: re-evaluating writes nothing.
        let again = pf
            .exec_policy_pending(&["ep_fav".to_string()], 10)
            .await
            .unwrap();
        assert!(again.is_empty(), "evaluated signals leave the pending scan");

        // Nothing books while the signals are open.
        assert!(
            pf.exec_policy_unbooked_resolved(10)
                .await
                .unwrap()
                .is_empty()
        );

        // Resolve: A wins, B wins (the maker missed the runaway winner — the
        // adverse-selection mechanism stays visible via B's abstention).
        for id in [sig_a, sig_b] {
            sqlx::query(
                "UPDATE consensus_signals SET resolved = TRUE, outcome_won = TRUE, \
                 resolved_at = NOW() WHERE id = $1",
            )
            .bind(id)
            .execute(&pf.pool)
            .await
            .unwrap();
        }

        let bookings = pf.exec_policy_unbooked_resolved(10).await.unwrap();
        assert_eq!(bookings.len(), 2);
        let mut total = 0usize;
        for b in &bookings {
            total += pf.book_exec_policy_entry(b, 100.0, 0.02).await.unwrap();
        }
        // A: fire + p15 + maker = 3. B: fire only (no later book row inside the
        // 15 min staleness for p15? — B's +10m row IS within 900 s of +15m, so
        // p15 books too; maker abstains) = 2.
        assert_eq!(total, 5, "A books 3 arms, B books 2 (maker abstained)");

        let (mrest_a,): (Option<f64>,) = sqlx::query_as(
            "SELECT entry FROM honest_paper_ledger \
             WHERE strategy = 'exec_mrest:ep_fav' AND condition_id = 'epc_a'",
        )
        .fetch_one(&pf.pool)
        .await
        .unwrap();
        assert!(
            (mrest_a.unwrap() - 0.81).abs() < 1e-9,
            "maker entry = fire mid"
        );
        let mrest_b: Option<(f64,)> = sqlx::query_as(
            "SELECT entry FROM honest_paper_ledger \
             WHERE strategy = 'exec_mrest:ep_fav' AND condition_id = 'epc_b'",
        )
        .fetch_optional(&pf.pool)
        .await
        .unwrap();
        assert!(mrest_b.is_none(), "unfilled maker = abstain, no ledger row");

        // Idempotency: a second booking pass appends nothing new.
        let again = pf.exec_policy_unbooked_resolved(10).await.unwrap();
        assert!(again.is_empty(), "booked entries leave the scan");
        for b in &bookings {
            assert_eq!(
                pf.book_exec_policy_entry(b, 100.0, 0.02).await.unwrap(),
                0,
                "ON CONFLICT: re-booking is a no-op"
            );
        }
        clean(&pf).await;
    }

    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn ledger_entry_guard_and_pnl_arithmetic() {
        let pf = pf().await;
        clean(&pf).await;
        // Entries outside (0,1) are refused outright.
        assert!(
            !pf.append_paper_bet_at("exec_fire:ep_g", "epc_g", 0, 100.0, 0.0, true, 0.02)
                .await
                .unwrap()
        );
        assert!(
            !pf.append_paper_bet_at("exec_fire:ep_g", "epc_g", 0, 100.0, 1.0, true, 0.02)
                .await
                .unwrap()
        );
        // Won at 0.80, fee 2%: pnl = 100 × ((1 − 0.8)/0.8 − 0.02) = 23.
        assert!(
            pf.append_paper_bet_at("exec_fire:ep_g", "epc_g", 0, 100.0, 0.80, true, 0.02)
                .await
                .unwrap()
        );
        let (pnl,): (f64,) =
            sqlx::query_as("SELECT pnl FROM honest_paper_ledger WHERE strategy = 'exec_fire:ep_g'")
                .fetch_one(&pf.pool)
                .await
                .unwrap();
        assert!(
            (pnl - 23.0).abs() < 1e-9,
            "pnl arithmetic matches the ledger contract"
        );
        clean(&pf).await;
    }
}
