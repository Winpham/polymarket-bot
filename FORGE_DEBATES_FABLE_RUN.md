# FORGE_DEBATES_FABLE_RUN — design record (2026-07-02)

Note on process: the forge normally fans out to 4 agents; this host could not fork subagents
mid-run (pty exhaustion), so the diagnostician/designer-A/designer-B/verifier passes were run
inline, sequentially, against the live code + DB. The dossier that seeded them is preserved at the
session scratchpad (`FORGE_DOSSIER.md`); its live-DB evidence is reproduced in the plan.

## Diagnostic highlights (beyond the run charter's own findings)
- `initial_mean_price` coverage is 100% on all 15.7k rows (COALESCE is only belt-and-suspenders).
- Scoreboard consumers: board.rs:347, telegram commands.rs:69, enrich/mod.rs:525 (e2e test). No
  other reader of `StrategyScore`. The fix is a single query body.
- `honest_pnl_by_strategy` does NOT suffer F1 for its own metric: entry is
  `COALESCE(entry_ask, initial_market_price + h)` (both set-once). Only its reference-only
  `sharp_adv` column uses drifted `mean_price` — deliberately KEPT (see debate 2).
- Resolution path healthy: `unresolved_consensus_signals` has no LIMIT; the 1.8k >30h unresolved
  are unplayed fixtures (CLOB `closed:false` spot-checked), not a backlog defect.
- Migrations 026-031 exist → next free is 032; NOT needed (no schema change in this run).

## Debate 1 — F1: in-place SQL fix vs parallel flagged scoreboard
- A (direct): edit the query in place; the drifted entry is a bug vs the documented at-fire spec.
- B (rethink): add `_atfire` twin + config flag, keep both on the board.
- Verifier: the guardrail says PROVE strictly better, not keep both forever. A twin permanently
  doubles every future consumer and leaves the false-negative primary. Chosen: **in-place + parity
  harness + drift regression test** (A's edit, B's evidence standard). K1 kill-criterion binds.

## Debate 2 — should `sharp_adv` / honest "sharp edge" also switch to at-fire?
No. `sharp_adv = won − mean_price(final)` measures the SHARPS' realized average fill — final mean
IS their completed average entry; it is reference-only and never judges promotion. The gate's
surplus judges OUR at-fire action point. Both facts documented at the query. This distinction is
why F1 is a bug and not a modeling choice: the gate was always speced as "what we act on at fire".

## Debate 3 — F2: Python instrument vs Rust in-gate null
- A: `scripts/selection_null.py` mirroring asof_preflight.py (stdlib, seeded, reproducible).
- B: port to promotion.rs so the board renders null-p per strategy each refresh.
- Verifier: B needs an RNG dep + an exact Rust mirror of SQL statistics (drift risk between two
  implementations of the same statistic), for a number that changes only when resolutions land.
  Chosen: **A**, with the pre-registered combined rule (LB ∧ p≤0.01 ∧ ≥2 sport-regimes) written
  into promotion.rs docs + board footnote so the human promotion call is bound to it. Revisit B
  only if promotion decisions become frequent enough that ad-hoc runs are the bottleneck.
- Null design points settled: sampling INCLUDES strategy-picked rows in the `_blind` pool (correct
  null: "random selection from the same observed universe at same composition"); cells with pool
  smaller than the pick-count fall back to with-replacement draws (variance impact negligible,
  documented); calibration mode is mandatory before first use (K2).

## Debate 4 — F4: instrument-first vs gate-requirement now
Tightening `pilot_verdict` with a sport-regime condition today changes rendered verdicts for zero
benefit (nothing is GO) and adds an untested condition to a shared verdict fn. Instrument-first
wins; the flip to a hard requirement is itself pre-registered as a later change once ≥3 sports have
floor-N. The rule ALREADY binds human promotion via Item 2's combined rule (c).

## Debate 5 — F6: schema/mode vs query-derived flat-shares
Ledger rows already store (entry, outcome_won, stake) → flat-shares P&L is pure arithmetic at query
time. Never rewrite/extend a durable forward ledger for a derivable number. Query-derived wins.

## Debate 6 — what NOT to do (explicitly parked)
- No promotion of `elite_fresh_fav` (N=38 < 50 floor; tennis regime N=17 thin). Re-read post-Wimbledon.
- `longshot`'s selection signal (null p=0.007) is real-but-cost-dead per standing findings — recorded
  as an instrument observation only; no arm, no bet, no Bonferroni slot.
- `market_resid` stays OFF (refuted 2026-07-01); nothing in this run touches it.
- No relational-consensus building (data-starved; standing decision).
- No crypto-consensus arm: strategies never fire there (consensus is sports-concentrated); crypto
  mass is baseline-only. Noted for the accrual watch, not built.
