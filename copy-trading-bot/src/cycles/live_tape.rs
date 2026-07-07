//! F1 live CLOB price tape (migration 040) — flag `LIVE_TAPE`, default OFF.
//!
//! Records the executable order book for every tracked-market asset in real time
//! into `clob_price_tape`, so the price path around any sharp fill is
//! reconstructable OFFLINE at 1s granularity (against each fill's clean `ts`).
//! This is the measurement substrate for `latency_edge_curve.py` — the poller
//! stays the completeness spine; this task is best-effort and additive.
//!
//! The connect/subscribe/PING/reconnect loop is COPIED from
//! `trading-bot/src/scanner/ws.rs` (the two protocols — CLOB text-PING here vs
//! JSON-RPC in live_fills — differ, so a shared abstraction serves neither
//! cleanly; see the plan's Item 8). Event types under `custom_feature_enabled`
//! are `book` (snapshot) and `price_change` (delta); both carry a top-level
//! ms-epoch `timestamp` (the exchange clock) and price_change carries
//! best_bid/best_ask directly (reports/PROTOCOL_FINDINGS.md).
//!
//! When `LIVE_TAPE=false` (default) `run_live_tape` is never spawned — the binary
//! is byte-identical to pre-040.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use chrono::{DateTime, TimeZone, Utc};
use futures_util::{SinkExt, StreamExt};
use serde_json::Value;
use tokio::sync::{mpsc, RwLock};
use tokio_tungstenite::tungstenite::Message;

use crate::config::CopyTradingConfig;
use crate::data::models::fetch_clob_market;
use crate::metrics;
use crate::storage::consensus::NewTapeTick;
use crate::storage::postgres::PgPortfolio;

const WS_URL: &str = "wss://ws-subscriptions-clob.polymarket.com/ws/market";
const PING_INTERVAL: Duration = Duration::from_secs(10);
const RECONNECT_DELAY: Duration = Duration::from_secs(5);
const CHANNEL_CAP: usize = 100_000; // bounded; overflow → drop + metric (best-effort)
const WRITE_BATCH: usize = 500;
const TOKEN_RESOLVE_THROTTLE: Duration = Duration::from_millis(120); // dense_capture citizenship

/// The tracked-only subscription universe: the token list plus, per token, its
/// (condition_id, outcome_index) so tape rows carry provenance without a 2nd
/// CLOB call. Swapped wholesale by the refresh loop; a version counter tells the
/// reader pool to re-shard on the next reconnect (the `ws.rs` refresh mechanism).
#[derive(Default)]
struct Universe {
    tokens: Vec<String>,
    meta: HashMap<String, (String, i16)>, // token_id -> (condition_id, outcome_index)
}

fn parse_f64(v: &Value) -> Option<f64> {
    v.as_str().and_then(|s| s.parse::<f64>().ok())
}

fn parse_exch_ts(v: &Value) -> Option<DateTime<Utc>> {
    let ms = v.as_str()?.parse::<i64>().ok()?;
    Utc.timestamp_millis_opt(ms).single()
}

/// Parse one WS text frame into zero or more tape ticks (book / price_change).
/// `meta` maps asset_id → (condition_id, outcome_index) for this worker's shard.
fn parse_frame(text: &str, meta: &HashMap<String, (String, i16)>) -> Vec<NewTapeTick> {
    let json: Value = match serde_json::from_str(text) {
        Ok(v) => v,
        Err(_) => return Vec::new(),
    };
    let items: Vec<&Value> = match json.as_array() {
        Some(arr) => arr.iter().collect(),
        None => vec![&json],
    };
    let recv_at = Utc::now();
    let mut out = Vec::new();
    for it in items {
        match it["event_type"].as_str().unwrap_or("") {
            "book" => {
                let asset_id = match it["asset_id"].as_str() {
                    Some(a) => a.to_string(),
                    None => continue,
                };
                // bids/asks: [{price,size}]. best_bid = max bid, best_ask = min ask.
                let best_bid = it["bids"]
                    .as_array()
                    .and_then(|a| a.iter().filter_map(|b| parse_f64(&b["price"])).fold(None, |m, p| {
                        Some(m.map_or(p, |mx: f64| mx.max(p)))
                    }));
                let best_ask = it["asks"]
                    .as_array()
                    .and_then(|a| a.iter().filter_map(|b| parse_f64(&b["price"])).fold(None, |m, p| {
                        Some(m.map_or(p, |mn: f64| mn.min(p)))
                    }));
                let (condition_id, outcome_index) = meta
                    .get(&asset_id)
                    .map(|(c, o)| (Some(c.clone()), Some(*o)))
                    .unwrap_or((None, None));
                out.push(NewTapeTick {
                    asset_id,
                    condition_id,
                    outcome_index,
                    event_type: "book".to_string(),
                    best_bid,
                    best_ask,
                    last_price: parse_f64(&it["last_trade_price"]),
                    last_size: None,
                    side: None,
                    // A `book` is a re-sent SNAPSHOT (on subscribe/reconnect); its
                    // `timestamp` is the last-trade time, NOT "now" — it can be HOURS
                    // stale and would create phantom inversions in the exch_ts-ordered
                    // curve. Leave exch_ts NULL so the curve/ordering fall back to
                    // recv_at (the true observation time). Only price_change carries a
                    // trustworthy real-time exch_ts. (Adversarial review D2.)
                    exch_ts: None,
                    recv_at,
                });
            }
            "price_change" => {
                let top_ts = parse_exch_ts(&it["timestamp"]);
                let changes = match it["price_changes"].as_array() {
                    Some(c) => c,
                    None => continue,
                };
                for ch in changes {
                    let asset_id = match ch["asset_id"].as_str() {
                        Some(a) => a.to_string(),
                        None => continue,
                    };
                    let (condition_id, outcome_index) = meta
                        .get(&asset_id)
                        .map(|(c, o)| (Some(c.clone()), Some(*o)))
                        .unwrap_or((None, None));
                    out.push(NewTapeTick {
                        asset_id,
                        condition_id,
                        outcome_index,
                        event_type: "price_change".to_string(),
                        best_bid: parse_f64(&ch["best_bid"]),
                        best_ask: parse_f64(&ch["best_ask"]),
                        last_price: parse_f64(&ch["price"]),
                        last_size: parse_f64(&ch["size"]),
                        side: ch["side"].as_str().map(|s| s.to_string()),
                        exch_ts: parse_exch_ts(&ch["timestamp"]).or(top_ts),
                        recv_at,
                    });
                }
            }
            _ => {}
        }
    }
    out
}

/// One sharded connection worker (index `idx`). On each (re)connect it snapshots
/// its shard of the universe, subscribes, streams, and re-shards when the universe
/// version bumps. On-change dedup (best_bid,best_ask,last_price) is LOSSLESS for
/// the curve and drops the bulk of quote churn (measured ~90% at scale).
async fn conn_worker(
    idx: usize,
    max_subs: usize,
    universe: Arc<RwLock<Universe>>,
    version: Arc<AtomicU64>,
    tx: mpsc::Sender<NewTapeTick>,
    coalesce_ms: i64,
) {
    loop {
        let my_version = version.load(Ordering::Relaxed);
        let (shard, meta): (Vec<String>, HashMap<String, (String, i16)>) = {
            let u = universe.read().await;
            let start = idx * max_subs;
            if start >= u.tokens.len() {
                (Vec::new(), HashMap::new())
            } else {
                let end = (start + max_subs).min(u.tokens.len());
                let shard: Vec<String> = u.tokens[start..end].to_vec();
                let meta: HashMap<String, (String, i16)> = shard
                    .iter()
                    .filter_map(|t| u.meta.get(t).map(|m| (t.clone(), m.clone())))
                    .collect();
                (shard, meta)
            }
        };
        if shard.is_empty() {
            tokio::time::sleep(Duration::from_secs(15)).await;
            continue;
        }
        if let Err(e) = stream_shard(&shard, &meta, &version, my_version, &tx, coalesce_ms).await {
            tracing::warn!(worker = idx, err = %e, "live-tape shard stream ended, reconnecting");
        }
        tokio::time::sleep(RECONNECT_DELAY).await;
    }
}

/// Connect, subscribe to `shard`, stream until disconnect or a universe re-shard.
async fn stream_shard(
    shard: &[String],
    meta: &HashMap<String, (String, i16)>,
    version: &Arc<AtomicU64>,
    my_version: u64,
    tx: &mpsc::Sender<NewTapeTick>,
    coalesce_ms: i64,
) -> Result<()> {
    let (ws_stream, _) = tokio_tungstenite::connect_async(WS_URL)
        .await
        .context("live-tape WS connect failed")?;
    let (mut write, mut read) = ws_stream.split();

    let sub_msg = serde_json::json!({
        "assets_ids": shard,
        "type": "market",
        "custom_feature_enabled": true,
    });
    write
        .send(Message::Text(sub_msg.to_string().into()))
        .await
        .context("live-tape subscribe failed")?;
    tracing::info!(tokens = shard.len(), "live-tape subscribed");

    // Volume control — store only TOP-OF-BOOK INFLECTIONS (measured: at scale ~4000
    // raw ev/s the vast majority of events don't move (best_bid,best_ask)). Two filters:
    //   (1) on-change — emit only when (best_bid, best_ask) actually changes. `last_price`
    //       in a price_change is order-BOOK-LEVEL churn (not a trade), so it is NOT in the
    //       key — including it stored a row on every level flicker for no curve benefit.
    //   (2) keep-LAST coalesce — at most one row per asset per `coalesce_ms` bucket,
    //       emitting the SETTLED (last) value, flushed on bucket rollover OR when the asset
    //       goes quiet (stale-pending flush below). exch_ts on the row is always correct.
    // The curve reads best_ask; best_bid is kept (spread/mid/CLV) and also keyed on.
    type Key = (Option<u64>, Option<u64>);
    // per-asset: the latest tick of the CURRENT bucket (pending) + (bucket, key).
    let mut pending: HashMap<String, (i64, Key, NewTapeTick)> = HashMap::new();
    // per-asset: key of the last row actually emitted (for cross-bucket on-change dedup).
    let mut last_emitted: HashMap<String, Key> = HashMap::new();
    // encode f64 as bits so it's Hash/Eq (NaN not expected here)
    let key = |x: Option<f64>| x.map(|v| v.to_bits());
    let coalesce_ms = coalesce_ms.max(1);

    macro_rules! emit {
        ($asset:expr, $k:expr, $t:expr) => {
            match tx.try_send($t) {
                Ok(()) => {
                    last_emitted.insert($asset, $k);
                }
                Err(mpsc::error::TrySendError::Full(_)) => metrics::record_live_tape_dropped(1),
                Err(mpsc::error::TrySendError::Closed(_)) => return Ok(()),
            }
        };
    }

    let mut last_ping = std::time::Instant::now();
    // Run the read loop to a result, then ALWAYS flush remaining pending before
    // returning — so a version bump (re-shard) or a read error never discards an
    // asset's un-emitted current-bucket inflection (review D3).
    let result: Result<()> = loop {
        // re-shard when the refresh loop bumped the universe version
        if version.load(Ordering::Relaxed) != my_version {
            break Ok(());
        }
        if last_ping.elapsed() >= PING_INTERVAL {
            if let Err(e) = write.send(Message::Text("PING".into())).await {
                break Err(anyhow::anyhow!("live-tape PING failed: {e}"));
            }
            last_ping = std::time::Instant::now();
            // Stale-pending flush: emit the settled value of any asset that has gone
            // quiet (no tick in the current bucket) so its final inflection isn't held
            // in `pending` indefinitely (reliability — closes the keep-last tail).
            let cur_bucket = Utc::now().timestamp_millis() / coalesce_ms;
            let stale: Vec<String> = pending
                .iter()
                .filter(|(_, (b, _, _))| *b < cur_bucket)
                .map(|(a, _)| a.clone())
                .collect();
            for asset in stale {
                if let Some((_, fk, ft)) = pending.remove(&asset)
                    && last_emitted.get(&asset) != Some(&fk)
                {
                    emit!(asset.clone(), fk, ft);
                }
            }
        }
        let msg = match tokio::time::timeout(PING_INTERVAL, read.next()).await {
            Ok(Some(Ok(m))) => m,
            Ok(Some(Err(e))) => break Err(anyhow::anyhow!("live-tape read error: {e}")),
            Ok(None) => break Err(anyhow::anyhow!("live-tape stream ended")),
            Err(_) => continue, // timeout → loop to send PING
        };
        let text = match msg {
            Message::Text(t) => t,
            Message::Close(_) => break Err(anyhow::anyhow!("live-tape server closed")),
            _ => continue,
        };
        let text = text.as_ref();
        if text == "PONG" {
            continue;
        }
        for tick in parse_frame(text, meta) {
            let k: Key = (key(tick.best_bid), key(tick.best_ask));
            // Bucket on the LOCAL receive clock (monotonic within a connection — frames
            // arrive in order), NOT exch_ts: a late/stale exch_ts would roll the bucket
            // backward and emit a spurious past-timestamped row (review D4). The stored
            // row still carries exch_ts (real time for price_change) for the curve anchor.
            let sec = tick.recv_at.timestamp_millis() / coalesce_ms; // coalesce bucket index
            let asset = tick.asset_id.clone();
            // copy the pending second out so the borrow drops before remove/insert.
            let psec = pending.get(&asset).map(|(s, _, _)| *s);
            match psec {
                Some(s) if s == sec => {
                    // same second: replace pending with the newer state (keep-last).
                    pending.insert(asset, (sec, k, tick));
                }
                Some(_) => {
                    // second rolled: flush the SETTLED value of the prior second (on-change
                    // vs the last row we actually emitted), then stage the current tick.
                    let (_, fk, ft) = pending.remove(&asset).unwrap();
                    if last_emitted.get(&asset) != Some(&fk) {
                        emit!(asset.clone(), fk, ft);
                    }
                    pending.insert(asset, (sec, k, tick));
                }
                None => {
                    pending.insert(asset, (sec, k, tick));
                }
            }
        }
    };
    // Exit flush: emit every asset's remaining settled inflection (best-effort) so a
    // re-shard / disconnect never silently drops the current-bucket value (review D3).
    for (asset, (_, fk, ft)) in pending.drain() {
        if last_emitted.get(&asset) != Some(&fk) {
            let _ = tx.try_send(ft); // best-effort; channel-full drops are metered elsewhere
        }
    }
    result
}

/// Drain the tick channel in batches and append to `clob_price_tape`.
async fn writer(portfolio: Arc<PgPortfolio>, mut rx: mpsc::Receiver<NewTapeTick>) {
    let mut batch: Vec<NewTapeTick> = Vec::with_capacity(WRITE_BATCH);
    loop {
        let n = rx.recv_many(&mut batch, WRITE_BATCH).await;
        if n == 0 {
            break; // channel closed
        }
        match portfolio.insert_tape_ticks(&batch).await {
            Ok(rows) => metrics::record_live_tape_events(rows),
            Err(e) => tracing::warn!(err = %e, "live-tape insert failed (batch dropped)"),
        }
        batch.clear();
    }
}

/// Resolve the tracked-only universe (condition,outcome) → token_ids and swap it
/// into the shared `Universe`, bumping the version so workers re-shard.
async fn refresh_universe(
    portfolio: &PgPortfolio,
    http: &reqwest::Client,
    cfg: &CopyTradingConfig,
    universe: &Arc<RwLock<Universe>>,
    version: &Arc<AtomicU64>,
) -> Result<usize> {
    let pairs = portfolio.tracked_tape_assets(cfg.live_tape_lookback_hours).await?;
    let mut tokens = Vec::new();
    let mut meta = HashMap::new();
    // resolve condition_id (unique) once; map each wanted outcome to its token
    let mut seen_conditions: HashMap<String, crate::data::models::ClobMarket> = HashMap::new();
    for (cond, oidx) in &pairs {
        if !seen_conditions.contains_key(cond) {
            tokio::time::sleep(TOKEN_RESOLVE_THROTTLE).await;
            match fetch_clob_market(http, cond).await {
                Ok(m) => {
                    seen_conditions.insert(cond.clone(), m);
                }
                Err(_) => continue, // resolved/closed market — skip
            }
        }
        if let Some(m) = seen_conditions.get(cond)
            && let Some(tid) = m.outcome_token_id(*oidx)
        {
            let tid = tid.to_string();
            if meta.insert(tid.clone(), (cond.clone(), *oidx as i16)).is_none() {
                tokens.push(tid);
            }
        }
    }
    let n = tokens.len();
    // Only bump the version (which forces EVERY shard to drop + reconnect, re-sending
    // book snapshots and dropping in-flight pending) when the token SET actually
    // changed. The old unconditional bump reconnected all shards every refresh_secs
    // (default 300s) for no reason — churning reconnect dups and lost tails (review D2/D3).
    let changed = {
        let mut u = universe.write().await;
        let same = u.tokens.len() == tokens.len()
            && u.tokens.iter().collect::<std::collections::HashSet<_>>()
                == tokens.iter().collect::<std::collections::HashSet<_>>();
        u.tokens = tokens;
        u.meta = meta;
        !same
    };
    if changed {
        version.fetch_add(1, Ordering::Relaxed);
    }
    let conns = n.div_ceil(cfg.live_tape_max_subs.max(1));
    metrics::record_live_tape_universe(n as u64, conns as u64);
    if conns > cfg.live_tape_max_conns {
        tracing::warn!(
            tokens = n,
            connections_needed = conns,
            max_conns = cfg.live_tape_max_conns,
            "live-tape universe exceeds the connection pool — tail tokens UNCOVERED \
             (raise LIVE_TAPE_MAX_CONNS)"
        );
    }
    Ok(n)
}

/// Entry point: spawn reader pool + writer + refresh + prune. Never returns.
/// Spawned from `live.rs` only when `cfg.live_tape` is true.
pub async fn run_live_tape(
    portfolio: Arc<PgPortfolio>,
    http: reqwest::Client,
    cfg: Arc<CopyTradingConfig>,
) {
    let universe: Arc<RwLock<Universe>> = Arc::new(RwLock::new(Universe::default()));
    let version = Arc::new(AtomicU64::new(0));
    let (tx, rx) = mpsc::channel::<NewTapeTick>(CHANNEL_CAP);

    // initial universe resolve (block until we have something to subscribe to)
    if let Err(e) = refresh_universe(&portfolio, &http, &cfg, &universe, &version).await {
        tracing::warn!(err = %e, "live-tape initial universe resolve failed");
    }

    // writer
    tokio::spawn(writer(Arc::clone(&portfolio), rx));

    // reader pool (fixed max_conns; empty shards idle)
    for idx in 0..cfg.live_tape_max_conns {
        tokio::spawn(conn_worker(
            idx,
            cfg.live_tape_max_subs.max(1),
            Arc::clone(&universe),
            Arc::clone(&version),
            tx.clone(),
            cfg.tape_coalesce_ms,
        ));
    }
    drop(tx); // workers hold their own clones; writer closes when all drop

    // prune + compaction loop
    {
        let p = Arc::clone(&portfolio);
        let retention = cfg.tape_retention_hours;
        let compact_every = (cfg.tape_compact_hours.max(1) as u64) * 3600;
        tokio::spawn(async move {
            let mut elapsed: u64 = 0;
            loop {
                tokio::time::sleep(Duration::from_secs(3600)).await;
                elapsed += 3600;
                match p.prune_tape(retention).await {
                    Ok(n) if n > 0 => tracing::info!(pruned = n, "live-tape retention prune"),
                    Ok(_) => {}
                    Err(e) => tracing::warn!(err = %e, "live-tape prune failed"),
                }
                // compaction sweep: drop reconnect-boundary duplicate top-of-book rows
                // (keep the last 60s so it never races the live writer's tail).
                if elapsed.is_multiple_of(compact_every) {
                    match p.compact_tape(60).await {
                        Ok(n) if n > 0 => {
                            metrics::record_live_tape_compacted(n);
                            tracing::info!(compacted = n, "live-tape compaction");
                        }
                        Ok(_) => {}
                        Err(e) => tracing::warn!(err = %e, "live-tape compaction failed"),
                    }
                }
            }
        });
    }

    // refresh loop
    let refresh_secs = cfg.live_tape_refresh_secs.max(60);
    loop {
        tokio::time::sleep(Duration::from_secs(refresh_secs)).await;
        if let Err(e) = refresh_universe(&portfolio, &http, &cfg, &universe, &version).await {
            tracing::warn!(err = %e, "live-tape universe refresh failed");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_book_frame() {
        let meta = HashMap::from([("111".to_string(), ("0xcond".to_string(), 0i16))]);
        let frame = r#"{"event_type":"book","asset_id":"111","timestamp":"1783381780533",
            "last_trade_price":"0.46",
            "bids":[{"price":"0.44","size":"10"},{"price":"0.45","size":"5"}],
            "asks":[{"price":"0.47","size":"8"},{"price":"0.48","size":"3"}]}"#;
        let ticks = parse_frame(frame, &meta);
        assert_eq!(ticks.len(), 1);
        let t = &ticks[0];
        assert_eq!(t.event_type, "book");
        assert_eq!(t.best_bid, Some(0.45)); // max bid
        assert_eq!(t.best_ask, Some(0.47)); // min ask
        assert_eq!(t.last_price, Some(0.46));
        assert_eq!(t.condition_id.as_deref(), Some("0xcond"));
        assert_eq!(t.outcome_index, Some(0));
        // book is a re-sent SNAPSHOT → exch_ts is NULLed (its `timestamp` is stale);
        // the curve/ordering fall back to recv_at. Only price_change carries exch_ts.
        assert!(t.exch_ts.is_none());
    }

    #[test]
    fn parse_price_change_frame() {
        let meta = HashMap::new();
        let frame = r#"{"event_type":"price_change","timestamp":"1783381780533",
            "price_changes":[
              {"asset_id":"a","price":"0.41","size":"15","side":"BUY","best_bid":"0.49","best_ask":"0.50"},
              {"asset_id":"b","price":"0.59","size":"15","side":"SELL","best_bid":"0.58","best_ask":"0.60"}
            ]}"#;
        let ticks = parse_frame(frame, &meta);
        assert_eq!(ticks.len(), 2);
        assert_eq!(ticks[0].best_ask, Some(0.50));
        assert_eq!(ticks[0].side.as_deref(), Some("BUY"));
        assert_eq!(ticks[0].last_size, Some(15.0));
        assert_eq!(ticks[1].best_bid, Some(0.58));
        // meta absent → provenance null, but tick still emitted
        assert_eq!(ticks[1].condition_id, None);
    }

    #[test]
    fn ignores_unknown_events() {
        let ticks = parse_frame(r#"{"event_type":"last_trade_price","asset_id":"x","price":"0.5"}"#, &HashMap::new());
        assert!(ticks.is_empty());
    }
}
