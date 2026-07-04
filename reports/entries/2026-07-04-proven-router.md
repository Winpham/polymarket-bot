# 2026-07-04 — Proven-trader router: the trader-selection lever, built and MM-cleaned

**What.** The 2026-07-04 deep-dive found the record's one big real lever: trader SELECTION
persists (within-trader H1→H2 copy-return corr 0.338 raw; H1 ≥10% wallets → +16.2% forward),
while equal-weight copying is negative and "top traders +80%" is survivorship mirage. This
entry ships the capture machinery, pre-registered BEFORE the instrument was built
(`reports/PREREG_2026-07-04T094304Z_proven_router.md`, thresholds frozen).

**Built (branch `feat/proven-router`).**
- Migration 039 `router_followset` — append-only follow-set batches (as-of audit trail).
- `refresh_router_followset` (Rust storage): FROZEN scorecard — trailing-365d resolved BUYs,
  0.45–0.90 band, repriced at OUR entry (+1.3¢ follower tax + pooled decision-time band spread),
  event-clustered copy-return ≥ +10% over ≥100 fills / ≥15 distinct days, MM-shaped wallets
  excluded by position-grain microstructure (round_trip ≥.30 | two_sided ≥.25 | sell_buy ≥.50;
  interim pending FORGE_PLAN_MM_FILTER's calibrated verdict).
- `proven_router` arm — `sharp_tail_fresh` construction (min_backers=1, ≤180m fresh) gated on
  the follow-set (`ConsensusParams.router_set`); alerting OFF; EXPERIMENTAL family; FAIL-CLOSED
  (unpublished or empty set counts nothing). Re-scored hourly on the trust cadence;
  `PROVEN_ROUTER` default OFF ⇒ portfolio byte-identical.
- `scripts/trader_scorecard.py` — read-only audit/replication (full distribution, R3
  persistence check with/without MM exclusion, drift vs the live set; `--selftest` green).

**First live read (the numbers that matter).**
- Follow-set = **4 wallets** of 408 scored (incl. the soccer wallet the MM-filter plan called
  the genuine directional one). The bar picks the set; nobody hand-picked the top.
- **R3 PASS:** persistence SURVIVES MM exclusion — corr 0.207 (n=92) vs 0.277 raw (n=188);
  166/258 half-qualified wallets are MM-shaped (matches D23's 59%).
- **The honest forward source edge is ~+10%, not +16%:** H1 ≥10% cohort forward (H2) copy-return
  at OUR repriced entry, MM-excluded = **+10.2%** (n=32); mid cohort −4.4%; negative −8.5%→−3.3%.
  Part of the deep-dive's +16.2% was MM contamination — the lever is real but smaller.

**Posture.** Paper-only; judged ONLY by the standing gate (promotion_verdict + selection_null
--calibrate + pilot_verdict + ≥2 disjoint regimes + λ̂ CI-lower > 0.25) on signals with
`first_detected_at ≥` the prereg timestamp. Expected verdict for months: INDETERMINATE-BY-POWER
(accrual is the binding constraint everywhere). Nothing promotes; no real money.

**Rollback.** Revert the merge (additive); or `PROVEN_ROUTER=false` + container recreate
(arm and re-scorer vanish; portfolio byte-identical).

---

## SAME-DAY ADVERSARIAL VERIFICATION (scripts/router_verify.py) — the first read was inflated

Four pre-named attacks on the +10.2% (A1 within-event leak, A2 fake-N, A3 no-blind-baseline +
permutation null, A4 market-mover reconciliation + survivorship). Results:

- **A1 (leak): CONFIRMED.** Event-safe halves (whole events assigned by first-fill time) drop the
  persistence corr 0.21 → **0.094** — much of the "persistence" was one event's fills straddling
  the H1/H2 boundary (the known within-match leak class). Cohort re-formed event-safe: n=18.
- **A2 (fake N): CONFIRMED.** Event-dedup + day-clustered SE over 47 forward days: raw mean
  −0.2%, **LB −16.5%**. The 32-wallet mean was pseudo-replication of the same games.
- **A3 (baseline + null): the surviving signal.** Surplus over the day-matched fleet blind =
  **+5.3% (LB −9.8%)**; permutation null (1000 random same-size cohorts) **p_emp = 0.034**,
  null p95 +4.7%. Selection carries real signal above chance — but it misses the p ≤ 0.01 bar
  and the LB is negative. Regime split: soccer +14% (62 ev) carries it; months Feb–Apr negative
  (thin), May–Jul positive.
- **A4 (market movers): ACTED ON.** The two detectors DISAGREE: of 161 half-eligible wallets,
  61 flagged by both, 25 microstructure-only, **26 bot-flag-only** (classify_trader_types).
  The UNION is now enforced in BOTH the Rust re-scorer (NOT EXISTS trader_type='bot') and the
  script. Today's follow-set-4 survives the union. **Survivorship: capture STOPS at
  deactivation** (245 inactive wallets, 0 fills after drop) ⇒ every forward number is
  conditioned on staying tracked (upward bias, magnitude unknown). Fix = keep polling dropped
  wallets' fills (proposed build).

**Corrected verdict:** the trader-selection lever is REAL-BUT-SMALL and NOT CERTIFIABLE today —
surplus ~+5% with a negative LB, p=0.034, soccer-carried, survivorship-biased upward.
INDETERMINATE-BY-POWER with a positive lean. The paper arm is exactly the right instrument:
forward accrual under the standing gate decides. Day profile of the cohort forward: 62% of days
raw-positive; worst days are single-event total losses — at ~2–5 events/day, all-days-profitable
is arithmetically out of reach for ANY selection at this edge size (P(day>0) rises with events/
day; ≈80+ independent events/day needed for ~85% positive days at μ≈5%, σ≈45%).
