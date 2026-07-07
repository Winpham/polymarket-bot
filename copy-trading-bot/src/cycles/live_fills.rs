//! F2 optional on-chain fast fills (migration 040) — flag `LIVE_FILLS`, default OFF.
//!
//! Observes Polymarket `OrderFilled` logs on Polygon and writes tracked-wallet
//! fills to `trader_fills` with `source='live_onchain'` + `live_seen_at`, at ~1–5s
//! fill→row latency (vs the poller's ~90s median). Built only because the P0-B
//! ingestion gate PASSed (reports/F2_CONSTANTS.md): address_match 100% (proxy wallet
//! is the log maker/taker directly), OrderFilled decodes, price/size reconstruct.
//!
//! Transport: `eth_blockNumber` poll + targeted `eth_getLogs(fromBlock..toBlock,
//! topics=[OrderFilled])` over a free Polygon RPC (HTTP, reqwest — ZERO new deps;
//! no alloy/ethers). Idempotent & gap-free: a missed block just widens the next
//! getLogs range — no survivorship hole.
//!
//! DEDUP is the load-bearing decision (P0-B: 15% of fills are multi-level VWAPs, so
//! the widened tx unique index — which includes `price` — will NOT collapse a
//! reconstructed live twin). Three layers, verified in live_reconcile.py:
//!
//! 1. live-vs-live  — the source-scoped `trader_fills_live_txkey` unique index (040c);
//! 2. live-vs-poll  — `filter_existing_txkey` pre-check before insert;
//! 3. poll-over-live — `collapse_live_over_poll` periodic sweep (poll row wins).
//!
//! The poller's write is UNCHANGED; only this constructor sets `source`.
//!
//! When `LIVE_FILLS=false` (default) the task is never spawned → byte-identical.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use chrono::{DateTime, TimeZone, Utc};
use serde_json::{json, Value};

use crate::config::CopyTradingConfig;
use crate::cycles::consensus_cycle::trade_to_fill;
use crate::data::models::fetch_clob_market;
use crate::metrics;
use crate::scanner::copy_trader::TraderTrade;
use crate::storage::postgres::PgPortfolio;

const POLL_SECS: u64 = 2; // ~Polygon block time
const RESOLVE_THROTTLE: Duration = Duration::from_millis(120);
const COLLAPSE_EVERY_TICKS: u64 = 30; // run the poll-over-live sweep periodically

/// Metadata to build a `TraderTrade` from an on-chain fill (keyed by decimal token_id).
#[derive(Clone)]
struct MarketMeta {
    condition_id: String,
    outcome_index: i32,
    slug: String,
    title: String,
    outcome: String,
    event_slug: Option<String>,
}

/// Decoded OrderFilled log (see reports/F2_CONSTANTS.md for the ABI).
struct OrderFilled {
    maker: String,
    taker: String,
    maker_asset: String, // decimal token_id or "0" (collateral)
    taker_asset: String,
    maker_amt: u128,
    taker_amt: u128,
}

/// Convert a 32-byte hex word (0x-prefixed or not, ≤64 hex chars) to a decimal
/// string — the CLOB token_id domain. Schoolbook base-256→base-10, no bignum dep.
fn hex_to_dec_str(hex: &str) -> String {
    let h = hex.strip_prefix("0x").unwrap_or(hex);
    let mut digits: Vec<u8> = vec![0]; // little-endian decimal
    for nib in h.chars() {
        let v = match nib.to_digit(16) {
            Some(v) => v as u16,
            None => continue,
        };
        // digits = digits * 16 + v
        let mut carry = v;
        for d in digits.iter_mut() {
            let cur = *d as u16 * 16 + carry;
            *d = (cur % 10) as u8;
            carry = cur / 10;
        }
        while carry > 0 {
            digits.push((carry % 10) as u8);
            carry /= 10;
        }
    }
    while digits.len() > 1 && *digits.last().unwrap() == 0 {
        digits.pop();
    }
    digits.iter().rev().map(|d| (b'0' + d) as char).collect()
}

/// Parse a 32-byte hex word as u128 (amounts fit; token_ids do not — use hex_to_dec_str).
fn hex_to_u128(hex: &str) -> Option<u128> {
    let h = hex.strip_prefix("0x").unwrap_or(hex).trim_start_matches('0');
    if h.is_empty() {
        return Some(0);
    }
    if h.len() > 32 {
        return None; // >128 bits — not an amount
    }
    u128::from_str_radix(h, 16).ok()
}

fn addr_from_topic(topic: &str) -> String {
    let h = topic.strip_prefix("0x").unwrap_or(topic);
    format!("0x{}", &h[h.len().saturating_sub(40)..]).to_lowercase()
}

/// Decode one getLogs entry into an OrderFilled (4 topics, 5 data words), else None.
fn decode_order_filled(log: &Value) -> Option<OrderFilled> {
    let topics = log["topics"].as_array()?;
    if topics.len() != 4 {
        return None;
    }
    let data = log["data"].as_str()?.strip_prefix("0x").unwrap_or("");
    if data.len() < 64 * 5 {
        return None;
    }
    let word = |i: usize| &data[i * 64..(i + 1) * 64];
    Some(OrderFilled {
        maker: addr_from_topic(topics[2].as_str()?),
        taker: addr_from_topic(topics[3].as_str()?),
        maker_asset: hex_to_dec_str(word(0)),
        taker_asset: hex_to_dec_str(word(1)),
        maker_amt: hex_to_u128(word(2))?,
        taker_amt: hex_to_u128(word(3))?,
    })
}

/// Reconstruct (price, size_usd, asset_id_dec, wallet_side) from the tracked
/// wallet's perspective. The USDC leg is the assetId=="0" side; whoever pays USDC
/// is BUYing shares. Returns None on a degenerate (zero) amount.
fn reconstruct(of: &OrderFilled, tracked: &str) -> Option<(f64, f64, String, String)> {
    let (usdc_amt, shares_amt, share_asset, usdc_payer) = if of.maker_asset == "0" {
        (of.maker_amt, of.taker_amt, of.taker_asset.clone(), of.maker.as_str())
    } else if of.taker_asset == "0" {
        (of.taker_amt, of.maker_amt, of.maker_asset.clone(), of.taker.as_str())
    } else {
        return None; // token-for-token (merge/split) — not a USDC-priced fill
    };
    if usdc_amt == 0 || shares_amt == 0 {
        return None;
    }
    let price = usdc_amt as f64 / shares_amt as f64;
    let size_usd = usdc_amt as f64 / 1e6;
    let side = if tracked == usdc_payer { "BUY" } else { "SELL" };
    Some((price, size_usd, share_asset, side.to_string()))
}

async fn rpc(
    client: &reqwest::Client,
    url: &str,
    method: &str,
    params: Value,
) -> Result<Value> {
    let body = json!({"jsonrpc":"2.0","id":1,"method":method,"params":params});
    let resp: Value = client
        .post(url)
        .json(&body)
        .send()
        .await?
        .json()
        .await?;
    if let Some(err) = resp.get("error") {
        anyhow::bail!("rpc {method} error: {err}");
    }
    Ok(resp.get("result").cloned().unwrap_or(Value::Null))
}

/// Build the token_id(decimal) → MarketMeta resolver from the tracked universe.
async fn build_resolver(
    portfolio: &PgPortfolio,
    http: &reqwest::Client,
    lookback_hours: i64,
) -> Result<HashMap<String, MarketMeta>> {
    let pairs = portfolio.tracked_tape_assets(lookback_hours).await?;
    let mut map = HashMap::new();
    let mut seen: HashSet<String> = HashSet::new();
    for (cond, _oidx) in &pairs {
        if !seen.insert(cond.clone()) {
            continue;
        }
        tokio::time::sleep(RESOLVE_THROTTLE).await;
        let market = match fetch_clob_market(http, cond).await {
            Ok(m) => m,
            Err(_) => continue,
        };
        for (i, tok) in market.tokens.iter().enumerate() {
            if tok.token_id.is_empty() {
                continue;
            }
            map.insert(
                tok.token_id.clone(),
                MarketMeta {
                    condition_id: cond.clone(),
                    outcome_index: i as i32,
                    slug: market.market_slug.clone(),
                    title: market.question.clone(),
                    outcome: tok.outcome.clone(),
                    event_slug: None,
                },
            );
        }
    }
    Ok(map)
}

#[allow(clippy::too_many_arguments)]
async fn process_logs(
    logs: &[Value],
    tracked: &HashSet<String>,
    resolver: &HashMap<String, MarketMeta>,
    block_ts: &HashMap<String, DateTime<Utc>>,
    portfolio: &PgPortfolio,
    dedup_precheck: bool,
) -> Result<usize> {
    let mut fills = Vec::new();
    for log in logs {
        let of = match decode_order_filled(log) {
            Some(o) => o,
            None => continue,
        };
        // BOTH sides may be tracked (two followed wallets trading against each other) —
        // emit a fill for EACH (maker BUY + taker SELL), not just the first (review D3).
        let mut parties: Vec<&String> = Vec::new();
        if tracked.contains(&of.maker) {
            parties.push(&of.maker);
        }
        if tracked.contains(&of.taker) && of.taker != of.maker {
            parties.push(&of.taker);
        }
        if parties.is_empty() {
            continue;
        }
        let ts = log["blockNumber"]
            .as_str()
            .and_then(|b| block_ts.get(b))
            .copied()
            .unwrap_or_else(Utc::now);
        let tx_hash = log["transactionHash"].as_str().map(|s| s.to_lowercase());
        for tracked_wallet in parties {
            let (price, size_usd, asset_dec, side) = match reconstruct(&of, tracked_wallet) {
                Some(x) => x,
                None => continue,
            };
            let meta = match resolver.get(&asset_dec) {
                Some(m) => m,
                None => {
                    // unmapped asset (new market) — the poller will catch it
                    metrics::record_live_fill_unresolved(1);
                    continue;
                }
            };
            let tr = TraderTrade {
                slug: meta.slug.clone(),
                condition_id: meta.condition_id.clone(),
                side,
                price,
                size_usd,
                tx_hash: tx_hash.clone(),
                timestamp: ts,
                outcome_index: Some(meta.outcome_index),
                outcome: Some(meta.outcome.clone()),
                title: Some(meta.title.clone()),
                event_slug: meta.event_slug.clone(),
            };
            // Reuse trade_to_fill so is_sports/sport/bet_type freeze IDENTICALLY to the
            // poller (no taxonomy drift), then stamp provenance.
            if let Some(mut fill) = trade_to_fill(tracked_wallet, &tr) {
                fill.source = Some("live_onchain".to_string());
                fill.live_seen_at = Some(Utc::now());
                fills.push(fill);
            }
        }
    }
    if fills.is_empty() {
        return Ok(0);
    }
    // LAYER 2: live-vs-poll pre-check — skip live rows the poller already holds.
    if dedup_precheck {
        // All four arrays MUST use the SAME iteration so a None tx_hash cannot shift
        // `tx` relative to the others (review D5). None → "" (never matches a poll row).
        let tx: Vec<String> = fills.iter().map(|f| f.tx_hash.clone().unwrap_or_default()).collect();
        let cond: Vec<String> = fills.iter().map(|f| f.condition_id.clone()).collect();
        let oidx: Vec<i32> = fills.iter().map(|f| f.outcome_index).collect();
        let side: Vec<String> = fills.iter().map(|f| f.side.clone()).collect();
        let existing = portfolio
            .filter_existing_txkey(&tx, &cond, &oidx, &side)
            .await
            .unwrap_or_default();
        fills.retain(|f| {
            let k = format!(
                "{}|{}|{}|{}",
                f.tx_hash.clone().unwrap_or_default(),
                f.condition_id,
                f.outcome_index,
                f.side
            );
            !existing.contains(&k)
        });
    }
    // LAYER 1: insert through the shared dedup path (source-scoped index collapses
    // live-vs-live replays; poller rows untouched).
    let n = portfolio.insert_trader_fills(&fills).await? as usize;
    metrics::record_live_fill_events(n as u64);
    Ok(n)
}

/// Entry point: poll blocks, getLogs OrderFilled, write tracked fills. Never returns.
/// Spawned from `live.rs` only when `cfg.live_fills` is true.
pub async fn run_live_fills(
    portfolio: Arc<PgPortfolio>,
    http: reqwest::Client,
    cfg: Arc<CopyTradingConfig>,
) {
    let url = cfg.live_fills_rpc_http.clone();
    if url.is_empty() {
        tracing::warn!("LIVE_FILLS on but LIVE_FILLS_RPC_HTTP empty — F2 idle");
        return;
    }
    let topic0 = if cfg.live_orderfilled_topic0.is_empty() {
        // P0-B verified default
        "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee".to_string()
    } else {
        cfg.live_orderfilled_topic0.clone()
    };
    let addr_filter: Vec<String> = cfg
        .live_ctf_addrs
        .split(',')
        .map(|s| s.trim().to_lowercase())
        .filter(|s| !s.is_empty())
        .collect();

    let tracked: HashSet<String> = match portfolio.tracked_wallets_for_live().await {
        Ok(w) => w.into_iter().collect(),
        Err(e) => {
            tracing::warn!(err = %e, "live-fills: tracked wallets load failed");
            return;
        }
    };
    let mut resolver = build_resolver(&portfolio, &http, cfg.live_tape_lookback_hours)
        .await
        .unwrap_or_default();
    tracing::info!(
        wallets = tracked.len(),
        resolved_tokens = resolver.len(),
        "F2 live on-chain fills ON"
    );

    // start from the current head
    let mut last_block: u64 = match rpc(&http, &url, "eth_blockNumber", json!([])).await {
        Ok(v) => v.as_str().and_then(|s| u64::from_str_radix(s.trim_start_matches("0x"), 16).ok())
            .unwrap_or(0),
        Err(e) => {
            tracing::warn!(err = %e, "live-fills: initial blockNumber failed");
            return;
        }
    };
    let mut tick: u64 = 0;
    loop {
        tokio::time::sleep(Duration::from_secs(POLL_SECS)).await;
        tick += 1;
        let head = match rpc(&http, &url, "eth_blockNumber", json!([])).await {
            Ok(v) => v.as_str().and_then(|s| u64::from_str_radix(s.trim_start_matches("0x"), 16).ok()),
            Err(e) => {
                tracing::warn!(err = %e, "live-fills: blockNumber failed");
                continue;
            }
        };
        let head = match head {
            Some(h) if h > last_block => h,
            _ => continue,
        };
        // gap-free: getLogs over the whole [last+1, head] range (bounded to avoid huge pulls)
        let from = last_block + 1;
        let to = head.min(from + 500);
        let mut filter = json!({
            "fromBlock": format!("0x{:x}", from),
            "toBlock": format!("0x{:x}", to),
            "topics": [topic0],
        });
        if !addr_filter.is_empty() {
            filter["address"] = json!(addr_filter);
        }
        let logs = match rpc(&http, &url, "eth_getLogs", json!([filter])).await {
            Ok(Value::Array(a)) => a,
            Ok(_) => Vec::new(),
            Err(e) => {
                tracing::warn!(err = %e, "live-fills: getLogs failed (will retry range)");
                continue; // do NOT advance last_block → range re-pulled (gap-free)
            }
        };
        // resolve block timestamps (event clock) for the blocks present
        let mut block_ts = HashMap::new();
        let mut blocks: HashSet<String> = HashSet::new();
        for l in &logs {
            if let Some(b) = l["blockNumber"].as_str() {
                blocks.insert(b.to_string());
            }
        }
        for b in blocks {
            if let Ok(Value::Object(blk)) =
                rpc(&http, &url, "eth_getBlockByNumber", json!([b, false])).await
                && let Some(ts_hex) = blk.get("timestamp").and_then(|t| t.as_str())
                && let Ok(secs) = i64::from_str_radix(ts_hex.trim_start_matches("0x"), 16)
                && let Some(dt) = Utc.timestamp_opt(secs, 0).single()
            {
                block_ts.insert(b, dt);
            }
        }
        match process_logs(&logs, &tracked, &resolver, &block_ts, &portfolio,
                           cfg.live_dedup_precheck).await {
            Ok(n) if n > 0 => tracing::debug!(fills = n, from, to, "live-fills wrote rows"),
            Ok(_) => {}
            Err(e) => {
                tracing::warn!(err = %e, "live-fills: process failed");
                continue; // range re-pulled
            }
        }
        last_block = to;

        // LAYER 3: periodic poll-over-live collapse.
        if tick.is_multiple_of(COLLAPSE_EVERY_TICKS) {
            if let Ok(c) = portfolio.collapse_live_over_poll().await
                && c > 0
            {
                tracing::info!(collapsed = c, "live-fills poll-over-live collapse");
            }
            // refresh the resolver so new markets become mappable
            if let Ok(m) = build_resolver(&portfolio, &http, cfg.live_tape_lookback_hours).await
                && !m.is_empty()
            {
                resolver = m;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_to_dec_matches_known_token_id() {
        assert_eq!(hex_to_dec_str("0000000000000000000000000000000000000000000000000000000000000002"), "2");
        assert_eq!(hex_to_dec_str("00000000000000000000000000000000000000000000000000000000000000ff"), "255");
        assert_eq!(hex_to_dec_str("0000000000000000000000000000000000000000000000000000000000000100"), "256");
        // multi-byte: 0x1a2b3c = 1715004
        assert_eq!(hex_to_dec_str("00000000000000000000000000000000000000000000000000000000001a2b3c"), "1715004");
    }

    #[test]
    fn hex_to_u128_amounts() {
        // 0x23e2ff50 = 602_079_056 (USDC 6dp-scale amount)
        assert_eq!(hex_to_u128("0000000000000000000000000000000000000000000000000000000023e2ff50"), Some(602_079_056));
        assert_eq!(hex_to_u128("0000000000000000000000000000000000000000000000000000000000000000"), Some(0));
        assert_eq!(hex_to_u128("000000000000000000000000000000000000000000000000000000000000000a"), Some(10));
    }

    #[test]
    fn reconstruct_buy_matches_071() {
        // maker paid 602.2788 USDC for 848.28 shares → price 0.71, BUY for maker.
        let of = OrderFilled {
            maker: "0xw".into(),
            taker: "0xother".into(),
            maker_asset: "0".into(),
            taker_asset: "90379...573".into(),
            maker_amt: 602_278_800,
            taker_amt: 848_280_000,
        };
        let (price, size, asset, side) = reconstruct(&of, "0xw").unwrap();
        assert!((price - 0.71).abs() < 1e-9, "price {price}");
        assert!((size - 602.2788).abs() < 1e-6, "size {size}");
        assert_eq!(asset, "90379...573");
        assert_eq!(side, "BUY");
        // the counterparty (taker) side is SELL
        let (_, _, _, tside) = reconstruct(&of, "0xother").unwrap();
        assert_eq!(tside, "SELL");
    }

    #[test]
    fn addr_from_topic_lowercases_last_20_bytes() {
        assert_eq!(
            addr_from_topic("0x00000000000000000000000099c4fb1f78881601075bc25b13c9af76bc5918e7"),
            "0x99c4fb1f78881601075bc25b13c9af76bc5918e7"
        );
    }
}
