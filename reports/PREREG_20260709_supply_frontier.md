# PRE-REGISTRATION — Supply-Frontier Arms `frontier_k3e` (primary) + `frontier_k2a` (explorer)
(frozen 2026-07-09, before any forward outcome)

Run: FABLE build run 2 (FABLE-SUPPLY-FRONTIER-RUN.md). Branch `feat/supply-frontier`.
Frozen BEFORE either arm emits a single forward signal. The replay evidence in the run doc
is MOTIVATION ONLY: it was produced by an 8-config in-sample sweep (multiplicity
uncorrected), at a proxy entry the paired-tape test showed flatters by ~2.4c median, over
a window whose tape segment is unusable after the 72h resolution guard (recency-censored,
winner-enriched), against baselines two independent adversarial audits found broken
(champ-replica ≠ live champion; blind pool adverse). None of it certifies anything.
This document is the contract.

SUPERSESSION NOTE: `favorite_wide_anchored` (prereg 2026-07-08) is REMOVED from the arm
set before ever emitting a forward signal (the flag was never flipped). Its diagnostic
role (deep-confirms vs deep-alone) is carried by `frontier_k2a`'s anchor mechanism. This
supersession is documented here and in both run docs — it is a pre-outcome design change,
not a post-outcome edit.

## The claims under test (stated so they can lose)

PRIMARY — `frontier_k3e` (favorite_wide + 60s echo-independence; the guarded replay's
only both-clusterings-positive config: n=121/8d, +5.3% proxy, LB_ev +1.1%, LB_day +1.2%,
incremental 79 @ +6.2% — in-sample, proxy-priced, pre-multiplicity):

S1 (SUPPLY): `frontier_k3e` adds a resolved fire-rate ≥ 1.5x the concurrent live
champion's, with ≥ 50% of fires on (condition,outcome) legs the champion never fires
(incremental legs).

S2 (EDGE, non-inferiority — per the methodology audit, NOT superiority): on incremental
legs, at the captured decision-time `entry_ask` ONLY (rows without a real captured ask are
EXCLUDED from the primary metric, not COALESCE-filled), the event-clustered ROI lower bound
(t(G-1), one-sided 95%) is > 0 AND the arm's ROI is not inferior to the concurrent live
champion's same-basis ROI by more than 3pp (the standing gate's margin, used as a
non-inferiority margin).

EXPLORER — `frontier_k2a` (2 echo-independent backers + ≥1 top-40 anchor): carries NO
edge claim. Guarded replay shows ~2.3x supply at incremental ROI ≈ +0.7% with negative
LBs; the earlier "+7.7% at tape ask" read is RETRACTED (recency-censored). It runs to
settle the delayed-mirror question with forward real-ask data; it is judged by the same
kill criteria below and dies quietly if they fire.

H0 kills (named in advance):
- DELAYED-MIRROR KILL (strategy audit K5): incremental legs are late re-detections of
  top-40 activity at drifted prices. Test: incremental-leg real-ask ROI LB_day ≤ 0 at the
  floors → the arm dies. Supporting diagnostic (PAID-DRIFT SHARE): fraction of fires where
  the anchor (top-40) fill precedes the gate-completing fill by > 10 min AND the tape ask
  moved > 2c against us in between; > 50% paid-drift share with LB_day ≤ 0 confirms the
  mirror mechanism, not just the outcome.
- SMALL-CELL MIRAGE KILL (strategy audit K2): the edge concentrates in n<10 sport cells.
  Test: report per-sport with day-clustered LBs; a GO requires the pooled LB to survive
  REMOVING every cell with n < 15 (leave-worst-cells-out is not allowed; this is
  leave-SMALL-cells-out, size-defined, not outcome-defined).
- ECHO KILL: >25% of fires would lose gate-eligibility at a 15-minute echo window
  (the shipped 60s window is a floor; the 15-min diagnostic is measured forward and
  reported — if the wide pool is minutes-scale herding, the 60s guard is cosmetic).

## Frozen arm definitions (as shipped)

Both on the WIDE book (`load_wide_window_votes` = eligible ∪ tracked deep non-bot),
silent, EXPERIMENTAL family, $100 flat, decision-time entry_ask capture, window 48h,
max_opposers ≤ 1, price_std ≤ 0.10, band 0.65–0.98:
- `frontier_k3e`: min_backers=3 counted echo-independently (60s collapse). No anchor.
- `frontier_k2a`: min_backers=2 counted echo-independently (60s collapse), plus ≥1 backer
  ranked ≤ `TRACK_CONSENSUS_RANK_CUTOFF` (40).
Config selection rationale: `frontier_k3e` is the guarded replay's only positive-LB
config; `frontier_k2a` is SUPPLY-STRUCTURAL (largest supply at the flat frontier), not
LB-selected. Anchor-depth insensitivity (40 vs 100 indistinguishable) and the rejections
(opp0, anchor10, band60, unanchored k2) are documented in the run doc.

Baselines that ship WITH it: `_blind_wide` (pool-matched capture-all; selection-null
population), and the concurrent live `favorite` record (the ONLY champion baseline —
the replay's champ-replica is explicitly disqualified per the methodology audit #1).

## Frozen measurement protocol

- Basis: real captured `entry_ask` rows only, for both the arm and the champion
  comparator, same days. Fallback-entry rows appear in a secondary table only.
- Resolution guard: signals detected within 72h of any measurement snapshot are excluded
  (losers resolve ~2x slower; floating-window recency is winner-enriched — audit #2).
- Clustering: event-cluster primary, day-cluster persistence wall, BOTH reported; plus a
  game-cluster read (super_event grouping) before any promotion discussion (audit K6).
- Floors: ≥ 30 resolved incremental real-ask signals AND ≥ 10 distinct day-clusters AND
  ≥ 2 disjoint sport-regimes surviving the small-cell rule. Below floors the only legal
  verdict is INDETERMINATE-BY-POWER (accrue).
- Multiplicity: the arm is judged alone (one primary hypothesis S2). The sibling wide
  arms (favorite_wide, favorite_wide_anchored) remain under their own 2026-07-08 prereg.
  Nothing here revises the core family's Bonferroni bar (EXPERIMENTAL family).
- Selection-null: `selection_null.py` vs the `_blind_wide` population, p ≤ 0.01, as a
  necessary supporting check (the blind pool is adverse — audit #4/K3 — so passing it is
  NECESSARY not sufficient; the primary is absolute real-ask ROI vs champion).

## What a GO would mean (and what it can never mean)

A GO here promotes NOTHING live. It qualifies the arm for the standing promotion
discussion (human decision, gate LB > 3% etc.). Paper-only forever under the current
legal posture (D26). A verdict of INDETERMINATE stays INDETERMINATE — "real-but-thin,
accrue more" is the only honest phrasing.
