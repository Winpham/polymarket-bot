# Entry 15 — "Bad Days" stress test: can this system lose, and is it worth the risk? (NOT-YET)

**Date:** 2026-07-02 · **Status:** paper-only, read-only on live behavior, **zero migrations**,
nothing promoted, no env/alert/ledger change. Artifacts under `reports/stress/` +
`scripts/stress/` (every script `--selftest` green). A hostile-risk-officer run against the two
certified-eligible arms (`favorite`, `elite_fresh_fav`), asking whether the system stays reliably
+profitable over a realistic 1–3-yr run that is *not* all good days.

## Bottom line: NOT-YET (leaning NO-GO on the current sizing)

Do not commit real money now under `kelly_eighth_capped`. Three pre-registered kill triggers fire
(#1 P(net<0)>35%, #2 P(DD>30%)>10%, #6 operator-pull is a false alarm in a majority). The binding
one needs **no** pessimistic modelling: **at ⅛-Kelly, if the true edge is half the measured +12.5%
(inside the honest CI), the strategy breaches its own 30%-drawdown ceiling in 44% of years — zero
other stress.** Flip to GO requires (1) de-lever the sizing, (2) ≥5 non-expiring regimes of
forward proof (calendar-gated → months), (3) populate the (empty) CLV/adverse-selection monitor.

## The central fact (Phase 0)

The whole evidentiary base is **4 day-blocks** (G=4) with **no losing slate**; the forward-sealed
ledger is ~1 day. So `risk_engine.json`'s P(profit)=100% is a no-losing-slate artifact
(`ceiling_slack=True` — the engine says so itself), and the empirical bootstrap CANNOT price a bad
regime. The mission required **injecting failure the record hasn't shown.** favorite's surplus LB
spans **+7.6% (tournament grain) … −8.2% (day grain, df=3)** — generalization is not bounded above
zero. `elite_fresh_fav` is 100% nested in favorite → **one bet, not two.** ~70% of profit is
Wimbledon + WC, both expiring; 2 of 4 "regimes" are N<10 perfect-record luck.

## What the injected failures showed

- **The structural flaw:** kelly-by-band = {band4: 0.009, band5: 0.565}. ⅛-Kelly stakes ~7% of
  bankroll per **band-5** bet (the ~break-even one, only ~5–8pp of margin) and ~0 on band-4 (the
  safe one). It bets biggest exactly where the margin is thinnest.
- **F1 clean-world (no stress, edge scaled):** DD>30% in **0% / 44% / 94%** of years at edge =
  +12.5% / +6% / +3%. Net-negative 0% / 0.4% / **42%**. Sizing-vs-uncertainty alone is disqualifying.
- **Composite (10k worlds, all failures partial + simultaneous):** P(net<0)=85%, P(DD>30%)=92%,
  P(ruin@20%)=39%, median 49-of-52 weeks underwater. **But** factor decomposition shows **each
  failure ALONE → 0% net-negative**; only the *stack* is lethal. The 85% is an adversarial upper
  bound (independent simultaneous erosion), not a forecast — the verdict rests on the
  stack-independent results (F1, the LB, the human matrix), not the 85%.
- **Human factor:** a reasonable operator pulls the plug in 70% of worlds, and **65% of pulls are
  false alarms** (edge intact, pulled on variance) → unrunnable by a human at this sizing.
- **F4 costs: PASS** — LB +4.1% at 2× haircut + 2¢ fill (dies only at 5×+3¢+2×fee). But band-5
  reverting to its price under those costs → −5.8% (the cost×regression interaction).
- **F3 multiplicity: PASS** — favorite null p=0.0000 survives ×13 Bonferroni. Caveats: pipeline
  FWER 7.5%; it certified `strict_retuned` on **N=14** — a tiny-N false-positive; don't count it.
- **F2 decay latency: PASS at +9% edge** (net +$2.5k–17k at pull); marginal at +3% (27–34% net≤0).
  Latency isn't the problem, thin edge is.
- **F6 overlay:** the per-slate stop-loss does NOT bound cross-regime drawdown (median maxDD 71%);
  the adaptive overlay needs ≥20 events / ~14 days per cell to DODGE — too slow for an upset burst,
  useless when all cells erode. Entry-12's "drawdown bounded by construction" holds only per-slate.
- **F7 (cohort) / F8 (adverse selection): INDETERMINATE-BY-POWER** — 4 days can't test cohort
  turnover; `signal_price_trajectory` is **empty**, so we can't measure our own fill quality.

## Guardrails before any real-money pilot

Flat-SHARES or ≤1/16-Kelly with a hard 2%-of-bankroll per-bet cap and a band-5 exposure cap;
bankroll-relative −8% daily stop; ≥50 events **and** LB>3% in **≥5 disjoint non-expiring regimes**;
two-strikes 50-event decay-pull (not tick-by-tick — 37% false alarm); cost-drift alarm; **populate
the CLV/adverse-selection monitor.**

## Honest "worth it?"

Upside is real and large IF +12.5% is genuine (clean-world median +$558k/yr @ $5k) — but 4 days
cannot confirm that, and the downside (39% ruin under the composite; a strategy pulled 70% of the
time, wrongly 65% of those) is disqualifying now. The juice may be worth the squeeze, but only
after de-levering and earning ≥5 non-expiring regimes of proof. Expected cost of finding out:
months of calendar time + paper-loss variance that would look like failure most of the way even if
the edge is real.

## Kill criteria honored / limitations
Pre-registration frozen before results (`01-pre-registration.md`); INDETERMINATE-BY-POWER used
where 4 days can't support a number (F7, F8); the composite's harshness is disclosed and the
verdict rests on stack-independent results. No live behavior, ledger, env, or migration touched.
**Rollback:** delete `scripts/stress/` + `reports/stress/`; nothing else changes.
