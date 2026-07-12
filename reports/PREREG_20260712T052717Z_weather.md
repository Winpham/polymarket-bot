# PRE-REGISTRATION — Weather (daily-temperature) shadow arm, forward gate

**Frozen:** 2026-07-12T05:27:17Z (UTC). **Branch:** `feat/weather-fav`. **Paper-only, read-only
effect on the record, promotes nothing, arms nothing, real-money eligibility UNCHANGED. Every
incumbent arm + the champion `favorite` + `ConsensusParams::default` BYTE-IDENTICAL (verified: 175
insertions, 0 deletions — purely additive).** Belief-blind: every rule/threshold/verdict below is
frozen HERE, before any forward weather data accrues. Inherits the audited conventions: match/day
super-key clustering, small-cluster t(G−1) cluster-robust LBs, `selection_null`, the `_blind`
softness/skill split, corrected fee `0.03·p·(1−p)`.

## 0. Why this arm exists (what the backtest settled — and could NOT)

Daily weather markets ("highest-temperature-in-{city}", ~20 cities/day, year-round, tournament-
independent) are the most EVERGREEN venue we track. The replay backtest (vote atoms logged from day
one) found: the wider trader universe (rank ≤250) converges on weather favorites at **+8.4%**
directional edge vs **+2.1%** for the blind weather favorite ⇒ **≈+6pt belief-blind skill**, on ~178
city-day observations. **But two things the backtest could NOT resolve, by construction:**

1. **Copyability is UNMEASURABLE from history.** The live `favorite` arm fired on weather **0** times
   (its forecast-specialist backers sit at rank 41–250, past the rank-40 gate), and there are **0**
   captured `entry_ask` rows and **0** `clob_price_tape` rows for any weather market. So the +8.4% is
   the specialists' OWN fill — we have no data on what a copier would pay. **This arm's sole purpose is
   to START that realizable capture forward.**
2. **Power is thin and correlation-inflated.** Same-day temperature is correlated across cities (a heat
   dome resolves 20 cities "hot favorite" together), so the honest cluster is the **DAY**, not the
   city-day: the 178 collapse to **~7 independent days**. A 7-day directional read is INDETERMINATE —
   the "heat-wave-week" version of the single-tournament trap that killed tennis under LODO.

The arm is default-OFF (`CONSENSUS_WEATHER_ARM=false`); `weather_fav` / `weather_fav_liq` are silent
(`alerting=false`). Nothing promotes. The forward record is the arbiter.

**In-sample refinement (Weather Edge Refinement run, phases 1–3 — `WEATHER-FINDINGS.md`; this is
in-sample, no forward data has accrued, so it legitimately refines the gate below):** on the at-fire
mid (realizable-proxy) basis, day-clustered, the edge is real and copyable (copyability haircut ≈0,
diffuse across 49 cities, top-city share 4.6%). The **0.71–0.90 sub-cell** (dropping the 0.90–0.98
deep-chalk band, which is DEAD — LB −2.1%, no selection skill, the win-rate trap) is markedly stronger:
day-clustered LB **+9.2%**, Bonferroni +7.2%, **passes the forecast-co-reading `selection_null`
(p=0.0065)**, and is **low-correlated with the champion (day-level −0.48)** — a genuine complement
profile. The pooled 0.71–0.98 cell FAILS the null (p=0.0125) because the dead deep-chalk band dilutes
it. **THE decisive limitation: all in-sample weather convergence is ONE consecutive week (july 2–8)**,
so LODO-by-week is impossible and the numbers could be a single early-July weather regime. The forward
gate below is therefore built around a hard ≥2-DISJOINT-WEEKS requirement.

## 1. What accrues forward (enablement)

On merge, the integrator sets `CONSENSUS_WEATHER_ARM=true` (keeping `SOFT_MARKET_RANK_CUTOFF=250`) in
`.env.consensus`. From that instant the cycle scores `weather_fav` / `weather_fav_liq` on the
wider-eligibility daily-temperature book and upserts their signals like any other arm — **capturing
`entry_ask` / `entry_ask_mid` at the first housekeeping pass (the realizable, leak-free entry weather
has never had).** No other behavior changes; every incumbent arm stays byte-identical. Nothing arms
real money or auto-promotes.

**Forward instruments (already built, `--selftest` green):** `scripts/weather_scan.py` (day-clustered
map + dual-basis edge) and `scripts/weather_verdict.py` (the full battery: day-clustered LB,
leave-one-week-out jackknife, forecast-co-reading `selection_null`, Bonferroni, champion correlation).
Re-run them as forward weeks accrue; they read the same `entry_ask`-captured signals the arm produces.
Certification is one command — no new tooling needed to arbitrate the gate.

## 2. The locked objective (identical to the run objective; no re-derivation)

> **θ = cluster-robust one-sided 95% LOWER BOUND of realizable ROI-on-turnover, clustered at the
> resolution DAY** (NOT city-day — cross-city same-day correlation), read at small-cluster t(G−1).
> Realizable entry = the captured `entry_ask` (fee `0.03·p·(1−p)`); a pick with no captured ask is
> EXCLUDED from θ. Win rate and total P&L are DIAGNOSTIC ONLY.

**Primary certification cell = `weather_fav` 0.71–0.90** (a-priori mechanism, frozen: the 0.90–0.98
deep-chalk band earns ~0/$ — the win-rate trap — and adds no selection skill, in-sample LB −2.1% and
it is what breaks the pooled `selection_null`). The arm still CAPTURES the full 0.71–0.98 band (broad
capture is free forward data that confirms whether 0.90–0.98 is really dead); the 0.90–0.98 slice is
tracked separately, NOT part of the primary θ. Forward θ uses ONLY `entry_ask` captured on live
`weather_fav` signals — never the sharps' fill, never mid, never a directional number.

## 3. Floors — INDETERMINATE until ALL met (frozen)

1. **Volume:** ≥ **20** distinct resolution-DAY clusters with a captured `entry_ask` AND resolution.
2. **Deployment:** ≥ **3** weather signals per active day (trivially met if it fires at all — ~20 cities/day).
3. **Duration + ≥2 DISJOINT WEEKS (the decisive floor — the in-sample failure mode):** the day-clusters
   must span ≥ **20 distinct active days** across ≥ **2 disjoint calendar weeks each with ≥ 5
   day-clusters**. The entire in-sample edge was ONE consecutive week (july 2–8); a second disjoint week
   is the minimum that distinguishes a strategy from a single weather regime. Until a second qualifying
   week exists, θ reads **INDETERMINATE — SINGLE WINDOW**, never PASS, regardless of point value.
4. **Disjoint-regime robustness:** θ LB must stay **> 0** under the **leave-one-week-out jackknife** (drop
   the calendar week with the most day-clusters and recompute) — a test that is IMPOSSIBLE today (one week)
   and becomes the gate the moment a second week accrues. An edge that only survives WITH its dominant
   week is that week's streak.

## 4. Belief-blind + skill (frozen, both required)

- **`selection_null`** on the weather-arm selection: p_emp ≤ **0.01**, ≥ **1000** matched draws vs the
  `_blind` weather-favorite universe, matched to the arm's (band × day) profile. This is the guard
  against the two efficiency traps: (a) sharps merely **co-reading the same public forecast** (no
  copyable alpha — a composition artifact), and (b) sharps selecting only **easy, high-confidence
  forecast days** (a selection artifact). If weather-consensus does no better than random weather
  favorites at the same band×day, it certifies to ~0.
- **Skill over blind:** the weather cell's surplus over the `_blind` weather favorite at the same band
  must stay **> 0** on captured entries (the +6pt directional signal must survive at OUR realizable price).
- **Multiple testing:** Bonferroni/BH over the arms scored (weather_fav + weather_fav_liq) — reported.

## 5. Head-to-head (the run's question)

The weather cell is a COMPLEMENT worth promoting only if, over the forward window, its realizable θ LB
(clearing §3+§4) is **> 0** AND it is **low-correlated (|match-day corr| < 0.3) with the champion
`favorite` 0.71–0.98** at the day level (weather resolves independently of sports, so a genuine
complement diversifies the champion rather than re-labeling it). `weather_fav_liq` is scored
identically so the thin-book spread tax is ruled on independently.

## 6. Decision (frozen)

- **PASS** (θ LB > 0 clearing §3+§4, low-correlated with champion, ≥ 6 forward weeks): weather is a
  real, evergreen, copyable complement — earns a deliberate human promotion review, NOT an automatic arm.
- **FAIL / INDETERMINATE** (any floor unmet, LODO-by-week collapses it, selection_null fails ⇒
  forecast-co-reading, or the edge evaporates at the realizable `entry_ask`): weather softness is either
  efficient or un-copyable — a fully valid, money-saving result. Retire the arm.
- The forward record supersedes the directional backtest either way. No goal-seeking.

## 7. Kill condition (frozen)

Retire `weather_fav` / `weather_fav_liq` if, after **≥ 6 forward weeks** with the volume floor met, the
realizable θ LB is **≤ 0** OR fails the leave-one-week-out jackknife OR fails `selection_null` OR the
day-level correlation with the champion is ≥ 0.3 (same bet re-labeled). A dead weather arm is a valid
outcome — do not keep it on hope. Weather's evergreen daily flow means this resolves in weeks, not a season.

## 8. Guardrails (unchanged)

Paper-only; arms nothing; real-money eligibility unchanged; `weather_fav`/`weather_fav_liq`
alerting=false, default-off (`CONSENSUS_WEATHER_ARM`); no `.env` ARMING edits (only the capture flag on
merge); champion `favorite` + every incumbent arm + `ConsensusParams::default` byte-identical (verified
additive-only); cost-zero (no `ANTHROPIC_API_KEY`, no child `claude`); DB read-only except the bot's
normal accrual writes; `clob_price_tape`/`trader_fills` SELECT-only.
