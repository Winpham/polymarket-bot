# Evergreen Certification — weather_fav through the exact 4-bar gauntlet that killed collapse

**Branch `feat/evergreen-cert` (off `feat/confidence-forensics`, a strict superset of `main`: D4 clean
`entry_ask` capture + the collapse gauntlet tooling the brief tells me to reuse). Paper / read-only.
No order placed, ever. No API key. Run 2026-07-15.**

---

## VERDICT (up front)

**NOT CERTIFIED. Weather clears NONE of the four bars as a bankable information edge. λ — computed for
the first time in this project's history — is ≈0 (CLV never turns positive at any honest horizon), the
same disease that read λ=0 on collapse and λ-indeterminate on the champion. The residual +3.4% at the
realizable ask (which the corrected fee keeps alive) is a structural favourite-longshot BAND premium,
not forecast selection: a truly-blind favourite-band pool harvests +5.3% on its own, and the sharp
apparatus adds only one-day variance. Do not size it (k=0). It is verdict C wearing a favourite's
clothes — exactly what the run was sent to find out.**

Two honest qualifiers, neither a rescue:
1. Unlike collapse (NEGATIVE on official US settlement), weather is **positive** at the realizable ask
   on official settlement (+3.4%, corrected fee). But that number is (a) uncertifiable — it rests on
   **2 resolution-day clusters**, and (b) λ-null, so it is the band's structural premium, not alpha.
2. The one genuine advance: the historical **price source is now VALIDATED** (MAE 1.5¢ vs the arm's real
   captured mid), so the MIRAGE null could finally be run on a trustworthy basis. It resolved AGAINST
   the sharps.

A well-evidenced NO was the deliverable. This is it.

---

## §1 — DATA CENSUS: what can be tested today vs what is calendar-blocked

The decisive census finding is that the `weather_fav` **arm** (the only source of clean, decision-time
`entry_ask`) began capturing on **2026-07-12** and has **3 detection days / 2 clean resolution days**.
The "July 2–8" and "W27+W28 two disjoint weeks" of the prior reports came from a *reconstruction* off
`trader_fills`, not from the arm — and the arm's own clean data is a single consecutive block.

| # | question | answer (measured 2026-07-15) |
|---|---|---|
| arm span | detection days of `weather_fav` | **07-12, 07-13, 07-14** (158 / 261 / 224 signals) |
| resolved | resolved arm signals | 371 total; **203 with a captured `entry_ask_mid`** (validatable) |
| clean days | distinct **resolution days** with `entry_ask_mid` | **2** (07-13: 88 · 07-14: 115) |
| cert band | band 0.71–0.90, resolved, with ask | **108 signals across 2 days** |
| p50 ask-lag | decision-time lag (W29) | **15.3 min** (W28 33.8) — near the <15min clean-basis gate |
| **λ close price** | `signal_price_trajectory` coverage for weather_fav | **0%** — no captured pre-resolution mid exists in the DB |
| degen check | `last_market_price` non-degenerate coverage | **0/371** (avg 0.941, all post-resolution hindsight) |
| official label | do weather markets join the US DMR (`us_daily_market_report`)? | **0 / 643** — weather is **intl-only** |

**What this scopes (honest):**
- **Bar #1 (≥3 expanding walk-forward folds): CALENDAR-BLOCKED.** The arm has 2 clean resolution days,
  consecutive, all mid-July. No disjoint weeks exist. Mark **PARTIAL**, never passed.
- **Bar #2 (λ): the DB route is dead** — trajectory coverage 0%. The ONLY close-price source is the
  public CLOB `prices-history` endpoint; per hard rule 4 it had to be validated first (see §3.1). It was
  — so λ is answerable, on **2 day-clusters** (power-starved).
- **Bar #4 (official settlement): answerable now.** Weather is intl-only, so the official label IS the
  Polymarket CLOB resolution `outcome_won` (highest-temperature markets settle to the observed/NOAA high
  — there is no separate DMR and no DMR gap). `entry_ask` is captured on 193 band-eligible signals.

---

## §2 — THE FOUR-BAR SCORECARD for `weather_fav` (band 0.71–0.90)

| # | bar | metric | value | verdict |
|---|-----|--------|-------|---------|
| 1 | Walk-forward-stable (≥3 expanding folds, no fold materially negative) | disjoint weeks of clean arm data | **2 consecutive resolution days**, 0 disjoint weeks | **PARTIAL — calendar-blocked** (cannot run; not passed) |
| 2 | **Information, not variance — λ CI LB > 0 @ ≥50% cov** | λ = CLV/surplus, day-clustered | validated source; **λ ≈ 0.00 (last-tick, CI [−0.74,+0.36]); −0.16 @ −24h; −0.96 @ −12h.** CLV point ≈ **+0.0002** (never positive); only **2 day-clusters** | **FAIL** (λ CI LB not >0; the market never confirms the picks) |
| 3 | Beats the market out of time (model Brier < market Brier, pooled OOS) | independent model vs market mid | **ill-posed** — the arm emits no probability distinct from the entry mid; the "does selection beat the band" substitute (§3) reads **NO** | **N/A → not passed** |
| 4 | Positive at the realizable ask, official settlement, corrected cost | day-clustered ROI-on-turnover at real `entry_ask` | **+3.39%** (point), win 0.87, mean ask 0.83, corrected fee 0.36¢ — but **2 day-clusters** ⇒ no credible LB; λ-null ⇒ structural | **PARTIAL** (positive point, uncertifiable; structural not alpha) |

**Weather clears 0 of 4.** The decisive bar is #2, and it reads the same as every prior arm.
`reports/clv_lambda_weather.json` holds the full horizon trajectory; the headline is: **on the honest
mid-to-mid basis, CLV is ≈0 at the last tick and NEGATIVE at every controlled pre-resolution horizon** —
the entire realized surplus (won − entry ≈ +6%) is *residual* (won − close), i.e. realized-outcome
variance / static premium, with **nothing** confirmed by the market before resolution.

**Why weather CANNOT clear bar #2 even in principle (the structural point).** A weather market's price
converges to 0/1 as the day's high temperature is *revealed* through the resolution day. Any "the market
moved toward our pick" measured late in the day is the answer leaking in, not a forecast. Measured at a
fair pre-resolution lead (−12h/−24h, before the temperature is known) the market has moved *away* from
the picks (CLV negative). So there is no window in which the market anticipatorily confirms the sharps'
weather selection. This is not a power problem you can fix by waiting — it is the nature of a
same-day-revealed settlement. (It mirrors the phase-9 finalhour correction: λ measured 5 min from
resolution is hindsight; at a tradeable lead it collapses.)

---

## §3 — THE MIRAGE, RESOLVED: do we need a sharp at all? **No — the band does the work.**

### 3.1 Price source — **VALIDATED** (the gate the 07-12 run failed)
The prior `atfire_recon` read MAE 22¢ and was rejected. Root cause: it validated against the
**structurally-absent `_blind` weather mid** (`_blind` never covered the weather book). The arm has since
captured **203 real `entry_ask_mid`** values — the correct target. Reconstructing the CLOB mid at each
signal's capture instant and comparing:

> **MAE 1.52¢ · bias +0.05¢ · corr 0.984** vs captured `entry_ask_mid` (n=108).
> Acceptance (MAE≤3¢, |bias|≤1¢, corr≥0.90) **MET.** The token-index mapping was correct all along; the
> 22¢ was a validation-target bug, not a price bug. The MIRAGE null can now be run on a trusted basis.

### 3.2 Blind favourite-band pool vs sharp-selected — head-to-head, neutral reference, official settlement
Every weather (highest-temperature) market-outcome any tracked trader touched, resolving on the 2 clean
days, priced at a **neutral res−24h reference** (not entry-anchored), settled official, band 0.71–0.90,
day-clustered:

| pool | n | win | mean mid | ROI @ neutral mid | 07-13 | 07-14 |
|---|---|---|---|---|---|---|
| **blind** favourite-band | 52 | 0.846 | 0.817 | **+5.27%** | +7.6% | +3.0% |
| **sharp-selected** weather_fav | 70 | 0.886 | 0.811 | **+8.39%** | +4.6% | +12.2% |
| Δ (sharp − blind) | | | | **+3.12pp** | **−3.0pp** | +9.2pp |

**Read:** the blind favourite band already earns **+5.3%** with *no sharp, no copy apparatus*. The sharp's
apparent +3.1pp premium is **one-day variance** — on 07-13 the blind pool BEATS the sharp (+7.6% vs
+4.6%); the sharp only "wins" on 07-14. And λ (§2) confirms none of the sharp margin is CLV-bearing.
**Conclusion: the edge is the mid-favourite BAND (structural favourite-longshot premium), not forecast
selection. We do not need a sharp.** This is precisely the mechanism the brief feared would lose real
money once costs and disjoint weeks are honest — the sharp selection is decorative.

(The prior in-sample `selection_null` p=0.0005 is not contradicted so much as re-interpreted: it measured
sharp-vs-random on **realized outcomes** over the same 2 favourable days that inflate every number here;
λ — the one test that does not need favourable realized outcomes — says there is no information.)

---

## §4 — COST RE-NET (corrected fee vs the phantom 3%)

The corrected Polymarket taker fee `FEE_RATE·p·(1−p)` ≈ **0.36¢** at the favourite band, vs the old flat
**3%** (3¢) some verdicts charged. Re-netting the arm's real captured ask, day-clustered:

| band | ROI @ ask, **corrected fee** | ROI @ ask, **old 3%** | ROI @ mid (gross) |
|---|---|---|---|
| 0.71–0.90 | **+3.39%** | +0.90% | +5.95% |
| 0.71–0.98 | +2.67% | −0.01% | +4.60% |
| 0.90–0.98 (deep chalk) | +2.01% | −0.90% | +3.20% |

The cost correction **helps weather** exactly as predicted — the phantom 3% had pushed the wider and
deep-chalk bands to ~0/negative; the real fee leaves them positive. **But λ gates:** a cheaper fee only
re-scales a premium the information test says is variance. It does not manufacture an edge. (Note also
the deep-chalk 0.90–0.98 band is now marginally positive after the corrected fee — but it is the
efficiently-priced win-rate-trap band with the least selection content; do not read its survival as
signal.)

---

## §5 — SECOND-EVERGREEN SWEEP (bounded): no capturable second arm exists

- **`weather_low_fav`** (lowest-temperature): already RETIRED — fails LODO-by-week (min-fold LB −35.9%);
  not re-opened (re-opening requires an a-priori mechanism, not a rescan).
- **crypto up/down, precip, wind:** structurally excluded — 5-minute crypto is uncopyable by
  construction; precip/wind ≈ 0. No favourite band to harvest.
- **Every intl evergreen family inherits weather's two fatal data gaps:** no `signal_price_trajectory`
  (⇒ λ unmeasurable without the CLOB-reconstruction build) and same-day-revealed settlement (⇒ CLV is
  hindsight). Any intl daily-settlement family will hit the identical wall.
- **The one genuine λ>0 lead — final-hour favourite late-convergence** (US, λ downgraded to 0.1–0.44 in
  the phase-9 audit) — generalizes across tennis/ITF/esports but is **NOT capturable** without an
  external live game-clock feed: every live-knowable trigger (venue `endDate` is ~4h off actual
  resolution, `gameStartTime` +2h, price-only features) reads negative. esports has a free bo3.gg feed;
  that is the only cost-zero path, and it is a data-acquisition + forward-test project, not an arm that
  certifies today. **Do not build a paid-feed dependency without Tue.**

**Answer to "is there another evergreen arm?": on this evidence, no.**

---

## §6 — GO-LIVE PATH: not unlocked (weather did not clear §2)

Per the run's own rule, the concrete go-live path (a `weather_forward.py` fork, pre-registered forward
bar, risk limits) is delivered **only if §2 passes**. It did not. **No go-live artifact is produced.**
The honest NO is added to the confidence ledger alongside champion (λ indeterminate) and collapse (λ=0):

> **weather_fav — verdict C: a favourite-longshot / variance premium, not information. λ ≈ 0 (CLV never
> positive at a fair horizon), positive at the realizable ask only as a structural band premium a blind
> bet harvests without a sharp, and uncertifiable on 2 resolution-day clusters. Do not size (k=0).**

What *would* change the verdict (each labelled human vs calendar):
- **λ turning positive on disjoint weeks** — CALENDAR-BOUND and structurally unlikely (same-day
  temperature revelation makes CLV hindsight); weeks of forward accrual would test it, but the mechanism
  argues it cannot clear bar #2. This is the honest blocker, and it is probably permanent.
- Nothing here is a human/ToS/wiring blocker, because there is no certified number to trade.

---

## Artifacts (all on `feat/evergreen-cert`, read-only)
- `reports/clv_lambda_weather.json` — **the λ number, computed for the first time** (full horizon
  trajectory, both entry bases, validation block). The single most important output.
- `reports/weather_bar4_net.json` — bar #4 realizable net-EV + §4 cost re-net.
- `reports/weather_blind_pool.json` — §3.2 MIRAGE head-to-head (blind band vs sharp-selected).
- `scripts/weather_clv_lambda.py`, `scripts/weather_bar4_net.py`, `scripts/weather_blind_pool.py`
  (each `--selftest`/idempotent; price caches under `reports/cache_weather_prices/`,
  `reports/cache_blind_prices/`). Extends `clv_lambda.py` + `atfire_recon.py`; no incumbent touched;
  nothing armed; no order path.
