//! Copy-trader monitor: discovers top traders from the Polymarket leaderboard
//! and polls their on-chain activity to surface trade signals.
//!
//! This module is not yet wired into the main execution loop — it will be
//! integrated via the `copy_trade_cycle` in `src/cycles/copy_trade.rs`.

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use futures_util::future::join_all;
use reqwest::Client;
use serde::Deserialize;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Semaphore;

use crate::storage::postgres::{NewCopyTradeEvent, PgPortfolio};

/// Trades older than this are skipped — price has likely moved too far.
const STALE_TRADE_SECS: i64 = 300; // 5 minutes

/// Max concurrent `/activity` polls in the legacy `detect_new_trades` fan-out.
/// Mirrors the consensus cycle's `CONSENSUS_MAX_CONCURRENCY` default so widening
/// the tracked universe can never turn `COPY_TRADE_ENABLED=true` into a burst of
/// hundreds of simultaneous requests (429 storm). Strict hardening, depth-agnostic.
const COPY_TRADE_MAX_CONCURRENCY: usize = 8;

const DATA_API: &str = "https://data-api.polymarket.com";
/// Default HTTP timeout for all data-API calls.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(15);
/// Server-side page size for the leaderboard endpoint. `limit` is hard-capped at
/// 50 server-side (verified 2026-07-01: sending `limit=100` returns 50), so depth
/// is achieved by paginating with `offset`, not by raising `limit`.
const LEADERBOARD_PAGE_SIZE: usize = 50;
/// Politeness delay between successive leaderboard pages so a deep (top-500) fetch
/// paces itself instead of bursting 10 back-to-back GETs into the data-api.
const LEADERBOARD_PAGE_DELAY: Duration = Duration::from_millis(150);
/// Max leaderboard pages fetched concurrently. Depth 1000 = 20 pages; at 4 concurrent
/// the refresh is ~5 round-trips deep instead of 20 sequential ones, while staying far
/// under the measured data-api ceiling (2026-07-13: ~38 req/s sustained, 0 × 429).
const LEADERBOARD_PAGE_CONCURRENCY: usize = 4;
/// Retries per leaderboard page before the whole period is abandoned.
const LEADERBOARD_PAGE_RETRIES: usize = 3;
/// Page size for `/activity`. The server caps `limit` at 1000 (verified 2026-07-13:
/// `limit=2000` returns 1000) and — critically — DEFAULTS to 100 when `limit` is
/// omitted, which is what silently truncated every backfill before this.
const ACTIVITY_PAGE_SIZE: usize = 500;
/// Hard server-side offset ceiling on `/activity` (verified 2026-07-13: `offset=3500`
/// returns `400 {"error":"max historical activity offset of 3000 exceeded"}`). With
/// [`ACTIVITY_PAGE_SIZE`] that makes **3 500 events the most any single `(start, end)`
/// window can yield**. A window denser than that is not reachable by paging further —
/// it has to be NARROWED. That is why the poll drains a bounded time window and halves
/// the span rather than just walking `offset` forever.
const ACTIVITY_MAX_OFFSET: usize = 3000;
/// Pages per window: offsets 0, 500 … 3000.
const ACTIVITY_MAX_PAGES: usize = ACTIVITY_MAX_OFFSET / ACTIVITY_PAGE_SIZE + 1;
/// Retries per `/activity` page. The data-api times out sporadically under a
/// depth-1000 fan-out; without this a transient blip needlessly costs a page.
const ACTIVITY_PAGE_RETRIES: usize = 2;
/// Widest span one poll will try to cover in a single cycle. A first-sight wallet
/// (48h of backfill) is therefore drained over several cycles, 6h at a time, instead
/// of in one burst — which is what keeps onboarding 800 new deep-pool wallets from
/// stampeding the data-api.
const ACTIVITY_WINDOW_SECS: i64 = 6 * 3600;
/// Stop halving the span here. A window this narrow holding >3 500 events is beyond
/// what the API will serve at all; we record it as an honest capture gap rather than
/// re-poll it forever.
const ACTIVITY_MIN_WINDOW_SECS: i64 = 300;
/// Number of traders shown per period section in the inline leaderboard reply.
const LEADERBOARD_SECTION_LIMIT: usize = 5;

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

/// One entry from `GET /leaderboard`.
/// Fields come as strings from the API, so we deserialize to `Value` and parse.
#[derive(Debug, Deserialize)]
struct LeaderboardEntry {
    #[serde(rename = "proxyWallet")]
    proxy_wallet: String,
    #[serde(rename = "userName")]
    name: Option<String>,
    #[serde(default)]
    pnl: Option<serde_json::Value>,
    #[serde(default, rename = "vol")]
    volume: Option<serde_json::Value>,
}

impl LeaderboardEntry {
    fn pnl_f64(&self) -> f64 {
        self.volume_like(&self.pnl)
    }

    fn volume_f64(&self) -> f64 {
        self.volume_like(&self.volume)
    }

    fn volume_like(&self, v: &Option<serde_json::Value>) -> f64 {
        v.as_ref()
            .and_then(|v| match v {
                serde_json::Value::Number(n) => n.as_f64(),
                serde_json::Value::String(s) => s.parse().ok(),
                _ => None,
            })
            .unwrap_or(0.0)
    }
}

/// One trade event from `GET /activity`.
#[derive(Debug, Deserialize)]
struct ActivityEvent {
    /// Market slug — used to look up the Gamma numeric ID.
    slug: Option<String>,
    #[serde(rename = "conditionId")]
    condition_id: Option<String>,
    /// "BUY" | "SELL"
    side: Option<String>,
    price: Option<f64>,
    /// Actual USD value of the trade (not shares).
    #[serde(rename = "usdcSize")]
    usdc_size: Option<f64>,
    #[serde(rename = "transactionHash")]
    tx_hash: Option<String>,
    timestamp: Option<i64>,
    /// Index of the outcome bought (0 = first outcome / "Yes"). Critical for
    /// consensus keying — buying a different outcome is the opposite bet.
    #[serde(default, rename = "outcomeIndex")]
    outcome_index: Option<i32>,
    /// Human label of the outcome ("Yes"/"No"/team name).
    #[serde(default)]
    outcome: Option<String>,
    /// Market title (display).
    #[serde(default)]
    title: Option<String>,
    #[serde(default, rename = "eventSlug")]
    event_slug: Option<String>,
}

// ---------------------------------------------------------------------------
// Public output types
// ---------------------------------------------------------------------------

/// A raw trade as returned by the Polymarket activity endpoint.
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct TraderTrade {
    /// Market slug — used to look up the Gamma market (fetch_market_by_slug).
    pub slug: String,
    /// Hex condition ID — used for deduplication.
    pub condition_id: String,
    /// "BUY" or "SELL"
    pub side: String,
    pub price: f64,
    /// Size in USD (usdcSize from API).
    pub size_usd: f64,
    pub tx_hash: Option<String>,
    pub timestamp: DateTime<Utc>,
    /// Index of the outcome bought (0 = first). `None` if the API omitted it.
    pub outcome_index: Option<i32>,
    /// Human outcome label ("Yes"/"No"/team).
    pub outcome: Option<String>,
    /// Market title (display).
    pub title: Option<String>,
    pub event_slug: Option<String>,
}

/// One row of `/trades?market=…` — a trade by ANY wallet in a given market.
///
/// The market-side twin of [`ActivityEvent`] (which is wallet-side). Same trade, keyed
/// the other way round, and that inversion is the entire point of the harvest lane:
/// `/activity?user=` can only tell you about wallets you already know, whereas
/// `/trades?market=` enumerates EVERY participant in a market you care about — including
/// the ones no leaderboard will ever show you.
#[derive(Debug, Clone, Deserialize)]
struct MarketTrade {
    #[serde(rename = "proxyWallet")]
    proxy_wallet: Option<String>,
    #[serde(rename = "conditionId")]
    condition_id: Option<String>,
    slug: Option<String>,
    side: Option<String>,
    price: Option<f64>,
    /// SHARES, not USD — unlike `/activity`'s `usdcSize`. USD = size × price.
    size: Option<f64>,
    #[serde(rename = "transactionHash")]
    tx_hash: Option<String>,
    timestamp: Option<i64>,
    #[serde(rename = "outcomeIndex")]
    outcome_index: Option<i32>,
    outcome: Option<String>,
    title: Option<String>,
    #[serde(rename = "eventSlug")]
    event_slug: Option<String>,
}

/// A trade harvested market-side, carrying the wallet that made it.
#[derive(Debug, Clone)]
pub struct HarvestedTrade {
    pub wallet: String,
    pub trade: TraderTrade,
}

/// A trade detected from a followed trader, ready for downstream filtering.
#[derive(Debug, Clone)]
pub struct DetectedTrade {
    pub trader_wallet: String,
    pub trade: TraderTrade,
}

/// Result of one `/activity` poll: the parsed trades plus `raw_count`, the
/// length of the **raw page** (pre-parse). The gap test keys on the real page
/// size — a full 100-row page whose oldest row is newer than everything we'd
/// seen means the trader traded faster than our cadence and we lost the
/// in-between trades. A 429 is surfaced as `Err` (not carried here) so the
/// caller does NOT advance the cursor and re-fetches the gap next cycle.
#[derive(Debug, Clone)]
pub struct PollResult {
    pub trades: Vec<TraderTrade>,
    pub raw_count: usize,
    /// `true` when the poll covered all the way to `now`. `false` when it covered only
    /// a leading window of `[since, now]` — the rest drains on later cycles.
    pub complete: bool,
    /// The instant through which this poll achieved COMPLETE coverage: every event in
    /// `[since, covered_through]` was read. This — not the newest event's timestamp —
    /// is the only safe cursor target, and it is a property of the WINDOW, so it holds
    /// even when the window turned out to be empty.
    ///
    /// `None` means nothing could be covered (the first page failed); the cursor must
    /// then stay put and the range is retried next cycle.
    pub covered_through: Option<DateTime<Utc>>,
}

/// Display-ready representation of a single leaderboard entry.
#[derive(Debug, Clone)]
pub struct LeaderboardDisplay {
    pub rank: usize,
    pub name: String,
    pub pnl: f64,
    pub volume: f64,
    pub wallet: String,
}

// ---------------------------------------------------------------------------
// Standalone leaderboard helpers (no monitor instance required)
// ---------------------------------------------------------------------------

/// Fetch a trader's display name via the activity endpoint.
/// Returns `None` if the request fails or the trader has no activity.
pub async fn fetch_trader_username(http: &Client, wallet: &str) -> Option<String> {
    let url = format!("{DATA_API}/activity?user={wallet}&type=TRADE&limit=1");
    let resp: serde_json::Value = http
        .get(&url)
        .timeout(REQUEST_TIMEOUT)
        .send()
        .await
        .ok()?
        .json()
        .await
        .ok()?;
    let name = resp.as_array()?.first()?["name"].as_str()?;
    if name.is_empty() {
        None
    } else {
        Some(name.to_string())
    }
}

/// Fetch the public Polymarket leaderboard for a given time period and return
/// the top entries formatted for display.  This is **read-only** — nothing is
/// written to the database.
///
/// `time_period` must be one of `"DAY"`, `"WEEK"`, `"MONTH"`, or `"ALL"`.
///
/// # Errors
///
/// Returns an error if the HTTP request fails or the response cannot be
/// parsed.
pub async fn fetch_leaderboard(
    http: &Client,
    time_period: &str,
) -> Result<Vec<LeaderboardDisplay>> {
    let url = format!("{DATA_API}/v1/leaderboard?timePeriod={time_period}&limit=10");

    let entries: Vec<LeaderboardEntry> = http
        .get(&url)
        .timeout(REQUEST_TIMEOUT)
        .send()
        .await
        .context("leaderboard request failed")?
        .error_for_status()
        .context("leaderboard returned non-2xx")?
        .json()
        .await
        .context("leaderboard JSON parse failed")?;

    // Sort by descending PnL, then assign sequential display ranks.
    let mut sorted = entries;
    sorted.sort_by(|a, b| {
        b.pnl_f64()
            .partial_cmp(&a.pnl_f64())
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let display = sorted
        .into_iter()
        .take(LEADERBOARD_SECTION_LIMIT)
        .enumerate()
        .map(|(i, e)| {
            let pnl = e.pnl_f64();
            let volume = e.volume_f64();
            let wallet = e.proxy_wallet;
            let name = e
                .name
                .filter(|n| !n.is_empty())
                .unwrap_or_else(|| format!("{}…", &wallet[..8.min(wallet.len())]));
            LeaderboardDisplay {
                rank: i + 1,
                name,
                pnl,
                volume,
                wallet,
            }
        })
        .collect();

    Ok(display)
}

/// A raw leaderboard entry for the auto-tracker (keeps the real username and
/// the API rank, unlike [`LeaderboardDisplay`] which substitutes a wallet
/// prefix and caps at the display limit).
#[derive(Debug, Clone)]
pub struct LeaderboardRaw {
    pub wallet: String,
    pub username: Option<String>,
    pub rank: i32,
    pub pnl: f64,
    pub volume: f64,
}

/// Fetch the top `limit` leaderboard traders for a period (cap 50), preserving
/// real usernames and PnL-descending rank. Read-only.
pub async fn fetch_leaderboard_n(
    http: &Client,
    time_period: &str,
    limit: usize,
) -> Result<Vec<LeaderboardRaw>> {
    let n = limit.clamp(1, 50);
    let url = format!("{DATA_API}/v1/leaderboard?timePeriod={time_period}&limit={n}");
    let entries: Vec<LeaderboardEntry> = http
        .get(&url)
        .timeout(REQUEST_TIMEOUT)
        .send()
        .await
        .context("leaderboard request failed")?
        .error_for_status()
        .context("leaderboard returned non-2xx")?
        .json()
        .await
        .context("leaderboard JSON parse failed")?;

    let mut sorted = entries;
    sorted.sort_by(|a, b| {
        b.pnl_f64()
            .partial_cmp(&a.pnl_f64())
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    Ok(sorted
        .into_iter()
        .take(n)
        .enumerate()
        .map(|(i, e)| LeaderboardRaw {
            pnl: e.pnl_f64(),
            volume: e.volume_f64(),
            username: e.name.filter(|s| !s.is_empty()),
            wallet: e.proxy_wallet,
            rank: (i + 1) as i32,
        })
        .collect())
}

/// Fetch a single leaderboard page (`offset..offset+PAGE_SIZE`) for a period.
/// Read-only. A 429 surfaces as `Err` (and is counted) so a rate-limited page
/// never silently truncates the paginated universe — the caller aborts the whole
/// fetch and the refresh leaves the universe untouched, retrying next cycle.
async fn fetch_leaderboard_page(
    http: &Client,
    time_period: &str,
    offset: usize,
) -> Result<Vec<LeaderboardRaw>> {
    let url = format!(
        "{DATA_API}/v1/leaderboard?timePeriod={time_period}&limit={LEADERBOARD_PAGE_SIZE}&offset={offset}"
    );
    let resp = http
        .get(&url)
        .timeout(REQUEST_TIMEOUT)
        .send()
        .await
        .context("leaderboard page request failed")?;

    // Mirror the activity-poll 429 discipline: surface as Err (counted) rather
    // than parse an empty/partial body and silently drop deeper ranks.
    if resp.status() == reqwest::StatusCode::TOO_MANY_REQUESTS {
        crate::metrics::record_data_api_429();
        return Err(anyhow::anyhow!(
            "data-api 429 (rate-limited) on leaderboard offset={offset}"
        ));
    }

    let entries: Vec<LeaderboardEntry> = resp
        .error_for_status()
        .context("leaderboard page returned non-2xx")?
        .json()
        .await
        .context("leaderboard page JSON parse failed")?;

    // Rank is re-derived globally in `merge_leaderboard_pages`; leave it 0 here.
    Ok(entries
        .into_iter()
        .map(|e| LeaderboardRaw {
            pnl: e.pnl_f64(),
            volume: e.volume_f64(),
            username: e.name.filter(|s| !s.is_empty()),
            wallet: e.proxy_wallet,
            rank: 0,
        })
        .collect())
}

/// Merge paginated leaderboard rows into a single PnL-descending, globally-ranked
/// universe: dedup by wallet (keep the higher-PnL sighting), sort PnL desc, cap at
/// `depth`, and re-derive `rank = i+1` across the merged pool. Pure — unit-tested.
fn merge_leaderboard_pages(rows: Vec<LeaderboardRaw>, depth: usize) -> Vec<LeaderboardRaw> {
    use std::collections::HashMap;
    let mut by_wallet: HashMap<String, LeaderboardRaw> = HashMap::new();
    for r in rows {
        by_wallet
            .entry(r.wallet.clone())
            .and_modify(|cur| {
                // Overlapping pages shouldn't happen with clean offset pagination,
                // but if a wallet is seen twice keep the higher-PnL (better) row.
                if r.pnl > cur.pnl {
                    *cur = r.clone();
                }
            })
            .or_insert(r);
    }

    let mut merged: Vec<LeaderboardRaw> = by_wallet.into_values().collect();
    merged.sort_by(|a, b| {
        b.pnl
            .partial_cmp(&a.pnl)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    merged.truncate(depth);
    for (i, r) in merged.iter_mut().enumerate() {
        r.rank = (i + 1) as i32;
    }
    merged
}

/// Fetch the top `depth` leaderboard traders for a period via `offset` pagination
/// (`offset = 0, 50, 100, …`), up to `depth` rows or a short/empty page (board
/// end). Additive sibling to [`fetch_leaderboard_n`] — the deep-universe path.
/// Paces requests, surfaces a 429 as `Err` (no silent truncation), dedups by
/// wallet, and re-derives global PnL-descending rank. Read-only.
pub async fn fetch_leaderboard_paged(
    http: &Client,
    time_period: &str,
    depth: usize,
) -> Result<Vec<LeaderboardRaw>> {
    let depth = depth.max(1);
    // Every offset is known up front (`depth` is the target), so the pages are an
    // independent fan-out rather than a chain: at depth 1000 that is 20 pages, which
    // sequentially cost 20 × (latency + 150ms). A page past the board end simply
    // comes back empty and merges to nothing.
    let n_pages = depth.div_ceil(LEADERBOARD_PAGE_SIZE);
    let sem = Arc::new(Semaphore::new(LEADERBOARD_PAGE_CONCURRENCY));

    let fetches = (0..n_pages).map(|p| {
        let sem = Arc::clone(&sem);
        let offset = p * LEADERBOARD_PAGE_SIZE;
        async move {
            let _permit = sem.acquire_owned().await;
            let page = fetch_leaderboard_page_retrying(http, time_period, offset).await;
            (offset, page)
        }
    });
    let results = join_all(fetches).await;

    // A page that failed every retry is NOT tolerated: silently dropping it would
    // hand back a universe with a rank-shaped hole in it, and the deep pool exists
    // precisely to be an unbiased net. Abort, leave the universe as-is, retry next
    // refresh (the caller logs and skips the period).
    let mut rows: Vec<LeaderboardRaw> = Vec::with_capacity(depth);
    for (offset, page) in results {
        let page = page.with_context(|| {
            format!(
                "leaderboard page offset={offset} failed after {LEADERBOARD_PAGE_RETRIES} retries"
            )
        })?;
        rows.extend(page);
    }

    let merged = merge_leaderboard_pages(rows, depth);
    tracing::info!(
        period = %time_period,
        depth,
        pages = n_pages,
        fetched = merged.len(),
        "Leaderboard paged fetch"
    );
    Ok(merged)
}

/// One leaderboard page, retried through the transient failures that a 20-page ×
/// 4-period refresh makes near-certain: at ~80 requests a refresh, a 1%-per-request
/// failure rate fails ~55% of refreshes if a single bad page is fatal.
///
/// Backoff is exponential and spread by offset, so 20 pages that all get 429'd do
/// not retry in lockstep and re-burst the same spike.
async fn fetch_leaderboard_page_retrying(
    http: &Client,
    time_period: &str,
    offset: usize,
) -> Result<Vec<LeaderboardRaw>> {
    let mut last_err = None;
    for attempt in 0..=LEADERBOARD_PAGE_RETRIES {
        if attempt > 0 {
            let backoff = LEADERBOARD_PAGE_DELAY * (1 << attempt)
                + Duration::from_millis((offset % 7) as u64 * 20);
            tokio::time::sleep(backoff).await;
        }
        match fetch_leaderboard_page(http, time_period, offset).await {
            Ok(page) => return Ok(page),
            Err(e) => {
                tracing::debug!(
                    period = %time_period, offset, attempt,
                    err = %e, "Leaderboard page failed; retrying"
                );
                last_err = Some(e);
            }
        }
    }
    Err(last_err.unwrap_or_else(|| anyhow::anyhow!("leaderboard page offset={offset} failed")))
}

/// Format a slice of [`LeaderboardDisplay`] entries as a single period section
/// (no header or footer — used internally by [`format_multi_leaderboard`]).
///
/// When `show_wallets` is `true`, each entry also shows a `/follow <wallet>`
/// code snippet that the bot owner can tap-to-copy in Telegram.
fn format_leaderboard_section(entries: &[LeaderboardDisplay], show_wallets: bool) -> String {
    let mut lines = Vec::with_capacity(entries.len());

    for entry in entries {
        let pnl_str = crate::format::format_dollars(entry.pnl);
        let vol_str = crate::format::format_dollars(entry.volume);

        let line = match entry.rank {
            1 => format!("🥇 *{}* — PnL: {} | Vol: {}", entry.name, pnl_str, vol_str),
            2 => format!("🥈 *{}* — PnL: {} | Vol: {}", entry.name, pnl_str, vol_str),
            3 => format!("🥉 *{}* — PnL: {} | Vol: {}", entry.name, pnl_str, vol_str),
            n => format!(
                "{} {}. {} — PnL: {} | Vol: {}",
                return_rank_str(n),
                n,
                entry.name,
                pnl_str,
                vol_str,
            ),
        };

        if show_wallets {
            lines.push(format!("{line}\n   `/follow {}`", entry.wallet));
        } else {
            lines.push(line);
        }
    }

    lines.join("\n")
}

/// Format leaderboard results for multiple time periods into a single Telegram
/// message with one section per period.
///
/// `periods` is a slice of `(label, entries)` pairs, e.g.:
/// `&[("Today", &day_entries), ("This Month", &month_entries), ("All Time", &all_entries)]`
///
/// # Example
///
/// ```ignore
/// let msg = format_multi_leaderboard(&[
///     ("Today", &day_entries),
///     ("This Month", &month_entries),
///     ("All Time", &all_entries),
/// ]);
/// notifier.send_to(&chat_id, &msg).await?;
/// ```
pub fn format_multi_leaderboard(periods: &[(&str, &[LeaderboardDisplay])]) -> String {
    let mut parts = Vec::with_capacity(periods.len() + 2);
    parts.push("🏆 *Polymarket Leaderboard*".to_string());

    for (label, entries) in periods.iter() {
        let section_header = format!("\n📅 *{label}*");
        if entries.is_empty() {
            parts.push(format!("{section_header}\n_No data available._"));
        } else {
            parts.push(format!(
                "{section_header}\n{}",
                format_leaderboard_section(entries, true)
            ));
        }
    }

    parts.push("\n_Data from Polymarket Data API_".to_string());
    parts.join("\n")
}

/// Returns a blank string for numbered ranks (the rank number is embedded in
/// the formatted line directly).
#[inline]
fn return_rank_str(_rank: usize) -> &'static str {
    " "
}

// ---------------------------------------------------------------------------
// Activity parsing
// ---------------------------------------------------------------------------

/// Convert raw deserialized activity events into `TraderTrade`s, dropping any
/// entries that are missing mandatory fields.
/// Map one `/trades` row onto the shared [`TraderTrade`] shape, so a harvested trade goes
/// through the SAME `trade_to_fill` → `insert_trader_fills` path as a polled one and lands
/// byte-identical (same frozen sport/bet_type classification, same ON CONFLICT dedup).
///
/// Drops rows missing anything the fill needs. Note `size` is SHARES here (the `/activity`
/// endpoint reports `usdcSize`), so USD is `size × price` — getting this wrong would silently
/// mis-scale every harvested wallet's stake and corrupt the very profiles we are mining.
fn market_trade_to_harvested(r: MarketTrade) -> Option<HarvestedTrade> {
    let wallet = r.proxy_wallet?.to_lowercase();
    let price = r.price?;
    let size_shares = r.size?;
    let ts = DateTime::from_timestamp(r.timestamp?, 0)?;
    Some(HarvestedTrade {
        wallet,
        trade: TraderTrade {
            slug: r.slug?,
            condition_id: r.condition_id?,
            side: r.side?,
            price,
            size_usd: size_shares * price,
            tx_hash: r.tx_hash,
            timestamp: ts,
            outcome_index: r.outcome_index,
            outcome: r.outcome,
            title: r.title,
            event_slug: r.event_slug.filter(|s| !s.is_empty()),
        },
    })
}

fn parse_activity_events(events: Vec<ActivityEvent>) -> Vec<TraderTrade> {
    events
        .into_iter()
        .filter_map(|e| {
            let slug = e.slug?;
            let condition_id = e.condition_id?;
            let side = e.side?;
            let price = e.price?;
            let size_usd = e.usdc_size.unwrap_or(0.0);
            let ts_secs = e.timestamp?;
            let timestamp = DateTime::from_timestamp(ts_secs, 0).unwrap_or_else(Utc::now);
            Some(TraderTrade {
                slug,
                condition_id,
                side,
                price,
                size_usd,
                tx_hash: e.tx_hash,
                timestamp,
                outcome_index: e.outcome_index,
                outcome: e.outcome,
                title: e.title,
                event_slug: e.event_slug,
            })
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Monitor
// ---------------------------------------------------------------------------

/// Polls the Polymarket data API for leaderboard and trader activity.
///
/// Pass `&PgPortfolio` directly to each method — no long-lived state beyond
/// the HTTP client.
pub struct CopyTraderMonitor {
    http: Client,
}

impl CopyTraderMonitor {
    /// Build a new monitor with a shared `reqwest::Client`.
    pub fn new(http: Client) -> Self {
        Self { http }
    }

    /// One page of `/activity` over the window `[start, end]`, retried through the
    /// transient timeouts the data-api throws under a depth-1000 fan-out.
    ///
    /// Note the parameter names: `start`/`end`/`offset`/`limit` are the ones the server
    /// actually honours. The long-standing `startTs` this poll used before is silently
    /// IGNORED (verified live 2026-07-13, and already known to `fetch_full_history`) —
    /// which is why the "incremental" poll was really re-reading the newest 100 events
    /// every cycle and losing everything older on first sight.
    ///
    /// A 429 is NOT retried here: it is the one signal that means "back off", so it
    /// propagates immediately and the caller leaves the cursor where it was.
    async fn fetch_activity_page(
        &self,
        wallet: &str,
        start_ts: i64,
        end_ts: i64,
        offset: usize,
    ) -> Result<Vec<ActivityEvent>> {
        debug_assert!(
            offset <= ACTIVITY_MAX_OFFSET,
            "offset past the server ceiling"
        );
        let url = format!(
            "{DATA_API}/activity?user={wallet}&type=TRADE&start={start_ts}&end={end_ts}\
             &limit={ACTIVITY_PAGE_SIZE}&offset={offset}"
        );

        let mut last_err = None;
        for attempt in 0..=ACTIVITY_PAGE_RETRIES {
            if attempt > 0 {
                tokio::time::sleep(Duration::from_millis(200 << attempt)).await;
            }

            let resp = match self.http.get(&url).timeout(REQUEST_TIMEOUT).send().await {
                Ok(r) => r,
                Err(e) => {
                    last_err = Some(anyhow::Error::new(e).context("activity request failed"));
                    continue;
                }
            };

            // Capture the status BEFORE `error_for_status` (which discards it). A 429
            // must surface as Err so the cursor is not advanced, and is counted for the
            // scale gate.
            if resp.status() == reqwest::StatusCode::TOO_MANY_REQUESTS {
                crate::metrics::record_data_api_429();
                return Err(anyhow::anyhow!("data-api 429 (rate-limited) for {wallet}"));
            }

            match resp.error_for_status() {
                Ok(r) => match r.json::<Vec<ActivityEvent>>().await {
                    Ok(events) => return Ok(events),
                    Err(e) => {
                        last_err = Some(anyhow::Error::new(e).context("activity JSON parse failed"))
                    }
                },
                Err(e) => {
                    last_err = Some(anyhow::Error::new(e).context("activity returned non-2xx"))
                }
            }
        }
        Err(last_err.unwrap_or_else(|| anyhow::anyhow!("activity page offset={offset} failed")))
    }

    /// Read EVERY event in `[start_ts, end_ts]`, or report that the window is too dense
    /// to be read at all.
    ///
    /// Pages newest→oldest on `offset` until a short page (the window is exhausted).
    /// `Ok(None)` means the [`ACTIVITY_MAX_OFFSET`] ceiling was reached with events
    /// still unread: the window holds more than 3 500 events and the server will not
    /// page past that, so the caller must narrow it rather than page on.
    async fn drain_activity_window(
        &self,
        wallet: &str,
        start_ts: i64,
        end_ts: i64,
    ) -> Result<Option<Vec<ActivityEvent>>> {
        let mut events: Vec<ActivityEvent> = Vec::new();
        for page in 0..ACTIVITY_MAX_PAGES {
            let offset = page * ACTIVITY_PAGE_SIZE;
            let batch = self
                .fetch_activity_page(wallet, start_ts, end_ts, offset)
                .await?;
            let got = batch.len();
            events.extend(batch);
            // Short page ⇒ nothing left in this window: it is fully covered.
            if got < ACTIVITY_PAGE_SIZE {
                return Ok(Some(events));
            }
        }
        // Ran out of reachable offsets with the window still producing full pages.
        Ok(None)
    }

    /// Fetch trade activity for `wallet` since `since`, covering a bounded window
    /// COMPLETELY rather than skimming the newest page of it.
    ///
    /// Returns BOTH sides (BUY and SELL) — `parse_activity_events` no longer filters by
    /// side; downstream consumers (consensus window vs durable ledger) decide what they
    /// keep.
    ///
    /// The contract that matters is [`PollResult::covered_through`]: every event in
    /// `[since, covered_through]` has been read, so that instant — and nothing later —
    /// is a safe cursor. A wallet with more history than one poll's budget is drained
    /// across successive cycles, 6h at a time, and never skipped.
    ///
    /// A 429 surfaces as `Err` (after recording the metric) so the caller does not
    /// advance its cursor and re-fetches the range next cycle.
    #[tracing::instrument(skip(self), fields(wallet = %wallet))]
    pub async fn poll_trader_activity(
        &self,
        wallet: &str,
        since: DateTime<Utc>,
    ) -> Result<PollResult> {
        let now = Utc::now();
        if since >= now {
            return Ok(PollResult {
                trades: Vec::new(),
                raw_count: 0,
                complete: true,
                covered_through: Some(now),
            });
        }

        // Cover at most ACTIVITY_WINDOW_SECS per poll. Steady state (cursor ~1 min old)
        // this is just [since, now] in a single page; a first-sight wallet backfills 6h
        // per cycle instead of trying to inhale 48h at once.
        let full_span = (now - since).num_seconds();
        let mut span = full_span.min(ACTIVITY_WINDOW_SECS);

        let (events, end) = loop {
            let end = (since + chrono::Duration::seconds(span)).min(now);
            match self
                .drain_activity_window(wallet, since.timestamp(), end.timestamp())
                .await?
            {
                Some(events) => break (events, end),
                None if span / 2 >= ACTIVITY_MIN_WINDOW_SECS => {
                    // >3 500 events in this window and the server will not page deeper.
                    // Halve the span and try again: a narrower window holds fewer events.
                    span /= 2;
                    tracing::debug!(
                        wallet = %wallet, span,
                        "Activity window too dense to page; halving"
                    );
                }
                None => {
                    // Even the minimum window is denser than the API will serve. We
                    // cannot read it, and re-polling it forever would wedge this wallet
                    // and starve every other one behind it. Take the newest 3 500 events
                    // we CAN see, advance past the window, and record the hole loudly —
                    // an unreadable range is a fact to surface, not to hide.
                    crate::metrics::record_activity_window_unreadable();
                    tracing::warn!(
                        wallet = %wallet,
                        window_secs = span,
                        "Activity window exceeds the server's 3 500-event page ceiling even at \
                         the minimum span — CAPTURE GAP: the oldest events in this window are \
                         unreachable and are being skipped"
                    );
                    let end = (since + chrono::Duration::seconds(span)).min(now);
                    let partial = self
                        .fetch_activity_page(wallet, since.timestamp(), end.timestamp(), 0)
                        .await
                        .unwrap_or_default();
                    break (partial, end);
                }
            }
        };

        let raw_count = events.len();
        let trades: Vec<TraderTrade> = parse_activity_events(events);
        let complete = end >= now;

        tracing::info!(
            wallet = %wallet,
            since = %since.format("%Y-%m-%d %H:%M"),
            covered_through = %end.format("%Y-%m-%d %H:%M"),
            raw_events = raw_count,
            parsed_trades = trades.len(),
            complete,
            "Trader activity fetched"
        );

        Ok(PollResult {
            trades,
            raw_count,
            complete,
            covered_through: Some(end),
        })
    }

    /// Harvest EVERY trade in one market — by every wallet, not just the ones we follow.
    ///
    /// This is the discovery primitive the deep-universe run exists for. The leaderboard
    /// sorts by absolute PnL, which is a bankroll-and-volume sort: measured on our own
    /// pool, `corr(rank, ROI) = -0.05` — rank says essentially NOTHING about efficiency.
    /// So an efficient, low-volume specialist may never appear on it at ANY depth, and
    /// widening the rank cutoff cannot find them. Measured: of the 4,341 wallets trading
    /// recent weather markets, our depth-1000 leaderboard pool contained 50 (1.2%).
    ///
    /// Enumerating from the MARKET side inverts that: it costs O(markets) instead of
    /// O(wallets) — one sweep of the ~450 daily weather+esports markets reaches the whole
    /// population, where polling those wallets individually would need ~167 req/s and blow
    /// the API budget outright.
    ///
    /// Pages `offset` 0..[`ACTIVITY_MAX_OFFSET`] (the same server ceiling as `/activity`).
    /// A market busier than that is truncated at the ceiling — logged, not silent.
    pub async fn harvest_market_trades(&self, condition_id: &str) -> Result<Vec<HarvestedTrade>> {
        let mut out: Vec<HarvestedTrade> = Vec::new();
        let mut offset = 0usize;

        loop {
            let url = format!(
                "{DATA_API}/trades?market={condition_id}&limit={ACTIVITY_PAGE_SIZE}&offset={offset}"
            );
            let resp = self
                .http
                .get(&url)
                .timeout(REQUEST_TIMEOUT)
                .send()
                .await
                .context("market trades request failed")?;

            if resp.status() == reqwest::StatusCode::TOO_MANY_REQUESTS {
                crate::metrics::record_data_api_429();
                return Err(anyhow::anyhow!("data-api 429 on /trades for {condition_id}"));
            }

            let rows: Vec<MarketTrade> = resp
                .error_for_status()
                .context("market trades returned non-2xx")?
                .json()
                .await
                .context("market trades JSON parse failed")?;

            let got = rows.len();
            for r in rows {
                if let Some(h) = market_trade_to_harvested(r) {
                    out.push(h);
                }
            }

            if got < ACTIVITY_PAGE_SIZE {
                break;
            }
            offset += ACTIVITY_PAGE_SIZE;
            if offset > ACTIVITY_MAX_OFFSET {
                tracing::warn!(
                    condition_id,
                    trades = out.len(),
                    "Market busier than the /trades offset ceiling — oldest trades in this \
                     market are unreachable and were NOT harvested"
                );
                break;
            }
            tokio::time::sleep(LEADERBOARD_PAGE_DELAY).await;
        }

        Ok(out)
    }

    /// Fetch a wallet's COMPLETE reachable trade history via **offset pagination**
    /// (`limit=500`, `offset` 0..10_000) — the correct params (`startTs` is silently
    /// ignored by the data-api; `offset`/`limit=500` and `start`/`end` DO work,
    /// verified live 2026-07-03). Pages newest→older until a short page or the
    /// 10_000-offset server cap. A wallet exceeding the cap is a high-frequency
    /// market-maker (10k+ trades) — capped here on purpose; genuine traders have far
    /// fewer and are captured completely. Returns ALL parsed trades (BUY and SELL);
    /// dedup is the DB's job (`insert_trader_fills` ON CONFLICT). 429 → bounded
    /// backoff-and-retry so a transient rate-limit doesn't truncate a wallet.
    pub async fn fetch_full_history(&self, wallet: &str) -> Result<Vec<TraderTrade>> {
        const PAGE: usize = 500;
        const MAX_OFFSET: usize = 10_000;
        let mut all: Vec<TraderTrade> = Vec::new();
        let mut offset = 0usize;
        'pages: loop {
            let url = format!(
                "{DATA_API}/activity?user={wallet}&type=TRADE&limit={PAGE}&offset={offset}"
            );
            let mut attempt = 0u32;
            let events: Vec<ActivityEvent> = loop {
                let resp = self
                    .http
                    .get(&url)
                    .timeout(REQUEST_TIMEOUT)
                    .send()
                    .await
                    .context("backfill activity request failed")?;
                let status = resp.status();
                // Throttle signals — a burst of sequential backfill requests draws
                // 429 OR a plain 403 (verified: throttled wallets return 200 again
                // after a pause) or a transient 5xx. Back off with escalating delay
                // and retry; after a few tries return the PARTIAL history (never a
                // hard error) so one throttled wallet can't abort the run — the
                // idempotent re-run completes it.
                if status == reqwest::StatusCode::TOO_MANY_REQUESTS
                    || status == reqwest::StatusCode::FORBIDDEN
                    || status.is_server_error()
                {
                    if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
                        crate::metrics::record_data_api_429();
                    }
                    attempt += 1;
                    if attempt > 6 {
                        tracing::warn!(wallet = %wallet, %status, got = all.len(),
                            "backfill: throttled, keeping partial history");
                        return Ok(all);
                    }
                    tokio::time::sleep(Duration::from_secs(2 * attempt as u64)).await;
                    continue;
                }
                // 400 = offset past the wallet's available data (or the 10k server
                // cap) — the clean end-of-history signal, NOT an error.
                if status == reqwest::StatusCode::BAD_REQUEST {
                    break 'pages;
                }
                break resp
                    .error_for_status()
                    .context("backfill activity non-2xx")?
                    .json()
                    .await
                    .context("backfill activity JSON parse failed")?;
            };
            let n = events.len();
            all.extend(parse_activity_events(events));
            offset += PAGE;
            if n < PAGE || offset > MAX_OFFSET {
                break;
            }
            // Gentle pacing between pages (well under the data-api rate limit).
            tokio::time::sleep(Duration::from_millis(200)).await;
        }
        Ok(all)
    }

    /// Iterate over all active traders, poll their recent activity in parallel,
    /// deduplicate against the `copy_trade_events` table, and return unseen trades.
    ///
    /// Each new trade is persisted to `copy_trade_events` before being returned
    /// so subsequent calls within the same run do not emit the same signal twice.
    #[tracing::instrument(skip(self, portfolio))]
    pub async fn detect_new_trades(&self, portfolio: &PgPortfolio) -> Result<Vec<DetectedTrade>> {
        let traders = portfolio
            .get_active_traders()
            .await
            .context("get_active_traders")?;

        tracing::info!(count = traders.len(), "Polling active traders");

        // Poll all traders concurrently, but BOUNDED by a semaphore so a large
        // tracked universe can't burst hundreds of simultaneous /activity requests
        // into the data-api (429 storm). Mirrors the consensus-cycle fan-out.
        let sem = Arc::new(Semaphore::new(COPY_TRADE_MAX_CONCURRENCY.max(1)));
        let poll_futures = traders.iter().map(|trader| {
            let since = trader
                .last_checked_at
                .unwrap_or_else(|| Utc::now() - chrono::Duration::hours(24));
            let name = trader
                .username
                .as_deref()
                .unwrap_or(&trader.proxy_wallet[..8.min(trader.proxy_wallet.len())])
                .to_string();
            tracing::info!(
                trader = %name,
                wallet = %trader.proxy_wallet,
                since = %since.format("%Y-%m-%d %H:%M"),
                "Polling trader"
            );
            let sem = Arc::clone(&sem);
            async move {
                let _permit = sem.acquire_owned().await;
                let result = self.poll_trader_activity(&trader.proxy_wallet, since).await;
                (trader, name, result)
            }
        });
        let poll_results = join_all(poll_futures).await;

        let now = Utc::now();
        let mut detected = Vec::new();

        // Process results sequentially for DB deduplication.
        for (trader, name, poll_result) in poll_results {
            let trades = match poll_result {
                Ok(r) => r.trades,
                Err(e) => {
                    tracing::warn!(
                        trader = %name,
                        wallet = %trader.proxy_wallet,
                        err = %e,
                        "Failed to poll trader activity, skipping"
                    );
                    continue;
                }
            };

            let mut new_count = 0usize;
            let mut skipped_count = 0usize;
            let mut stale_count = 0usize;

            for trade in trades {
                // Skip trades that are too old — market price has likely moved.
                let age_secs = (now - trade.timestamp).num_seconds();
                if age_secs > STALE_TRADE_SECS {
                    stale_count += 1;
                    continue;
                }

                let already_seen = portfolio
                    .is_copy_trade_seen(
                        &trader.proxy_wallet,
                        &trade.condition_id,
                        &trade.side,
                        trade.price,
                    )
                    .await
                    .context("is_copy_trade_seen")?;

                if already_seen {
                    skipped_count += 1;
                    continue;
                }

                let event = NewCopyTradeEvent {
                    trader_wallet: trader.proxy_wallet.clone(),
                    market_id: trade.condition_id.clone(),
                    condition_id: trade.condition_id.clone(),
                    side: trade.side.clone(),
                    price: trade.price,
                    size_usd: trade.size_usd,
                    tx_hash: trade.tx_hash.clone(),
                };

                portfolio
                    .save_copy_trade_event(&event)
                    .await
                    .context("save_copy_trade_event")?;

                detected.push(DetectedTrade {
                    trader_wallet: trader.proxy_wallet.clone(),
                    trade,
                });
                new_count += 1;
            }

            tracing::info!(
                trader = %name,
                new = new_count,
                skipped = skipped_count,
                stale = stale_count,
                "Trader poll complete"
            );

            // Stamp the poll timestamp regardless of whether any trades were found.
            if let Err(e) = portfolio.update_trader_checked(&trader.proxy_wallet).await {
                tracing::warn!(
                    wallet = %trader.proxy_wallet,
                    err = %e,
                    "Failed to update last_checked_at"
                );
            }
        }

        tracing::info!(count = detected.len(), "New copy-trade events detected");
        Ok(detected)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Real `/trades?market=` row shape, captured live 2026-07-13.
    const MARKET_TRADE_JSON: &str = r#"[{
      "proxyWallet":"0x06AE9A98783712FB490e9500481c67c3655af059",
      "side":"BUY",
      "conditionId":"0x507b6ff91651f4305eb0891afc31c44bb2b236997410f93afbbf4eaf9233b1c7",
      "size":10.0,
      "price":0.77,
      "timestamp":1783959212,
      "title":"Highest temperature in Tokyo",
      "slug":"highest-temperature-in-tokyo-on-july-13",
      "eventSlug":"",
      "outcome":"Yes",
      "outcomeIndex":0,
      "transactionHash":"0xd872e371968dc1ae75425a2138701a5c8566865e"
    }]"#;

    #[test]
    fn harvested_trade_converts_shares_to_usd() {
        // `/trades` reports SIZE IN SHARES; `/activity` reports `usdcSize` in DOLLARS.
        // Treating one as the other would silently mis-scale every harvested wallet's stake
        // and corrupt the very profiles the harvest exists to build. 10 shares @ $0.77 = $7.70.
        let rows: Vec<MarketTrade> =
            serde_json::from_str(MARKET_TRADE_JSON).expect("fixture must parse");
        let h = market_trade_to_harvested(rows.into_iter().next().unwrap()).expect("maps");
        assert!(
            (h.trade.size_usd - 7.70).abs() < 1e-6,
            "size_usd must be shares × price (got {})",
            h.trade.size_usd
        );
        assert_eq!(h.wallet, h.wallet.to_lowercase(), "wallet is lowercased for join keys");
        assert_eq!(h.trade.outcome_index, Some(0));
        assert_eq!(h.trade.side, "BUY");
        // Empty eventSlug is normalised away rather than stored as "".
        assert_eq!(h.trade.event_slug, None);
    }

    #[test]
    fn harvested_trade_without_a_wallet_is_dropped() {
        // A row we cannot attribute is useless to a per-wallet profile — drop it rather than
        // inventing an owner.
        let json = r#"[{"side":"BUY","price":0.5,"size":1.0,"timestamp":1783959212,
                        "conditionId":"0xabc","slug":"s","outcomeIndex":0}]"#;
        let rows: Vec<MarketTrade> = serde_json::from_str(json).unwrap();
        assert!(market_trade_to_harvested(rows.into_iter().next().unwrap()).is_none());
    }

    // Real API response shape captured 2026-03-15
    const ACTIVITY_JSON: &str = r#"[
        {
            "proxyWallet": "0x37c1874a60d348903594a96703e0507c518fc53a",
            "timestamp": 1773601939,
            "conditionId": "0xfab8520004b4d201119f0362dc8678e8cf7f11b514efc48bc5a48aebf7974b50",
            "type": "TRADE",
            "size": 19.6,
            "usdcSize": 9.604,
            "transactionHash": "0x36b6c841eb1",
            "price": 0.49,
            "asset": "87207434043876055147",
            "side": "BUY",
            "outcomeIndex": 0,
            "title": "Spread: Trail Blazers (-8.5)",
            "slug": "nba-por-phi-2026-03-15-spread-away-8pt5",
            "icon": "https://example.com/icon.png",
            "eventSlug": "nba-por-phi-2026-03-15",
            "outcome": "Trail Blazers",
            "name": "CemeterySun",
            "pseudonym": "Pale-Bend",
            "bio": "",
            "profileImage": ""
        },
        {
            "proxyWallet": "0x37c1874a60d348903594a96703e0507c518fc53a",
            "timestamp": 1773601939,
            "conditionId": "0x65c3ff402d81e756af732fd67ea6521b15395206d2d77b8b2b006c212f620981",
            "type": "TRADE",
            "size": 1554.74,
            "usdcSize": 855.107,
            "transactionHash": "0x197d26499737",
            "price": 0.55,
            "asset": "87796361570300895",
            "side": "BUY",
            "outcomeIndex": 0,
            "title": "Spread: Bucks (-6.5)",
            "slug": "nba-ind-mil-2026-03-15-spread-home-6pt5",
            "icon": "https://example.com/icon2.png",
            "eventSlug": "nba-ind-mil-2026-03-15",
            "outcome": "Bucks",
            "name": "CemeterySun",
            "pseudonym": "Pale-Bend",
            "bio": "",
            "profileImage": ""
        }
    ]"#;

    /// Verify that the real API response shape deserializes correctly and all
    /// mandatory fields are extracted — this guards against the previous bug
    /// where `marketId` (non-existent) caused every trade to be dropped.
    #[test]
    fn test_parse_activity_events_real_shape() {
        let events: Vec<ActivityEvent> = serde_json::from_str(ACTIVITY_JSON).unwrap();
        assert_eq!(events.len(), 2, "should deserialize both events");

        let trades = parse_activity_events(events);
        assert_eq!(trades.len(), 2, "both trades should survive parsing");

        let t = &trades[0];
        assert_eq!(t.slug, "nba-por-phi-2026-03-15-spread-away-8pt5");
        assert_eq!(
            t.condition_id,
            "0xfab8520004b4d201119f0362dc8678e8cf7f11b514efc48bc5a48aebf7974b50"
        );
        assert_eq!(t.side, "BUY");
        assert_eq!(t.price, 0.49);
        // usdcSize, not size (shares)
        assert_eq!(t.size_usd, 9.604);
        assert_eq!(t.tx_hash.as_deref(), Some("0x36b6c841eb1"));
        assert_eq!(t.timestamp.timestamp(), 1773601939);
    }

    #[test]
    fn test_parse_drops_events_missing_mandatory_fields() {
        // Missing slug → should be dropped
        let json = r#"[
            {"conditionId": "0xabc", "side": "BUY", "price": 0.5, "usdcSize": 10.0, "timestamp": 1000},
            {"slug": "some-market", "conditionId": "0xdef", "side": "BUY", "price": 0.6, "usdcSize": 20.0, "timestamp": 2000}
        ]"#;
        let events: Vec<ActivityEvent> = serde_json::from_str(json).unwrap();
        let trades = parse_activity_events(events);
        assert_eq!(trades.len(), 1, "event with missing slug should be dropped");
        assert_eq!(trades[0].slug, "some-market");
    }

    #[test]
    fn test_parse_uses_usdc_size_not_shares() {
        let json = r#"[{
            "slug": "market-a",
            "conditionId": "0xabc",
            "side": "SELL",
            "price": 0.9,
            "size": 1000.0,
            "usdcSize": 900.0,
            "timestamp": 1000
        }]"#;
        let events: Vec<ActivityEvent> = serde_json::from_str(json).unwrap();
        let trades = parse_activity_events(events);
        assert_eq!(trades.len(), 1);
        // Must be usdcSize (900), not size/shares (1000)
        assert_eq!(trades[0].size_usd, 900.0);
    }

    #[test]
    fn test_parse_usdc_size_defaults_to_zero_when_absent() {
        let json = r#"[{
            "slug": "market-b",
            "conditionId": "0xabc",
            "side": "BUY",
            "price": 0.5,
            "timestamp": 1000
        }]"#;
        let events: Vec<ActivityEvent> = serde_json::from_str(json).unwrap();
        let trades = parse_activity_events(events);
        assert_eq!(trades.len(), 1);
        assert_eq!(trades[0].size_usd, 0.0);
    }

    #[tokio::test]
    #[ignore] // hits real API
    async fn test_fetch_leaderboard_live() {
        let http = Client::new();
        let entries = fetch_leaderboard(&http, "ALL").await.unwrap();
        assert!(!entries.is_empty(), "leaderboard should have entries");
        assert!(entries.len() <= LEADERBOARD_SECTION_LIMIT);
        assert_eq!(entries[0].rank, 1);
        assert!(!entries[0].name.is_empty());
        assert!(entries[0].pnl > 0.0);
        println!(
            "{}",
            format_multi_leaderboard(&[("All Time", entries.as_slice())])
        );
    }

    #[tokio::test]
    #[ignore] // hits real API
    async fn test_poll_trader_activity_live() {
        let monitor = CopyTraderMonitor::new(Client::new());
        // Top leaderboard trader from 2026-03-15
        let wallet = "0x37c1874a60d348903594a96703e0507c518fc53a";
        let since = chrono::Utc::now() - chrono::Duration::hours(24);
        let result = monitor.poll_trader_activity(wallet, since).await.unwrap();
        assert!(
            !result.trades.is_empty(),
            "active trader should have recent trades"
        );
        assert!(
            result.raw_count >= result.trades.len(),
            "raw_count is the page length"
        );
        for t in &result.trades {
            assert!(!t.slug.is_empty(), "slug must be populated");
            assert!(!t.condition_id.is_empty(), "condition_id must be populated");
            assert!(t.price > 0.0 && t.price < 1.0, "price must be in (0,1)");
            assert!(t.size_usd >= 0.0, "size_usd must be non-negative");
        }
    }

    fn raw(wallet: &str, pnl: f64) -> LeaderboardRaw {
        LeaderboardRaw {
            wallet: wallet.to_string(),
            username: Some(wallet.to_string()),
            rank: 0,
            pnl,
            volume: pnl * 2.0,
        }
    }

    /// Three contiguous pages merge into one PnL-descending pool with contiguous
    /// global rank and no gaps — the core offset-pagination invariant.
    #[test]
    fn test_merge_pages_contiguous_rank() {
        // Page 0 (ranks 1-3), page 1 (4-6), page 2 (7-9), each PnL-descending and
        // globally continuous (no overlap), as the live API returns them.
        let rows = vec![
            raw("0xa", 900.0),
            raw("0xb", 800.0),
            raw("0xc", 700.0),
            raw("0xd", 600.0),
            raw("0xe", 500.0),
            raw("0xf", 400.0),
            raw("0xg", 300.0),
            raw("0xh", 200.0),
            raw("0xi", 100.0),
        ];
        let merged = merge_leaderboard_pages(rows, 100);
        assert_eq!(merged.len(), 9);
        // Contiguous rank 1..=9, PnL strictly descending.
        for (i, r) in merged.iter().enumerate() {
            assert_eq!(r.rank, (i + 1) as i32, "rank must be contiguous i+1");
        }
        assert_eq!(merged[0].wallet, "0xa");
        assert_eq!(merged[8].wallet, "0xi");
        for w in merged.windows(2) {
            assert!(w[0].pnl >= w[1].pnl, "PnL must be descending");
        }
    }

    /// A wallet appearing on two pages (overlap) is deduped to a single row,
    /// keeping the higher-PnL sighting; global rank stays contiguous.
    #[test]
    fn test_merge_pages_dedup_by_wallet() {
        let rows = vec![
            raw("0xa", 900.0),
            raw("0xb", 800.0),
            raw("0xa", 950.0), // duplicate wallet, higher PnL — should win
            raw("0xc", 700.0),
        ];
        let merged = merge_leaderboard_pages(rows, 100);
        assert_eq!(merged.len(), 3, "duplicate wallet collapsed to one row");
        assert_eq!(merged[0].wallet, "0xa");
        assert_eq!(merged[0].pnl, 950.0, "kept the higher-PnL sighting");
        for (i, r) in merged.iter().enumerate() {
            assert_eq!(r.rank, (i + 1) as i32);
        }
    }

    /// `depth` caps the merged pool and re-ranks over the survivors only.
    #[test]
    fn test_merge_pages_depth_cap() {
        let rows = vec![
            raw("0xa", 900.0),
            raw("0xb", 800.0),
            raw("0xc", 700.0),
            raw("0xd", 600.0),
            raw("0xe", 500.0),
        ];
        let merged = merge_leaderboard_pages(rows, 3);
        assert_eq!(merged.len(), 3, "capped at depth");
        assert_eq!(merged[2].wallet, "0xc");
        assert_eq!(merged[2].rank, 3);
    }

    /// SCALE-GATE MEASUREMENT (Phase 2): poll a real depth-200 universe through the
    /// same semaphore-bounded fan-out the consensus cycle uses, and report the
    /// wall-clock + 429 count. This is the regression surface — if this stays well
    /// inside the ~120s cycle window with zero 429s, the semaphore alone is the
    /// poll-cadence budget and no cadence tiering is needed.
    #[tokio::test]
    #[ignore] // hits real API ~200 times; run explicitly to read the number
    async fn measure_deep_poll_load_live() {
        let http = Client::new();
        let universe = fetch_leaderboard_paged(&http, "WEEK", 200).await.unwrap();
        let wallets: Vec<String> = universe.iter().map(|e| e.wallet.clone()).collect();
        let n = wallets.len();
        let monitor = CopyTraderMonitor::new(http);
        let since = Utc::now() - chrono::Duration::hours(48);

        let before_429 = crate::metrics::data_api_429_count();
        let t0 = std::time::Instant::now();
        let sem = Arc::new(Semaphore::new(COPY_TRADE_MAX_CONCURRENCY.max(1)));
        let polls = wallets.iter().map(|w| {
            let sem = Arc::clone(&sem);
            let monitor = &monitor;
            async move {
                let _permit = sem.acquire_owned().await;
                monitor.poll_trader_activity(w, since).await.is_ok()
            }
        });
        let results = join_all(polls).await;
        let elapsed = t0.elapsed();
        let ok = results.iter().filter(|r| **r).count();
        let n429 = crate::metrics::data_api_429_count() - before_429;

        println!(
            "SCALE-GATE: polled {n} deep traders @ concurrency {COPY_TRADE_MAX_CONCURRENCY} in \
             {:.1}s ({ok} ok, {} failed), data-api 429s: {n429}",
            elapsed.as_secs_f64(),
            n - ok,
        );
        // The fan-out must clear the universe well inside a ~120s consensus cycle.
        assert!(
            elapsed.as_secs() < 120,
            "depth-200 poll fan-out took {:.1}s — approaching the cycle window; \
             cadence tiering would be required",
            elapsed.as_secs_f64()
        );
    }

    #[tokio::test]
    #[ignore] // hits real API
    async fn test_fetch_leaderboard_paged_live() {
        let http = Client::new();
        let entries = fetch_leaderboard_paged(&http, "WEEK", 120).await.unwrap();
        assert!(entries.len() >= 100, "should page past the 50-row cap");
        // Ranks contiguous from 1, PnL descending — proves offset pagination.
        for (i, r) in entries.iter().enumerate() {
            assert_eq!(r.rank, (i + 1) as i32);
        }
        for w in entries.windows(2) {
            assert!(w[0].pnl >= w[1].pnl, "PnL descending across page seams");
        }
        // No duplicate wallets across pages.
        let mut wallets: Vec<&str> = entries.iter().map(|e| e.wallet.as_str()).collect();
        let n = wallets.len();
        wallets.sort_unstable();
        wallets.dedup();
        assert_eq!(wallets.len(), n, "no duplicate wallets across page seams");
    }
}
