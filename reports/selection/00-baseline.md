# WS-0 Baseline — Specialist Selection foundation (refreshed 2026-07-03)

Ground-truth refresh + foundation changes for the Specialist-Selection program
(`run-prompts/RUN-SPECIALIST-SELECTION.AUTONOMOUS.md`, FORGE_PLAN Items 1–2).
Everything below was **re-measured against the live Postgres**, read-only — the
authoring-time snapshot numbers are corrected where they were stale.

---

## 1. Archive state (measured, not assumed)

| metric | authoring snapshot | **measured 2026-07-03** | note |
|---|---|---|---|
| `trader_fills` rows | ~1,036,974 | **1,070,923** | grew |
| distinct wallets | 397 | **400** | — |
| resolved rows | 766,444 | **847,875** | grew |
| **distinct resolved events (event-slug grain)** | ~5,922 | **3,772** | ⚠ see §1a |
| distinct resolved *conditions* | — | 6,132 | the grain the snapshot used |
| calendar span | 2022-12-15 → 2026-07-03 | **2022-12-15 → 2026-07-03** | ✓ |

### 1a. The distinct-event count is definition-dependent — the honest number is 3,772
Every resolved fill has a non-NULL `event_slug` (0 resolved rows fall back to
`condition_id`), so the gate's clustering unit `COALESCE(event_slug, condition_id)`
= **event-slug grain = 3,772 distinct events**. The snapshot's "~5,922" is the
**condition grain** (6,132 markets). One World-Cup *event* bundles many
*condition* markets (moneyline + spread + o/u + BTTS + exact-score…), so the two
differ by ~1.6×. **All gate math clusters at event-slug grain**, so 3,772 is the
power-relevant number. Report it, not 5,922.

## 2. Profiling reach — smaller than advertised at the gate's own grain

Wallets clearing the distinct-**event** floor (the gate's clustering unit):

| floor | event-slug grain (**gate unit**) | condition grain (the snapshot's) |
|---|---|---|
| ≥25 | **72** | 99 |
| ≥30 | **59** | 85 |
| ≥50 | 36 | 58 |

The snapshot's "**78 wallets clear ≥30**" is a **condition-grain** figure
(here 85). At the gate's event-slug grain only **59** clear ≥30. **Lowering the
trust floor 30→25 (Item 1) lifts gate-grain profiling reach 59 → 72 (+13
wallets)** — a real but modest power gain, not the "78+" the prose implied. This
is the honest reach the specialist map (WS-1) has to work with.

## 3. Cohort coverage & eligibility

`followed_traders`: **463 tracked · 309 active · 167 consensus_eligible · 0
earned_eligible** (snapshot: 457/309/167/0 — tracked grew by 6, the rest
unchanged). **`earned_eligible` is still 0** — nobody has earned into the voter
set. FORGE_PLAN Item 7 diagnoses this: `promotable_deep_sharps` demands an
*undiluted overall* Trusted verdict, which a specialist (sharp in one sport,
weak in another → overall washes to Indeterminate) structurally cannot clear.
Not routed around — diagnosed in WS-3/Item 7.

## 4. Capture completeness (who can be trusted as a specialist at all)

`followed_traders.capture_gap_count`: **370 wallets clean (0 gaps) · 93 with ≥1
gap · worst = 683 gaps.** The `/activity` API returns a hard 100-row newest page
and ignores `startTs`, so deep history exists only where polling kept up. ~20% of
tracked wallets carry capture gaps and **cannot be trusted as specialists no
matter how clean their surplus looks** — WS-1 must flag/￼exclude high-gap wallets.

---

## 5. Deploy-mechanism correction (governs all isolation) — **important**

The prompt says "the live bot auto-deploys from `feat/consensus-engine` HEAD."
**This is stale.** `scripts/consensus-autoupdate.sh` rebuilds/redeploys when
**HEAD of the main working checkout advances** *and* a code path under
`common/ | copy-trading-bot/ | migrations/ | Cargo | Dockerfile | compose`
changed (it also `git merge --ff-only @{u}` if an upstream is set). The main
checkout is on **`main`**, which is **102 commits ahead** of
`feat/consensus-engine`. Consequences:

- **Isolate off `main`, not `feat/consensus-engine`** — branching off the stale
  branch would drop 102 commits of merged work (corr-risk, honest-pnl, deep-edge…).
  This program's worktree: `../pmkt-selection` on `lever/specialist-selection`
  off `main`.
- **Python + `reports/` changes never trigger a rebuild** (outside `CODE_RE`), so
  all analysis/scripts/report work is deploy-safe even on `main`.
- **Merging to `main` advances HEAD ⇒ deploy.** Safe here because every new arm is
  default-OFF/silent, but it means the merge itself is the deploy event — gate
  must be green first.

## 6. As-of leak caveat (governs WS-1's persistence split) — **important**

`trader_slice_scores_asof(cut)` bounds everything by `resolved_at < cut`, but on
the *backfilled* archive `resolved_at` is a **bulk-ingest stamp** (all in
2026-06/07), so `resolved_at < cut` is **degenerate for retrospective analysis**
(DECISIONS.md D1, noted in the code). Therefore:

- A real **in/out temporal split on the deep archive** (WS-1 persistence) must use
  the **slug-parsed event-date** harness (`scripts/asof_preflight.py`), NOT the
  as-of query.
- The as-of query is correct **for forward data**, where `resolved_at` is stamped
  in real time — that is where Item 4 L3's binding forward permutation lives.
- Do not conflate "the specialist map fits the deep archive" with "it is
  forward-valid." The map is mined on history; any *arm* is silent + forward-accruing.

---

## 7. Foundation changes shipped in this WS-0 (Items 1–2)

### Item 1 — `TrustParams { min_events: 25 }` (trust floor split)
- New `TrustParams` type in `promotion.rs` (distinct from `PromotionParams`), with
  `into_promotion()`; `trust_verdict` now reads it. Floor 30→25 for the
  **trust/specialist** verdict only.
- **Pilot floor untouched**: `honest::PilotThresholds::default().min_events == 50`
  (asserted). Real-money bar unchanged.
- Tests: `trust_floor_is_25_pilot_floor_still_50`,
  `hairline_25_event_slice_reads_indeterminate` (a 25-event +0.04/sd-0.10/12-day
  slice still reads **Indeterminate** — 25 widens *eligibility*, never *false trust*).

### Item 2 — `bet_type` axis (migration 037) + favorite-residual cell-blind
- Migration **037** `trader_fills_bettype.sql` (next free; 036 confirmed latest in
  this trunk): nullable `bet_type TEXT`, no backfill, mirrors `sport`.
- `bet_type_bucket(title, slug)` classifier: `moneyline | spread | totals | prop |
  other` (first-hit-wins; prop before moneyline). **Validated on the live archive**
  (distinct-event share): moneyline 900 ev, prop 113, totals 177, spread 170,
  other 2,707. `other` = **16.3% of rows** and is dominated by **crypto price
  markets** (1,946 events) — for which "other" (binary threshold event) is the
  *honest* bucket, not a classifier miss. Sports residual in `other` is tiny
  (soccer 23 ev). Meets the "<15%-ish, honest tail" bar.
- Slice CTEs (`trader_slice_scores` + `_asof`): blind generalized from `band`-only
  to a **`(sport, band)` cell-blind with cascade fallback**
  `COALESCE(blind_cell, blind_band, 0)` (never fails *open* to raw advantage), plus
  a new `bettype` slice branch. `TraderSliceStat` FromRow order unchanged (bettype
  is a slice *value*, not a column).

#### Why the cell-blind matters — measured, read-only (the favorite-in-disguise fix)
The incumbent band-only blind differs from the new `(sport,band)` cell-blind by up
to **±0.44 surplus** in high-volume cells:

| cell | n | cell-blind | band-blind | Δ (favorite residual) |
|---|---|---|---|---|
| nba band-2 | 692 | +0.347 | −0.095 | **+0.442** |
| cs2 band-4 | 1552 | −0.176 | +0.068 | −0.244 |
| nba band-4 | 879 | −0.163 | +0.068 | −0.231 |
| mlb band-4 | 6187 | −0.083 | +0.068 | −0.151 |

Under the old band-only blind, a wallet loading (say) nba-band-2 underdogs scored
its surplus against the *cross-sport* band-2 average (−0.095) and looked skilled;
the cell-blind reveals the whole fleet won there (+0.347) ⇒ surplus ≈ 0. **The
band-only baseline was NOT neutralizing favorite/regime-loading per sport; Item 2
fixes it at the verdict.** (These are in-sample fleet averages over a
WC-soccer-heavy archive — direction and magnitude are the finding; per-cell noise
at low n is why WS-1 keeps the ≥25 floor + Bonferroni.)

---

## 8. Honest thin-vs-deep distinction (the governing caveat, restated)
- **Deep** (mine/profile OK): `trader_fills` back to 2022, 3,772 event-grain
  resolved events, 72 wallets ≥25 — the specialist *map* may be fit here (with a
  slug-date in/out split, §6).
- **Thin** (certify only here): the forward consensus-signal record is ~days. No
  arm built on the deep map is certified until it clears the pilot gate on
  **forward** data (Item 4 L3, ≥2 disjoint windows). This run certifies **nothing**
  live; every arm is silent + default-OFF.

## 9. Open follow-ups carried into WS-1+
- Codify the two cell-blind cascade properties (`_falls_back_to_band_blind_when_thin`,
  `_single_sport_wallet_cell_blind_equals_band`) as fixture-DB integration tests
  (mirror `trust_scores_e2e`, `#[ignore]`); the cascade is currently verified
  **empirically read-only** (§7, no NULLs, correct fallback shape) — strong but not
  yet a codified fixture test.
- WS-1 must exclude/flag the 93 high-`capture_gap` wallets (§4).
- Item 7 diagnosis of the 0-`earned_eligible` puzzle (§3).
