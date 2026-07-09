# PRE-REGISTRATION — `favorite_v2` forward gate (frozen 2026-07-09T15:42:54Z)

**Frozen BEFORE any forward-outcome analysis.** `favorite_v2` is a SHADOW arm (`alerting=false`,
paper-only, promotes nothing, arms nothing, real-money eligibility UNCHANGED). This document freezes
the metric, margins, power floor, and kill condition it must clear on FORWARD data before it may be
considered a challenger to the champion `favorite`. Amending this after seeing forward outcomes is a
goalpost-move and voids the gate.

## The arm (derived, not guessed — see POLICY-SEARCH-LOG.md)
`favorite_v2` = champion `favorite` (price_band 0.65–0.98, strict base) **+ two additive gates**:
- `min_total_usd = 1000` — at-fire one-sided backer volume floor (illiquidity mechanism).
- `require_backer_rank_lt = Some(5)` — require ≥1 backer with leaderboard rank < 5 (skill mechanism).

Both cuts were swept to a plateau, OOS-validated (time-split + non-FIFWC), confound-checked (rank is
not a price/sport/liquidity proxy), and clear the belief-blind selection-null in-sample.

## In-sample basis (for reference only — NOT the gate)
Corrected fee (sports `0.03·p(1−p)` taker, maker 0), turnover $100/bet, at-fire entry.

| | champion `favorite` | `favorite_v2` |
|---|---|---|
| resolved ROI (taker) | +2.81% | **+9.66%** (arm-exact fwd-semantics, covered: +11.23%, n=74) |
| OOS non-FIFWC ROI | −2.08% | **+7.63%** |
| belief-blind surplus / p_emp / LB | +2.85% / 0.13 / −1.07% | **+10.84% / 0.0000 / +5.86%** |

## THE FORWARD GATE (the only arbiter) — all must hold on FORWARD-accrued resolutions

**Realizable metric** (frozen): event-clustered resolved ROI-on-turnover at the corrected taker fee
(`audit_pnl_books` accounting, fee `0.03·p(1−p)`), measured on signals **first detected after
2026-07-09T15:42:54Z** (zero in-sample overlap). Champion measured on the SAME forward window.

1. **Non-inferiority + superiority.** `favorite_v2` realizable ROI ≥ champion `favorite` realizable
   ROI on the shared forward window (NI margin 0). Adoption as a challenger additionally requires it
   to **beat** the champion (point estimate) on that window.
2. **Belief-blind gate** (`selection_null.py --challenger favorite_v2`, reused, not reimplemented):
   p_emp ≤ 0.01 with `--calibrate` PASS, belief-blind LB > 3% margin, and **≥ 2 disjoint
   NON-SOCCER regimes** with surplus > 0 (SOCCER-ARTIFACT law: soccer never counts).
3. **Power floor** (gate is UNREADABLE below this — report "power-limited", not a verdict):
   ≥ 30 resolved events, ≥ 10 distinct UTC day-clusters, ≥ 2 non-soccer regimes at support.
4. **Non-regression guard** (`standard_guard.py`): champion `favorite` belief-blind LB must stay > 0
   on the same window; if the champion itself dies (regime change), that is flagged separately.

## KILL CONDITION (pre-registered)
`favorite_v2` **dies** (de-registered proposal, only the sport-map fix survives) if, once the power
floor is met, EITHER:
- it is **inferior to champion `favorite` by > 3 percentage points** of realizable ROI on the forward
  window, OR
- its **belief-blind LB ≤ 0** (the selection edge did not survive forward).

A power-limited window (floor unmet) is **neither pass nor kill** — it keeps accruing.

## Honest expectations
- The arm cuts ~39% of champion volume → forward accrual to the 30-event / 2-non-soccer floor is
  **~1.6× slower** than the champion's. Expect the gate to be **readable in ~2–3 weeks**, not sooner.
- In-sample the "≥2 non-soccer regimes" clause is **NOT yet met** (only tennis positive at support;
  mlb n=3, other n=7 below floor). This is the champion's own binding constraint; the forward gate,
  accruing new tennis/mlb/nba/esports regimes, is what resolves it. A pass is NOT guaranteed.

## Accrual verification
`favorite_v2` is registered in `default_portfolio` (asserted by unit test) and `LEDGER_STRATEGIES` is
unset in prod (default empty ⇒ `should_ledger` accrues every non-blind strategy, `housekeeping.rs`).
So on merge + autoupdater deploy the arm fires into `consensus_signals` and accrues into
`honest_paper_ledger` **automatically** — no config change required.

_Reproduce the derivation: `garbage_segments.py`, `policy_search.py {--sweep,--bbgate,--residual}`._
