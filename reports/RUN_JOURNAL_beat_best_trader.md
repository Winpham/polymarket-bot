# Run journal — "Beat the Best Tracked Trader"

Prereg frozen: 2026-07-05T18:30:36Z · branch run/beat-best-trader · PAPER-ONLY · nothing promoted.

---

### Run beat-best-trader — cycle 1 — 2026-07-05T18:45Z
ACCRUAL: distinct events (favorite) 146, distinct days 5, disjoint sport-regimes positive 2–3/13
  (nba +0.47 n=6, soccer +0.08 n=96, tennis +0.86 n=1 — all thin/expiring).
λ̂: 0.144 CI [0.074, 0.278] (floor 0.25 → **BELOW**). Dense-capture ask coverage: **0.6%**
  (traj started 2026-07-03; 2 of 307 favorite positions have real trajectory).
ELIGIBILITY / MM-FILTER (H7): eligible (relaxed τ_rt=0.50) **264** vs frozen (0.30) **224** →
  relaxed **restores 40** directional wallets. A4 reconciliation (200 half-eligible): both=61 |
  micro_only=38 | bot_only=30 | clean=71. Cohort fwd copy-return: **frozen −2.7% = relaxed −2.7%**
  (no-downside; DECAYED from the D29 +0.043/+0.045 — now NEGATIVE). Profit-source (mm_persistence):
  removing flagged wallets does NOT raise persistence (Δcorr −0.066, p_emp 0.637) → NO-GO.
BEAT-BEST-TRADER BENCHMARK (PREDICTORS ONLY, repriced at our entry):
  overall B_LB=−0.112 (0x99e42eb9), B_point=+0.225 (MM=False, selection-inflated), N_elig=98,
  copyable=49. Every context B_LB negative except `other` +0.043 (noisy, single-cluster).
  → **INDETERMINATE-BY-POWER**: per-wallet effective_n≈1–3 days ⇒ Bonferroni LB uninformative.
OPERATOR HEAD-TO-HEAD (OUT set):
  ROUTER fwd surplus_vs_fleet = **−3.8%** (LB −16.7%, 40 days), perm-null p_emp=**0.70** (NO edge).
  SKILL-WEIGHTED (trust_weighted) honest ledger = **−21.8%** (worst arm); at-fire +7.4% does not survive.
  FLEET-AVG incumbent honest ledger ≈ **−14%** (loose/strict/count/whales); favorite-concentrated +5.6%.
  B_LB = −11.2%.
  H3 within-trader LOO routing-vs-averaging: SIGNED = **relaxed meanΔ −0.077 (cond, CI[−0.44,+0.29],
  5/10 pos) / −0.044 (abstain-as-0, CI[−0.31,+0.22], 7/13)** → **INDETERMINATE, point mildly favors
  AVERAGING**. Frozen screen: −0.144 / −0.065 (also INDETERMINATE). Single-wallet argmax is dominated
  by idiosyncratic per-wallet variance (one wallet 0x4f1af091 drives nhl +0.76 / crypto +0.34 wins AND
  other −0.43 / cs2 −0.96 losses).
CANDIDATE ARMS: favorite — honest LB −4.6%, promotion=SELECTION-REAL(null) but pilot=HOLD (5 days
  < 50 events / <5 day-regimes), λ̂ CI-lo 0.074<0.25 → self-veto, beats_best_trader=INDETERMINATE-BY-POWER.
  Nothing clears the full gate.
FADE PROBE (H5): discovery-cell soccer/directional/b5 NO net_edge +8.2% (p=0.001, z=−4.6) — but
  transfer to non-soccer band5 = **ZERO** (tennis flips YES p=0.56; other +1.3% not soft; crypto −0.8%).
  → HOLD (SOCCER-ARTIFACT, fails anti-overfit transfer guard).
RELATIONAL (relational_probes): DEFERRED this cycle (blind-universe permutation slow; relational
  fitting is graveyard on current data — does not change any verdict).
VERDICT THIS CYCLE: **nothing promoted — INDETERMINATE-BY-POWER** across H1,H2,H4,H6,H7-persistence;
  H3 signed = INDETERMINATE (point favors averaging); H5 = HOLD (no transfer).
BINDING CONSTRAINT: **persistence** (ETA months) — regime=SOCCER-ARTIFACT; 0/4 recurring regimes clear
  floor; nearest actionable lever = dense-capture coverage (λ̂ measurable).
NEXT: non-soccer regime population (esports/NFL Sept/NBA Oct) + dense-capture accrual to lift λ̂ coverage
  from 0.6% toward 50%.
WATCH-LIST: (1) mm_screen_refinement — relaxed ≥ frozen holds, re-confirm on +1 forward week before any
  Rust change (Phase-1 STOP). (2) favorite arm — closest to gate but pilot/λ̂/persistence all block.
  (3) soccer band5 fade — real in-cell; watch for a non-soccer band5 soft cell to appear.
