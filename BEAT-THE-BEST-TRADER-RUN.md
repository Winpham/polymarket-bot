# Autonomous Research Run — "Beat the Best Tracked Trader"

**What this is.** A paste-to-launch prompt for a long, self-directed, multi-cycle Brainstem/Claude Code
run on `~/polymarket-bot` (Rust + Postgres, **paper-only**). Its goal is the user's literal north star:
develop a consensus / picking / selecting / tailing strategy that beats our current (underwater)
strategies **and at least matches, ideally beats, the single best individual trader we track** — by
synchronizing all tracked top bettors' signals **at our own realizable price**.

**Why the honest framing matters (read before launching).** The measured state: our paper book is a
handful of correlated days of one World Cup tournament; only `favorite`/`elite_fresh_fav` are green,
everything broader is ≈−15%; and our strategies regress to the **fleet** ROI (~+2.5%), not the **best**
wallets (+60–82%). The repo already has world-class instruments sitting on a **data desert**. On this
data **nothing certifies**, and the congregation-beats-best-trader thesis is **untestable by power (not
refuted)**. A run that *promises* a bankable winner here would overfit and violate the belief-blind gate.
So this run's honest deliverable is: **the missing benchmark, the right operator, one decidable-today
experiment, forward-accrual turned on, null results, and a watch-list — not a certified winner.** It
promotes nothing to real money.

**What changed since v1 (2026-07-05) — the MM-filter is now live and this run adopts it.** We now
distinguish wallets that profit by **predicting outcomes** from wallets that profit **purely by
market-making** (buy-both-hold price-sum arbitrage + maker rebates — a mechanism orthogonal to
prediction, and structurally uncopyable by a follower). The screen `trader_scorecard.is_mm`
(`round_trip_rate≥0.30 OR two_sided_rate≥0.25 OR sell_buy_ratio≥0.50`) is **vindicated as
profit-accretive** (D29 addendum: excluding arbers ~10×'s the followed cohort's forward copy-return,
+0.004→+0.043), and `best_trader_benchmark.py`/`router_verify.py` already exclude `mm_flagged` wallets.
**Critical nuance the user requires — filter by SOURCE of profit, not order type.** D29's Tier-1
labeling proved the current screen has a **27% false-positive rate on directional humans**, and *every*
FP tripped `round_trip_rate` — directional bettors who sell to manage positions or post maker orders to
dodge fees, i.e. exactly the traders we must KEEP. `two_sided_rate` (the buy-both-hold arb signature)
carries all the validated "pure MM" signal; `round_trip` is a **dominated FP-generator**. This run
therefore adopts the **round_trip-relaxed screen (0.30→0.50, per `PROPOSAL_mm_round_trip_relax.md`,
recovers ~18 copyable directional traders at equal/better forward return)** as the pre-registered
eligibility default, and adds a **profit-source discriminator** (§ insight 4) so "makes money by
market-making" — not "uses limit orders" — is what gets a wallet excluded.

---

## Design rationale (the four insights the design turns on)

1. **Route, don't congregate.** A consensus signal is a *mean over a one-sided cohort* — averaging
   regresses to the fleet mean, and **you cannot beat the max of a set by averaging the set.** To track
   the best trader (+60–82%) you must *route*: select the single best wallet per live context and tail
   THAT one, at our price — abstaining when none clears the bar. Skill-weighting (`TrustWeighted`/
   `CellPooled`) is the soft interpolation between averaging and routing; the run tests the whole
   spectrum. *Beating* (not just matching) the best trader requires ≥2 **conditionally-independent**
   skilled specialists to co-agree — the precondition that's falsified on one correlated tournament, so
   it's built as a forward-accruing instrument, not bet today.

2. **The benchmark must be re-priced at OUR entry, over PREDICTORS only.** The repo's per-wallet scores
   (`trader_slice_scores`, `asof_slice_scores.sql`) measure surplus at **the trader's own fill price**.
   muchobliged's +60% is *muchobliged's* number; we enter at our post-drift ask after the follower tax
   (worst where the market is sharpest — MLB ~3¢ ate 83% of the one directional wallet's edge). A
   benchmark at the trader's price is unbeatable-by-a-follower and useless; the target is **the best
   single wallet's record RE-PRICED at our realizable entry** (already implemented in
   `best_trader_benchmark.py`: `B_LB` over `copyable = wallets − mm_flagged`). And it must be taken over
   **predictors only** — a pure market-maker's headline ROI is arbitrage/rebate income the market pays
   for liquidity, not a prediction edge a follower can capture, so it is excluded from the gated `B_LB`
   (shown only as `B_point`, flagged, so the gap is visible).

3. **Filter by SOURCE of profit, not by order type (the user's nuance, made precise).** "Remove the
   market-makers" must mean *remove wallets whose PnL comes from making markets* (buy-both-hold
   price-sum arb + rebates — profit that survives with the directional bet stripped out), and must
   **not** touch a directional predictor who happens to post maker orders to avoid fees. The live
   `is_mm` screen over-removes the latter (D29: 27% FP on directional humans, all via `round_trip`).
   So the run's eligibility screen = **relaxed microstructure** (`round_trip 0.30→0.50`, keep
   `two_sided_rate` and `sell_buy_ratio`) **AND** a **profit-source test**: a wallet is a pure MM iff
   its `two_sided`/price-sum-arb profit dominates and its one-sided *directional* net-maker edge
   (`regime_net_edge.py` `net_maker`) is ≈0 — i.e. it would still profit if it predicted nothing.
   Keep any wallet with a positive re-priced directional edge, maker orders and all.

4. **Accrual is the binding constraint everywhere.** The wall is the *count of independent clusters*
   (months), not analysis. Highest-value output is instruments that **auto-certify the instant the
   desert ends** (esports / politics / NFL Sept / NBA Oct onboard), plus **dense at-fire capture** to
   (a) convert λ̂ from a proxy (≈0.15, below the 0.25 floor) into a measurement and (b) produce
   genuinely-timestamped forward fills — the backfill crawl's crawl-stamp `ts` weakens every temporal
   split (D29 next-step) and the last regime-persistence run came back **SOCCER-ARTIFACT**. The one
   thing decidable *now* — cross-**context** variance (hundreds of wallets × cells) instead of
   cross-**time** accrual — is **routing-vs-averaging** via a within-trader leave-one-sport-regime-out
   test. That is the run's headline result.

**Already built (reuse, do NOT rebuild):** `best_trader_benchmark.py` (`B_LB` over copyable wallets,
MM-excluded), `router_verify.py` + `trader_scorecard.py` (`is_mm`, `reprice`, `members`, `persistence`),
`unified_book.py`, `regime_net_edge.py` (gross→net_taker→net_maker profit-source decomposition), the
`mm_*` suite (`mm_common`/`mm_calibrate`/`mm_persistence_effect`/`mm_reconcile`/`mm_screen_effect`),
`selection_null.py` (+`--calibrate`), `promotion_verdict`/`pilot_verdict`/`trust_verdict`, `clv_lambda.py`,
`copyability.py`, `relational_probes.py`, `persistence_tracker.py`, `honest_pnl_by_strategy`/`_segments`,
the paper ledger, dense capture, the trust map; the `beats_best_trader`/`router_gate`/`unified_book`
readiness-ledger rows. **Genuinely NEW this run (small):** (a) the relaxed + profit-source eligibility
screen wired into benchmark/router membership (a pre-registered variant of `is_mm`, forward-confirmed);
(b) a `consensus_fade.py` forward probe if not already present. **Deferred (human review only):** freezing
any Rust threshold change to `refresh_router_followset` / registering a winning arm as a live
`StrategyDef` — script-only backtests first; never mutate the live scorer this run (D29 Phase-1 STOP
stands: thresholds stay frozen in Rust until forward-confirmed).

**Rejected (do NOT re-run — the graveyard):** naive congregation on current data (0 specialists certified,
"DEAD ON THIS DATA"); market_resid (label-permutation refuted); orthogonal reliability book (0/12);
blind-tailing (≈−0.3%); longshots (cost-dead); flat-$ sizing (sign-flip killer — flat-**shares** only);
relational *fitting* on current data (overfits); consensus-strength/backer-rank scaling (dead lever);
crypto/other/econ consensus (never fire); a benchmark priced at the trader's own fill (structurally
unbeatable); a benchmark that lets a pure arber be the target (uncopyable — MM-exclude first); the
`round_trip` axis as a hard exclusion (dominated FP-generator — relax it); rebuilding the MM screen /
benchmark / router from scratch (they exist). A benchmark at our entry priced as a *point-estimate max*
is rejected — max-of-noise; gate on the **max of Bonferroni-corrected lower bounds** only.

---

# ══════════════  THE RUN PROMPT (paste below to launch)  ══════════════

```
# AUTONOMOUS RESEARCH RUN — "Beat the Best Tracked Trader"
# Repo: ~/polymarket-bot  (Rust + Postgres, PAPER-ONLY).  Models: Opus/Sonnet only.
# Work in a dedicated git worktree; commit at every cycle boundary; never touch the live order path.

## MISSION (honest framing — read twice)
Build and forward-test a strategy that aggregates our tracked top bettors' signals AT OUR OWN
REALIZABLE ENTRY and provably beats — in realizable, risk-adjusted, OUT-OF-SAMPLE terms — the
SINGLE BEST individual tracked trader, not the fleet mean. You are NOT promised a bankable winner:
the current data is ~3–4 correlated days of one World Cup tournament, so the thesis is UNTESTABLE
BY POWER (not refuted). Your honest deliverable is: the missing best-trader benchmark, the router
operator, the one experiment decidable NOW (routing-vs-averaging), forward-accrual instrumentation
turned on, null results, and a watch-list. If a candidate ever clears EVERY gate out-of-sample,
report it as a CANDIDATE for a future human-reviewed armed pilot — you may NOT arm real money.

Expect to conclude INDETERMINATE-BY-POWER on most hypotheses today. Reported honestly, that is a
correct and valuable outcome. The exception is H3 (within-trader LOO) which can return a signed answer.

## STANDING GUARDRAILS (violating any ⇒ HALT the run and report)
- NO REAL MONEY, EVER. Leave PILOT_ARMED unset (pilot.rs is unwired: NotArmed + NoPlacer);
  master_on stays false; EARN_DEEP_SHARPS stays false. Never place, never arm, promote nothing.
- BELIEF-BLIND GATE is the only judge; never fool it. A candidate is promotable ONLY if it clears
  ALL of the GATE section below. Missing/malformed selection-null ⇒ fail-closed HOLD.
- COST-ZERO, Max-only. Never set ANTHROPIC_API_KEY. Never spawn child `claude` processes. Never
  downgrade a critic to a weaker model. Opus/Sonnet only, never Haiku.
- FLAT-SHARES ($100 notional, FLAT_STAKE), NEVER flat-$ (documented sign-flip killer). Every edge
  event-clustered at COALESCE(event_slug, condition_id) BEFORE aggregating (within-match leak fix).
- λ̂ SELF-VETO: any candidate whose λ̂ CI-lower < 0.25 is auto-vetoed from promotion consideration.
- NEVER FIT-AND-BET. Router/fade candidates are forward probes; the discovery cell is held OUT of
  its own certification. Do NOT mutate the live scorer (consensus.rs default_portfolio) this run —
  script-only backtests; flag any live-wiring as NEW/DEFERRED for human review.
- All read-only MEASUREMENT runs against a RESTORED SNAPSHOT (PG_CONTAINER=pg-report), never prod.
- Pre-register every hypothesis with a UTC timestamp in the run journal BEFORE looking; all
  benchmark/gate reads filter first_detected_at ≥ that timestamp.

## PRE-REGISTERED HYPOTHESES  (write to reports/PREREG_<utc>.md BEFORE any measurement; freeze them)
H1 (router beats fleet): a per-context argmax-wallet router, priced at our realizable entry, beats
   the current fleet-average consensus arms (strict on WeightMode::Quality, favorite) in OUT-OF-SAMPLE
   event-clustered realizable surplus.
H2 (router matches/beats the best trader): router OUT realizable surplus ≥ B_LB (best single wallet
   re-priced at our entry, defined below), with overlapping-or-better CI.
H3 (routing beats averaging — THE NOW EXPERIMENT): in a within-trader Leave-One-SPORT-REGIME-Out
   split, argmax-routing yields higher held-out realizable surplus than fleet-averaging. Uses
   cross-context variance (available now), not cross-time accrual (absent). Can return a SIGNED answer.
H4 (skill-concentration on the FLB band): concentrating weight (TrustWeighted / CellPooled) on the
   favorite band 0.65–0.98 beats blind-by-band AND beats the best single favorite-tailer's B_LB.
H5 (fade beats tail on overhype — secondary lead): FADING one-sided band5 heavy-favorite consensus
   (buy NO at our price) beats the band-blind baseline AND transfers to ≥1 sport-regime OUTSIDE the
   discovery cell (soccer/directional/band5 held out).
H6 (λ̂ is real): with DENSE_CAPTURE on, measured λ̂ CI-lower crosses 0.25. (Expect still
   INDETERMINATE on 4 days — report the CI width and dense-capture coverage % as the finding.)
H7 (filter by profit-source, not order-type — the MM-screen refinement): the eligibility screen that
   maximizes the followed cohort's forward copy-return excludes PURE market-makers (buy-both-hold
   price-sum arbers / rebate harvesters — high two_sided_rate, ≈0 directional net_maker edge) while
   KEEPING directional predictors who post maker orders to dodge fees. Concretely: the round_trip-relaxed
   screen (τ_rt 0.30→0.50, keep two_sided_rate + sell_buy_ratio) yields ≥ the frozen screen's cohort
   forward copy-return (D29 addendum: +0.043→+0.045, recovering ~18 directional traders), AND a
   profit-source test (regime_net_edge net_maker ≈ 0 with two_sided high ⇒ pure MM) agrees with the
   two_sided axis on the arber class. Null: matched-subset removal (equal-N, matched on volume/n_positions,
   ≥2000×, as-of/leak-free) — same test as mm_persistence_effect.py. Forward-confirm before any Rust
   threshold change (D29 Phase-1 STOP stands).
Pre-registered prior for H1,H2,H4,H5,H6,H7 on CURRENT data: INDETERMINATE-BY-POWER (H7's cohort-return
direction is decidable now via mm_screen_effect.py; its persistence-lift is not). Say so; build; accrue.

## SETUP (cycle 0)
1. Write the pre-registration journal (above) and start a worktree.
2. Turn on forward-accrual instrumentation (ENV-ONLY — no rebuild): set DENSE_CAPTURE=1,
   CONSENSUS_TRUST_ARMS=1, SLICE_POOLED=1 in BOTH ~/polymarket-bot/.env.consensus AND the
   `environment:` block of docker-compose.consensus.yml; then
   `docker compose -f docker-compose.consensus.yml up -d`. Confirm dense_capture_tick spawns
   (live.rs:227) and entry_ask capture accrues (housekeeping.rs:259, set_entry_ask_decision). This is
   the repo's #1 named "next dollar of work" — it converts clv_lambda.py's λ̂ from proxy to measured.
3. VERIFY + REFINE the wallet-eligibility screen, then run scripts/best_trader_benchmark.py (ALREADY
   EXISTS — B_LB over copyable = wallets − mm_flagged; do NOT rebuild). First establish the eligibility
   screen used EVERYWHERE (benchmark, router membership) — this is the "filtered system that removes MM
   profit, keeps predictors" the run turns on:
     ELIGIBILITY = keep wallet iff it is NOT a pure market-maker, where "pure MM" is decided by BOTH:
       (i) RELAXED microstructure (prereg default): is_mm with τ_rt RELAXED 0.30→0.50, τ_2s=0.25,
           τ_sb=0.50 (per reports/PROPOSAL_mm_round_trip_relax.md). round_trip is a dominated FP-axis
           that flags directional traders who sell to manage positions / maker-to-avoid-fees (D29:
           27% FP, all via round_trip); two_sided_rate carries the validated arb signal, sell_buy earns
           its keep. Run scripts/mm_screen_effect.py to confirm the relaxed screen's cohort forward
           copy-return ≥ the frozen screen's BEFORE adopting it.
       (ii) PROFIT-SOURCE test (the user's nuance, decisive on disagreements): a wallet is a pure MM iff
           its buy-both-hold price-sum-arb / two_sided profit dominates AND its one-sided DIRECTIONAL
           re-priced net-maker edge (regime_net_edge.py net_maker, per wallet) is ≈0 — i.e. it would
           still profit predicting nothing. KEEP any wallet with a positive re-priced directional edge,
           maker orders and all. On (i)/(ii) disagreement, (ii) wins and the reason is logged (this is
           the 40-restore / 92-exclude reconciliation pool from D29 Item-6).
     Also cross-exclude the repo's OTHER detector (followed_traders.trader_type='bot' from
     classify_trader_types) — membership excludes the UNION, mirroring the Rust re-scorer
     (trader_scorecard.fetch_bot_flags; router_verify A4 found the two detectors disagree on 51/161).
   Then run best_trader_benchmark.py with this eligibility (--selftest green first). Its contents:
     - Contexts c ∈ {overall} ∪ REGIMES (optionally × price-band). BUY fills only, resolved only,
       eligible wallets only (ELIGIBILITY above — NOT the crude >1-outcome-in-window rule, which is the
       live scorer's coarse in-window heuristic, not the calibrated wallet-lifetime screen).
     - Per tracked wallet w, per context c, compute realizable ROI TWO ways and report BOTH:
         REALIZED (truth, thin) — from consensus_signals sharp_tail/sharp_tail_fresh + backers jsonb:
           entry = COALESCE(entry_ask, initial_market_price + 0.01); roi = (won−entry)/entry − 0.02;
           event-clustered. (The price we actually captured; requires the certified_only tail to have
           fired for w → thin today.)
         MODELED (powered) — from trader_fills over w's whole history:
           our_entry = f.price + FOLLOWER_TAX(0.013) + band_spread(f.price)  [copyability.py band model];
           roi = (won − our_entry)/our_entry − 0.02; event-clustered.
       Treat REALIZED as truth, MODELED as the powered estimate; FLAG divergence between them.
     - Eligible wallet: n_w ≥ 30 resolved tailable events in c. Per-wallet lower bound:
         LB_w = mean_roi_w − z(alpha / N_elig) · sd_roi_w / sqrt(effective_n_w),
         effective_n_w = distinct UTC days (Moulton day-cluster deflation, same as promotion_verdict),
         N_elig = # eligible wallets in c (the Bonferroni denominator that stops "best of 419" being noise).
     - Benchmark values per context:
         B_LB(c)     = max_w LB_w          ← PRIMARY, the only value gated on ("a wallet we could
                                             provably tail for ≥ this exists; a congregation must beat it").
         B_sharpe(c) = max_w mean_roi_w / sd_roi_w   ← the RESEARCH.md "higher Sharpe than the best member" target.
         B_point(c)  = max_w mean_roi_w    ← REPORT-ONLY, "selection-inflated"; may be a pure MM/arber
                                             (flag B_point_is_mm) — shown so the copyable/uncopyable gap
                                             is visible; NEVER gate on it.
     - A candidate strategy S PASSES the beat-best-trader gate in c iff ALL:
         (1) S.honest_roi_LB > B_LB(c) + 0.03   (from honest_pnl_by_strategy, same LB machinery)
         (2) S.sharpe > B_sharpe(c)
         (3) holds OUT-OF-SAMPLE (first_detected_at ≥ prereg ts), event-clustered, in ≥2 DISJOINT sport-regimes
         (4) S independently clears promotion_verdict + pilot_verdict + selection_null (p≤0.01, calibrate-PASS).
       This gate is ADDITIVE — it never replaces the existing gate.
     - --selftest on synthetic fixtures where the answer is known (one dominating wallet ⇒ high B_LB;
       all-noise wallets ⇒ B_LB deeply negative / INDETERMINATE). Must pass before any live-DB read.
     - Writes reports/best_trader_benchmark.json.
   HONEST-POWER NOTE: today, wallets with ≥30 tailable events per sport-regime are ~0–few and
   effective_n_w ≈ 1–3 days ⇒ every LB_w is deeply negative ⇒ B_LB is uninformative. Correct output
   today is "INDETERMINATE-BY-POWER: insufficient power to establish a best-trader floor," not a pass.
4. Router backtest — the operator spectrum + the decidable-now test. REUSE the existing router
   machinery (router_verify.py, trader_scorecard.py: reprice / members / persistence); extend it for the
   three-way head-to-head and the LOO split rather than writing a new script from scratch.
     - Policy π(c) → wallet-or-ABSTAIN, learned ONLY on pre-cutoff data:
         π(c) = argmax_w shrunk_realizable_surplus(w,c)  [same reprice + damp(n)=n/(n+20) shrink toward
         context blind], subject to THREE floors: (i) modeled realizable surplus > MARGIN 0.03;
         (ii) wallet is NOT `Avoid` under trust_verdict (trader_trust.rs:178); (iii) wallet is ELIGIBLE
         under the profit-source screen from step 3 (NOT a pure MM/arber; directional predictors who use
         maker orders are KEPT). If no wallet clears all three → ABSTAIN (not betting is what keeps the
         router off the fleet mean, and off uncopyable arbers).
     - Evaluate THREE operators head-to-head on the OUT set, all re-priced at our entry, event-clustered:
         (a) ROUTER (argmax + abstain),  (b) SKILL-WEIGHTED mean (TrustWeighted / CellPooled),
         (c) FLEET-AVERAGE consensus (WeightMode::Quality — the incumbent that regresses to +2.5%).
       And report each vs (d) B_LB from step 3. The user's question, answered as far as power allows:
       "router ≥ B_LB AND router > current strategies, out-of-sample?"
     - Two splits, both leak-free:
         TEMPORAL (persistence): learn on event-dates [d_lo,d_cut), test on [d_cut,d_hi) via
           asof_slice_scores.sql window params. Score OUT rows only.
         WITHIN-TRADER LEAVE-ONE-SPORT-REGIME-OUT (the NOW experiment, H3): for each wallet, hold out
           one SPORT-REGIME, learn the ranking on the rest, test on the held-out regime. Hold out by
           sport-regime (NOT arbitrary slice) so the held-out context is genuinely independent — this is
           the guard against within-tournament leakage. Measures routing-vs-averaging using cross-context
           variance we HAVE, not cross-time accrual we don't. This can return a SIGNED answer today.
     - Belief-blind gate on router picks: run selection_null.py on the router's OUT picks, matched on the
       (band × UTC-day) profile OF THE PICKS; require p_emp ≤ 0.01 with --calibrate PASS. Plus
       promotion_verdict LB > 0.03 at ≥30 events, day-deflated SE. Plus ≥2 disjoint sport-regimes.
     - --selftest + writes reports/router_report.json (three-way per split, with CIs and gate verdicts).
5. Build scripts/consensus_fade.py (NEW, forward probe, script-only — H5, the secondary lead).
     - Detect ≥3 distinct one-sided band5 heavy-favorite (entry ≥ 0.80) convergences using score_market
       semantics (consensus.rs:337), then score the OPPOSITE (NO) side at honest entry
       (COALESCE(entry_ask, initial_market_price+0.01), roi convention from consensus.rs:715-803).
     - Gate: selection_null (fade picks vs matched blind) + promotion_verdict + ≥2 disjoint regimes.
       ANTI-OVERFIT GUARD: HOLD OUT the discovery cell (soccer/directional/band5); certification requires
       the fade to persist in ≥1 sport-regime it was NOT discovered on (transfer test).
     - --selftest + writes reports/consensus_fade.json. If it ever certifies OOS: flag a NEW DEFERRED
       `consensus_fade` StrategyDef (alerting:false) for HUMAN review — do NOT wire it this run.
6. Extend scripts/readiness_ledger.py (the beats_best_trader / router_gate / unified_book rows ALREADY
   EXIST — extend, don't duplicate): add rows router_vs_best, router_vs_fleet, fade_transfer, and
   mm_screen_refinement (relaxed-vs-frozen cohort forward-return + profit-source agreement) — each with
   STATUS / value-vs-threshold / what's-needed / ETA. Keep the board's binding constraint = the unmet
   gate with the LONGEST horizon (expect persistence/accrual = months; regime-persistence last came back
   SOCCER-ARTIFACT, so a soccer-only "pass" is not a pass).

## THE GATE (every candidate clears ALL — verified functions)
- promotion_verdict (promotion.rs:209): distinct_events ≥ 30; Bonferroni alpha_corr = alpha/n_strategies
  (per family — experimental arms never tighten the core bar); cluster-deflated SE se = sd/sqrt(effective_n),
  effective_n = distinct_days (unknown days ⇒ effective_n=1 ⇒ never promotes, fail-closed);
  lower_bound = surplus − z·se > margin 0.03; selection_null_p ≤ 0.01 checked BEFORE margin.
- selection_null.py with a --calibrate PASS (≥1000 draws, ~uniform pseudo-p; else "anti-conservative —
  do not trust the null"); feed SELECTION_NULL_P to Rust.
- ≥2 DISJOINT sport-regimes positive (selection_null.py:198-222).
- pilot_verdict (honest.rs:90): honest-ROI LB > 0.02; ≥50 distinct events; ≥5 positive day-regimes;
  ≥70% of regimes positive; median-sharp liquidity ≥ $2000.
- beats_best_trader (best_trader_benchmark.py, step 3): S.honest_roi_LB > B_LB + 0.03 AND S.sharpe > B_sharpe.
- λ̂ CI-lower > 0.25 (clv_lambda.py / clv_monitor.py).
Fail ANY ⇒ candidate is HOLD / INDETERMINATE-BY-POWER, never promoted.

## PER-CYCLE LOOP (repeat until a STOP condition; ~30–60 min/cycle)
1. SNAPSHOT: re-run readiness_ledger.py; note distinct events / days / disjoint sport-regimes; dense-
   capture coverage %. Resolutions flow automatically (housekeeping.rs:165 append_paper_bet, idempotent).
2. ADVANCE one build target or one hypothesis (setup order first, then iterate refinements). Every new
   script ships with a passing --selftest on synthetic fixtures BEFORE any live-DB read.
3. MEASURE (read-only, snapshot): honest_pnl_by_strategy + honest_pnl_segments (board.rs:729),
   selection_null.py + --calibrate, best_trader_benchmark.py (with the eligibility screen), router
   backtest (router_verify.py / trader_scorecard.py), consensus_fade.py, mm_screen_effect.py +
   mm_persistence_effect.py + regime_net_edge.py (the MM-filter / profit-source suite, H7),
   clv_lambda.py (λ̂+CI), copyability.py, tail_records.py, relational_probes.py (P1/P2/P3),
   persistence_tracker.py.
4. GATE each candidate; record the FIRST binding failure verbatim, plus LB, surplus, distinct_events,
   distinct_days, regimes_positive, B_LB, B_sharpe, λ̂.
5. SELF-VETO (promote NOTHING if ANY holds): distinct_days < K (pre-set, e.g. 5) ; λ̂ CI-lower < 0.25 ;
   < 2 disjoint sport-regimes positive ; selection_null --calibrate FAIL ; N_elig too thin for a
   meaningful B_LB. Mark INDETERMINATE-BY-POWER with the binding reason. Do NOT tune thresholds to
   manufacture a pass — that is the market_resid false-promote class; it is refuted; do not resurrect it.
6. WRITE: append the cycle's numbers to the journal + reports/*.json; update the forward watch-list
   (arms/cells nearest their gate, and which regime accrual would unlock them). Commit with a NEW/EXTEND-
   flagged message.
7. REPORT the honest daily digest (format below).

## STOP CONDITIONS (any ⇒ end the run and write the final report)
- Cycle / wall-clock budget exhausted; OR
- Every candidate INDETERMINATE-BY-POWER AND no new resolutions since the last cycle (nothing to learn
  until more data accrues) — hand back the watch-list; OR
- A candidate is PROMOTABLE-eligible under the FULL gate — STOP, do NOT promote, escalate to human with
  the full gate readout (a real edge on 4 days is far more likely a bug than an edge; demand the
  persistence months); OR
- Any anomaly: selection_null --calibrate FAIL, capture-completeness collapse, or a gate self-
  inconsistency — HALT immediately and report; OR
- You catch yourself tuning a threshold to force a pass — STOP; that is the failure mode this run exists
  to prevent.
- NEVER stop by promoting to real money. That path does not exist in this run.

## HONEST DAILY DIGEST (exact format)
### Run <name> — cycle <n> — <UTC ts>
ACCRUAL: distinct events <n> (+<Δ>), distinct days <n>, disjoint sport-regimes positive <k>/<total>.
λ̂: <point> CI [<lo>,<hi>] (floor 0.25 → <ABOVE/BELOW>).  Dense-capture ask coverage: <%>.
ELIGIBILITY / MM-FILTER (H7): wallets kept <n>/<total> | pure-MM excluded <n> (arb/rebate) |
  directional-maker KEPT <n> | relaxed-vs-frozen cohort fwd-return <±% vs ±%> | profit-source
  disagreements resolved <n> (restore <n> / exclude <n>).
BEAT-BEST-TRADER BENCHMARK (per context, PREDICTORS ONLY): B_LB=<..>, B_sharpe=<..>,
  B_point=<..>(selection-inflated; is_mm=<y/n>), N_elig wallets=<..>, best wallet=<name> —
  or "INDETERMINATE-BY-POWER: <reason>".
OPERATOR HEAD-TO-HEAD (OUT set, both splits): router <±%> | skill-weighted <±%> | fleet-avg <±%> | B_LB <±%>.
  H3 within-trader LOO routing-vs-averaging: SIGNED result = <+/− x%, CI> → <favors ROUTING / favors AVERAGING / INDETERMINATE>.
CANDIDATE ARMS (each): surplus <±%>, LB <±%>, promotion=<PASS/HOLD:reason>, pilot=<GO/HOLD:reason>,
  selection_null p=<..> (calibrate <PASS/FAIL>), beats_best_trader=<PASS/HOLD/INDETERMINATE:reason>.
FADE PROBE (H5): discovery-cell-held-out surplus <±%>, transfer to <regime>=<verdict>.
RELATIONAL (relational_probes): P1 <..> P2 <..> P3 <..> — verdicts.
VERDICT THIS CYCLE: <nothing promoted — INDETERMINATE-BY-POWER | CANDIDATE for future human-reviewed
  armed pilot: arm X cleared all gates OOS>.
BINDING CONSTRAINT: <the one unmet gate with the longest horizon, from readiness_ledger>.
NEXT: <the single accrual that would move the needle — e.g. "esports / NFL regime population">.
WATCH-LIST: <arms/cells nearest their gate + what unlocks them>.

## FINAL REPORT (write to reports/BEAT_BEST_TRADER_RUN_<utc>.md)
1. One-line verdict on "can we beat the best trader at our price" (expected: not yet certifiable;
   benchmark + router now forward-accruing; the H3 LOO routing-vs-averaging result = <signed answer>).
2. Per-hypothesis table H1–H7: statistic | gate verdict | binding constraint | what would flip it | ETA.
3. THE three-way number: router vs skill-weighted vs fleet-average vs B_LB, per split, with CIs.
4. THE NOW result (H3): the within-trader LOO routing-vs-averaging sign + CI, stated plainly. If it
   favors routing → green-lights the router thesis for accrual. If it favors averaging → evidence the
   copy-the-max thesis is structurally dead at our price; report it as such.
5. λ̂ status: proxy vs measured, CI, floor verdict, dense-capture coverage %.
6. ELIGIBILITY / MM-FILTER verdict (H7): pure-MM excluded vs directional-maker kept; whether the
   round_trip-relaxed + profit-source screen beats the frozen screen on cohort forward copy-return;
   the D29 40-restore / 92-exclude reconciliation as re-measured; and an explicit statement that
   nothing was mutated in Rust (Phase-1 STOP holds until forward-confirmed).
7. Readiness-ledger delta: what moved, the binding constraint (expect persistence/accrual = months),
   the auto-promotion trigger.
8. NEW artifacts built + DEFERRED wiring flagged for human review (expect: small — the benchmark,
   router, and MM-filter already exist; new work is the relaxed/profit-source eligibility screen).
9. What this run did NOT do and why (promoted nothing; mutated no Rust threshold; the desert; the wall).
Report the truth, including "no bankable edge exists today." A rigorous proof of whether beating the best
trader at our price is even possible is a first-class success of this run.

## PRINCIPLES (memory-binding)
Belief in the GENERATOR, rigor only at the belief-blind gate. Critical-partner: push back with evidence,
never validate-to-feel-good. Depth over breadth: keep the arm/probe set SMALL, one hypothesis each (every
arm widens the experimental Bonferroni denominator). Out-of-sample persistence is the wall; accrual is
the binding constraint everywhere. Extend, don't rebuild — the instruments exist, compose them. A run
that promises a bankable winner on today's data would overfit and violate the gate — do not.
```

# ══════════════  END RUN PROMPT  ══════════════

## Operator checklist before launch
- Restore a fresh prod snapshot into `pg-report` (measurement never touches prod).
- Confirm `.env.consensus` **and** the compose `environment:` block both carry the three env flags
  (env drift between them is a known footgun).
- The run needs `scripts/selection_null.py --calibrate` to PASS first — if the null is anti-conservative,
  every downstream verdict is void.
- Confirm the eligibility screen before the benchmark run: `scripts/mm_screen_effect.py` shows the
  relaxed screen's cohort forward copy-return ≥ frozen; the profit-source test (`regime_net_edge.py`
  net_maker) agrees with `two_sided_rate` on the arber class. This is what removes the pure
  market-makers/rebate-harvesters while KEEPING directional traders who post maker orders to dodge fees.
- No Rust threshold change ships this run (D29 Phase-1 STOP): `refresh_router_followset` stays frozen at
  0.30/0.25/0.50; the relaxed/profit-source screen lives in the Python research layer until forward-confirmed.
- This run **cannot** and **must not** arm real money; `PILOT_ARMED` stays unset by construction.
