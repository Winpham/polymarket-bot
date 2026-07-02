# FORGE_PLAN_FABLE_RUN — at-fire gate integrity + standing selection null (2026-07-02)

Implementation blueprint for the Fable improvement run. After this is built: the promotion gate
judges strategies on the **at-fire** consensus entry (not the upsert-drifted one), every promotion
candidate must additionally survive a **standing selection-matched null** (the market_resid
false-promote class gets a permanent defense), real executable asks accrue from today, sport-regime
persistence is measured, and the paper ledger reports the flat-shares discipline alongside flat-$.

Pre-run anchor: `main = ae0db80`, tag `pre-fable-run-20260701`. Branch `fable/improve-run-20260702`
in worktree `~/pmkt-fable-run`. Rollback of everything: `git reset --hard pre-fable-run-20260701`
(plus removing one env line, Item 0). Gate at every commit:
`cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace` (+ build).

## Pre-registered hypotheses (fixed BEFORE code)

- **H1 (F1):** the scoreboard's drifted `mean_price` entry understates true at-fire surplus. On the
  live DB, switching to `initial_mean_price` moves `favorite` (N=92) from LB +0.2% to LB +3.3%
  (> 3% capture margin) and `elite_fresh_fav` (N=38) to LB +4.8%. Prediction: the parity harness
  shows N unchanged per strategy, surplus deltas explained by drift alone.
- **H2 (F2):** a (band × UTC-day)-matched random-selection null over `_blind` separates
  selection-skill from composition: `elite_fresh_fav` p<0.005 and `favorite` p≤0.01 survive;
  `strict`/`count`/`whales` read NULL. Calibration prediction: the same null applied to random
  `_blind` subsets yields approximately uniform p (no anti-conservative bias).
- **H3 (F4):** the favorite-band consensus surplus is positive in ≥2 disjoint sport-regimes with
  regime-matched blind baselines (already observed at-fire: elite_fresh_fav soccer +6.0/tennis +8.3;
  favorite positive in 4/4). The sport-segment instrument will keep showing this as data accrues —
  if it collapses in a new regime, the gate must see it.
- **H0 (standing):** nothing is promoted to alerting or real money in this run. All items are
  measurement/instrument fixes. `strict` alerting, `trader_trust`, honest-P&L math, as-of harness
  stay byte-identical except where the parity harness proves the scoreboard fix strictly better.

## Binding kill-criteria

- K1: if the at-fire switch changes any strategy's `distinct_events` (it must only change surplus
  values), or requires touching `strict` alerting/`trader_trust` code paths → STOP Item 1, re-scope.
- K2: if the null instrument's calibration check is anti-conservative (>20% of known-null runs give
  p<0.05) → the instrument does NOT ship; report the failure.
- K3: if sport-regime mapping covers <95% of resolved event_slugs → extend patterns or bucket
  'other'; never guess a sport.
- K4: any commit that can't go gate-green cleanly is reverted, not patched around.
- K5: nothing merges to main unless ALL items are green and the REPORT's before/after is written.

---

## Item 0 — Ops: turn on real book-ask capture (F3). NO code.

**Before:** `entry_ask` coverage 0% (0/178 favorite rows); honest P&L runs on mid+1¢ heuristic.
**After:** every strict-fired signal captures the real CLOB best ask at first detection (cap 40/cycle).
**Implementation:** append to `~/polymarket-bot/.env.consensus`:
```
# 2026-07-02 Fable run (Item 0): capture real executable asks (paper realizability data;
# additive, flag-gated code shipped in 8e59b68; revert = delete this line + recreate stack)
CAPTURE_ENTRY_ASK=true
```
then `docker compose -f docker-compose.consensus.yml --env-file .env.consensus up -d` (recreate).
**Verify:** within ~3 cycles `SELECT count(*) FROM consensus_signals WHERE entry_ask IS NOT NULL`
grows; data-api 429 counter does not spike (board header).
**Reversibility:** delete the line, recreate. Not git-tracked → recorded in DECISIONS.md (D5).
**Source:** direct (shipped code; the only missing piece was the flag).

## Item 1 — Scoreboard at-fire entry (F1): drifted `mean_price` → set-once `initial_mean_price`

**Before:** `consensus_scoreboard_by_strategy` (common/src/storage/consensus.rs:524-572) computes
`a = outcome_won − mean_price`, `band = width_bucket(mean_price,…)`; `mean_price` is overwritten on
every upsert (consensus.rs:226) so the gate's entry embeds post-fire information (avg drift +1.2¢ on
strict; 29% of rows move >2¢). favorite reads LB +0.2% → NOT promotable (a false negative).
**After:** `a = outcome_won − COALESCE(initial_mean_price, mean_price)`, band likewise, for BOTH the
strategy rows and the `_blind` baseline; `capture_lag = initial_market_price − initial_mean_price`.
favorite reads LB +3.3% at the 3% capture margin; the board shows the honest at-fire gate.

**Implementation (SQL delta, in place — safe-swap proven by parity harness):**
In the `adv` CTE (consensus.rs:525-530):
```sql
SELECT strategy, COALESCE(event_slug, condition_id) AS ev, resolved, outcome_won,
       width_bucket(COALESCE(initial_mean_price, mean_price), 0.0, 1.0, 5) AS band,
       (outcome_won::int)::double precision
         - COALESCE(initial_mean_price, mean_price) AS a
FROM consensus_signals
```
In `clv_evt` (consensus.rs:548-555): `AVG(initial_market_price - COALESCE(initial_mean_price, mean_price)) AS ev_lag`.
(100% of rows have `initial_mean_price` today — COALESCE is belt-and-suspenders for any legacy path.)
Update the doc comment: the entry is the AT-FIRE consensus mean (set-once at insert,
consensus.rs:212-214), because we act at fire (REFINED-STRATEGY rule 4); the drifted `mean_price`
remains stored for capture/diagnostics but never judges.

**Regression tests (new, in consensus.rs tests or enrich e2e):**
`#[ignore]`d live-DB test `scoreboard_uses_at_fire_entry`: seed one signal with
`initial_mean_price=0.50` then upsert-drift `mean_price=0.60`, resolve won=true; assert the
scoreboard row's edge/surplus reflects 0.50 (a=+0.50), not 0.60. Mirror an equivalent pure test if
feasible. Existing 6/6 promotion tests + enrich passthrough must stay green untouched.

**Parity harness (proves the swap, keeps the before-picture):** `scripts/scoreboard_parity.py`
(stdlib-only, house pattern of scripts/asof_preflight.py): runs BOTH the drifted and at-fire
versions of the exact scoreboard SQL against the live DB, prints per-strategy
(N_old, N_new, surplus_old, surplus_new, Δ, LB_old, LB_new @3% margin, family-Bonferroni z) and
asserts N_old == N_new for every strategy (K1). Output goes in the REPORT verbatim.

**Consumers (all inherit the fix, no signature change):** board.rs:347 render; telegram
commands.rs:69 `/consensus`; enrich/mod.rs:525 e2e test.
**Source:** hybrid — in-place fix (direct) + parity-harness proof (rethink's safe-swap evidence).

## Item 2 — Standing selection-matched null (F2): one-off nulls → permanent instrument + rule

**Before:** the gate can false-promote composition artifacts (market_resid: +30% "surplus",
permutation z −0.10). No routine null exists; the market_resid null was a one-off.
**After:** `scripts/selection_null.py` is a repo instrument run per tournament block (and before ANY
promotion decision), and the promotion RULE is pre-registered: a strategy is promotion-eligible
only if (a) gate LB > capture margin (existing math), AND (b) selection-null p_emp ≤ 0.01, AND
(c) regime-matched surplus positive in ≥2 disjoint sport-regimes (Item 3's readout).
Rust stays byte-identical this run — the rule binds the HUMAN promotion call and is written into
promotion.rs module docs, DECISIONS.md (D6), and the board footnote (single HTML string edit).

**Implementation (`scripts/selection_null.py`, stdlib-only, seeded):**
- Input: `DATABASE_URL` or docker-exec fallback (copy asof_preflight.py's connection pattern).
- Pull resolved signals: strategy, ev=COALESCE(event_slug,condition_id), at-fire entry
  (COALESCE(initial_mean_price, mean_price)), outcome_won, first_detected_at.
- Statistic (exact scoreboard mirror): event-clustered mean of `a − blind_edge[band]`, blind_edge
  from `_blind` rows at the same at-fire convention.
- Null: 2000 seeded draws; each draw samples from the `_blind` pool matched to the strategy's
  (band × UTC-day) pick profile (sample without replacement per cell; `random.choices` only when
  the cell pool is smaller than the strategy's cell count), scored with the identical statistic.
- Output table per strategy: N_events, observed, null μ±σ, z, one-sided p_emp, verdict
  (`SELECTION-REAL` p≤0.01 / `indeterminate` / `NULL`), plus a multiplicity note (Bonferroni ×
  number of strategies tested).
- `--calibrate` mode (K2): treat 50 random `_blind` subsets (matched to a reference profile, e.g.
  favorite's) as pseudo-strategies; print the p distribution; PASS iff ≤20% of runs give p<0.05
  and ≥60% land in [0.1, 0.9].
**Verify:** run both modes on the live DB; H2 predictions hold; calibration passes.
**Source:** refined — prototype (scratchpad null_harness.py) promoted to house conventions +
calibration self-test + pre-registered combined rule.

## Item 3 — Sport-regime persistence instrument (F4): day-regimes only → sport segments visible

**Before:** `honest_pnl_segments` (consensus.rs:663+) emits seg_kinds day/band/horizon; the true
disjointness axis (tournament/sport) is invisible; the gate's regime requirement lives nowhere.
**After:** the segments query ALSO emits `seg_kind='sport'` rows (soccer/tennis/mlb/crypto/cs2/
other via event_slug prefix), the board honest-panel tooltip shows `sports: soccer +5.9 · tennis
+8.3 …`, and selection_null.py prints the per-sport regime table used by rule (c) of Item 2.
`pilot_verdict` logic UNTOUCHED this run (instrument-first; gate-requirement is a later, separate
pre-registered change once ≥3 regimes have floor-N).

**Implementation:** one SQL CASE fragment, defined ONCE as a Rust const (new, in
common/src/storage/consensus.rs near the segments query) and reused by both segment SQL and the
Python scripts (documented duplication with a parity unit test listing each prefix):
```sql
CASE WHEN event_slug ~ '^(btc|eth|sol|xrp|bnb|doge|hype|bitcoin|ethereum)' THEN 'crypto'
     WHEN event_slug ~ '^(atp|wta|itf)' OR event_slug LIKE '%wimbledon%'   THEN 'tennis'
     WHEN event_slug LIKE 'fifwc%'  THEN 'soccer'
     WHEN event_slug LIKE 'mlb%'    THEN 'mlb'
     WHEN event_slug LIKE 'cs%'     THEN 'cs2'
     ELSE 'other' END
```
Coverage check (K3) in scripts (print % of resolved slugs mapped ≠ 'other'; must be ≥… note:
'other' is a legitimate bucket — K3 binds on NULL/garbage, expect crypto+tennis+soccer+mlb+cs2 to
cover ≳85% and report the actual number). Board: render sport segs in the existing per-row tooltip
(`render_honest`, board.rs:271-321) — string-only change, no new query shape (reuse
`honest_pnl_segments` rows already fetched).
**Source:** direct (additive seg_kind + display; the rethink "gate requirement now" was rejected —
regression risk on rendered verdicts with zero present-day benefit since nothing is GO).

## Item 4 — Flat-shares readout (F6): flat-$-only ledger → both disciplines visible

**Before:** `append_paper_bet` (consensus.rs:717-760) records flat-$ P&L only; REFINED-STRATEGY
rule 3 says flat-$ is the sign-flipping mistake on mixed price bands.
**After:** the board equity panel shows, per strategy, BOTH `flat-$` (existing ledger) and
`flat-shares` equity: `pnl_shares = K × ((outcome_won::int) − entry) − fee_pct × K × entry` with
K = flat_stake shares, computed at QUERY time from the ledger's stored (entry, outcome_won, stake)
— no schema change, no backfill, historic rows untouched.
**Implementation:** extend `ledger_stats` SQL (locate `FROM honest_paper_ledger` aggregation) with
`SUM($K * (outcome_won::int - entry) - $fee * $K * entry) AS total_pnl_shares` (+ per-day curve if
trivial); render one extra muted figure in the equity tooltip/row. Unit math test: one won-at-0.9 +
one lost-at-0.1 row ⇒ flat-$ favors the longshot, flat-shares doesn't (sign demonstration).
**Source:** rethink (derivable-at-query beats schema/mode changes; zero migration).

## Item 5 — Docs & report (Phase 3 vehicle)

DECISIONS.md += D5 (entry_ask ops flag), D6 (at-fire entry is the judged statistic — why), D7 (the
combined promotion rule LB∧null∧regimes — why 0.01), D8 (what was deliberately NOT done: no gate-
requirement flip for regimes, no elite_fresh_fav promotion at N=38<50, longshot selection signal
documented-and-parked as cost-dead, market_resid untouched-OFF).
REPORT.md: before/after tables from scoreboard_parity.py + selection_null.py, certified-vs-paper-
vs-refuted board, exact rollback commands. PROGRESS.md: phase log.

---

## Execution order

0. **Item 0** (env flag) — first; accrual starts during the run. Verify entry_ask count grows.
1. **Item 1** (at-fire fix + parity + tests) — the highest-impact honest-measurement fix.
   Verify: parity harness (N unchanged, deltas as predicted), full gate green.
2. **Item 2** (null instrument + calibration + rule docs) — depends on Item 1's at-fire convention.
   Verify: H2 + K2 on live DB.
3. **Item 3** (sport segments + board tooltip) — independent of 2; after 1 for the same convention.
   Verify: segments appear; coverage number printed; gate green.
4. **Item 4** (flat-shares readout) — independent. Verify: unit sign-test + board renders.
5. **Item 5** (docs) — last, with all evidence inline.
Merge: single `--no-ff` merge of `fable/improve-run-20260702` → `main` only after K5; auto-deploy
picks it up; watch one cycle of logs + board.

## Cost summary (currencies that matter here)

| Item | API load | DB load | Bonferroni budget |
|---|---|---|---|
| 0 | +≤40 book calls/cycle (capped, flag) | ~0 | 0 |
| 1 | 0 | same query shape | 0 (same single hypothesis per strategy, better entry) |
| 2 | 0 | one read-only script, ad-hoc | 0 new arms; the RULE only tightens |
| 3 | 0 | +1 seg_kind in an existing GROUP BY | 0 |
| 4 | 0 | +1 aggregate over ledger | 0 |

## Open questions (resolved during implementation)

- Exact `ledger_stats` SQL location/shape → read at Item 4 start; if the curve reuse is non-trivial,
  ship totals-only (still satisfies F6's "visible discipline").
- Whether `%wimbledon%` matches any live slugs (tennis futures) → check with one SQL count; drop the
  clause if dead.
- `scoreboard_parity.py`: embed both SQL texts verbatim (drifted from git history ae0db80, at-fire
  from the new code) — keep them literal so the parity claim is auditable.

## Rejected approaches

- **Parallel at-fire scoreboard behind a flag** (keep drifted as primary): rejected — the drifted
  statistic is a measurement BUG against the documented at-fire spec (REFINED-STRATEGY rule 4;
  set-once initial_* columns exist precisely for this); keeping it primary preserves a false
  negative that hides a promotable edge. The parity harness + regression test provide the safe-swap
  proof instead.
- **Rust-port of the selection null inside promotion.rs**: rejected this run — new dep/complexity,
  duplicates a statistic that must mirror SQL exactly; Python-instrument-first is the house pattern
  (asof_preflight.py precedent). Revisit only if the null becomes a per-render gate input.
- **Making ≥2-sport-regimes a hard pilot_verdict condition now**: rejected — changes rendered
  verdicts for zero present benefit (nothing is GO); instrument-first, flip later pre-registered.
- **Schema/mode change for flat-shares ledger**: rejected — derivable at query time; never rewrite
  a durable forward ledger.
- **Promoting elite_fresh_fav now** (LB +4.8% at N=38): rejected — below the 50-event pilot floor
  and the N=38 regime table is thin (tennis N=17); the run's job is honest instruments, not eager
  promotion. Re-read after Wimbledon completes.
