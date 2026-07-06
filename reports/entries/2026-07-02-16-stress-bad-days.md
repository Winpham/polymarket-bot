# Stress test — "Bad Days": can this system lose, and is it worth real capital? (2026-07-02, entry 16)

Hostile-risk-officer run (`STRESS-TEST-BAD-DAYS-PROMPT.md`). Paper-only, live DB read-only,
ledger + migrations untouched; all artifacts under `reports/stress/` + `scripts/stress/` (each
script `--selftest` green). Mission: not "confirm it works" — find the **realistic path to
ruin** before money does, or prove there isn't one after genuinely trying.

## Bottom line — **NOT-YET** (do not commit capital now; ≥$25k bankroll if/when GO)

The favorite edge is **not refuted** (survives cost, multiplicity, decay tests; thrives in a
friendly world) but the honest generalization LB is **unbounded below on G≈4 independent
day-blocks (−8.2%, df=3)**, and the 12-month outcome is **bimodal & currently unknowable**:

| world | P(net<0 @12mo) | P(DD>30%) | P(ruin@20%) | p5 P&L @$5k |
|---|---:|---:|---:|---:|
| FRIENDLY (mild-everything, point edge) | **0.4%** | 0.1% | 0.0% | **+$1,247** |
| ADVERSE composite (⅛-Kelly, 10k worlds) | **85.1%** | **91.5%** | **38.8%** | −$4,988 |
| POSTERIOR edge~CI (flat-shares) | 70.4% | 63.8% | 36.3% | −$10,568 |

4 days cannot tell us which world is real (cohort persistence, adverse-selection, decay are
unmeasured free parameters). Spending money now = betting, with no evidence, that we live in the
friendly world; the loss if we don't is ruin. → **NOT-YET, not NO-GO.**

## What this session did
- **Reproduced** the 10k-world composite from scratch: 85.1% / 91.5% / 38.8% matched the prior
  VERDICT to the digit (independent verification).
- Built **`phase3_posterior.py`** (flat-shares under the honest fat-tailed edge posterior;
  P(true edge≤0)=12.8%, q05=−7.9% ≈ Phase-0 −8.2%) and **`friendly_sensitivity.py`** (the H1
  fairness check — mild versions of all factors at once). The friendly result **quantified the
  bimodality** and sharpened the verdict from "leaning NO-GO" to a clean **NOT-YET (resolve the
  uncertainty)**.

## Pre-registered triggers that FIRED: #1 (P net<0>35%), #2 (P DD>30%>10%), #6 (false-alarm
majority — softened to *fixable*, the 4-red-week stop is naive). #3/#4/#5 did NOT fire.

## Ranked binding failures
1. **F7/F1/F5 together** (binding): small-or-regressing edge + correlated upset variance, sized by
   a policy calibrated on lucky bands, grinds the bankroll down before human/gate reacts.
2. **Sizing is the amplifier:** band 5 (51% of bets, 97.9% winrate on ~50 events = likely luck) →
   ⅛-Kelly still stakes **7.5%/bet**. Flat-shares on <$25k ruins too (64% ruin @$1k).
3. **F4 PASS** (LB +4.1% at 2×hc+2¢; band-5-revert −5.8% caveat). **F3 PASS** (favorite null
   p=0, ×13 Bonferroni; but synthetic-null certifies *someone* 7.5%/search → don't count the
   nested elite as a 2nd win). **F2 PASS-with-tail** (median net@pull>0, but 28–34% of decay
   paths net-neg at the honest +3% edge). **F6 PARTIAL** (overlay reflexes work but detect in
   hundreds of events — slow vs the grind).

## Flip-to-GO (all needed)
(1) de-lever sizing: flat-shares + hard 1.5–2%/bet cap + band-5 exposure cap; (2) forward paper to
**N≥50/arm AND ≥5 established regimes excluding the two expiring tournaments** — calendar-gated,
**~2–6 months**; (3) populate the live CLV / adverse-selection monitor (`signal_price_trajectory`
currently empty — the system cannot see its own fill quality).

Full memo: `reports/stress/VERDICT.md` (§4b = bimodal finding). Self-review:
`reports/stress/04-adversarial-self-review.md`.
