# VERDICT — "Bad Days" stress test: can this system lose, and is it worth the risk?

**NOT-YET (leaning NO-GO on the current sizing).** Do **not** commit real money now, at **any**
bankroll, under the currently-recommended `kelly_eighth_capped` policy. The consensus-favorite
edge is real in-sample and survives costs and multiplicity — but three pre-registered kill
triggers fire, and the binding one does **not** depend on any pessimistic modelling: at the
recommended ⅛-Kelly sizing, if the true edge is merely **half** of the measured +12.5% (entirely
inside the honest confidence interval), the strategy breaches its own 30%-drawdown ceiling in
**44%** of simulated years — with zero other stress. The system *can* lose, realistically, and in
a way a human cannot sit through.

**What would flip it to GO** (all three needed):
1. **Sizing fix (do first, cheap):** abandon ⅛-Kelly-on-the-frozen-band-5-fraction. Use
   flat-SHARES or de-rate to ≤1/16-Kelly with a hard band-5 fraction cap (≤2% of bankroll/bet).
   The current policy stakes ~7% of bankroll per band-5 bet on a market that is only ~5–8pp above
   break-even — over-levered by construction.
2. **Edge realness (the long pole):** forward paper until the edge LB clears 3% on **≥5 disjoint
   sport-regimes** that are **not** the two expiring tournaments (Wimbledon tennis + World-Cup
   soccer are ~70% of current profit and both end within weeks). This is **calendar-gated →
   months**, not volume-gated.
3. **Live CLV / adverse-selection monitor populated** (currently **zero rows** — we cannot measure
   our own fill quality; see F8).

---

## 1. The three numbers that drove the verdict

| # | number | meaning |
|---|---|---|
| 1 | **43.8%** | P(drawdown > 30%) in a CLEAN world (no cost/decay/upset) if the edge is HALF of measured, at ⅛-Kelly. 94.3% if the edge is at its +3% honest lower bound. Kill-criterion #2 (>10%) fires without any pessimism-stacking. |
| 2 | **−8.2%** | favorite's surplus lower bound at the honest grain (cluster-robust, small-sample t, df=3, G=4 day-blocks). The generalization CI is **not bounded above zero** — 4 days cannot rule out "no edge". |
| 3 | **65%** | share of operator "pull-the-plug" decisions that are FALSE ALARMS (edge was intact, pulled on variance). Combined with P(pull)=70%, the strategy is **unrunnable by a normal human** at current sizing. Kill-trigger #6 fires. |

## 2. Ranked failure table (plausibility × damage; pre-registered kill-criteria)

| rank | mode | mechanism | kill-criterion | verdict |
|---|---|---|---|---|
| **1** | **F1 thin-edge × over-sizing** | ⅛-Kelly bets f=0.57 on band-5 (marginal, ~break-even) and f=0.009 on band-4 (safe). Calibrated to the +12.5% point; over-levered if edge is smaller. | P(net<0)>35% **or** P(DD>30%)>10% at recommended sizing | **FAIL** — at ½ edge: DD>30% in 44%; at +3% LB: 42% net-neg, 94% DD>30%. |
| **2** | **Tiny-N / no adverse regime (Phase 0/3)** | 4 day-blocks (G=4); record has **no losing slate**; edge LB spans +7.6% … −8.2% by grain. | edge LB ≤ 0 at the honest grain | **FAIL** (LB −8.2% at df=3). Real edge, unproven generalization. |
| **3** | **F6/F5 correlated bad days + slow overlay** | per-slate stop-loss does NOT bound cross-regime drawdown (median maxDD 71% despite the −10% slate stop); adaptive overlay needs ≥20 events / ~14 days per cell to DODGE — too slow for an upset burst, and useless when ALL cells erode. | upset cluster breaches DD>30% in >10% | **FAIL** (composite P(DD>30%)=92%). |
| **4** | **Composite compounding (Phase 2)** | no single failure sinks it; a bad year stacks partial decay + cost + upset + adverse-selection + cohort-regression at once. | P(net<0 @12mo)>35% | **FAIL** (85% net-neg) — but this is an **adversarial upper bound** (assumes independent simultaneous erosion), not a forecast. See §4. |
| 5 | **F2 edge-decay detection latency** | gate pulls on trailing ROI < 2%; latency bleeds capital. | dollars bled > earned pre-decay (net≤0 at pull) | **PASS at +9% edge** (net +$2.5k–17k, P(net≤0)<3%); **MARGINAL at +3% edge** (P(net≤0 at pull) 27–34%). Latency isn't the problem; thin edge is. |
| 6 | **F7 cohort regression** | leaderboard top-N partly lucky, regress. | edge doesn't persist out-of-cohort (split-half LB≤0) | **INDETERMINATE-BY-POWER** — 4 days / 1 cohort snapshot cannot test turnover; modelled parametrically (cohort ∈[0.4,1.0]) in the composite. |
| 7 | **F4 costs worse than modeled** | thin favorite book, adverse fill, dispute. | favorite LB ≤0 under 2× haircut + 2¢ fill | **PASS** — LB +4.12% (still >3% margin). Edge only dies at 5× haircut + 3¢ + 2× fee (LB −0.9%). BUT band-5 reverting to price + these costs → −5.8% (the F4×F7 interaction, folded into the composite). |
| 8 | **F3 multiplicity / null survivor** | ~15 arms searched; keep the best. | FWER-adjusted favorite p > 0.05 | **PASS** — favorite null p=0.0000 survives ×13 Bonferroni. **Caveats:** pipeline FWER 7.5% (a null search certifies someone 1-in-13), and it just certified `strict_retuned` on **N=14** — do NOT treat that or the nested `elite_fresh_fav` as extra winners. |
| 9 | **F8 operational / adverse selection** | capture-LEAD misses → fire late at drifted line; captured fills are the leftover worse ones; daemon wedge precedent. | realized edge after capture failure < 3% margin | **INDETERMINATE-BY-POWER** — `signal_price_trajectory` is **empty (0 rows)**; per-minute decay uncomputable on real data; modelled parametrically. **Operational finding: the system cannot currently measure its own fill quality.** |

**Pre-registered triggers that FIRED: #1 (P net<0 >35%), #2 (P DD>30% >10%), #6 (operator pull is a false alarm in a majority).** Three of six. Triggers #3 (F4 LB≤0), #4 (F2 latency), #5 (F3 multiplicity) did **not** fire.

## 3. Drawdown / ruin & detection-latency tables

**Composite (10k worlds, 12 mo, `kelly_eighth_capped`, scale-invariant → fractions identical at
all bankrolls):** median P&L −$3,245 @ $5k · **P(net<0)=85%** · **P(DD>30%)=92%** · **P(ruin@20%)=39%**
· median longest-underwater **49 of 52 weeks**. Flat-shares @ $5k: −$1,682, P(net<0)=75% (better
tail — ruin 8% vs 39% — but still a losing majority under the full stack).

**F1 clean-world (edge scaled, NO other stress), ⅛-Kelly @ $5k:**

| true edge | median P&L | P(net<0) | **P(DD>30%)** | P(ruin) |
|---|---:|---:|---:|---:|
| +12.5% (measured point) | +$558k | 0.0% | **0.0%** | 0.0% |
| +6% (½ — inside the CI) | +$21k | 0.4% | **43.8%** | 0.0% |
| +3% (honest LB) | +$0.7k | 41.6% | **94.3%** | 1.2% |

**F2 detection-latency (dollars bled before the gate pulls a decaying arm):** at a true +9% edge,
net at pull is +$2.5k–17k across all half-life × fire-rate cells (P(net≤0)<3%) — **latency is not
the problem.** At a true +3% edge, median net at pull is small-positive but **27–34% of paths end
net-negative.** Context: a *stable* +9% edge trips the naive continuous monitor 37% of the time —
the false-alarm problem quantified.

**Factor decomposition (each factor ALONE at a typical level → P(net<0)):** clean 0% · cost(2×+1¢)
0% · cohort 0.7 → 0% · adv-sel 0.75 → 0% · decay 6mo → 0% · upset → 0% · miss 0.2 → 0% · drought
0% · **ALL together → 96.6%.** No single failure is lethal; the stack is.

## 4. Adversarial self-review (Phase 4)

Red-teamed with the stance "this test went easy on the system":
- **Where I went EASY (makes the true picture WORSE, reinforcing NOT-YET):** (a) the composite
  *seeds base win-rates at the observed lucky values* (band-5 97.8% — itself 4-day luck); if the
  true rate is lower, every result understates risk. (b) No cost-upset *correlation* (costs spike
  exactly when markets are stressed). (c) Dispute risk omitted from the composite.
- **Where the composite is HARSH (the honest caveat on the 85%):** it draws 6 erosion factors
  independently, each with mean <1, so the *typical* world assumes the edge is ~40% of measured.
  That is why the composite's 85% is presented as an **adversarial upper bound, not a forecast** —
  and why the verdict rests on the **stack-independent** results (F1 half-edge DD, the −8.2% LB,
  the human-factor matrix), not on the 85%.
- **A cap that only works because the record never stressed it:** confirmed — the per-slate
  −10% stop-loss does NOT bound cumulative drawdown across a losing regime (median maxDD 71%). The
  entry-12 claim "drawdown bounded by construction" holds only *within a single slate*.
- **The risk engine's own blind spot:** `risk_engine.json` reports `ceiling_slack=True` and
  P(profit)=100% even at λ=0.25 — because its block bootstrap resamples a record with no losing
  slate. This stress test fills exactly that hole and shows the drawdown the bootstrap cannot see.

The verdict survived the skeptic — but one correction points the *other* way, and it is the key
to reading this honestly (see §4b).

## 4b. The outcome is BIMODAL and currently UNKNOWABLE (friendly-world sensitivity)

The one fair objection to the composite's 85% is H1: it draws six erosion factors independently,
so the *typical* world assumes the edge is ~40% of measured. To test whether the failure is
**structural** or just an **adverse-assumption artifact**, I re-ran the *same calibrated simulator*
under a deliberately **friendly** world distribution (mild costs, high cohort/adverse-selection
persistence 0.85–1.0, rare shallow upsets, edge at the point estimate), flat-shares
(`scripts/stress/friendly_sensitivity.py`, `--selftest` green):

| world | P(net<0 @12mo) | P(DD>30%) | P(ruin) | p5 P&L @$5k |
|---|---:|---:|---:|---:|
| **FRIENDLY** (point edge, mild ops) | **0.4%** | 0.1% (@$5k) | 0.0% | **+$1,247** |
| **ADVERSE composite** (⅛-Kelly) | 85.1% | 91.5% | 38.8% | −$4,988 |
| **POSTERIOR** edge~CI, flat-shares @$5k | 70.4% | 63.8% | 36.3% | −$10,568 |

In the friendly world the strategy is comfortably profitable — **even its 5th percentile is
positive.** So the composite's ruin is **not** purely structural: it is driven substantially by the
adverse-world assumptions (cohort regression + adverse selection + decay + upset clustering). **But
4 days of data cannot distinguish the friendly world from the adverse one** — cohort persistence,
adverse-selection rate, and decay half-life are all *unmeasured free parameters*, and the outcome
pivots on them (friendly → +$3.9k median; adverse → 39% ruin). That is the precise reason the
verdict is **NOT-YET (resolve the uncertainty), not NO-GO (edge fake):** committing capital now is
betting, with no evidence, that we live in the friendly world — and the loss if we don't is ruin.
Forward paper to the §5.3 gate is what actually collapses the bimodality into a knowable answer.
*(Independent cross-check: this session re-ran the 10k composite from scratch — 85.1% / 91.5% /
38.8% reproduced to the digit.)*

## 5. Guardrail spec (concrete, implementable — required before any real-money pilot)

1. **Sizing:** replace `kelly_eighth_capped` with **flat-SHARES** (or ≤1/16-Kelly) and a **hard
   per-bet cap of 2% of bankroll**, plus a **hard band-5 exposure cap** (≤40% of deployed capital
   in band ≥0.80). Rationale: the DD ceiling is breached at ½-edge *only because* band-5 is sized
   at 7%/bet.
2. **Max exposure:** ≤3 units/slate, ≤40%/regime (keep), **and a bankroll-relative daily stop at
   −8% of equity** (the current −5-unit absolute stop becomes negligible as the bankroll grows).
3. **Per-regime min-N before real money:** ≥50 events **and** LB>3% in each of **≥5 disjoint
   regimes that exclude the two expiring tournaments.**
4. **Automatic decay-pull trigger:** non-overlapping 50-event review blocks, two-strikes rule
   (pull after 2 consecutive blocks with mean ROI < 2%). Do NOT use a tick-by-tick rule (37%
   false-alarm).
5. **Cost-drift monitor:** alarm if realized (haircut+fill) exceeds 1.5× the modeled 0.5¢/2%.
6. **Live CLV / adverse-selection monitor:** **populate `signal_price_trajectory`** (currently
   empty) and alarm if median realized entry is worse than the at-fire mid by >1¢, or if captured
   fires' forward CLV is negative — you currently cannot see adverse selection at all.

## 6. The honest "worth it?" paragraph

**Is the edge diverse enough?** No — it is **one bet wearing two names** (`elite_fresh_fav` is 100%
nested in `favorite`), ~70% concentrated in two tournaments that expire within weeks, with 2 of its
4 "regimes" being N<10 perfect-record luck. There is **no orthogonal second edge** today (0/12 by
the orthogonality gate). **Reliable enough to survive a normal bad year?** Not at the current
sizing: no single failure sinks it, but a realistic bad year stacks several partial failures, and
the ⅛-Kelly band-5 concentration turns a plausible edge-overestimate into a 44–94% chance of a
>30% drawdown. **Is the net return worth the tail risk and the learning cost?** The *upside* is
real and large if the +12.5% edge is genuine (clean-world median +$558k/yr @ $5k) — but that
upside is exactly what 4 days cannot confirm, and the *downside* (39% ruin under the composite, a
strategy a human pulls 70% of the time and is wrong 65% of those times) is disqualifying **now**.
The juice may well be worth the squeeze — but only after (a) the sizing is de-levered, and (b) the
edge earns ≥5 non-expiring regimes of forward proof. Until then the honest expected cost of finding
out is **months of calendar time** (regime-gated) and a paper-loss variance that, at the current
sizing, would look like failure most of the way even if the edge is real.

---
*Artifacts: `reports/stress/{00-baseline,01-pre-registration,04-adversarial-self-review,VERDICT}.md`
+ `{cost_stress,multiplicity,decay_latency,bad_life_mc,scenarios,phase3_posterior,
friendly_sensitivity}.json`. Scripts: `scripts/stress/*.py` (each `--selftest` green). Paper-only,
read-only, zero migrations, no live-behavior or ledger change.*
