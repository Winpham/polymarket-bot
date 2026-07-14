# Favorite‑Edge Erosion Forensics — findings

**Run:** 2026‑07‑14, autonomous. **Branch:** `feat/erosion-forensics`.
**Question:** the champion `favorite` 0.71–0.98 slid from ~+8% cumulative ROI‑turn to +7.1% over ~5 days.
Why — and is anything mechanism‑justified to be done?

## Verdict — NO ACTION WARRANTED

**This is a cold streak that the data is underpowered to distinguish from a decay.** No cause was
established. The strategy, every incumbent, and `ConsensusParams::default` are **unchanged**. No arm was
added, no flag, no migration. The run's product is a trustworthy attribution and a frozen forward gate.

### The decisive fact: power

> Detecting a fall from **+8% → 0%** at 95% needs **~62 matches per window**.
> The recent window has **38** (k=5) / **20** (k=3).

The recent window **cannot resolve the question it is being asked to resolve.** Everything below follows
from that.

## Phase A — variance is NOT ruled out

Match‑clustered (`superkey.super_event`), on a **stationary** price basis.

| null | k=3 | k=4 | k=5 | k=7 |
|---|---|---|---|---|
| match permutation *(anti‑conservative — ignores slate correlation)* | 0.001 | 0.021 | 0.013 | 0.128 |
| **day‑block permutation (exact, the honest null)** | **0.021** | 0.077 | 0.054 | 0.197 |

**BH‑adjusted minimum over the day‑block family: p = 0.086.** A constant +8% edge is not excluded.
For contrast, the 07‑06 drawdown — which *was* a real, diagnosed decay — returned **p ≈ 0.002**.

The cumulative slide is also less dramatic than it looks: excluding the hot first day (06‑29, +13.1% on 32
matches), the series has sat in a **6–8% band since 07‑03**. The 8.4→7.1 move is a 1.3pt wobble inside it.

## Phase B — every mechanical cause came back negative

| axis | result |
|---|---|
| 1. edge decay | **INCONCLUSIVE — underpowered.** Skill drop not separable from noise. |
| 2. **crowding / market tightening** | **NEGATIVE.** `_blind` structural edge is **flat**: 1.70% → 1.81%. Softness is *not* being arbitraged away. |
| 3. **tournament/regime mix shift** *(the brief's leading hypothesis)* | **NEGATIVE — and backwards.** The mix moved hard (soccer 75% → 33% of turnover) but the Oaxaca **mix term is +2.5pt** — it *helped*. The damage is entirely the **−7.4pt within‑cell performance term**. |
| 4. price‑band drift | **NEGATIVE.** Mean entry 0.860 → 0.842; sub‑band moves within noise on 18–25 legs each. |
| 5. trader/convergence quality | **NEGATIVE.** net_count 2.59 → 2.65, n_backers 3.08 → 3.06. Unchanged. |
| 6. pipeline/capture artifact | **NEGATIVE for the headline series** (stationary basis, 100% coverage) — but a real hazard was found, below. |
| 7. single‑cell contamination | **POSITIVE but NOT ACTIONABLE** — see below. |

## The one thing that looked like a cause — and why it isn't

The within‑cell loss localises to **tennis: +13.4% → −9.9%**, now the dominant recent cell (19 of 38
matches). Post‑Wimbledon the tour drops to small events (`boulais‑zhang`, `kopriva‑prizmic`,
`penicko‑thandi`) where a 0.75–0.85 "favorite" is two similar journeymen, not a mispriced star. That is a
genuine *a‑priori* mechanism, so it earned a real test. **It failed all four:**

1. **Multiplicity** — found by scanning 7 categories. Bonferroni **p = 0.100**.
2. **CI** — recent tennis 95% CI is **[−36.2%, +16.3%]**, which **contains** the earlier **+13.4%**.
3. **LODO** — drop the single **07‑13** slate (10 of the 19 matches) and recent tennis flips to **+6.3%**.
   The entire "tennis decay" is *one slate*.
4. **The remainder doesn't even pay** — non‑tennis recent is +3.4% with a **95% LB of −5.8%**.

Excluding tennis would be precisely the forbidden dredge: *remove whatever lost last week.* It always
improves the backtest and never replicates. **It is explicitly frozen out in the prereg.**

Also rejected: a **volume‑floor self‑suspension** — volume is **not** draining (07‑13 was the
second‑heaviest slate of the whole window, 16 matches). The trigger does not fire.

## A real measurement hazard found (documented, not patched)

**`COALESCE(entry_ask, initial_mean_price)` is unusable for any time‑comparison.** `entry_ask` coverage is
**non‑stationary — ~5% of legs on 06‑29, ~70% on 07‑13** (the capture work landed mid‑window) — and
`entry_ask` sits *above* `initial_mean_price`. That basis silently swaps a more expensive price source
into a growing share of legs as the window advances, **manufacturing a downward drift out of capture
coverage alone.**

It did **not** affect this investigation — the incumbent daily table already uses `initial_mean_price`
(100% coverage, all 16 days), verified to reproduce the brief's series exactly (8.35/8.29/8.04/7.78/7.07).
But any future time‑series analysis on the coalesce basis would invent a decay that isn't there.
`erosion_lib.legs(basis=…)` enforces a single stationary basis and refuses to mix band‑membership and
P&L price sources.

## What actually settles this

**The weeks after the World Cup final (~2026‑07‑19).** The edge has only ever been measured on summer
tournaments. The post‑tournament stretch is the **first genuine out‑of‑tournament test it has ever
faced** — and a far more important question than the current cold streak. The gate is frozen in
`reports/PREREG_20260714_erosion.md`: ≥62 matches, belief‑blind surplus, day‑block null, BH‑corrected.

## Artifacts

| what | where |
|---|---|
| Variance null (Phase A) | `reports/EROSION-VARIANCE-NULL.json` |
| Seven‑axis decomposition (Phase B) | `reports/EROSION-DECOMPOSITION.json` |
| Adversarial test of the tennis finding | `reports/EROSION-TENNIS-TEST.json` |
| Action verdict (Phase C) | `reports/EROSION-ACTION-VERDICT.json` |
| **Frozen forward gate** | `reports/PREREG_20260714_erosion.md` |
| Instruments (all `--selftest`) | `scripts/erosion_{lib,variance_null,decompose,tennis_test,action_verdict}.py` |
