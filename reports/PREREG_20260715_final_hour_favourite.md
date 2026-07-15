# PRE-REGISTRATION — final-hour favourite late-convergence, forward paper test

**Frozen 2026-07-15, branch `feat/confidence-forensics`. Paper/analysis only. No live order, ever.**
This freezes the forward test BEFORE any live data is collected, because a backtest can prove an edge
fake but never prove it real (see `reports/CONFIDENCE-FORENSICS.md`): the confirmation must be live,
out-of-sample, at the realizable price, on a live-knowable trigger. Nothing below may be changed once
signals accrue; changes require a new dated PREREG and reset the count.

## Hypothesis (from Phases 7–8, retrospective, event-clustered, official DMR)
A thin US book underprices the LEADING favourite in the final ~30 minutes of a near-decided game.
Retrospective (maturity-anchored, buy-favourite [0.65,0.98], 1c haircut): ATP/WTA −0.5h **+7.55c**
(p<.005), ITF **+3.94c** (p<.005), esports **+4.51c** (p=0.02); all flip NEGATIVE by −2h. It is
information (λ=0.73 [0.51,0.91], CLV +0.042 p(CLV≤0)=0.001) and generalises across 3 independent
regimes (clears the ≥2-regime bar `favorite_v2` failed). It is NOT capturable retrospectively — the
price tape and venue schedule don't locate the final ~30min (endDate is ~4h off; all live-knowable
price anchors are negative). It IS capturable live via a game-state feed. This test proves or kills that.

## Universe (frozen)
- US `aec-` game-WINNER markets only; standard (non-exotic — the `us_native_backtest.EXOTIC` regex);
  liquid (≥50 prints / active book on `us_mid_tape`).
- Sports, FREE-feed subset first: **tennis ATP/WTA** (ESPN hidden API), **esports CS2** (bo3.gg, the
  Foresight feed). ITF (paid tennis feed) and other esports titles are OPT-IN extensions logged
  separately, not part of the primary gate.

## Trigger (frozen, live-knowable — the whole point)
Fire at most ONCE per market, at the first instant ALL hold:
1. The live feed reports the market's favourite side is **near-decided**:
   - tennis: a player is **up 2 sets** (best-of-3) OR **serving for the match** (leading the final set
     by a break, game score ≥5 or ≥5-4/deciding);
   - esports: **match point** (leading maps, on the closing map/decisive round lead).
2. The US book prices that same favourite in **[0.65, 0.92]** on `us_mid_tape` (headroom band; excludes
   the near-ceiling degenerate zone).
3. The market is still actively trading (a fresh `us_mid_tape` quote within 5 min).

## Entry / costs / settlement (frozen)
- Entry = the real US **best_ask** at trigger time (record `entry_ask`, `mid`, `spread`, feed state, ts).
- Cost = US taker fee θ=0.06·p(1−p) + **measured** realized slippage from the book (NOT an assumed
  haircut — `feedback-measure-costs-not-just-edges`).
- Settlement = official DMR `settlement_price` (business_date=maturity_date); interim = terminal
  `us_mid_tape` state, flagged provisional.
- λ/CLV close = last non-degenerate `us_mid_tape` mid in [0.02,0.98] after entry, before resolution.
- Sizing = PAPER, flat $50/signal for accounting. No real order path is touched.
- `warmup=TRUE` for any signal where the feed/book history at fire time is <30 min (excluded from gate).

## Success gate (frozen) — clears only if ALL:
Over **≥60 clean events** (warmup=false), spanning **≥2 sports** AND **≥2 distinct tournament weeks with
≥1 non-Wimbledon week**:
1. event-clustered ROI **lower bound > 0**;
2. point ROI **≥ +2.0%**;
3. **λ (CLV/surplus) CI lower bound > 0** — the market must confirm the pick (else it is variance).

## Retract conditions (frozen) — any one kills it:
- R1: ROI LB ≤ 0 at ≥60 clean events.
- R2: λ CI includes 0 at ≥60 events (it was variance, like the champion/collapse).
- R3: edge exists ONLY in Wimbledon / one tournament (fails the ≥2-week, ≥1-non-Wimbledon requirement).
- R4: measured slippage/fee eats the gross to ROI LB ≤ 0 (dies at the realizable price, like the rest).

## Standing bar mapping
This is the standing certification bar (`feedback-confidence-certification-bar`), forward: walk-forward
(live is inherently OOS) + λ>0 + realizable-price + live-knowable trigger. Green here = a
pre-registered forward test passing on a genuinely information-bearing, realizable-price edge — the
first the project has had. It does NOT authorise a live order; that remains a separate, explicit,
Tue-only decision.
