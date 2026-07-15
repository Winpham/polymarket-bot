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

## The go-live checklist — status after the 2026-07-15 build run
**A. Prove it forward (THE GATE) — BUILT + STARTED, now accruing.** `collapse_forward.py` +
`migration 047` run the pre-registered test on **real live US prices** (frozen model, curated
universe, entry at the real ask, forward settlement). First scan recorded 103 markets but flagged
them **warm-up** (feed had <1 day of history → caught mid-life → excluded from the gate). CLEAN
forward-caught signals accrue going forward. Success bar (frozen): ROI LB > 0 over ≥60 events, point
≥ +2.0%, positive in ≥2 of {soccer,tennis,esports}. **The ONE action left for Tue: keep it running**
(install the launchd timer — see below). Est. wall-clock to power: weeks (calendar-bound).

**B. Execution spine — BUILT (paper-first, no money):**
- [x] Pre-trade **risk gate** (`scripts/execution/risk_gate.py`): kill-switch, model-provenance,
      niche allowlist, 0.80–0.98 band, min-EV, daily loss-limit breaker, ⅛-Kelly sizing, per-EVENT
      cap, $50/$100/$250 hard-stop ladder. Pure + fully unit-tested.
- [x] **Order client** (`scripts/execution/us_order_client.py`): paper client (idempotent) runs;
      live client **refuses at three latches** + transport unimplemented — no accidental money path.
- [x] Live signal generator = `collapse_forward.py --scan` (frozen model + curated gate off the feed).
- [ ] Fill reconciliation + real-money ledger DB — **deferred to the post-gate authorised change**
      (needs Tue's credentials; not built by design).

**C. Shadow-trade the spine** against the paper ledger for the same window as A — pending A's accrual.

**D. Go-live is a config flip, only if:** A passes its frozen bar AND C matches AND Tue authorises
AND wires the live transport. Start at $50/signal, ⅛-Kelly, one sport, kill-switch armed. Scale only
on realised forward P&L.

## The ONE command to keep the forward test running (Tue's call — persistence)
```
cp launchd/com.tue.collapse.forward.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.tue.collapse.forward.plist
```
Scans + settles every 10 min, durably (no long-lived process to be reaped). Read-only except the
append-only ledger; no API key, no order path. Check progress any time:
`python3 scripts/niche/collapse_forward.py --report`.

## The honest one-liner for Tue
The research is done and it is strong — but it is strong **on the international book**. On the book you
actually trade, we have proven the model *selects* correctly and have NOT yet proven it *makes money
after everything*, because the historical US data can't measure the absolute level cleanly. The
responsible next step is the forward paper test on live US prices; building the execution spine in
parallel means the day that test passes, going live is a switch, not a project. **Do not send money
before the forward gate clears** — the US absolute edge is genuinely unknown and could be ~0.
