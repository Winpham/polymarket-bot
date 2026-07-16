# weather_fav — ADVERSARIAL VERIFICATION of the "accrue-forward / leaning-positive" finding

**Branch `feat/weather-verify` (worktree `wt/weather-verify`, off the `feat/weather-cert` commit
`5802516`). Read-mostly. No order placed, no API key, `main`/`feat/weather-cert`/`wt/evergreen-cert`
untouched. Scripts' `--selftest` green. Run 2026-07-15. Stance: SKEPTIC — default to artifact unless
evidence is strong.**

---

## ONE-LINE VERDICT

**SURVIVES-AS-INDETERMINATE on disposition (k=0, do-not-size, do-not-kill) — but the report's central
*interpretive* claim is REFUTED.** The +15% is a real-within-July favourite-longshot **band** premium
(fee-robust, day-drop-robust), so it is not a kill. But "the sharp SELECTION carries genuine forward
information / the market confirms it / this corrects the evergreen-cert null" does **not** survive a
proper paired test: at the fair 24h horizon on the primary band the sharp selection is *worse* than the
blind band. The finding is the **band's** λ≈0 variance premium — exactly what `1c140f1` said — and it
**cannot be certified now**: the decisive disjoint-time test is *structurally impossible* (zero
pre-July convergence signal). **Must accrue; cannot test now.**

---

## PER-ATTACK SCORECARD

| # | attack | result | verdict |
|---|--------|--------|---------|
| 1 | **Disjoint-time (decisive)** | Selection signal cannot exist before July: June had **154** weather markets with ≥1 rank≤250 backer but **0 with ≥2 backers** → **0 convergence picks** pre-July (removing `GO_LIVE` entirely still yields 1412 picks, *all* ts0 in July). Resolution labels also dense only in July. Out-of-regime test impossible. | **INDETERMINATE (impossible)** — cannot refute, cannot confirm; forces accrue-only |
| 2 | **Independent λ/CLV recompute** | Reproduced the harness exactly. Fair-horizon (24h) λ CI LB **negative** (atfire λ [−0.089, +0.897]; tape λ [−0.222, +0.73]); CLV CI straddles 0 (p(CLV≤0) 0.08–0.18); coverage 90%; day-clustering correct. The report's own numbers are honest and the crux **does not pass**. | **SURVIVES (as reported = fails crux)** |
| 3 | **Leakage hunt** | No survivorship (testable 648 win-rate **95.5%** ≈ all-resolved 1183 **95.9%**); closes strictly after `ts0`; decision→resolution gap median **52.6h** (p05 27.9h) so 24h closes are genuinely forward (winners' 24h close 0.899 vs entry 0.826, only 32% degenerate); entry basis apples-to-apples. | **SURVIVES (no leak found)** |
| 4 | **Adjudication / MIRAGE** | The "sharp beats blind band" overturn fails a **paired day-clustered difference** test: primary band 0.71–0.90 @24h DIFF **−2.5¢** (sharp *worse*), p(diff≤0)=**0.78**; @12h +3.3¢ but p=0.28; only wide band @24h is significant (+1.5¢, 5 days). The report compared two point estimates whose CIs both straddle 0 and overlap heavily, never testing the difference. Evergreen-cert's "band does the work, sharp ~decorative" is the better-supported reading. | **REFUTED (the interpretive overturn)** |
| 5 | **Fragility** | Bar-1 ROI robust: drop-best(07-03)→+14.0% [+5.1,+19.9]; drop-worst(07-04)→+18.8% [+16.2,+21.0]; drop-both→+18.2%. Fee-insensitive: 0.05→+14.86% vs 0.03→+15.19% (fee ~0.7¢ on 83¢ favourites). BUT **48% of picks (113/236) fall on one day (07-06)**; all 9 days are consecutive July; effective N ≈ **9 day-clusters**. | **SURVIVES within-July / regime-fragility unquantifiable** |

---

## THE DECISIVE FACT (attack 1, in full)

The positive result is 9 consecutive days (2026-07-03…07-14), one regime. The brief's decisive test —
run the frozen gate on *earlier* held-out weeks — is **structurally impossible**:

```
convergence picks (≥3 rank≤250 one-sided backers, band 0.71–0.98), by ts0 month, GO_LIVE removed:
  2026-06 : 154 markets with ≥1 backer → 0 with ≥2 backers → 0 picks
  2026-07 : 8427 with ≥1 → 5809 with ≥2 → 4084 with ≥3 → 1412 in band
```

The rank≤250 backer population simply did not trade weather markets densely enough to form a ≥3-backer
convergence until July (`trader_fills` weather volume: May 506 → June 7,338 → July 264,522 fills).
Resolution labels (`outcome_won`) are likewise dense only in July (May 9 / June 108 / July 5,987 resolved
conds). **There is no earlier data on which to falsify the July result.** Per the brief this is the
explicit "selection cannot be computed before July" branch → the finding is INDETERMINATE and accrue-only,
**not** refuted-by-regime — but it also **can never be certified from history**; only forward accrual can
move it.

## WHY THE INTERPRETIVE OVERTURN IS OVERSOLD (attack 4, in full)

The report's load-bearing claim (WEATHER-FAV-CERT.md:66–71) is that the sharp selection carries **+6.0¢**
forward CLV vs the blind band's **+1.7¢**, therefore "the sharp is not decorative — it is the entire
information channel," overturning `1c140f1`. But:

- Both pools' CLV CIs **straddle 0 at every horizon** (sharp p(CLV≤0) ≈ 0.05–0.09; blind ≈ 0.28–0.53) —
  neither is individually significant.
- The report never tests the **difference**. When tested paired (same days, same tape entry/close):
  - primary band 0.71–0.90 @ **24h (the harness's own fair headline horizon)**: sharp−blind = **−2.5¢**,
    p(diff≤0) = **0.78** — the sharp selection is, if anything, *worse* than the band;
  - @12h: +3.3¢ but p = 0.28 (not significant);
  - only the *wide* band @24h clears (+1.5¢, p=0.013) — on 5 shared days.
- The "+6¢" headline uses 12h, a shorter (more hindsight-contaminated) lead than the 24h the four bars
  headline; at 24h the sharp CLV is only +2.1¢ (tape) / +3.6¢ (atfire), CI straddling 0.

So the proper apples-to-apples test does **not** support "sharp beats band." The positive ROI is the
favourite-longshot **band** premium — which `1c140f1` already characterised as variance/λ≈0 — and the
sharp selection adds nothing statistically demonstrable on top. Both certs in fact agree on the *action*
(k=0, don't size); the weather-cert's *narrative* correction ("information-bearing, accrue because the
sharp works") is not earned by the data.

## RECONCILING THE TWO CERTS

Neither session made a computational error; the numbers reconcile. `1c140f1` measured λ≈0 on 2 stalled
days at a late entry (underpowered). `feat/weather-cert` measured a positive-*point* λ on 9 July days at
convergence entry (still CI-straddles-0). The disagreement is purely interpretive. Adjudicated: the
**band** carries the (unfalsified, within-July, variance-dominated) premium; the **sharp selection** does
not demonstrably beat it. That is closer to `1c140f1`'s reading than to weather-cert's. The one thing
weather-cert is right about: `1c140f1`'s "confirmed *permanent* null" was over-stated on a 2-day window —
the honest status is INDETERMINATE-by-power, not a proven null. Symmetrically, weather-cert's
"leaning-positive / information" is over-stated.

## CAN WE TEST NOW, OR MUST WE ACCRUE?

**Must accrue — and even accrual cannot rescue the *sharp* thesis specifically.** The disjoint-time
falsification is impossible (no pre-July convergence). Forward accrual of disjoint weeks is the only path
to move the λ CI LB. But since the sharp selection is not demonstrably better than the blind favourite
band, the practical question collapses to the blind-band question `1c140f1` already answered (λ≈0). **Do
not build sharp-selection execution infra on this evidence; do not size (k=0).** If anything accrues, it
should be logged as a *band*-level favourite-longshot observation, not as a validated sharp signal.

---

## Artifacts (all on `feat/weather-verify`, read-only)
- `reports/repro_4bar.json` — exact reproduction of the 4-bar harness (numbers match WEATHER-FAV-CERT.md).
- This report. All DB reads SELECT-only; no incumbent touched; cost-zero.
