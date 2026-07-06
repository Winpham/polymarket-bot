# REAL FOLLOWER-TAX MEASUREMENT — Cycle-5 report

**Branch:** run/beat-best-trader · **UTC:** 2026-07-06T05:06Z · **Posture:** PAPER-ONLY, nothing
promoted, no Rust mutated (D29 Phase-1 STOP holds), DB read-only, cost-zero. `selection_null.py
--calibrate` **PASS** (p<0.05 at 4% ≤ 20%; mid-range 84% ≥ 60%) → every null below is trustworthy.
Instruments: `real_tax.py` (NEW), `clv_lambda.py --market-key-join` (EXTEND), `drawdown_optimization.py
--real-tax` (EXTEND), `readiness_ledger.py` +3 informational rows (EXTEND). All `--selftest` green.

---

## 0. One-paragraph bottom line
The follower tax that every prior verdict rested on was **MODELED** (FOLLOWER_TAX 0.013 + band_spread ≈
**2.9¢** fill-weighted). This cycle **MEASURED** it from real captured asks: the REAL follower tax on
the recovered sample is **~1.0¢ market-clustered / 1.3¢ pooled (median 1.0¢)** — **materially SMALLER
than modeled** (real < modeled overall and in the book's bands 3/5; ≈ equal in 4). So the tax is
**partly a modeling artifact**. But that does **not** resurrect an edge: substituting the measured tax
into the realizable-Calmar pipeline lifts every book's realizable Calmar **~15–50%** — and the single
best reliable trader (master-wuji) **improves in lockstep and still dominates every book**, while the
belief-blind selection p **stays ≈0.10 regardless of tax level** (a common price shift cannot change
whether reliability-selection beats a random book). Under **all three** tax variants the WORTH-IT gate
returns the **same verdict: NOT_MET / INDETERMINATE-BY-POWER** — no play beats a random book OR the best
single at real prices. Meanwhile the recovered-capture **λ̂ = 0.136, CI-lo 0.065** sits far below the
0.25 edge-reality floor: the underlying favorite edge is still mostly FLB-bias. **VERDICT: the tax is a
partial modeling artifact, but the WALL IS REAL — optimization is over; only forward accrual remains.**
T4 forward-track **SKIPPED** (nothing survives to pre-register). Everything here is **thin** (~2.3 days
of dense capture, 8% fill coverage, capture-burst-adjacent bias) → INDETERMINATE-BY-POWER, not a win.

---

## T1 — Dense-capture coverage recovery (read-side market-key join)
`clv_lambda.py --market-key-join` (Cycle-2 fix in the research layer: join the trajectory by
(condition_id, outcome_index) instead of signal_id, so sibling-anchored paths attach to the favorite).

| join | trajectory coverage | real traj closes | λ̂ | λ̂ 95% CI | CLV-null p |
|---|---|---|---|---|---|
| signal_id (today) | **2.0%** | 7 / 347 | 0.146 | [0.078, 0.306] | 0.0000 |
| **market-key (fix)** | **19.9%** | **69 / 347** | 0.136 | **[0.065, 0.276]** | 0.0000 |

**~10× coverage recovery (2.0% → 19.9%)**, consistent with the Cycle-2 projection (~15%). This is the
true recovered coverage on the current record — below the projected 15.1% ceiling on the addressable set
only because the ceiling itself accrues; 19.9% is the *measured* recovery on all resolved favorites. Even
recovered, coverage is **< 50%** (K1 fires) so λ̂ is still fallback-mixed and INDETERMINATE-BY-DATA. The
default `clv_lambda` λ̂ join is **NOT** swapped (it's a GO-gate input — DEFERRED for human/Rust review).

## T2 — REAL follower tax vs MODELED (the core)
`real_tax.py`: for each resolved BUY trader fill on a captured market, REAL executable entry = the
earliest captured **ASK** on that same market within [fill_ts, fill_ts+900s]; REAL tax = ask − fill price.
Overall **12,174 / 152,354 fills matched (coverage 8.0%) across 153 markets.**

| cell | MODELED tax | REAL tax (median) | REAL tax (mkt-clustered mean) | n_matched | real < modeled? |
|---|---|---|---|---|---|
| **overall** | **0.0289** (fill-wt) | **0.0100** | **0.0102** (pooled 0.0134) | 12174 | **YES** |
| band 1 (0.0–0.2) | 0.0361 | 0.010 | 0.0223 | 1908 | yes |
| band 2 (0.2–0.4) | 0.0230 | 0.000 | 0.0273 | 947 | no (≈) |
| band 3 (0.4–0.6) | 0.0408 | 0.010 | 0.0259 | 2735 | yes |
| band 4 (0.6–0.8) | 0.0209 | 0.010 | 0.0235 | 1973 | no (≈) |
| band 5 (0.8–1.0) | 0.0236 | 0.010 | 0.0092 | 4611 | yes |

**The modeled tax OVERSTATES the real follower cost.** At the overall/pooled level the real tax (~1.0¢)
is roughly **⅓ of modeled (~2.9¢)**; per band the picture is milder — real < modeled in bands 1/3/5 (incl.
the book's band-5 favorites, 0.9¢ vs 2.4¢), ≈ equal in 2/4. The flat **FOLLOWER_TAX = 0.013** assumption
in particular looks too high given the measured median drift+spread of ~1.0¢. **Honest caveats:** (1)
coverage is 8% — captures cluster around OUR signal fires, so a fill only matches if it landed shortly
before a capture burst → the matched slice is biased toward capture-adjacent (liquid, tight) moments;
(2) thin single-market cells (e.g. lol|b4) are junk even after clustering; (3) ~2.3 days of capture.
→ **INDETERMINATE-BY-POWER; directionally real < modeled.**

**REAL λ̂ (front-running / edge-reality):** on the recovered market-key sample, λ̂ = **0.136, CI [0.065,
0.276]** — **CI-lower 0.065 is far below the 0.25 floor** (and the point estimate is below it too). CLV is
positive vs the selection-matched null (p=0.0000), i.e. the line does move our way, but it explains only
~14% of the favorite surplus — **the edge is still mostly favorite-longshot bias, not information.**

## T3 — Re-decide realizable edge on the MEASURED tax
`drawdown_optimization.py --real-tax {clustered,pooled}` substitutes the per-band measured tax for the
modeled reprice; re-run on identical current data. Belief-blind gate = realizable OOS Calmar, weighting
held equal (isolates SELECTION), vs a random equal-size book AND vs the best single reliable trader.

| tax mode | equal-book our OOS Calmar | refined book OOS Calmar | best single (master-wuji) OOS Calmar | beats best? | belief-blind p | verdict |
|---|---|---|---|---|---|---|
| MODELED (baseline) | 0.0215 | 0.1061 | **0.2113** | **NO** | 0.103 | INDETERMINATE |
| REAL — clustered | 0.0374 | 0.1256 | **0.2368** | **NO** | 0.1005 | INDETERMINATE |
| REAL — pooled | 0.0521 | 0.1573 | **0.2633** | **NO** | 0.0999 | INDETERMINATE |

**Three findings, one conclusion:**
1. **The lighter measured tax helps — but not enough.** Realizable Calmar rises ~15–50% (equal-book OOS
   0.0215 → 0.0374 → 0.0521; refined 0.106 → 0.126 → 0.157). The max-Calmar in-sample recovery of the
   0.167→0.044 collapse climbs 28% → 51% → 66%. But **OOS it still overfits** (0.007 / 0.014).
2. **The best single trader improves in lockstep and still dominates.** master-wuji's realizable OOS
   Calmar rises 0.211 → 0.237 → 0.263 — because the tax cut is a *common* shift, the single-best tail
   benefits exactly as much as the book. `beats_best_single = False` under **every** tax variant.
3. **Selection significance is invariant to the tax level.** The belief-blind p stays **≈0.10** across
   modeled/clustered/pooled — a uniform price shift moves the refined book and the random null together,
   so it **cannot** change whether reliability-selection beats random. Even a *zero* tax would not make
   selection significant. The book's realizable dd-reduction-per-return-sacrificed vs the best single
   stays **negative** (−7.67 → −5.93 → −4.02): the diversified book still adds drawdown per return.

**THE DECISION:** the follower tax is a **PARTIAL modeling artifact** (real < modeled), but **NO
realizable play survives the belief-blind gate at the measured tax.** The single best reliable trader
still beats every book; reliability-*selection* is still indistinguishable from a random book. **The wall
is confirmed. Optimization on the current record is over.**

## T4 — Forward-track (SKIPPED)
T3 shows **no surviving realizable edge that clears the belief-blind gate**, so per the charter T4 is
**SKIPPED** — there is nothing to pre-register that isn't already dominated by simply tailing the single
best reliable trader (itself gated behind the same persistence wall). **The honest next step is (a)
forward accrual** of independent non-soccer regimes (esports / NFL Sept / NBA Oct) to attack the binding
persistence wall, **and (b) promoting the read-side dense-capture market-key join to a real gate input**
(the λ̂/tax pipeline) — flagged **DEFERRED for human + Rust review** (it changes a GO-gate input and
touches the live capture/scoring path; do not silently swap mid-run).

## READINESS-LEDGER DELTA
`readiness_ledger.py` +3 informational rows (`--selftest` PASS; NOT GO gates): `real_follower_tax` =
**MEASURED (thin)** (real ~1.0¢ < modeled 2.9¢, 8% coverage → INDETERMINATE-BY-POWER); `edge_reality_
recovered` = **INDETERMINATE** (coverage 2%→20%, λ̂-lo 0.065 << 0.25); `realizable_edge_on_measured_tax`
= **NOT_MET** (best single still dominates; selection-p tax-invariant ≈0.10 → wall confirmed). **GO gates
unchanged 2/4; real-money-eligible = False; binding constraint = persistence over independent non-expiring
regimes (MONTHS).**

## HONEST BOTTOM LINE
This was the last analysis lever, and it landed cleanly on the truth: **the modeled follower tax was too
harsh (real ≈ ⅓–1× of it), but fixing it changes the *level*, not the *verdict*.** Because a tax cut
lifts the single-best tail exactly as much as the book, and because selection significance is invariant
to a common price shift, **no amount of tax-realism makes reliability-selection beat a random book or the
best single trader.** Combined with a recovered-capture λ̂ still far below the edge-reality floor, the
conclusion is unambiguous: **the remaining wall is not modeling — it is forward accrual (months of
independent non-soccer persistence).** Nothing promoted, nothing armed, no Rust touched.

---
*New: `real_tax.py` (T2). Extended: `clv_lambda.py --market-key-join` (T1/λ̂), `drawdown_optimization.py
--real-tax clustered|pooled` (T3), `readiness_ledger.py` +3 rows. Reports: `real_tax.json`,
`clv_lambda_marketkey.json`, `drawdown_optimization_real_{clustered,pooled}.json`. All `--selftest` green;
read-only, paper-only, nothing promoted.*
