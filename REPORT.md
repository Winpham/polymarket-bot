# REPORT — Fable improvement run (2026-07-02)

## Executive summary (one screen)

**Mission:** more reliable, more accurate, more profitable — nothing regressed, everything
reversible, paper-only, the belief-blind gate the only judge.

**What shipped (branch `fable/improve-run-20260702`, off main ae0db80):**
1. **Ops (no code): real book-ask capture ON** (`CAPTURE_ENTRY_ASK=true`, D5). 0% → accruing
   (40 rows in the first cycle). Unrecoverable data that now accrues forever.
2. **The gate now judges the AT-FIRE entry** (D6). `mean_price` is upsert-drifted; judging it
   both leaked post-fire information and UNDERSTATED the edge. Proof of safe swap:
   `scripts/scoreboard_parity.py` — per-strategy N identical, only surplus moves.
3. **Standing selection-matched null + pre-registered promotion rule** (D7):
   `scripts/selection_null.py` (calibration-gated, seeded, exact scoreboard statistic).
   Rule: eligible ⇔ gate LB>3% ∧ null p≤0.01 ∧ ≥2 sport-regimes positive.
4. **Docs:** DECISIONS D5-D8, this report, FORGE_PLAN_FABLE_RUN.md (pre-registration),
   FORGE_DEBATES_FABLE_RUN.md (design record).

**Headline finding (full live record: 11,819 resolved signals, 3,113 blind events, 2026-06-29→07-02):**
the consensus-favorite selection is REAL and now measured honestly —

| strategy | events | at-fire surplus | LB @3% margin | selection-null p | regimes > 0 |
|---|---:|---:|---:|---:|---|
| favorite | 92 | +10.54% | **+3.33% ✅** | **0.0000 (z 3.82)** | 4/4 (soccer/tennis/mlb/other) |
| elite_fresh_fav | 38 | +8.87% | **+4.80% ✅** | **0.0000 (z 2.77)** | 2/2 (soccer/tennis) |
| strict/count/whales | 212 | +3.53% | −2.61% ⏳ | 0.022-0.028 | mixed |
| loose | 381 | +1.00% | −3.20% ⏳ | 0.21 NULL | — |

**Certified vs paper vs refuted:**
- *Promotion-ELIGIBLE (per D7 rule, first time ever):* `favorite`, `elite_fresh_fav` — BUT
  **deliberately NOT promoted**: elite_fresh_fav N=38 < 50 pilot floor, favorite honest-ROI LB
  still below the pilot bar after execution haircut, regimes thin (tennis N=17-44), and the
  record is one 4-day window, not two disjoint accrual blocks. Re-read after Wimbledon.
- *Paper-only instruments:* everything in this run. No alerting change, no real money.
- *Refuted/parked:* `longshot` selection signal is real-ish per-share (p=0.03) but cost-dead
  (flat-shares −$227 after haircut+fee) — parked. `loose`/`tight_cluster` selection = NULL.
  market_resid stays OFF (2026-07-01 refutation stands).
- *Sizing discipline confirmed on full data:* strict flat-$ −$4,726 vs flat-shares +$114;
  loose flat-$ −$18,198. Flat-shares is mandatory (REFINED-STRATEGY rule 3 re-confirmed).

**What was deliberately NOT done:** see DECISIONS D8 (parallel-session file regions deferred —
sport segments + flat-shares in Rust board; migration-032 collision flagged for the integrator;
no promotions; no new arms; no relational build).

**Non-regression evidence:** full gate green at every commit (`cargo fmt --check`, `clippy
--workspace --all-targets -Dwarnings`, `cargo test --workspace`: 228 passed / 0 failed);
`scoreboard_at_fire_it` regression test green on a throwaway PG; parity harness K1 OK;
`strict` alerting, trader_trust, honest-P&L math untouched.

**Exact rollback:**
- Code: `git -C ~/polymarket-bot reset --hard pre-fable-run-20260701` (or revert the single
  --no-ff merge commit).
- Ops: delete the `CAPTURE_ENTRY_ASK=true` line from `.env.consensus`
  (backup: `backups/pre-fable-run-20260701-untracked/.env.consensus.bak`) + recreate the stack.

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
