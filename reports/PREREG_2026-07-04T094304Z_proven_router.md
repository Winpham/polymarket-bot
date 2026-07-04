# PRE-REGISTRATION — Proven-Trader Router (scorecard + paper arm)

**Frozen at: 2026-07-04T09:43:04Z (UTC), BEFORE any new measurement.**
Provenance: 2026-07-04 deep-dive on the live DB (memory topic `project-polymarket-refined-strategy`):
within-trader H1→H2 copy-return corr **0.338** (188 wallets, ≥100 fills/half, favorites 45–90¢);
H1 ≥10% wallets delivered **+16.2% forward**; equal-weighted all-wallet copying is **negative (−7%)**.
This registers the scorecard + router BEFORE the instrument is built, per the belief-blind protocol.
Paper-only. NO real money. Nothing here promotes anything.

## Hypotheses

- **R1 (scorecard forward validity):** the follow-set defined below has FORWARD modeled
  copy-return (a) > the all-wallet size-weighted baseline on the same cells, and (b) ≥ +10%
  at source. Prior on current data: replication of the deep-dive should hold in-sample;
  the forward read accrues from this timestamp on.
- **R2 (paper arm):** a `proven_router` paper strategy firing on follow-set wallets' fresh
  BUYs in-band accrues a forward paper record judged ONLY by the standing gate
  (promotion_verdict + selection_null --calibrate PASS + pilot_verdict + ≥2 disjoint
  sport-regimes + λ̂ CI-lower > 0.25). Expected verdict for months: INDETERMINATE-BY-POWER.
- **R3 (MM-exclusion sanity):** excluding market-maker-shaped wallets does not DESTROY the
  H1→H2 persistence (corr stays > 0); report the delta it causes on the ≥10%-cohort forward
  return (either direction is a finding, not a failure).

## Frozen scorecard definition (`scripts/trader_scorecard.py`)

- Universe: `trader_fills`, `side='BUY'`, `resolved`, entry band **0.45 ≤ price < 0.90**.
- Reprice at OUR entry (copyability.py conventions, byte-consistent):
  `our_entry = price + FOLLOWER_TAX(0.013) + band_spread(band(price))`;
  `copy_return = (won − our_entry)/our_entry − FEE(0.02)`.
  band_spread = pooled decision-time ask spreads (copyability.py `band_spreads()`);
  missing band ⇒ 0 (conservative only for spread-free markets; reported).
- Clustering: event = `COALESCE(event_slug, condition_id)`; per-wallet mean is the
  event-clustered mean; SE day-deflated (`effective_n` = distinct UTC fill-days).
- **Membership (the follow-set):** trailing **365 days**, **≥100 resolved scored fills**,
  **≥15 distinct fill-days**, event-clustered modeled copy-return **≥ +10%**, and NOT
  MM-excluded. Also reported (not gating): the strict set with Bonferroni LB > 0
  (alpha/N_eligible, day-deflated SE).
- **MM exclusion (interim, frozen; to be reconciled with FORGE_PLAN_MM_FILTER when built):**
  position-grain microstructure over ALL fills (BUY+SELL) — exclude a wallet iff
  `round_trip_rate ≥ 0.30` OR `two_sided_rate ≥ 0.25` OR `sell_buy_ratio ≥ 0.50`.
  (Separates the D26 churner 0.78/0.64/0.92 and the patient MM 0.71/0.61/0.88 from the
  WC-burst human 0.04/0.02/0.05 with wide margin.) Exclusion lists are REPORTED in the JSON
  so the future calibrated MM verdict can reconcile against them.
- Re-score cadence: on demand + at least daily while the arm runs; the JSON is the arm's input.
- Self-check in-script: replicate the H1→H2 split (equal-halves by time per wallet, ≥100
  fills/half) with and without MM exclusion; `--selftest` on synthetic fixtures (one skilled
  wallet ⇒ in set; noise wallets ⇒ out; churner ⇒ MM-excluded) must pass before any live read.

## Frozen paper-arm definition (`proven_router`)

- Fires on a fresh follow-set wallet BUY in band 0.45–0.90 (one signal per (market, outcome),
  standard dedup); sizing **flat-shares**; `alerting: false`; env-gated **default OFF**
  (`PROVEN_ROUTER`), set in BOTH `.env.consensus` and the compose `environment:` block.
- Never touches the live alert path or the pilot; PILOT_ARMED stays unset; EARN_DEEP_SHARPS
  stays false.
- Judged by the standing gate only. The discovery data (≤ 2026-07-04) is IN-sample by
  construction; certification reads use `first_detected_at ≥` this prereg timestamp.

## What would falsify / stop this

- R3 fails hard (persistence corr ≤ 0 after MM exclusion) ⇒ the deep-dive lever was
  MM-contaminated; report and HOLD the arm.
- selection_null --calibrate FAIL on router picks ⇒ verdicts void; HALT and report.
- Any threshold tuning to manufacture a pass = the market_resid failure class; forbidden.
