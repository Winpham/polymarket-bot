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
**first housekeeping pass** (≤5 min after detection; base strategies fetch no mid at detection).
`entry_ask` is the real executable best **ask** from `/book` — the price a follower could truly hit.

Capture state (columns on `consensus_signals`):
- `entry_ask` (mig 030) — best ask captured once while OPEN (set-once, `resolved=FALSE`, leak-free).
- `entry_ask_at` / `entry_ask_mid` (mig 032) — WHEN the ask was captured and the mid at the SAME
  instant. Together they (a) **prove decision-time** (`entry_ask_at ≈ first_detected_at`) and
  (b) **measure the real haircut** (`entry_ask − entry_ask_mid`), replacing the `EXEC_HAIRCUT` guess.

Decision-time discipline: the ask is captured in the SAME housekeeping pass that first sets
`initial_market_price`, so `entry_ask_mid == initial_market_price` and both come from one moment.
If that first pass is capped/empty-book, a **lagged fallback** captures on a later pass — visible as
`entry_ask_at − first_detected_at` (the capture-lag histogram), so the realized ROI can filter to
decision-time-only rows (within `REALIZED_DECISION_LAG_SECS`).

History: capture was default-OFF (`CAPTURE_ENTRY_ASK=false`) and, when enabled, LAGGED — the only
site was the housekeeping snapshot loop, which grabbed whatever ask existed whenever it next ran, not
the ask paired with the decision-time mid. The decision-time capture + `entry_ask_at`/`entry_ask_mid`
tagging (mig 032) fixed both: the headline realized ROI now rests on a measured, decision-time ask.
When `entry_ask` is NULL (capture off / empty book / pre-032 row) the query falls back to
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
