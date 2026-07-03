# FINDINGS — Specialist Selection (the compounding ledger)

One row per lever. A lever joins the **surviving set** only after the belief-blind
gate passes **AND** it adds *independent* edge over the current surviving set
(WS-5 orthogonality vs favorite AND global `trust_weighted`). REFUTED /
INDETERMINATE-BY-POWER rows are **kept, with the number that killed them**, so no
session re-runs a dead idea. Every new lever is tested against the *current*
surviving set — findings compound, they don't pile up correlated copies.

Verdict vocabulary: **SURVIVED** (gate + orthogonality) · **REFUTED** (gate says
no / null manufactures it) · **INDETERMINATE-BY-POWER** (can't tell on current
data — a finding, not a failure) · **SHIPPED-FOUNDATION** (mechanism/plumbing, not
itself an edge claim) · **PENDING-FORWARD** (built, silent, accruing forward data).

Surviving set so far: **∅** (nothing certified — expected; forward data is thin).

---

## Foundation (WS-0, Items 1–2) — mechanism only, no edge claim

| id | what | config | verdict | notes |
|---|---|---|---|---|
| F1 | Trust floor 30→25 | `TrustParams{min_events:25}`, pilot stays 50 | SHIPPED-FOUNDATION | lifts gate-grain reach 59→72 wallets; hairline-25 still Indeterminate (tested). Does **not** relax margin/Bonferroni/selection-null. |
| F2 | `bet_type` axis | mig 037; `bet_type_bucket`; new `bettype` slice | SHIPPED-FOUNDATION | `other`≈16% = honest crypto binary; classifier unit-tested. Forward-only meaning (historical rows read `other`). |
| F3 | favorite-residual cell-blind | `(sport,band)` blind, cascade → band → 0 | SHIPPED-FOUNDATION | differs from band-blind by up to ±0.44 in high-vol cells (00-baseline §7). Neutralizes favorite-loading **at the verdict**. Never fails open (cascade). |

## Levers (WS-1…WS-4) — pre-registered here BEFORE running; gate decides

_(none run yet — WS-1 specialist map next; each lever gets a row with hypothesis ·
exact config · verdict · LB/CI · forward-N · orthogonality vs surviving set · what
would flip it, BEFORE it runs.)_

---

## Pre-registered kill-criteria (from the AUTONOMOUS spec §8) — a lever is NOT real if ANY hold
1. the specialist book does **not** beat `favorite`-only out-of-cohort/forward → favorite in disguise;
2. per-cell heterogeneity does **not** persist across the in/out temporal split → fit, not skill;
3. a **label-permuted null** manufactures "certified specialists" at the observed rate → multiplicity ate it;
4. survivors add **no independent edge** over favorite in the orthogonality test → redundant, not diversifying.

## Standing truths (don't re-derive / regress)
- Congregation (per-sport book) was **DEAD** 2026-06-30 (0 certified). This program is a *different object*
  (re-weights votes inside an already-+EV consensus) — but the death modes (multiplicity, favorite-in-disguise)
  are identical. Be willing to conclude it's still congregation-2.
- `elite_fresh_fav ⊂ favorite`; **0/12 strategies diversify favorite** — no free orthogonal edge yet.
- Real money stays gated on the unchanged pilot bar (N≥50 events, ≥5 regimes) + de-lever + months. This run
  flips none of that; all arms silent/default-OFF.
