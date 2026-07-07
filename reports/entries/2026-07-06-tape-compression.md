# Tape compression — store only top-of-book inflections

**Date:** 2026-07-06 · **Branch:** `feat/live-ingestion` · Follows the migration-040 build.

## Problem
The first cut keyed the on-change filter on `(best_bid, best_ask, last_price)`. But `last_price` in a
`price_change` event is order-book-**level churn** (the price level whose size changed), not a trade —
so it fired a stored row on every level flicker, for zero curve benefit. We only care about
**inflection points**: when the executable top-of-book actually moves, timestamped.

## Measurement (empirical, `tape_compression_study.py` on a real raw capture)
1,478 assets, 1.79M raw events, 482s wall-clock. Rows/day + a lossless-for-curve proof
(reconstruct the `best_ask` step function from each strategy's stored rows, assert identity):

| key | rows/day | % of full | best_ask lossless | best_bid lossless |
|---|---|---|---|---|
| `(bid, ask, last_price)` (old) | 23.2M | 100% | yes | yes |
| **`(bid, ask)` — top-of-book (new)** | **3.19M** | **13.7%** | **yes** | **yes** |
| `(ask)` only | 2.0M | 8.6% | yes | (bid dropped) |

→ Dropping level-churn from the key is a **7.3× further cut**, fully lossless for both the curve
(`best_ask`) and spread/mid/CLV (`best_bid`). Chose top-of-book (keep `best_bid`) over ask-only: the
extra ~1.2M rows/day buys the full executable book (future-proof), still 7× smaller than before.

## What shipped (`live_tape.rs` + migration-040 storage)
- **On-change keyed on `(best_bid, best_ask)`** — inflections only; `last_price` no longer triggers a row.
- **keep-LAST coalesce** at `TAPE_COALESCE_MS` (default 1000 = 1 Hz), emitting the settled value, with a
  **stale-pending flush** on the PING interval so an asset that goes quiet still emits its final
  inflection within ~10s (closes the keep-last tail; the earlier review's D4 residual).
- **`compact_tape()`** sweep (`TAPE_COMPACT_HOURS`, default 6): removes consecutive-duplicate
  top-of-book rows left at reconnect/reshard boundaries (a fresh stream re-sends an unchanged `book`).
  Proven lossless in `live_reconcile.py` (5→3 rows, step function unchanged).

## Net at 1000-user scale
~3.2M rows/day (down from ~23M), 72h retention ⇒ ~9.6M rows ≈ ~1GB, hourly-pruned + 6-hourly-compacted.
Reliable (no unbounded pending, no reconnect-dup accumulation), future-proof (configurable coalesce,
full executable book retained), self-compressing at the source.

**Gate:** clippy -Dwarnings + cargo test (288 pass) + 5 py self-tests (incl. compression study +
compaction proof), all green.
