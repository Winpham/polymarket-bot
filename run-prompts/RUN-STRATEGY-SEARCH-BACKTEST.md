# Long Autonomous Run — Strategy Search & Honest Backtest (anti-overfit by construction)

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot`. **Branch off the integration branch the auto-updater deploys** —
it is now `main` (consolidated). Work in a dedicated git worktree; gate-green + commit after
EVERY phase; at the end `merge --no-ff` into `main` so the auto-updater deploys it. Companion
reading (REQUIRED — build on these, don't duplicate): `REFINED-STRATEGY.md` (current best
hypothesis), `run-prompts/RUN-HONEST-PNL-TRACKER.md`, `scripts/asof_preflight.py` +
`asof_slice_scores.sql` (the as-of certification), the merged honest-P&L tracker, `DATA-MODEL.md`.

---

## 0. The one-sentence mission
Systematically search the strategy space over the data we have, evaluate every candidate on a
**leak-free, CLV-based, execution-haircut, event-clustered** backtest, and — because the record
is **one FIFA World Cup weekend** — **quantify and subtract the overfitting** (multiple-comparison
correction over the whole search + a shuffled-outcome overfit floor + out-of-sample holdouts), so
the output is the **best DEFENSIBLE strategy with a deflated, honest expected edge and a
certification verdict**, plus a re-runnable harness that sharpens as more regimes accrue — not a
green backtest number.

The motto: **the backtest is a microscope on overfitting, not a profit oracle. Every config tried
counts against us. A candidate must beat its own shuffled ghost and survive out-of-sample, or it's
noise. Inform what to watch forward; the forward gate — not the backtest — promotes.**

---

## Philosophy — read first, it overrides everything
- **The data is ~2.4 days ≈ one World Cup weekend (~89% WC soccer).** A search over it WILL find
  gorgeous configs. Most are noise. This run exists to measure HOW MUCH is noise and hand back only
  what survives deflation — not to celebrate the top of a leaderboard. Per the congregation
  SUCCESSFUL NULL, the honest likely output is "leading candidate X, but its edge is mostly
  overfit; here is the deflated residual and its (in)determinacy."
- **Every candidate evaluated is a comparison.** "Best of 500 configs" over one weekend is almost
  certainly the max of 500 noise draws. We correct for the FULL search size (Bonferroni / a deflated
  performance bound), and we PRE-REGISTER a bounded, meaningful config grid rather than mining
  unboundedly — mining inflates the correction and the overfit.
- **Deflate, don't trust.** Three mandatory deflators before believing any candidate: (1)
  multiple-comparison correction across the whole search; (2) a **shuffled-outcome overfit floor**
  (re-run the ENTIRE search on permuted outcomes — the best ghost candidate is the noise the search
  can conjure; subtract it); (3) **out-of-sample** (by-sport, by-time, event-clustered k-fold CV) —
  report IS→OOS degradation.
- **Realizable, not flattering.** CLV (outcome vs the mid we observed while open) minus an explicit
  execution haircut (ask/spread + fee), **flat-SHARES** sizing (flat-$ over-exposes to longshots and
  flips the sign), event-clustered at the distinct-EVENT level. Inherit the honest-P&L discipline;
  reuse its machinery.
- **Leak-free (preserve it).** Selection uses only pre-resolution fields; `outcome_won` is a label
  written only at resolution; entry prices are strictly pre-resolution (`initial_market_price`,
  captured open-only). A backtest that lets the outcome touch selection or entry is worthless.
- **No new live arm, no real money.** The deliverable INFORMS which config to TRACK forward through
  the existing belief-blind gate (as-of, ≥30 independent events, multi-regime). The backtest never
  authorizes a bet. Paper/analysis only.

---

## The honest metrics (implement exactly; reuse honest-P&L where built)
For a resolved signal: `p0 = initial_market_price` (our open-market mid), `w = outcome_won::int`,
event key `ev = COALESCE(event_slug, condition_id)`, band `= width_bucket(p0,0,1,5)`.
- **Entry (executable):** `entry = COALESCE(entry_ask, p0 + EXEC_HAIRCUT)` (`EXEC_HAIRCUT` config,
  default 0.01; buy-side). Net of `FEE_PCT` (≈0 today).
- **Flat-SHARES P&L:** fixed `SHARES` per bet → `pnl = SHARES × (w − entry)`; ROI on stake =
  `(w − entry)/entry`. (Never flat-dollar.) Event-cluster ROI: mean within `ev`, then across events.
- **Confidence:** event-clustered mean + `STDDEV_SAMP` of per-event ROI → **bootstrap CI** (resample
  events). Report distinct_events, hit-rate, equity curve, max drawdown, a Sharpe-like ratio.
- **A candidate** = a config over the population: `price_band (lo,hi)`, `consensus_level ∈ {count,
  rank, trust, trusted}`, `min_consensus`, `side ∈ {all, favorite}`, `sport_filter`, `freshness
  (recency_mins cap)`, `sizing ∈ {flat_shares, quarter_kelly}`. Evaluated leak-free over resolved
  rows with `p0` present. The incumbents to BEAT: `favorite`, `elite_fresh_fav` (REFINED-STRATEGY.md),
  and the blind-favorite baseline (blind uses `mean_price` — `_blind` has no `p0`).
- **Multiple-comparison-corrected lower bound:** with `K` = total candidates searched, correct α by
  `K` (Bonferroni) OR report a deflated-Sharpe bound (Bailey/López de Prado); reuse the binary's
  `promotion.rs` (`surplus_bounds`/probit) for the per-candidate bound, apply the `K` denominator.
- **Overfit floor:** `deflated_edge = candidate_edge − best_shuffled_candidate_edge` (from the full
  search re-run on permuted `w` within band, averaged over many shuffles).
- **Verdict per candidate:** **CERTIFIED** (corrected OOS lower bound > `MARGIN` (default 3%), ≥
  `MIN_EVENTS` (default 30) distinct events, positive across ≥2 disjoint regimes) / **INDETERMINATE**
  (positive but under the bar) / **OVERFIT** (good IS, collapses OOS or below the shuffle floor).

---

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (the harness home): `python3 -m py_compile <f>` + a smoke run on a synthetic fixture.
**numpy/pandas only** (no scipy/sklearn unless already present — `python3 -c "import scipy"`; the
bootstrap, folds, and shuffles are hand-rolled). Live-verify DB reads on a **throwaway Docker
Postgres** (migrations via `run_migrations`, seed a fixture with resolved rows + `initial_market_price`,
run the harness, inspect). This run is READ-ONLY on the DB (no new tables needed unless Phase 4 caches
the report — then migrations are append-only, next free number = `ls migrations/`). New tunables go in
the compose `environment:` allowlist as `${VAR:-default}` and are verified in the container. Deploy
ONLY via the auto-updater script.

---

## Context (extend, don't rebuild — verified; grep to pin lines)
- `common/src/storage/consensus.rs` — `consensus_scoreboard_by_strategy` (surplus + CLV + band SQL to
  mirror), the honest-P&L query if the tracker merged it, `StrategyScore`; `consensus_signals` cols:
  `strategy, condition_id, outcome_index, event_slug, initial_market_price, mean_price, outcome_won,
  resolved, resolved_at, first_detected_at, net_count, n_backers, best_backer_rank, is_sports,
  recency_mins, total_usd`; `entry_ask`/`first_features` if the harden/tracker runs added them.
- `scripts/asof_preflight.py`, `asof_slice_scores.sql` — the as-of, leak-free, capture-margin
  certification (the gate the backtest's survivors must eventually pass forward). REUSE its
  event-clustering + Bonferroni conventions; do NOT re-derive a different certifier.
- `copy-trading-bot/src/scanner/promotion.rs` — `promotion_verdict`, `surplus_bounds`, private
  `probit`, `PromotionParams {min_events, margin, alpha}`. The corrected-bound machinery to reuse.
- `copy-trading-bot/src/scanner/consensus.rs` — the strategy definitions + `WeightMode`
  (count/quality/trust) + `quality_weight(rank)` — the consensus-level ladder the search parameterizes.
- `REFINED-STRATEGY.md` — the current best hypothesis + the metrics we already track (consensus-vs-
  blind-favorite premium, flat-shares vs flat-$, the level ladder). The backtest must reproduce these
  numbers as a sanity check and try to BEAT the incumbent.
- `copy-trading-bot/src/board.rs` — the board (`BOARD_PORT` 9002) for the Phase 4 leaderboard panel.
- Scheduling: `~/Library/LaunchAgents/com.tue.consensus.*.plist` + `scripts/consensus-autoupdate.sh`
  (launchd pattern for the auto re-run agent). `scripts/` — Python harness home (mirror
  `asof_preflight.py` / `train_market_resid.py`: argparse, `$DATABASE_URL` via psycopg2 or `--input`).

---

## Rejected approaches (do not build these)
- **Grid-search → report the top config's raw backtest.** That's the overfit trap. Never surface a
  candidate without the multiple-comparison correction, the shuffle floor, AND the OOS degradation.
- **Unbounded mining.** Pre-register a bounded, findings-motivated grid; every extra knob inflates the
  correction and the overfit. Log `K` and correct by it honestly.
- **Flat-dollar sizing / `edge` vs `mean_price` / pooled (non-event-clustered) stats.** Use flat-shares,
  CLV−haircut, event-clustered — inherited from the honest-P&L discipline.
- **Building a new live arm or betting from the backtest.** The output informs what to WATCH forward;
  the forward as-of gate promotes. No real money.
- **scipy/sklearn or new deps; probit-in-SQL.** numpy/pandas only; corrected-bound math in the binary
  or hand-rolled; SQL stays sums/means/stddev.
- **Ignoring the leak rails.** Any config whose selection or entry can see the outcome is invalid.

---

## Phase 0 — The backtest evaluation primitive (`scripts/strategy_backtest.py`)
**Goal:** a leak-free function `evaluate(config) -> metrics` that filters resolved signals and returns
honest CLV−haircut, flat-shares, event-clustered metrics + equity/drawdown + bootstrap CI.
- Read resolved rows (`$DATABASE_URL` or `--input` fixture). Apply the config filter (band, level,
  min_consensus, side, sport, freshness, sizing). Compute the metrics above. numpy/pandas only.
- **Sanity gate:** reproduce the known numbers from REFINED-STRATEGY.md — favorites-only ≈ +$900-1,300
  paper (flat-$ for that check), the consensus-vs-blind-favorite premium (+6-11 pts), and the
  flat-shares(+$571) vs flat-$(−$4,584) `strict` split. If it can't reproduce these, the primitive is wrong.
**Verify:** synthetic fixture with a known edge → recovered within CI; a no-edge fixture → ≈0;
event-clustering + leak rails asserted. Gate (`py_compile` + smoke), commit.

## Phase 1 — Pre-registered search + multiple-comparison correction
**Goal:** enumerate a bounded, findings-motivated candidate grid, evaluate all, and rank by the
CORRECTED lower bound (not the point estimate).
- Pre-register the grid in the script header (bands × consensus_level × min_consensus × side × sport ×
  freshness × sizing) — bounded to a few hundred meaningful configs, NOT a mine. Log `K` = |grid|.
- Evaluate every candidate (Phase 0). Rank by the Bonferroni(`K`)-corrected event-clustered lower
  bound (reuse `promotion.rs` bound machinery / hand-rolled probit). Emit the full ranked table +
  the incumbent (`favorite`/`elite_fresh_fav`) rows for comparison.
**Verify:** on a fixture the corrected bound tightens with `K`; the incumbent appears; the search is
deterministic + logged. Gate, commit.

## Phase 2 — The three deflators (overfit floor, OOS, degradation)
**Goal:** subtract the overfitting; only survivors advance.
- **Shuffle floor:** re-run the ENTIRE Phase-1 search on `w` permuted within band (many shuffles,
  seed-logged); record the best-ghost edge per shuffle → the overfit floor distribution. `deflated_edge
  = candidate_edge − mean(best_ghost)`; also report the percentile of the real best vs the ghost
  distribution (a real edge sits far in the tail).
- **Out-of-sample:** by-sport holdout (fit-select on soccer, test on tennis/MLB and vice-versa —
  report coverage honestly given ~89% soccer), by-time holdout (day1-2 select → day3 test),
  event-clustered k-fold CV. Report IS vs OOS ROI + degradation for the top candidates.
- Assign each top candidate a **verdict** (CERTIFIED / INDETERMINATE / OVERFIT) per the rule above.
**Verify:** a fixture with an injected edge survives the deflators; a fixture that is pure noise →
the search's best candidate is INDETERMINATE/OVERFIT and its deflated edge ≈ 0 within CI (the harness
correctly refuses to hallucinate). Gate, commit.

## Phase 3 — Refinement loop + the honest recommendation
**Goal:** from the survivors, iterate a few targeted refinements (e.g., favorites × sport × freshness),
re-run Phases 0-2 on the refined set (counting the extra candidates in `K`), and converge on the single
best DEFENSIBLE config.
- Emit `reports/strategy_search.json` + a plain summary: the ranked leaderboard (raw, corrected,
  deflated, OOS), the incumbent vs best-defensible delta, the recommended config with its **deflated,
  corrected expected edge + CI + verdict**, and an explicit **"what to watch forward"** (the config to
  track through the as-of gate) — with the honest caveat that on one tournament the most likely verdict
  is INDETERMINATE. NO new live arm; NO bet authorization.
**Verify:** the report is reproducible from a fixture; the recommendation never exceeds what the
deflators support (assert recommended.deflated_lower_bound is what's surfaced, not the raw best). Gate, commit.

## Phase 4 — Durable harness: board leaderboard + auto re-run as data accrues
**Goal:** make the search continuous and legible so it sharpens with each new regime.
- `copy-trading-bot/src/board.rs`: a "Strategy Search" panel reading `reports/strategy_search.json` —
  the top configs with raw vs corrected vs deflated edge, OOS degradation, verdict, and a one-line
  headline ("best-defensible: <config> — deflated +X% [verdict]; incumbent favorite +Y%"). Fail-soft
  if the report is missing/stale. Clearly label read-only / paper / not-a-bet-signal.
- A launchd agent `com.tue.consensus.search` (RunAtLoad + StartInterval, e.g. daily) runs the harness
  against prod and refreshes the JSON. Idempotent, best-effort, logs to a file.
**Verify:** the panel renders from a fixture report; the agent runs and refreshes; stale/missing
degrades gracefully. Gate, commit.

## Phase 5 — QA, reliability, merge, deploy, verify
- QA gates baked in: assert the shuffle floor is computed and subtracted before any recommendation; the
  correction denominator equals the true search size `K`; OOS degradation is reported for every surfaced
  candidate; leak rails asserted (outcome never in selection/entry); the noise-fixture yields ≈0 deflated
  edge. Confirm READ-ONLY + non-regressive: live `strict`/alerting byte-identical; no writes unless the
  Phase-4 report cache (append-only migration) is enabled.
- Final `merge --no-ff` into `main`; deploy via the auto-updater script.
- **Post-deploy VERIFY (do not skip):** new env vars in the container; the launchd search agent produced
  a fresh `strategy_search.json`; the board panel is live; ingestion + 0 restarts intact. **Report the
  first real result:** the best-defensible strategy, its RAW vs CORRECTED vs DEFLATED edge + CI, its OOS
  degradation, its verdict, and how it compares to the incumbent `favorite` — the honest answer to "what
  is the best strategy and is it actually better."

---

## Acceptance
Every phase gate-green + committed; final `merge --no-ff`. Deliverables: a numpy/pandas, leak-free,
CLV−haircut, flat-shares, event-clustered backtest primitive that reproduces the known numbers; a
pre-registered, bounded strategy search with an honest multiple-comparison correction over the full
search size; three deflators (shuffle overfit-floor, by-sport/by-time/event-k-fold OOS, IS→OOS
degradation) with per-candidate CERTIFIED/INDETERMINATE/OVERFIT verdicts; a reproducible report + a
single best-DEFENSIBLE recommendation surfaced at its deflated corrected lower bound (never the raw
best); a board leaderboard + a self-running launchd re-run that sharpens as regimes accrue. Read-only,
non-regressive, self-healing. Informs what to watch forward; the forward as-of gate promotes. NO real money.

## Standing disciplines
The backtest is a microscope on overfitting, not a profit oracle; every config tried counts toward the
correction; pre-registered bounded grid, not a mine; three deflators mandatory (correction + shuffle
floor + OOS) before any recommendation; surface deflated corrected lower bounds, never raw bests;
CLV−haircut realizable, flat-shares, event-clustered; leak-free (outcome as label only, entry strictly
pre-resolution); numpy/pandas only, no new deps; read-only + non-regressive; reuse asof_preflight +
promotion.rs, don't re-derive certifiers; migrations append-only; every tunable in the compose allowlist
and verified in-container; commit per phase; `merge --no-ff`; deploy via the auto-updater; NO real money.
