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

================================================================================
CYCLE 5 — REAL FOLLOWER-TAX MEASUREMENT (the decisive modeling-artifact test)
UTC 2026-07-06T05:06Z · selection_null --calibrate PASS · read-only · nothing promoted · no Rust
--------------------------------------------------------------------------------
PREMISE: every Cycle 1-4 realizable verdict rests on a MODELED follower tax (FOLLOWER_TAX 0.013 +
  band_spread ≈ 2.9¢). Nobody MEASURED it. Dense capture (signal_price_trajectory, ASK column, live
  since 07-03 20:09) now lets us read the real executable ask on a captured market → measure the real tax.
T1 — COVERAGE RECOVERY (clv_lambda.py --market-key-join, Cycle-2 fix in research layer): join trajectory
  by (condition_id,outcome_index) not signal_id. Trajectory coverage 2.0% (7 closes) → 19.9% (69 closes),
  ~10x — the real recovered coverage (Cycle-2 projected ~15%). Still <50% (K1) → λ̂ fallback-mixed.
  clv_lambda default λ̂ join NOT swapped (GO-gate input; DEFERRED for human review).
T2 — REAL TAX (real_tax.py NEW): real entry = earliest captured ASK in [fill_ts, fill_ts+900s]; real tax
  = ask − trader fill price. 12174/152354 fills matched (coverage 8.0%, 153 markets). REAL tax median 1.0¢,
  market-clustered mean 1.0¢, pooled 1.3¢ vs MODELED 2.9¢ (fill-wt). Per band real<modeled in b1/b3/b5
  (incl book's band-5 favorites 0.9¢ vs 2.4¢), ≈equal b2/b4. → MODELED tax OVERSTATES the real cost;
  FOLLOWER_TAX=0.013 looks too high. THIN: 8% coverage, ~2.3d capture, capture-burst-adjacent bias →
  INDETERMINATE-BY-POWER, directionally real<modeled. REAL λ̂ (recovered market-key sample) = 0.136,
  CI [0.065, 0.276] — CI-lo 0.065 << 0.25 floor; CLV+ (null p=0.0000) but only ~14% of surplus → edge
  still mostly FLB-bias, NOT information. λ̂ does NOT clear the floor.
T3 — RE-DECIDE (drawdown_optimization.py --real-tax clustered|pooled, EXTEND): substitute measured per-band
  tax; re-run realizable-Calmar + belief-blind gate on identical data.
    tax mode | refined OOS Calmar | best-single(master-wuji) OOS Calmar | beats best | belief-blind p
    modeled  |   0.1061           | 0.2113                              | NO         | 0.103
    real clus|   0.1256           | 0.2368                              | NO         | 0.1005
    real pool|   0.1573           | 0.2633                              | NO         | 0.0999
  Lighter tax lifts realizable Calmar ~15-50% (max-Calmar IS-recovery 28%→51%→66%, still overfits OOS) BUT
  (1) the best single trader improves in lockstep and STILL dominates every book; (2) belief-blind
  selection p stays ≈0.10 REGARDLESS of tax — a common price shift can't change whether selection beats a
  random book (even zero tax wouldn't); (3) book dd-reduction-per-return vs best single stays NEGATIVE
  (-7.67→-5.93→-4.02). VERDICT under all three: NOT_MET / INDETERMINATE-BY-POWER — unchanged.
T4 — SKIPPED: no surviving realizable edge to pre-register. Honest next step = forward accrual of
  independent non-soccer regimes (persistence wall) + promote the dense-capture market-key join to a real
  gate input (DEFERRED, human + Rust review).
DECISION: the follower tax is a PARTIAL MODELING ARTIFACT (real ≈ ⅓-1× of modeled) — but correcting it
  changes the LEVEL, not the VERDICT. The WALL IS REAL. Optimization on the current record is OVER; only
  forward accrual remains.
LEDGER DELTA: +3 informational rows (real_follower_tax=MEASURED-thin; edge_reality_recovered=INDETERMINATE;
  realizable_edge_on_measured_tax=NOT_MET). GO gates 2/4; real-money-eligible=False; binding=persistence
  (months). REPORT: reports/REAL_TAX_MEASUREMENT_2026-07-06T050603Z.md

================================================================================
CYCLE 6 — FORWARD-TRACK INSTRUMENT + HUMAN-REVIEW HANDOFF (the dormancy setup)
SEAL 2026-07-06T06:25:17Z · read-only · nothing promoted · nothing armed · no Rust · DB read-only
--------------------------------------------------------------------------------
CHARTER: this is ENGINEERING/SETUP, not more research. Freeze the candidate plays into a pre-registered,
  gated, forward-accruing instrument that auto-flags GO if an edge ever emerges; write a clean handoff for
  the two real wins; then go dormant. Promote NOTHING, arm NOTHING, change NO Rust.
TUE REFINEMENT (folded into the seal BEFORE finalizing): anti-longshot/reliability-of-source screen +
  high-volume/long-term floors, and a candidate re-rank.
F1 — PREREG SEAL (reports/PREREG_FORWARD_TRACK_2026-07-06T062517Z.md, FROZEN):
  · PLAYS: PLAY-A=master-wuji (single-best reliable TAIL, 103 ev, 19% LS, +12.4%); PLAY-B=DaBossHogg
    (best high-volume LOW-longshot alternative, 282 ev, 2% LS, +4.4% — highest volume / near-zero longshot,
    the purest durable-skill diversifier); PLAY-C=equal-weight survivor BOOK {master-wuji, acorp,
    Sportbetting76, DaBossHogg} (the diversification benchmark; equal-wt because Cycle-4 proved equal wins OOS).
  · EXCLUDED (screen working): Villson (57 ev < 100 high-volume floor — only ever admitted when Cycle-4
    widened into the longshot band); djokowin (53% longshot > 40% cap); pfk.bgd (58% longshot > cap, the
    archetype). PLAY-B re-picked to DaBossHogg (Villson dropped).
  · FROZEN ELIGIBILITY: relaxed round_trip τ=0.50 + directional net-maker (no arbers/MM/bots); ANTI-LONGSHOT
    (price<0.35): ≥40% longshot-exposure ⇒ exclude; drop-best-3-events must not flip realizable ROI ≤0;
    longshot-stripped profitability >0 at corrected tax. HIGH-VOLUME/LONG-TERM: ≥100 events, ≥20 active days,
    positive corrected-tax ROI in BOTH time-halves (sustained, not recent-only).
  · METRIC: realizable Calmar at the MEASURED band-aware tax (~1.0¢; Win #1 baked in via real_tax.json
    market-clustered per band, NOT the old flat 0.013), forward-only (first_seen ≥ SEAL), event-clustered.
  · GATE (all, forward-only): power ≥30 ev; realizable Calmar >0; beats a RANDOM equal-size book belief-blind
    p≤0.01; beats the single-best benchmark; selection_null p≤0.01 + --calibrate PASS; promotion_verdict
    (≥30 ev, Bonferroni, day-deflated SE, LB>0.03); pilot_verdict (LB>0.02, ≥50 ev, ≥5 +regimes, ≥70% +,
    liq≥$2000); persistence ≥2 DISJOINT NON-SOCCER regimes (soccer alone NEVER counts); real λ̂ CI-lo ≥0.25.
    GO-CANDIDATE ⇒ loud ESCALATE-TO-HUMAN (a GO on thin data is more likely a bug; demand the months).
F2 — forward_track.py (NEW, --selftest green): read-only snapshot; re-runnable with NO code change; just
  accrues. Per play: forward realizable Calmar at measured tax + ordered gate + STATUS (HOLD /
  INDETERMINATE-BY-POWER / GO-CANDIDATE) + first binding failure + accrued ev/days/non-soccer-regimes +
  needs/ETA; writes reports/forward_track.json; GO-CANDIDATE ⇒ escalate banner (never auto-promote/arm).
  Expensive nulls (checks 3/5/6/7) are DOWNSTREAM of the power+persistence accrual gates that bind for
  months → reported PENDING, re-computed by companion instruments in the accrual cycle. selftest covers:
  clears-all⇒GO-CANDIDATE+escalate; thin⇒INDETERMINATE-BY-POWER(power_events); powered+unprofitable⇒HOLD;
  1-regime⇒persistence binds; pending-null⇒no false GO. LIVE (at seal): all 3 plays INDETERMINATE-BY-POWER
  (0 forward events — EXPECTED), no GO-CANDIDATE, no escalation.
F3 — readiness_ledger +3 forward-track rows (EXTEND, --selftest green): forward_track_rows() (pure) reads
  forward_track.json → forward_play_A_tail / forward_play_B_dabosshogg / forward_play_C_book (informational,
  NOT GO gates). Live: all 3 INDETERMINATE-BY-POWER; GO gates unchanged 2/4; real-money-eligible=False;
  binding=persistence(months).
F4 — HANDOFF-HUMAN-REVIEW.md (NEW): two DEFERRED wins (D29 Phase-1 STOP — NOT applied). #1 tax correction:
  FOLLOWER_TAX=0.013 (copyability.py:41 / trader_scorecard.py:42 / regime_edge.py:56) + band_spread ≈2.9¢
  overstates the real ~1.0¢ band-aware; per-band measured value proposed; Rust EXEC_HAIRCUT default 0.01
  already matches; caveat 8% coverage/~2.3d ⇒ forward-confirm. #2 dense-capture join: promote clv_lambda
  MARKET_KEY_TRAJ_SQL to the default so clv_lambda.json (the edge_reality GO-gate input) carries recovered
  coverage 2%→19.9%; residual to 50% = pure temporal accrual (342 pre-dense-start favorites); λ̂-lo 0.065<<0.25.
  Plus HOW TO CHECK IN: weekly `python3 scripts/forward_track.py` + what STATUS/accrual/first-binding to watch.
VERDICT THIS CYCLE: the dormancy instrument is BUILT and clean enough to sit unattended for months. Nothing
  promoted, nothing armed, no Rust touched. Currently all-INDETERMINATE-BY-POWER (0 forward events — the
  expected state at seal). The ONLY lever left is forward accrual of independent NON-SOCCER regimes.
BINDING CONSTRAINT: the accrual horizon — independent non-soccer regime persistence (MONTHS). GO gates 2/4,
  real-money-eligible=False.
NEXT (on wake): re-run forward_track.py weekly; watch STATUS move off INDETERMINATE-BY-POWER as
  esports/NFL(Sept)/NBA(Oct) regimes accrue; escalate to Tue ONLY on a hand-verified GO-CANDIDATE.
REPORTS: reports/PREREG_FORWARD_TRACK_2026-07-06T062517Z.md, reports/forward_track.json, HANDOFF-HUMAN-REVIEW.md

================================================================================
CYCLE 7 — CONSOLIDATION: FREEZE THE STANDARD + NON-REGRESSION GUARD
UTC 2026-07-06T21:20Z · read-only · nothing promoted · nothing armed · no Rust · DB read-only
--------------------------------------------------------------------------------
CHARTER (Tue): "get rid of all the noise, make sure we don't regress from this system, only iterate and
  improve upon this one, make it our current standard and focus — it's our current best and it should be
  real." Honesty paramount: the standard rests on a REPRODUCIBLE, audited number, not a screenshot.

C1 — SCREENSHOT RECONCILIATION (data forensics). Tue's screenshot: 349 bets / +$2,008 / +6.9% turnover /
  "+63% on ~$3.2k working bankroll" / 06-29..07-06 / an Edge/bet column. It does NOT reconcile with the
  canonical honest_paper_ledger (favorite+elite_fresh_fav = 229 bets, +$497, +2.2% ROI). RESOLVED:
  · WHAT IT MEASURED = the honest-P&L tracker's REALIZABLE-EDGE view (outcome vs the mid we observed while
    OPEN = CLV, minus a ~1c execution haircut), POOLED at flat stake, over the FULL 06-29..07-06 window.
    Reproduced today (398 resolved signals; the screenshot's 349 = an earlier snapshot, fewer resolved):
    realizable entry (mid+1c) pooled = +$2,123 / +5.33% ROI-turnover; CLV-mid pooled = +$2,427 / +6.10%.
    "+6.9% turnover" ≈ the event-clustered honest_roi (favorite +8.36%, elite_fresh_fav +3.29%).
    "+63% on ~$3.2k working bankroll" = total realizable P&L ÷ PEAK working capital (avg 8.95h to resolve
    → capital recycles ~2.7×/day; ~$1.85k avg, ~$3.2k peak). That is a capital-VELOCITY return, NOT
    ROI-on-turnover.
  · WHY ~4× THE LEDGER (+$497): (1) the ledger starts 07-01 and NEVER recorded the two front-loaded days —
    06-29 alone = +$1,026 (World Cup), 06-30 = −$151, = +$875 missing; (2) the screenshot POOLS every
    signal fire (398) vs the ledger's deduped/appended 229 unique bets; (3) CLV/realizable-entry basis is
    more favorable than resolved fills. Realizable pooled by resolved-day: 06-29 +$1026, 06-30 −$151,
    07-01 +$475, 07-02 +$932, 07-03 −$71, 07-04 +$68, 07-05 −$283, 07-06 +$129.
  · HONEST OR OPTIMISTIC: the realizable-edge BASIS is a legitimate designed metric (CLV−haircut = the
    edge we could realize). The +63% HEADLINE is OPTIMISTIC — half the profit is one un-repeatable World
    Cup day, it's return-on-working-capital (velocity leverage) not edge-on-turnover, and it's best-case
    pooled CLV fills. THE SINGLE REPRODUCIBLE BASELINE TO TRUST = resolved-P&L +2.2% (229 bets, +$497).
    Report the realizable +5–8% ONLY when explicitly labeled CLV/realizable-edge.
  VERDICT: fully reconciled. The +63% is not a bug and not a lie — it's an optimistic FRAMING (working-
  bankroll velocity × front-loaded regime × CLV basis) of a real but small, decaying edge. Baseline = +2.2%.

C2 — FREEZE THE STANDARD (reports/STANDARD-BASELINE.md + reports/baseline_champion.json). Standard defined
  by CONFIG not a peak: favorite (price_band 0.65-0.98) + elite_fresh_fav (require_elite, 0.80-0.97,
  180min) on the strict base params (consensus.rs::default_portfolio). Belief-blind evidence (fresh
  selection_null, 2000 draws seed 20260702): favorite 158 ev, surplus +8.06% over blind, z=4.28,
  p_emp=0.0000 SELECTION-REAL, LB(1.64σ) +4.93%>0, positive in 3 disjoint NON-soccer regimes (tennis/mlb/
  other). Audited metrics BOTH labeled: (a) resolved-P&L +2.2% (229 bets, +$497 — THE baseline, decaying);
  (b) realizable-edge/CLV +5-8% (the tracker's designed metric). Standard = METHODOLOGY + belief-blind
  edge, NOT the peak. Frozen champion snapshot written for the guard to reference.
C3 — RETIRE THE NOISE. The ~14 net-negative arms (loose −$14.8k, fresh2h −$6.0k, whales/count/strict ~−$5.9k
  each, sports_only/trust_weighted/longshot/elite_gated, strict_retuned, trusted_only, tight_cluster,
  nonsports, proven_router) documented as DEPRECATED/non-focus in STANDARD-BASELINE.md + HANDOFF WIN #3.
  Rust NOT touched (D29 Phase-1 STOP). DEFERRED human-review item: narrow live LEDGER_STRATEGIES=
  favorite,elite_fresh_fav (paper append only — keep SCORING the arms, they are the belief-blind comparison
  set the guard needs). KEY INSIGHT surfaced: several retired arms are selection-REAL (strict/count/whales
  +4.7%, trust_weighted +6.7%) yet net-NEGATIVE in P&L — because they trade the FLB-losing longshots. The
  favorite-tilted standard is the one whose selection surplus AND realizable P&L both survive; that is why
  the standard is favorite, and why a challenger must beat it on the REALIZABLE metric, not just selection.
C4 — NON-REGRESSION GUARD (scripts/standard_guard.py, --selftest 12/12 green; reports/standard_guard.json).
  Champion-challenger: measures the champion on the honest belief-blind metric (reuses selection_null.py by
  subprocess — no logic dup), judges a challenger (--challenger STRAT: ADOPT only if beats champion OOS on
  realizable edge AND clears belief-blind gate p≤0.01/calibrate-PASS/promotion-LB>3%/≥2 non-soccer regimes;
  else CHAMPION-STANDS), and raises a loud REGRESSION-ALARM if the champion's own belief-blind LB drops ≤0.
  LIVE: REGRESSION STATUS = HEALTHY (favorite LB +4.94%>0, p 0.0000, 158 ev). --challenger strict correctly
  returns CHAMPION-STANDS (selection-real but loses on realizable −3.3% vs +5.3%). Folded standard_champion
  + standard_regression informational rows into readiness_ledger.py (--selftest green); GO verdict UNCHANGED
  (2/4, real_money_eligible=False, binding=persistence months).
VERDICT THIS CYCLE (critical-partner honest): the STANDARD is frozen, belief-blind-validated, and guarded
  against silent regression — the DISCIPLINE Tue asked for is now structural. But the honest baseline is
  small and fragile: resolved-P&L only +2.2% and DECAYING post-World-Cup, the belief-blind edge is carried
  by EXPIRING regimes, and it is NOT real-money-eligible (binding = non-expiring regime persistence over
  MONTHS). The value is the protected, non-regressing standard + the champion-challenger loop, NOT an
  inflated number. Screenshot's +63% = optimistic working-bankroll-velocity framing of this same edge.
BINDING CONSTRAINT: unchanged — non-expiring regime persistence (MONTHS). GO gates 2/4, eligible=False.
NEXT: forward accrual (forward_track.py weekly) + standard_guard.py weekly to watch REGRESSION STATUS;
  any proposed iteration goes through standard_guard.py --challenger before it can be considered.
REPORTS: reports/STANDARD-BASELINE.md, reports/baseline_champion.json, scripts/standard_guard.py,
  reports/standard_guard.json, HANDOFF-HUMAN-REVIEW.md (WIN #3).

================================================================================
CYCLE 8 — CONSOLIDATE-AND-IMPROVE (2026-07-06T21:55Z) — apply accumulated learnings as CHALLENGERS
================================================================================
GOAL: iterate the frozen STANDARD (favorite-tilted consensus champion) via champion-challenger — adopt
  ONLY what beats the champion OOS on realizable AND clears belief-blind; pre-register promising-but-
  underpowered; NEVER manufacture a win. NEW: scripts/consolidate_challengers.py (--selftest 7/7 green;
  reuses selection_null null-math + standard_guard.judge_challenger verbatim; realizable metric verified
  in selftest to reproduce the guard's band-tax formula). Report: reports/CONSOLIDATE_IMPROVE_2026-07-06T215541Z.md
  + reports/consolidate_challengers.json + PREREG seal reports/PREREG_CONSOLIDATE_2026-07-06T215541Z.md.
CHAMPION (live this run): realizable +4.92% (139 ev) · belief-blind favorite LB +4.69% p 0.000 (164 ev) ·
  calibrate PASS · resolved +2.43% · REGRESSION STATUS HEALTHY.
RESULT — NO CHALLENGER ADOPTS; CHAMPION STANDS UNCHANGED (baseline_champion.json + STANDARD-BASELINE.md
  NOT modified). Ranked by realizable Δ (90% event-bootstrap CI):
  C1 reliability-weighted (reliable-backed subset): +9.20% realizable, Δ +4.28% [CI −19.3%,+25.0%] →
     INDETERMINATE-BY-POWER. FINDING: reliability-scored durable traders are NEAR-DISJOINT from favorite
     consensus backers (shortlist overlap 0 ev; skill-pool overlap 13/164 ev). Can't concentrate on
     reliable backers because they aren't the backers. Pre-registered (blocked on accrual).
  C3 mid-band consensus add-on: standalone marginally selection-real (229 ev, +4.0%, p 0.041, LB +0.20%,
     4 non-soccer regimes+) AND day-return corr with favorite = 0.05 (beautifully uncorrelated) BUT
     realizable −2.0% after tax → combined book +1.01% (Δ −3.91% [−10.9%,+3.5%]) DILUTES the champion.
     The selection≠realizable trap again. CHAMPION-STANDS. Pre-registered: viable diversifier ONLY if the
     realizable tax is cut (see C6).
  C2 backer-quality screen (majority-directional; drop MM/bot): keeps only 11/164 ev, realizable −13.9%
     (Δ −18.8% [−54%,+11%]) → INDETERMINATE-BY-POWER, leans REFUTED. FINDING: ~93% of favorite events have
     backer pools our MM/bot screen flags — the favorite edge RIDES ON high-volume/MM-flagged wallets;
     screening them out kills edge + sample. Do not apply. DISCARDED.
  C4 CLV-exit overlay (284 ev): early-exit LOWERS mean (−1.0..−1.6%), barely cuts variance, slightly RAISES
     drawdown at every target → REFUTED. Favorites should be HELD to resolution (full 1−entry payoff beats a
     small locked CLV move). Champion's hold posture correct. DISCARDED.
  C5 conviction-weighted sizing overlay: log-growth +0.21, Calmar 5.49 vs 4.09 BUT max drawdown DOUBLES
     (8.2% vs 4.2%); same selection ⇒ leverage not edge; single 8-day path, cannot clear belief-blind.
     PRE-REGISTERED (needs multi-path CI + ruin analysis); not adopted.
  C6 entry-timing/tax reduction = HIGHEST-LEVERAGE next improvement (DEFERRED live change): real measured
     tax ~1.0-1.3¢ vs the conservative band-aware ~2.3¢ the guard scores; favorite CLV +1.3¢ (z=3.5);
     dense at-open capture recovers ~84% post-dense, 12.6× coverage. Cutting tax adds ≈+1.5-2% realizable
     to the CHAMPION'S OWN edge and could rescue the uncorrelated mid-band stream (C3) into a real
     diversifier. LIVE capture change → DEFERRED to human review (no Rust/config touched here).
VERDICT (critical-partner honest): nothing beat the champion at current power — the EXPECTED outcome on ~8
  correlated World-Cup-front-loaded days. Delivered a ranked, CI'd, pre-registered improvement pipeline +
  two clean refutations (CLV-exit; backer-quality screen), not a forced upgrade. Two structural findings:
  (a) our reliability instrument's population ≠ the consensus backer population; (b) the favorite edge is
  carried by high-volume/MM-flagged backers, not "clean" ones.
BINDING CONSTRAINT: unchanged — non-expiring regime persistence (MONTHS) + the realizable tax (C6 lever).
  GO gates 2/4, real_money_eligible=False. Promoted/armed/adopted NOTHING; no Rust; DB read-only; Max-only.
NEXT: pull the C6 dense-capture lever (DEFERRED human review) — the one improvement that lifts the champion
  itself; re-run consolidate_challengers.py weekly to re-judge the 3 pre-registered forward challengers as
  events accrue.
REPORTS: reports/CONSOLIDATE_IMPROVE_2026-07-06T215541Z.md, reports/consolidate_challengers.json,
  scripts/consolidate_challengers.py, reports/PREREG_CONSOLIDATE_2026-07-06T215541Z.md.

================================================================================
CYCLE 9 — TRADER-UNIVERSE CURATION (2026-07-07T02:47Z) — score the whole tracked universe, flag the
  leaderboard-inflated bad traders, surface the durable quality cohort + any NEW names, prune/add rec
================================================================================
GOAL (Tue): "get rid of unprofitable users, find more profitable long-term/consistent/high-ROI
  cohorts; ignore the really bad traders somehow in the top leaderboard." Belief-blind, PAPER-ONLY,
  adopt/prune NOTHING (DB read-only; prune/add = DEFERRED human review). Honored the Cycle-8 TWO-ROLE
  nuance: CONSENSUS BACKER (favorite edge RIDES ON high-vol/MM backers — do NOT prune) vs TAIL/COPY
  candidate (curate aggressively). Every number LABELED their-price skill vs our-price realizable.
NEW INSTRUMENTS: scripts/universe_curation.py (--selftest green; reuses reliability_score factor lib +
  trader_scorecard reprice/is_mm/persistence verbatim — no logic dup) → reports/universe_scorecard.json
  (per-wallet all factors + buckets + durable-quality gate). scripts/curation_guardcheck.py (--selftest
  green) → reports/curation_guardcheck.json (U2 cross-tab, U4 sub-cohorts, U5 prune + backer-criticality
  guard-check; invokes standard_guard.py read-only).
SCOPE: 1023 tracked (grew from ~475); 850 have fills; 147 JUDGEABLE (>=30 band ev, 0.45-0.90, 365d).
U1 bucket tally (147 judgeable): mm_arber 86, bad_predictor 28, skill_within_luck 22, genuinely_skilled
  7, longshot_lucky 3, skilled_not_copyable 1. → 59% of the top-leaderboard universe are market-makers.
U2 — THE COMPLAINT QUANTIFIED: 103/147 (70%) of judgeable top-leaderboard traders are BAD at OUR price.
  Rank 1-10 = 4/4 mm_arber (100% market-makers — exactly Tue's "bad traders somehow in the top LB").
  Top-PnL decile: 8/14 bad. Inflation buckets: (a) pure MM/arb (86, dominant), (b) longshot-lucky (3,
  die on drop-best-3), (c) bad_predictor/big-bankroll-mediocre (28, high PnL neg calibration), (d)
  genuinely skilled (7). IGNORE-for-tailing list = 117 wallets (bucket+reason in scorecard).
U3 — DURABLE cohort at strict bar (>=100 ev + 20d + consistent + non-longshot + directional + copyable)
  = ZERO. Root cause (real finding): every wallet durable enough (>=100 band ev) is MM-flagged; every
  clean-directional wallet has <100 ev — the two populations don't intersect yet. At relaxed >=30-ev bar,
  7 genuinely-skilled+copyable; only master-wuji (+15.7% realizable, 60d, 3 sports) and acorp (+5.9%,
  80d, 4 sports) are DURABLE (multi-sport, long span, robust drop-3) — BOTH are 2 of the current 4 and
  they SURVIVE. 5 NEW names (cnyek +21.3% but single-sport, RISK-IS-NEVER-OK 8-day burst, cigarettes
  6-day burst, Oneger single-sport, lookaon drop3-negative) = WATCH-list, NOT certifiable. STATUS OF THE
  4: Sportbetting76 DECAYED (skill_within_luck, null_p 0.40, realizable -5.8% → DROP candidate);
  DaBossHogg now MM-flagged (264 ev, realizable +0.9%, keep-track-don't-tail). Durable+copyable
  near-misses that fail ONLY the MM screen: 0x6db568e6 (167ev +3.3%), Latina (104ev +3.0%), DaBossHogg
  — flagged for a targeted MM-screen audit (are we over-excluding?).
U4 — 16 shared-best-cell sub-cohorts. Skill concentrates in favorite-leaning bands of soccer/mlb/nba
  (b3-b4) — exactly where the STANDARD lives (cross-validating). Best populated: soccer|b4 (20 wallets,
  6 copyable), soccer|b3 (17, 9 copyable); nba|b3 = master-wuji+djokowin. BUT copyable fraction only
  ~30-50% and this is DESCRIPTIVE best-cell clustering, NOT out-of-sample certified. NO sub-cohort
  certifiable (none clears >=2 disjoint NON-soccer copyable-LB). Too soccer-weighted + thin to bank.
U5 — PRUNE 79 wallets (help neither role: bad tail AND not a fav-backer): mm_arber 36, bad_predictor 21,
  skill_within_luck 18, longshot_lucky 3, skilled_not_copyable 1. GUARD-CHECK ✅: 32 "bad-looking"
  wallets are consensus-critical BACKERS (21 mm_arber, 7 bad_predictor, 4 skill_within_luck; incl rank-4
  wr0ngw4yb3tt0r realizable -12.8% as tail but a backer) → EXCLUDED from prune, flagged KEEP (the nuance
  in action). Favorite signals are backer-DEFINED, so pruning the 79 non-backers cannot change recorded
  signals by construction. standard_guard.py re-measure: champion REGRESSION STATUS = HEALTHY (belief-
  blind LB +4.42% > 0, p_emp 0.0000, 167 ev) → CHAMPION STANDS UNCHANGED; safe prune. ADD rec (deferred):
  do NOT ingest by rank/PnL (top is MM); deepen fill history on the near-miss cohort to reach >=100 ev;
  audit the MM screen vs the 3 durable near-misses; ingest more mid-rank (20-170) recurring WEEK+MONTH.
VERDICT (critical partner): complaint REAL (70% of top-LB bad at our price; top-10 = 100% MM). Durable
  quality cohort still TINY + FRAGILE — empty at the strict bar, 7 at relaxed, only 2 durable (both
  already tracked). NEW names are watch-list, not bankable. Distinguished skill (their price, detectable)
  from copyable realizable edge (our price, tax-gated). Cohort ERODES without maintenance (Sportbetting76
  decayed, DaBossHogg drifted MM) — the argument FOR this loop. Promoted/armed/adopted/pruned NOTHING;
  DB read-only; no Rust; Max-only. Binding constraint unchanged (regime persistence over months + tax).
REPORTS: reports/UNIVERSE_CURATION_2026-07-07T024744Z.md, reports/universe_scorecard.json,
  reports/curation_guardcheck.json, scripts/universe_curation.py, scripts/curation_guardcheck.py.
