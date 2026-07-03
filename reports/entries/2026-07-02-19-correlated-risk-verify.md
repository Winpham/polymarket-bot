# Entry 19 — Correlated Risk, verified: the finding holds, the cap RECOMMENDATION was overstated

**Date:** 2026-07-02 · **Branch:** `feat/corr-risk-verify` (worktree off `main` 81db85b, tag
`pre-corr-risk-verify-20260702`) · **Status:** paper-only, read-only, zero migrations, nothing
promoted, no env/alert change. The adversarial audit of entry 18 / D20. One new self-testing
instrument (`scripts/corr_risk_verify.py`) + a Rust-code fidelity check. Artifact:
`reports/corr_risk_verify.json`.

## Why this run exists

D20 recommended re-keying the exposure cap to the GAME (**≤3 units/game**), claiming it "bounds
the worst single-game block 35%→21% while preserving 91% of growth — the knee." That was stated
with more confidence than the evidence supported. This run attacks the result on its three load-
bearing modeling assumptions and asks, with kill criteria, whether it is TRUE or a modeling
artifact. **The headline: the phenomenon is real and robust; the specific cap recommendation was
overstated and is here CORRECTED.**

---

## Q3 — data-model fidelity: the Monte Carlo's atomic unit is correct ✓

Read the Rust directly (not assumed). The consensus bot stakes **one flat bet per
`(strategy, condition_id, outcome_index)` row** — `append_paper_bet(... cfg.flat_stake ...)` per
resolved signal (`copy-trading-bot/src/cycles/housekeeping.rs:163`), ledger keyed
`ON CONFLICT (strategy, condition_id, outcome_index)` (`common/src/storage/consensus.rs:896`).
Event/`event_slug` clustering exists **only in the edge/promotion statistics** (`consensus.rs:624`),
NEVER to pool or size stakes. So the position-grain Monte Carlo (one stake per DB row) is faithful
to the code. (Record grew to **229 positions / 80 games** by live accrual; one condition_id has 2
outcome-index rows = 2 legitimate bets, not a double-count.)

## Q1 — tail-model robustness: the result SURVIVES ✓

Re-ran every policy under three tail models at λ=0.5, **8 seeds × 2500 paths**: D20's
Gaussian-homogeneous; **Gaussian-heterogeneous** (directional markets w=0.55, the near-independent
total/exact-score markets w=0.08 — 122 directional / 107 independent positions); and the **adverse
t-copula + heterogeneous** (ν=4, per-game χ² tail dependence, scipy). Findings:

- **The cap-vs-P1 p95 ordering is STABLE** where the caps actually bind (cap_1, cap_2, dir_cap_1/2:
  Δp95 same sign across all three models). It "flips" only for cap_3/cap_5, where Δp95 ≈ **±0.3pp ≈
  0** — i.e. those caps barely change p95, and the sign of a near-zero difference is Monte-Carlo
  noise, not model-dependence.
- **The t-copula fattens the single-GAME worst-block tail but is DILUTED at the portfolio level**
  (worst-block −$1648→heavier, but p99 maxDD ≈ 31% under Gaussian *and* t). Over ~80 games one
  heavy-tailed block is diversified away. **So the Gaussian assumption did NOT materially understate
  the portfolio tail** — a genuine robustness pass, not a lucky one.

## Q2 — the honest override was NOT justified on portfolio metrics ✗ (the correction)

D20's cap recommendation rested on an "honest override": the average-path DD ceiling is slack, so
prefer a construction-bounded cap. This run tests whether any per-game cap **dominates P1 on the
downside** (CVaR₅ ↑ AND p99 maxDD ↓ AND worst-block ↑) under the adverse model. **No cap does.**
The two downside metrics tell OPPOSITE stories:

| policy | bets | worst single-game block (band) | portfolio CVaR₅ (band) | p99 maxDD | K5 (λ=1 growth) |
|---|---:|---:|---:|---:|---:|
| P0 flat_shares | 229 | **−$606** | **−$359** | **11%** | 30% |
| **P1 (≤1/event, no game cap)** | 116 | −$1648 | **−$1390** | 31% | **100%** |
| P2 ≤1/game | 80 | **−$1173** | −$1580 | 30% | 73% |
| P2 ≤3/game (D20's pick) | 103 | −$1490 | −$1514 | 31% | 92% |
| P4 per-game Kelly | 116 | **−$1156** | −$1434 | 28% | 71% |
| **P5 dir-cap ≤1 (market-aware)** | 107 | −$1557 | −$1437 | 31% | 94% |

- **On the worst single-game block, the caps DO help** (P1 −$1648 → cap_1 −$1173, P4 −$1156;
  non-overlapping seed bands). D20's mechanism is real — a per-game cap bounds the specific-game
  catastrophe.
- **On portfolio CVaR₅ and p99 maxDD, P1 (no cap) is the BEST Kelly policy**, and every cap makes
  CVaR₅ *worse* (−$1390 → −$1514…−$1586). The caps drop **+EV diversifying volume** (especially the
  near-independent total/exact-score markets), which lowers the whole outcome distribution including
  its 5th percentile. So capping trades *worse* typical-tail + *less* growth for protection against a
  *rare specific-game* catastrophe. **That is a risk-aversion CHOICE, not a Pareto improvement — and
  D20 presented it as closer to the latter.**
- **The dominant risk lever is the KELLY FRACTION, not the game cap.** P0 flat-shares has 4× better
  CVaR₅ (−$359) and 11% p99 maxDD vs every ⅛-Kelly policy's ~31% — regardless of game cap. This
  **converges with D18/D19's "de-lever the band-5 Kelly"**: the leverage, not the game-stacking, is
  the first-order tail driver.

## Q5 — a real refinement: if you cap, cap DIRECTIONAL, keep the independent markets ✓

The blunt count cap ranks by band-edge, so it **keeps the directional markets (the correlated
tail-carriers) and drops the near-independent totals/exact-score** — exactly backwards for tail
control. The market-type-aware cap (`P5 dir-cap`: keep all independent markets, cap only DIRECTIONAL
units/game — classified by slug string, no outcome fitting) **Pareto-dominates the blunt cap_3**:
better growth (K5 94% vs 92%) AND better CVaR₅ (−$1437 vs −$1514). It doesn't beat P1 on CVaR, but
among *capping* policies it is strictly better than the blunt count cap. So the refinement is real:
**the independent totals/exact-score markets are diversifying +EV ballast — keep them; bound only the
directional stack.**

## Q4 — false-positive / null: the "good trade-off" IS the (unproven) edge

- **λ=0 (efficient market, δ removed): every policy loses to costs** (median −$812) ✓ — the machinery
  is not manufacturing profit.
- **The copula's entire edge is δ = realized-WR − mean-price ≈ +0.14, and δ is SHUFFLE-INVARIANT**
  (any permutation of outcomes preserves WR and price ⇒ δ unchanged: real δ +0.143 = shuffled δ
  +0.143). So **this sizing engine cannot self-validate the edge** — δ's reality (is the favorite WR
  genuinely above the price-implied prob, or favorite-longshot bias?) is the **selection-null's job**
  (`selection_null.py` / D16: favorite p=0.0000, beats blind-favorite +6–11pt), NOT this engine's.
  The "good risk/profit trade-off" is therefore **conditional on δ being real**, which is the
  unchanged D7/persistence wall (NOT-YET) — not a new validation.

---

## Verdict — what is TRUE, what was OVERSTATED, what is REFINED

**TRUE and robust (survives t-copula, heterogeneous correlation, 8-seed CI, correct data grain):**
the correlation unit is the GAME; the favorite book is game-concentrated (229 positions / 80 games,
66% WC); a per-game cap really does bound the worst single-game block; and at λ=0 everything loses.

**OVERSTATED in D20 (corrected here):** that ≤3/game "improves the risk-adjusted trade-off / is the
knee." It does **not** improve portfolio-level downside (CVaR₅, p99 maxDD) — it *worsens* CVaR by
shedding +EV diversifying volume, and only bounds a *rare* specific-game block. The per-game cap is
**optional targeted insurance, not a Pareto win**, and the **Kelly fraction is the first-order risk
lever** (P0 flat is 4× safer than any ⅛-Kelly cap).

**REFINED (a genuine improvement over D20):** if a per-game cap is used at all, use the
**market-type-aware** form — keep the near-independent totals/exact-score markets (+EV ballast), cap
only the DIRECTIONAL units/game. It strictly beats the blunt count cap on both growth and CVaR.

**Corrected recommendation (PROPOSED, not applied — Tue's call):** the base policy is **P1: ⅛-Kelly
per band, ≤1/event, no mandatory game cap** — best portfolio downside AND growth. To harden the
tail, **the ordered levers are (1) de-lever the Kelly fraction** (⅒–⅟₁₆, per D18/D19 — first-order),
**then (2) an OPTIONAL market-type-aware directional cap** for the rare stacked-game catastrophe —
NOT the blunt ≤3/game of D20. And the whole trade-off remains **conditional on the edge**, which
only forward persistence (≥K adverse correlated days across ≥5 non-expiring regimes, months) can
establish.

## Kill criteria outcomes
- Q1 ordering-stable: **PASS** (stable where caps bind; "flips" are ≈0-difference noise).
- Q2 cap-dominates-P1-downside: **FAIL for all caps** → D20's cap framing corrected (as above).
- Q4 null: λ=0 **PASS** (loses); δ shuffle-invariance **demonstrated** (edge is δ's, not this engine's).
- Q5 market-aware Pareto-beats blunt cap_3: **PASS**.
- K4 nothing live changed: **confirmed**.

## What was NOT done / limitations
- No live/Rust change; the corrected recommendation is proposed, not applied.
- The heterogeneous w_dir/w_indep are ASSIGNED by market-type string and SWEPT, not fit (no upset in
  the record to estimate them — the binding uncertainty remains, per K2).
- The de-lever lever itself (⅒/⅟₁₆-Kelly) is D18/D19's domain; this run confirms its primacy but
  does not re-derive the optimal fraction.

## Rollback
`git revert` the merge of `feat/corr-risk-verify`; delete `scripts/corr_risk_verify.py` +
`reports/corr_risk_verify.json`. No migrations, env, or live behaviour touched. D20's instruments
remain; this entry corrects its *interpretation*, not its code.
