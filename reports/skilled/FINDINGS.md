# FINDINGS — "Identify the Genuinely Skilled" (compounding ledger)

Run date 2026-07-05. Snapshot: `trader_fills` 2,469,459 fills / 491 wallets (2023-01-12 →
2026-07-05). Cohort for every skill test: **non-MM directional** (churner screen). All tests
event-clustered at `ev=COALESCE(event_slug,condition_id)`, split leak-free by placement time.
Pre-registered gates in `PRE_REGISTRATION.md` (frozen before any number was seen).

Each row: verdict · statistic (LB/CI) · forward-N · what would flip it.

| # | Signal | Verdict | Key stat (95%) | N | What would flip it |
|---|--------|---------|----------------|---|--------------------|
| 0.2a | Blind-surplus rank persistence | **REFUTED (NULL)** | ρ=−0.04, CI [−0.21,0.14] | 116 wallets | — (frozen wall) |
| 0.2b | Realized-ROI rank persistence | **REFUTED (NULL)** | ρ=−0.06, CI [−0.23,0.13] | 116 | — |
| 0.2c | Success-rate selection (top-tercile edge retained) | **REFUTED (NULL)** | −0.016, CI [−0.037,0.004] | 116 | — |
| 2a | Mean-surplus (baseline) | **REFUTED** | ρ=−0.04, tercile LB −0.004 | 116 | ρ_lo>0 & tercile LB>0 fwd |
| 2b | Sign-consistency (robust location) | **REFUTED** | ρ=+0.02, tercile LB −0.020 | 116 | same |
| 2c | Empirical-Bayes shrinkage rank | **REFUTED** | ρ=+0.03, tercile LB −0.013 | 116 | same |
| 2d | Calibration slope | **REFUTED (least-dead)** | ρ=+0.08, CI [−0.11,0.26]; tercile LB +0.005 | 116 | persistence CI must exclude 0 |
| 3 | Structural attributes ×6 (entry-timing, price-discipline, band-frac, bet-size CV, sport-HHI, cadence) | **REFUTED (NULL)** | 0/6 generalize out-of-cohort; signs flip between folds | 100 (A51/B49) | out-of-cohort LB>0 in both folds + Bonferroni |
| 4-persist | Round-trip / timing PnL persistence | **REAL** (not noise) | ρ=+0.62, CI [+0.30,+0.83]; tercile late LB +0.39 | 33 non-MM | — (confirmed) |
| 4-copy | Timing → **copyable** directional surplus (selector) | **INDETERMINATE-BY-POWER** | ρ=+0.29, CI [−0.07,+0.57] | 30 | CI must exclude 0 (needs more traders/time) |
| 1-persist | Tape-derived **CLV** persistence | **INDETERMINATE-BY-POWER** | ρ=+0.27, CI [−0.09,+0.59] | 36 | forward gate: CLV_lo>0, ≥50 ev, 2 windows |
| 1-copy | CLV → copyable directional surplus | **INDETERMINATE-BY-POWER** | ρ=+0.14, CI [−0.26,+0.48] | 36 | same |

## What is REAL
- **Round-trip / timing skill persists** strongly early→late (ρ=0.62). This is genuine and
  reproducible — but it is the **trading/spread-capture mechanism**, structurally **uncopyable**
  by a taker-follower (you cannot capture the trader's EXIT at their price), and it is **not**
  the same wallets as directional edge (its cross-prediction to copyable direction straddles 0).
  Real skill, wrong kind for the mission.

## What is REFUTED (do not re-open)
- **Every past-outcome ranking** — blind-surplus, ROI, success-rate, and the reduced-variance
  cousins (sign-consistency, EB-shrinkage, calibration slope). Confirmed AGAIN on the current
  2.47M-fill snapshot, event-clustered. The winner's-curse wall stands.
- **Every ex-ante structural attribute** tested — none generalizes to a disjoint trader set;
  in-sample signs flip out-of-cohort. Max-of-noise, killed by the out-of-cohort + fold test.

## What is INDETERMINATE-BY-POWER (positive lean, underpowered — accrue, do not promote)
- **CLV** (the lead): tape-derived CLV persistence point estimate is positive (ρ=0.27) with a
  clean near-zero fleet mean (−0.004, sanity OK), but only 36 wallets clear ≥10 CLV-events/half;
  CI includes 0. **Needs forward accrual to the pre-registered gate.**
- **Timing→direction selector**: positive point (ρ=0.29) but CI includes 0 at n=30.

## Multiplicity note (WS-5)
No signal cleared its pre-registered in-sample / out-of-cohort gate (every copyable-mission
statistic's lower bound ≤ 0). With **zero** gate-clearers across a family of ~13 signals, there
is nothing to submit to the label-permutation null or orthogonality test — the family produced
fewer survivors than noise alone would occasionally manufacture. The two positive leans (CLV,
timing→direction) are **below** the certification bar, not above it.

## Bottom line
Past PnL cannot find the skilled (re-confirmed). No retrospective signal — including the
reduced-variance and structural classes — survives. The one real signal (timing) is uncopyable.
**CLV is the only lead with a positive forward-shaped point estimate, and it is power-limited;
only forward CLV accrual (months) can decide it.** That is the honest verdict the mission
anticipated.
