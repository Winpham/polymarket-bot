# weather_fav — ADVERSARIAL VERIFICATION (v2, with recovered June out-of-sample)

**Branch `feat/weather-verify` (worktree `wt/weather-verify`, off `feat/weather-cert` `5802516`).
Read-mostly. No order placed, no API key. `main`/`feat/weather-cert`/`wt/evergreen-cert` untouched.
Scripts `--selftest` green. Run 2026-07-15. Stance: SKEPTIC — default to artifact unless evidence is
strong. This gates real money.**

---

## ONE-LINE VERDICT

**SURVIVES-AS-INDETERMINATE — cannot refute, cannot certify. k=0, do-not-size, MUST accrue forward; the
sharp edge is structurally untestable on history.** The +15% July ROI is a **genuine, non-leaked
in-sample edge** (entry lands ~46h *before* the weather outcome; official settlement) and it is **not**
the raw favourite-longshot band premium (the raw band earns ~0% in July, −7% in June). But the sharp
selection **cannot be tested out-of-regime** (zero convergence signal exists before July), the λ/CLV
"market-confirms" crux is **not robustly demonstrated** (CI straddles 0 at the fair horizon), and the one
OOS-testable adjacent — the favourite band — **loses money in June**. So there is no out-of-sample support
for the edge and the surrounding regime is hostile. Disposition matches weather-cert (accrue, don't kill);
its "market confirms the move / λ information" *framing* is oversold, but its core claim that the sharp
selection beats a naive band is **vindicated in-sample**.

---

## PER-ATTACK SCORECARD

| # | attack | result | verdict |
|---|--------|--------|---------|
| 1 | **Disjoint-time (decisive)** | **Independently confirmed pre-July is structurally empty.** Raw-tape weather market universe by month: Dec 1 / Jan 1 / Mar 1 / Apr 1 / **May 20 / Jun 392 / Jul 6,325** (matches the cert agent's claim). Sharp convergence (≥3 rank≤250 one-sided backers, band): June had **0 markets with even ≥2 backers** → 0 picks; dropping `GO_LIVE` entirely still yields all 1,412 picks in July. The sharp edge cannot be falsified out-of-regime. | **INDETERMINATE — untestable-on-history** (NOT a refutation) |
| 1b | **RECOVERED out-of-sample: the BAND** | Since the sharp signal is absent pre-July, I ran the *band* (the only OOS-testable component) on **20–22 disjoint June resolution days** (May 30–Jun 30), tape-inferred resolution **validated 605/605 = 100% vs official**. Favourite band 0.71–0.90: **ROI −6.8%** [−21.9, +6.5], win 78.9%. Band 0.71–0.98: **−8.6%** [−21.7, +1.9], win 84.5%. Same construction on July = ~0% (band 0.71–0.90 **−0.4%**, win 81.1%). **The band is no edge and is regime-fragile.** | **REFUTED (the band); sharp untestable** |
| 2 | **Independent λ/CLV recompute** | Reproduced the harness exactly. Fair-horizon (24h) λ CI LB **negative** (atfire [−0.089,+0.90]; tape [−0.222,+0.73]); CLV CI straddles 0 (p 0.08–0.18). Higher "clean" CLV (+7.6¢ using last print before weather-day-end) uses a near-outcome horizon that partly reflects the *already-known intraday high* → not a clean forward confirmation. The market-confirmation (λ) claim is **not robustly demonstrated**. | **SURVIVES (crux unproven, as reported)** |
| 3 | **Leakage hunt** | ROI is **not** lookahead: entry `ts0` median **46h before weather-day-end** (p25 38h); `resolved_at` ≈ weather-day-end (median +2.4h); only **3/212** closes fall after the outcome. No survivorship (testable 95.5% ≈ all-resolved 95.9%). Entry basis apples-to-apples. | **SURVIVES (ROI leak-free)** |
| 4 | **Adjudication / MIRAGE (CORRECTED)** | The sharp selection **does** beat a naive favourite band: same ~82¢ entry, win-rate **95.8% (sharp) vs 81% (raw band)**, ROI **+15% vs ~0%** in July. My v1 wrongly used the consensus `_blind` pool (itself pre-selected) as comparator; against the *raw* band the sharp lift is real. BUT it is a **win-rate/selection** edge, not the CLV "market-confirms" edge the report headlines — paired CLV diff is not significant (primary band 24h −2.5¢, p=0.78). | **sharp-vs-raw-band SURVIVES; CLV-confirmation claim REFUTED** |
| 5 | **Fragility** | Bar-1 ROI robust: drop-best→+14.0%, drop-worst(07-04)→+18.8%, drop-both→+18.2%; fee-insensitive (0.05 vs 0.03 = 0.3pp). BUT **48% of picks (113/236) on one day (07-06)**; 9 consecutive July days; effective N ≈ **9 day-clusters**. | **SURVIVES within-July / regime-fragility unquantifiable** |

---

## THE TWO DECISIVE FACTS

**(A) The sharp selection is real in-sample and cannot be a close-timing artifact.** Entry converges the
day *before* the weather day (median 46h before the outcome is knowable); official CLOB settlement; buying
82¢ favourites that win 95.8%. A naive favourite band at the same price wins only 81% and earns ~0%, so
the ≥3-backer convergence is doing genuine selection work (plausibly it is riding public weather
forecasts, which are genuinely predictive). This **corrects my v1** and **vindicates** weather-cert's core
claim over evergreen-cert's "band does the work" — against the *raw* band, the sharp is not decorative.

**(B) But every path to validating it fails or is unavailable.**
- The sharp signal **cannot be computed before July** (0 pre-July convergence; the wide-rank population did
  not trade weather until July). The decisive disjoint-week test is structurally impossible.
- The only OOS-testable adjacent — the favourite band — **loses −7% to −9% in June** and earns ~0% in July.
  So the edge is not resting on a stable band premium, and the surrounding weather regime is hostile.
- The λ/CLV "the market confirms the move before resolution" crux is **not robustly positive**: CI
  straddles 0 at the fair horizon, and the larger CLV numbers borrow from horizons where the intraday high
  is already public. The demonstrable edge is *selection/win-rate*, not *market confirmation*.
- 9 consecutive days, 48% of mass on one day (07-06), effective N ≈ 9 → no regime-robustness.

## RECONCILING THE TWO CERTS (corrected)

Both certs are right about the **disposition** (k=0, don't size) and both are partly oversold on
*interpretation*. Weather-cert is **right** that the sharp selection carries a real in-sample edge beyond a
naive band (evergreen-cert's "band does the work / sharp decorative" is wrong against the *raw* band). But
weather-cert **oversells** the mechanism: the edge is win-rate selection, not the "+6¢ forward move the
market confirms" (λ). Evergreen-cert is **right** that λ≈0 / market-confirmation is not demonstrated.
Neither ran the June band OOS; it is negative, which neither narrative accounts for.

## CAN WE TEST NOW, OR MUST WE ACCRUE?

**Must accrue — the sharp edge cannot be validated on history at all.** No pre-July convergence exists, and
the one adjacent OOS test (band) is negative. Certification requires forward accrual of disjoint weeks with
the λ CI LB clearing 0 under the frozen gate. Until then: **k=0, do not size, do not build sharp-selection
execution infra on this evidence.** If accrual proceeds, log it as an explicit forward paper track of the
sharp signal (not the band), and treat the −7% June band as a live regime-fragility warning.

---

## Artifacts (all on `feat/weather-verify`, read-only; DB reads SELECT-only, no incumbent touched)
- `reports/repro_4bar.json` — exact reproduction of the 4-bar harness (numbers match WEATHER-FAV-CERT.md).
- `reports/.prejuly_wx_tape.pkl`, `.july_wx_tape.pkl` — raw weather tape for the June/July OOS band test.
- This report. Cost-zero (no `ANTHROPIC_API_KEY`, no child `claude`).
