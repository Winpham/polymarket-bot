# weather_fav — 4-bar certification on the HARVEST-TAPE edge window

**Branch `feat/weather-cert` (off the `feat/evergreen-cert` commit, a superset of `main`). Paper /
read-only. No order placed. No API key. `main` never advanced; the active `wt/evergreen-cert` worktree
never touched. Run 2026-07-15. Gate frozen in `PREREG_WEATHER_FAV_4BAR_HARVEST.md` BEFORE any number.**

---

## VERDICT (up front)

**NOT CERTIFIED — do not size (k=0). Binding constraint = Bar 2 (λ) significance + the disjoint-weeks /
day-cluster power floor. BUT the evidence LEANS toward a genuine, power-limited information edge —
materially more favorable than the committed `1c140f1` "verdict C / variance-not-information / probably
permanent." Recommendation: ACCRUE FORWARD (power-limited), do NOT kill.**

This run is an **independent, higher-powered, fully-OFFLINE replication** of the committed cert's crux.
That cert computed λ on **2 consecutive stalled resolution-day clusters (07-13/14)** — the exact window
the brief says to ignore — via a live CLOB fetch, entering at the *arm's* late detection price. This run
computes λ + all four bars on the window where the +7.9% edge actually lives (**9 resolution-day
clusters, july 3–14, ~90% forward-close coverage**), using the `harvest_fills` intl taker tape (the same
source `collapse_lambda_wf.py` uses), entering at the **original consensus-convergence** moment, and with
two adversarial hardenings the committed cert lacked:

1. **Leak-free closes** — every forward close is a print STRICTLY AFTER the convergence `ts0` (the
   decision→resolution gap is large — median 52.6h, p05 27.9h — so res−24h closes are genuinely forward,
   not pre-entry).
2. **Spread-neutral entry** — headline λ/ROI use the first EXECUTED taker BUY print at/after convergence
   (a real ask), not the `_blind` mid, removing the ~½-spread upward bias that inflates a mid-to-ask CLV.

The two results diverge because of **window power (9 vs 2 clusters)** and **entry timing** (convergence
vs the arm's late detection, which eats the CLV) — not a methodology error on either side.

---

## THE 4-BAR SCORECARD — `weather_fav`, primary band 0.71–0.90

(day-clustered bootstrap, 4000 draws, one-sided 95% LB; spread-neutral tape-print entry unless noted;
corrected fee `shares×0.05×p×(1−p)`, NOT the stale flat 0.03)

| # | bar | metric | value | verdict |
|---|-----|--------|-------|---------|
| 1 | **Walk-forward net ROI, CI LB > 0** | day-clustered ROI-on-turnover, 3 expanding folds | pooled **+15.0%** CI **[+6.8%, +20.4%]**, p(≤0)=0.002; folds **+15.6% / +19.8% / +18.3%** (all > 0); one negative day 07-04 (−14.8%) | **PASS — but FRAGILE** (all 9 days are july 3–14, a single regime span; the disjoint-week floor is NOT met — these folds are consecutive-day blocks, not disjoint weeks) |
| 2 | **λ = CLV/surplus, CI LB > 0 @ ≥50% cov (THE CRUX)** | day-clustered, controlled pre-resolution horizons, spread-neutral | λ point **+0.17 … +0.53** (positive at every horizon); CLV **+2.1¢ … +6.6¢**; but **CI LB straddles 0** (p(CLV≤0) ≈ 0.05–0.18); coverage **90%**, 9 days | **INDETERMINATE-BY-POWER — leaning positive** (NOT a clean pass; NOT the confirmed λ≤0 null of `1c140f1`) |
| 3 | **Brier-beat out of sample** | sharp converged price vs blind at-fire mid, forecasting `won` | sharp Brier **0.0551** < blind Brier **0.0575**; sharp beats blind on **8/9 days** | **PASS** |
| 4 | **Realizable at the executed ask, official settlement, corrected fee** | day-clustered ROI at first executed BUY print ≥ ts0, fee 0.05 | **+14.9%** CI **[+3.8%, +23.1%]**, p(≤0)=0.006; spread tax (mid→ask) ≈ +0.2¢ (negligible here); mean fee 0.7¢/share | **FRAGILE PASS** — CI LB > 0 but only **9 day-clusters < 20** floor; executable-ask *spread on thin books* remains a forward unknown |

**Clears cleanly: bars 1, 3. Crux bar 2: indeterminate-leaning-positive. Bar 4: fragile. → 0 of 4 at
certification strength, but the failures are POWER, not confirmed nulls.** Secondary band 0.71–0.98 is
similar (bar 1 +9.1% CI [+2.0,+14.5]; bar 2 λ point +0.42, CLV +4.4¢, 24h CI LB just clears at +0.020 but
not robustly across horizons; bar 3 sharp beats blind 7/9; bar 4 +12.3% CI [+1.4,+20.7] fragile).

---

## THE DECISIVE RECONCILIATION — the MIRAGE test (`weather_mirage_lambda.txt`)

The committed cert's core claim is that the sharp selection is **decorative** — "the favourite BAND does
the work, we do not need a sharp" — inferred from a blind-band pool on 2 days. Adjudicated on the 9-day
window, day-clustered, spread-neutral, leak-free:

| pool | CLV @ 12h (band 0.71–0.90) | CLV @ 6h | p(CLV≤0) | days |
|---|---|---|---|---|
| **sharp-selected `weather_fav`** | **+6.0¢** | **+6.6¢** | ≈ 0.05 | 9 |
| **blind favourite band** | +1.7¢ (≈0) | +1.9¢ (≈0) | ≈ 0.28 | 8 |

**The blind favourite band has ≈ zero forward CLV** — its "edge" is the structural favourite-longshot
premium, confirmed only AT resolution (residual/variance), exactly λ≈0. **The sharp SELECTION carries a
genuine +6¢ forward move** the market partially confirms before resolution. The sharp is **not
decorative** — it is the entire information channel. This is the opposite of the committed conclusion, and
it is corroborated by Bar 3 (sharp price out-forecasts the blind mid on 8/9 days). The λ≈0 the committed
cert measured was the **blind band's** λ (correct for the band) mistaken for the **arm's** λ, on a window
too short and an entry too late to see the selection's forward move.

**Honest limit:** the sharp CLV significance is borderline (p(CLV≤0) ≈ 0.05; CI LB touches 0). So the
correct statement is "the selection has a positive, power-limited forward CLV that clearly exceeds the
blind band's zero" — **information, but not yet at certification strength.**

### Leave-one-day-out jackknife (the out-of-cohort robustness check)

Is the positive CLV driven by one lucky day? No. Per-day sharp CLV (band 0.71–0.90, 12h) is **positive on
8 of 9 days** (only 07-04 negative, −19.5¢ — the same day that dragged Bar 1); and **all 9
leave-one-day-out folds stay positive** — min-fold (drop the strongest day, 07-03) = **+4.75¢**. Same for
the wide band (all folds > 0). So the forward information is **robust within-cohort — not a single-day
artifact.** The wide Bar-2 CI is inflated by the one −20¢ day's variance, not by concentration of the
signal. (What LODO *cannot* test is disjoint WEEKS — all 9 days are one july span; see blocker #2.)

### Which of the two reconciliation outcomes did we land in?

Neither pole cleanly — a legible in-between:
- **NOT the "definitive kill"** (λ≈0 with CI *upper* bound near 0): the CI upper bounds are large positive
  (+0.7 … +1.5), CLV point is clearly positive at every horizon, LODO all-folds-positive, and the
  selection decisively beats the blind band. The evergreen-cert kill is **over-called** on the real window.
- **NOT a clean "overturn"** either (CI *lower* bound > 0 surviving the frozen gate): with 9
  single-regime day-clusters the λ CI LB does not clear 0.

→ The honest landing is **information-bearing but power-limited** — the point estimate and out-of-cohort
robustness say "real"; the CI width and single-regime span say "not yet certified." Disposition: **accrue
the disjoint weeks that would move the CI LB, do not kill.**

---

## WHY THIS IS NOT A CERTIFICATION (the honest blockers)

1. **Bar 2 CI LB straddles 0.** Point λ and CLV are positive at every horizon and the selection clearly
   beats blind, but with 9 day-clusters the lower bound is not > 0. This is *power*, not a null.
2. **Disjoint-weeks floor unmet.** All 9 resolution days are july 3–14 — a single ~12-day span, largely
   one summer regime. The incumbent prereg's decisive floor (≥2 disjoint weeks, LODO-by-week) is
   structurally impossible here, and one day (07-04, −14.8%) shows the regime-fragility is real. Bar 1's
   "walk-forward" folds are consecutive-day blocks, NOT disjoint weeks — they do not establish
   regime-robustness.
3. **Executable-ask spread on thin weather books** is measured here only via executed taker prints (a
   fast copier's realized ask); the live limit-book spread/depth at size stays a forward unknown. The
   spread tax observed (mid→executed-ask ≈ +0.2¢) is small, but on thin books at real size it may widen.

None of these is a confirmed kill. All three resolve with **forward accrual of disjoint weeks** — which
weather's evergreen daily flow supplies in 2–4 weeks, not a season.

---

## DEPLOY VERDICT

**k = 0 (do not size). NOT CERTIFIED, but ACCRUE FORWARD — do not retire.** The edge is
information-bearing but power-limited: λ point positive at every horizon, the sharp selection's forward
CLV (+6¢) decisively exceeds the blind band's (≈0), and the sharp price out-forecasts the blind mid 8/9
days — yet the λ CI lower bound does not clear 0 on 9 single-regime day-clusters. Re-run this exact,
frozen gate as disjoint weeks accrue; certify (and only then propose ⅛-Kelly-capped sizing on the
$50/$100/$250 ladder) if the λ CI LB clears 0 across ≥2 disjoint weeks with the day-cluster floor met.

**Correction to the committed record:** `1c140f1`'s "variance-not-information / band-does-the-work /
probably-permanent" is **too pessimistic** — it measured the blind band's λ on 2 stalled days. On the
edge window the selection carries genuine (power-limited) forward information. The right disposition is
*accrue*, not *kill*.

---

## Artifacts (all on `feat/weather-cert`, read-only; each `--selftest` green)
- `reports/PREREG_WEATHER_FAV_4BAR_HARVEST.md` — the gate, frozen before any number.
- `scripts/weather_fav_4bar_harvest.py` → `reports/weather_fav_4bar_harvest_full.json` — the 4 bars,
  both entry bases (atfire mid + spread-neutral tape), full horizon trajectories.
- `scripts/weather_mirage_lambda.py` → `reports/weather_mirage_lambda.txt` — the sharp-vs-blind CLV
  adjudication of the MIRAGE claim.
