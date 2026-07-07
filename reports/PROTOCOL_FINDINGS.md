# CLOB WS protocol — live ground-truth (P0-A pre-probe, 2026-07-06)

Captured raw frames from `wss://ws-subscriptions-clob.polymarket.com/ws/market`
subscribing `{"assets_ids":[...],"type":"market","custom_feature_enabled":true}`.
This SUPERSEDES the plan's open questions and parts of `ws.rs`'s handler set.

## Event types actually received (custom_feature_enabled=true)

`ws.rs` handles `best_bid_ask` / `last_trade_price` / `price_change` / `market_resolved`.
The LIVE stream under this subscription sends **`book`** and **`price_change`**
(no `best_bid_ask`/`last_trade_price` seen in a 20s window). `live_tape.rs` must
handle `book` + `price_change`.

### `book` (snapshot, ~1 per asset on subscribe / resync)
keys: `asks`, `asset_id`, `bids`, `event_type`, `hash`, `last_trade_price`,
`market`, `tick_size`, `timestamp`
- `bids`/`asks`: arrays of `{price, size}` (strings). Sample `bids` ascending by
  price (0.01, 0.02, ...) → **best_bid = max(bid.price)**, **best_ask = min(ask.price)**.
- `last_trade_price`: string.
- `timestamp`: **ms epoch as string** (e.g. "1783381780533") = exchange clock.

### `price_change` (high-frequency delta — 399 in ~20s for 14 assets)
keys: `event_type`, `market`, `price_changes[]`, `timestamp` (top-level ms epoch)
each element of `price_changes`:
`asset_id`, `price`, `size`, `side` (BUY/SELL), `hash`, **`best_bid`**, **`best_ask`**
→ resolved top-of-book is delivered directly; no REST snapshot needed.

## Resolved open questions

| Question | Answer |
|---|---|
| Does `best_bid_ask` carry `best_ask`? | N/A — the live event is `price_change`, which carries `best_ask` directly (and `book` carries full asks). **REST fallback NOT needed.** |
| Does any message carry `exch_ts`? | **YES** — top-level `timestamp` (ms epoch string) on both `book` and `price_change`. Curve anchors on exch_ts (same domain as fill `ts`) → skew ≈ 0. |
| best_ask presence % | expected ~100% on price_change (measured in the 30-min probe). |

## Consequences for the build
- `clob_price_tape.exch_ts` is populated from `timestamp` (ms→timestamptz), NOT NULL in practice.
- `clob_price_tape.best_ask` populated from `price_change.best_ask` / `min(book.asks.price)`.
- Item-3 "best_ask absent → last_trade_price + fetch_best_ask REST fallback" is DEAD CODE — drop it.
- Item-7 dual-clock skew reporting stays as a VALIDATION (report skew = recv_at − exch_ts), but the
  anchor is exch_ts, so the correction is not load-bearing.
- Event volume is high and bursty (subscribe burst). Steady-state events/s measured in the 30-min probe
  sizes storage; retention prune bounds it.
