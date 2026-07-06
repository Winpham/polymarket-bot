# Phase 1 — failure taxonomy & pre-registered kill-criteria (FROZEN before results)

Written before any stress number was computed (anti-p-hacking; the discipline this repo uses).
Each failure mode: **mechanism** · **how simulated (named machinery)** · **kill-criterion**
(the numeric result that alone makes it "not worth the risk"). Verdicts filled in Phase 5.

Recommended policy under test throughout = **`kelly_eighth_capped`** (⅛-Kelly per SE-shrunk band,
≤1 unit/event, ≤3/slate, ≤40%/regime, −5-unit daily stop), flat-SHARES, on **favorite only**
(elite_fresh_fav adds 0 independent bets — Phase 0). Bankrolls {1k, 5k, 25k}.

---

### F1 — Thin-edge variance (edge real but small; variance dominates a human)
- **Mechanism:** even a true +3–12% edge produces long red stretches by chance.
- **Simulate:** extend `risk_engine.py` block bootstrap to 1–3-yr horizons (H up to ~1000
  events). Report longest losing streak (events & weeks), max drawdown dist, P(net<0 at
  3/6/12 mo | edge genuinely +3%). Uses `bad_life_mc.py` with adversity OFF but edge set to the
  **honest LB (+3%)**, not the point estimate.
- **KILL:** P(net-negative at 12 mo | true edge = +3%) > 35% at recommended sizing, OR a normal
  variance stretch drives a >30% drawdown in >10% of clean-edge worlds.

### F2 — Edge decay to zero (efficiency / crowding catches up)
- **Mechanism:** the mispricing closes as the trade gets crowded or the book adapts.
- **Simulate:** `risk_engine` `edge_mult λ` swept {1,0.75,0.5,0.25,0}; then `decay_latency.py`
  models **λ(t) declining** with half-life {3,6,12 mo} and measures **detection latency** —
  events & dollars bled before the system's own gate (`MIN_PILOT_ROI 0.02`, `PILOT_MIN_EVENTS 50`,
  selection-null p≤0.01) would pull the arm.
- **KILL:** detection latency costs **more dollars than the cumulative edge earned before decay
  began** (i.e. by the time the gate fires, net lifetime P&L ≤ 0).

### F3 — Null-edge survivor (multiplicity / the market_resid trap generalized)
- **Mechanism:** ~15 arms were searched; keeping the best inflates family-wise error. Recall
  market_resid: a +30% "surplus" was a baseline artifact a 0-baseline gate false-promoted.
- **Simulate:** `multiplicity.py` — count the full family (§0.5), estimate FWER, re-run
  `selection_null` across all arms, and run the **certification pipeline end-to-end on
  label-permuted / synthetic-null data** to measure how often *some* arm emerges "certified" by
  chance.
- **KILL:** a synthetic-null world produces a certified-looking winner at a rate (≥ ~1 per search)
  that makes favorite's survival unremarkable — i.e. FWER-adjusted favorite p > 0.05.

### F4 — Costs worse than modeled (only +EV on paper)
- **Mechanism:** thin favorite-side book (0.80–0.97), partial fills, worse-than-mid execution,
  resolution/dispute risk. Current: `FEE 0.02`, `HAIRCUT 0.005`.
- **Simulate:** `cost_stress.py` — sweep haircut & fee 1×–5×; add a **liquidity-limited adverse-
  fill model** (entry bumped +1–3¢ on the favorite side) + small graded-loss dispute probability;
  recompute favorite's **realizable ROI and bootstrap surplus LB**.
- **KILL:** favorite's corrected surplus LB (event-N, gate convention) goes **≤ 0** under
  **2× haircut + adverse-fill (+2¢)** model.

### F5 — Correlated bad days (no diversification when you need it)
- **Mechanism:** on a bad slate most bets are the *same* bet (elite ⊂ favorite; within-tournament
  co-movement). An upset cluster (Cinderella run, high-variance format) hits the whole slate.
- **Simulate:** `bad_life_mc.py` injects **upset slates the record never saw** — with prob
  π_upset a slate's favorites (priced ~0.80) win at a depressed correlated rate q_upset (~0.55–0.65).
  Run through caps (`CAP_MAX_PER_SLATE 3`, `CAP_REGIME_FRAC 0.40`, `CAP_STOP_LOSS 5u`). Report
  worst slate / week / month.
- **KILL:** a plausible upset cluster (π_upset ≤ 0.15, q_upset ≈ 0.60) breaches the drawdown
  ceiling (maxDD > 30%) in **> 10%** of worlds (the repo's own `DD_CEIL_P`).

### F6 — Regime shift / sport drought (edge is regime-conditional; the regime changes)
- **Mechanism:** edge certified on tennis+WC+MLB. Calendar moves to (a) drought (no qualifying
  markets) or (b) a regime where the favorite bias is absent/reversed.
- **Simulate:** `bad_life_mc.py` regime sequence includes ≥1 drought stretch (fire rate → ~0) and
  ≥1 favorite-bias-absent stretch. Test the **adaptive overlay** (`map_state.py`) DODGE/PRIORITIZE
  latency when a cell flips winning→losing: does it pull out fast (good), lag (bleed), or thrash?
- **KILL:** overlay's regime-change response is **slower than F2's loss budget** (adaptivity
  doesn't actually save capital), OR drought forces >K weeks of zero fires making the arm
  operationally dead.

### F7 — Signal-source regression (the leaderboard cohort was lucky, not skilled)
- **Mechanism:** top-N leaderboard traders are partly lucky and regress; the edge rides a cohort
  that won't persist.
- **Simulate:** split-half persistence of the edge across time (adversarial_battery F3 style) +
  a cohort-persistence factor c ∈ [0.4,1.0] applied to the edge in `bad_life_mc.py`.
- **KILL:** edge does not persist out-of-cohort (split-half surplus LB ≤ 0), i.e. the measured
  edge is mostly last period's luck.

### F8 — Operational failure & adverse selection (you don't get the fills you backtested)
- **Mechanism:** capture-LEAD misses → fire late at a drifted line; **adverse selection** — the
  good lines get taken first, so *captured* fires are the leftover worse ones. Plus daemon wedge,
  stale-`main` deploy, leaderboard staleness.
- **Simulate:** quantify edge lost per minute of delay from `signal_price_trajectory`
  (`decay_analysis` split); inject missed-fire rate X% with adverse-selection bias on captured
  fills in `bad_life_mc.py`.
- **KILL:** realized edge after realistic capture failure + adverse selection falls **below the
  3% promotion margin.**

---

## Phase 2 composite — `bad_life_mc.py`
A **world** = (λ(t) decay path) × (cost level 1–3×) × (regime sequence w/ ≥1 upset stretch + ≥1
drought) × (missed-fire + adverse-selection rate) × (cohort-persistence c). Run recommended
policy end-to-end (kelly_eighth_capped, flat-SHARES, all caps, adaptive overlay) through ≥10k
seeded worlds. Report full tail: P(net<0 @12mo) at B∈{1k,5k,25k}; median & worst-decile terminal;
P(ruin@20%); P(maxDD>30%); longest underwater (weeks); and the **human-factor matrix**: P(a
reasonable operator pulls the plug after K red weeks) × whether pulling was *correct* (edge truly
gone) or a *false alarm* (edge intact, just variance).

## Pre-registered "NOT worth the risk" triggers (frozen)
Conclude **NO-GO / NOT-YET** if ANY hold under the composite realistic-bad MC:
1. P(net-negative @12 mo, recommended sizing) **> 35%**; or
2. P(maxDD > 30% of bankroll) **> 10%**; or
3. favorite's corrected LB **≤ 0** under 2× haircut + adverse-fill (F4); or
4. edge-decay detection latency costs **more than cumulative edge earned pre-decay** (F2); or
5. the winner is **not distinguishable from the multiplicity null** once the full family is
   counted (F3); or
6. the "operator pulls the plug" event is a **false alarm in a majority of worlds where the edge
   was actually intact** (strategy real but **unrunnable by a human**).

## Honesty rules
INDETERMINATE-BY-POWER is a valid verdict; never manufacture a number the 4-day record cannot
support. Distinguish refuted / survived / unknown. Every new script ships a `--selftest` that
exits non-zero on failure.
