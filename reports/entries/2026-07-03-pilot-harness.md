# 2026-07-03 · WS-D — the unarmed pilot harness (build + shadow; real money = Tue only)

**One line:** built the truth-generating pilot as a **self-contained, default-OFF, NOT-wired-in**
Rust module (`copy-trading-bot/src/pilot.rs`) — de-levered ⅟₁₂-Kelly sizing, four latching
kill-switches, CLV + honest-P&L tracking — with the order path **proven unreachable by two
independent locks** (10 unit tests). The shadow replay shows the honest outcome: on today's evidence
the pilot's **own edge-degradation kill-switch self-vetoes** (WS-A's λ̂≈0.15 < the 0.25 floor ⇒ 0
bets). It places nothing. **Real money awaits Tue's go.**

## What was built (all additive, nothing wired into the running binary)
`copy-trading-bot/src/pilot.rs` (+ `mod pilot;` declaration only — `live.rs` never calls it, so the
daemon is byte-identical):
- **Sizing:** `delevered_stake_frac(c, p, k)` = the exact two-outcome Kelly of `risk_engine`,
  de-levered by `k=⅟₁₂` (WS-B) and hard-capped at 5% of bankroll.
- **Kill-switches (`KillSwitch`, latching):** DayStopLoss (5%/day), MaxDrawdown (15% peak-to-trough),
  **EdgeDegraded** (halts when the live λ̂/CLV estimate falls below `min_lambda`=0.25), and the manual
  master switch. **Safety-first: a `KillSwitch` is halted FROM BIRTH** when `master_on=false` (the
  default) — it evaluates at construction, so the default state places nothing before any fill. (This
  was a real gap the tests caught: `new()` originally didn't evaluate.)
- **Two locks on the place path (`OrderGate::place`) — provably unreachable in this build:**
  1. unarmed ⇒ `NotArmed` (needs `PILOT_ARMED=1`, the single env gate Tue controls);
  2. even armed + un-halted + positive stake ⇒ `NoPlacer` — the bot is paper-only, **no order client
     exists**, so it physically cannot submit. A halt in between ⇒ `Halted(reason)`.
- **Ledger (`PilotLedger`):** CLV + realizable-P&L per fill, per-day reconciliation.
- **10 unit tests PASS**, incl. `place_refuses_when_unarmed`, `place_refuses_even_when_armed_no_placer`,
  `master_off_halts_by_default`, and each kill-switch tripping. Gate: fmt + clippy (`-Dwarnings`) +
  test all green on the workspace.

`scripts/pilot_shadow.py` — a paper replay mirroring the pilot rules (the Rust module is the source of
truth for real money; this is for the report). `--selftest` PASSES (sizing/pnl parity + self-veto).

## The shadow (favorite, 232 resolved positions, WR 93.1%, δ +0.112; $500 bankroll, ⅟₁₂-Kelly)

| mode | λ | bets | equity | ROI | maxDD | halt |
|---|---:|---:|---:|---:|---:|---|
| **honest (WS-A λ̂)** | 0.15 | **0** | $500.00 | +0.0% | 0.0% | **EdgeDegraded (self-veto)** |
| counterfactual | 0.50 | 229 | $819.63 | +63.9% | 3.7% | — |
| counterfactual | 1.00 | 78 | $618.67 | +23.7% | 7.8% | **DayStopLoss** |

- **Honest outcome: the pilot self-vetoes.** WS-A's measured λ̂≈0.15 is below the 0.25 edge floor, so
  the edge-degradation kill-switch halts it before a single bet. The harness, run honestly on today's
  evidence, **refuses to bet** — the safety property working as designed.
- The counterfactuals show the machinery IF λ were measured above the floor. Note λ=1 (aggressive
  sizing) trips the **day-stop** after 78 bets — bigger Kelly stakes → bigger swings → the kill-switch
  fires. That is the de-lever lesson (WS-B) in miniature and validates why `k` is pinned LOW.

## Go/no-go conditions (the harness is one-approval-away; these gate the real-money flip — Tue's)
1. **λ measured above the floor.** Dense capture ON (WS-A), ≥2 weeks of real CLV, `clv_lambda.py`
   emits λ̂ with a CI whose lower bound clears `min_lambda`. Today it does not (self-veto).
2. **Persistence (D7).** Independent-cluster count across ≥5 non-expiring regimes (months) — the
   standing gate, unchanged. CLV shortens the wait; it does not replace this.
3. **Sizing pinned (WS-B done):** ⅟₁₂-Kelly knee, ⅟₁₆ conservative, flat floor.
4. **Kill-switches + tiny bankroll wired and drilled** (built; wiring into `live.rs` is the
   approval-gated step, behind `PILOT_ARMED` + master switch).

## STOP → Tue's decision
The place path is unreachable without `PILOT_ARMED=1` **and** master-on **and** no latched halt — none
hold in this build (proven). **Committing real money to the pilot is one of the two Tue-only
decisions.** This run merges the unarmed harness + shadow and stops. Nothing is armed; the daemon is
unchanged.
