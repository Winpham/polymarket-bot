# Maker-Copy G3 — forward maker-fill simulator (measure, don't assume)

**Date:** 2026-07-08 · **Branch:** `feat/maker-copy-g3` · **Instrument:** `scripts/maker_copy_g3.py`
(`--selftest` green) · **Artifact:** `reports/maker_copy_g3.json` · **Extends:** D26 (Market-making
KILL+PARK). Paper-only, read-only, **promotes nothing, no capital.**

## The question
Copy the sharps we follow with a **maker** order — rest a BUY at the sharp's fill price P instead of
paying the taker spread. G2/G2b explicitly punted the one unanswerable historical question to G3:
does the resting bid actually fill, and on which side of the outcome? Since 2026-07-07 we ingest a
forward top-of-book tape (`clob_price_tape`), so G3 is finally buildable. This idea was **wrong
twice** (G2 v1 "+4.8% LB" = a units bug × a backwards complement rule), so the run was
pre-registered blind to outcomes (`reports/PREREG_20260709T011424Z_maker_copy_g3.md`) and gated on an
adversarial audit.

## What the data actually is (the load-bearing finding)
The ingested `clob_price_tape` is a **faithful top-of-book (`best_bid`/`best_ask`) inflection series
with NO trade tape.** On a `price_change` event, `last_price`/`last_size`/`side` are order-**book-level
churn** — the resting size at a level that moved — **not executed trades** (`live_tape.rs:141-142`,
comment `:222-223`; independently verified by the audit against the Rust). Consequence: the
pre-registered **volume-based REALISTIC** model ("cumulative `last_size × price ≥ stake`") is **not
measurable** — building it would count quote flicker as volume, the exact G2-class trap. Recorded as a
forced, outcome-blind deviation in `PREREG_..._ADDENDUM.md`. So the realized **volume / queue-capture /
partial-fill** fraction remains **OPEN** (still needs a real trade tape; data-api `/trades` is
offset-capped for busy markets, per G2b). The simulator **never reads `last_size` in a fill decision**
(audit-confirmed inert).

## Method
Universe (frozen): `strategy='favorite'`, resolved, fired after the tape start, with (a) a followed-
sharp BUY in `[T−5m,T+5m]` and (b) tape coverage after `T=first_detected_at`. **N = 20 signals, 19
event-clusters, 2 calendar days.** P = the earliest sharp BUY fill (the entry we copy). Fill decision
brackets the unknowable queue position with three `best_ask`-only models:
**OPTIMISTIC** (best_ask≤P touched — 100% capture ceiling), **DWELL** (≥2 touches spanning ≥30s —
repeated availability, *not* verified-continuous), **PESSIMISTIC** (best_ask<P strict — traded
through). Sweeps: decision-lag {0,12,60}s (no look-ahead: fills before T+lag dropped), cancel-after
{5,15,60m, until-tape-ends}. Cost = the honest ledger's contract (stake $100, fee 2% buffer + fee 0).
Cluster-robust LB via `effective_n.cluster_robust` + `regime_edge.lb_small_cluster` (event and day
grains). Head-to-head taker reference = **decision-time tape ask** at T (causal).

## Results (fee 2% buffer; the full menu is in the JSON)
- **Taker reference on the same 20 signals:** ROI **−18.6%** at the decision-time tape ask (mean entry
  **0.809**), −17.8% at anchor+1¢, −16.0% at the (capture-lagged) `entry_ask`. Favorites won 70% at a
  ~0.77–0.81 entry — below break-even on this 2-day sample, so the **taker also loses** here. Small,
  unlucky window.
- **Maker gets a better entry than taking-at-detection.** Resting at the sharp's P (mean 0.786) beats
  the decision-time ask (0.809), so **maker−taker on the filled subset is +2.4% to +3.7% at every
  cell** — the sharp lifted the ask ~3 min before we detect, so a taker copying at T buys into the
  elevated ask; the maker's resting P is cheaper. This entry edge is **real but power-limited.**
- **Adverse selection is real and, at realistic long rest windows, dominates.** At `cancel=until-tape`:
  fill 80–85%, but `wr_missed → 100%` while `wr_filled ≈ 62–65%` → adverse-WR gap **−35% to −38%**,
  and we still **miss 21–29% of the winners** (they drift to $1 and never come back to P). Filled ROI
  −21% to −23%. The entry edge is swamped by catching the reverters.
- The only non-negative adverse-WR cells (dwell/pess at **15m**: +8%/+14%) are **refuted as noise**
  (Fisher p = 0.64 / 1.0, n_filled 8–9) compounded by short-horizon censoring — 15 min is too short
  for the winners to run away, so they're still sitting in the filled set. Give them time and the sign
  flips hard negative (the 60m/RES cells).

## Adversarial audit (mandatory gate; 3 independent Opus skeptics, refute stance)
- Fill machinery **SOUND**: no look-ahead (fills before T+lag dropped), clock resolved on
  `exch_ts`/`recv_at` (mean skew 0.15s), `last_size` inert, historical G2 bugs structurally
  unrepresentable. Verdict derivation double-locked and correct.
- **One real leak caught + fixed:** the taker's stored `entry_ask` is captured ~20 min post-detection
  (`entry_ask_at=NOW()`, per-cycle-budgeted) — a **future price** flattering the taker ~1.8pp and
  contaminating the head-to-head. Replaced with the causal decision-time tape ask. This **reversed**
  the pre-fix "maker underperforms taker everywhere" into the correct "maker has a real +2–4% entry
  edge, adversely selected." Reporting the contaminated version would have been a wrong (if
  pessimistic) conclusion — the gate earned its keep in the honest direction.
- Two labeling fixes applied: DWELL relabeled (2 touches spanning 30s, not continuous dwell);
  `maker_edge_per_signal` flagged as abstention-confounded (never a fair maker-vs-taker read).

## Verdict — INDETERMINATE-BY-POWER (accruing)
N=20 filled ≤17 < 30 floor; **2 day-clusters < 5** is the binding wall (day-LB t(1) is uninformative:
−0.78 to −1.64). No cell reaches GO (needs power AND filled-LB>0 AND adverse-gap≥0 AND maker≥taker AND
audit-survival). **Nothing promoted; D26 KILL+PARK and the legal-posture gate stand.** The *lean* is
toward confirming the adverse-selection trap at realistic rest windows, but paired with a genuine
entry-price edge — both under-powered. This is the honest, anticipated outcome for a ~2-day tape.

## Limitations / forward path
Tape ~2 days deep and self-compressing; "until-resolution" is bounded by tape coverage (~hours,
universe = hot-6h), not settlement. Volume/queue-capture still OPEN (needs a trade tape). The
instrument is **idempotent and read-only** — re-run as the tape deepens; it reads accruing rows,
nothing to persist for the measurement. A GO would need ≥30 filled signals across ≥5 day-clusters
with filled-LB>0 after fees and a non-negative adverse-selection gap — at which point Phase 2 (a
persisted forward maker paper-ledger, migration 041, coordinated) could be earned. Not today.
