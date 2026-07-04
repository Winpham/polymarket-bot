# 2026-07-04 — Unified risk policy (the survivor stack) + the fair best-trader benchmark

## Part 1 — the risk/diversification survey: what won, what was overturned

| attempt | verdict |
|---|---|
| D15 `kelly_eighth_capped` (risk_engine) | **OVERTURNED** by the bad-days stress test: at half the measured edge it breaches its own 30%-DD ceiling in 44% of years (VERDICT.md F1) |
| D17 orthogonal multi-edge book (portfolio_constructor) | Framework kept, book empty: 0/12 strategies add a second independent edge — the menu is [favorite] until something certifies |
| D20 per-game caps (corr_risk_engine) | **REJECTED** by its own verification (D21): caps worsen CVaR by shedding +EV diversifying volume |
| D21/D22 de-lever (corr_risk_verify/delever) | **SURVIVED**: Kelly fraction is the first-order lever; knee ⅟₁₂ (feasible), ⅟₁₆ conservative, flat-shares floor at λ≈0; ¼ and ⅙ infeasible |
| Sizing-deployment run (optimal_deploy) | **SURVIVED**: 13%/day blended-median-optimal under P(ruin)≤5%-even-if-fake; hard ceiling 16%; forward-sealed instrument running |
| flat-SHARES convention | Survived everything (flat-$ flips the sign; P0 flat ~4× safer on CVaR) |

**The pick = the composed survivor stack**, frozen as `reports/risk_policy.json` and applied
forward by `scripts/unified_book.py` (read-only virtual book, forward-sealed 2026-07-04):
flat-shares base → λ̂-gated Kelly ladder PARKED at the floor (λ̂ CI-lower must clear 0.25→⅟₁₆,
0.50→⅟₁₂; λ̂ is 0.15 fallback-dominated today) → 13%/day deploy cap → 2%/bet cap → entry ≥0.45
longshot block → NO game cap → DODGE steering stays owned by map_state at selection time →
slate stop kept as a brake (no DD-bounding claim). First read: +230 on 10k over the 4-day seed,
maxDD 1.3%, worst day −128 (flat-$100 same bets: +472 but worst −219 — the stack trades upside
for a bounded tail, by design). Verdict: INDETERMINATE, 1/20 forward day-blocks.

## Part 2 — "at least as profitable as the most profitable players": the fair benchmark

`scripts/best_trader_benchmark.py` (run-plan step 3, lean): per-wallet MODELED copy-return at
OUR realizable entry, day-clustered, Bonferroni over eligible wallets; MM-union wallets excluded
from the gated number (structurally uncopyable) but shown in headlines.

- **B_LB overall = +3.4%** — the highest PROVABLE floor of any copyable wallet at our price —
  and it belongs to **0x99e42eb9…, already one of the router follow-set-4.** The system is
  configured to copy exactly the wallet whose edge is provable.
- **B_point (headline) = +25.6%** — the "most profitable player" number — is selection-inflated
  by construction; per-sport headline winners are mostly MM=True (book-makers we cannot tail).
- **Why-gap on the top raw wallets**: raw +26–31% → repriced at ours +20–26% (copyability tax
  ≈5–6.6pp) → provable floor +3.4% (the statistical noise haircut on thin day-counts is the
  BIGGEST term) → and part of the residual is survivorship (capture stops at deactivation).
- **Our arms vs the floor**: favorite mean +5.4% (LB −7.1%, 4 days) — statistically
  indistinguishable from B_LB. We are NOT provably behind the best copyable trader; nothing is
  provable either way at arm grain yet. The path to "at least as profitable": accrual to
  ≥20 forward day-blocks + the router already tailing the B_LB wallet + dense-capture keeping
  the tax measured. NOT: chasing the +25% headline (max-of-noise; mostly MMs).

Read-only, paper-only; nothing promotes. Follow-ups queued: survivorship capture fix
(poll dropped wallets), readiness-ledger rows for unified_book + beats_best_trader.
