# Go-live readiness — the collapse model on real money

**2026-07-15. Branch `feat/copy-edge-hardening`. Honest gate assessment. Nothing here is deployed.**

Tue's goal: prepare to trade this with real money. This is the straight answer on where we are,
what is proven, and the specific things that stand between here and a live order. **Verdict up front:
NOT READY to send money — but the path is now concrete and short, and the one blocker is a forward
measurement, not a rebuild.**

## What is PROVEN (rigor-hardened, international tape)
- **Mechanism.** The edge is collapse-avoidance; binary-market structure forces it (same-outcome
  Δ(won)≡0; 100% of the effect is the 5% of prints on the collapsing side). Not price composition,
  not timing, not weighting.
- **Roster-free capture.** A market-feature model matches the roster (+3.15¢ vs +3.68¢), 18× universe.
- **Edge vs the champion.** Refined tradeable subset +4.14% (EV>0.01) / +5.65% (EV>0.03) ROI,
  event-clustered, p=0.000 — dead heat to a gain vs the trustworthy `favorite_liq` anchor (+4.17%).
- **Durability.** Certifies in soccer/tennis/esports independently (clears the bar favorite_v2 failed);
  mlb/nba dead (excluded) — structure, not a scan artifact.
- **Execution cost.** Survives a 2¢ ask haircut (defuses the ITER-5 failure mode). US fee is inside it.
- **Risk.** At ⅛-Kelly: 0% modelled ruin, ~17% median max drawdown, P&L broad (top-5% events = 26%).
- **No leakage.** Feature builder passes future-rewrite tests; train/test effectively event-disjoint.

## What is NOT proven — the blockers, in order
1. **Absolute US profitability is UNMEASURED.** The frozen model's *selection* transfers to the US
   tape (paired model−blind surplus +0.97¢ EV>0.01 / +1.80¢ EV>0.03, p=0.000) — but the *absolute*
   US ROI cannot be read from history because T&S-inferred settlement is biased negative (winners
   stop trading ~0.90 and drop out; losers crash to 0 and stay). The true US edge is roughly
   [−2%, +1%] and **not demonstrably positive.** This is THE blocker. It is a measurement gap, and
   only clean forward settlement closes it.
2. **The US edge looks ATTENUATED** — ~1¢ surplus vs intl's ~3¢. Whether that is genuine (thinner US
   book, WC-heavy window) or residual bias is unknown. Size expectations DOWN accordingly.
3. **No live execution path exists.** No US order client, no auth wiring, no kill-switch, no position/
   exposure ledger, no reconciliation. All to build (see checklist).
4. **The US tradeable universe is thin + must be curated.** Pointing the model at the raw US tape
   loses money (exotic-prop pollution). A live signal MUST gate to standard, liquid game markets and
   exclude exact-score/corner/stat submarkets. The clean universe is small in a WC-dominated window.

## The go-live checklist (nothing is optional before real money)
**A. Prove it forward (the gate).** Run the pre-registered paper test
(`PREREG_20260715_collapse_model.md`) on **real forward US prices with real forward settlement**,
gating to the curated universe. Success bar (frozen): ROI LB > 0 over ≥60 events, point ≥ +2.0%,
positive in ≥2 of {soccer,tennis,esports}. **This is the only thing that turns "unmeasured" into a
number.** Est. wall-clock: weeks (calendar-bound).

**B. Build the execution spine (parallel to A, no money):**
- [ ] US order client (Python/TS SDK; `keyId`+`secretKey` HMAC — Tue's KYC'd credentials, never in repo).
- [ ] Live signal generator: frozen model + curated-universe gate + EV>threshold, off the live
      `us_mid_tape`/`us_trade_tape` feed (already accruing).
- [ ] Pre-trade risk gate: ⅛-Kelly sizing, per-event exposure cap, daily loss limit, price-band guard.
- [ ] Kill switch + heartbeat; hard cap on order size ($50 start, $100 ceiling per capacity memo).
- [ ] Fill reconciliation + a real-money ledger separate from the paper ledger.
- [ ] Idempotent order submission (no double-fills on retry).

**C. Shadow-trade the spine** against the paper ledger for the same window as A, so we confirm the
live signal path reproduces the backtest's selections before a cent is at risk.

**D. Go-live is a config flip, only if:** A passes its frozen bar AND C matches AND Tue authorises.
Start at $50/signal, ⅛-Kelly, one sport, with the kill-switch armed. Scale only on realised
forward P&L.

## The honest one-liner for Tue
The research is done and it is strong — but it is strong **on the international book**. On the book you
actually trade, we have proven the model *selects* correctly and have NOT yet proven it *makes money
after everything*, because the historical US data can't measure the absolute level cleanly. The
responsible next step is the forward paper test on live US prices; building the execution spine in
parallel means the day that test passes, going live is a switch, not a project. **Do not send money
before the forward gate clears** — the US absolute edge is genuinely unknown and could be ~0.
