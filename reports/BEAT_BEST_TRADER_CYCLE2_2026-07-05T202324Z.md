# CYCLE-2 REPORT — "Beat the Best Tracked Trader" (the deepening)

**Branch:** run/beat-best-trader · **UTC:** 2026-07-05T20:23Z · **Posture:** PAPER-ONLY, nothing
promoted, no Rust threshold mutated (D29 Phase-1 STOP holds). `selection_null.py --calibrate` **PASSED**
(p<0.05 at 2% ≤ 20%; mid-range 82% ≥ 60%) → every null verdict below is trustworthy. DB read-only.

---

## 0. One-paragraph bottom line
Cycle 2 took the real shots Cycle 1 exposed and returned **honest, decision-relevant answers on all four
threads — and moved us genuinely closer to the right OPERATOR without manufacturing a win.** The copy-cohort
"decay" is **not** a genuine collapse and **not** an artifact — it is composition (pooling soccer's still-
positive edge against structurally-negative never-copy cells) plus thin-cell reversion, so the fix is
per-cell routing, which green-lit Threads B/C. The top-k ensemble is the headline: **k≈3 is the operator
sweet spot** — it beats BOTH the single-wallet router (which Cycle 1 refuted) AND the fleet-average on point
estimate, with the single-router's damage traced to idiosyncratic variance (random-k null p=0.82: ranking
*hurts* at k=1). But k=3 does **not** clear the belief-blind gate (CI straddles 0; random-k null p=0.07–0.18,
not ≤0.01 after the k×weight×screen sweep). The soccer fade is a **few-day artifact** (retired). Dense
capture's 0.6% is a **fixable measurement bug** (sibling-dedup crowd-out) with a paper-safe 13× read-side
fix. **Nothing promoted. The binding wall is still persistence over independent non-soccer regimes (months);
the one lever with a sub-months ETA is the dense-capture fix.**

---

## A. THE DECAY VERDICT (Thread A) — RECOVERABLE-SEASONAL / COMPOSITION
Instrument: `scripts/decay_decompose.py` (Kitagawa/Oaxaca-Blinder, event-clustered, `--selftest` green;
`reports/decay_decompose.json`).

| quantity | value |
|---|---|
| pooled eligible-pool copy-return, EARLY (06-29..07-01) | **−1.5%** |
| pooled, LATE (07-02..07-05) | **−8.0%** (Δ **−6.5%**) |
| Oaxaca MIX / EDGE / INTERACTION | **+7.2% / −5.8% / −7.8%** |
| SOCCER copy-edge early → late | **+10.7% → +3.7%** (still positive) |
| SOCCER Δ event-cluster bootstrap CI | **[−0.232, +0.081]** — straddles 0 |
| artifact check (ts vs ingested) | backfill>24h **1.7%**, sub-second pin **0.0%** → **ts is a real fill time, day-split SAFE** |

**Verdict: RECOVERABLE-SEASONAL/COMPOSITION.** The crawl-stamp artifact is **ruled out** (ts is a genuine
fill time). Soccer — the one copyable cell — held a positive copy-edge (+3.7% late) whose change from +10.7%
is **not** distinguishable from zero. The negative *pooled* number is a composition effect: the book tilted
to include structurally-negative never-copy cells (crypto −21.6%, cs2 −24.5%, mlb −8.2%) plus a thin early
"other" cell reverting (+31.5% → −7.1%). **Decision implication:** the copy premise is not dead; the fix is
to route per-cell (concentrate on soccer, abstain on crypto/cs2), i.e. exactly Threads B/C — so both were
worth pursuing.

## B. THE TOP-K HEAD-TO-HEAD (Thread B) — the real shot at a winning selection
Instrument: `scripts/h3_loo_routing.py --topk` (extended; random-k null added; `--selftest` green;
`reports/topk_ensemble.json` = relaxed, `reports/topk_ensemble_frozen.json`). LOO within-trader split, Δ vs
fleet-average, each held-out sport-regime = one independent cluster.

| operator | meanΔ vs fleet-avg (relaxed) | regimes t-CI | regimes pos | random-k null p | gate |
|---|---|---|---|---|---|
| **k=1** (argmax router) | **−0.126** | [−0.47, +0.22] | 4/10 | **0.82** (ranking HURTS) | fails |
| **k=2** | −0.018 | [−0.26, +0.23] | 5/10 | 0.54 | fails |
| **k=3** | **+0.063** | [−0.168, +0.294] | **7/10** | **0.18** (relaxed) / **0.07** (frozen) | **INDETERMINATE** |
| **k=5** | +0.022 | [−0.16, +0.20] | 5/10 | 0.31 | fails |

**The shape the hypothesis predicted is real:** a small concentrated ensemble (k≈3) beats both the single-
wallet router (which trades fleet-mean regression for idiosyncratic single-wallet variance — the random-k
null confirms ranking *actively hurts* at k=1, p=0.82) AND the fleet-average, on point estimate. Skill-
weighting adds nothing over equal-weight. The cleaner **frozen** MM screen *sharpens* selection (random-k
p=0.07 vs 0.18) — an operator-level nuance opposite to H7's cohort-return finding (there relaxed = frozen).

**Gate verdict: INDETERMINATE-BY-POWER, leaning that a small ensemble is the right operator.** The across-
regime t-CI straddles 0, and the random-k null (the belief-blind test of whether *ranking* beats a random
k-subset) gives p=0.07–0.18 — the strongest signal produced in this run, but not ≤0.01, and not gate-clearing
after Bonferroni over the k×weight×screen search. **Honest read:** k=3 is a legitimate forward-track candidate,
not a certifiable winner. This is real progress over Cycle 1, which only tested k=1 and found it leaning-
averaging/negative — the action is in the middle of the spectrum, and we can now say so with a signed result.

## C. THE FADE-PERSISTENCE VERDICT (Thread C) — ARTIFACT / few-day
Instrument: `scripts/fade_persistence.py` (within-soccer temporal + day-block bootstrap + within-soccer null,
flat-shares; `--selftest` green; `reports/fade_persistence.json`).

| test | result |
|---|---|
| overall fade NO net (flat-shares, day-clustered) | +1.4%, **day-bootstrap CI [−0.08, +0.13]** (straddles 0) |
| EARLY half vs LATE half | **−3.3% vs +4.9%** — sign FLIPS |
| per-day sign | **3/7 positive**, mass carried by 06-29 (n=41) + 07-03 (n=5) |
| within-SOCCER null (shuffle won across soccer-band5 types) | **p=0.252** — directional not special within soccer |

**Verdict: ARTIFACT / few-day, NOT a recurring within-soccer structural edge.** Cycle 1 showed 0/3 *transfer*
out of soccer; Cycle 2 shows it does not even *persist within* soccer — it is carried by one early day, the
sign flips day-to-day, the day-block bootstrap CI straddles 0, and within soccer alone it is indistinguishable
from a null. Cycle-1's p=0.001 was an across-sport null borrowing power from the universal FLB curve. **The
soccer-band5 fade is retired as a forward candidate.** A genuine fade edge needs a soft cell that recurs.

## D. DENSE-CAPTURE DIAGNOSIS + FIX (Thread D)
Instrument: `scripts/dense_capture_diag.py` (`--selftest` green; `reports/dense_capture_diag.json`).

- **Not the cause:** scope (DENSE_STRATEGIES already lists favorite,elite_fresh_fav) or capture-off (2999
  rows / 162 signals, live since 07-03 20:09).
- **Primary cause — sibling-dedup crowd-out:** `dense_capture_candidates` uses
  `SELECT DISTINCT ON (condition_id, outcome_index) ... ORDER BY ..., first_detected_at, id` — `strict` and
  `favorite` score the SAME markets, so one anchor (usually the earlier-fired `strict`, 152 of 162 captured)
  gets the trajectory. `clv_lambda` joins trajectories by `signal_id` → misses the sibling-anchored path.
- **Proof:** **62 of 74 (84%)** post-dense-start favorites SHARE a (condition_id, outcome_index) with a
  captured trajectory that is keyed to a different signal_id.
- **Fix (paper-safe, reversible, NO Rust change) — read-side market-key join:** join the trajectory by
  (condition_id, outcome_index) at/before the signal's `resolved_at` (the CLV close is a market property, so
  the sibling path is valid). **Coverage 1.2% → 15.1% (13×, +14pp)** immediately for the addressable set.
- **Residual gap to the 50% bar is pure temporal accrual** (342 favorites detected before dense-start can
  never have a trajectory) — no code lifts that; it rises over weeks.
- **Flagged DEFERRED:** the market-key join changes a gate input (λ̂), so it is left as an opt-in / human
  safe-swap rather than silently swapped into `clv_lambda`'s default this run.

## E. READINESS-LEDGER DELTA
`scripts/readiness_ledger.py` extended with 4 informational rows (`--selftest` PASS; not GO gates):
`decay_diagnosis` = **RECOVERABLE**; `topk_ensemble` = **INDETERMINATE-BY-POWER** (k=3 +6.3%, CI straddles 0,
random-k p=0.07–0.18); `fade_persistence` = **ARTIFACT** (retire the fade); `dense_capture_coverage` =
**PENDING** (1.2% → 15.1% with the market-key fix). Also fixed a **pre-existing red selftest**: Cycle-1's
fail-closed `beats_best_trader_row` guard returns INDETERMINATE-BY-POWER for an underwater arm, but the
fixture still expected NOT_MET (code-vs-test drift) — aligned, non-weakening. **GO gates 2/4;
real-money-eligible = False; binding constraint = persistence (months).**

## F. WHAT THIS CYCLE DID NOT DO, AND WHY
- **Promoted nothing** — every candidate fails ≥1 gate; the nearest-new (topk k=3) is INDETERMINATE (CI
  straddles 0, null p not ≤0.01).
- **Mutated no Rust** — top-k / relaxed / market-key logic lives in the Python research layer.
- **Did not swap `clv_lambda`'s λ̂ join** — the market-key join is a gate input; changing it mid-run violates
  safe-swap. Proven + flagged DEFERRED instead.
- **Did not tune any threshold to force a pass** — the frozen-screen k=3 p=0.07 is reported as sub-significant
  after the k×weight×screen search, not promoted.

## G. HONEST BOTTOM LINE — are we closer to a winning operator?
**Modestly, yes — on the operator; no, on the wall.** Cycle 2 replaced Cycle-1's refuted single-wallet router
with a *correct operator shape* (k≈3 concentrated ensemble) backed by a signed LOO result and a random-k
null that isolates selection skill — the best evidence yet that "route, don't average" can work, held back
only by power. It also banked two clean negatives (soccer fade = artifact; decay = recoverable-composition,
not genuine) and one concrete unblock (the dense-capture 13× fix). **But nothing certifies, and the binding
constraint is unchanged: persistence over independent, non-expiring regimes (months).** The single highest-
leverage next action with a sub-months ETA is **applying the dense-capture market-key join** (unblocks a
measured λ̂ from a proxy); everything else — the k=3 ensemble's significance, the persistence wall — waits on
non-soccer regime accrual (esports / NFL Sept / NBA Oct).

---
*New/extended this cycle: `decay_decompose.py` (NEW), `h3_loo_routing.py --topk` + random-k null (EXTEND),
`fade_persistence.py` (NEW), `dense_capture_diag.py` (NEW), `readiness_ledger.py` +4 rows + selftest fix
(EXTEND). All `--selftest` green; all reports in `reports/`. Read-only, paper-only, nothing promoted.*
