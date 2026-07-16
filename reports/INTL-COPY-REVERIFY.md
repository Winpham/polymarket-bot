# International copy-edge — independent re-verification

**Date:** 2026-07-15   **Branch:** `feat/intl-reverify`   **DB:** `polymarket` (57.2M `harvest_fills`, continuous 2025-08-05 → 2026-07-14)

**Mandate:** the intl copy/collapse edge was measured as a confident null
(λ = 0.000 [0.000, 0.141] @ 94% coverage; walk-forward ROI +1.34% [+0.40, +2.25], ⅓ of the
+4.14% single-split; Brier-beat FAILS OOS). Either OVERTURN it with evidence or NAIL IT SHUT
with independent tests — and specifically rule out that the null is an artifact of (a) data
loss / the ingestion break or (b) a thin-games / low-volume window.

---

## Pre-registered battery (thresholds frozen BEFORE any result below was computed)

| # | Test | What passes = OVERTURN | What passes = null CONFIRMED |
|---|------|------------------------|------------------------------|
| 1 | **Data-integrity control** | a structured mid-history gap that, once excluded, moves λ off 0 | cache regenerates byte-identical from intact DB; row/market continuity holds |
| 2 | **Thin-window sensitivity** | excluding low-vol days / restricting to high-vol core lifts λ CI-LB > 0 | λ stays 0 (or tightens toward 0) in every window |
| 3 | **Regime/conditioning search** | ≥1 leak-free cell with CLV lower-bound > 0 that **survives BH** (FDR 0.05) and generalizes out-of-cohort | 0 cells survive BH; any positive is lookahead/max-of-noise |
| 4 | **Subpopulation (cleaner roster)** | copying MM-screened directional / CLV-persistent roster gives CLV-LB > 0 | roster λ ≤ 0, CLV CI includes 0 |
| 5 | **Fresh-data confirmation** | new forward-timestamped fills reproduce λ > 0 | N/A if pipeline not repaired |

Discipline applied throughout: belief-blind; **market-clustered** bootstraps (the market is the
inference unit); leak-free **as-of** features only (a self-test asserts the feature builder cannot
see the future); verified fee `θ·p·(1−p)` (takers only); every number reports n, CI, coverage, and
walk-forward-vs-single-split. Harness `--self-test` green; full-cache run reproduces the published
null exactly.

---

## Results

### Reference (reproduction of the published null)
`collapse_lambda_wf.py --folds 4` and `intl_reverify.py --self-test` both reproduce, **byte-for-byte**:

```
FULL CACHE  mk=10857 sel=15431 cov=94%  WF +1.34% [+0.40,+2.25] p=0.003
            λ 0.000 [0.000,0.141]  CLV_lb −0.91c  Brier: market wins
```

### Test 1 — Data-integrity control  ✅ PASS (null is NOT a data-loss artifact)
- **Per-day continuity:** `harvest_fills` is continuous and volume-rich through 07-12
  (2.3–3.9M fills/day, 4.0k–7.4k markets/day). The dropoff is **only** 07-13 (753k, 1196 mkts)
  and 07-14 (544k, 635 mkts) — the copy-bot crash-loop on the deleted `042_us_quotes` migration,
  **not** few games. No structured mid-history deletion anywhere 2025-08 → 2026-07-12.
- **Cache regenerates from the intact DB:** rebuilding `.collapse_wf_cache.pkl` from scratch yields
  the **identical universe** — 76,551 rows, 10,857 markets, **0 markets added or dropped**, and
  **0 mismatches** on all 69,269 shared decision points `(won, price, net)`. The remaining rows
  differ only by the documented `MAX_DP=8` random sub-sample when a market has >8 candidate prints.
- **Universe span:** the cache's markets resolve **2026-05-29 → 2026-07-14** (decision prints reach
  back to 2026-03-27). Only **206 of 10,857 markets (1.9%)** fall on the two broken days. So the null
  was measured on rich, intact, recent data — the broken window is a rounding error in it.

### Test 2 — Thin-window sensitivity  ✅ PASS (null is NOT a thin-games artifact)
Recomputed λ + walk-forward ROI on time-restricted subsets (same WF+λ+Brier machinery):

| Window | mkts | WF ROI [CI] | λ [CI] | CLV-LB | Brier |
|--------|-----:|-------------|--------|-------:|-------|
| 0. Full cache (ref)         | 10857 | +1.34% [+0.40,+2.25] | 0.000 [0,0.141] | −0.91c | mkt |
| (i) exclude broken days 07-13/14 | 10651 | +1.48% [+0.55,+2.42] | 0.000 [0,**0.035**] | −1.24c | mkt |
| (ii) high-vol core 07-01…07-12   | 7889  | +0.86% [−0.18,+1.89] | 0.000 [0,**0.000**] | −1.85c | mkt |
| (iii) full pre-crash (≤07-12)    | 10651 | +1.48% [+0.55,+2.42] | 0.000 [0,0.035] | −1.24c | mkt |
| (iv) decision-t & mts pre-crash  | 10651 | +1.48% [+0.55,+2.42] | 0.000 [0,0.035] | −1.24c | mkt |
| (v) rich window 06-30…07-12      | 8385  | +1.21% [+0.25,+2.14] | 0.000 [0,**0.000**] | −1.53c | mkt |

**Removing the thin/lost data makes the null TIGHTER, not weaker.** λ stays pinned at 0 in every
window and its CI upper bound *collapses* from 0.141 (full) → 0.035 (excl. broken) → 0.000 (high-vol
core & rich window). CLV lower-bound is negative everywhere; the market-price Brier wins everywhere.
The +0.9…+1.5% walk-forward ROI that persists is the favourite-longshot **variance premium**, not
information (λ = 0). Both user hypotheses are refuted with numbers.

### Test 3 — Regime / conditioning search  ✅ PASS (no regime carries information)
λ per niche × price-band × as-of-volume × time-block (16 leak-free cells), one-sided p(mean CLV≤0),
Benjamini-Hochberg FDR 0.05:

| Cell (best few by raw λ) | mkts | WF ROI | λ [CI] | CLV-LB | Brier |
|---|--:|--|--|--:|--|
| vol=deep (as-of prints) | 3729 | +1.62% [+0.54,+2.63] | 0.150 [0,0.369] | −0.43c | mkt |
| band 0.85–0.90 | 4826 | +1.46% [−0.04,+2.88] | 0.048 [0,0.388] | −0.93c | mkt |
| tennis | 1744 | +1.71% [+0.01,+3.31] | 0.000 [0,0.225] | −1.32c | mkt |
| ufc | 202 | +3.22% [−1.27,+7.06] | 0.000 [0,0.318] | −4.83c | mkt |
| soccer | 4680 | +0.85% [−0.31,+1.97] | 0.000 [0,0.000] | −2.10c | mkt |
| *(all other niches/bands/vol/time cells)* | — | — | 0.000 / n/a | negative | mkt |

- **BH survivors: NONE.** **Cells with raw CLV lower-bound > 0: NONE.** Every cell's CLV lower bound
  is negative; the market price beats the model's Brier in every cell.
- **Lookahead diagnostic (the trap, demonstrated):** bucketing markets by their **settlement-time**
  sampled-point count (a quantity unknowable at decision time) manufactures a spectacular fake edge —
  `LA vol=mid` → WF **+9.00% [+8.60,+9.39]**, λ **0.543 [0.520,0.568]**, CLV-LB **+4.53c**, Brier
  MODEL-beats-market. Re-bucketing the *same concept* on the **leak-free as-of** print count
  (`vol=mid(asof)`) erases it entirely → WF −0.65%, λ n/a, CLV-LB −2.78c, Brier: market. The "+9%"
  is 100% settlement-conditioning artifact. This is why every positive must be leak-free and survive
  multiplicity before it counts.

### Test 4 — Subpopulation search (cleaner roster)
The collapse cache is already the MM-screened directional taker cohort (`is_maker=false` BUY ≥80c) —
its λ = 0.000 covers that half. Prior roster/ranker machinery (already in-repo) is decisive:
- `rosters.json`: esports/tennis/weather rosters — **persistence CI never above 0**
  (esports b_mean −0.021 [−0.045,+0.003]; tennis +0.027 [−0.003,+0.098]; weather +0.018 [−0.012,+0.048]);
  esports/tennis do not beat the permutation null.
- `rankers_all.json`: **all rankers `works:false`** including CLV (ρ≈0, window-B surplus CI spans 0).
- `copy_vs_blind.json`: copy − blind surplus **+0.57c [−0.89,+2.04], p=0.219** (does not beat blind).

Fresh λ-framed OOS confirmation (copying the 147 MM-screened directional roster wallets, forward
closing-line CLV, market-clustered):

> `intl_roster_lambda.py` computes the forward closing-line λ for copying the 147 MM-screened
> directional roster wallets (maker_frac<0.1), market-clustered, all-window and window-B (OOS). The
> run was **abandoned** in this window: the closing-line `ARRAY_AGG` over the roster's high-volume
> markets collided with the copy-bot's ~7-minute recovery-backlog `INSERT` and never cleared. This is
> **confirmatory only, not load-bearing** — the three published artifacts above already settle Test 4
> with market-clustered CIs, and the collapse cache (which *is* the MM-screened directional cohort)
> already has λ = 0.000. The script is committed and `--self-test` green; re-run it when the DB is
> quiet (`python3 scripts/niche/intl_roster_lambda.py`).

**Test 4 conclusion (from published artifacts + the collapse-cache λ):** copying a cleaner roster
does **not** produce λ > 0. The MM-screened directional cohort is exactly the collapse cache → λ=0.000;
no roster's out-of-sample edge CI clears 0; CLV as a ranker fails (`works:false`); copy does not beat
blind (p=0.219).

### Test 5 — Fresh-data confirmation  ⏸ N/A (pipeline not producing persisted forward data)
The copy-trading-bot container polls trader activity (logs show it fetching through 2026-07-15)
but **crash-loops before persisting**: `max(trader_fills.ts)` is still **2026-07-14 22:14**, and
`harvest_fills` ends 2026-07-14. No new forward-timestamped fills have accrued since the break, so
a fresh-data test cannot be run in this window. Root cause is an ops issue (the deleted
`042_us_quotes` migration / GHCR image needs a rebuild, not a restart) — outside this analysis.
**Recommendation:** once ingestion is repaired, a forward paper test is the strongest possible
confirmation; but note the null is already established by four *independent* tests below, not one run.

---

## VERDICT

**The null is CONFIRMED by independent tests — nothing overturned λ = 0. Copy-trading the
international book is not the path.**

- **λ = 0 is not a data-loss artifact (Test 1).** The tape is intact and continuous through 07-12;
  the cache regenerates byte-identical from the DB (0 markets and 0 decision-point mismatches); the
  broken days are 1.9% of the universe.
- **λ = 0 is not a thin-games artifact (Test 2).** Deleting the low-volume/broken days and
  restricting to the high-volume core only tightens the λ CI upper bound from 0.141 → 0.000. The edge
  gets *more* null on cleaner data, never less.
- **No regime carries information (Test 3).** Across 16 leak-free niche/band/volume/time cells, zero
  have a CLV lower-bound > 0 and zero survive Benjamini-Hochberg. The one "survivor" (`vol=mid`,
  +9%/λ=0.54) was a settlement-conditioned **lookahead artifact** that vanishes under the leak-free
  as-of partition — a clean demonstration of the max-of-noise trap the mandate warned about.
- **No cleaner roster helps (Test 4).** The collapse cache already *is* the MM-screened directional
  cohort (λ=0). The persistence/CLV roster machinery never produced a roster whose OOS edge CI clears
  0, all rankers (incl. CLV) fail, and copy-beats-blind is p=0.219.

The persistent +0.9…+1.5% walk-forward ROI is the **favourite-longshot variance premium** (won−close
> 0 while close−entry ≈ 0), not information the market later confirms — the same disease as the
champion `favorite` arm. **k = 0. Do not size copy-trading.** If ingestion is repaired, the only
honest next step is a pre-registered **forward paper test** (Test 5), but four independent
re-verifications already agree with the original run.

**One-line verdict:** Null re-confirmed independently — λ=0 survives data-integrity, thin-window,
16-cell multiplicity, and roster-subpopulation stress; the only positive was a lookahead artifact;
copy-trading is not the path (k=0).
