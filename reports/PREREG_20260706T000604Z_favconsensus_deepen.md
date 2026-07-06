# PRE-REGISTRATION — Favorite-Consensus: Deepen, Re-verify, Diversify

**Frozen at 2026-07-06T00:06:04Z, BEFORE any outcome-conditioned number of this run was computed.**
Only composition data (signal counts, day×sport mix, wallet counts) was inspected prior to freezing.
Run charter: `RUN — Favorite-Consensus: Deepen, Re-verify, Diversify`. Branch
`research/favconsensus-deepen` (worktree; deploy `main` untouched; all arms alert-OFF; paper-only).

## 0. Data inventory at freeze (composition only)

| Quantity | Seed (2026-07-02 docs) | Now (2026-07-06) |
|---|---|---|
| Distinct UTC event-days (graded consensus record) | ~2.4 (06-29→07-01) | **7 full** (06-29→07-05, +partial 07-06) |
| `favorite` graded signals / distinct super-events | 220 pos / 78 games | **325 graded / 104 super-events** |
| `favorite` soccer share (super-events) | ~89% (rows) | **22.1%** (23/104; tennis 55, mlb 14, esports 5, nba/cbb 4, politics 2) |
| Followed wallets (universe) | "handful of backers/signal" era → top-250 rollout | **560 followed / 284 active / 506 with fills** |
| Historical mine (`trader_fills`) | — | 2,622,995 fills / 506 wallets / 517 fill-days (2022-12→2026-07) |
| Dense capture (`signal_price_trajectory`) | **0 rows** | **3,345 rows / 186 signals** (accruing since 07-03) |

Caveat frozen in: tennis = Wimbledon = EXPIRING regime (regime_classify Rule E), same as WC soccer.
The recurring-regime question is decided on **mlb, nba/cbb, esports, crypto, econ/other** cells only.

## 1. The statistic (identical to the shipped instruments — no re-derivation)

- Per pick: `a = outcome_won − entry`, `entry = COALESCE(initial_mean_price, mean_price)` (at-fire).
- **Surplus-over-blind**: `a − blind_edge[band]` where `blind_edge[band]` is the `_blind` strategy's
  event-clustered mean edge in the same price band (5 equal bands, `int(p*5)+1`, as in
  `selection_null.py` / `adversarial_battery.py`). Band scheme FROZEN at 5×0.2.
- **Cluster key**: match-level `super_event` (`scripts/superkey.py`) — never `event_slug`, never rows.
- **SE**: cluster-robust at super-event grain; day-clustered read reported alongside (both shown, per
  D17 effective-N convention; the binding accrual count = distinct UTC days and distinct super-events).
- Realizable variants use `entry_ask` where captured; 2% fee stays a conservative BUFFER (never booked
  as recoverable).

## 2. The gate (ALL must hold for CERTIFIED; frozen thresholds)

1. **As-of & leak-free** — features known at bet time; splits by WHOLE super-events only.
2. **Event-clustered surplus** at super-event grain (day-grain reported).
3. **Bonferroni lower bound > +3%** after the measured copyability tax (§H5). Bonferroni divisor =
   number of (hypothesis × cell) tests in that hypothesis family, counted in each family section below.
4. **≥30 distinct super-events** in the cell (N_eff reported when ICC>0).
5. **Persistence across ≥2 DISJOINT regimes**: clears on ≥2 different sport-categories, or on both
   frozen time blocks **A = days ≤ 2026-07-01** and **B = days ≥ 2026-07-02** (blocks frozen here,
   chosen as seed-window vs new-accrual boundary, before outcomes were seen).
   Soccer-only or Wimbledon-only ⇒ NOT certified (both expiring).
6. **Selection-matched permutation null p ≤ 0.01** (`selection_null.py` machinery, N_PERM=2000,
   **seed 20260706**, null matched on (band × UTC-day) composition).

Verdict vocabulary: **CERTIFIED** (all 6), **INDETERMINATE-BY-POWER** (positive but a gate fails on
N/power — name the failing gate + the LB), **REFUTED** (sign flips under the null / mirror / holdout).

## 3. Hypothesis families (Bonferroni counted per family)

### H1 — Core re-verify (family size 4)
1. `favorite` surplus-over-blind > 0 (all bands pooled, bands 4+5 in practice).
2. Band decomposition: 0.6–0.8 premium ≥ 0.8–1.0 premium (the sweet-spot claim).
3. Longshot block: consensus-on-longshots (<0.45 entry, bands 1–2 + band 3 lower half) surplus ≤ 0.
4. flat-SHARES P&L ≥ flat-$ P&L on the full graded record (sign check, $100-flat vs 100-share).
No new thresholds; this is a re-measurement of the seed numbers on 7 days.

### H2 — Regime cells (family = number of cells with ≥10 graded events; counted at runtime, reported)
Cells = (sport-category × band ∈ {4,5} × time-block ∈ {A,B}) for `favorite` picks.
A cell is CERTIFIABLE only at ≥30 super-events (gate 4); cells with 10–29 events are reported as
accrual targets with their current LB. **Abstention rule (frozen, not tuned):** abstain from
(a) bands 1–3 entirely, (b) the standing DODGE cells of `reports/map` state v002
(`mlb/deriv/0.60–0.80` and the two non-favorite residue DODGEs), (c) any sport-category with <10
graded favorite super-events on the record. Abstention is judged by: Δ(pooled LB) and Δ(fraction of
positive UTC days), abstained vs not — no other abstention variant will be scored.

### H3 — Routing enrichments (family size 3)
On the historical mine + forward record, judged at OUR repriced entry (follower-tax adjusted):
1. **Regime-conditional scorecard**: wallet trust computed per sport-category (vs global) — does the
   per-sport follow-set beat the global follow-set's forward surplus?
2. **Conviction weighting**: following only fills ≥$1k (frozen threshold — mine showed >$10k
   strongest but N collapses; $1k is the pre-registered compromise) vs all fills.
3. **Survivorship correction**: forward reads including CAPTURE_DROPPED recovered fills vs without —
   report the bias direction and magnitude (measurement, no certification claim).
UNION MM-exclusion stays ON for all three. Frozen scorecard procedure (no fitted learner, no new
parameters beyond the $1k threshold above).

### H4 — Relational layer (family size 1; parameter budget frozen)
**Model (frozen):** for wallet pair (i,j), conditional lift `L_ij = P(win | i∧j back) − P(win | i backs)`,
shrunk toward 0 with prior weight **m=20 events** (Beta-style shrinkage). A pick's relational score =
rank-weighted consensus score + **β=1** (not fitted) × mean shrunk L over the pick's observed backer
pairs, top-**K=5** pairs by |L| per pick. Parameter budget: {m=20, β=1, K=5} — all frozen here, zero
fitting on outcomes.
**Test:** split by WHOLE super-events, alternating odd/even by first-detection order (both halves
scored; report both). PASS only if relational ordering beats rank-weighted ordering (surplus of top-N
picks at equal N) on BOTH held-out halves AND the full gate. Otherwise **kill and report the negative.**

### H5 — Copyability tax (measurement, no certification)
From `signal_price_trajectory`: tax = (first executable price ≥60s after fire) − (at-fire mean_price),
per band × sport-category. Where the trajectory lacks a ≥60s point, the row is excluded (no imputation).
Output: tax table + tax-adjusted realizable LB for every H1/H2 positive. The 2% fee buffer is NOT
netted out.

## 4. Anti-patterns bound to this run (from the charter — violations void the result)
No threshold tuning beyond the frozen values above; no within-event splits; no online/fitted router;
no forward reads on wallet sets that stop capturing at deactivation (H3.3 exists to measure this);
no real money; alerts stay OFF; a single-pass positive is not a result until the §8 adversarial
verify pass (independent re-derivation, mirror test, null re-run) has attempted to kill it.

Seeds: python `random.seed(20260706)` everywhere; N_PERM=2000.
