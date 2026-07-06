# Phase 4 — adversarial self-review (red-team of the stress test itself)

Stance: *"this stress test went easy on the system — find where it flattered the edge, and also
where it was UNFAIRLY harsh, because a hostile risk officer who cries wolf is as useless as a
sycophant."* Every soft spot below was hunted before the verdict was written; fixes/caveats are
folded into VERDICT.md.

## A. Where the test may have gone EASY (system looks better than reality)

- **E1 — upsets are independent across slates.** `bad_life_mc.draw_world` draws `is_upset`
  per-slate i.i.d. Real upset regimes are **serially correlated** (a Cinderella tournament run,
  a high-variance format spans a week+). Independent upsets **undercount the correlated bad
  MONTH** — the worst-month figure is therefore *optimistic*. Direction: the composite is if
  anything **too kind** on tail clustering. Not corrected (would only worsen the verdict);
  flagged.
- **E2 — cohort turnover is not correlated with outcomes.** A market-structure break that
  regresses the leaderboard cohort (F7) is exactly when outcomes also turn — the composite
  treats `cohort` and slate outcomes as independent, so it misses the joint hit.
- **E3 — drought = fewer fires only.** The prompt's real worry was drought → *pressure to loosen
  filters and bet worse*. Modeled only as rate×0.1 (opportunity cost), not degraded selection.
  Mild optimism.

## B. Where the test may have gone TOO HARD (system looks worse than reality) — must flag

- **H1 — the median world is genuinely adverse.** Every world draws `cohort∈[0.4,1.0]` (mean
  0.7) AND `adv_sel∈[0.5,1.0]` (mean 0.75) → a ~47% edge haircut as the *central* case, before
  decay/upset/cost. If true central persistence is higher (cohort~0.85, adv_sel~0.9), the picture
  is materially less dire. **This is the single biggest lever in the whole test.**
  *Counterweight (why it's still roughly fair):* the base edge fed in is the **optimistic point
  estimate** — including band 5's 97.9% winrate on ~50 events, which Phase 0 flagged as
  small-sample luck. So the two errors roughly offset: point-optimistic base × pessimistic
  haircut ≈ an effective central edge near the **honest LB region**, which is the right place to
  be. The verdict does **not** rest on H1 — see §D.
- **H2 — the composite does NOT credit the adaptive overlay's mid-run DODGE.** F6 shows
  `map_state` correctly DODGEs a cell that turns reliably negative. The composite only measures
  an *end-of-run* operator pull, so it gives the system **no** mid-run defensive exits. Real
  deployment with the overlay live would rescue some decayed/upset cells. *Counterweight:* F2's
  detection latency is **hundreds of events**, so the overlay is slow relative to the grind —
  partial mitigation at best, not a rescue. Net: composite is a **lower bound** that omits a real
  (but slow) defense.
- **H3 — the operator-pull rule (4 consecutive red weeks) is naive and over-triggers.** With
  thousands of ~1%-bank bets and injected upset variance, 4 red weeks in a row occurs often even
  on a truly +EV edge — which is *why* the false-alarm rate is 65%. A statistically literate stop
  (CUSUM / sequential-probability-ratio on realized-vs-expected) would false-alarm far less. So
  "unrunnable by a human" is **partly a bad-stop-rule artifact**, not pure edge-smallness. The
  guardrail spec replaces the naive rule; trigger #6 is therefore marked **PARTIALLY-FIRING /
  fixable**, not a clean kill.

## C. Structural findings that are INDEPENDENT of the composite's parameter choices

These survive every fairness caveat above, because they are properties of the *data and the
sizing*, not of the injected world:

1. **The generalization LB is unbounded below on G≈4 independent day-blocks** (Phase 0; df=3
   one-sided 5% LB = −8.2%). No parameter choice fixes too-few-blocks.
2. **The sizing is calibrated on lucky bands.** Band 5 = 51% of bets, observed winrate 97.9% on
   ~50 events → implied full-Kelly 0.60; even ⅛-Kelly stakes **7.5% of bankroll per bet**. If the
   true band-5 rate is even a few points lower (F4: band-5 reverting to price = −5.8%), the
   sizing is catastrophically overconfident. This is a **structural** ruin driver.
3. **It is one bet stream, concentrated in expiring tournaments.** elite_fresh_fav ⊂ favorite
   (adds 0); ~70% of profit is Wimbledon + WC soccer, both expiring within weeks. No
   diversification when a correlated bad slate hits.

## D. Does the verdict survive the fairness caveats?

Yes — but with the honest refinement H1 forces. A friendly-world rerun (mild versions of all
factors at once, edge at point) is comfortably profitable: **P(net<0)=0.4%, 5th-pct positive**
(`friendly_sensitivity.json`). So the composite's ruin is **not** purely structural — it needs the
adverse stack. The correct reading is therefore **BIMODAL**: friendly world → profit, adverse world
→ 85% net-neg / 39% ruin, and the §C structural facts (unbounded-below LB on G=4, sizing on lucky
bands, one concentrated bet stream) make the adverse world **impossible to rule out on 4 days**.
That is exactly why the verdict is **NOT-YET (resolve the bimodality with forward paper), not
NO-GO (edge fake)** — the edge survives F2/F3/F4 and thrives in the friendly world; what it lacks
is the data to prove which world is real. A sycophantic reading ("the composite was just too mean")
is still refuted — flat-shares fails, the posterior fails, band-5 is fragile — but so is an
over-harsh reading ("it's structurally doomed"): the friendly world shows it isn't.

## E. Fixes applied as a result of this review
- Report **both** policies (kelly + flat-shares) in the verdict; do not headline the flattering
  kelly-deleverage DD without the flat-shares tail.
- Add a **hard per-bet fraction cap** (≪ ⅛-Kelly-of-band-5) to the guardrail spec.
- Replace the naive K-red-weeks stop with a **sequential/CUSUM decay-pull** trigger.
- State the H1 lever explicitly so Tue can see how much of the bad outcome is adversity-assumption
  vs structural.
