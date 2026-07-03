# 2026-07-03 · WS-B — pin the de-lever Kelly fraction

**One line:** the honest de-lever knee is **⅟₁₂-Kelly**, sitting on a **flat objective plateau
spanning ⅛–⅟₁₆** (growth-per-tail-risk barely moves across it). The binding constraint is the
**P(maxDD>25%) ≤ 10%** feasibility cap, which rules out ¼ (41%) and ⅙ (14%). This converges with
D18/D19's "⅒–⅟₁₆" hint and keeps flat-shares (D21) as the honest floor. **Proposed, not applied.**

## What was built
`scripts/corr_risk_delever.py` — reuses `corr_risk_verify`'s adverse simulator (t-copula ν=4 +
heterogeneous within-game correlation) verbatim, so every number is comparable to D20/D21. It holds
the CAP question fixed (settled: D20→D21, the cap is not a free win) and isolates the **sizing**
question: sweep the Kelly multiplier `k` on the P1 constitution policy (all favorite positions, −5u
per-slate stop), `f_i = k·kelly_full[band_i]`, flat-shares as the floor. Objective (frozen):
**growth/100 ÷ fractional-CVaR₅ at λ=0.5, feasible ⇔ P(maxDD>25%) ≤ 10% at λ=0.5.** `--selftest`
PASSES (growth↑ in k, |CVaR|↑ in k, flat is the tail floor, λ=0 loses at every k).

## The frontier (favorite, 232 pos / 81 games, WR 93.1%, δ +0.138; 8 seeds; adverse t+hetero)

| k | feas @0.5 | OBJ | λ=0.5 g100 | CVaR₅ | p95 DD | P(DD>25%) | λ=1 g100 | λ=0.25 g100 | λ=0 med |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flat-shares | yes | 0.59 | +0.024 | −401 | 7% | 0% | +0.051 | +0.007 | −228 |
| ¼ | **NO** | 0.67 | +0.195 | −2898 | 42% | **41%** | +0.466 | +0.058 | −1524 |
| ⅙ | **NO** | 0.75 | +0.146 | −1958 | 31% | **14%** | +0.335 | +0.044 | −1092 |
| ⅛ | yes | 0.77 | +0.113 | −1466 | 25% | 5% | +0.263 | +0.035 | −853 |
| **⅟₁₂** | **yes** | **0.79** | +0.080 | −1009 | 18% | 1% | +0.179 | +0.025 | −658 |
| ⅟₁₆ | yes | 0.79 | +0.062 | −782 | 14% | 0% | +0.137 | +0.019 | −546 |
| ⅟₂₄ | yes | 0.77 | +0.042 | −546 | 10% | 0% | +0.092 | +0.012 | −399 |
| ⅟₃₂ | yes | 0.75 | +0.031 | −419 | 8% | 0% | +0.069 | +0.009 | −307 |

(OBJ = g100 ÷ (|CVaR₅|/bankroll); CVaR₅ in $ on a $10k bankroll.)

## The read
1. **The ratio is a plateau, not a peak.** OBJ is 0.77–0.79 across ⅛→⅟₂₄ — because both growth and
   CVaR scale ~linearly with leverage in this regime, so their ratio is nearly leverage-invariant.
   There is **no sharp optimum**; picking `k` is choosing an absolute risk level, not a ratio peak.
2. **The feasibility cap is what binds.** ¼-Kelly blows the drawdown budget (P(DD>25%)=41%, p95 DD
   42%) and ⅙ still breaches it (14% > 10%). **⅛ is the most aggressive feasible** but marginal
   (p95 DD exactly 25%, P(DD>25%)=5%). **⅟₁₂ is the OBJ-max feasible with real headroom**
   (p95 DD 18%, P(DD>25%)=1%) → the recommended knee.
3. **λ-sensitivity: the conservative binds.** argmax-OBJ by λ = {λ=1 → ¼, λ=0.5 → ⅟₁₂, λ=0.25 →
   ⅟₁₂}. Only the OPTIMISTIC λ=1 wants ¼ (and ¼ is feasible only if λ=1). At the λ we cannot rule
   out (≤0.5), the knee is **⅟₁₂**. Since WS-A's proxy read is λ̂≈0.15 — **below** the λ=0.25 that
   ⅟₁₂ is tuned for — the conservative reading pushes toward the **⅟₁₆ end of the plateau**, and
   **flat-shares stays the floor if λ≈0** (its λ=0 loss is the smallest, −228).

## Recommendation (proposed default for rule 3, NOT applied)
- **De-lever to ⅟₁₂-Kelly** as the pinned knee; treat **⅟₁₆** as the conservative default given
  WS-A's low λ̂; **flat-shares remains the floor** until an adverse regime accrues (D21).
- ¼-Kelly is off the table until λ is measured ≥ ~0.75 (only there does it clear the drawdown cap).
- This does not touch the cap question (D21) and is conditional on δ being real (selection-null, D16);
  every row carries the λ=0 loss column.
