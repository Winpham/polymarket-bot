# HANDOFF — HUMAN REVIEW (beat-best-trader run, Cycle 6, dormancy)

**For:** Tue · **Branch:** `run/beat-best-trader` · **Posture:** PAPER-ONLY, nothing promoted, nothing
armed, no Rust/migration touched, DB read-only. **Status:** this run is going **DORMANT**. Five cycles
established that nothing clears the belief-blind gate on the current ~5-day record and the only remaining
lever is forward accrual over **months** of independent non-soccer regimes. This doc hands off (a) the two
**real wins** that need a human + Rust decision before they can be frozen, and (b) how to check whether any
frozen play has moved toward GO while the run sleeps.

**D29 Phase-1 STOP holds:** both wins below are **DEFERRED**. They are NOT applied. They change a GO-gate
input and/or a cost constant that the live capture/scoring path uses; a silent mid-run swap is exactly the
failure mode the STOP exists to prevent. Apply only with your review.

---

## WIN #1 — The modeled follower tax overstates the real cost (correct `FOLLOWER_TAX`)

**Claim.** Every Cycle 1–4 realizable verdict rested on a **MODELED** follower tax
(`FOLLOWER_TAX = 0.013` + per-band `band_spread`, ≈ **2.9¢** fill-weighted). Cycle 5 **MEASURED** it from
real captured asks: the real follower tax is **~1.0¢ band-aware** — roughly **⅓** of modeled at the
pooled level, and lighter than modeled in the favorite band the plays live in (band 5: **0.9¢** measured vs
2.4¢ modeled). The modeled tax is a **partial modeling artifact**.

**Exact constants / files (research layer — Python).** The `0.013` reprice constant appears in:
- `scripts/copyability.py:41` — `FOLLOWER_TAX = 0.013` (the canonical copyability reprice)
- `scripts/trader_scorecard.py:42` — `FOLLOWER_TAX = 0.013` (feeds the drawdown/optimization our-price)
- `scripts/regime_edge.py:56` — `FOLLOWER_TAX = 0.013` (regime net-edge reprice)
- `scripts/real_tax.py:46` — its own `0.013` baseline for the modeled-vs-measured comparison
The full modeled tax = `FOLLOWER_TAX` **+** `band_spread(price)` (per-band spread from
`copyability.band_spreads()`); the ≈2.9¢ is that sum, fill-weighted.

**Live path (Rust) — already close.** The live honest-P&L / pilot reprice does **not** use `0.013`; it
uses `EXEC_HAIRCUT` (`copy-trading-bot/src/config.rs`, env `EXEC_HAIRCUT`, **default 0.01 = 1¢**) added to
the captured mid when no real book-ask was captured. **That default (1¢) already matches the measured
tax.** So the correction is primarily a **Python research-layer** fix (bring the `0.013`+spread model down
to the measured ~1.0¢ band-aware); the Rust live haircut is already right. If you ever want the research
layer and the live path to agree exactly, align both on the per-band measured values.

**Measured evidence (Cycle 5, `reports/real_tax.json`; 12,174 / 152,354 fills matched, 8% coverage, 153 markets):**

| cell | MODELED tax | REAL median | REAL mkt-clustered mean | real < modeled? |
|---|---|---|---|---|
| **overall** | **0.0289** (fill-wt) | **0.0100** | **0.0102** (pooled 0.0134) | **YES** |
| band 1 (0.0–0.2) | 0.0361 | 0.010 | 0.0223 | yes |
| band 2 (0.2–0.4) | 0.0230 | 0.000 | 0.0273 | ≈ |
| band 3 (0.4–0.6) | 0.0408 | 0.010 | 0.0259 | yes |
| band 4 (0.6–0.8) | 0.0209 | 0.010 | 0.0235 | ≈ |
| **band 5 (0.8–1.0)** | 0.0236 | 0.010 | **0.0092** | **yes (the favorites)** |

**Proposed band-aware value.** Replace the flat `0.013` + spread with the per-band **market-clustered**
measured tax `{b1: 0.0223, b2: 0.0273, b3: 0.0259, b4: 0.0235, b5: 0.0092}` (fall back to `0.013` for a
band with no measured value). This is exactly what `forward_track.py` and `drawdown_optimization.py
--real-tax clustered` already consume from `real_tax.json` — so you can preview the effect before freezing
it as the default.

**Caveat (why DEFERRED, not applied).** The measurement is **thin**: 8% fill coverage, ~2.3 days of dense
capture, and captures cluster around our own signal fires → the matched slice is biased toward
capture-adjacent (liquid, tight) moments. It is **directionally** real < modeled but **INDETERMINATE-BY-
POWER**. **Forward-confirm** (accrue coverage across more days/regimes) before freezing the constant. Note
this correction does **not** resurrect an edge: Cycle 5 showed a lighter tax lifts every book AND the best
single trader in lockstep, and the belief-blind selection-p is invariant to the tax level (~0.10) — the
wall is persistence, not the tax.

---

## WIN #2 — Promote the read-side market-key join so λ̂ becomes measurable (dense-capture coverage)

**Claim.** The dense-capture trajectory table crowds the favorite out via `DISTINCT ON (condition_id,
outcome_index)` keying to the earliest-fired **sibling**, and `clv_lambda.py` joins by `signal_id`, so it
misses those siblings. A **read-side market-key join** — attach the trajectory by `(condition_id,
outcome_index)` instead of `signal_id` — recovers the sibling-keyed coverage. **Coverage 2.0% → 19.9%
(~10×)** on resolved favorites (Cycle 5, `reports/clv_lambda_marketkey.json`).

**Exact join to change.** In `scripts/clv_lambda.py`:
- default (today): `TRAJ_SQL` (line ~80) — joins `signal_price_trajectory` by `signal_id`.
- fix (proven): `MARKET_KEY_TRAJ_SQL` (line ~100) — for each resolved signal, take the latest
  non-degenerate mid from **any** signal sharing `(condition_id, outcome_index)` at/before its
  `resolved_at`. Selected today only behind the `--market-key-join` flag (`measure(... market_key=True)`,
  writes `reports/clv_lambda_marketkey.json`).

**The promotion.** Make `MARKET_KEY_TRAJ_SQL` the **default** join so the standard artifact
`reports/clv_lambda.json` carries the recovered coverage. That artifact is the **`edge_reality` GO-gate
input** in `readiness_ledger.py` (`load("clv_lambda.json")` → λ̂ CI-lower vs the 0.25 floor). This is why
it is a **DEFERRED gate-input swap**, not a silent change: it moves a GO-gate input and touches the
read-side of the live capture/scoring path.

**Caveat (residual to 50%).** Even recovered, coverage is **19.9% < 50%** (the `K1` coverage floor still
fires), so λ̂ stays fallback-mixed and **INDETERMINATE-BY-DATA**. The recovered λ̂ = **0.136, CI-lo 0.065**
— still **far below the 0.25** edge-reality floor (the favorite surplus is ~86% longshot bias, ~14%
information). The residual from ~20% to ≥50% coverage is **pure temporal accrual**: the ~342 pre-dense-
start favorites have no trajectory and can only be filled by dense capture running forward. So promoting
the join makes λ̂ **measurable at all**, but λ̂ clearing the floor is still a months-of-accrual question.

---

## HOW TO CHECK IN (while the run is dormant)

Re-run the forward-track instrument (e.g. **weekly**) — read-only, snapshot-only, NO code change:

```
cd ~/polymarket-bot/wt/beat-best-trader && python3 scripts/forward_track.py
```

(and, for the full board: `python3 scripts/readiness_ledger.py`)

**What to look for, per play (play_A_tail = master-wuji, play_B_dabosshogg = DaBossHogg,
play_C_book = {master-wuji, acorp, Sportbetting76, DaBossHogg}):**
- **STATUS moving off `INDETERMINATE-BY-POWER`.** It stays there until forward events accrue.
  - → **`HOLD`** means enough data arrived and a *substantive* gate failed (e.g. forward realizable
    Calmar went non-positive, or λ̂ measured but below floor): the play is decided NO on current evidence.
  - → **`GO-CANDIDATE`** means a play cleared **every** gate. The script prints a loud
    **"ESCALATE TO HUMAN — do NOT auto-promote/arm"** banner. **Treat a GO on thin data as a probable
    bug**, not a green light: verify by hand, demand the months of independent non-soccer persistence,
    then it is your call behind the standing 4 GO gates. Nothing auto-promotes or auto-arms, ever.
- **Accrual columns:** `ev` (forward events), `d` (days), `regimes` (distinct **non-soccer** sport×month,
  ≥8 events each). The binding constraint is `persistence_non_soccer` → you want to see esports / NFL
  (Sept) / NBA (Oct) regimes appear and persist. **Soccer alone never counts** (the SOCCER-ARTIFACT
  lesson).
- **`first-binding`:** the first gate that fails — the one thing that governs each play's timeline.

The exact gate and the frozen plays live in `reports/PREREG_FORWARD_TRACK_2026-07-06T062517Z.md` (sealed,
do not edit — a change is a new seal). Excluded candidates and why: **Villson** (57 events < the 100
high-volume floor), **djokowin** (53% longshot > the 40% cap), **pfk.bgd** (58% longshot > cap) — the
anti-longshot / reliability-of-source screen working as intended.

---

*Cycle-6 dormancy handoff. Both wins DEFERRED (human + Rust review). Nothing promoted, nothing armed, no
Rust touched, DB read-only.*
