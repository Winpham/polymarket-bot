# PRE-REGISTRATION — `favorite_opposed`: the opposed-favorites challenger

**UTC stamp:** 2026-07-09T03:45:00Z · **Arm:** `favorite_opposed` (silent, EXPERIMENTAL
family — never tightens core's Bonferroni bar) · **Branch:** `feat/exec-policy`.
Paper-only; alerting false; replaces nothing; judged ONLY by the standing gate.

## Provenance (why this is not a fresh data-dredge)

- **Nominated 2026-07-02** by the pre-registered slice study (entry 10): favorite∩opp≥1,
  forward read gated at 30 NEW events — one of exactly two nominations, chosen before
  any of the data below existed.
- **Forward window (2026-07-02 16:45 UTC → 2026-07-08, fully out-of-sample):** the due
  read at 39 events: opp≥1 **+2.58%** honest ROI (62 sig, WR 85.5%) vs complement
  opp=0 **−2.78%** (89 sig) — while ALL favorite ran **−0.58%** over the same window.
- **Whole record, event-clustered:** opp≥1 **+11.26%/event (SE 3.57%, 85 events)** vs
  opp=0 **−0.73% (124 events)**. The champion's entire edge concentrates in the
  opposed slice.
- **Mechanism:** ≥1 opposing sharp means the market has NOT fully converged on the
  favorite — the price still carries disagreement premium; unopposed consensus is
  already in the price. (Slice study's "capital-efficiency" cell, now with a forward
  confirmation.)

## Definition (frozen)

`favorite` construction with one added hard gate: `min_opposers = 1` (with the base
`max_opposers = 1`, this is exactly-one-opposer). Band (0.65, 0.98), all other knobs
identical to `favorite`. Pure subset of the champion by construction — it can never
fire where the champion doesn't.

## Judgment (frozen — nothing new invented)

The standing machinery is the sole judge: belief-blind scoreboard surplus over the
band-matched `_blind` baseline, selection-null p ≤ 0.01, Bonferroni LB > 3% margin
within the EXPERIMENTAL family, ≥30 distinct-event floor, ≥2 disjoint regime
persistence, honest-P&L realizable ROI. Promotion to alerting/pilot is Tue's decision
after the gate clears — never automatic. The historical numbers above do NOT count
toward certification (the arm accrues its own forward rows from deploy).

## Non-regression contract

Registered silent; EXPERIMENTAL family; every other strategy keeps `min_opposers = 0`
(unit-tested); default-config portfolio unchanged in behavior for all existing arms.
