# Long Autonomous Run — Paired-cohort realized-vs-modeled ROI (make the haircut comparison honest)

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace + Python), in a dedicated git worktree off
**`main`** (the deploy branch the launchd autoupdater builds). Gate-green + commit after
EVERY phase; at the end `merge --no-ff` into `main` via the sanctioned path so the
autoupdater redeploys.
Companion reading (same house style, READ FIRST): `run-prompts/RUN-ENTRY-ASK-CAPTURE.md`
(the run this builds on), `DATA-MODEL.md` (the "Executable entry price" section),
`migrations/032_entry_ask_decision_time.sql`, `common/src/storage/consensus.rs`
(`honest_pnl_by_strategy`), `copy-trading-bot/src/board.rs` (`render_honest`),
`copy-trading-bot/src/scanner/{honest,promotion}.rs`.

---

## Philosophy — read first, it overrides everything
- **The one comparison that would justify real money is "did the real ask cost more/less
  than the assumed haircut," and today that comparison is CONFOUNDED.** The board puts
  "honest ROI (blended)" (over the FULL resolved population) next to "realized ROI (real
  ask)" (over only the decision-time-ask SUBSET). Their difference is dominated by *which
  events are in each set and how many*, NOT by the haircut. The feature's own test shows
  realized > modeled purely because a lagged bad ask sits in one set and not the other — a
  cohort artifact, the exact opposite of a haircut signal. This run replaces the confounded
  side-by-side with a **paired, same-cohort, event-for-event** comparison so the only thing
  that varies is the entry price.
- **Paired or it doesn't count.** For each signal that has a real decision-time ask, compute
  BOTH entries over the SAME event: `entry_modeled = entry_ask_mid + haircut` and
  `entry_real = entry_ask`. Aggregate both over the identical event set, and report the
  **paired gap** `roi_real − roi_modeled` with a paired lower bound. Holding the event set
  fixed, the gap isolates `entry_ask − (entry_ask_mid + haircut)` = exactly "how wrong was
  the haircut assumption," with nothing else moving.
- **One definition of "decision-time," keyed off provenance, not a wall clock.** Today the
  code tags a capture `kind=decision` by `first_price` (it first-set `initial_market_price`
  that pass), but the SQL builds the realized cohort by a wall-clock `lag ≤
  REALIZED_DECISION_LAG_SECS` (900s). These are DIFFERENT populations; the observed lag
  (~856s) sits right at the 900s edge, so scheduling jitter silently flips membership.
  Persist the `first_price` provenance and key the cohort off it, so the metric and the
  board agree on one definition.
- **Conditional, and say so.** The decision-time cohort is **liquidity-selected** (a signal
  only enters it if `/book` had an ask at capture). The paired gap answers "for the signals
  we could capture, was the haircut right," NOT "for all signals." Quantify and SURFACE the
  selection (decision cohort vs full population), never launder it into a general claim.
- **Pure analytics, never the live path.** No change to firing, tiering, scoring, alert text,
  or any strategy's edge. The provenance column is set-once, `resolved=FALSE`-guarded,
  pre-resolution — exactly like `entry_ask`. Leak-free: no outcome term ever enters an entry
  price or the cohort filter.
- **Paper/measurement only. No wallet, no order, NO real money.**
- **Extend, don't rebuild.** `honest_pnl_by_strategy`, `set_entry_ask_decision`,
  `snapshot_consensus_signal` (returns `first_price`), `surplus_bounds`, the board panel, and
  the config knobs ALL exist. Add the provenance column, the paired query, and the paired
  board columns; do not reimplement the capture or the gate machinery.

---

## What already shipped (do NOT redo — this run continues it)
The decision-time `entry_ask` capture (`RUN-ENTRY-ASK-CAPTURE.md`) + a deep-audit follow-up
are already on `main`:
- Capture is leak-free, non-regressive, failure-isolated; `entry_ask` / `entry_ask_at` /
  `entry_ask_mid` (mig 030 + 032) are set once while OPEN, paired with the same-pass mid.
- The audit's **honesty + safety subset** shipped: realized LB is gated at `N ≥ min_events`
  (no false confidence at N=1); `median_haircut` is decision-time-cohort-only; `base_r` is a
  strict subset; the board relabels the column "blended" and its note WARNS the two ROI
  columns are different samples and points to the per-strategy decision-time haircut as the
  valid read.
- **DEFERRED to THIS run (audit #1 + #2):** the two columns are still different cohorts (the
  note warns but the number is still confounded), and "decision-time" still has two
  definitions (metric `first_price` vs SQL wall-clock). This run closes both.

---

## The gaps this run closes (from the deep audit)
1. **Cohort mismatch (#1, HIGH).** `honest_roi` is over the full resolved population (`base`);
   `realized_roi` over the decision-time subset (`base_r`). Shown adjacently, they invite an
   invalid inference. Fix = paired same-cohort modeled-vs-real ROI + gap.
2. **Dual "decision-time" definition (#2, HIGH).** Metric `kind` uses `first_price`; the SQL
   realized cohort uses a wall-clock window. Fix = persist `first_price`, key the cohort off
   it, reconcile the metric.
3. **Selection bias is unquantified.** The decision cohort is liquidity-selected but the board
   never shows how it differs from the full population. Fix = a diagnostic that quantifies it
   and a coverage line the reader can't miss.

---

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a synthetic smoke run.
Live-verify DB-touching changes on a **throwaway Docker Postgres** (own port, e.g. 55434;
apply migrations via the repo's `run_migrations`, exercise the path, inspect rows). Do NOT
touch the live prod stack (`polymarket-bot-postgres-1`, `polymarket-bot-copy-trading-bot-1`)
for verification.
**MIGRATION SAFETY (learned the hard way — non-negotiable):** migrations are IMMUTABLE once
applied. `sqlx::migrate!` checksums every migration file and re-checks it against
`_sqlx_migrations` at boot; **any byte change to an already-applied file (even a COMMENT)
fails with `migration N was previously applied but has been modified` and CRASH-LOOPS the
container.** `cargo test`/clippy do NOT catch this — it is a RUNTIME check against the live
DB. So: (a) NEVER edit a shipped migration; put prose in code/DATA-MODEL, add a NEW numbered
migration for any schema change; (b) before deploying a migration change, verify boot against
a Postgres that ALREADY has the prior migrations applied (dump the prod schema's
`_sqlx_migrations` or re-run your throwaway PG twice), not just a fresh one.

---

## Context (extend, don't rebuild — verified `file:line`; lines DRIFT as other chats commit,
so re-`grep` the symbol names if a line is off)
- `common/src/storage/consensus.rs`:
  - `honest_pnl_by_strategy(exec_haircut, fee_pct, decision_lag_secs)` (~:705) — CTEs
    `base`/`sig`/`evt`/`agg` (modeled, FULL population, entry = `COALESCE(entry_ask,
    initial_market_price + $1)`), `liq` (coverage + `median_haircut`, decision-time-filtered),
    `base_r`/`evt_r`/`agg_r` (~:757, realized, decision-subset, entry = `entry_ask`). **The
    paired query is a sibling of this; reuse its event-clustering idiom verbatim.**
  - `set_entry_ask_decision(signal_id, ask, mid) -> Result<bool>` (~:544) — set-once,
    `resolved=FALSE`, writes `entry_ask`/`entry_ask_at`/`entry_ask_mid`. **Add a `decision:
    bool` param and write the new provenance column in the SAME UPDATE (still set-once).**
  - `snapshot_consensus_signal(...) -> Result<bool>` — returns `first_price` (this pass
    first-set `initial_market_price`). Housekeeping already has this bool.
  - `pub struct HonestPnl` (~:1613) with `realized_roi`/`realized_roi_sd`/`realized_events`
    (~:1657), `median_haircut` (~:1651), `decision_coverage` (~:1645). **Add a sibling struct
    `PairedCohortPnl` rather than overloading this one.**
- `copy-trading-bot/src/cycles/housekeeping.rs` — the capture block: `first_price` from
  snapshot, decision/lagged budgets, `set_entry_ask_decision(sig.id, ask, mid)`. **Pass
  `first_price` into the setter as the new `decision` arg.**
- `copy-trading-bot/src/scanner/promotion.rs` — `surplus_bounds(distinct_events, surplus, sd,
  n_comparisons, params)` (~:? — `grep`); NB it has **no** `min_events` floor (that lives in
  `pilot_verdict`/`promotion_verdict`), so the caller MUST gate `N ≥ min_events` (the audit-#4
  fix already does this for the realized LB — mirror it for the paired LB).
- `copy-trading-bot/src/scanner/honest.rs` — `PilotThresholds` (`min_events` default 50),
  `verdicts_by_strategy`, `pilot_verdict`; the modeled GO marker keys off `honest_roi` (do NOT
  change what the GO uses — the paired numbers are a measurement column, not a new gate).
- `copy-trading-bot/src/board.rs` — `render_honest` (~:485+): the `realized_lb` closure
  (~:526, already N-floored), the table header (~:574), the row cells, the `<p class=note>`,
  and `HonestBoardParams.realized_decision_lag_secs` (~:35). **Add the paired "haircut impact"
  columns here.**
- `copy-trading-bot/src/config.rs` — `CAPTURE_ENTRY_ASK` (:352), `ENTRY_ASK_DECISION_MAX_PER_CYCLE`
  (:366), `REALIZED_DECISION_LAG_SECS` (:377). **Keep the wall-clock knob as a SECONDARY
  recency sanity guard; the PRIMARY cohort key becomes the provenance column.**
- `common/src/metrics.rs` — `record_entry_ask_capture(decision, spread, lag_secs)`; the
  `kind=decision|lagged` label already uses `first_price`. Reconcile the doc so `kind` and the
  board cohort now share ONE definition.
- Migrations dir: highest is `034`. **Next free is `035`.** Additive, nullable, `IF NOT EXISTS`.

---

## Rejected approaches (do not do)
- **Editing migration 032 (or any applied migration) to add a flag.** IMMUTABLE — crash-loops
  prod. Add `035` for the provenance column.
- **Deriving the cohort from `entry_ask_mid == initial_market_price` alone.** A lagged capture
  on a market whose price never moved would falsely qualify; a first-price capture with any
  rounding would falsely disqualify. Use an explicit persisted `first_price` boolean.
- **Comparing realized-subset ROI to full-population ROI.** That IS the confound this run
  removes. The comparison must be paired within ONE event set.
- **Claiming the paired gap generalizes to all signals.** It is conditional on the
  liquidity-selected decision cohort. Report coverage + the cohort-vs-population diagnostic;
  never drop the conditional.
- **Letting any of this gate/alter firing, tiering, scoring, the GO marker, or alert text.**
  Measurement only. GO stays on the existing modeled + `min_events` path.
- **Backfilling the provenance column with a guess on old rows.** Leave pre-035 rows NULL
  (unknown); the paired cohort accrues forward. Document the ramp.
- **Placing real orders / any wallet or signing path.** Never.

---

## Phase 0 — Honest diagnostic + design doc (no behavior change)
Quantify the confound on LIVE data before building, so the design is evidence-led.
- Add a **read-only** diagnostic (a `scripts/paired_cohort_diag.py` or an `#[ignore]` query
  test) that, against the prod DB, reports per strategy: full-population blended ROI + N vs
  the decision-cohort's own blended ROI + N + price-band mix + hit-rate — i.e. HOW different
  the decision cohort is from the population (the selection-bias magnitude). Also report the
  current disagreement between the `first_price`-metric cohort and the wall-clock-≤900s
  cohort (how many captures each includes but the other doesn't).
- Document in `DATA-MODEL.md` (Executable-entry section) and a short design note: the cohort
  mismatch (#1), the dual definition (#2), and the plan (paired same-cohort comparison keyed
  off persisted `first_price`). No logic change. Gate, commit.

## Phase 1 — Persist `first_price` provenance (additive, leak-free)
**Goal:** one authoritative, leak-free record of which captures were first-price.
- Migration `035_*.sql` (append-only, additive, nullable): add `entry_ask_first_price BOOLEAN`
  to `consensus_signals` — `TRUE` = captured on the first-price pass (`entry_ask_mid ==
  initial_market_price` by construction), `FALSE` = lagged fallback, `NULL` = pre-035 /
  uncaptured. No backfill.
- Extend `set_entry_ask_decision(signal_id, ask, mid, decision: bool)` to write
  `entry_ask_first_price = $decision` in the SAME set-once, `resolved=FALSE` UPDATE (never
  overwritten, never post-resolution — same guard as `entry_ask`).
- In `housekeeping.rs`, pass the `first_price` bool the capture block already computes into the
  setter. No other call sites change behavior.
**Verify (throwaway PG, exercised TWICE to prove the migration is re-applicable):** a
first-price capture writes `TRUE`; a lagged capture writes `FALSE`; second capture is a no-op;
post-resolution refused; the value is set in the same row/instant as `entry_ask`. Gate, commit.

## Phase 2 — Paired-cohort query (the core), min-events-floored + paired LB
**Goal:** modeled vs real ROI over the IDENTICAL decision cohort, plus the paired gap + LB.
- Add `honest_pnl_paired_cohort(exec_haircut, fee_pct) -> Vec<PairedCohortPnl>` in `common`
  (sibling of `honest_pnl_by_strategy`). Cohort = `resolved AND strategy<>'_blind' AND
  entry_ask IS NOT NULL AND entry_ask_mid IS NOT NULL AND initial_market_price IS NOT NULL AND
  entry_ask_first_price = TRUE` (optionally AND within `REALIZED_DECISION_LAG_SECS` as a
  secondary recency guard). Per row, per event (`COALESCE(event_slug, condition_id)`):
  - `roi_modeled = (w − (entry_ask_mid + $1)) / (entry_ask_mid + $1) − $2`
  - `roi_real    = (w − entry_ask) / entry_ask − $2`
  - `d = roi_real − roi_modeled` (the PAIRED per-event difference)
  Event-cluster (AVG within event, then across events), returning per strategy: `n_events`,
  `roi_modeled` + `roi_modeled_sd`, `roi_real` + `roi_real_sd`, and `gap` + `gap_sd` (the
  paired difference — its SD is the WITHIN-event-pair variability, tighter and correct for the
  paired design; this is the number that says "real ≠ assumed").
- Corrected LBs via `surplus_bounds`, **gated `N ≥ min_events`** (mirror the audit-#4 realized
  guard); the gap's LB uses `gap_sd`. Same Bonferroni family logic as the modeled verdict.
- Re-key the EXISTING realized cohort (`base_r` in `honest_pnl_by_strategy` + the board's
  `realized_lb`) off `entry_ask_first_price = TRUE` (provenance), keeping the wall-clock as a
  secondary guard — so #2 is closed everywhere.
**Verify (synthetic rows, throwaway PG):** rows with known `entry_ask`, `entry_ask_mid`, and
`first_price` produce `roi_modeled` and `roi_real` over the SAME N, and `gap` = exactly the
haircut effect (e.g. real ask 2¢ above mid+1¢ ⇒ a known negative gap); a lagged row
(`first_price=FALSE`) is EXCLUDED from all three. Gate, commit.

## Phase 3 — Board: the "haircut impact" comparison (replaces the confounded side-by-side)
**Goal:** show modeled-vs-real on ONE cohort + the gap, and stop inviting the population-vs-
subset misread.
- In `render_honest`, add a paired block/columns per strategy: `modeled ROI` and `real ROI`
  over the SAME `n_events` (shown once), and the **paired gap ± corrected LB** (the headline:
  "real execution costs X more/less than assumed, LB Y"). Keep the full-population blended
  `honest_roi` as a clearly SEPARATE portfolio figure (it is not the comparison).
- Rewrite the note: the haircut question is answered by the paired gap on ONE cohort; the
  blended column is the whole-population figure and is NOT to be differenced against realized.
  Surface `decision_coverage` + the Phase-0 selection-bias line (decision cohort vs population)
  prominently so the conditional is unmissable. Show "N<floor" (not "—") when the cohort is
  too small for a gap LB.
- Reconcile the metric doc so `kind=decision` == the board's provenance cohort.
**Verify:** board renders the paired columns + gap; synthetic cohort shows the expected
gap/LB; the note no longer implies a population-vs-subset comparison. Gate, commit.

## Phase 4 — Adversarial validation + honest surfacing
**Goal:** make the gap trustworthy and its limits explicit.
- Bootstrap the paired gap's CI (resample events with replacement; a `scripts/*.py` or a
  Rust test) and confirm it agrees with the analytic `surplus_bounds` LB — the gap LB is
  honest, not a normal-approx artifact. The null is `gap = 0` (real == assumed haircut); a gap
  whose LB doesn't clear 0 is "haircut assumption not refuted," and that's a fine, honest
  result to report.
- Quantify + surface selection bias: report the decision cohort's blended ROI vs the full
  population's, and its price-band/liquidity skew, so a reader sees the paired gap is
  conditional. A completeness-critic pass: what's unmeasured (illiquid/empty-book signals
  excluded; forward-only ramp; small N)? Log/surface it; do not represent partial coverage as
  complete. Gate, commit.

## Phase 5 — Merge, deploy, verify (with the migration-safety check)
- `merge --no-ff` into `main` (rebase onto the FRESH tip first — this repo is shared, other
  chats advance it; re-run the gate after rebase). Do NOT `docker compose up -d` by hand — let
  `scripts/consensus-autoupdate.sh` rebuild + redeploy on the HEAD advance.
- **BEFORE relying on the deploy, prove migration 035 applies WITHOUT crash on an
  already-migrated DB** (throwaway PG loaded with the current prod schema / migrations 021-034,
  then boot): confirm no `migration ... has been modified` and `035` applies cleanly. This is
  the exact failure that crash-looped prod last time — do not skip it.
- Post-deploy VERIFY (report numbers): 035 applied, 0 restarts, no checksum error in logs;
  `entry_ask_first_price` populating (TRUE on fresh first-price captures, FALSE on lagged);
  the paired gap + LB rendering for `elite_fresh_fav` / `favorite` as their decision cohort
  accrues; the board note reflects the paired design. Arm/scoring/GO paths unchanged.

---

## Acceptance
Every phase gate-green + commit; final `merge --no-ff` deployed via the autoupdater.
Deliverables: a persisted `first_price` provenance column (mig 035, additive, set-once,
leak-free) that makes the decision cohort provenance-keyed and reconciles the metric with the
board; a `honest_pnl_paired_cohort` computing modeled-vs-real ROI over ONE event set + the
paired gap with a min-events-floored corrected LB; a board "haircut impact" comparison that
replaces the confounded population-vs-subset side-by-side and surfaces the selection-bias
conditional; a bootstrap validation of the gap LB. The full-population blended ROI stays as a
separate portfolio figure; the GO marker is unchanged. Live firing/tiering/scoring byte-
identical when no ask is captured. Paper/measurement only, no wallet, NO real money.

## Standing disciplines
Analytics only, never the live path; paired same-cohort (never population-vs-subset); one
definition of decision-time keyed off persisted `first_price` provenance; leak-free (pre-
resolution, set-once, `resolved=FALSE`, no outcome term in any entry/cohort filter); realized
+ gap LBs gated `N ≥ min_events`; report the selection-bias conditional honestly (a
haircut-not-refuted gap is a valid result, not a failure); **migrations are IMMUTABLE once
applied — NEVER edit a shipped migration (comments included; sqlx checksum crash-loops prod;
runtime-only so tests miss it); add the next number (035) and verify boot against an already-
migrated DB**; every new tunable in the compose `environment:` allowlist and verified in the
container; SQL/pool in `common`, cycle wiring in the binary; commit per phase; `merge --no-ff`
→ main → autoupdater; NO real money.
