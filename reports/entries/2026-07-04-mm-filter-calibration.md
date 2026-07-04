# 2026-07-04 — MM-FILTER Phase 1: the microstructure screen, validated offline — NO-GO on the binding test

**Headline verdict: NO-GO / INDETERMINATE-BY-POWER.** The live `0.30 / 0.25 / 0.50` churn
screen **correctly identifies market-makers** (Tier-1: catches 27/27 economic arbers, FN-rate 0%),
but **excluding the wallets it flags does NOT make the copy pool more persistent** out-of-sample
beyond a matched-subset null (Tier-2: NO-GO across all 12 operating points, every p ≥ 0.16, Δcorr
flips sign −0.13…+0.13). Per the brief's own gate, **we STOP at Phase 1 and do not build Phase 2.**
The screen stays an offline audit; the live paper screen is left byte-identical.

This is the deferred verdict the `refresh_router_followset` docstring
(`consensus.rs:1569-1574`) has been waiting on — *"interim pending FORGE_PLAN_MM_FILTER's
calibrated verdict."* The honest answer: the two-sided axis is a valid MM detector, but at n≈30-60
wallets we **cannot show the screen improves the thing we copy for (forward persistence)**, and the
`round_trip_rate` axis is an unvalidated false-positive generator.

## What was built (Phase 1 only — offline Python, read-only, paper-only)

Four scripts in `scripts/`, all with `--selftest`, all reading the live DB read-only (no Rust
changes, no `trader_type` mutation, live `strict` path untouched):

- `mm_common.py` — shared microstructure algebra reproducing `refresh_router_followset`'s
  `pos→sided→two→micro` CTEs (`consensus.rs:1587-1610`), **as-of capable** (`ts < cutoff`) for
  leak-free Tier-2, plus blind-baselined per-event surplus (mirrors `trader_slice_scores`).
  Crosscheck: Python rates == persisted `router_followset` rates (0 disagreements > 0.02).
- `mm_calibrate.py` — Tier-1 labeled FP/FN + AUC + label-permutation null + LOO sweep.
- `mm_persistence_effect.py` — Tier-2 matched-subset-null persistence-effect test (the binding gate).
- `mm_reconcile.py` — Item-6 reconciliation of the 115 `fpd` flags vs the screen.

## Tier-1 — labeled (necessary, NOT sufficient; partly circular by construction)

Labeled set (provenance recorded in `mm_calibrate.py`): **27 MM** = economic buy-both-hold arbers
identified by *price-sum* economics (median two-leg sum ≤ 1.10 over ≥20 paired markets, both-hold
frac ≥ 0.50 — the `mm_premise_probe.sql` arb signature, orthogonal to the rate thresholds) + the
flagship $51M churner. **41 HUM** = the two D23 soccer humans (`0xe9a6ed2e4d`/`0x56f0321917`,
+10-11% tax-surviving) + active directional bettors (both-hold frac < 0.10, ≥20 days, ≥200 fills).

| axis (higher = more MM-like) | AUC |
|---|---|
| `two_sided_rate` | **1.000** ← carries all the discrimination (but circular: HUM labelled by low both-hold ≈ two-sided) |
| `round_trip_rate` | **0.265** ← below 0.5: *anti*-discriminates this MM type |
| `sell_buy_ratio` | **0.244** ← below 0.5: same |
| ensemble (max of normalized) | 0.995 (perm-null p = 0.0005) |

Live-threshold confusion on the labeled set: **TP=27, FP=11, TN=30, FN=0** → FN-rate **0.0%**
(catches every arber), FP-rate **26.8%** (11 of 41 directional humans flagged).

**The FP driver is `round_trip_rate ≥ 0.30`.** All 11 false positives are directional bettors
(both-hold ≈ 0, `two_sided` ≈ 0, 25–88 active days) flagged because they *sell to manage positions*
— exactly the human the brief warned the round-trip axis would wrongly catch. The buy-both-hold
arbers, by contrast, **hold both legs to resolution** and so read *low* `round_trip`/`sell_buy` —
which is why those two axes score AUC < 0.5 here. **Net: on the MM class actually present in the
data, `two_sided_rate` does all the work; the `round_trip`/`sell_buy` thresholds are unvalidated
and FP-generating.** Sweep (freeze `two_sided`=0.30, float `round_trip`): balanced accuracy is
maximized at `round_trip`=0.50 (LOO-stable, std 0.00) — i.e. the data wants the round-trip knob
*relaxed*, not at 0.30. **Circularity caveat: the HUM label leans on low both-hold, so Tier-1
over-states separation. Tier-1 is necessary, not sufficient — Tier-2 is binding.**

## Tier-2 — label-free persistence effect (THE BINDING TEST) → NO-GO

Method: collapse fills to `(wallet, match_key)` event surplus; split each wallet's picks
early/late by placement day; measure cross-wallet corr(early mean surplus, late mean surplus)
**with vs without** screen-flagged wallets. Screen verdict computed **as-of the cutoff** (early
fills only — leak-free). Δcorr tested against a **matched-subset null**: remove random equal-N
subsets matched on (volume, n_positions) strata ≥2000×; require the real Δcorr in the right tail.

Primary operating point (cutoff 2026-07-01, min_ev 8, n=56, 27 flagged):

| | corr | 95% CI |
|---|---|---|
| WITH flagged | +0.005 | [−0.26, +0.27] |
| WITHOUT flagged | +0.000 | [−0.37, +0.37] |
| **Δcorr** | **−0.005** | matched-null p = **0.332** |

Robustness — **all 12 operating points** (cutoff × min_ev):

```
cutoff      min_ev  n   nflag  corr_with corr_wo  dcorr    p     verdict
2026-06-30    5     71   28    -0.126   -0.168   -0.041  0.49  NO-GO
2026-06-30    8     46   19    -0.071   -0.098   -0.028  0.37  NO-GO
2026-06-30   12     22    9    +0.017   +0.087   +0.069  0.55  INDET-POWER
2026-07-01    5     99   44    -0.098   -0.048   +0.050  0.32  INDET-POWER
2026-07-01    8     56   27    +0.005   +0.000   -0.005  0.33  NO-GO   (primary)
2026-07-01   12     32   17    +0.006   +0.139   +0.133  0.16  INDET-POWER
2026-07-02    5    118   52    +0.112   +0.138   +0.026  0.41  INDET-POWER
2026-07-02    8     54   25    -0.025   -0.155   -0.129  0.86  NO-GO
2026-07-02   12     35   19    -0.128   -0.250   -0.122  0.48  NO-GO
2026-07-03    5     97   56    +0.053   +0.049   -0.004  0.57  NO-GO
2026-07-03    8     58   36    +0.050   +0.043   -0.007  0.34  NO-GO
2026-07-03   12     41   28    -0.091   -0.198   -0.107  0.48  NO-GO
```

Parity split-half (crawl-stamp-robust, n=147): corr −0.102 → −0.235, Δcorr **−0.134**, p **0.910**
(deep in the *wrong* tail — removal makes persistence *worse*).

**Reading:** (1) baseline early→late persistence is ≈0 (not the −0.10 the brief assumed) and its CI
(±0.3+ at these N) **swamps any effect**; (2) Δcorr is unstable in sign and **never clears its
matched-subset null** — the sporadic positive Δcorr's are the *mechanically-expected* artifact of
removing high-leverage points, which is exactly what the matched null exists to catch. The
persistence signal itself is too weak to have a screen effect to detect. **Verdict:
NO-GO / INDETERMINATE-BY-POWER.**

**Data caveat (headline):** resolved-BUY fills are dominated by a backfill crawl over 2026-06-30…
07-03 and `ts` on backfilled rows is a crawl stamp, so the temporal split is only weakly temporal.
The parity cross-check exists precisely because of this and agrees (NO-GO). This is a *second*,
independent reason the temporal read cannot certify.

## Item 6 — reconciliation of the 115 `fpd` flags vs the screen (`mm_reconcile.py`)

The two detectors disagree on **132 wallets** (matches the docstring's "51/161 disagree → enforce
both"). Read-only recommendations, **nothing mutated**:

- **(a) 40 RESTORE candidates** — `fpd='bot'` but screen-**clean** (burst-human FPs the `fpd≥400`
  rule likely deleted). Several carry high surplus with clean microstructure — e.g. `0x29b52d98`
  (+0.251, rt/ts/sb ≈ 0/.07/0), `0x7c1ee865` (+0.172), `0xf1528f12` (+0.154, 98 pos). Strong
  candidates to return to the copy pool.
- **(b) 92 EXCLUDE candidates** — `fpd='human'` but screen-**churner** (patient MMs the fpd rule
  missed), almost all `two_sided`-driven, most with low/negative surplus — e.g. `0x6db568e6`
  (two_sided 0.85, 348 pos), `0xc3656b31` (two_sided 0.50, 187 pos, −0.011). *Refinement noted:* a
  handful fire on `two_sided`=1.0 with 2-5 positions (noise, not MMs) — an `n_pos` floor on the
  screen would spare them (Phase-2 territory, not applied).

Full tables in `reports/mm_reconcile.json`; Tier-1 in `mm_calibrate.json`; Tier-2 in
`mm_persistence_effect.json`.

## Decision & next step

**STOP at the Phase-1 gate. Do not build Phase 2** (the calibrated Rust verdict / migration 040 /
shadow arm) — it was conditional on a Tier-2 GO, which we do not have. The live paper screen is
unchanged and byte-identical.

The binding constraint is exactly the accrual wall every other track hit: **out-of-sample
persistence needs independent forward clusters, and at n≈30-60 wallets over a crawl-contaminated
4-day live window there is not enough power to decide whether MM-exclusion helps.** Recommended next
data-collection step: accrue **≥2-3 months of genuinely-timestamped forward fills** (dense at-fire
capture, not backfill), re-run `mm_persistence_effect.py` with a rolling cutoff, and only revisit
Phase 2 if Δcorr clears its matched-subset null on that forward record. Until then the two open,
lower-risk, offline-decidable items are: (a) the 40 restore / 92 exclude reconciliation for a human
pool review, and (b) the Tier-1 finding that the `round_trip_rate<0.30` axis is FP-generating and
carries no validated benefit on the visible MM class — a candidate simplification (drop to
`two_sided` + `sell_buy`, or relax round-trip to ~0.50) whenever Tue chooses to touch the screen.
Neither is applied here.
