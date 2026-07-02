use metrics::{counter, gauge, histogram};
use metrics_exporter_prometheus::PrometheusBuilder;
use std::net::SocketAddr;

/// Install the Prometheus exporter, process collector, and tokio runtime
/// metrics collector. Call once at startup before any `metrics::*` macros.
pub fn init(port: u16) {
    let addr: SocketAddr = ([0, 0, 0, 0], port).into();

    PrometheusBuilder::new()
        .with_http_listener(addr)
        .install()
        .expect("failed to install Prometheus exporter");

    // Process-level metrics (RSS, CPU, open FDs, threads, etc.)
    let collector = metrics_process::Collector::default();
    collector.describe();
    collector.collect();

    tracing::info!(%addr, "Prometheus metrics server started");
}

/// Spawn a background task that polls tokio runtime metrics every 10s
/// and records them into the `metrics` facade.
pub fn spawn_tokio_collector(runtime_monitor: tokio_metrics::RuntimeMonitor) {
    tokio::spawn(async move {
        for interval in runtime_monitor.intervals() {
            // Point-in-time values → gauges
            gauge!("tokio_workers_count").set(interval.workers_count as f64);
            gauge!("tokio_live_tasks_count").set(interval.live_tasks_count as f64);
            gauge!("tokio_global_queue_depth").set(interval.global_queue_depth as f64);
            gauge!("tokio_total_local_queue_depth").set(interval.total_local_queue_depth as f64);
            gauge!("tokio_blocking_queue_depth").set(interval.blocking_queue_depth as f64);
            gauge!("tokio_blocking_threads_count").set(interval.blocking_threads_count as f64);
            gauge!("tokio_mean_poll_duration_seconds")
                .set(interval.mean_poll_duration.as_secs_f64());
            gauge!("tokio_busy_ratio").set(interval.busy_ratio());

            // Per-interval deltas → counters (so rate() works in dashboards)
            counter!("tokio_total_park_count").increment(interval.total_park_count);
            counter!("tokio_total_noop_count").increment(interval.total_noop_count);
            counter!("tokio_total_steal_count").increment(interval.total_steal_count);
            counter!("tokio_total_steal_operations").increment(interval.total_steal_operations);
            counter!("tokio_total_polls_count").increment(interval.total_polls_count);
            counter!("tokio_total_local_schedule_count")
                .increment(interval.total_local_schedule_count);
            counter!("tokio_num_remote_schedules").increment(interval.num_remote_schedules);
            counter!("tokio_total_overflow_count").increment(interval.total_overflow_count);
            counter!("tokio_budget_forced_yield_count")
                .increment(interval.budget_forced_yield_count);
            counter!("tokio_io_driver_ready_count").increment(interval.io_driver_ready_count);
            gauge!("tokio_total_busy_duration_seconds")
                .set(interval.total_busy_duration.as_secs_f64());

            // Refresh process metrics each cycle
            metrics_process::Collector::default().collect();

            tokio::time::sleep(std::time::Duration::from_secs(10)).await;
        }
    });
}

// ---------------------------------------------------------------------------
// Application-level metric helpers
// ---------------------------------------------------------------------------

/// Record a completed scan cycle.
pub fn record_scan(markets_scanned: u64, news_total: u64, news_new: u64, signals: u64) {
    counter!("bot_scans_total").increment(1);
    counter!("bot_markets_scanned_total").increment(markets_scanned);
    counter!("bot_news_fetched_total").increment(news_total);
    counter!("bot_news_new_total").increment(news_new);
    counter!("bot_signals_found_total").increment(signals);
}

/// Record a bet placement.
pub fn record_bet(strategy: &str, source: &str, cost: f64) {
    counter!("bot_bets_placed_total", "strategy" => strategy.to_string(), "source" => source.to_string()).increment(1);
    histogram!("bot_bet_cost_eur", "strategy" => strategy.to_string()).record(cost);
}

/// Record a bet resolution.
pub fn record_resolution(strategy: &str, won: bool, pnl: f64) {
    let outcome = if won { "win" } else { "loss" };
    counter!("bot_bets_resolved_total", "strategy" => strategy.to_string(), "outcome" => outcome.to_string()).increment(1);
    gauge!("bot_last_pnl_eur", "strategy" => strategy.to_string()).set(pnl);
}

/// Update bankroll gauges.
pub fn record_bankroll(strategy: &str, bankroll: f64) {
    gauge!("bot_bankroll_eur", "strategy" => strategy.to_string()).set(bankroll);
}

/// Update total bankroll gauge.
pub fn record_total_bankroll(total: f64) {
    gauge!("bot_bankroll_total_eur").set(total);
}

/// Record open bets count.
pub fn record_open_bets(count: u64) {
    gauge!("bot_open_bets").set(count as f64);
}

/// Record unrealized PnL.
pub fn record_unrealized_pnl(pnl: f64) {
    gauge!("bot_unrealized_pnl_eur").set(pnl);
}

/// Record a housekeeping cycle.
pub fn record_housekeeping() {
    counter!("bot_housekeeping_cycles_total").increment(1);
}

/// Record a heartbeat.
pub fn record_heartbeat() {
    counter!("bot_heartbeats_total").increment(1);
}

/// Record WS alert processing.
pub fn record_ws_alert(had_signal: bool) {
    counter!("bot_ws_alerts_total").increment(1);
    if had_signal {
        counter!("bot_ws_signals_total").increment(1);
    }
}

/// Record ML model sidecar status: age in seconds and whether it's reachable.
pub fn record_model_status(age_secs: Option<f64>) {
    match age_secs {
        Some(age) => {
            gauge!("bot_model_age_seconds").set(age);
            gauge!("bot_model_up").set(1.0);
        }
        None => {
            gauge!("bot_model_up").set(0.0);
        }
    }
}

/// Record a duration histogram for the given metric name.
pub fn record_duration(name: &'static str, duration: std::time::Duration) {
    histogram!(name).record(duration.as_secs_f64());
}

// ---------------------------------------------------------------------------
// Consensus engine metrics
// ---------------------------------------------------------------------------

/// Update the count of actively tracked leaderboard traders.
pub fn record_tracked_traders(count: u64) {
    gauge!("consensus_tracked_traders").set(count as f64);
}

/// Update the hot/deep split of the tracked universe: `hot` = consensus-eligible
/// (voting) traders, `deep` = captured-but-not-voting deep candidates. The gap is
/// the candidate pool the depth-widening buys us without touching the live engine.
pub fn record_tracked_split(hot: u64, deep: u64) {
    gauge!("consensus_tracked_hot").set(hot as f64);
    gauge!("consensus_tracked_deep").set(deep as f64);
}

/// Record a completed consensus cycle: markets scored and signals found.
pub fn record_consensus_cycle(markets: u64, signals: u64) {
    counter!("consensus_cycles_total").increment(1);
    gauge!("consensus_markets_scored").set(markets as f64);
    gauge!("consensus_signals_active").set(signals as f64);
}

/// Record a pushed consensus alert by strategy + tier.
pub fn record_consensus_alert(strategy: &str, tier: &str) {
    counter!("consensus_alerts_total",
        "strategy" => strategy.to_string(),
        "tier" => tier.to_string())
    .increment(1);
}

/// Record a resolved consensus signal by strategy, outcome, and segment.
pub fn record_consensus_resolution(strategy: &str, won: bool, is_sports: bool) {
    let outcome = if won { "win" } else { "loss" };
    let segment = if is_sports { "sports" } else { "nonsports" };
    counter!("consensus_resolved_total",
        "strategy" => strategy.to_string(),
        "outcome" => outcome.to_string(),
        "segment" => segment.to_string())
    .increment(1);
}

/// Process-global 429 count, mirrored alongside the Prometheus counter so the
/// in-process board can read it back (Prometheus counters aren't readable here).
static DATA_API_429: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

/// Record a data-api HTTP 429 (rate-limited). The scale gate (Phase 5) only
/// widens the tracked universe / cadence once this rate is ≈ 0.
pub fn record_data_api_429() {
    counter!("consensus_data_api_429_total").increment(1);
    DATA_API_429.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
}

/// Total data-api 429s seen since process start (for the board's scale gate).
pub fn data_api_429_count() -> u64 {
    DATA_API_429.load(std::sync::atomic::Ordering::Relaxed)
}

/// Last consensus cycle's poll fan-out size and wall-clock (ms), mirrored to
/// readable atomics so the board scale-gate can show whether the fan-out at the
/// current tracked depth stays comfortably inside the cycle window.
static LAST_POLL_COUNT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static LAST_POLL_LATENCY_MS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

/// Record the poll fan-out cost of one consensus cycle: how many traders were
/// polled and how long the (semaphore-bounded) ingest took. This is the depth
/// regression surface — the scale gate reads it to decide if cadence tiering is
/// needed or the semaphore alone suffices.
pub fn record_consensus_poll(polled: u64, dur: std::time::Duration) {
    gauge!("consensus_poll_count").set(polled as f64);
    histogram!("consensus_poll_latency_seconds").record(dur.as_secs_f64());
    LAST_POLL_COUNT.store(polled, std::sync::atomic::Ordering::Relaxed);
    LAST_POLL_LATENCY_MS.store(dur.as_millis() as u64, std::sync::atomic::Ordering::Relaxed);
}

/// `(polled, latency_ms)` from the most recent consensus cycle (for the board).
pub fn consensus_last_poll() -> (u64, u64) {
    (
        LAST_POLL_COUNT.load(std::sync::atomic::Ordering::Relaxed),
        LAST_POLL_LATENCY_MS.load(std::sync::atomic::Ordering::Relaxed),
    )
}

/// Forward feature-log rows flushed this cycle (the `market_resid` accrual rate).
pub fn record_market_feature_log_rows(n: u64) {
    counter!("market_feature_log_rows_total").increment(n);
}

/// Silent `market_resid` arm emissions this cycle.
pub fn record_market_resid_emits(n: u64) {
    counter!("market_resid_emit_total").increment(n);
}

/// Time spent in `prefetch_markets` (per cycle) — the accrual/arm data fetch cost.
pub fn record_consensus_prefetch(duration: std::time::Duration) {
    histogram!("consensus_prefetch_seconds").record(duration.as_secs_f64());
}

/// Record a captured executable entry ask (honest-tracker instrumentation).
/// `decision` = captured on the first-price pass (`entry_ask_mid` ==
/// `initial_market_price`) vs a lagged backlog capture. `spread` =
/// `entry_ask − entry_ask_mid` (the REAL execution haircut, replacing the guess).
/// `lag_secs` = `entry_ask_at − first_detected_at`. Never on the live alert path.
/// NB (audit #2, KNOWN GAP): this `kind` uses the code's `first_price` provenance,
/// while the board's REALIZED-ROI cohort uses a wall-clock `lag ≤ REALIZED_DECISION_
/// LAG_SECS` filter — so `kind=decision` here and the realized cohort can diverge
/// near the window edge. Reconciling them (key the SQL off provenance) is deferred.
pub fn record_entry_ask_capture(decision: bool, spread: f64, lag_secs: f64) {
    let kind = if decision { "decision" } else { "lagged" };
    counter!("consensus_entry_ask_captured_total", "kind" => kind).increment(1);
    histogram!("consensus_entry_ask_spread").record(spread);
    histogram!("consensus_entry_ask_capture_lag_seconds").record(lag_secs.max(0.0));
}

/// Record a failed `/book` fetch during entry-ask capture. Best-effort: this
/// NEVER blocks the alert path — the signal stays alive with a NULL ask and the
/// honest query falls back to mid+haircut.
pub fn record_entry_ask_fetch_failed() {
    counter!("consensus_entry_ask_fetch_failed_total").increment(1);
}

/// Record that entry-ask capture hit its per-cycle budget (`decision` vs lagged),
/// so remaining signals settle on later cycles. Surfaces silent truncation.
pub fn record_entry_ask_capped(decision: bool) {
    let kind = if decision { "decision" } else { "lagged" };
    counter!("consensus_entry_ask_capped_total", "kind" => kind).increment(1);
}

/// Process-global multi-outcome (non-binary) skip count, mirrored alongside the
/// Prometheus counter so the in-process board can read it back (Prometheus
/// counters aren't readable here). These strict markets have no single
/// complementary YES side, so feature-building skips them and `market_resid`
/// never fires on them — the board surfaces the running total.
static MARKET_MULTI_OUTCOME_SKIPPED: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(0);

/// Record `n` multi-outcome markets skipped by feature-building this cycle.
pub fn record_market_multi_outcome_skipped(n: u64) {
    counter!("market_multi_outcome_skipped_total").increment(n);
    MARKET_MULTI_OUTCOME_SKIPPED.fetch_add(n, std::sync::atomic::Ordering::Relaxed);
}

/// Total multi-outcome markets skipped since process start (for the board line).
pub fn market_multi_outcome_skipped_count() -> u64 {
    MARKET_MULTI_OUTCOME_SKIPPED.load(std::sync::atomic::Ordering::Relaxed)
}

/// Publish a strategy's live forward-tracking scoreboard as gauges.
pub fn record_consensus_strategy_score(strategy: &str, resolved: i64, hit_rate: f64, edge: f64) {
    gauge!("consensus_strategy_resolved", "strategy" => strategy.to_string()).set(resolved as f64);
    gauge!("consensus_strategy_hit_rate", "strategy" => strategy.to_string()).set(hit_rate);
    gauge!("consensus_strategy_edge", "strategy" => strategy.to_string()).set(edge);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn multi_outcome_skip_mirror_accumulates() {
        // The in-process mirror (readable by the board) advances by exactly `n`.
        let before = market_multi_outcome_skipped_count();
        record_market_multi_outcome_skipped(3);
        record_market_multi_outcome_skipped(2);
        assert_eq!(market_multi_outcome_skipped_count(), before + 5);
    }
}
