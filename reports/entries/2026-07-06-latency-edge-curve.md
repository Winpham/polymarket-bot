# Latency → edge curve — live fill ingestion (migration 040)

**Date:** 2026-07-06 · **Branch:** `feat/live-ingestion` · **Both gates PASS.**

## Pre-registration (fixed in `latency_edge_curve.py` before the run)
- grid `t ∈ {1,5,15,30,60,120,300,900}s`, anchored on fill `ts` (clean exchange clock).
- cells `band(price) × sport(category)`; metric `drift = best_ask(asset, ts+t) − fill.price`,
  signed toward the fill side (BUY: ask firming up = +).
- CI: event-clustered bootstrap (`superkey.super_event`), 1000 resamples, 95%; resample EVENTS.
- baselines WITHIN category (no pooling — composition-attack lesson); OBSERVABLE denominator;
  underpowered cells → INDETERMINATE-BY-POWER (n_events < 30).
- anchor on `exch_ts` (same clock domain as `ts` → ~zero skew).

## Two-gate decision (P0)
| Gate | Result |
|---|---|
| **GATE 1 — measurement** (gates the curve) | **PASS** — `tape_coverage_observable_pct = 99.91%` @30s TOL (≥95%), 45-min window, median fill→tape gap **0.11s**, best_ask 99.98% / exch_ts 100% present, 3 connections, 22 disconnects (coverage held). |
| **GATE 2 — ingestion** (gates F2 only) | **PASS** — OrderFilled address_match **100%** (proxy wallet is the log maker/taker), price/size reconstructs, free RPC stable, no rate-limit. `f2_dedup_layer = source_scoped+collapse` (15% of fills are multi-level VWAPs → tx-index rounding ruled out). |

## Preliminary curve (45-min capture, 2026-07-07 00:01–00:46 UTC)
18,042 raw BUY fills → 426 event-deduped → **357 observable**. Cells are INDETERMINATE-BY-POWER on a
single 45-min window (3–5 events/cell) — **the pipeline and signal are validated; power comes from
production accrual over days.** Signal (soccer, most data):

| cell | n_ev | drift@1s | @5s | @30s | @60s | @900s |
|---|---|---|---|---|---|---|
| soccer 0.55–0.75 | 5 | +1.53¢ | +1.82¢ | +2.08¢ | +1.82¢ | +1.23¢ |
| soccer 0.45–0.55 | 4 | +0.76¢ | +0.84¢ | +1.31¢ | +1.27¢ | +1.30¢ |
| soccer 0.75–0.90 | 3 | +1.91¢ | +1.82¢ | +1.75¢ | +1.92¢ | +0.46¢ |

**Read:** the executable ask **firms +1.5–2¢ within the first seconds** of a sharp BUY and stays
elevated ~15 min — a front-loaded copy tax. Most of the move is already present at t=1–5s, so the
first-order lever is *seeing the fill fast at all* (F2's ~1–5s vs the poller's ~90s), more than
shaving 60s→5s. CIs are wide (power-limited) and exclude 0 for most points; the powered read is the
forward deliverable.

## What shipped
- Migration 040: provenance (`source`, `live_seen_at`) + `clob_price_tape` + source-scoped live index.
- `live_tape.rs` (F1) — flag `LIVE_TAPE`, 1 Hz on-change tape (~28M rows/day at full 1000-user scale).
- `live_fills.rs` (F2) — flag `LIVE_FILLS`, OrderFilled→~1–5s fills, three-layer dedup, RPC constants
  in config. Built + unit-tested; OFF by default.
- Instruments: `probe_{f1_tape,f2_onchain,build_token_map,coverage}.py`, `live_reconcile.py` (dedup
  proof), `latency_edge_curve.py`, `backfill_trajectory_from_tape.py` — all `--self-test` green.
- **Not shipped:** P4 live-vote wiring (doubly-gated on a POSITIVE powered curve — not yet).

## Next
1. Enable `LIVE_TAPE=true` in production → accrue days of tape → re-run the curve for powered cells.
2. With the powered curve, decide `LIVE_FILLS=true` (set `LIVE_FILLS_RPC_HTTP`) and the P4 wiring.
