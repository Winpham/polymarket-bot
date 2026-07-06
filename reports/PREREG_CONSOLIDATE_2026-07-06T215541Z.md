# PRE-REGISTRATION SEAL — Cycle-8 forward challengers (beat-best-trader)

**SEAL (UTC): 2026-07-06T21:55:41Z** · branch `run/beat-best-trader` · PAPER-ONLY · adopts/arms/promotes
NOTHING · no Rust/migration change · DB read-only · cost-zero (Max-only).

Frozen at the seal timestamp. These are the challengers from the Cycle-8 CONSOLIDATE-AND-IMPROVE run that
were **promising but underpowered / not-yet-adoptable** on the current ~8-day record. They are frozen here
so they can be re-judged forward through `scripts/standard_guard.py` + `scripts/consolidate_challengers.py`
as events accrue. **Nothing here may be re-tuned to pass.** A change to any floor is a NEW seal with a new
timestamp. A challenger is ADOPTED only when it BEATS the champion out-of-sample on the realizable metric
**and** clears the belief-blind gate (`selection_null` p≤0.01, `--calibrate` PASS, LB>3%, ≥2 disjoint
NON-soccer regimes). Adoption stays a deliberate human call behind the standing 4 GO gates.

Champion at seal: realizable **+4.92%** (139 ev) · belief-blind favorite LB **+4.69%**, p_emp 0.000 (164 ev).

---

## Forward challenger 1 — Reliability-weighted consensus
- **Rule (frozen):** favorite arm restricted to events with ≥1 backer in the `reliability_score` skill
  pool (cal_gap>0, per-wallet belief-blind null p≤0.05, directional).
- **Blocked by:** reliable-backer accrual. At seal only **13 of 164** favorite events qualify (durable
  reliable traders are near-disjoint from the favorite backer population) → belief-blind underpowered
  (<30-event floor); realizable +9.20% but CI [−19.3%, +25.0%].
- **GO condition:** ≥30 distinct reliable-backed favorite events AND realizable > champion AND belief-blind
  gate cleared. Re-judge via `consolidate_challengers.py` challenger `1_reliable_backed`.

## Forward challenger 3 — Mid-band consensus as an uncorrelated diversifier
- **Rule (frozen):** `strict` consensus restricted to band 0.35–0.65, added to the favorite standard as a
  combined book.
- **Status at seal:** marginally selection-real standalone (229 ev, surplus +4.0%, p_emp 0.041, LB +0.20%,
  4 non-soccer regimes+) and **uncorrelated** with the favorite standard (day-return corr **0.05**), BUT
  realizable **−2.0%** after the band-aware tax → combined book realizable +1.01% (Δ −3.91%): DILUTES the
  champion. CHAMPION-STANDS today.
- **Blocked by:** the realizable tax. **GO condition:** mid-band standalone realizable > 0 at the measured
  tax (contingent on the §6 dense-capture lever) AND combined-book realizable > champion +4.92% AND the
  low correlation persists → then the diversification is real. Re-judge via challenger `3_midband_consensus`.

## Forward challenger 5 — Conviction/edge-weighted sizing
- **Rule (frozen):** size favorite bets 1%→3% of bankroll by `net_quality` conviction percentile (cap 3%),
  vs flat 1%.
- **Status at seal:** log-growth +0.21 / Calmar 5.49 vs 4.09 on a **single 8-day path**, but max drawdown
  **doubles** (8.2% vs 4.2%). Same selection ⇒ leverage, not a selection edge; cannot clear the belief-blind
  gate. Not adoptable.
- **GO condition:** on ≥30 independent days, block-bootstrap CI on the log-growth delta excludes 0 AND a
  ruin/Kelly-fraction analysis shows the drawdown is acceptable at ≤⅛-Kelly. This is a SIZING overlay on the
  champion's selection, never a substitute for beating the belief-blind gate.

---

## Discarded this cycle (NOT pre-registered — refuted or edge-destroying)
- **Backer-quality screen (challenger 2):** the majority-directional screen keeps only 11/164 events and is
  realizable −13.9% — the favorite edge rides on high-volume/MM-flagged backers; screening them out kills
  edge and sample. Do not apply.
- **CLV-exit overlay (challenger 4):** early-exit lowers mean return, barely cuts variance, and raises
  drawdown at every target — favorites should be HELD to resolution. Discarded.

## The one live lever (DEFERRED — human review, not sealed as a paper challenger)
- **Dense at-open capture / entry-tax reduction (challenger 6):** the highest-leverage improvement — it
  lifts the CHAMPION'S OWN realizable (real tax ~1.0–1.3¢ vs the ~2.3¢ scored) and could rescue forward
  challenger 3 into a positive-realizable diversifier. It is a LIVE capture change → DEFERRED to human
  review (see `dense_capture_diag.json` fix_spec). No Rust/config touched in this run.
