# PRE-REGISTRATION — the collapse-risk model, forward paper test (frozen 2026-07-15)

**Frozen BEFORE any forward-outcome data is scored.** The model is trained on the international
harvest tape through window B (last-harvest ts ≤ 2026-07-14). Every knob below is fixed now, so the
forward record cannot be tuned into existence. **SHADOW / paper only — this pre-registration authorises
no live order.** Supersedes nothing; extends `project-polymarket-collapse-avoidance`.

## The claim, in one sentence
A roster-free win-probability model over **backward-looking price-path features** identifies ≥80¢
sports favourites that will **not collapse**, netting **+4.14% ROI-on-turnover** (EV>+0.01) OOS on
the international tape, event-clustered, p=0.000 — and this survives forward, at real forward prices,
on soccer/tennis/esports.

## Frozen decision rule (no free parameters left)
- **Universe:** markets in niches **{soccer, tennis, esports, ufc}** only. `mlb`/`nba` are EXCLUDED
  — they were negative OOS (mlb −0.47%, nba −0.95%) and the exclusion is registered here, not chosen later.
- **Trigger:** a taker BUY print at price **p ≥ 0.80** on a binary-market outcome.
- **Features (14, all strictly backward-looking; the exact builder is `collapse_risk.py::featurize`):**
  p, persistence≥0.80, n_prints, elapsed, max_p, drawdown_from_max, vol(last 30), n_dips_out_of_band,
  n_flips(50¢ crossings), drift_15m, drift_1h, staleness, mean_p_1h, niche. **No `n_trades`, no
  life-fraction, no market-end** (all lookahead).
- **Model:** `HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
  min_samples_leaf=80, l2_regularization=1.0)`, trained on window-A+B labelled data, **frozen**. The
  serialized model hash is committed alongside this file. It is **not retrained** during the forward window.
- **Entry gate:** act iff model **EV = p_win − p − fee(p, niche) > +0.01** (primary) — plus a
  registered secondary at **> +0.03**. `fee = θ·p·(1−p)`, θ = {sports 0.05}; at the US book θ=0.06.
- **Entry price:** the **real forward taker print** at/after the trigger (no lookahead), **plus a 0.5¢
  ask haircut** (we add size). On US, the first real US print from `us_trade_tape`.
- **Sizing for the paper ledger:** **flat** (1 unit/signal) for the edge test; a parallel **⅛-Kelly
  (f=0.069)** shadow book for the growth/drawdown test. No discretionary sizing.
- **Exit:** hold to settlement (0/1).

## Evaluation gate (the numbers that decide it, fixed now)
- **Unit of clustering:** the **EVENT** (game); a day-block sensitivity is reported but the gate is
  event-clustered.
- **Primary success:** forward **ROI-on-turnover CI lower bound > 0** at EV>+0.01, over **≥ 60 events**
  (power floor), with the point estimate **≥ +2.0%** (below that it does not beat the trustworthy
  `favorite_liq` anchor and is not worth the operational complexity).
- **Durability breaker:** must stay positive in **≥ 2 of {soccer, tennis, esports}** at support. One
  sport carrying it = the `favorite_v2` trap = FAIL.
- **Execution breaker:** the edge must survive the realised entry haircut (measured forward, not
  assumed). If realised slippage at $50–$100 exceeds ~2¢, the edge is gone (per the stress curve).
- **Drawdown breaker:** realised max drawdown must not exceed **2×** the modelled ⅛-Kelly median
  (16.6% event-block) — i.e. a hard stop for review at **~33%** drawdown.

## What would make me RETRACT (registered kill conditions)
1. Forward ROI LB ≤ 0 over ≥60 events.
2. Positive in only one sport.
3. Realised entry cost eats the edge (slippage breaker).
4. AUC on forward data drops below 0.60 (the model stops ranking collapse) — trained value was 0.78.

## Known residual risks carried into the test (not resolved by it unless stated)
- **Cross-venue basis tail.** Intl↔US median |basis| 0.8¢ but mean 2.4¢, corr 0.63 — the forward US
  paper test at real US prices RESOLVES this (that is a main reason to run it US-native).
- **79 days of history.** Day-Kelly is estimated on few draws; forward time is the only fix.
- **One harvest, one model fit.** Multi-seed EV sd=0.0006 (stable), but a single training epoch — the
  forward window is genuinely out-of-time.

Frozen by: Claude, 2026-07-15, on `feat/copy-edge-hardening`. Model artifact + feature builder pinned
at commit HEAD. No forward outcome has been scored at freeze time.
