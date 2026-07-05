# PRE-REGISTRATION — "Identify the Genuinely Skilled"

**Frozen:** 2026-07-05, BEFORE any signal was scored. Amendments append below with a
timestamp and reason; no silent edits. This document is the belief-blind gate. A signal
is real only if it passes the criteria written here, decided before the number was seen.

**Mission.** Skilled, persistently-profitable Polymarket traders exist (leaderboard = realized
on-chain PnL). Identify them EX-ANTE — predict who profits *forward*, not who profited in the
past. Every past-PnL signal has failed (see WS-0.2 frozen null). Find the non-PnL forward
signal, or prove honestly that only forward-CLV accrual can.

**Data snapshot at freeze.** `trader_fills`: 2,469,459 fills / 491 wallets, ts range
2022-12-15 → 2026-07-05. (Prompt was written at 1.79M/423; accrual is live.)

---

## Global conventions (frozen)

- **Event-clustering.** Every persistence/edge statistic clusters at
  `ev = COALESCE(event_slug, condition_id)`. One event = one cluster. N reported is
  N_events (or N_clusters), never N_fills. Correlated legs within an event do not inflate N.
- **Leak-free time axis.** Split by **placement day** = `(ts AT TIME ZONE 'UTC')::date`, the
  day the pick was MADE — never `resolved_at` (bulk-stamp, D1). Early and late windows are
  disjoint pick-sets. As-of microstructure/attributes use only fills with `ts < cutoff`.
- **Blind baseline.** The honest baseline is the fleet **favorite-residual per (band)**:
  `a = outcome_won - price`; `blind_edge[band] = AVG(a)` over the fleet in the SAME window;
  `surplus = a - blind_edge[band]`. `band = width_bucket(price,0,1,5)`. A signal must beat
  THIS, not raw ROI. (Sport optionally added as `(sport,band)` in robustness.)
- **Copyable price (when profit is claimed).** Returns at OUR realizable entry:
  `our_entry = price + 0.013 (follower tax) + band_spread`; `ret = (won - our_entry)/our_entry - 0.02 (fee)`.
  Convention identical to `refresh_router_followset` / copyability.py. Persistence tests of a
  *ranking signal* may use blind-surplus (variance, not level, is what persists); any
  *bankability* claim uses the copyable price.
- **MM exclusion.** Churner screen (WS-0.1, vindicated D29): a wallet is a market-maker
  (excluded from "skill" cohorts) iff NOT(`round_trip_rate<0.30 AND two_sided_rate<0.25 AND
  sell_buy_ratio<0.50`). MM profit is a mechanism orthogonal to prediction and structurally
  uncopyable by a follower. All skill signals are computed on the NON-MM (directional) cohort.

## Multiplicity (frozen — applies to the WHOLE search)

Signals tested across WS-2/3/4 × traders form one search family. Any survivor must additionally:
1. **Label-permutation null (`selection_null`)** over the whole search: shuffle the
   forward-outcome labels within event-clusters, re-run the FULL selection, repeat ≥1000×.
   A signal is real only if its observed forward statistic exceeds the **95th percentile** of
   the permuted-null distribution of the *max* statistic across the family (controls
   max-of-noise / winner's curse).
2. **Bonferroni** on the per-signal test as a sanity floor: α = 0.05 / (#signals tested).
3. **Orthogonality (`edge_orthogonality`)**: add independent edge over (a) the aggregate
   consensus edge and (b) every other surviving signal, forward. A signal that only re-expresses
   the aggregate adds 0 and does not count.

---

## WS-0.1 — churn classifier swap  (code, not a signal)
Replace `classify_trader_types` (`fpd≥400`) with the churner screen. **Accept criterion:**
re-classification flags ≈25 wallets as MM (was 115 under fpd) and restores ≈100 formerly
mislabeled directional traders; `cargo clippy -D warnings` + build + selftests green. The swap
changes only advisory `trader_type` + the paper `router_followset` union; **held off
auto-deploying `main`** and surfaced for Tue (main auto-deploys on HEAD advance).

## WS-0.2 — frozen retrospective NULL baseline  (reproduce the wall)
Reproduce, event-clustered, on the current 2.47M-fill snapshot: early→late persistence of
(a) blind-surplus rank, (b) realized ROI rank, (c) success-rate selection edge-retained.
**Expectation (frozen):** all ≈0 or negative (NULL). This is an anchor artifact, not a test to
pass — it documents that past-PnL ranking is exhausted so no later WS re-opens it.

## WS-1 — forward CLV instrument  (the lead; accrues, no verdict now)
**Gate (pre-registered, cannot certify this session — it accrues):** per-trader forward CLV
`= (mkt_price_near_resolution − entry_price)` on held direction, event-clustered. A trader's
CLV skill is REAL iff, forward and out-of-sample: **CLV lower bound (one-sided 95%, day/event
deflated) > 0** over **≥50 events** across **≥2 disjoint forward windows** (both windows'
point CLV same sign, each window ≥20 events). Cohort selection (which traders) is frozen at
capture start; no post-hoc trader picking. This session: build the silent instrument, turn on
accrual, report current N=0→ and the weeks-to-N ETA. **No verdict.**

## WS-2 — reduced-variance retrospective signals
Signals: **calibration slope** (Cox recalibration slope of trader's implied prob vs outcome,
vs the market's), **Brier/log-loss improvement over blind**, **empirical-Bayes shrinkage rank**.
**Gate:** early-window signal predicts late-window blind-surplus, event-clustered, Spearman
persistence **ρ_lo (95%) > 0** AND late-cohort (top-tercile by early signal) forward
blind-surplus lower-bound > 0. Must also clear the global multiplicity gate. **Kill if** any:
in/out persistence ≤0; permutation null manufactures it; no edge over aggregate; Bonferroni-fail.

## WS-3 — cross-sectional structural identifiers (EX-ANTE attributes)
Attributes (fit on IN-cohort traders, tested on a DISJOINT OUT-cohort): entry-timing (early/late
in market life), price-band discipline, market-type concentration (HHI), bet-size distribution
shape, activity cadence. **Gate:** attribute→forward-blind-surplus map fit on in-cohort has
out-of-cohort forward lower-bound > 0, survives Bonferroni over all attributes AND the
label-permutation null. **Kill** on the same four criteria.

## WS-4 — round-trip / timing skill axis
Leak-free round-trip realized PnL per trader (entry→exit matched at position grain), a skill
axis distinct from BUY-only directional `advantage`. **Gate:** early-window round-trip skill
rank predicts late-window round-trip PnL, event-clustered, ρ_lo>0 AND forward cohort LB>0;
clears multiplicity + orthogonality (independent of directional signals). **Kill** identically.

---

## Pre-registered honest kill-criteria (ALL WS)
A signal is NOT real if ANY holds:
1. It does not beat the aggregate consensus edge, forward / out-of-cohort.
2. It does not persist across the in/out (or forward) split (ρ_lo ≤ 0 or cohort LB ≤ 0).
3. A label-permutation null over the whole search manufactures it at the observed rate.
4. It adds no independent edge in the orthogonality test.

**Legitimate verdicts include:** "INDETERMINATE-BY-POWER" (CI straddles 0, N too small) and
"only forward-CLV accrual over N more weeks can decide." A sycophantic "it works" on the fit
window is a FAILURE, not a result. Nothing here promotes to real money; all arms silent/paper.
