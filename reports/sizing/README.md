# Live sizing deployment — instrument + first reading

Paper-only, live DB **read-only**. Never writes the DB/ledger, never places an order, no migration
or daemon change. Turns the stress-work sizing analysis into a **forward-verified** paper
instrument. Pre-registration (frozen policy + success criteria): `00-PRE-REGISTRATION.md`.

## The answer to "what deployment?" — blended-median-optimal, ruin-constrained

`scripts/sizing/optimal_deploy.py` (`--selftest` green). Maximises blended median bankroll growth
subject to **P(ruin) ≤ 5% even if the edge is fake**, swept over the belief P(edge real):

| P(edge real) | optimal deploy/day | blended median/yr |
|---|---:|---:|
| 0.3 | 3% | −10% |
| 0.4 | 3% | −8% |
| **0.5** | **13%** | **+64%** |
| 0.6 | 16% | +221% |
| 0.7 | 16% | +271% |

- **Hard ceiling: 16%/day** — beyond it, ruin-if-fake exceeds 5% (20%→20% ruin, 40%→86%).
- **Recommended: 13%/day** — optimal at 50/50 belief, ruin-safe at every belief.
- Belief-sensitive: if you lean the edge is probably fake (P≤0.4), it collapses to 3%. The "real"
  edge used is a **conservative +3.9%/bet** (not the optimistic +12.6% live point), so the sizing
  is not over-fit to the lucky 2-day sample.

## The live forward test — does the real stream deliver the model?

`scripts/sizing/forward_deploy.py` (`--selftest` green) applies the 13%/day policy to the REAL
favorite outcomes in `honest_paper_ledger` (read-only), on a virtual bankroll, and checks
realized-vs-modeled. **Forward-sealed:** freeze `2026-07-03 18:49 UTC`; only bets resolved after it
count as forward evidence. Re-run to accrue (`bash scripts/sizing/accrue.sh` logs one line to
`accrual_log.txt`).

**First reading (2026-07-03):**
- Forward: **0 bets** (freeze just set) → **VERDICT: INDETERMINATE-BY-POWER, 0/20 forward
  day-blocks.** Honest: the test starts now.
- In-sample seed (illustrative, NOT evidence): 63 bets / 3 days, +3.9% growth at 13%/day, maxDD
  0.3%, no ruin. Realized edge **+9.8%/bet but day-clustered LB −10.2%** on 3 day-blocks — the same
  wall as everywhere: the point edge looks great, the generalization LB is still below zero on too
  few independent days.
- Model band (good-edge, 3 days): p10 −3% / p50 +1% / p90 +5% — the seed's +3.9% sits inside it.

## What "it works" will mean (from the pre-registration)

Forward, on post-freeze bets: (1) realized equity stays within the model 10–90 band; (2) no ruin
breach; (3) favorite realized-ROI LB climbs **> 0** as independent day-blocks accrue; (4) verdict
stays **INDETERMINATE** until ≥ 20 forward day-blocks / ≥ 5 regimes. Kill/downgrade on realized LB<0
over ≥15 forward events, a ruin breach, or realized below model-p10 for ≥2 weeks.

## To accrue it forward
Re-run `bash scripts/sizing/accrue.sh` (or `python3 scripts/sizing/forward_deploy.py`) periodically
— it recomputes from the frozen ts and reads only newly-resolved bets. A ready-to-install launchd
agent was intentionally **not** installed (persistence you didn't ask for); enable one yourself if
you want unattended 6-hourly accrual.

## Files
- `scripts/sizing/optimal_deploy.py` · `forward_deploy.py` · `accrue.sh` (each `--selftest` green)
- `reports/sizing/{00-PRE-REGISTRATION, README}.md` · `{optimal_deploy, forward_deploy}.json` ·
  `accrual_log.txt` · `freeze_ts.txt`
- Reuses stress machinery: `scripts/stress/{portfolio_corr, cost_of_caution, bad_life_mc}.py`
