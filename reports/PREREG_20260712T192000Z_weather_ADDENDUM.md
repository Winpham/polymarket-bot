# PRE-REGISTRATION ADDENDUM — Weather arm (`weather_fav` / `weather_fav_liq`)

**Frozen:** 2026-07-12T19:20:00Z (UTC). **Branch:** `feat/weather-deepen`. **Amends**
`PREREG_20260712T052717Z_weather.md` by **ADDING floors ONLY — nothing below is loosened, and every
original floor (§3 volume ≥20 day-clusters, ≥2 disjoint FORWARD weeks, §4 `selection_null` p≤0.01 +
skill-over-blind, LODO-by-week, Bonferroni, §5 champion correlation, §7 kill condition) STANDS
UNCHANGED.** Paper-only; promotes nothing; arms nothing; the arm's code is BYTE-IDENTICAL (this run
changed **no** Rust, **no** migration, **no** `.env`, **no** compose — verified `git diff main...HEAD`).

Written **before** any forward `entry_ask` week has accrued, so it is belief-blind with respect to the
forward record it will judge.

---

## A. Why this addendum exists

The Weather Deepen run (WS1–WS4, `WEATHER-DEEPEN-FINDINGS.md`) found **three things the original gate
did not anticipate**, each of which makes the gate STRICTER:

1. **The at-fire-mid basis is OPTIMISTIC — it is not a copier's price.** The CLOB-at-`ts0` mid sits
   **1.65¢ BELOW what the sharps actually paid** (mean `atfire − sharp_fill` = −0.0165, n=860), while
   the WS1-measured executable `entry_ask` is **+1.87¢ ABOVE the sharp fill**. A copier therefore pays
   **≈3.5¢ more** than any mid-basis number implies. (The original in-sample `_blind`
   `initial_mean_price` basis was worse still — **lag-contaminated**: 424/433 mids were captured >30 min
   late, often days, landing near resolution.)
2. **The edge is a mid-favorite PRICE-BAND property, NOT a consensus/copy skill.** On the corrected
   basis the `selection_null` **FAILS (p≈0.5)**: the ≥3-backer consensus is indistinguishable from a
   single-sharp weather favorite at the same (band × day). Independently (WS2), discovered weather
   specialists' pooled skill **over the blind band** on a disjoint test week is only **+2.1pp** — ~79%
   of their apparent edge is just the blind band — and that residual is selected-on-train out of 1,507
   screened (not Bonferroni-significant).
3. **SIZE is unproven.** `weather_fav_liq` (the ≥$1k-liquidity twin) has captured **0**. Weather books
   are thin.

At the **realizable** copier price the refined cell does clear the champion's floor — `weather_fav`
0.71–0.90 LB **+7.9%** (LODO held-out week **+6.5%**) vs the champion's **+5.6%** — but that number
rests on an ask premium measured from 38 **deep-chalk-skewed** captures, so it is a *promising estimate*,
not a certification. The floors below close exactly those gaps.

---

## B. ADDED floors (ALL required, on top of the original gate)

**B1 — REALIZABLE BASIS IS MANDATORY (supersedes any mid-basis reading).**
θ is computed **only** at the captured executable `entry_ask`. The at-fire mid and the sharps' own fill
are **PROXY / CEILING diagnostics** and may **never** certify. A pick with no captured `entry_ask` is
EXCLUDED from θ (unchanged from §2) — and every reported θ must state its `entry_ask` **coverage %**.

**B2 — BAND-SPECIFIC SPREAD FLOOR (new).**
The executable ask premium must be measured **ON the 0.71–0.90 certification band**, from **≥ 100
captured `entry_ask` signals whose `entry_ask` lies in 0.71–0.90**, across **≥ 2 disjoint weeks**. The
existing 38-capture estimate (avg ask 0.912 — deep chalk) does **NOT** certify the cert band; mid-priced
weather books may be thinner and the spread wider. Until B2 is met, θ on the cert band reads
**INDETERMINATE — SPREAD UNMEASURED**, regardless of point value.

**B3 — BEAT-THE-BLIND-BAND FLOOR (new, decisive).**
Because the consensus null fails, the arm must justify existing at all: at the realizable `entry_ask`,
`weather_fav`'s θ must **exceed the θ of a BLIND mid-favorite weather rule** (buy every 0.71–0.90
weather favorite, no consensus requirement) on the **same day-clusters**, with a cluster-robust
one-sided 95% LB on the **difference** that is **> 0**. If the consensus arm does **not** beat the blind
band, the honest implementation is the **blind band rule**, and `weather_fav` as a *consensus* arm is
RETIRED (the band rule would then need its own prereg + forward gate — it is NOT auto-promoted).

**B4 — SIZE / FILLABILITY FLOOR (new).**
`weather_fav_liq` (≥$1k liquidity) must capture **≥ 20** signals with a resolved outcome, and the
realizable θ measured on that liquid subset must be **> 0**. A fat % on unfillable size is not a
strategy: if the edge exists **only** where the book cannot absorb a real stake, weather is
**NOT BANKABLE** and the arm is retired regardless of the headline LB.

**B5 — ENTRY-TIMING GUARD (new).**
The at-fire mid is reconstructed at `ts0` = **a sharp's own first-buy time**. If sharps systematically
buy transient dips, any mid-anchored number is contaminated by entry-timing selection. Forward θ at the
captured `entry_ask` is immune (it is OUR price at OUR time) — so **no mid-anchored or `ts0`-anchored
number may be used for certification**, only for exploration.

---

## C. Decision (frozen, replaces §6's PASS clause by ADDING conditions)

- **PASS** requires **ALL** of: the original §3+§4+§5 floors **AND** B1–B4. (B5 is a
  construction constraint on every θ.) A PASS earns a **deliberate human promotion review**, never an
  automatic arm.
- **FAIL / RETIRE** on any of: realizable θ LB ≤ 0 at the captured ask · B3 unmet (the arm does not beat
  the blind band) · B4 unmet (edge only on unfillable size) · the original §7 kill conditions.
- **INDETERMINATE** while B2/B4 coverage is unmet — the correct and expected reading for the next
  several weeks. Weather's evergreen daily flow means this resolves in weeks, not a season.

## D. Known BLOCKER to forward accrual (reported, NOT fixed here)

Forward certification is currently **throttled by a resolution-pipeline defect**, reported for a
separate, coordinated run (it touches `trader_fills` resolution, which `feat/maker-copy-g3` owns; this
run changed no pipeline code):

> `Postgres::trader_fill_unresolved_conditions` selects unresolved conditions **`ORDER BY MIN(ts)`
> (oldest-first FIFO)**, capped at `TRADER_FILLS_RESOLVE_PER_CYCLE = 200` per housekeeping cycle,
> against a backlog of **~42,000 unresolved conditions**. Recent weather is therefore **head-of-line
> blocked** behind ancient (often permanently unresolvable) conditions: week-2 weather (july 6–12) had
> **~648 converged picks with only ~45 graded**. The `_blind` at-fire-mid snapshot lagged too (11/557).

**Impact on this gate:** the DB will not grade forward weather weeks promptly, so the frozen gate cannot
be evaluated on schedule by the normal instruments. **Mitigation used here (read-only, no pipeline
change):** `scripts/weather_clob.py` grades outcomes + reconstructs mids directly from the public CLOB,
bounded to weather conditions. **Recommended fix (separate run, human decision):** prioritise recent /
recently-closed conditions in the resolver (e.g. newest-first or a dual lane), and/or negative-cache
permanently-unresolvable conditions so they stop occupying the 200/cycle budget. **Not attempted here**
per the run's guardrails.

## E. Guardrails (unchanged)

Paper-only; arms nothing; real-money eligibility unchanged; `weather_fav`/`weather_fav_liq`
`alerting=false`, default-off (`CONSENSUS_WEATHER_ARM`); **no `.env` ARMING edits**; champion `favorite`
+ every incumbent arm + `ConsensusParams::default` **byte-identical** (verified: this run changed no
Rust); cost-zero; DB read-only except the bot's normal accrual writes; new ingestion **bounded to
weather markets** (CLOB `/markets`, `/prices-history`; data-api `/trades`), cached, no global poll.
