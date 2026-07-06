# FORGE PLAN — Live Fill Ingestion (event-driven sharps feed + latency→edge curve)

**What the system does differently after this run.** Today every sharp fill waits ~90s (median
90.4s, 5.19% of rows >1h) for its wallet's next poll slot before we even see it, and the copy-tax
curve is two lonely dots. After the run: a flag-gated **CLOB price tape** records the executable
book for every tracked-market asset in real time, so we can reconstruct — **offline, against each
fill's already-clean `ts`** — the second-by-second price drift after any sharp fill, and finally
answer *in ¢-per-second* what speed is worth (against the honest +3–5%/bet baseline). An **optional,
separately-gated** on-chain `OrderFilled` feed cuts fill→row latency to ~1–5s for the future
auto-trader — but the deliverable (the curve) ships even if that feed fails its probe, because the
curve was never downstream of ingestion. The poller stays the completeness spine, untouched.

**The single design decision that shapes everything:** the run prompt frames the curve as
*downstream* of a fast-fills build (P1→P2→P3), gated by one STOP rule on "the feed." That framing is
wrong, and verification proves the rethink is safer: `trader_fills.ts` is already the exchange/fill
clock (`trade_to_fill` sets `ts: tr.timestamp`, `consensus_cycle.rs:334`), so the curve needs only a
low-latency **price** observation (the wallet-blind CLOB WS, zero new deps), not low-latency
**ingestion**. We therefore adopt Design B's **tape-decoupling** as the spine and graft Design A's
dedup rigor onto the optional on-chain build. See `FORGE_DEBATES_LIVE_INGESTION.md` for the full
verification record, including the price-precision verdict that killed Design B's dedup shortcut.

---

## Items

Gap index follows the Diagnostic's GAP-0…GAP-7 (Design B merged several; noted per item).

---

### Item 1 — Two-gate P0 probe + decision memo (GAP-0 + GAP-3)

**Before.** Zero probe data. `MAX_SUBSCRIPTIONS = 200` is an untested constant (`ws.rs:14`). One
conflated STOP rule ("no feed <10s + ≥95% coverage → deliver negative, don't build P1") ties the
*measurement* feed to the *ingestion* feed, so an on-chain-RPC failure would abort a deliverable that
never depended on it.

**After.** `reports/live_ingestion_probe.json` with two independent verdicts. The **measurement
gate** (F1 tape) decides whether the curve is buildable; the **ingestion gate** (F2 on-chain) decides
only whether the fast-fills accelerator is built. The curve can PASS while F2 SKIPs.

**Implementation.** Four throwaway probe scripts (`scripts/probe_*.py`, `py_compile`-clean,
`--self-test` on recorded fixtures, deleted or kept read-only; no workspace coupling). Each appends
its block to `reports/live_ingestion_probe.json`.

- **P0-A `probe_f1_tape.py`** (measurement gate; reuses the exact `ws.rs` protocol). Connect
  `wss://ws-subscriptions-clob.polymarket.com/ws/market`; subscribe
  `{"assets_ids":[…],"type":"market","custom_feature_enabled":true}`; text `"PING"` every 10s
  (`ws.rs:161`). Escalate `N ∈ {200, 350, 500, 800}` on separate connections to find the **real**
  per-connection max (binary-search `take(N)` until updates stall or the socket closes) — this
  validates/overwrites the `200` constant (GAP-3). Record, over ≥30 min: `max_subs_per_conn_observed`,
  `connections_needed` for the tracked asset set, `disconnects_per_30min`, `reconnect_recovery_s_p50`,
  `events_per_sec` (**storage-sizing input**), **`best_ask_present_pct`** and **`exch_ts_present_pct`**
  (ws.rs today parses only `best_bid`/`price`/`size` — `best_ask` and any `timestamp` field are
  **to-be-confirmed**, see Open Questions), and **`tape_coverage_observable_pct`** = fraction of the
  window's tracked sharp fills (from `trader_fills`, joined `condition_id`→token_id) whose asset had
  ≥1 tick within `±TOL` of `ts`, **denominator = two-sided-quotable fills only** (the ~22% unquotable
  picks are excluded — speed cannot manufacture a price that is not on the book).
- **P0-B `probe_f2_onchain.py`** (ingestion gate, OPTIONAL). For ≥50 known tracked sports fills
  (`SELECT tx_hash,wallet,condition_id,outcome_index,side,price,size_usd,ts FROM trader_fills WHERE
  is_sports AND wallet IN (tracked) AND ts>now()-interval '2 hours' ORDER BY ts DESC LIMIT 50` —
  **100% carry tx_hash**, verified `[DB:mine 361328/361328]`), fetch each tx's logs over a free
  Polygon RPC (`eth_getTransactionReceipt` / `eth_getLogs` HTTP), decode the CTF-Exchange
  `OrderFilled` log, and measure: `address_match_pct` (does `maker`/`taker` equal the data-api proxy
  wallet?), **`price_size_roundtrip`** (does the on-chain `usdc_amount/share_amount` f64 reconstruct
  to the stored VWAP `price`, and *at what rounding*? — this SELECTS the F2 dedup layer, see Item 5),
  `fill_to_log_s_p50` (block/log availability lag over ≥30 min), and free-RPC rate-limit behavior.
  Also probe transport: `eth_subscribe(logs)` wss **vs** `newHeads + eth_getLogs` HTTP — record which
  a free RPC holds without silently dropping.
- **P0-C `build_token_map.py`** (shared helper). `conds = SELECT DISTINCT condition_id FROM
  trader_fills WHERE is_sports AND wallet IN (tracked) AND ts>now()-interval
  'LIVE_TAPE_LOOKBACK_HOURS'`; for each, `GET https://clob.polymarket.com/markets/{condition_id}`
  (`fetch_clob_market` equivalent) → `token_id → (condition_id, outcome_index, slug, title)`, throttle
  **120ms** (`dense_capture.rs:47` citizenship). This is the tracked-only subscription universe (a few
  thousand tokens, **not** the full ~8k), the input to both P0-A and P1'.
- **P0-D fuzzy-join latency floor** (folded into P2's instrument but run in P0 for the decision memo):
  match anonymous `last_trade_price` tape ticks to polled fills on `(asset↔cond/outcome, round(price,2),
  |size−last_price·last_size|<ε, |recv_at−ts|<TOL)` → the *fill→first-observable latency floor*, the
  exact "how much earlier could we have seen it" number, measured **with zero on-chain client** — a
  real input to whether F2 is even worth building (see Item 6).

**`reports/live_ingestion_probe.json` shape:**
```json
{ "probed_at":"2026-07-06T..Z",
  "f1_clob_ws":{ "endpoint":"wss://ws-subscriptions-clob.polymarket.com/ws/market",
    "max_subs_per_conn_observed":0, "assets_target_tracked":0, "connections_needed":0,
    "disconnects_per_30min":0, "reconnect_recovery_s_p50":0.0, "events_per_sec":0.0,
    "best_ask_present_pct":0.0, "exch_ts_present_pct":0.0,
    "tape_coverage_observable_pct":0.0, "verdict":"PASS|FAIL" },
  "f2_onchain":{ "transport":"newHeads+getLogs(HTTP) | eth_subscribe(logs)",
    "rpc_probed":[{"url":"https://polygon-rpc.com","block_lag_s":0.0,"getlogs_ok":false,
                   "sub_logs_ok":false,"rate_limited_after_s":null}],
    "address_match_pct":0.0, "price_size_roundtrip":{"exact":0,"eq_after_round10dp":0,"eq_after_round2dp":0,"n":50},
    "fill_to_log_s_p50":null, "verdict":"PASS|FAIL|SKIP" },
  "fuzzy_join_latency_floor":{ "matched":0,"collision_rate":0.0,"floor_s_p50":null },
  "decision":{ "curve_feed":"f1_tape", "build_p1_live_fills":false, "stop_curve":false,
    "f2_dedup_layer":"source_scoped+collapse | tx_index_round10", "rationale":"…" } }
```

**STOP-rule arithmetic (two gates, written before probing):**
```
MEASUREMENT GATE (gates the deliverable / curve):
  PASS iff  tape_coverage_observable_pct >= 95
       AND  F1 held connections_needed for >= 30 min with reconnect_recovery_s_p50 < 10
  FAIL -> STOP the curve: write reports/entries/<date>-live-ingestion-NEGATIVE.md with the
          partial coverage number honestly; deliver the probe report; build nothing downstream.

INGESTION-BUILD GATE (gates F2/P1 ONLY; independent):
  BUILD P1 iff  address_match_pct >= 94 (>=47/50)
           AND  a free RPC held its transport >= 30 min with fill_to_log_s_p50 < 10 and no rate-limit
  price_size_roundtrip does NOT gate PROCEED — it SELECTS the F2 dedup layer (Item 5):
     eq_after_round10dp >= 49/50  -> tx-index dedup viable (round price to 10dp at live write)
     else                         -> source-scoped index + poll-over-live collapse are PRIMARY
  FAIL -> defer P1 (build_p1_live_fills=false); the curve still ships from F1 tape.
```

**Integration points.** New files only: `scripts/probe_{f1_tape,f2_onchain,build_token_map}.py`,
`reports/live_ingestion_probe.json`, `tests/fixtures/{orderfilled_log,clob_market,activity_row}.json`.
**Nothing in the workspace changes in P0.** Ground-truth oracle = `trader_fills` (read-only), joined by
`tx_hash` (100% coverage) and `condition_id`.

**API-budget/storage.** All probes read-only, time-boxed, on endpoints **disjoint from the data-api
poller** (CLOB WS host; Polygon RPC) → zero contention with the poller's 429 budget. The only shared
surface is CLOB REST token resolution (P0-C, 120ms-throttled, few-thousand one-off calls). F2 probe is
≤50 one-off HTTP receipt calls with backoff. Storage: none (probes append one JSON).

**Source: rethink** — B's two-gate split decouples the measurement feed from the ingestion feed so an
F2 failure cannot abort a deliverable that never depended on it; A's probe JSON rigor and the
price-byte-match probe are grafted in because they still decide the F2 dedup architecture.

---

### Item 2 — Migration 040: provenance + the CLOB price tape (GAP-6 + substrate for GAP-2/5)

**Before.** `trader_fills` has `ts` (clean fill clock) and `ingested_at` (contaminated: `NOW()` even
on backfilled rows → 5.19% of 24h rows carry >1h lag `[DB:mine 18771/361389]`). No provenance, no
price-tape store. `EXTRACT(EPOCH FROM ingested_at-ts)` reports a p90 that is a lie.

**After.** Two additive nullable columns give every row honest provenance; a new append-only
`clob_price_tape` table is the measurement substrate for the curve. `ingested_at` is **left untouched**
(still means "write time") and simply **no longer used as a clock**: event-time is `ts`, live
observation latency is `live_seen_at − ts`, both against a clean clock.

**Implementation.** `migrations/040_live_ingestion.sql` (additive + idempotent; re-check the number is
still 040 at merge — 039 is highest, verified `migrations/`; concurrent-chat collisions have happened):
```sql
-- 040: live-ingestion provenance + raw CLOB price tape.
-- Additive & idempotent; touches NOTHING in 001-039 (sqlx checksums immutable).

-- (a) Provenance on the durable archive. NULL == existing poller spine (~2.9M rows read as poll,
--     back-compat). 'live_onchain' == F2 fills (Item 5). live_seen_at = wall clock this process FIRST
--     saw the fill on a live channel (NULL for poll/backfill). We store a TIMESTAMP, not a duration:
--     lag = live_seen_at - ts is computed at read against the clean `ts`, so a mis-defended clock can
--     be re-derived later, not baked in.
ALTER TABLE trader_fills
    ADD COLUMN IF NOT EXISTS source        TEXT,           -- NULL=poll | 'live_onchain' | 'backfill'
    ADD COLUMN IF NOT EXISTS live_seen_at  TIMESTAMPTZ;    -- wall clock of first live sight; NULL=poll

-- (b) Raw CLOB price tape — the measurement substrate for the latency->drift curve. Append-only;
--     anchor OFFLINE by joining a sharp fill's `ts` to (asset_id, recv_at). Keep BOTH clocks
--     (skew defence): recv_at (local WS receive) and exch_ts (message timestamp IF the payload
--     carries it — to-be-confirmed P0-A). Forward-only, flag-gated (LIVE_TAPE), retention-pruned.
CREATE TABLE IF NOT EXISTS clob_price_tape (
    id            BIGSERIAL PRIMARY KEY,
    asset_id      TEXT             NOT NULL,   -- CLOB token_id (one YES/NO leg)
    condition_id  TEXT,                        -- carried from the subscription map (no 2nd CLOB call)
    outcome_index SMALLINT,
    event_type    TEXT             NOT NULL,   -- 'best_bid_ask'|'last_trade_price'|'price_change'
    best_bid      DOUBLE PRECISION,
    best_ask      DOUBLE PRECISION,            -- the executable BUY price (curve reads this)
    last_price    DOUBLE PRECISION,            -- last_trade_price only
    last_size     DOUBLE PRECISION,            -- last_trade_price only (SHARES)
    exch_ts       TIMESTAMPTZ,                 -- exchange ts if the message carries it, else NULL
    recv_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tape_asset_recv ON clob_price_tape (asset_id, recv_at);
CREATE INDEX IF NOT EXISTS idx_tape_cond_recv  ON clob_price_tape (condition_id, recv_at)
    WHERE condition_id IS NOT NULL;

-- (c) Only if F2 is built (Item 5): a source-scoped unique index for live-vs-live dedup across
--     reconnect replays. SAFE: constrains ONLY live rows among themselves, so it cannot conflict
--     with the full-precision poller rows (source IS NULL is excluded).
CREATE UNIQUE INDEX IF NOT EXISTS trader_fills_live_txkey
    ON trader_fills (tx_hash, condition_id, outcome_index, side)
    WHERE source = 'live_onchain' AND tx_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tf_source_ts ON trader_fills (source, ts) WHERE source IS NOT NULL;
```

**`NewTraderFill` + the write path (refined — one gate, not a clone).** Add two appended `Option`
fields to `NewTraderFill` (`common/src/storage/consensus.rs:108`, honoring its own "appended after,
never reordered" discipline): `pub source: Option<String>, pub live_seen_at: Option<DateTime<Utc>>`.
Extend the **single** `insert_trader_fills` UNNEST (`consensus.rs:1270`) to bind two more columns
(`source`, `live_seen_at`) — the poller passes `None → NULL` and its behavior is byte-identical. The
production constructor `trade_to_fill` (`consensus_cycle.rs:319`) and the **3 test constructors**
(`consensus.rs:2257,2498,2881`) each get `source:None, live_seen_at:None`. This keeps the run prompt's
mandate literally ("writes rows via the **EXISTING** `trader_fills` dedup path") and avoids a
17-column cloned insert.

**Integration points.**
- `migrations/040_live_ingestion.sql` — NEW.
- `common/src/storage/consensus.rs:108` `NewTraderFill` — +2 appended `Option` fields.
- `common/src/storage/consensus.rs:1270` `insert_trader_fills` — bind `source`, `live_seen_at`.
- `copy-trading-bot/src/cycles/consensus_cycle.rs:319` `trade_to_fill` — construct `source:None,
  live_seen_at:None`. Test sites `consensus.rs:2257/2498/2881` — same.

**API-budget/storage.** Migration: two nullable columns (no rewrite) + one append-only table + two
indexes. Tape storage = `events_per_sec × TAPE_RETENTION_HOURS`; `events_per_sec` is **to-be-measured
(P0-A)**, bounded by tracked-only subscription + 72h retention prune (Item 4). Unbounded-growth risk is
called out and pruned.

**Source: refined** — B's `live_seen_at` timestamp beats A's `ingest_lag_ms` duration (store the raw
observation, compute lag at read against clean `ts`); the tape table is B's substrate; but **both
designs' insert approach is corrected** — extend the one `insert_trader_fills` rather than clone it (A)
or leave it ambiguous (B).

---

### Item 3 — `live_tape.rs`: store the CLOB price tape (GAP-2, part 1; the real unblocker)

**Before.** `dense_capture.rs` samples at 45s, anchored on **signal-fire**, capped 40/tick — the
favorite band has n=3 points ever in 60–120s, median trajectory lag 551.5s `[audit]`. The 1–120s zone
where the copy tax lives is empty.

**After.** A `LIVE_TAPE=false`-gated tokio task records **every** book/trade tick for the tracked
asset universe into `clob_price_tape`, so the price path around any fill is reconstructable offline at
1s granularity — including the pre-signal window the signal-fire anchor could never see.

**Implementation.** `copy-trading-bot/src/cycles/live_tape.rs` (NEW). **Copy** the `ws.rs`
connect/subscribe/PING/reconnect loop into copy-trading-bot (do not generalize into `common` — see
Item 8). Add `tokio-tungstenite = "0.28"` to `copy-trading-bot/Cargo.toml` (workspace already resolves
it for `trading-bot`; zero version churn; `futures-util` already present). The one change from
`ws.rs::handle_message`: emit a raw `TapeTick` per event instead of the `PriceTracker` delta filter —
store everything, filter offline.
```rust
struct TapeTick {
    asset_id: String,              // CLOB token_id
    event_type: &'static str,      // "best_bid_ask" | "last_trade_price" | "price_change"
    best_bid: Option<f64>,
    best_ask: Option<f64>,         // parse json["best_ask"] the same string-parse way ws.rs:213 reads best_bid
    last_price: Option<f64>,       // last_trade_price
    last_size: Option<f64>,        // last_trade_price (SHARES)
    exch_ts: Option<DateTime<Utc>>,// parse json["timestamp"] IF present (P0-A confirms), else None
    recv_at: DateTime<Utc>,        // Utc::now() at frame receive
}
```
Handler mapping (in the copied loop):
- `best_bid_ask` → read `best_bid` (as `ws.rs:213`) **and** `best_ask` (new, same parse); one tick.
- `last_trade_price` → `last_price`,`last_size` (`ws.rs:264-268` already parses these).
- `price_change` → one tick per element of `json["price_changes"]` (`ws.rs:230`).

Two tasks + a refresh loop:
- **reader** — N sharded connections (`ceil(assets / LIVE_TAPE_MAX_SUBS)`), each the copied ws.rs loop
  with `.take(max_subs)`; on each parsed event `let _ = tx.try_send(tick)` into a **bounded** mpsc; on
  overflow, drop + bump `record_live_tape_dropped()` (tape is best-effort; the poller stays the
  completeness spine).
- **writer** — drain-batch (≤200 ticks OR 500ms) → `PgPortfolio::insert_tape_ticks(&[TapeTick])` (NEW),
  one UNNEST insert (no `ON CONFLICT` — append-only log, offline dedup by `id`):
  ```sql
  INSERT INTO clob_price_tape
    (asset_id,condition_id,outcome_index,event_type,best_bid,best_ask,last_price,last_size,exch_ts,recv_at)
  SELECT * FROM UNNEST($1::text[],$2::text[],$3::int2[],$4::text[],$5::float8[],
    $6::float8[],$7::float8[],$8::float8[],$9::timestamptz[],$10::timestamptz[])
  ```
- **retention prune** — periodic `DELETE FROM clob_price_tape WHERE recv_at < now() - (TAPE_RETENTION_HOURS||' hours')::interval`.

**Fallback if P0-A shows `best_ask` absent from the payload:** anchor the curve on
`last_trade_price` and top up grid points via `fetch_best_ask` REST snapshots (`models.rs:330`) — lower
density, still ships (Item 7 curve handles both sources).

**Integration points.**
- `copy-trading-bot/src/cycles/live_tape.rs` — NEW (reader, writer, prune).
- `copy-trading-bot/src/cycles/mod.rs` — `pub mod live_tape;` (grep `mod hot_lane;`).
- `copy-trading-bot/src/live.rs:227` pattern — NEW `if cfg.live_tape { spawn reader/writer/refresh }`.
- `copy-trading-bot/Cargo.toml` — add `tokio-tungstenite="0.28"` (features matching `trading-bot`).
- `common/src/storage/consensus.rs` — NEW `insert_tape_ticks`, NEW `tracked_tape_assets` (Item 4).
- `common/src/metrics.rs:194` pattern — NEW `record_live_tape_events/_dropped/_lag_ms` dual-mirror.

**API-budget/storage.** F1 endpoint disjoint from data-api → zero poller-429 contention. Connection
count `ceil(assets/max_subs)` (~5–15 for tracked-only) documented from P0-A before broad subscribe.
Storage bounded by retention prune + tracked-only; `events_per_sec` from P0-A sizes it.

**Source: rethink** — store-the-tape is B's centerpiece and the real unblocker; A's `ws.rs`-protocol
reuse and 120ms citizenship are grafted in.

---

### Item 4 — Tracked-only subscription universe + refresh (GAP-3, part 1)

**Before.** `MAX_SUBSCRIPTIONS=200` hard-coded; the trading-bot only ever watched a small hot set; the
constant was never stress-tested against our real asset count.

**After.** Subscribe **only** to token_ids of conditions a *tracked* wallet has filled in the last
`LIVE_TAPE_LOOKBACK_HOURS` (default 6) — a few thousand, not ~8k — sharded across
`ceil(N / LIVE_TAPE_MAX_SUBS)` connections, `LIVE_TAPE_MAX_SUBS` set from the P0-A probe result.

**Implementation.**
```rust
// PgPortfolio::tracked_tape_assets [NEW] -> condition_ids to resolve to token_ids
"SELECT DISTINCT condition_id, outcome_index
   FROM trader_fills
  WHERE ts > now() - ($1||' hours')::interval
    AND wallet IN (SELECT lower(proxy_wallet) FROM followed_traders)
    AND is_sports"
```
A refresh loop resolves each `(condition_id, outcome_index)` →
`fetch_clob_market(...).outcome_token_id(outcome_index)` (`models.rs:301`), 120ms-throttled
(`dense_capture.rs:47`), and swaps the token list into a shared `Arc<RwLock<Vec<String>>>` — readers
pick it up on their next reconnect (the mechanism `ws.rs:109`/`MarketWatcher.tokens` already uses).

**Integration points.** `live_tape.rs` (refresh loop); `common/src/storage/consensus.rs`
`tracked_tape_assets` (NEW); `models.rs:301,352` reused; config `LIVE_TAPE_MAX_SUBS`,
`LIVE_TAPE_LOOKBACK_HOURS` (Item 9).

**API-budget/storage.** Token resolution = few-thousand one-off CLOB REST @120ms, amortized over the
lookback window; the only poller-shared surface, matched to dense-capture citizenship.

**Source: hybrid** — B's tracked-only bounded universe + A's "measure the ceiling before subscribing
broadly" anti-pattern guard.

---

### Item 5 — `live_fills.rs`: OPTIONAL on-chain fast fills (GAP-1) — built only if P0-B PASSes

**Before.** Poll-only; median fill→row **90.4s** `[DB:mine]` + up to 60s cycle tick; the hot lane's
≲30s path covers only ~5 follow-set wallets (`hot_lane.rs:48`).

**After** (`LIVE_FILLS=true`, gated on P0-B): `OrderFilled` observed ~2s after the block, row written
`source='live_onchain'`, `live_seen_at` stamped, at ~1–5s for all tracked wallets. Poller's later twin
**deduped** (source-scoped index) or **collapsed** (poll-over-live) — never double-counted.

**Implementation — transport.** **`newHeads` + targeted `eth_getLogs` (HTTP)**, not
`eth_subscribe(logs)` wss (unless P0-B shows a free RPC holds the wss sub without silent drops). One
cheap `newHeads` sub (or `eth_blockNumber` poll ~2s); on each new block, one
`eth_getLogs(fromBlock=last+1, toBlock=head, address=[CTF_EXCHANGE, NEG_RISK_EXCHANGE],
topics=[ORDERFILLED_TOPIC0])`, decode, filter to tracked wallets in-process, write through the dedup
path. This is **idempotent and gap-free**: a dropped sub or missed block just widens the next
`getLogs` range — no survivorship hole to reason about. Raw JSON-RPC over the already-present
`tokio-tungstenite`/`reqwest` → **zero new deps** (`alloy`/`ethers` avoided; fallback only if
hand-decoding proves brittle). `address`/`topic0` are **P0-verified constants** stored in config so a
Polymarket contract change is a config edit, not a redeploy.
```rust
struct OnchainFill {
    tx_hash: String,        // "0x..", LOWERCASED to match data-api
    maker: String, taker: String,   // lowercased proxy wallets (P0-B verifies proxy, not EOA)
    asset_id: String,       // -> (condition_id, outcome_index) via the token map (Item 4)
    price: f64,             // usdc_amount as f64 / share_amount as f64  (dedup rounding per Item-1 verdict)
    size_usd: f64,
    block_ts: DateTime<Utc>,// on-chain settlement instant (defended event clock for F2)
}
```
Build a `TraderTrade`-shaped value + the token map's `MarketRef` (slug/title/outcome) and call the
existing `trade_to_fill(wallet_lc, &trade)` (`consensus_cycle.rs:307`) so `is_sports`/`sport`/
`bet_type` freeze **identically to the poller** — no taxonomy drift. Then set `source='live_onchain'`,
`live_seen_at=Utc::now()`. Bounded channel; **drop-to-poller** on overflow (`record_live_dropped()`).

**Implementation — DEDUP (the load-bearing decision; Design B's shortcut is BROKEN).**
> **Verified `[DB:mine]`: 50.2% of 24h fills (181,336/361,368) carry >2 decimals; 50,499 carry 16dp
> (e.g. `0.9969990269270036`).** `trader_fills.price` is a **full-precision VWAP** (`size_usd/size`,
> set by `trade_to_fill` from the data-api), NOT a 2dp tick grid. Migration 027's unique index is
> `(tx_hash, condition_id, outcome_index, side, price)`. **Rounding the live price to 2dp (Design B's
> checklist) would give a DIFFERENT index key from ~half of poller rows → no conflict → DOUBLE-COUNT.**
> Cross-source auto-dedup on the tx index is therefore **NOT reliable** — an on-chain-reconstructed
> f64 won't ULP-match the VWAP, and a single tx can carry several price-level `OrderFilled` events the
> data-api may VWAP into one row (migration 027's own rationale). The blueprint mandates **Design A's
> three layers**, with the P0-B `price_size_roundtrip` result selecting the primary:
> 1. **live-vs-live**: the source-scoped `trader_fills_live_txkey` index (Item 2c) collapses reconnect
>    replays — safe, constrains only live rows.
> 2. **live-vs-poll pre-check** (`filter_existing_txkey`): before insert, skip live rows whose
>    `(tx_hash,cond,outcome_index,side)` already exists from the poller.
> 3. **poll-over-live collapse** (idempotent, runs inside the reconciliation window): keep the
>    canonical poller row, drop the redundant live twin per `(tx,cond,outcome,side)`:
>    ```sql
>    DELETE FROM trader_fills live USING trader_fills poll
>    WHERE live.source='live_onchain' AND poll.source IS NULL
>      AND live.tx_hash=poll.tx_hash AND live.condition_id=poll.condition_id
>      AND live.outcome_index=poll.outcome_index AND live.side=poll.side;
>    ```
> If P0-B shows `eq_after_round10dp >= 49/50`, additionally round live `price` to 10dp so the tx index
> itself dedups (layer 1+2 become belt-and-suspenders). Either way the **poller's write is unchanged**;
> rounding lives only in the live constructor.

**Spawn (byte-identical off):** `if cfg.live_fills { tokio::spawn(run_live_fills(...)) }` in `live.rs`
(cloned from the hot-lane block `live.rs:440`).

**Integration points.** `copy-trading-bot/src/cycles/live_fills.rs` (NEW); `cycles/mod.rs`;
`live.rs:~473` spawn; `common/src/storage/consensus.rs` NEW `filter_existing_txkey`,
`tracked_wallets_for_live`; reuse `trade_to_fill`, `insert_trader_fills` (now source-aware, Item 2),
`fetch_clob_market`; metrics `record_live_event/_dropped/_reconnect`; migration 040 index (2c).

**API-budget/storage.** Polygon RPC, **different endpoint** from data-api → no poller-429 contention.
`getLogs`-per-block = one HTTP call / ~2s; jittered backoff; drop-to-poller on overflow. Storage: live
rows share `trader_fills` (deduped against poller — net zero extra beyond provenance columns).

**Source: hybrid** — B's `newHeads+getLogs` transport (robust, gap-free, dissolves survivorship) +
B's "F2 is optional, gated separately" framing, but **A's three-layer dedup architecture** because
verification proved B's 2dp rounding double-counts half the fills.

---

### Item 6 — `live_reconcile.py`: reconciliation + completeness for a dual-path world (GAP-4)

**Before.** Completeness = a scalar `capture_gap_count` per wallet (`record_capture`,
`consensus.rs:1353`). No coverage %, no per-source diff, no dedup proof.

**After** (`scripts/live_reconcile.py --self-test`), three jobs:
```
tape covered 12,481/12,530 observable sharp fills (99.6%)
WS-trade<->poll fuzzy join matched 11,940/12,481 (95.7%), collision rate 1.2%
observation-latency FLOOR p50 = 82s earlier than poll  [the "how much earlier" number, zero on-chain client]
injected live dup (price 0.6052265345 vs 0.6052265344590034): tx-index collapsed? NO -> layer 2/3 -> net 1 row (PASS)
live-blind: 0 wallets (getLogs range re-pull dissolves disconnect survivorship)
```
1. **Tape coverage oracle** (feeds the STOP rule): % of tracked sharp fills whose asset has ≥1 tape
   tick within `±TOL` of `ts`, split observable vs unquotable. Needs no F2 to be a ground truth.
2. **WS-trade ↔ poll fuzzy join** (attribution latency, zero on-chain client): match anonymous
   `last_trade_price` ticks to polled fills on `(asset↔cond/outcome, round(price,2),
   |size−last_price·last_size|<ε, |recv_at−ts|<TOL)`; each match yields `ingested_at − recv_at` = the
   fill→first-observable **latency floor**; emit the **collision rate** (two candidates → one tick) so
   reliability is quantified, not assumed. High-collision fills excluded from the floor (reduced N).
3. **Dedup proof** (only if F2 built; load-bearing given the Item-1 verdict): on throwaway PG (port
   55432), insert a real polled row, inject its `live_onchain` twin with the **reconstructed** on-chain
   price (ULP-different), assert the tx index does **not** collapse it, then run the layer-3 collapse
   and assert net rows == 1. Also inject a `round(price,10)`-matched twin and assert layer-1 collapses.
   This exercises the true hazard, not a strawman.

`--self-test`: synthetic CSVs (known coverage %, one guaranteed collision, one dup pair) into throwaway
PG; asserts each number. **Zero network.**

**Adversarial verify (mandatory after P2, fresh code/own SQL):** `live_reconcile_verify.py` attacks
clock-skew (block_ts/exch_ts vs recv_at vs ts), duplicate masking, survivorship, whole-event
clustering — independent re-derivation.

**Integration points.** `scripts/live_reconcile.py` + `_verify.py` (NEW); imports
`scripts/superkey.py::super_event` (`superkey.py:43`, verified); reads `trader_fills.source/live_seen_at`
+ `clob_price_tape`; throwaway-PG (55432) harness; `record_capture` kept as the per-wallet baseline it
compares against (extend, not replace).

**API-budget/storage.** Pure DB reads + throwaway PG. Zero external calls.

**Source: hybrid** — B's tape-as-oracle + fuzzy-join latency floor (a real pre-F2 decision input) +
A's rigorous throwaway-PG dedup proof (the +4.8%-maker-read killer, now load-bearing because of the
price-precision verdict).

---

### Item 7 — `latency_edge_curve.py`: THE DELIVERABLE — ¢-per-second curve (GAP-5), independent of F2

**Before.** Two dots: +0.4¢@60–80s (strict, N=169) and +1.74¢@895s (favorite, N=7) `[audit]`; the
1–60s and most of 60–120s unmeasured.

**After** (`reports/entries/<date>-latency-edge-curve.md`):
```
favorite 0.55-0.75, mlb: drift +0.3¢@5s  +0.6¢@30s  +0.9¢@60s  +1.6¢@900s  (95% CI ±0.4¢, N=210 event-clusters)
recoverable at 5s vs 60s ≈ 0.6¢ ≈ +1.0%/bet | vs status-quo ~90s ≈ +1.3¢ ≈ +2.1%/bet
verdict vs honest +3-5%/bet baseline: 5s sight recovers ~1/3 of the tax on the money band; thin elsewhere.
```

**Implementation.** Prereg FIRST → `reports/PREREG_<ts>_latency_curve.md`, written **before** looking:
```
grains:    t ∈ {1,5,15,30,60,120,300,900}s, anchored on the fill's `ts` (clean exchange clock)
cells:     band ∈ {0.45-0.55, 0.55-0.75, 0.75-0.90} × sport ∈ {mlb, nba/major, esports, soccer}
metric:    executable drift = tape_ask(asset, ts+t) − fill.price, signed toward the fill side (BUY firming=+)
CI:        event-clustered bootstrap (superkey.super_event), 1000 resamples, 95%; resample EVENTS not fills
baselines: WITHIN-category (never pool soccer into "sports" — composition-attack lesson)
denominator: OBSERVABLE fills only (two-sided book at ts); the ~22% unquotable are reported separately
recoverable: drift(60)−drift(5) and drift(~90)−drift(5), per cell, claim only if CI excludes 0
exclusions: source='backfill'; ingested_at as a clock (contaminated); underpowered cells -> INDETERMINATE-BY-POWER
clock-skew: anchor on exch_ts when the tape carries it (same domain as ts, zero skew), else recv_at minus a
            MEASURED median skew = median(recv_at − exch_ts); report the curve BOTH ways so skew is visible
```
Core estimator (reads the tape directly — no F2 required):
```python
def drift_row(fill, tape_by_asset):        # tape_by_asset: asset_id -> sorted [(clock, best_ask)]
    anchor = fill.ts
    for t in GRID:
        tick = nearest_le(tape_by_asset[fill.asset_id], anchor + t, TOL_S)  # last ask <= anchor+t within TOL
        out[t] = None if tick is None else round(tick.best_ask - fill.price, 4)
    return out
# dedup each fill to ONE per (super_event, wallet, condition, outcome); group by super_event;
# per t: cluster-bootstrap mean & 95% CI; report by band × sport; emit recoverable_5_vs_60 / _vs_status_quo.
```
**Consensus-formation-latency replay:** for each historical `favorite` signal, recompute *when
consensus would have formed* if constituent BUY votes had arrived at their fills' `ts` instead of
`ingested_at` — the delta is the "how much earlier" number (Python re-implements the `net_count`
threshold crossing over the vote timeline via `books_from_window_votes` logic offline).

`--self-test`: synthetic `fills.csv` + `tape.csv` with a known linear drift (+0.1¢/10s) across 3
event-clusters (incl. a tape-gap fill → `None`, a two-fill event → one cluster); asserts the estimator
recovers slope within tolerance, the bootstrap CI brackets truth, within-category baselines don't pool.
**Zero network.**

**Adversarial verify (mandatory after P3):** independent `latency_edge_curve_verify.py` re-derives one
cell with its own SQL, attacks whole-event clustering / within-event splits / the skew correction.

**Integration points.** `scripts/latency_edge_curve.py` + `_verify.py` (NEW); imports
`superkey.super_event`, `market_taxonomy.py` band/sport buckets; reads `clob_price_tape` +
`trader_fills` (clean `ts`); prereg precedent `reports/PREREG_*`.

**API-budget/storage.** Pure DB reads over the accrued tape. Zero external calls.

**Source: rethink** (data substrate = tape + clean `ts`, B) **+ refined estimator** (A's and B's
event-clustered, within-category, prereg-first estimator are near-identical; the observable-denominator
and dual-clock skew reporting are carried in explicitly).

---

### Item 8 — Lift decision: COPY `ws.rs` into copy-trading-bot, do NOT generalize into `common`

**Before.** `ws.rs` (295 lines) is a working CLOB WS client but lives only in `trading-bot`; the run
prompt wrongly says "no websocket dependency exists in the workspace" (false — `trading-bot/Cargo.toml`
has `tokio-tungstenite=0.28`).

**After.** The connect/subscribe/PING/reconnect pattern is **copied** into
`copy-trading-bot/src/cycles/live_tape.rs` (F1) and the JSON-RPC loop is hand-written in `live_fills.rs`
(F2). `trading-bot/src/scanner/ws.rs` stays untouched.

**Rationale (honoring extend-don't-rebuild AND focus-discipline).** Generalizing a
`connect+subscribe+ping+reconnect` core into `common` is a public-API design task (closure-taking
handler, generic over event type) for two consumers whose **protocols differ** (F1 = CLOB text-PING;
F2 = JSON-RPC `eth_subscribe`/`getLogs`) — a single generalized core wouldn't cleanly serve both. The
codebase's own "extract on the second *identical* use" bar isn't met. Copying ~120 connect/reconnect
lines is lower-risk and keeps each protocol legible. If a third consumer of the *same* protocol
appears, extract then.

**Integration points.** `copy-trading-bot/Cargo.toml` (+`tokio-tungstenite`); `live_tape.rs`,
`live_fills.rs` each own their loop. No `common` API change.

**Source: refined** — A's copy-over-generalize reasoning (F1≠F2 protocol) resolves the lift question B
left as "lift verbatim"; both agree the destination is copy-trading-bot, not a `common` abstraction.

---

### Item 9 — Config, dual env plumbing, GAP-7 (consensus wire-in, scoped down)

**Before.** No live flags. GAP-7 as originally framed wires live fills into consensus to fix BOTH the
trajectory coarseness AND signal-formation lag — but the trajectory coarseness is a *measurement*
artifact.

**After.** All flags default-OFF (byte-identical when off). GAP-7 **split**: the trajectory hole is
closed **offline** by a tape backfill (unconditional, no `strict`-byte-identity risk); the live-vote
wiring is **doubly-gated** (F2 built AND P3 positive).

**Config (`copy-trading-bot/src/config.rs`, confique, mirroring `dense_capture:163`):**
```rust
#[config(env="LIVE_TAPE", default=false)]                pub live_tape: bool,
#[config(env="LIVE_TAPE_MAX_SUBS", default=200)]         pub live_tape_max_subs: usize,   // set from P0-A
#[config(env="LIVE_TAPE_LOOKBACK_HOURS", default=6)]     pub live_tape_lookback_hours: i64,
#[config(env="TAPE_RETENTION_HOURS", default=72)]        pub tape_retention_hours: i64,
#[config(env="LIVE_FILLS", default=false)]               pub live_fills: bool,            // F2, optional
#[config(env="LIVE_FILLS_RPC_WS", default="")]           pub live_fills_rpc_ws: String,
#[config(env="LIVE_CTF_ADDRS", default="")]              pub live_ctf_addrs: String,      // P0-verified
#[config(env="LIVE_ORDERFILLED_TOPIC0", default="")]     pub live_orderfilled_topic0: String,
#[config(env="LIVE_DEDUP_PRECHECK", default=false)]      pub live_dedup_precheck: bool,   // P0-B sets
#[config(env="LIVE_FILLS_TO_CONSENSUS", default=false)]  pub live_fills_to_consensus: bool,
```
**Dual plumbing** — same keys in **both** `.env.consensus` AND the `environment:` block of
`docker-compose.consensus.yml` (`${VAR:-default}`; container won't see `.env` alone):
```yaml
  - LIVE_TAPE=${LIVE_TAPE:-false}
  - LIVE_TAPE_MAX_SUBS=${LIVE_TAPE_MAX_SUBS:-200}
  - LIVE_TAPE_LOOKBACK_HOURS=${LIVE_TAPE_LOOKBACK_HOURS:-6}
  - TAPE_RETENTION_HOURS=${TAPE_RETENTION_HOURS:-72}
  - LIVE_FILLS=${LIVE_FILLS:-false}
  - LIVE_FILLS_RPC_WS=${LIVE_FILLS_RPC_WS:-}
  - LIVE_CTF_ADDRS=${LIVE_CTF_ADDRS:-}
  - LIVE_ORDERFILLED_TOPIC0=${LIVE_ORDERFILLED_TOPIC0:-}
  - LIVE_DEDUP_PRECHECK=${LIVE_DEDUP_PRECHECK:-false}
  - LIVE_FILLS_TO_CONSENSUS=${LIVE_FILLS_TO_CONSENSUS:-false}
```
**GAP-7 trajectory fix (unconditional, offline):** `scripts/backfill_trajectory_from_tape.py` (NEW) —
for each favorite signal, insert `signal_price_trajectory` rows at the grid using `clob_price_tape` asks
anchored on the sharp's fill `ts`, via the existing `insert_trajectory_point` (migration 034 shape). No
live path, no FK gymnastics, no risk to the pipeline.

**GAP-7 live votes (conditional — F2 built AND P3 positive):** in `run_live_fills`, after insert, when
`cfg.live_fills_to_consensus`, feed BUY fills through `trade_to_window_vote` (`consensus_cycle.rs:593`)
→ `insert_window_votes` → the hot lane's scoped-scoring sequence (`hot_lane.rs:132-163`:
`affected → load_window_votes → books_from_window_votes → score_router_only → upsert_consensus_signal`),
reused verbatim. Feeds the **same** `books_from_window_votes` so `strict` tiering (keyed on `net_count`)
stays **byte-identical**; scores only the router arm (never `strict`). Off ⇒ no live votes ⇒ byte-identical.

**Integration points.** `config.rs`; `.env.consensus`; `docker-compose.consensus.yml`;
`scripts/backfill_trajectory_from_tape.py` (NEW); `live_fills.rs` (conditional vote block reusing
`trade_to_window_vote`/`insert_window_votes`/`books_from_window_votes`/`score_router_only`/
`upsert_consensus_signal`, all `pub(crate)`, imported like `hot_lane.rs:32`).

**API-budget/storage.** Backfill = read-only over the tape. Live-vote path adds no new endpoint load
(fills already arrive via F2). Config: none.

**Source: rethink** — B's split (trajectory offline, live-votes doubly-gated) removes strict-byte-
identity risk from the trajectory fix; A's hot-lane scoped-scoring reuse carries the conditional half.

---

## Execution Order

Dependency-ordered; each step has a Verify gate. Two STOP/decision gates: **P0 measurement gate**
(gates the whole deliverable) and **P0 ingestion gate** (gates F2 only); plus the **P3 verdict**
(gates the P4 live-vote wire-in and confirms whether F2 was worth building).

1. **Worktree + skeleton.** `git worktree add wt/live-ingestion -b feat/live-ingestion main`. Confirm
   next migration is still 040. *Verify:* `git status` clean on branch; `ls migrations | tail -1` = 039.
2. **[P0] Item 1 probes** (unconditional). Run P0-A/B/C/D ≥30 min each; write
   `reports/live_ingestion_probe.json` + `reports/entries/<date>-probe-memo.md`. *Verify:* both gate
   verdicts computed from the STOP arithmetic; commit.
   - **★ GATE 1 (measurement):** if `tape_coverage_observable_pct < 95` or F1 unstable → write the
     NEGATIVE entry, deliver the probe, **STOP the run**. Else continue.
   - **★ GATE 2 (ingestion):** record `build_p1_live_fills` and `f2_dedup_layer` for Item 5; does NOT
     block the curve.
3. **[P1'] Item 2 migration 040** (columns + tape table; index 2c only if GATE 2 PASS). *Verify:*
   throwaway-PG apply is clean; `NewTraderFill` +2 fields compiles; poller path constructs `None`.
4. **[P1'] Item 3 `live_tape.rs` + Item 4 subscription** (unconditional; the real unblocker). *Verify:*
   `LIVE_TAPE=true` on the throwaway/staging DB writes `clob_price_tape` rows with `best_ask` populated
   (or the documented fallback); `LIVE_TAPE=false` ⇒ task not spawned ⇒ byte-identical; Rust unit tests
   + integration test green; full gate green; commit.
5. **[P2] Item 6 `live_reconcile.py`** on ≥24h of tape capture (+ dual capture if F2 built). Run the
   **adversarial verify** pass. *Verify:* `--self-test` green; coverage/fuzzy-join/dedup-proof numbers
   written to `reports/`; verify pass independently reproduces them; commit.
6. **[P3] Item 7 `latency_edge_curve.py`** — **prereg FIRST**, then the curve; run the **adversarial
   verify** pass. *Verify:* `--self-test` green; `reports/entries/<date>-latency-edge-curve.md` with
   band×sport drift, CIs, ¢/s verdict vs +3–5%/bet, consensus-formation replay; verify pass reproduces
   one cell; commit.
   - **★ P3 VERDICT:** decides (a) whether F2/P1 is worth building at all, (b) whether the P4 live-vote
     wire-in ships.
7. **[P1, OPTIONAL] Item 5 `live_fills.rs`** — build **only if GATE 2 PASSed** (and P3 shows the latency
   is worth it). Apply Item-5 dedup architecture per `f2_dedup_layer`. *Verify:* dedup proof (Item 6
   job 3) green on throwaway PG; `LIVE_FILLS=false` byte-identical; gate green; commit.
8. **[P4] Item 9 wire-in.** Trajectory backfill (unconditional). `LIVE_FILLS_TO_CONSENSUS` live votes
   **only if F2 built AND P3 positive**; else leave OFF/unshipped. *Verify:* `strict` signals
   byte-identical with flag off; trajectory backfill populates favorite grid points; gate green.
9. **Docs + ship.** DATA-MODEL.md (source/provenance + tape), PROGRESS.md, ≤10-line memory note for
   [[project-polymarket-consensus]] + [[project-polymarket-refined-strategy]], the auto-trader
   next-step entry-convention line (from the curve). Rebase on fresh main, re-gate, `merge --no-ff`.
   *Verify:* full gate + all `--self-test`s green on fresh main; migration number still free.

---

## API-Budget & Storage Summary

| Component | Endpoint | Connections | Req/s to data-api | Storage | Notes |
|---|---|---|---|---|---|
| P0 probes | CLOB WS / Polygon RPC / CLOB REST | 1–~40 (escalating) | 0 | 1 JSON | disjoint from data-api; anti-pattern guard runs BEFORE broad subscribe |
| CLOB price tape (F1) | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | `ceil(assets/max_subs)` ~5–15 | 0 | `events/s × 72h`, pruned; **events/s = P0-A** | disjoint from data-api → zero poller-429 contention |
| Token-map resolution | CLOB REST `/markets` | 0 | 0 | cache | 120ms-throttled; few-thousand one-off; only poller-shared surface |
| On-chain fills (F2, optional) | free Polygon RPC | 1 (+newHeads) | 0 | shares `trader_fills` (deduped) | different endpoint → no poller-429; getLogs 1 call/~2s block |
| Reconcile / curve / backfill | Postgres (read) + throwaway PG | 0 | 0 | none | pure DB reads |
| **Poller (unchanged)** | data-api | as today | as today | as today | **spine untouched** |

Unbounded-growth risk (tape) is explicitly bounded by tracked-only subscription + `TAPE_RETENTION_HOURS`
prune; `events/s` is measured in P0-A before commit.

---

## Existing Infrastructure Leveraged

- **`trading-bot/src/scanner/ws.rs`** — CLOB WS connect/subscribe/PING/reconnect pattern (copied, not
  generalized); `tokio-tungstenite=0.28` already workspace-resolved (zero version churn).
- **`insert_trader_fills` (`consensus.rs:1270`)** — the single shared dedup gate; extended (not cloned)
  to bind `source`/`live_seen_at`.
- **`trade_to_fill` (`consensus_cycle.rs:307`)** — reused verbatim so live taxonomy can't drift.
- **`hot_lane.rs:41,132-163`** — the additive-lane + scoped-scoring template for the F2 task and the
  P4 wire-in.
- **`dense_capture.rs:47` / `fetch_clob_market`,`outcome_token_id`,`fetch_best_ask` (`models.rs:301,330,352`)**
  — 120ms throttle citizenship + token/price resolution.
- **`insert_trajectory_point` + `signal_price_trajectory` (migration 034)** — the trajectory store the
  offline backfill writes into.
- **`scripts/superkey.py::super_event` (`:43`), `market_taxonomy.py`** — event-clustering + band/sport
  buckets for P2/P3.
- **`common/src/metrics.rs:194,214`** — dual `counter!` + readable `AtomicU64` mirror for the new
  `record_live_*` metrics.
- **`live.rs:227,440` `if cfg.flag { spawn }`** — byte-identical-when-off gate.
- **Throwaway-PG (port 55432)** — Rust integration test + the dedup-injection proof.
- **`trader_fills.ts` = clean fill clock** (`trade_to_fill` sets `ts: tr.timestamp`) — the anchor that
  makes the curve independent of any on-chain build.

---

## Open Questions (resolved during implementation)

| Question | When | How it resolves |
|---|---|---|
| Does `best_bid_ask` carry `best_ask`? Does any message carry a `timestamp`/`exch_ts`? | P0-A | Subscribe + inspect raw frames; record `best_ask_present_pct`, `exch_ts_present_pct`. If `best_ask` absent → `last_trade_price` + `fetch_best_ask` REST fallback (Item 3). |
| Real per-connection max subscriptions (vs the `200` constant)? | P0-A | Binary-search `take(N)` escalation until updates stall; set `LIVE_TAPE_MAX_SUBS`. |
| Tape `events/s` (storage sizing)? | P0-A | Count events over the ≥30-min window; size `events/s × 72h`; adjust retention if large. |
| Do `OrderFilled` `maker`/`taker` = data-api **proxy** wallets (not EOA/operator)? | P0-B | Decode ≥50 known-tx logs, compare to `trader_fills.wallet`; `address_match_pct`. If EOA → F2 needs an address map (ingestion-gate STOP; curve unaffected). |
| Does on-chain `usdc/share` price round-trip to the stored VWAP `price`, at what rounding? | P0-B | `price_size_roundtrip` on ≥50 fills → selects the F2 dedup layer (tx-index-round10 vs source-scoped+collapse). **Already verified the poller price is full-precision VWAP, so 2dp rounding is ruled out.** |
| `eth_subscribe(logs)` wss vs `newHeads+getLogs` HTTP on a free RPC? | P0-B | Hold each ≥30 min; prefer whichever is gap-free without rate-limit; default `newHeads+getLogs`. |
| CTF-Exchange address(es) + `OrderFilled` topic0? | P0-B | Confirm by decoding a log whose `tx_hash` is in `trader_fills`; store in config (`LIVE_CTF_ADDRS`, `LIVE_ORDERFILLED_TOPIC0`). |
| Fuzzy-join collision rate (attribution reliability)? | P2 | `live_reconcile.py` job 2 measures it; high-collision fills excluded from the latency floor. |

---

## Rejected Approaches

- **Round the live on-chain price to 2dp for tx-index dedup (Design B checklist item #1).** **REJECTED
  — broken.** Verified `[DB:mine]`: 50.2% of 24h fills (181,336/361,368) carry >2 decimals, 50,499 at
  16dp (`0.9969990269270036`); `trader_fills.price` is a full-precision VWAP (`size_usd/size`), and
  migration 027's index includes `price`. 2dp rounding gives a different key from ~half of poller rows →
  **double-count**. Replaced by Design A's source-scoped index + app pre-check + poll-over-live collapse.
- **Make the curve downstream of the on-chain fills build (Design A's original P1→P3 chain).**
  **REJECTED.** `trader_fills.ts` is already the clean fill clock, so the curve needs only price
  observation (F1 tape), not ingestion. Coupling the deliverable to a fragile free-RPC build means an
  RPC failure ships nothing. Decoupled per Design B.
- **One conflated STOP rule on "the feed."** **REJECTED.** It lets an ingestion-feed failure abort a
  measurement that never depended on it. Split into two independent gates.
- **`eth_subscribe(logs)` wss as the sole F2 transport (Design A).** **DEMOTED to fallback.** Free-RPC
  wss log subs are the first thing silently dropped, and a silent drop is a survivorship hole;
  `newHeads + eth_getLogs` over a known block range is resumable and gap-free. Probe both; prefer getLogs.
- **Clone `insert_trader_fills` into a 17-column `insert_trader_fills_live` (Design A).** **REJECTED —
  unnecessary divergence.** Extend the single insert to bind two nullable columns (poller passes NULL);
  the run prompt mandates the EXISTING dedup path.
- **Store `ingest_lag_ms` duration (Design A).** **REJECTED in favor of `live_seen_at` timestamp
  (Design B).** A stored timestamp lets lag be recomputed at read against the clean `ts` and any
  defended clock; a precomputed duration bakes in a possibly-skewed clock.
- **Generalize a WS core into `common` (Design A option a).** **REJECTED for this run.** F1 (CLOB
  text-PING) and F2 (JSON-RPC) protocols differ; one abstraction serves neither cleanly. Copy the
  pattern; extract only on a third same-protocol consumer.
- **Live F1 consumer + new `fill_price_trajectory` table for the trajectory fix (Design A GAP-2).**
  **REJECTED in favor of offline tape backfill.** The tape already holds every tick; a backfill script
  into the existing `signal_price_trajectory` closes the hole with no live path and no FK gymnastics.
- **Subscribe to all ~8k sports token_ids.** **REJECTED** (named anti-pattern). Tracked-only
  (few-thousand), sharded by the P0-measured max, staggered opens.
