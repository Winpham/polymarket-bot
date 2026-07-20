# RETRACTION — the final-hour favourite arm

**2026-07-20. The +6.29¢ final-hour favourite edge is RETRACTED. It was an artifact of
maturity-anchoring. The arm is closed and the hypothesis family with it.**

Supersedes `PREREG_20260719_final_hour_favourite_v3.md` (and v2, v1). Zero signals ever accrued;
`finalhour_paper_signals` is empty. No money was ever at risk. k=0 throughout.

---

## 1. The finding

The effect was never in the market. It is produced by the estimator.

A **zero-edge martingale** — a price process whose true edge is exactly zero by construction —
returns the same effect through the same estimator. Two independent implementations agree:

| | maturity-anchored (conditions on a retrospectively-known endpoint) | endpoint-free anchor, SAME paths |
|---|---|---|
| −30 | **+12.00¢** [LB95 +11.96¢] | −0.07¢ [LB −0.48¢] |
| −45 | **+17.49¢** [LB95 +17.41¢] | −0.26¢ [LB −0.66¢] |
| −60 | **+17.02¢** [LB95 +16.83¢] | −0.08¢ [LB −0.49¢] |

*(independent re-implementation, 60,000 paths, k=0.0878/step calibrated from the tape; the
workflow's own run returned +6.41¢ [LB +6.31¢] at −30 with endpoint-free controls at −0.01¢/+0.24¢
/−0.88¢. The two differ in path parameterisation and agree in conclusion.)*

**The original +6.29¢ is smaller than what pure endpoint conditioning manufactures from nothing.**

The endpoint-free column is the control that matters: on the *same simulated paths* it correctly
returns zero, so the simulation is not biased everywhere — only when the sample is chosen by its
endpoint.

**Why it happens.** Anchoring "30 minutes before resolution" selects for contracts that were *about
to resolve*. Among those sitting at 0.85 in that window, the ones travelling to 1 arrive quickly;
the ones travelling to 0 have four times as far to go and mostly fall outside the window. The sample
is enriched with winners **by the act of defining it**. No market behaviour is required.

**On real data the endpoint-free controls agree with the simulation:** time-uniform anchor
**−1.34¢ [LB −2.11¢]**; hourly wall-clock marks clustered one-per-market **−3.04¢ [LB −5.85¢]**.

## 2. The independent, sufficient second kill

Even had the anchor been sound, the arm cannot reach the tape. Live capture, 2026-07-19/20:

- 999 polls, 18 competitions, 69 near-decided observations, **0 fires**, empty ledger.
- **0 of 13** near-decided opportunities in band across BOTH orientations; **minimum ask 0.940**.
- The book re-rates **+10–13¢ before** the trigger fires — a larger move than the edge sought.
- The gradient: price rises monotonically with decidedness (0.880 → 0.940 → 0.950 → 0.970;
  52% → 45% → 16% → **0%** in band). **No state is both clearly-winning and cheap.**

This is not a fail-closed artifact: the recorder was verifiably alive (launchd exit 0, `us_mid_tape`
current to 2026-07-20 07:59Z, median quote age 1.70s).

**Not decisive, and stood down:** `finalhour_leadlag.py`. Every surviving line of evidence is
independent of it. If the book LAGS the feed the arm is still dead by fire starvation — a faster
feed reaches 0.97 sooner, it does not create a band crossing. If the book LEADS, it is dead
trivially.

## 3. Retract condition R7 (adopted, and tripped)

PREREG v3's R1–R6 all presuppose accrued signals; the futility stop needs ≥150 events. None can fire
when the trigger never fires. That was a real gap.

> **R7 — FIRE STARVATION.** Retract when the one-sided 95% Clopper-Pearson upper bound on
> P(fire | near-decided match) implies >180 days to reach N=250 at the measured flow.
> Threshold 0.126; trips at F=0, M=23.

Current state F=0, M=11 (bound 0.238 ⇒ ≥95 days minimum; the mechanistic funnel estimate is ~1,000
days). **R7 is not yet formally tripped on count** — but §1 closes the arm on grounds that do not
depend on fire rate at all, so the retraction does not wait for it.

## 4. What was discarded, and why

| approach | verdict |
|---|---|
| Re-examine the edge | **SURVIVES as a finding** — the retrospective is manufactured by endpoint conditioning |
| The disciplined null | **SURVIVES as the conclusion** — fire starvation stands alone |
| Short-side capture | not a second book: 1−best_bid is already in `us_mid_tape`; doubles N, 0-in-band unchanged |
| Alt formulations (overreaction / stale quote / asymmetry) | book is calibrated at the real ask across all bands; the one positive cell dissolved under a price-matched control, and the "stale quote" signal tracked **recorder outages**, not venue behaviour |
| Time-to-completion trigger | 20–27 min estimator error against a ~15-min λ window; states precise enough to time already price ≥0.94 |
| Earlier trigger | in-band states sit ~52 min from the end, inside the measured λ LB=0.00 region; the in-band sample fails to reject the market's own ask (P=0.233) |
| Richer/point-level feed | ATP point data exclusively Sportradar under ITIA undertakings; WTA (96.7% of this tape) exclusively Stats Perform to licensed books; resellers publish no terms ⇒ **ToS-INDETERMINATE = hold** by the bo3.gg precedent. Moot: the executable leader ask never enters the band |

## 5. What would overturn this

An **in-band executable leader ask at a genuinely near-decided state**: a `finalhour_feed_tape` row
with set-lead ≥1, game-lead ≥3, leader-side ask (real `best_ask`, or 1−`best_bid`) in [0.65,0.92],
`quote_age_s` < 15s, `best_ask_qty` ≥ 61 shares. Observed **zero in 13 opportunities**, minimum
0.940; the rule of three caps the in-band rate at 0.231, so ~10 such observations would falsify
"the intersection is empty" outright.

Or: re-running the maturity-anchored estimator with the anchor at a **live-knowable** timestamp
(`gameStartTime + 90min`) returning LB95 > +1.43¢. The endpoint-free controls (−1.34¢, −3.04¢)
indicate it will not.

## 6. Two instruments worth keeping (neither is an arm)

1. **A standing anchor-placebo gate.** Any retrospective whose sample is located relative to a
   retrospectively-known endpoint must first pass (a) an endpoint-free control anchor and (b) a
   volatility-calibrated zero-edge simulation. **If the null reproduces ≥50% of the claimed effect,
   the effect is not credited.** This check costs ~10 minutes and would have killed this arm before
   it consumed weeks.
2. **A capture-uptime ledger.** `us_mid_tape` has **zero rows on 2026-07-17 and 2026-07-18** and only
   350,902 on 07-16 versus 2.5–3.9M on adjacent days. Every historical claim computed on this tape
   inherits an unquantified survivorship filter — one candidate's entire "stale quote" signal traced
   to these outages rather than to the venue. This contaminates future work regardless of this arm.

## 7. Correction to the record

The previously-cited *"last-25%-of-tape placebo = +8.46¢"* does **not** reproduce when the
pseudo-endpoint is drawn uniformly in **time** rather than in **print index** — it gives +1.13¢
[LB +0.41¢]. Prints cluster heavily near resolution, so the index-based version was never the
control it claimed to be. The retraction does not rest on it.

## 8. Standing conclusion

Six arms have now died here: copy-trading, consensus, weather, collapse-avoidance, `favorite_v2`,
and the final-hour favourite. **The last of them — the only λ>0 result the project ever produced —
was an artifact of the estimator, not a property of the market.**

The recorder stays running as a passive collector. It is the first instrument in this project to
capture a real, decision-time, executable ask with size and quote age attached — precisely the
defect that killed four of the five prior arms — and it should be pointed at whatever is tested next.

**k=0 remains correct. No live order is authorised.**
