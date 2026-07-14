# RUN: Copy-Edge Hardening — audit it, then make it pay

**Branch:** `feat/copy-edge-hardening`. **Paper/analysis only. No order is placed. Ever.**
Predecessor: `feat/follower-tax` (`FOLLOWER-TAX-ANATOMY.md`, commit 5eba04d), which decomposed the
follower tax and concluded copy-trading is **alive in the 80–100¢ band**: +2.99¢/share, +2.62¢ over
a matched blind baseline, p=0.000, 830 markets, BH-clean.

This run does **not** assume that conclusion. It tries to kill it, and only then tries to grow it.

---

## The one-paragraph reason this run exists

The predecessor's own result table contains a row it printed and did not discuss:

| cell | COPY | BLIND | SURPLUS | 95% CI | p | mkts |
|---|---|---|---|---|---|---|
| **band 80–100¢** (headline) | +2.23¢ | −0.39¢ | **+2.62¢** | [+1.24,+4.00] | **0.000** | 830 |
| **FAVOURITES 80–100¢ × sports** | +2.66¢ | **+2.27¢** | **+0.39¢** | [−2.22,+2.99] | **0.372** | 196 |

Restrict the *same band* to **sports** — the only niche the live bot trades, and the only one where
the US book is deep enough to fill — and the blind baseline **rises to +2.27¢** (that is the
favourite–longshot bias, exactly where theory says it should be) and **the copy surplus collapses to
zero.** The headline's +2.62¢ is carried by non-sports markets. The only significant niche is **MLB:
+9.73¢ surplus on 67 markets** — the concentration signature that has already produced one retracted
"maker-copy +4.8%" in this repo.

Meanwhile the depth cut says the surplus lives in **deep >1k markets (+1.82¢, p=0.042)** and is
**negative in the mid 200–1k band (−0.69¢, p=0.702)** — which is precisely the slice
`project-polymarket-capacity` named as *the tradeable one*.

So the claim being carried into memory may be true only where we cannot trade it. Phase 0 decides.

---

## Non-negotiables (violating any of these invalidates the run)

1. **`psql` always with `-v ON_ERROR_STOP=1`.** The predecessor's helper ran without it, so a failed
   query **exits 0 and returns an empty CSV** — a broken query becomes a clean "0 signals" *null
   result* instead of a crash. It already did exactly that once (a 1,109-wallet `IN`-list blew the
   container's 64MB `/dev/shm`). `copy_econ.py` **still has the defect**; fix it here.
2. **`SET max_parallel_workers_per_gather=0`** on every analysis query. That Postgres serves the
   **live bot**; a parallel seq-scan over 57M `harvest_fills` rows already caused one outage
   (`project-polymarket-us-outage-2026-07-14`).
3. **Every cost is measured, with a CI, or it is not used.** This run exists because a *typed*
   constant decided a verdict. Do not type a new one. Note the predecessor typed `sports: 0.03` into
   `copy_vs_blind.py` while the repo's own verified figure is **sports 0.05 / US taker 0.06** — the
   same error class, this time biased *in our favour*. See §A0.
4. **Any cell scan is BH-corrected across every cell scanned**, and the correction set includes the
   cells scanned in *previous* runs when re-using their rosters. Re-running a graveyard of parked
   arms under a friendlier cost model is a multiple-testing machine.
5. **Honest reporting.** A timed-out or partial phase is "incomplete + resumable", never "done".
   A NO is a cheap, good outcome. A fabricated YES is the only real failure.

---

## PHASE 0 — Kill tests. Everything downstream is gated on these.

### A0. Reconcile the fee constant, from the source
`copy_vs_blind.py` / `net_surface.py` use `REAL_FEE_RATE = {sports: 0.03, politics: 0.04, crypto:
0.07}`, default 0.05. The repo's verified figures (`project-polymarket-global-shrunk-edge`,
`project-polymarket-us-economics`) are **sports 0.05, crypto 0.07, politics 0.04, US taker Θ=0.06
confirmed on all 2,999 US markets**. Where did 0.03 come from?

- Re-derive `fee = shares × Θ × p × (1−p)` against the live fee schedule and, where possible,
  **measure Θ empirically from the tape** (US regulatory T&S + `us_trade_tape` give realised fees).
- Re-run the headline at the corrected Θ. Report the delta. Both legs pay it, so the *surplus*
  should be near-invariant — **if it is not, that is itself a finding.**
- **Deliverable:** a single `costs.py` / `costs.rs` module that is the only place a cost lives.

### A1. Decompose the surplus. **This is the decisive test and it is cheap.**
`net = won − p − fee`, so exactly:

> **surplus = Δ(win-rate) − Δ(entry price) − Δ(fee)**

Report those three terms for every cell. The interpretation is binary:

- If the surplus is **Δ(won)** — the roster picks *winners* — it is **selection skill**. Real.
- If the surplus is **−Δ(p)** — the roster merely enters *cheaper within the same 20¢ band* — it is a
  **price-composition artifact with zero skill**, because the "band" is 20¢ wide and the blind leg
  samples every print across the market's whole life while copy enters at one specific point on the
  price path.

Nobody has run this decomposition. Run it first.

### A2. Re-do the blind baseline with a **price caliper**
Replace "same 20¢ band" with **same market, same side, entry price within ±1¢** (and report ±0.5¢,
±2¢). This is the control that A1 will have already told you the answer to; A2 makes it airtight and
survives review.

### A3. A **pre-drift-matched** momentum control
The predecessor rejected momentum with *roster-blind* policies. That is the wrong control. The event
study says the price rallies **−6.05¢ over the 15 min before** a roster fill. So the honest control
is: **non-roster prints in the same market and band that exhibit the same 15-min pre-drift.** If the
surplus vanishes against *that*, the roster is a pre-drift detector and the wallets are decoration —
we can drop the roster and trade the pre-drift, or we have nothing.

### A4. Is copy **additive** to the favourite arm we already own?
The repo already runs a **certified** favourite arm (`favorite_v2`, liquidity ≥ $1k ∧ rank < 5,
+7.63%). The sports-favourite blind leg here nets +2.27¢ — i.e. *buying favourites blind is already
most of the copy leg's +2.66¢.* The question that decides whether this deserves a single dollar:

> Inside the **gated favourite-arm universe**, does a roster print **improve the arm's ROI**?
> (Interaction test: arm-only vs arm ∧ roster-print vs roster-print-only.)

If copy is a *worse* version of an arm we already trade, it is not an edge — it is a distraction.

### A5. The slippage the run set to zero
The predecessor is right that the 1% slippage was **double-counted** in the backtest — entry is
priced at a real taker print that really cleared, which *is* the spread. But live, **we are not
inheriting that print; we are adding an order that was not in the book.** The claim "slippage = 0"
is therefore itself an *assumption* — the very sin the run's own lesson names. Measure it:

- Replay $50 / $100 / $250 clips against **measured book depth** (`us_book_tape`, `us_quotes`) in
  the favourite band, and report **slippage(size, depth) with a CI.**
- Expect it to be small in deep sports-favourite books (`project-polymarket-us-venue`: $50–250 fills
  at ~0¢ slip, ~$2.5k at touch) — but *measured small*, not *asserted zero*.

### A6. Drawdown, not just the mean
Favourites **win small and often, lose big and rarely.** The mean is established; the tail is not.
- Block-bootstrap the equity curve **clustered by EVENT, not market** — `project-polymarket-correlated-risk`
  established the unit of risk is the **GAME** (both legs of a game resolve together).
- Report max drawdown, risk-of-ruin at the intended bankroll, and the **Kelly fraction** (cap at ⅛,
  per `project-polymarket-risk-engine`).

### PHASE 0 GATE
- **A1/A2 show the surplus is Δ(won)** ∧ **A3 survives the pre-drift control** ∧ **A4 shows
  additivity** ⇒ proceed to Phase 2.
- **Otherwise:** write the negative up honestly, **retract the memory**, and go straight to Phase 1 —
  *which pays regardless of the copy edge's fate.*

---

## PHASE 1 — The cost-model prize. **Run this even if Phase 0 kills the copy edge.**

This is worth more than the copy edge and it is independent of it.

`margin = slippage(0.01) + fee(0.02) = 3%` (`RESEARCH.md:24`) is wired into the **live board gate**
(`board.rs::render`), the certification bar, and **every negative verdict in the graveyard**. The
true cost in the favourite band is **~0.5–0.9¢**. We have been charging ~3¢ against ~0.9¢ — and a
cost that biases *against* your own strategy reads as honesty, so nobody ever audited it.

1. Land the measured `costs` module from A0/A5 (Θ by niche **and venue**, plus measured slippage).
2. **Re-net every parked arm** against it. Rank by *cost-marginality*: arms whose gross edge sits in
   **[0.9¢, 3.0¢]** were killed by a phantom ~2.3¢ and are the candidates to flip. Known graveyard:
   per-sport conditioning (0/7), cross-market price bands (0 cells), the fade inversion, exec-policy,
   the decision kernel (parked at k=0), favourite-consensus.
3. **BH-correct across the entire graveyard**, not per-arm. Anything that flips is a **candidate**
   requiring a pre-registered forward test — *not* a resurrection.
4. Fix the live board gate so it stops rejecting real arms.

---

## PHASE 2 — Make it pay. (Gated on Phase 0.)

**$13/day at $50/signal is not a business.** If the edge survives, the job is to grow it — and the
levers are not the ones the predecessor reached for.

- **Band frontier.** The tax at 60–80¢ is only **1.70¢**, and that band holds **788 markets** of
  volume vs 830. The predecessor certified only 80–100¢ and stopped. Trace **net edge × signal
  volume** across the whole band curve and find the **$/day-maximising** frontier — not the
  edge-maximising cell.
- **Roster-depth frontier.** The roster is top-100 of 11,127. The *complete* population (~90k
  wallets) is already harvested. More wallets ⇒ more signals at lower average edge. Maximise
  **signals/day × edge/signal**, not edge/signal. Nobody has traced this curve.
- **Capital turnover — probably the biggest untouched lever.** Every number in this repo is ROI *per
  trade*. Money is made on ROI *per capital-day*. A favourite held 3 days to resolution at +3.4% is a
  very different business from one held 6 hours. **Measure hold-time, and prefer fast-resolving
  markets.** This can multiply $/day at a *fixed* bankroll with no new edge.
- **Sizing.** Fractional Kelly from A6, capacity-capped by the A5 depth curve, correlation-clustered
  by event.

---

## PHASE 3 — The venue bridge. **The signal is intl. The money is US.**

Every number in the follower-tax run was measured on the **international** tape. Tue executes on
**Polymarket US** — a *different exchange with a different book* (proven: same contract, same
instant, different BBO). Nothing here transfers for free.

1. **Does the intl-observed signal survive on the US book?** Price it at the US touch, at the US fee
   (**Θ=0.06**, ~0.77¢/share at p=0.85), at the US book's **real measured depth**, across the
   **cross-venue basis** (`cross_venue_basis`, 8,651 rows; `us_arb_scan.py` already found the
   favourites efficient — which cuts both ways: no free lunch, but also no adverse basis).
   The US fee is **double** the 0.03 the predecessor charged. Confirm the edge is not fee-fragile.
2. **The US-native roster is a CLOCK — and it is already ticking.** The US venue publicly broadcasts
   a live trade tape **with per-trader identity** (`taker.username` on 100% of prints) over an
   unauthenticated WebSocket. `us_tape_ingest.py` is running under a keepalive and `us_trade_tape`
   holds **759k rows**. But there is **no US identity history** — the regulatory T&S tape is
   anonymous. A US-native roster can therefore only be built **forward**, and **every day of delay is
   a day of roster history that cannot be recovered.**
   - **Keep that ingest alive. Monitor it. This is the single highest-leverage standing action in the
     repo, and it costs nothing.**
   - A US-native roster would make the whole cross-venue basis question *moot* — signal and execution
     on the same book.

---

## PHASE 4 — Pre-registration (the only path to money)

If and only if something survives: write the pre-registration **before** looking at another number —
cell, band, roster, ranker, size, fee model, entry lag, stop rule, N, and the success criterion —
then run it forward on the `honest-pnl` paper ledger. Retrospective slices are exhausted; the binding
constraint is **power**, and only forward time buys it.

**Nothing in this run authorises a live order.**
