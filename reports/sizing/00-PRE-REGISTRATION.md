# Live sizing deployment — PRE-REGISTRATION (frozen before any forward result)

**Goal.** Take the blended-median-optimal deployment policy derived in the stress work and run it
**live, forward, paper-only** to see whether the real signal stream actually delivers the modeled
returns without ruin. Belief-blind: the policy is frozen here, before we look at how it does
forward, and applied mechanically. Honest: forward-sealed; INDETERMINATE until enough independent
days accrue; realized is compared to a pre-computed model band, not to a moving target.

Paper-only, live DB **read-only**. Never writes the DB, never mutates `honest_paper_ledger`, never
places or simulates a real order, never touches migrations/daemon. All artifacts under
`reports/sizing/` + `scripts/sizing/` (each script `--selftest`, exits non-zero on failure).

---

## The policy under test (frozen)

**Sizing:** fixed **fraction of current bankroll per day** (`DEPLOY`), spread across the day's
favorite signals, with:
- per-market cap = `DEPLOY / n_bets_today` (equal-weight across the slate), capped at **2% of
  bankroll** per single market (no single market can dominate);
- per-day cap = `DEPLOY` (total across all correlated bets that day — the day is the correlated
  risk unit);
- the fraction is proportional (scale-invariant) — it deleverages on losses, compounds on wins.

**`DEPLOY` value:** the **blended-median-optimal** deployment output by
`scripts/sizing/optimal_deploy.py`, subject to the hard constraint **P(ruin, 20% of bankroll,
over 1 yr) ≤ 5% even if the edge is FAKE.** Reported per belief P(edge real); the deployed value
is the one that is optimal at P(edge real)=0.5 AND still ruin-safe at P=0.3 (robust choice).

**Strategy:** `favorite` only (the one certified-eligible independent edge). `elite_fresh_fav`
is nested (adds 0) — not a second book. No real money at any point.

---

## What "it works" means (success criteria, frozen)

Evaluated forward on the paper equity curve produced by `forward_deploy.py` on **signals fired
after the freeze timestamp** (forward-sealed):

1. **Reliability (realized within model):** the realized paper equity path stays within the MC
   model's central band (10th–90th pct) for its number of forward bets. A path that falls **below
   the 10th pct** is evidence the live edge is worse than modeled → flag.
2. **No ruin breach:** the paper bankroll never drops below 20% of its start. A breach = fail.
3. **Edge persistence:** the favorite realized-ROI lower bound (event-clustered, honest grain)
   stays **> 0** as independent day-blocks accrue toward the go-live gate (≥50 events, ≥5 regimes).
4. **Honesty gate:** verdict is **INDETERMINATE-BY-POWER** until ≥ 20 independent forward
   day-blocks / ≥ 5 regimes. No "it works" claim before then. Wide bands are a finding.

**Kill / downgrade:** realized median ROI/bet turns negative over ≥ 15 forward events with LB<0;
or a ruin breach; or realized path below the model 10th pct for ≥ 2 consecutive weeks.

---

## Freeze

- Freeze timestamp (UTC): recorded in `forward_deploy.py` as `FREEZE_TS` at first run; only signals
  resolved at/after it count toward the forward verdict. Pre-freeze bets are shown separately as
  an in-sample seed, clearly labelled, and never counted as forward evidence.
- Calibration anchors (live, read-only, 2026-07-03): favorite realized ROI/bet **+12.65%**,
  std **0.36**, avg entry **0.829**, win rate **93.7%**, N=63 over ~2 days. The optimal-deploy
  solver uses a CONSERVATIVE "real edge" (≈ +3.9%/bet, well below the optimistic +12.65% point) so
  the sizing is not over-fit to the lucky sample; the "fake edge" arm is −2%/bet (costs on a fair
  price). P(edge real) is swept, never assumed.

## Honesty rules
INDETERMINATE-BY-POWER is a valid verdict. Never manufacture a number the ~2-day record can't
support. Distinguish refuted / survived / unknown. The instrument accrues; today's output is the
mechanism + first (in-sample-seeded, forward-empty) reading, NOT a verdict.
