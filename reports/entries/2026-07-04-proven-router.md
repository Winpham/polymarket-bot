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
