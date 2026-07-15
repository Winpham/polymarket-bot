# RUN: Confidence Forensics — why nothing is *confidently* profitable, and how to fix it

**Branch:** cut a fresh one off `main` (`coord/newchat.sh` if solo-multi; else `feat/confidence-forensics`).
**Paper/analysis only. No order is placed. Ever.** Predecessor context:
`REPORT-COPY-EDGE-HARDENING.md`, `reports/GO-LIVE-READINESS.md`, `PREREG_20260715_collapse_model.md`,
and the memory node `project-polymarket-collapse-avoidance`.

## The question, stated honestly (do not accept the comfortable version)

The prompt that spawned this run was: *"figure out why we're not completely confidently profitable
like we were, and fix it."* **The premise "like we were" is probably false, and your first job is to
test it, not assume it.** The evidence on hand says we were *never* confidently profitable:

- The live champion `favorite` arm ran — and still runs — at **k=0 (zero Kelly sizing)**. The
  decision kernel is PARKED at k=0 on purpose (`project-polymarket-decision-kernel`).
- Why: **λ̂ ≈ 0.14, CI [0.065, 0.276]** (`reports/clv_lambda_marketkey.json`). λ is the fraction of
  the favourite surplus that is *information* rather than *variance / favourite–longshot premium*.
  λ≈0.14 means **~86% of the "edge" is variance harvesting, not predictive skill.** The sizing engine
  never believed the backtest, which is why it stakes nothing.
- The belief-blind champion LB was **+2.85% at p=0.13** — not significant. `favorite_v2`'s +7.63% was
  ruled **"not bankable"** (tournament artifact). Every other arm in the repo is a retraction
  (copy-trading DEAD→INDETERMINATE, market-making KILLED, per-sport 0/7, cross-market 0 cells, …).

So the real question is the systematic one:

> **Why does every edge here look confidently profitable in a retrospective backtest and then
> dissolve — into variance (low λ), or into ~0 at the realizable price on the venue we can trade —
> the moment we try to size it or ship it? Diagnose the systematic cause, then determine whether the
> collapse model escapes it or is its latest instance.**

A NO ("the collapse edge is variance / dies at the US ask, same as the rest") is a *complete, valuable*
answer. A fabricated YES is the only real failure.

## Non-negotiables

1. **`psql` always `-v ON_ERROR_STOP=1`** and **`SET max_parallel_workers_per_gather=0`** (the DB
   serves the live bot; a parallel seq-scan already caused an outage). Reuse the pinned helpers in
   `scripts/niche/*.py`.
2. **Every cost/price is the REALIZABLE one, measured, with a CI.** No typed constants
   (`feedback-measure-costs-not-just-edges`). Price at the real ask you'd pay, on the venue you'd
   trade.
3. **Separate information from variance everywhere.** A positive mean ROI is not an edge if it is
   variance premium (low λ). Report λ (or an equivalent info-vs-variance decomposition) for any arm
   you would size.
4. **The unit of risk is the EVENT (game).** Cluster CIs on event; block-bootstrap by day for tail
   risk (`project-polymarket-correlated-risk`).
5. **Honesty > tidiness.** Retract your own prior claims the instant a test overturns them. A
   timed-out/partial phase is "incomplete + resumable", never "done".

---

## PHASE 1 — Confidence forensics: what was ever real?

Build the timeline of every "profitable" claim and classify each as **JUSTIFIED**, **VARIANCE
(low-λ)**, **ARTIFACT (leak/tournament/coverage)**, or **RETRACTED**. Sources: the memory graph, the
`reports/` graveyard, `RESEARCH.md`, `DECISIONS.md`, the PREREG files.

- For the champion `favorite` and `favorite_liq`: recompute **λ / info-vs-variance** on current data.
  Is any of the surplus information? If λ CI still includes ~0, the arm is a variance premium and
  "profitable" was always the wrong word for it.
- Deliverable: a one-page ledger — claim → what it rested on → what it actually is now. This is the
  honest answer to "were we ever confidently profitable?" Most likely: **no**, and that reframes the
  rest of the run from *recover* to *establish for the first time*.

## PHASE 2 — The crux: MEASURE the US absolute cleanly (the "unmeasurable" verdict is not acceptable)

The predecessor concluded the US absolute edge is "unmeasurable retrospectively" because T&S-inferred
settlement is biased. **That verdict is a starting point to attack, not a stopping point.** Get a
CLEAN US absolute by routing around the biased label, three independent ways — they must agree:

1. **Intl-resolution settlement (the strong one).** A US contract and its intl twin resolve on the
   *same real-world event*. `us_mapper.py` + `cross_venue_basis` map US↔intl (only 58 live-captured,
   but the mapper can map more offline from `us_markets.parquet` ↔ `harvest_markets` on
   `(teams, date, market-type)`). For every mappable US symbol, settle from the **clean intl
   resolution** (`trader_fills.outcome_won`), and re-run the US backtest. **This eliminates the T&S
   settlement bias entirely.** Report the US absolute (blind + model) on the mapped subset,
   event-clustered.
2. **DMR-clean days.** 2026-07-12 and 07-13 have explicit `settlement_price` in
   `us_daily_market_report` (or the local `us_reports/*-daily-market-report.csv`). Small but
   *unbiased*. Measure blind + model there; it is a clean spot-check on (1).
3. **Forward-clean (already accruing).** `collapse_forward.py` settles on terminal market state going
   forward. Report whatever CLEAN (warmup=FALSE) signals have accrued.

**The decisive sub-question:** on cleanly-settled US data, **are US favourites genuinely overpriced
(~3pp at the touch, as the biased data hinted) or was that the artifact?** If they are genuinely
overpriced, the collapse edge likely does not pay on US and you must say so. If not, the earlier
negative was measurement and the port is alive — quantify it.

## PHASE 3 — The attenuation: matched-event intl-vs-US (is 3¢→1¢ real?)

On the mappable subset from Phase 2, run the frozen model on the **same games** priced two ways:
intl ask vs US ask. If the model nets ~3¢ on intl and ~1¢ on US **for the same events**, the
attenuation is real — and you must explain it (US book prices favourites more efficiently? US entry
ask worse? thinner/ different population?). If it nets ~3¢ on both for matched events, the "1¢" was a
universe/settlement artifact and the port is stronger than the predecessor thought. **This is the
cleanest possible transfer test — same events, both venues, one model.**

## PHASE 4 — Re-audit the INTL edge under fresh skepticism (was our confidence justified?)

The intl +4.14% is the thing that *felt* confident. Attack it as if you were trying to retract it:

- **Walk-forward, not one split.** The whole intl result is a single A/B split + one model fit
  (multi-seed stable, but one epoch). Do a proper **rolling walk-forward** (≥3 folds, expanding
  window). If the edge is a lucky window, this exposes it. ITER-5 died exactly here
  (`project-polymarket-garbage-policy`: "single-split +1.58% but walk-forward −2.75%").
- **λ / info-vs-variance for the collapse model itself.** Is the collapse edge *information* (λ high —
  it genuinely predicts which favourites hold) or is it a **fancier variance-premium harvester** (low
  λ, same disease as the champion)? Decompose. **This may be the single most important test in the
  run** — it tells you whether the collapse model is categorically different from everything that
  came before, or just a better-dressed version of the same variance harvest.
- **The Brier-beat.** "Model Brier beats the market price" is the signature of a leak. Re-examine on
  walk-forward, out-of-time, curated. Does it survive?
- **Temporal stability.** ROI by sub-window — stable, or driven by one hot stretch (a WC, a Slam)?

## PHASE 5 — The systematic pattern: do our edges die at the realizable price?

Zoom out. Across the graveyard, is there ONE recurring killer?
- `project-polymarket-exec-policy`: "selection exhausted at the realizable price."
- `feedback-measure-costs-not-just-edges`: unmeasured costs decide verdicts.
- λ≈0.14: variance masquerading as edge.
- The US attenuation: backtest edge shrinks at the tradeable ask.

Characterise the pattern precisely: **at what step does confidence evaporate, every time?** Then
state what a genuinely confident edge would have to survive that our past "edges" never did (e.g.
λ CI lower-bound > 0 AND positive at the realizable venue ask AND walk-forward-stable AND
information-not-variance). Make that the **standing certification bar** for anything that gets sized.

## PHASE 6 — Resolve it (the point of the run)

Land on one of these, with the evidence to back it:

- **A) The collapse edge is real, information-driven (λ>0), and survives clean US measurement.** Then:
  quantify the confident US ROI, update the forward-test expectations, and define the exact go-live
  trigger. This is the win.
- **B) The collapse edge is information on intl but does NOT pay on US** (favourites genuinely
  overpriced / attenuation real). Then: the intl book is where the money is — assess the CFTC
  reopening petition path (`project-polymarket-us-venue`), and/or design a **US-NATIVE** model trained
  on US data once the forward tape accrues enough (the model needs only price paths). Say plainly that
  US is not tradeable-profitable today.
- **C) The collapse edge is variance, not information** (low λ, dies on walk-forward) — same disease
  as the champion. Then: we have *never* had a confident edge, retract accordingly, and either pivot
  to a genuinely information-bearing signal or conclude this market is efficient at our realizable
  price and stop.

Whichever it is, deliver: (1) the honest verdict, (2) the standing certification bar from Phase 5,
(3) the updated memory, (4) if A: the go-live trigger; if B/C: the pivot.

## Gates & kill conditions
- **Phase 2 channels must agree.** If intl-resolution settlement, DMR-clean, and forward-clean give
  materially different US absolutes, you have a measurement bug — resolve it before concluding.
- **λ CI lower-bound ≤ 0 ⇒ do not call it an edge.** Size nothing on variance.
- **Walk-forward mean ≤ 0 ⇒ the intl edge was a lucky window.** Retract.
- **No fabricated YES.** If the honest answer is B or C, that is the deliverable, not a failure.

**Nothing in this run authorises a live order.** Green means a *pre-registered forward test running
on a genuinely information-bearing, realizable-price-surviving edge* — not a backtest number.
