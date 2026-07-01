# REPORT — Optimal Congregation Engine

## Executive summary (one screen)

**The optimal model I arrived at:** a diversified book of per-sport gate-certified
specialists, each sized by its shrunk certified lower-bound edge, combined so that
uncorrelated edges raise risk-adjusted return above any single member. That is the only
mathematically honest way to beat the best of them — and it rests on one precondition:
≥2 independent, capturable, persistent per-sport specialists must exist on the data.

**Does it beat naive count and the market today? No — and neither does anything else,
because the precondition fails.** A leak-free as-of certification (reproducible,
`scripts/asof_preflight.py`) finds **zero** wallets certified as per-sport specialists at
the capture bar — not as-of, not persistent, and not even full-window in-sample (the most
generous possible test). The reason is structural: the entire forward record is
essentially **two adjacent days of one tournament** (World Cup soccer 2026-06-29/30 ≈ 89%
of resolved buys) plus a few Grand-Slam tennis bursts. There are not two uncorrelated
edges to diversify; there is not one certified edge to size.

**Honest odds & accrual ETA:** Not a near-term date. Two conditions must both hold and the
second is the wall: (1) ~30 *independent* event-days per wallet in a sport — months of
continuous major-tournament slates, and soccer density collapses when the World Cup ends;
(2) a surplus clearing `lo > 3%`, which is **absent for every wallet today**. More data
mainly tightens bounds around point estimates that mostly sit below the capture margin.
Correct posture: keep accruing, re-run this one-hour pre-flight after each tournament
block, promote nothing until ≥2 cross-sport cells clear `lo>3%` on ≥2 disjoint cuts.

**Exact human action to promote (when ready):** none today. There is no flag to flip —
the arms were intentionally not built (charter §0.5 DEAD branch). When the pre-flight
first shows ≥2 persistent cross-sport specialists, the next run builds Phase 1
(`SliceTrustMap`) + Arm A (`spec_footprint`) + Arm D (`spec_contrarian`) silent/OFF, and a
human would set `CONSENSUS_ARM_SPEC_FOOTPRINT=true` only after the on-board forward record
certifies at a pre-registered evaluation point (H5: first at N=30 distinct events, then
every +15).

**Verdict: SUCCESSFUL NULL.** A correctly-built, leak-free instrument that correctly
reports the edge is not yet identifiable — not a green number that fools us.

---

## Per-arm certification board

No arm was built (premise DEAD, charter §0.5). The board below reports the **candidate
specialist identification** that gates every would-be arm, over event-clustered units, at
the capture margin — the certification the arms would have depended on.

| unit | events (N) | surplus | Bonferroni lower bound @ 3% margin | verdict | vs naive count | vs market |
|---|---|---|---|---|---|---|
| best soccer cell (0x65018f9f, in-sample) | 28 | +27.4% | +9.7% | **INDETERMINATE** (N<30 floor) | n/a — no arm | not snapshotted¹ |
| best soccer cell ≥floor (0xe9a6ed2e) | 58 | +10.8% | −3.4% | **INDETERMINATE** | n/a | ¹ |
| best tennis cell (0x204f72f3) | 112 | +4.2% | +0.2% | **INDETERMINATE** | n/a | ¹ |
| **any per-sport specialist Trusted@capture** | — | — | — | **0 cells** | — | — |
| **≥2 uncorrelated, cross-sport, persistent** | — | — | — | **0 (slate-collapsed)** | — | — |

¹ CLV/line-movement lens (charter Item 5) is unavailable as a certifier: `_blind` rows are
never price-snapshotted (`housekeeping.rs`), so the price-move band-blind degenerates to 0.
It remains a reported lens only; primary certification is the outcome scoreboard. Moot here
since no arm cleared the outcome gate.

## Nulls

The identity- and outcome-shuffle nulls are pre-registered for any *fitted/mined* model
(Item 6 harness). None was built (no fitted/mined arm survived the identification gate to
justify spending the harness), so there is no fitted model whose edge needs shuffling to 0.
The identification result itself is the stronger statement: the edge is absent *before* any
fitting, at `margin = 0` as well as `margin = 3%`.

## Walk-forward holdout

The forward-live arms' on-board record *is* their holdout — but no arm exists to have one.
The retrospective walk-forward (as-of cuts 06-29, 06-30) is the holdout for the
identification claim: **0 certified specialists on the train side of either cut; 0 cells
with ≥30 events on both sides of any cut** → persistence is not even measurable, because
there is only one cut with two-sided coverage and it fails to certify anyone.

## Diversification result

The central thesis — a combined book beats the single best specialist out-of-sample,
risk-adjusted — is **untestable and moot** on this data: 0 certified specialists, and the
correlation structure that drives any diversification benefit is degenerate (one
tournament slate; H4 slate-clustering collapses all candidates onto the same World Cup
matches). There is no independent edge to combine.

## Accrual curve

Dated independent event-days per sport (ceiling on any wallet's independent-N): **soccer
21, tennis 9, mlb 12**, else ≤4; crypto 237 events but **0** dated days. See DECISIONS.md
D4 for the full ETA argument. Bottom line: coverage is months away and edge is absent
today; no defensible near-term bet exists.

## Recommendation

**Promote nothing.** Keep the forward record accruing. Ship the durable leak-free
instrument (done: `trader_slice_scores_asof`, capture-margin gate, the pre-flight harness).
Re-run `scripts/asof_preflight.py` after each major tournament block; the first time it
shows ≥2 persistent cross-sport specialists clearing `lo>3%` on ≥2 disjoint cuts is the
trigger to build Phase 1 + Arms A/D. Until then, the honest congregation signal is silence.
