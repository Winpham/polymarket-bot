# PRE-REGISTRATION — `weather_low_fav` (lowest-temperature) shadow arm, forward gate

**Frozen:** 2026-07-12T19:30:00Z (UTC). **Branch:** `feat/evergreen-portfolio`. **Paper-only,
promotes nothing, arms nothing, real-money eligibility UNCHANGED. Champion `favorite` +
`weather_fav`/`weather_fav_liq` + `ConsensusParams::default` + every incumbent BYTE-IDENTICAL**
(the family refactor is guarded by a byte-identity test). Default-OFF behind
`CONSENSUS_WEATHER_LOW_ARM`; `alerting=false`.

Inherits, without re-derivation, the audited conventions of the weather prereg: day/region-clustered
small-cluster t(G−1) LBs, `selection_null`, corrected fee `0.03·p·(1−p)`, capture broad (0.71–0.98) /
certify narrow (0.71–0.90).

## 0. Why this arm is SEPARATE from `weather_fav`

High- and low-temperature markets are siblings with **different mechanisms**, so they get different
arms rather than one blended `temperature` filter: the casual crowd prices *hot* favorites about right
(blind favorite ≈ +2%) but **MIS-prices cold ones** (blind favorite negative), so the sharps'
skill-over-blind is much larger on lows — on a far **thinner** book. Blending would average away the
very asymmetry that made a portfolio worth attempting. Each branch certifies on its own gate or is
retired; neither is ever carried by its sibling.

## 1. The locked objective (identical in form to the weather gate)

> **θ = cluster-robust one-sided 95% LOWER BOUND of realizable ROI-on-turnover, clustered at the
> resolution DAY.** Realizable entry = the captured `entry_ask` (fee `0.03·p·(1−p)`); a pick with no
> captured ask is EXCLUDED from θ. Win rate, total P&L and the NUMBER OF ARMS are DIAGNOSTIC ONLY.

Primary certification cell: **0.71–0.90** (a-priori: deep chalk 0.90–0.98 earns ~0/$ — the win-rate
trap — and adds no selection skill). The arm still CAPTURES 0.71–0.98; that slice is tracked separately.

## 2. Floors — INDETERMINATE until ALL met (frozen)

1. **Volume:** ≥ 20 distinct resolution-DAY clusters with a captured `entry_ask` AND resolution.
2. **≥2 DISJOINT WEEKS**, each with ≥ 5 day-clusters, spanning ≥ 20 distinct active days.
3. **Disjoint-regime robustness:** θ LB stays **> 0** under **leave-one-week-out** (drop each calendar
   week in turn). An edge that survives only WITH its dominant week is that week's streak.
4. **Belief-blind:** `selection_null` p_emp ≤ **0.01** (≥1000 matched draws, matched on band × day),
   AND skill-over-blind > 0 **at the realizable `entry_ask`** — never merely at the sharps' fill.
5. **Copyability:** measured at the captured `entry_ask`, with the spread tax reported. A fat % on
   unfillable size is not a strategy. (`weather_fav_liq` fired 0 on enable — these books are THIN.)

## 3. Head-to-head (the diversification question)

`weather_low_fav` earns a promotion review only if, on top of §2, its day-level return correlation with
`weather_fav` is **|corr| < 0.3** over **≥ 20 common days**. A correlation estimated on <20 common days
is **INDETERMINATE** and may not be used to claim diversification, however favourable.

## 4. VERDICT AS OF FREEZING — **FAILED · RETIRED · STAGED OFF**

Run against this gate on the data that exists today (2026-07-12, after the resolver fix made a second
disjoint week available for the first time):

| test | result |
|---|---|
| picks / days / weeks (0.71–0.90) | 59 / 9 / W27 + W28 |
| `sharp_fill` LB (directional ceiling) | **−3.5%** (point +9.6%) |
| **leave-one-week-out** | **FAILS — min fold LB −35.9%** |
| `selection_null` | p = 0.0085 (passes) |
| realizable `entry_ask` θ | **UNMEASURED** — arm never enabled, 0 captured asks |

The discovery run's low-temp read (+4.0% LB, +16.3% skill-over-blind, n=21/5 days) **was a single-week
artifact.** Instructively, the selection null *passes* — the sharps really do pick cold favorites well —
but the realized edge **does not survive dropping a week**, and the pooled LB is negative once the
second week resolves. **Selection skill is not money at our price.**

Per this run's own rule — *an arm that cannot clear its own gate over ≥2 disjoint weeks is RETIRED, not
carried on hope* — the arm is **staged OFF and recommended OFF**. It is genuinely power-starved (59
picks), so this means "do not enable on this evidence," not "proven worthless."

## 5. Re-opening condition (frozen, deliberately narrow)

Re-open ONLY on an **a-priori mechanism** stated before looking (e.g. a cold-market structural reason
the summer book cannot express), never on a rescan, a re-slice, or a widened band. Any re-open starts
from this gate unchanged — floors may be ADDED, never loosened. Enabling the live flag is a human
decision; nothing here promotes.

## 6. Guardrails (unchanged)

Paper-only; `alerting=false`; default-off flag; no `.env` ARMING edits; champion + every incumbent arm
byte-identical; cost-zero (no `ANTHROPIC_API_KEY`, no child `claude`); DB read-only except the bot's
normal accrual writes (the one-off resolution backfill writes exactly the rows the daemon's own
resolver would have written, and nothing else).
