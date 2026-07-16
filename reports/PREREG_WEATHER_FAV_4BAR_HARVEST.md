# PRE-REGISTRATION — weather_fav through the 4-bar gauntlet, on the HARVEST-TAPE edge window

**Frozen:** 2026-07-15 (UTC), before computing any new number on this branch.
**Branch:** `feat/weather-cert` (off the `feat/evergreen-cert` commit `05b0e10`; a strict superset of
`main`). **Paper / read-only. No order placed, ever. No API key. No incumbent touched, nothing armed.**

## 0. Why this run exists (and how it differs from the committed 1c140f1 cert)

The active `feat/evergreen-cert` session already ran a weather_fav 4-bar gauntlet (commit `1c140f1`,
verdict C / 0-of-4 / λ≈0). Its λ — the crux — was computed on **2 consecutive stalled resolution-day
clusters (07-13, 07-14)** using a live CLOB `prices-history` fetch, because the `weather_fav` *arm*
only began capturing `entry_ask` on 07-12. The brief tells me to **ignore the last ~2 days (ingestion
stalled 07-14)** — i.e. exactly that window.

This run is an **independent, higher-powered, fully-OFFLINE replication of the crux** on the window
where the edge actually lives:
- **Universe / close source = the `harvest_fills` intl taker tape** (niche='weather', 6,719 untruncated
  markets, ~4M prints, 2025-12→07-14) — the SAME source `collapse_lambda_wf.py` uses. No live endpoint.
- **Edge window = the in-sample consensus edge (july 1–8+), ~1,180 resolved picks, ~81% forward-close
  coverage, 7+ resolution-day clusters** — ~4× the day-clusters of the committed cert.

If λ still reads ≈0 / negative at a fair horizon here, verdict C is **independently confirmed with
power**, not merely power-starved. If λ turns positive, the committed verdict is contradicted.

## 1. The selection under test (FROZEN, leak-free) = the weather_fav arm's own rule

A `weather_fav` pick = one `(condition_id, outcome_index)` such that, over `trader_fills` BUY prints
with `ts >= GO_LIVE (2026-06-29)`, `slug ~ 'highest-temperature'`, and backer `followed_traders.rank ≤ 250`:
- ≥ **3** distinct one-sided backers (no backer holds both outcomes of the market), AND
- mean backer price `AVG(px)` ∈ the certification band, AND
- the market is resolved with a known `outcome_won`.

Decision time `ts0 = MIN(backer ts)`. This is byte-identical to `weather_scan.py::fetch_weather_picks`.
**Primary band = 0.71–0.90** (a-priori: the 0.90–0.98 deep-chalk band earns ~0/$ — the win-rate trap —
and adds no selection skill; frozen in the incumbent prereg). **0.71–0.98 tracked secondarily.**

## 2. Price bases (FROZEN)

- **entry = at-fire mid** = `_blind` signal `initial_mean_price` for the SAME `(condition, outcome)` — the
  CLOB mid ~10–15 min post-convergence, the champion's realizable-PROXY basis. PRIMARY. A pick with no
  `_blind` at-fire mid is EXCLUDED from the entry-anchored bars.
- **forward close(H)** = the last `harvest_fills` BUY print for that `(condition, outcome)` with
  `ts ≤ res_ts − H·3600`, degenerate-guarded to [0.02, 0.98]. `res_ts` = `_blind resolved_at`.
  `H ∈ {last-tick, 24h, 12h, 6h, 3h, 1h}`. **last-tick OVERSTATES** (weather price → 0/1 as the day's
  high is revealed, so a late "close" is hindsight); the HONEST λ is at the fairest tradeable lead with
  ≥50% coverage.
- **realizable ask** (bar 4): in-sample there is NO captured executable ask (0 rows pre-07-12). Bar 4 is
  therefore reported as (a) at-fire mid net of the CORRECT fee `shares×rate×p×(1−p)` with **rate=0.05**
  (weather θ; NOT the stale 0.03), the realizable proxy; plus (b) the real `entry_ask` on 07-12+ labelled
  FORWARD/STALLED. The executable-ask spread on thin weather books stays the acknowledged forward unknown.

## 3. Clustering & CIs (FROZEN)

Bootstrap **clustered on the resolution DAY** (cross-city same-day temperature is correlated — a heat
dome resolves ~20 cities together). 2000+ draws, one-sided 95% lower bound. Day-clustering is
conservative (also lumps weather-independent global cities into one cluster).

## 4. The four bars & pass thresholds (FROZEN — belief-blind)

1. **Walk-forward positive.** Resolution-day-ordered expanding-window folds (≥3 if days allow); net-of-fee
   (rate 0.05) at-fire-mid ROI-on-turnover, day-clustered; **pooled CI lower bound > 0** AND latest fold
   not materially negative. Calendar-blocked if <3 usable day-blocks → PARTIAL, never PASS.
2. **λ CI lower bound > 0 (the crux).** λ = day-clustered mean(CLV)/mean(surplus), CLV = close−entry,
   surplus = won−entry, at the fairest tradeable horizon with ≥50% coverage; market-clustered bootstrap
   CI. **PASS iff λ CI LB > 0 AND CLV CI LB > 0 at that horizon.** λ≈0 = variance premium = FAIL.
   Report coverage %.
3. **Brier-beat OOS.** Walk-forward: does the sharp converged price (sharp_px) predict `won` with a
   LOWER Brier than the blind at-fire mid, out of time? **PASS iff sharp Brier < blind Brier pooled OOS.**
   (For a fixed-rule selection there is no distinct model probability; the sharp-vs-blind price forecast
   is the honest analog of "model beats market price.")
4. **Realizable at the ask, official settlement, corrected fee.** Weather is intl-only ⇒ official label =
   Polymarket CLOB `outcome_won`. **PASS iff day-clustered ROI-on-turnover CI LB > 0 at the realizable
   entry with fee rate 0.05.** In-sample: at-fire mid − fee(0.05). A positive POINT on <20 day-clusters
   or with λ-null is labelled PARTIAL/fragile, never PASS.

## 5. Decision (FROZEN)

- **CERTIFIED (size)** iff ALL FOUR bars PASS (not PARTIAL). Then propose ⅛-Kelly-capped sizing per the
  existing risk_gate ladder ($50/$100/$250).
- **NOT CERTIFIED** otherwise: name the single binding bar, and state whether it is power-limited (accrue
  forward) or a confirmed null (kill). A fragile pass (insignificant latest fold, <50% coverage, <20
  day-clusters) is labelled **fragile**, never PASS. This gates real money — honesty over optimism.

## 6. Guardrails (unchanged)

Paper-only; reads `harvest_fills`/`trader_fills`/`consensus_signals` SELECT-only; writes only under
`reports/` on this branch; no `.env` edits; champion + every incumbent arm byte-identical; cost-zero (no
`ANTHROPIC_API_KEY`, no child `claude`); `main` never advanced; the active `wt/evergreen-cert` worktree
never touched.
