# Autonomous program — "Identify the Genuinely Skilled": find traders whose profit PERSISTS

> **How to run.** Open a FRESH Claude Code session in `~/polymarket-bot` and paste this whole
> file. Work WS-0 → WS-5 in order. Self-directed: work autonomously to finished, gate-green,
> forward-accruing artifacts. Cost-zero (Max only; never `ANTHROPIC_API_KEY`; never spawn child
> `claude`). Read-only against reality; new arms silent + default-OFF; live alert path byte-identical.

## 0. Mission (and the wall you must not walk into again)

Skilled, persistently-profitable Polymarket traders **exist** — the leaderboard is realized on-chain
PnL. The open problem is **identifying them EX-ANTE**: which traders will profit *going forward*, not
which profited in the past. Every past-performance signal has been tested and **fails**:

| signal (retrospective) | early→late persistence | verdict |
|---|---|---|
| surplus-over-cell-blind | −0.10 | NULL |
| realized ROI (dollar-weighted) | −0.15 | NULL |
| "highest success rate" selection | edge retained ≈ 0 | NULL |
| per-sport specialist book | 0 certified | DEAD |

These held even after: full-history backfill (1.07M→1.79M fills), weeding market-makers by **churn**
(not trade-count — see §2), and requiring genuinely time-separated periods. **Do not re-run
past-performance ranking in any form — it is exhausted.** The winner's curse (leaderboards are
short, variance-dominated samples of PnL-selected survivors) is the wall. Your job is to find the
signal that is NOT past PnL.

**The generator/gate contract:** be a wild generator about what *could* identify skill; put ALL
rigor at the **belief-blind, forward, event-clustered gate**. A signal counts only if it predicts
**forward** profitability out-of-sample — never on the fit window. Expect several hypotheses to be
REFUTED or INDETERMINATE-BY-POWER; a sycophantic "it works" is a failure.

## 1. The lead hypothesis: CLV (closing line value) — the betting-world gold standard

A trader who consistently buys **before the price moves toward the outcome** has skill that ROI
variance cannot drown. CLV = (price at/near resolution − entry price) on their held direction. It is
the single most robust skill signal in sports betting and **we have never measured it.**

**It is NOT retrospectively computable** — our price-history tables (`signal_price_trajectory`,
`market_feature_log`) cover only bot-tracked consensus markets, a sliver of what these traders bet.
So CLV must be **captured forward**: WS-1 builds the instrument.

## 2. Standing truths to respect (verified this program; don't re-derive)

- **Churn, not trade-count, separates predictors from market-makers.** The fills/day filter was 92%
  wrong (flagged 100 directional limit-order traders as bots, caught only 8 real MMs). Churn =
  `Σ 2·min(buy_sh,sell_sh) / Σ(buy_sh+sell_sh)` per wallet; **≥0.70 = pure market-maker** (mechanical
  spread/rebate profit, weed out); <0.70 = directional (keep, even if high-frequency). ~25 wallets
  fleet-wide are true MMs. **Swap this into `classify_trader_types` (still fills/day in prod).**
- **The aggregate consensus edge is real (~+2–4% over blind) and already captured** — that is the
  system's edge. Individual selection has added 0 on top of it, five ways. Any new signal must beat
  the aggregate, forward, to matter.
- Data: `trader_fills` (1.79M fills, 423 wallets, backfilled). Leak-free event dates come from the
  slug (`asof_slice_scores.sql` / `asof_preflight.py`), NOT `resolved_at` (bulk-stamp, D1). The
  favorite-residual `(sport,band)` cell-blind is the honest baseline.

## 3. Workstreams

### WS-0 — Foundation (do first)
1. Swap the churn classifier into `classify_trader_types` (migration/code); re-run classification;
   confirm ~25 MMs flagged, ~100 formerly-mislabeled directional traders restored. Gate green.
2. Refresh the retrospective null table (§0) as a frozen baseline artifact so no future WS re-opens it.

### WS-1 — Forward CLV instrument (the lead)
Build a silent, read-only forward capture: for every fill a tracked trader makes (from the live
poll), record entry price + snapshot the market's price at fixed horizons after entry and near
resolution (reuse the `signal_price_trajectory`/dense-capture machinery, generalized to
trader-fill markets, bounded + throttled — respect the data-api rate limit, §churn run showed 403
burst-throttling; back off on 429/403/5xx). Emit per-(trader) forward CLV, event-clustered. **No
verdict yet — it accrues.** Pre-register the gate: CLV_lo>0 forward, ≥N events, ≥2 disjoint windows.

### WS-2 — Reduced-variance retrospective signals (exhaust what's left, honestly)
Past *outcomes* are noisy; test signals that are lower-variance than ROI and MIGHT persist:
- **Calibration slope** (do their prices predict frequencies better than the market's?), Brier/
  log-loss improvement over the blind, **shrinkage (empirical-Bayes) ranking**. Judge by forward/
  in-out persistence, event-clustered. Likely NULL — record it and move on if so.

### WS-3 — Cross-sectional / structural identifiers (not past PnL)
Search for EX-ANTE trader attributes that correlate with FORWARD profit: entry-timing behavior
(early vs late in a market's life), price-band discipline, market-type concentration, bet-size
distribution shape, activity cadence. Fit on in-sample traders, test the attribute→forward-profit
map on a DISJOINT set of traders (out-of-cohort). Adversarial: any attribute selected from many is
max-of-noise — Bonferroni + label-permutation null.

### WS-4 — Round-trip / timing skill (the second axis)
`advantage` is BUY-only. Build leak-free round-trip (entry→exit) realized PnL per trader as a
*distinct* skill axis (a trader sharp at TIMING differs from one sharp at DIRECTION). Test its
forward persistence separately.

### WS-5 — Integration, multiplicity, verdict
Any survivor must (a) clear the belief-blind forward gate on ≥2 disjoint windows, (b) survive a
label-permutation null over the WHOLE search (many signals × traders → some clear by chance —
`selection_null.py`), (c) add independent edge over the aggregate consensus (`edge_orthogonality.py`)
AND over each other survivor. Write `reports/skilled/VERDICT.md` (bottom line first, unhedged), a
`FINDINGS.md` compounding ledger (SURVIVED/REFUTED/INDETERMINATE with LB/CI/forward-N/what-would-
flip-it), and a `DECISIONS.md` D-entry. Real money stays gated (paper/silent).

## 4. Pre-registered honest kill-criteria (decide BEFORE running each WS)
A signal is NOT real if ANY hold: it doesn't beat the aggregate consensus forward/out-of-cohort; it
doesn't persist across the in/out (or forward) split; a label-permuted null manufactures it at the
observed rate; or it adds no independent edge in the orthogonality test. **Be willing to conclude
that identification requires MONTHS of forward CLV accrual and that no retrospective signal suffices
— that is a legitimate, valuable verdict, not a failure.**

## 5. When done
Print the one-line verdict, the SURVIVED/REFUTED table, and the exact forward-N/weeks still needed
to certify any silent instrument. Leave all artifacts under `reports/skilled/`; all arms silent;
nothing merged to live alerting. Note for memory (Tue decides): which signals survived vs refuted,
the churn-classifier swap, and the forward-CLV ETA.

**Remember the point:** the skilled traders are real; past PnL cannot find them; find the forward
signal that can — or prove, honestly, that only forward CLV accrual will.
