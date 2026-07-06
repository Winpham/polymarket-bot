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

---

### Run beat-best-trader — cycle 2 (deepening) — 2026-07-05T20:23Z
THREAD A — DECAY DIAGNOSIS (decisive, gates B/C): copy-cohort forward-return decay is
  **RECOVERABLE-SEASONAL/COMPOSITION**, not genuine soccer-decay, not artifact.
  · ARTIFACT ruled out: ts is a real fill time (backfill>24h = 1.7%, sub-sec pin = 0.0%) → day-splits SAFE.
  · Oaxaca (eligible-pool copy-return, EARLY 06-29..07-01 vs LATE 07-02..07-05):
    pooled −1.5% → −8.0% (Δ −6.5%); MIX +7.2%, EDGE −5.8%, INT −7.8%.
  · SOCCER (the one copyable cell): +10.7% → +3.7% (still POSITIVE); bootstrap Δ CI[−0.232,+0.081]
    STRADDLES 0 → soccer's own edge is intact-but-unpowered, NOT a proven collapse.
  · The negative pooled number = pooling soccer's real edge against structurally-negative never-copy
    cells (crypto −21.6%, cs2 −24.5%, mlb −8.2%) the book newly contains + thin-cell reversion
    (other +31.5%→−7.1%). Decision-level fix = route PER-CELL, don't pool → green-lights B/C.
THREAD B — TOP-K ENSEMBLE OPERATOR (the real shot): the untested middle of routing↔averaging, LOO split.
  · k=1 (argmax router) meanΔ −0.126 (random-k null p=0.82 → RANKING HURTS at k=1, the idiosyncratic-
    variance mechanism) → k=2 −0.018 → **k=3 +0.063 (relaxed) / +0.091 (frozen), 7/10 regimes positive**
    → k=5 +0.022. k≈3 is the operator sweet spot, beats BOTH single-router AND fleet-average on point est.
  · GATE: t-CI across regimes STRADDLES 0 (relaxed CI[−0.168,+0.294]); random-k null p=0.18 (relaxed)/
    0.07 (frozen) — best signal in the run but NOT ≤0.01, and not gate-clearing after k×weight×screen
    Bonferroni. selection_null --calibrate PASS (2%≤20%, 82%≥60%). → **INDETERMINATE-BY-POWER, leaning
    that a small concentrated ensemble is the right operator.** Cleaner (frozen) MM-exclusion sharpens
    selection (p 0.07 < 0.18) — nuance: for the OPERATOR, frozen may beat relaxed (opposite of H7's cohort).
THREAD C — FADE PERSISTENCE (soccer/directional/band5): **ARTIFACT / few-day**, NOT a recurring edge.
  · flat-shares NO surplus: overall +1.4% but day-block bootstrap CI[−0.08,+0.13] straddles 0;
    EARLY −3.3% vs LATE +4.9% (sign FLIPS between halves); 3/7 days positive, mass carried by
    06-29 (n=41) + a tiny 07-03 (n=5). Within-SOCCER null p=0.252 (directional NOT special within
    soccer band5). Cycle-1's p=0.001 borrowed power from an across-sport null; within soccer it collapses.
  · → do NOT forward-track the fade; it fails BOTH transfer (0/3, Cycle 1) AND within-soccer persistence.
THREAD D — DENSE-CAPTURE DIAGNOSIS: 0.6% coverage is **sibling-dedup crowd-out**, not scope/off.
  · DENSE_STRATEGIES already includes favorite,elite_fresh_fav and rows ARE written (2999 rows/162 sig,
    live since 07-03 20:09). Root cause: dense_capture_candidates DISTINCT ON (condition_id,outcome_index)
    keys the trajectory to the earliest-fired SIBLING (usually strict, 152/162); clv_lambda joins by
    signal_id → misses it. Proven: 62/74 (84%) post-dense-start favorites SHARE a market with a captured
    trajectory. FIX = read-side market-key join → coverage 1.2% → 15.1% (13×, +14pp), paper-safe, NO Rust
    change; residual to 50% is pure temporal accrual (342 pre-start favorites). Flagged DEFERRED (gate input).
CANDIDATE ARMS: unchanged — nothing clears the full gate. favorite still pilot=HOLD, λ̂ CI-lo<0.25,
  persistence=SOCCER-ARTIFACT. topk k=3 is the nearest-new candidate but INDETERMINATE.
VERDICT THIS CYCLE: **nothing promoted.** Genuine forward progress on the OPERATOR (k≈3 ensemble is the
  right shape, vs Cycle-1's refuted k=1) and on the LEVER (dense-capture 13× fix identified). Two clean
  negatives banked: soccer fade = artifact (retired), decay = composition/recoverable not genuine (B/C worth it).
BINDING CONSTRAINT: **persistence** (months) — regime=SOCCER-ARTIFACT, 2/4 GO gates, real-money-eligible=False.
NEXT (single highest-leverage): apply the dense-capture market-key join (weeks, unblocks a measured λ̂) —
  it is the only binding lever with a <months ETA; everything else waits on non-soccer regime accrual.
WATCH-LIST: (1) topk k≈3 ensemble — forward-track meanΔ vs fleet-avg + random-k p as regimes accrue;
  frozen-screen selection is sharper. (2) dense_capture_coverage — market-key join DEFERRED for human
  safe-swap; then accrue to 50%. (3) mm_screen_refinement — relaxed=frozen on cohort (H7) but frozen
  SHARPER for the top-k operator; keep both objectives distinct. (4) soccer fade — RETIRED (artifact).

---

### Run beat-best-trader — cycle 3 (RELIABILITY PORTFOLIO) — 2026-07-05T21:45Z
REFRAME (Tue): prior "everyone negative" = OBJECTIVE-FUNCTION artifact (variance-punishing, our-price,
  thin-data LB), not fact. Select a WINNING PORTFOLIO by reliability at THEIR price; copyability is a
  separate downstream filter. selection_null --calibrate PASS. Paper-only, nothing promoted, no Rust.
THREAD R1 — factor library + GATED reliability composite (reliability_score.py, NEW, --selftest green):
  · per-wallet event-clustered at THEIR fill price; unit = flat-shares per-event calibration gap (won-price).
  · factors: RISK (downside dev, maxDD+Ulcer, CVaR5), CONSISTENCY (pos-window frac, cal_gap, loss streak),
    STRENGTH (best sport×band cell + skill concentration, MM/bot-excluded directional), CONFIDENCE
    (n_ev/n_days, cross-sport + both-halves stability, per-wallet Bernoulli-at-their-price skill null with
    H0 mean pinned at 0 exactly — the exact "beat the prices you pay by more than luck" test).
  · GATED (floor on every axis) then ranked by Sortino. LIVE: 66% of 121 scored wallets +EV at their price;
    shortlist n=4 = djokowin/master-wuji/acorp/zhuz632. SANITY PARTIAL 1/5 named surface: master-wuji ok;
    johndegen skilled(null_p .003) but MM-flagged (= Cycle-1 idiosyncratic-variance wallet → exclusion is
    the gate working); PatienceCapital MM+neg; Sportbetting76/sport-intelligence miss skill-null. Gate
    surfaced belief-blind winners NOT on the reputation list → not rubber-stamping names.
THREAD R2 — RELIABILITY-PERSISTENCE (the GO/NO-GO) (reliability_persistence.py, NEW, --selftest green):
  · leak-free per-wallet median-ts early/late split, each R1-scored. VERDICT = GO.
  · reg_sortino rank early→late Spearman rho +0.220, boot CI95 [+0.03,+0.40], perm p_global 0.0070,
    p_nstrata 0.0055 (n-tertile-stratified null AGREES → NOT a power confound; survives ×4 Bonferroni).
    cal_gap +0.207 (.0085/.0055); pos_window_frac +0.264 (.002/.0005). Transition: early-top-Q → top-HALF
    60% (chance 50%). Practical: early-selected 12 wallets → LATE cal_gap +0.052 vs random +0.019, beats-
    random p=0.0445 (MARGINAL, would NOT survive Bonferroni).
  · CAVEATS: effect modest (rho~0.22); practical profit-arm marginal; split is within-wallet-temporal NOT
    single-calendar-forward → regime-shift persistence still months-bound. Strongest signal any cycle produced.
THREAD R3 — correlation-diversified reliability-weighted BOOK (reliability_portfolio.py, NEW, --selftest green):
  · shortlist mostly LOW-corr (median ~0.10; one +0.85 on 6 days). Inverse-downside equal-risk, 40% cap.
  · Diversification HALVES drawdown: book maxDD 0.58 vs best-single(acorp) 1.14, IN-sample AND OUT-of-sample
    (wts from early, eval late) → the "minimal risk/variance" axis Tue prioritized: WIN.
  · Book LOSES to best single on SORTINO: 0.678<0.853 in-sample, 0.267<0.337 OOS (diluting the best name
    drags return-per-risk down). posWin book 67% < best 81%.
  · COPYABILITY LAST (reprice at our entry): book stays POSITIVE (totalPnL +2.89, Sortino +0.321, 0 dropped)
    — but MODELED tax only, NOT fill/lag-validated → copyable-positive ≠ bankable.
  · BELIEF-BLIND: selection-beats-random-book on Sortino p=0.093 (conservative inf-clamp) → NOT gate-clearing.
    Nothing promoted.
LEDGER: +3 informational rows (reliability_shortlist=BUILT, reliability_persistence=GO, reliability_book=
  RISK-REDUCTION-ONLY). GO gates unchanged 2/4, real-money-eligible=False, binding=persistence(months).
VERDICT THIS CYCLE: reframe VALIDATED at core (reliability real, prevalent, PERSISTS OOS — R2 GO is new
  and survives the confound-controlled null) and honestly BOUNDED at edge (book = risk-reduction not a
  return edge; loses to best single on Sortino; selection not distinguishable from random on Sortino).
  Defensible product = "low-drawdown book of reliability-persistent specialists", NOT "out-returns the
  best trader per unit risk". Nothing promoted.
BINDING CONSTRAINT: persistence over independent non-expiring regimes (months) + fill/lag copyability.
NEXT (single highest-leverage): GROW the shortlist past n=4 — R3 diversification is power-starved at 4
  names (a +0.85 corr on 6 days can swing it). Accrue non-soccer regimes + RELAX the band scoping so
  specialists' longshot/other-band skill enters the gate, then re-run R2/R3 as the shortlist widens.
  That is what could turn "reliability persists (proven)" into "the book beats the best trader (now NO)".
WATCH-LIST: (1) reliability_persistence — re-run as regimes accrue; watch whether rho holds on a single
  calendar-forward holdout (stronger claim than within-wallet split). (2) reliability_book — re-benchmark
  vs best-single-Sortino as the shortlist widens; the drawdown win is real now. (3) band scoping — the
  favorite-band 0.45–0.90 gate under-credits longshot specialists (PatienceCapital etc.).
REPORT: reports/RELIABILITY_PORTFOLIO_2026-07-05T214500Z.md

---

### Run beat-best-trader — cycle 4 (DRAWDOWN-TO-PROFIT OPTIMIZATION) — 2026-07-06T04:38Z
OBJECTIVE SWITCH: primary metric = realizable (OUR-price) CALMAR = return/maxDD (NOT Sortino); MAR +
  return/CVaR5 siblings. Instrument drawdown_optimization.py (NEW, --selftest green). Event-level SQL
  aggregation proven IDENTICAL to the per-fill pipeline (134 wallets, max score-field diff 4.7e-14) —
  built because the per-fill fetch (1.6M rows/105s) was the runtime wall. reliability_score.py: score_evs
  split out of score_wallet (EXTEND, selftest green). Paper-only, nothing promoted, no Rust, DB read-only.
O0 — reframe reproduced EXACTLY (frozen anchor): their-price book Calmar 0.167 > best-single 0.122;
  tax collapses realizable Calmar to 0.044 (gap 0.123 = the target). Live (drifted) agrees: their 0.177.
O1 — WEIGHTING HEAD-TO-HEAD (equal/inv-dd/risk-parity/HRP/max-Calmar), realizable OOS Calmar (early→late):
  · WINNER = plain EQUAL (OOS 0.0265). RISK-PARITY ≡ EQUAL to 4dp + HRP≈equal → near-disjoint trading days
    make the 0-fill covariance ~diagonal; covariance-aware methods add NOTHING (no usable corr structure).
  · max-Calmar optimizer: best IS (our Calmar 0.0798, maxDD 0.775 — the ONLY method that cuts drawdown
    below best-single at our price, ddRed/ret +6.29) but OVERFITS OOS (0.0028). inv-dd baseline OOS 0.0105.
  · DECISIVE: at our price the generic diversified book has NEGATIVE ddRed/retGiveup (−5.75) — book maxDD
    1.19 > best-single 1.14 → the Cycle-3 "halved drawdown" is a THEIR-PRICE property that repricing kills.
O2 — WIDEN band 0.45–0.90 → 0.10–0.97 (pre-registered P1; P2 = cross-sport ≥1, sensitivity only). Pool
  166, shortlist n=4 [Villson, zhuz632, master-wuji, djokowin]: acorp drops, VILLSON (longshot/other-band
  specialist invisible to the favorite gate) ENTERS = the charter's mechanism working. Calmar-vs-#names
  curve PEAKS OOS 0.2306 at n=3 BUT that book's IS Calmar = 0.0076, maxDD 1.93 (IS/OOS disagree 30×) →
  PEAK IS A THIN-WINDOW ARTIFACT, not a stable frontier gain. Durable signal: Villson alone has the lowest
  our-price IS drawdown of any name (0.46) but ZERO OOS coverage → a lead to accrue, not a result.
O3 — TAX-AWARE: name-DROP filter (our Calmar≤0) drops 0 names (all widened names our-price-positive) →
  recovers nothing. Tax-aware WEIGHTING (max-Calmar, narrow shortlist) 0.044→0.0798 IS = recovers ~29% of
  the collapse by concentrating tax-robust low-drawdown names — but OOS 0.0028 (overfits). Lever exists,
  points right in-sample, not bankable on current data.
O4 — REBALANCING: UNTESTABLE / INSUFFICIENT-DATA — rolling re-score on a trailing half leaves 0 wallets
  above the 30-event floor (roll_n=0). Months-of-data question; can't answer now.
WORTH-IT GATE (belief-blind, realizable OOS Calmar): (1) refined book 0.1044 vs random equal-size book
  mean −0.0225, p=0.120 (1455 draws, weighting held equal → isolates SELECTION) — NOT ≤0.05. (2) vs best
  single reliable trader master-wuji 0.2113 → book LOSES. (3) selection_null --calibrate PASS.
  → VERDICT = NOT WORTH-IT / INDETERMINATE-BY-POWER. Headline dd-reduction-per-return at our price = −7.79
  (book ADDS drawdown per return). The value is diversification / the single best trader, NOT selection.
VERDICT THIS CYCLE: the optimization is honest and DECISIVE — "not worth it on the current record." Right
  objective (realizable Calmar) makes the failure legible: the drawdown edge lives at THEIR price, the
  follower tax eats it, and NO weighting escapes OOS (sophisticated ones collapse to equal; max-Calmar
  cuts our-price drawdown in-sample but overfits). Single strongest REALIZABLE approach is NOT a book —
  it's following the single best reliability-persistent trader (master-wuji: our OOS Calmar 0.2113, maxDD
  0.57), which dominates every optimized book at our price. Nothing promoted.
BINDING CONSTRAINT: unchanged — OOS persistence across independent non-expiring regimes (months) +
  fill/lag copyability. GO gates 2/4, real-money-eligible=False.
NEXT (single highest-leverage): accrue forward days for VILLSON (only genuinely-low our-price drawdown
  name, 0 OOS coverage) + forward-test the tax-aware max-Calmar weighting (only method that cuts our-price
  drawdown) — both need weeks of forward data to move from in-sample lead to bankable; both gated behind
  the same months-long persistence wall.
WATCH-LIST: (1) Villson — low our-price IS drawdown (0.46), untested OOS; accrue. (2) max-Calmar weighting
  — cuts our-price maxDD 1.14→0.77 IS; forward-test whether it survives (currently overfits 0.0028 OOS).
  (3) covariance-aware weighting — worthless while trading days are near-disjoint; revisit only if overlap
  grows. (4) reliability book at our price = risk-reduction ONLY at their price; repricing negates it.
REPORT: reports/DRAWDOWN_OPTIMIZATION_2026-07-06T043802Z.md
