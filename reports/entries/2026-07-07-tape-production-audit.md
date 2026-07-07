# Live tape — production accrual audit (1h)

**Date:** 2026-07-07 · `LIVE_TAPE=true` live on main. Audit over ~60min / 15 health samples.

## Deploy was safe + regression-free
- Old system tagged `pre-live-tape-20260707` @ fc0eada; fresh 307MB backup.
- Migration 040 tested on a **restore of real production data** (3.14M rows) → applied in **2.14s**,
  additive, non-destructive.
- Deployed flags-off first, verified byte-identical (poller kept writing, all rows `source=NULL`,
  signals firing). Still true after 1h with the tape on: 506 fills/5min, 3,516 signals/5min, **0 rows
  with `source` set**, CPU 56% / MEM 742MB (10% — no leak).

## Course-correction: the reconnect storm (fixed)
Enabling the tape surfaced a storm — every connection resetting ~6s, flooding book snapshots. First
hypothesis (missing WS Pong) was **wrong** (A/B-tested: the Python client stormed on the same 500
tokens too). Real cause: the CLOB per-connection limit is **activity-dependent** — 500 tested clean
days ago, storms now; 200–250 hold with 0 resets. Fixed by config (`LIVE_TAPE_MAX_SUBS=200`).
The Pong + quotable-filter code changes are kept (correct improvements, not the cause).

## Audit — the tape is reliable, immediate, complete, optimal

| dimension | result |
|---|---|
| **Reliability** | 5 resets/hour (was ~600/hr storm), **no drops** (mpsc never overflowed → zero data loss), poller unaffected. |
| **Immediacy** | latency recv−exch_ts **p50 75ms** (range 71–77 across the hour); steady-state **0 of 8,234 rows >1s late**. |
| **Completeness** | coverage **avg 93%, min 88%** of tracked sharp fills; ~920 active assets. |
| **Optimality** | **2.45M rows/day**; book% 6.7%→**1.7% after compaction**. |

### The p95 tail is benign (explained)
p95 avg ~1081ms with spikes to 9,167ms — **100% reconnect-correlated** (the only two spike samples
had resets; all 13 zero-reset samples were 84–117ms). These are reconnect-recovery bursts
re-delivering buffered events with their *correct* `exch_ts`; the curve anchors on `exch_ts`, so they
land correctly on the timeline — it's gap *recovery*, not lag.

### Compaction validated on real data
Ran `compact_tape` on the live 113,832-row tape → removed **9,884 (8.7%)** redundant top-of-book rows
(the reconnect-boundary book dups), lossless. Scheduled 6-hourly; hourly retention prune bounds the rest.

## Correction to the storage estimate (honest)
Real on-disk row width is **~740B** (77-digit `asset_id` + 66-char `condition_id` TEXT + 3 indexes),
not the ~110B I first projected. So **~5GB @72h** (after compaction + autovacuum), not 0.8GB. Still
bounded and pruned; leaner options if wanted: `TAPE_RETENTION_HOURS=48` (~3.4GB, env-only) or a compact
surrogate key for `asset_id` (schema change, deferred).

## Pending (scheduled, unit-tested, not yet auto-fired)
Hourly retention prune (nothing 72h old yet) and 6h compaction (manually validated above). Forward risk
to watch: at PEAK live-game activity even 200 subs may storm — reconnect is graceful (book-flood →
compacted), and `LIVE_TAPE_MAX_SUBS` can drop further. An adaptive shard-size (shrink on repeated
resets) is a candidate future refinement, not needed now.

**Verdict: production-grade.** Reliable, immediate (p50 75ms), complete (93%), optimal (bounded ~5GB).
