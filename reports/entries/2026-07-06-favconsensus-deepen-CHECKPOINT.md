# CHECKPOINT — favconsensus-deepen run (mid-run, 2026-07-06 ~00:40Z)

Salvage point in case the session is reaped. Prereg: `PREREG_20260706T000604Z_favconsensus_deepen.md`
(frozen BEFORE outcomes). Branch `research/favconsensus-deepen`. All numbers super-event clustered.

## Done

**§0 Inventory (deltas vs seed):** 7 full days (was ~2.4); favorite 325 graded / 101 super-events
(was 220 pos / 78 games); soccer share of favorite super-events **22%** (was ~89%) — tennis 55
(Wimbledon, expiring), soccer 23, mlb 14, esports 5, nba/cbb 4; universe 560 followed / 284 active /
506 with fills (was "handful"); dense capture **accruing** (3,345 rows / 186 signals since 07-03,
was 0); historical mine 2.6M fills / 517 fill-days.

**H1 core re-verify (reports/favconsensus_reverify.json):**
- H1.1 pooled favorite surplus-over-blind **+8.39%**, ev-clustered LB(Bonf k=4) **+1.96%**, n=101 ev;
  day-clustered LB +1.42% (7 days). Selection-null **p=0.0005** (seed was p=0.034 — gate 6 now CLEARS);
  block-B-only (post-seed window) null p=0.0095. Battery: mirror symmetric, placebo flat, early
  +6.68%/late +10.49%, odd +5.93%/even +11.34% (adversarial_battery on 101 ev). Follower tax ~0.7¢.
  **Only failing gate = LB < +3% margin → INDETERMINATE-BY-POWER, ~143 ev closes it at current surplus.**
- H1.2 sweet spot: band4 +9.32% ≥ band5 +7.28% — ordering HOLDS (band4 LB −0.2%, band5 LB +2.7%).
- H1.3 longshot block WEAKENED: consensus-longshot arm raw edge **+2.3%**, surplus +4.7% (LB −2.7%,
  93 ev) — "longshots lose hard" does NOT reproduce as a point estimate; skip-<45¢ rule now rests on
  the negative LB + flat-shares $ (−$428 after costs), i.e. INDETERMINATE, not refuted-lose.
- H1.4 sizing: strict flat-$ **−$4,575** vs flat-shares **+$2,654** — seed sign flip REPRODUCES on the
  longshot-bearing stream. favorite-only: both positive (+$2,280/+$1,751 after 1¢+2% costs).

**H2 regime cells (reports/regime_cell_scoreboard.json):** no cell certifies (floor 30). Closest:
- `soccer|band4|B` +17.0%, LB +5.7%, p=0.0065 — only the floor fails (14/30 ev).
- `tennis|band5|A` +12.9%, LB +10.3%, p=0.0005 (16 ev) — expiring (Wimbledon), cannot certify by rule.
- mlb cells 4-6 ev each, +11..+31% point estimates; pooled mlb (H1 by_category) **+22.4%, LB +16.3%,
  14 ev** — the prime recurring-regime accrual target (~16 more MLB events needed).
- **Abstention: NO LIFT.** full LB 2.80% vs abstained 2.74%; positive days 7/7 both. Supply, not skipping.

**H4 relational (reports/relational_lift.json): KILLED at the frozen params** (m=20, β=1, K=5,
primary top-50%). odd→even +0.53pp lift, even→odd −0.10pp → fails "both halves" rule. Not
data-starved anymore (2.1-2.6k pairs, 95-98% coverage) — just no consistent ordering lift.

## In flight
- Agent `routing-h3` (H3 enrichments: regime-conditional scorecard / $1k conviction / survivorship) →
  scripts/routing_enrich.py + reports/routing_enrich.json.
- Agent `copytax-h5` (dense-capture tax by band×sport; tax-adjusted realizable LBs) →
  scripts/copy_tax.py + reports/copy_tax.json.
- Then: adversarial verify pass on every positive (fresh-code re-derivation of H1.1 pooled, mlb
  pooled cell, soccer|band4|B), REFINED-STRATEGY.md update, final report, memory note.
