# Consensus engine — data model & capture

What's captured, how it flows, how it's stored, and why it's futureproof. (Audited against the
live DB 2026-06-29.)

## Capture flow (where each row comes from)
```
leaderboard_tracker (hourly)  → followed_traders            (the tracked top-N universe)
consensus_cycle (2 min)       → consensus_signals (upsert)  one row per (strategy, market, outcome)
                              → consensus_signals.observed_votes  raw vote ATOMS (futureproof replay)
                              → consensus_alerts             one row per pushed alert
housekeeping (5 min)          → consensus_signals.resolved/outcome_won   via CLOB /markets/{condition_id}
                              → consensus_snapshots          the trajectory ("stock chart"), change-only
```
Every signal is keyed by `(strategy, condition_id, outcome_index)` and carries the full vote atoms,
the initial position, the live-price trajectory, and the resolution — so nothing about a signal's
life is lost.

## Core tables
| Table | Grain | Purpose | Growth |
|-------|-------|---------|--------|
| `consensus_signals` | (strategy, market, outcome) | the signal: consensus stats, atoms, initial position, resolution | bounded ≈ markets × strategies (upserted, not appended) |
| `consensus_snapshots` | (signal, time) | trajectory: net/backers/mean_entry/market_price over time | **change-only** — a row only when the chart moves (net/backers change or price ≥0.5¢) |
| `consensus_alerts` | (alert) | append-only log of every pushed alert | one per alert (rare) |
| `followed_traders` | (wallet) | tracked top-N universe + provenance (rank/pnl/vol/periods/seen) | bounded (~top-N, upserted) |

Key columns on `consensus_signals`: `observed_votes` (JSONB atoms), `initial_*` (set once),
`last_market_price`, `mean_price`/`mean entry`, `net_count`/`net_quality`, `is_sports`, `event_slug`
(cluster key), `resolved`/`outcome_won`/`resolved_at`.

## Executable entry price (`entry_ask`) — the realizable-ROI input
The honest P&L panel measures the outcome against a **realizable entry**, not the sharps' fill:
`entry = COALESCE(entry_ask, initial_market_price + EXEC_HAIRCUT)`. `initial_market_price` is the
first live CLOB **mid** a signal ever sees — set COALESCE-once in `snapshot_consensus_signal` on the
**first housekeeping pass to reach the signal**. That is NOT ≤5 min: the loop iterates the whole open
backlog at 120ms/condition, so a pass is **~10-15 min** (the 5-min figure is only the post-cycle
sleep), and base strategies fetch no mid at detection. So `initial_market_price` / `entry_ask` is the
**first-OBSERVED** executable price ~10-15 min post-alert — a serviceable proxy for a follower's fill
on a signal that resolves in hours, but NOT the alert-instant price, and it does not capture the
alert→first-observed drift (that drift is separately measured as `capture_lag = initial_market_price −
mean_price`). `entry_ask` is the real executable best **ask** from `/book`.

Capture state (columns on `consensus_signals`):
- `entry_ask` (mig 030) — best ask captured once while OPEN (set-once, `resolved=FALSE`, leak-free).
- `entry_ask_at` / `entry_ask_mid` (mig 032) — WHEN the ask was captured and the mid observed in the
  SAME pass (the /markets mid + /book ask are ~sub-second apart, two endpoints — not one tick).
  Together they (a) **time-stamp the capture** (`entry_ask_at − first_detected_at` = the capture lag)
  and (b) **measure the real haircut** (`entry_ask − entry_ask_mid`), replacing the `EXEC_HAIRCUT` guess.

First-price discipline: the ask is captured in the SAME housekeeping pass that first sets
`initial_market_price`, so `entry_ask_mid == initial_market_price` and both come from one pass.
If that first pass is capped/empty-book, a **lagged fallback** captures on a later pass — visible as
`entry_ask_at − first_detected_at`, so the REALIZED ROI can filter to first-pass rows (within
`REALIZED_DECISION_LAG_SECS`, a wall-clock proxy for `first_price` provenance — see audit #2).

History: capture was default-OFF (`CAPTURE_ENTRY_ASK=false`) and, when enabled, LAGGED (housekeeping
grabbed whatever ask existed whenever it next ran, not the ask paired with the first-observed mid).
The first-price capture + `entry_ask_at`/`entry_ask_mid` tagging (mig 032) pairs the ask with its mid.
The realized ROI **will rest on a measured ask as decision-time coverage accrues** — mig 032 does NO
backfill, so on freshly-captured rows only; until coverage is high the realized column is directional
(small, liquidity-selected N) and is NOT the same cohort as the blended `honest_roi` (see the board
note). When `entry_ask` is NULL (capture off / empty book / pre-032 row) the query falls back to
`initial_market_price + EXEC_HAIRCUT` — never a crash or a dropped signal.

## Storage efficiency
- **Upsert, not append** for signals — a market/outcome is one row per strategy, refreshed in place.
- **Change-only snapshots** — identical consecutive points are not stored (was ~20k/day of mostly
  duplicate rows; now only real moves). A stable market produces a handful of points; a volatile one
  produces the detail that matters.
- **Indexes**: unique `(strategy, condition_id, outcome_index)`; `strategy`, `resolved`, `tier`,
  `first_detected_at`; a **partial** index over open rows `(condition_id) WHERE resolved=FALSE` for
  the hot housekeeping scan; `snapshots(signal_id, ts)` and `snapshots(ts)`.
- **JSONB atoms** average ~600 bytes/signal — compact, and they unlock retroactive strategy replay.
- Postgres autovacuum reclaims the dead tuples from per-cycle upserts; no manual VACUUM needed.

## Durability / futureproofing
- **Resolutions can't be backfilled** (you can't recover a market's outcome timing after the fact),
  so the forward record is irreplaceable. A **daily `pg_dump`** runs via `scripts/consensus-backup.sh`
  (launchd `com.tue.consensus.backup`, 04:00, keeps 14 days) into `backups/`. Data lives in the
  `pgdata` Docker volume across restarts.
- **Migrations are append-only** (`migrations/0NN_*.sql`, idempotent `IF NOT EXISTS`) — schema evolves
  without destroying data; `sqlx::migrate!` applies them at boot.
- **Vote atoms are logged from day one** — any strategy invented later is replayable over all data
  already collected (the no-backtest superpower).
- To restore: `gunzip -c backups/<file>.sql.gz | docker exec -i <pg> psql -U bot -d polymarket`.

## Legacy tables (from the disabled per-trader copy + ML paths — kept, not used)
`bets`, `copy_trade_events`, `prediction_log`, `llm_estimates`, `portfolio`, `rejected_signals`,
`correlation_blocked`, `daily_snapshots`, `bet_features`, `telegram_users`. These are small and
inert now (`COPY_TRADE_ENABLED=false`). Left in place for futureproofing / optional re-enable; safe
to ignore. They are NOT part of the consensus forward record.

## Known future capture enhancement (documented, not yet done)
- **Executable bid/ask** (not just CLOB mid) per snapshot — needed for spread-net realizability/CLV
  on thin markets, and can't be backfilled. Deferred because it needs a per-token orderbook call
  (extra API load); the captured CLOB mid (`market_price`) is a serviceable proxy meanwhile.
  → **RESOLVED by the live CLOB price tape (migration 040 below):** real-time executable
  best_bid/best_ask over a websocket (zero REST/poller load), 1 Hz per asset.

## Live ingestion (migration 040) — provenance + CLOB price tape

Two feeds, both **flag-gated OFF by default** (byte-identical to pre-040 when off). Purpose: earn a
second-by-second answer to "what is fill-observation *speed* worth?" (the `latency_edge_curve.py`
deliverable), and, optionally, a ~1–5s on-chain fills path for tracking/copyability.

### `trader_fills` provenance columns (additive, nullable)
- `source` — `NULL` = poll spine (the ~3.0M-row default, back-compat); `'live_onchain'` = F2 fast
  fill; `'backfill'` = historical replay.
- `live_seen_at` — wall clock this process FIRST saw the fill on a live channel (`NULL` for poll).
  Latency is derived at read as `live_seen_at − ts` against the CLEAN exchange clock `ts`
  (`trade_to_fill` sets `ts = tr.timestamp`), so a mis-defended clock can be re-derived, not baked in.
  `ingested_at` is untouched and simply no longer used as a clock (5.5% of 24h rows carry >1h ingest lag).

### `clob_price_tape` (append-only, retention-pruned)
Every top-of-book move for tracked-market assets, from the CLOB market websocket
(`wss://ws-subscriptions-clob.polymarket.com/ws/market`, same protocol as `trading-bot/src/scanner/ws.rs`).
Columns: `asset_id, condition_id, outcome_index, event_type('book'|'price_change'), best_bid, best_ask,
last_price, last_size, side, exch_ts, recv_at`. Anchor OFFLINE by joining a fill's `ts` to
`(condition_id, outcome_index, exch_ts)` — no token map needed (the tape carries provenance).
- **exch_ts** = the frame's ms-epoch `timestamp`, the exchange clock — same domain as fill `ts` → curve
  anchoring has ~zero skew. TRUSTWORTHY only on `price_change` (real-time deltas); a `book` is a re-sent
  SNAPSHOT whose `timestamp` is the last-trade time (can be hours stale), so **`book` rows store
  `exch_ts = NULL`** and the curve/ordering fall back to `recv_at` (the true observation time). Coalesce
  bucketing and `compact_tape` order by the always-present, monotonic `recv_at` — never `exch_ts` — so a
  NULL/stale snapshot timestamp can never mis-sort and delete a real inflection.
- **Volume control (measured at 1000-user scale):** raw stream is ~4,000 events/s (287M rows/day) —
  untenable. The tape stores only **top-of-book INFLECTIONS**, keyed on `(best_bid, best_ask)`:
  1. **on-change** — emit only when `(best_bid, best_ask)` actually moves. `last_price` in a
     `price_change` is order-book-LEVEL churn (not a trade), so it is NOT in the key — including it
     stored a row on every level flicker for no curve benefit (measured: dropping it cut rows **7×**).
  2. **keep-LAST coalesce** — ≤1 row/asset per `TAPE_COALESCE_MS` (default 1000 = 1 Hz), emitting the
     SETTLED (last) value, flushed on bucket rollover OR when the asset goes quiet (stale-pending
     flush — no inflection is ever held indefinitely).
  3. **compaction sweep** (`TAPE_COMPACT_HOURS`, default 6) — `compact_tape()` drops consecutive-
     duplicate top-of-book rows the stream filter couldn't catch across reconnect/reshard boundaries
     (a fresh stream re-sends a `book` snapshot of the unchanged book).
  **Measured** (1478 assets, real capture, `tape_compression_study.py`): the full `(bid,ask,last_price)`
  key = 23.2M rows/day; the top-of-book key = **3.2M rows/day (13.7%)**, provably LOSSLESS for both
  `best_ask` (curve) and `best_bid` (spread/mid/CLV) — the study reconstructs the step function and
  asserts identity. Bounded further by the hourly `TAPE_RETENTION_HOURS` prune. **Measured live
  (2026-07-07, LIVE_TAPE on):** 2.45M rows/day, ~740B/row on disk (long `asset_id`/`condition_id` TEXT
  + 3 indexes), so **~5GB @72h** after compaction; `TAPE_RETENTION_HOURS=48` → ~3.4GB if leaner is wanted.
  Live latency recv−exch_ts p50 **75ms**; coverage **93%** of tracked fills; the per-connection subscribe
  ceiling is activity-dependent (`LIVE_TAPE_MAX_SUBS=200`, not 500 — see the 2026-07-07 production audit).
- **Subscription universe:** tracked-only (conditions a followed trader filled in `LIVE_TAPE_LOOKBACK_HOURS`)
  — ~1.6k tokens at 6h even across all 1012 followed wallets; sharded at `LIVE_TAPE_MAX_SUBS=500`
  (P0-A: 500/conn safe, 0 disconnects) → 3–4 connections; pool sized `LIVE_TAPE_MAX_CONNS=8` (4000-token
  headroom for future growth). Endpoint disjoint from the data-api poller → zero 429 contention.

### `trader_fills_live_txkey` (source-scoped unique index)
Collapses live-vs-live OrderFilled replays (reconnect / getLogs-range overlap). Constrains ONLY
`source='live_onchain'` rows, so it can't touch the full-precision poller rows. Cross-source dedup is
NOT index-based — the poller stores a full-precision VWAP price (51% of 24h rows carry >2 decimals; 15%
of fills are multi-level VWAPs that don't even match at 10dp) and the widened tx index (migration 027)
includes `price`, so a reconstructed on-chain f64 would not collide. Cross-source dedup is the app-level
`filter_existing_txkey` pre-check + the idempotent `collapse_live_over_poll` sweep (poll row wins).
