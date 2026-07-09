# HARDEN THE FAVORITE EDGE — Findings

> Autonomous run on `~/polymarket-bot`, branch `harden-edge` off `main` (4940509).
> North star: *turn the favorite edge into a real, profitable edge we can be confident in — or
> prove, rigorously, that it can't be yet.* Belief-blind discipline (§3 of the run brief). No real
> money, DB read-only, cost-zero, nothing armed/promoted, `strict` path untouched.
> Both are success; a goal-sought green is failure.

---

## 0. Baseline reproduction (starting verdict — before any lever)

Reproduced the frozen champion (`reports/STANDARD-BASELINE.md`, frozen 2026-07-06) on the **current**
(more-accrued) data. Instruments re-run unchanged from `main`:

- `standard_guard.py --selftest` → **PASS** (12/12 invariants).
- `selection_null.py --calibrate` → **PASS** (p<0.05: 12% ≤20% bar; p∈[0.1,0.9]: 72% ≥60% bar) —
  the belief-blind gate is trustworthy (not anti-conservative).
- `standard_guard.py` (champion measured forward):
  - `favorite`: **197 ev · surplus +6.29% · z 3.58 · p_emp 0.0000 · LB +3.44% · 2 non-soccer
    regimes+ · SELECTION-REAL**
  - realizable edge (band-aware tax, event-clustered): family **+2.88%** over 169 ev
  - resolved-P&L (canonical ledger): **306 bets · +$388.5 · ROI +1.27%**
  - REGRESSION STATUS: **HEALTHY** (LB +3.44% > 0).

### The honest decay since the 2026-07-06 freeze (more data → weaker edge)

| metric | freeze (07-06) | now (more accrued) | direction |
|---|---|---|---|
| favorite events | 158 | 197 | +39 |
| selection surplus | +8.06% | **+6.29%** | ↓ |
| belief-blind LB | +4.93% | **+3.44%** | ↓ (toward the +3% floor) |
| resolved ROI | +2.17% | **+1.27%** | ↓ |
| non-soccer positive regimes | 3 | **2** | ↓ (`other` flipped −3.12%) |

**favorite per-regime (current):** soccer 82 ev **+7.11%**, tennis 76 ev **+5.27%**,
mlb 18 ev **+13.54%**, other 21 ev **−3.12%**.

The two surviving non-soccer positives are **tennis** (Wimbledon/ATP — seasonally expiring) and
**mlb** (only 18 ev). This is exactly the SOCCER-ARTIFACT / expiring-regime concern the freeze warned
about, now sharper: as fresh data lands the edge is **decaying and its regime support is thinning**,
not broadening. The champion is still SELECTION-REAL and HEALTHY, but the LB has moved from +4.93% to
+3.44% — closer to the +3% adoption floor / 0 regression floor.

**Starting verdict (unchanged, re-confirmed):** `real_money_eligible = false`, **2/4 GO gates**,
binding constraint = **persistence** (non-soccer, months), `edge_reality` also unmet (capture
coverage ~2%). Nothing here flips a gate.

---

## 1. Persistence (the binding gate)

_(in progress)_

## 2. Capacity & fills

_(pending)_

## 3. Edge refinement (challengers under the guard)

_(pending)_

## 4. Execution realism

_(pending)_

## 5. Sizing / risk

_(pending)_

## 6. Bottom line for Tue

_(pending)_
