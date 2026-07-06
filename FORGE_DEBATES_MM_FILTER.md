# Forge Debates — Market-Maker Detection & Filtering

Compressed record of the 4-agent Forge run (2026-07-04) behind `FORGE_PLAN_MM_FILTER.md`.
Diagnose → dual-design (Direct / Rethink) → reality-check + synthesis. All facts verified vs source.

## The problem as diagnosed
- Live MM defense = **only** the in-window, per-market, BUY-only two-sided drop (`consensus.rs:365-382`).
  The D23 "59% of top wallets are MMs" figure is measured *after* it runs → it's insufficient.
- The blunt classifier (`classify_trader_types`, `fpd≥400`, `storage/consensus.rs:1327`) already ran,
  flagged **115 `bot`**; after filtering, **29–72 humans** survive with enough monthly history. So a
  **false positive deletes 1 of ~29 humans**; a false negative re-pollutes the pool with churn PnL.
- **Two dossier corrections found by the diagnostician**: (1) **no Rust reads `trader_type`** — live
  filter is `consensus_eligible OR earned_eligible` (`:1403`); the 115 flags feed only offline Python.
  (2) `quality_weight(rank20)=1.6`, not 1.8.
- **The untapped signal**: the SELL leg is captured but featurized nowhere (`advantage` NULL for SELL,
  `:1450`; `trader_slice_scores` is `side='BUY'`, `:1507`). Round-tripping — the *definition* of
  market-making — is directly measurable and currently thrown away.

Six gaps: GAP-1 no calibration/null/FP-FN (the spine); GAP-2 SELL unfeaturized; GAP-3 both-sides is
per-window not lifetime; GAP-4 single `fpd` threshold; GAP-5 `Indeterminate` fails *open* on weighting;
GAP-6 no audit trail.

## Direct Path (Agent A) — "wire up the last 20%"
One combined `trader_mm_features` aggregation → a **frozen weighted scorecard**
(0.35·two_sided + 0.20·sell_buy + 0.20·round_trip + 0.15·breadth + 0.10·flat-edge) with **one
calibrated threshold** `score_hi`; verdict `MM` iff `score≥score_hi AND two_sided≥hard AND !proven`.
Three-way `MmVerdict{Mm,Unknown,Human}`, Unknown fail-open. Calibration = labeled AUC + label-
permutation null. Weight-cap at the `earned_quality` seam (MM→0.5). Audit table (single row/wallet).
`exclude_mm` param mirroring `trusted_only`; shadow-first. **Strength**: minimal, high-reuse, and the
"one knob not five" discipline is right for N≈40 labels. **Weakness**: a summed score lets one loud
confounded feature dominate; calibration is labeled-only (circular).

## Rethink Path (Agent B) — position-level + orthogonal agreement + label-free validation
Reframe 1: classify **positions**, not wallets — aggregate BUY+SELL to `(wallet,cond,outcome)` and read
MM-ness from *how positions end* (`round_trip_rate`, `sell_buy_ratio`, lifetime `two_sided_rate`),
subsuming GAP-2+3 into one query. Reframe 2: **AND-of-K-orthogonal signals** (S1 churn, S2 both-sides,
S3 = invert-the-trust-gate: `Indeterminate AND high volume`, zero new features) — exclude only when
K≥2 agree, so FP is multiplicative. Reframe 3: **two-tier validation** — Tier-1 labeled+null, **Tier-2
label-free**: does excluding MMs improve the survivor pool's early→late persistence (−0.10 baseline)?
Weight-cap, audit table (append-only `(wallet,computed_at)` PK), shadow-first `mm_arms`. **Strength**:
the label-free Tier-2 is the only non-circular validation; orthogonal agreement is the literal "cross-
reference"; S3 is free and hard to fake. **Weakness**: 5 thresholds to calibrate on ~40 labels; the
"3 orthogonal signals" claim overstates independence (S1,S2 correlated).

## Reality-check findings
- **RC-1 (B, real)**: S1(churn) and S2(both-sides) are both "how they trade" and correlated → not 2
  independent votes. The genuinely orthogonal split is **structural(S1∨S2) AND edge(S3)**. → refined
  the verdict to a 2-axis conjunction.
- **RC-2 (A, minor)**: A's scorecard is *already* a conjunction (`score≥hi AND two_sided≥hard AND
  !proven`), so A and B converge more than they appear — both gate on structural evidence + no proven
  edge.
- **RC-3 (decisive)**: labeled MM set is drawn from the same `two_sided≥0.30` heuristic under test →
  Tier-1 labeled AUC is **partly circular**. B's Tier-2 (downstream persistence effect) needs no
  labels and is the binding validation. → **B wins the validation gap.**
- **RC-4**: both independently added the `!proven` fail-open guard → load-bearing, kept.
- **RC-5**: both correctly demote `median_hold` to advisory (backfilled `resolved_at`/`ts` as-of
  noise) → non-issue.
- **RC-6**: adding `is_mm` to `TraderVote` touches **9 constructor sites** (verified) → mechanical
  cost, noted in the plan.
- **Verified real**: `selection_null.py`, `specialist_mining.py` (two-sided MECH_SQL, `≥0.30`),
  `persistence_tracker.py` all exist → clone claims hold. SELL `advantage` NULL confirmed.

## Synthesis decisions (per gap)
| Gap | Winner | Rationale |
|-----|--------|-----------|
| 1 validation | **rethink** (two-tier, label-free Tier-2) + direct's "few knobs" discipline | labeled set circular; Tier-2 is non-circular ground truth |
| 2+3 features | **rethink** position-grain `wallet_microstructure` | one query, crisper unit-of-observation; same table scan as direct's combined query |
| 4 verdict | **refined hybrid** | rethink's orthogonal-agreement spine, refined to structural∧edge∧!proven (RC-1), with direct's explicit `!proven` guard |
| 5 weight seam | **both (identical)** | `.min(cap)` at `earned_quality`; merged direct's 0.5 MM floor + rethink's 1.0 suspected cap |
| 6 audit | **rethink** append-only `(wallet,computed_at)` table | keeps verdict-drift history; both reconcile the 115 without overwriting `trader_type` |
| wiring | **both (identical)** | shadow-first `exclude_mm` arm mirroring `trust_arms`, env-gated |

## Key insight that emerged
The reliability the user asked for is **not a better separator** — it's **agreement across
orthogonal axes** (cross-reference) **validated by downstream effect** (non-circular). A churner and a
predictor can look identical on *structure* but never on *resolution edge*, so the binding rule is
"structural churn AND edge≈0-despite-volume AND not-proven." And because the labels are drawn from the
same heuristic under test, the only trustworthy validation is whether excluding the suspects makes the
surviving human pool measurably more persistent out-of-sample — the exact metric the winner's-curse
work depends on. Everything else (features, tables, weight-cap, wiring) is additive, no-op-by-default,
shadow-first plumbing over infrastructure that already exists.
