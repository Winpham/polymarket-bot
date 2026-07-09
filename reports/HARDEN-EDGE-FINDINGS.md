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

## 1. Persistence (the binding gate) — full ledger in `reports/PERSISTENCE-LEDGER.md`

Re-generated all four persistence instruments live (`regime_edge`, `regime_net_edge`,
`regime_persistence`, `persistence_tracker` — all `--selftest` green) on the current record.

**Verdict: `SOCCER-ARTIFACT` / INDETERMINATE-BY-POWER — re-confirmed and quantified.**

- The **recurring (non-expiring) regimes are directionally positive AND net-positive after the copy
  tax** — mlb\|2026-07 +11.2% gross / **+7.4% net**, nba/cbb\|2026-07 +36.4% / **+32.8% net**. This
  is the most hopeful fact in the system.
- But the gate is **power**, not the point estimate:
  - **0/4** recurring regimes clear the 10-cluster floor (best: mlb\|07 at 7 clusters).
  - Only **1** recurring regime is net-positive with **LB>0** (nba/cbb, N=4) — need ≥2.
  - Cross-regime permutation null is **structurally inert** (min achievable p_conc 0.353 — can't fire
    below ~5–6 regimes).
  - Temporal OOS pooled surplus is **−0.87% (flat)** — so count-power could resolve **REFUTED**.
  - Expiring regimes carry **67% of edge mass** (tennis 43%, other 27%, soccer 17%).
- **`forward_track.py` verified**: correctly accrues + gates forward non-soccer regimes (0 since the
  07-06 seal — only ~2 days elapsed — all INDETERMINATE-BY-POWER, binding = months). Working; needs time.

**Months-to-power (concrete):** Only **MLB** is a non-expiring sport firing at volume now (~0.9
clusters/day). MLB alone hits its 10-cluster floor in ~1 week, but that is one sport. The binding wall
is a **second non-soccer sport in-season**: World Cup ends ~07-19, Wimbledon ~07-12, NBA offseason to
~10-21, NFL starts ~09-10. ⇒ earliest 2nd independent non-soccer recurring regime at power = **NFL,
~early Oct 2026 (≈3 months)**; robust ≥5-regime non-expiring panel = **~Nov 2026–Feb 2027 (4–6
months)**. Even then, PERSISTS is conditional — current OOS edge ≈ 0. **No run can manufacture this.**

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
