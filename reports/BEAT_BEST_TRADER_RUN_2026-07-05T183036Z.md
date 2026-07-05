# FINAL REPORT — "Beat the Best Tracked Trader" autonomous run

**Prereg frozen:** 2026-07-05T18:30:36Z · **branch:** run/beat-best-trader
**Posture:** PAPER-ONLY. Nothing promoted to real money. No Rust threshold mutated (D29 Phase-1 STOP
holds). `selection_null.py --calibrate` **PASSED** (p<0.05 at 10% ≤ 20%; mid-range 66% ≥ 60%) →
every downstream null verdict below is trustworthy.

---

## 1. One-line verdict
**Not yet certifiable — and this cycle produced a genuine negative signal, not just "no power":** at OUR
realizable entry the router (argmax-tail-the-best) forward surplus is **−3.8%, indistinguishable from a
matched null (p=0.70)**, and the one decidable-now experiment (H3 within-trader leave-one-sport-regime-out)
puts the routing-minus-averaging point estimate **mildly NEGATIVE (−0.077, CI straddles 0) → INDETERMINATE
but leaning AVERAGING**. The best-trader benchmark, router, and MM/profit-source filter are all built and
forward-accruing; the binding wall remains **persistence over independent, non-expiring regimes (months)**.

## 2. Per-hypothesis table

| H | statistic (this run) | gate verdict | binding constraint | what would flip it | ETA |
|---|---|---|---|---|---|
| **H1** router beats fleet | router fwd surplus_vs_fleet **−3.8%** (LB −16.7%), perm-null **p=0.70** | **NOT_MET** (null-indistinguishable) | forward edge is ≈0 on current (soccer-heavy) data | a real per-context routing edge that survives the matched null | months |
| **H2** router ≥ best trader (B_LB) | router raw **−6.6%** vs overall **B_LB −11.2%** (both negative) | **INDETERMINATE-BY-POWER** | B_LB uninformative: <30 tailable ev/wallet-regime, effective_n≈1–3 days | ≥30 tailable events per copyable wallet × regime | months |
| **H3** routing beats averaging (LOO) | relaxed **Δ=−0.077** cond (CI[−0.44,+0.29], 5/10 pos) / **−0.044** abstain-as-0 (CI[−0.31,+0.22]) | **SIGNED = INDETERMINATE, leans AVERAGING** | huge per-wallet idiosyncratic variance drowns the routing signal | more sport-regimes per wallet to shrink the CI | now→weeks |
| **H4** skill-concentration on FLB | trust_weighted honest ledger **−21.8%** (worst arm); favorite-concentrated +5.6% | **NOT_MET / INDETERMINATE** | skill weight helps at-fire (+7.4%) but is destroyed by follower-tax to realizable | a concentration that survives repricing + passes null | months |
| **H5** fade overhyped band5 | soccer/directional/b5 NO **+8.2%** (p=0.001, z=−4.6) but **0/3** non-soccer band5 transfer | **HOLD (SOCCER-ARTIFACT)** | edge confined to discovery cell; fails transfer guard | a non-soccer band5 soft cell appearing OOS | months |
| **H6** λ̂ real | λ̂ **0.144** CI **[0.074, 0.278]**; dense-capture coverage **0.6%** | **BELOW floor** (CI-lo 0.074 < 0.25) | trajectory coverage 0.6% (dense capture only live since 07-03) | dense-capture coverage → ~50% (≈2–4 wk) | weeks |
| **H7** filter by profit-source not order-type | relaxed cohort-fwd **−2.7%** = frozen **−2.7%**, relaxed **restores 40** directional wallets; persistence-lift NO-GO (Δcorr −0.066, p=0.637) | **direction HOLDS (no-downside); persistence-lift INDETERMINATE** | cohort forward-return has decayed NEGATIVE; single 4-day record | re-confirm relaxed ≥ frozen on ≥1 more independent forward week | weeks |

## 3. The three-way operator number (router vs skill-weighted vs fleet-average vs B_LB)

**Temporal / forward split** (router_verify, event-clustered, day-deflated, repriced at our entry):

| operator | forward surplus vs fleet-day blind | LB95 | null p | note |
|---|---|---|---|---|
| ROUTER (argmax + abstain) | **−3.8%** | −16.7% | **0.70** | no edge vs matched null |
| SKILL-WEIGHTED (trust_weighted) | honest ledger **−21.8%** | — | — | at-fire +7.4% does not survive the follower tax |
| FLEET-AVERAGE (incumbent broad arms) | honest ledger **≈ −14%** | — | — | favorite-concentrated arm +5.6% is the only non-negative |
| B_LB (best copyable wallet, repriced) | **−11.2%** (overall) | — | — | uninformative (Bonferroni over thin per-wallet days) |

**Within-trader LOO split (H3, the decidable-now three-way core — router vs averaging per held-out
sport-regime, relaxed screen):**

| regime | n_elig | n_ev | averaging | router | Δ (router−avg) | pick |
|---|---|---|---|---|---|---|
| nhl | 18 | 81 | −0.133 | +0.627 | **+0.759** | 0x4f1af091 |
| crypto | 32 | 395 | −0.115 | +0.228 | +0.343 | 0x4f1af091 |
| lol | 52 | 237 | −0.028 | +0.277 | +0.305 | 0x4f1af091 |
| tennis | 46 | 349 | −0.201 | −0.051 | +0.151 | 0x65018f9f |
| nba | 52 | 761 | −0.035 | −0.026 | +0.009 | 0x499f1381 |
| soccer | 218 | 2438 | +0.030 | −0.065 | −0.095 | 0x96a3a4d0 |
| ufc | 29 | 131 | −0.235 | −0.477 | −0.241 | 0x4f1af091 |
| other | 84 | 865 | −0.019 | −0.446 | −0.426 | 0x4f1af091 |
| mlb | 50 | 1361 | −0.052 | −0.662 | −0.610 | 0xc660ae71 |
| cs2 | 38 | 497 | −0.060 | −1.020 | −0.960 | 0x38337de2 |
| dota/nfl/politics | | | | ABSTAIN | — | |
| **aggregate (cond-on-pick)** | | | | | **−0.077** CI[−0.438,+0.285] | 5/10 pos |
| **aggregate (abstain-as-0)** | | | | | **−0.044** CI[−0.313,+0.224] | 7/13 pos |

## 4. THE NOW result (H3), stated plainly
On the cross-context variance we have TODAY, **argmax-routing does NOT beat fleet-averaging** — the point
estimate is mildly negative (routing loses by ~4–8 pp) and the confidence interval is far too wide to call
either way (**INDETERMINATE, leaning AVERAGING**). The mechanism is visible in the per-regime table: a
single wallet (0x4f1af091) wins big where it happens to be hot (nhl +0.76, crypto +0.34) and loses big
elsewhere (other −0.43, cs2 −0.96, ufc −0.24). **Single-wallet routing trades fleet-mean regression for
idiosyncratic single-wallet variance, and on this data that trade is not paying.** This does NOT refute the
"beat the best trader by routing" thesis (the CI includes large positive values), but it is the first
signed, leak-free piece of evidence and it **does not green-light the router** — it says the router needs
either (a) ≥2 conditionally-independent specialists co-agreeing per context (the built-but-unpopulated
congregation precondition) or (b) far more sport-regimes per wallet to shrink the variance, before routing
can be expected to beat averaging at our price. Relaxing the MM screen (τ_rt 0.30→0.50) makes routing
marginally LESS bad (Δ −0.077 vs frozen −0.144), consistent with H7 — but still INDETERMINATE.

## 5. λ̂ status
**Proxy, not measured.** λ̂ = 0.144, CI [0.074, 0.278]; **CI-lower 0.074 is well below the 0.25 floor** →
λ̂ self-veto is active (any candidate is auto-vetoed from promotion). Dense-capture trajectory coverage is
only **0.6%** (2 of 307 favorite positions have a real at-fire trajectory; the rest use the weak
single-snapshot mean_price proxy). Dense capture is confirmed live (DENSE_CAPTURE=true; 2800 trajectory
rows, 149 signals, since 2026-07-03) — it just needs weeks to accrue coverage toward ~50% before λ̂ is a
measurement rather than a proxy. Note: mean_CLV itself is +0.0149 with a matched-null p=0.0000, but it
explains only 14% of realized surplus — the rest is luck/static-FLB-bias, not front-run-able information.

## 6. Eligibility / MM-filter verdict (H7)
- **Relaxed round_trip (0.30→0.50) is no-downside and recovers copyable directional traders:** eligible
  pool 224 (frozen) → **264 (relaxed) = +40 wallets restored**, with cohort forward copy-return **equal**
  (−2.7% = −2.7%). This re-confirms the D29 direction: `round_trip` is a false-positive axis that flags
  directional bettors who sell to manage positions / post maker orders to dodge fees.
- **BUT the copy-cohort forward-return has DECAYED negative.** D29's addendum measured +0.043 (frozen) /
  +0.045 (relaxed); this run, on more-accrued (soccer-tournament-decayed) data, measures **−2.7% for both**.
  The screen still beats no-screen (−2.7% vs −3.5%) — it keeps arbers out — but the followed cohort is no
  longer forward-profitable at all. This is the honest update: **the copy-the-cohort premise itself is not
  currently forward-profitable**, independent of which MM screen is used.
- **Profit-source test (the user's decisive nuance):** `mm_persistence_effect` (matched-subset removal,
  2000×, as-of/leak-free) is **NO-GO** — removing microstructure-flagged wallets does NOT raise early→late
  persistence (Δcorr −0.066, p_emp 0.637). Both early→late correlations are themselves negative (−0.13 with
  flagged, −0.20 without), i.e. **wallet skill does not persist early→late on this window at all** — the
  profit-source discriminator cannot be validated here because there is no persistence signal to raise.
- **A4 two-detector reconciliation (the 40-restore / 92-exclude pool):** on 200 half-eligible wallets the
  microstructure `is_mm` screen and the repo `trader_type='bot'` detector agree on **both=61** exclusions
  and **disagree on 68** (micro_only=38, bot_only=30); membership excludes the **UNION** (mirrors the Rust
  re-scorer), leaving **clean=71**. The relaxed screen's 40-wallet restore is exactly the round_trip FP pool.
- **Nothing was mutated in Rust.** `refresh_router_followset` stays frozen at 0.30/0.25/0.50. The relaxed +
  profit-source screen lives only in the Python research layer (`mm_screen_effect.py`, `h3_loo_routing.py`
  `--frozen/--relaxed`). Phase-1 STOP holds until relaxed ≥ frozen is forward-confirmed on ≥1 more week.

## 7. Readiness-ledger delta
- **Added rows:** `router_vs_fleet` = NOT_MET (fwd surplus −3.8%, null p=0.70); `router_vs_best` =
  INDETERMINATE-BY-POWER (both negative, B_LB uninformative); `fade_transfer` = NOT_MET (1 soft cell = the
  discovery cell only, no transfer); `mm_screen_refinement` = LEAD (relaxed −2.7% = frozen −2.7%, no-downside).
- **Integrity fix:** hardened `beats_best_trader_row` with a **fail-closed guard** — when B_LB is deeply
  negative (uninformative Bonferroni floor) or the arm LB ≤ 0, it now returns **INDETERMINATE-BY-POWER**
  instead of a mechanical MET. Before the fix it falsely read MET (favorite LB −4.6% "beating" B_LB+3pp
  −8.2%) — i.e. beating a garbage floor with a losing arm. This is the exact market_resid false-promote
  class the run exists to prevent.
- **GO gates 2/4 met** (power, sizing); **real-money-eligible = False**. **Binding constraint = persistence
  (months)** — regime verdict SOCCER-ARTIFACT, 0/4 recurring regimes clear the floor, 57% of edge mass is
  in expiring (World Cup / Wimbledon) regimes. **Auto-promotion trigger:** the ledger + benchmark + router +
  fade instruments all re-run read-only and will flip the moment ≥5 non-expiring regimes accrue with
  positive, null-surviving, day-deflated LB.

## 8. NEW artifacts + DEFERRED wiring
- **NEW:** `scripts/h3_loo_routing.py` (the H3 within-trader leave-one-sport-regime-out routing-vs-averaging
  experiment; --selftest green; --frozen/--relaxed; writes `reports/h3_loo_routing{,_relaxed,_frozen}.json`).
- **EXTENDED:** `scripts/readiness_ledger.py` (+4 rows above + the beats_best_trader fail-closed guard).
- **REUSED (not rebuilt), re-run this cycle:** `best_trader_benchmark.py`, `router_verify.py`,
  `trader_scorecard.py`, `mm_screen_effect.py`, `mm_persistence_effect.py`, `regime_net_edge.py`,
  `selection_null.py --calibrate`, `clv_lambda.py`, `copyability.py`, `softness_fade.py`.
- **DEFERRED (human review only):** amending the frozen `refresh_router_followset` constants to the relaxed
  0.50 round_trip cutoff — HOLD pending ≥1 forward-week re-confirmation (Phase-1 STOP). Registering any
  `consensus_fade` / router StrategyDef — HOLD (H5 fails transfer; router fails the null). `SLICE_POOLED`
  env-flip — deferred (requires a main-repo compose edit + live-bot rebuild; the measurement core does not
  depend on it; DENSE_CAPTURE + CONSENSUS_TRUST_ARMS were already live).

## 9. What this run did NOT do, and why
- **Promoted nothing to real money** — by construction (PILOT_ARMED unset; pilot.rs unwired). Every
  candidate failed ≥1 gate: favorite passes the selection-null but fails pilot_verdict (5 days < 50 events /
  <5 day-regimes), fails λ̂ (CI-lo 0.074 < 0.25), and sits under a SOCCER-ARTIFACT persistence wall.
- **Mutated no Rust threshold** — the relaxed/profit-source screen is Python-research-layer only.
- **Did not flip SLICE_POOLED** — it needs a main-repo compose edit + bot rebuild (a main-checkout change
  the isolation rule warns against), and nothing here depends on it. DENSE_CAPTURE (the λ̂-relevant flag)
  was already live; I confirmed it is accruing.
- **Did not certify a best-trader floor** — B_LB is uninformative today (per-wallet effective_n≈1–3 days ⇒
  Bonferroni-crushed). Correct output is INDETERMINATE-BY-POWER, not a fabricated pass.
- **The desert and the wall:** the paper ledger is ~5 correlated days of one soccer tournament plus thin
  spillover into other sports; cross-CONTEXT variance is now enough for a signed H3 read, but cross-TIME
  accrual (independent, non-expiring day-clusters) is still a handful. **Beating the best tracked trader at
  our realizable price is not provably possible on today's data — and the first signed evidence (H3) leans
  the other way (averaging ≥ routing).** That is the honest, first-class result of this run.

---
*Instruments are read-only; measured directly against prod container `polymarket-bot-postgres-1` with zero
write statements (no `pg-report` snapshot was cheaply available). All artifacts in `reports/`.*
