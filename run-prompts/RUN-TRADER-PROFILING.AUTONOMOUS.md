# Long Autonomous Run — Per-Trader Strength-Profiling & Slice-Aware Tailing

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace; deploy branch = `main`, auto-deploys ~5 min after
merge). The IMPLEMENTATION DETAIL for every item — actual type defs, SQL fragments, integration
file:lines — lives in the two companion docs; read them first and treat them as the spec:
- `run-prompts/RUN-TRADER-PROFILING.FORGE_PLAN.md` — the 5-item blueprint (the spec you build).
- `run-prompts/RUN-TRADER-PROFILING.FORGE_DEBATES.md` — why each item won, what was rejected.
Companion ground truth (house style + the reality you must not relitigate): `DECISIONS.md`
(esp. **D1–D4** = the DEAD-premise finding), `REFINED-STRATEGY.md`, `run-prompts/README.md`,
`scripts/asof_preflight.py`, `scripts/selection_null.py`, `scripts/slice_study.py`,
`copy-trading-bot/src/scanner/trader_trust.rs`, `.../promotion.rs`, `.../consensus.rs`,
`copy-trading-bot/src/cycles/consensus_cycle.rs`, `common/src/storage/consensus.rs`.

---

## 0. The one-sentence mission

Build the **per-trader strength-profiling instrument** (glance any tracked wallet and see, per
market/bet-type cell, its N, event-days, corrected surplus bound, and a strong/promising/thin/avoid
verdict — "understand them better than they understand themselves") AND wire the **slice-aware
tailing mechanism inert and ready-to-flip** (only tail a trader on the cells they demonstrably excel
at), plus the **automated forward trigger** that fires the day real specialists finally emerge —
shipping measurement now and promoting **nothing**.

The motto: **profile freely, judge only at the belief-blind gate; a slice is a hypothesis, the
family is corrected; measurement promotes nothing and selection stays silent until forward data +
Tue say go.**

---

## Ground truth you must NOT relitigate (established — evidence in DECISIONS.md D1–D4)

- **The naive version of this is DEAD on current data (D2, binding, charter §0.5).** A live
  per-slice "specialist" book that overrides the overall trust gate was tested: **0** capturable
  persistent specialists at every cut — killed by (1) sample floor (edge-showing cells sit below
  the 30-event floor), (2) thin capture margin + variance (cells clearing N≥30 don't clear `lo>3%`),
  (3) slate collapse (the archive is ~one World-Cup weekend + tennis bursts → effective independent-N
  ≪ 30, co-active "specialists"). **This run does NOT flip any specialist arm live.** It builds the
  instrument + the wired-but-inert mechanism + the trigger. A dead premise correctly kept dead is a
  successful run.
- **The gate is reused VERBATIM; add ZERO new statistics.** `surplus_bounds` / `promotion_verdict`
  (promotion.rs) are the only judges. The per-cell verdict (Item 1) calls `surplus_bounds` with the
  SAME per-wallet `n_comparisons` and the SAME `eff_n = n_days.clamp(1, n_events)` event-day
  deflation the overall verdict already uses. No new estimator enters the gate. (Hierarchical/EB
  shrinkage was considered and REJECTED for the gate — see Rejected approaches.)
- **The selection gap is real and located.** `earned_quality` (consensus_cycle.rs:69) branches on
  the wallet's **OVERALL** `TrustVerdict` only — so a whale Trusted overall counts as trusted even on
  markets it loses money on, and a wallet whose only edge is NBA gets zero NBA credit because its
  overall is Indeterminate. Item 4 fixes this per-vote, silently.
- **The slice SQL is already the right shape.** `trader_slice_scores` / `_asof`
  (common/src/storage/consensus.rs:1459 / :1526) emit per-`(wallet × slice_kind × slice_key)` rows
  (slices today: overall / sport / band b1..b5 / recency7d / recency30d) with event-clustered
  `n_events`, `n_days`, `surplus`, `surplus_sd`. New axes are new `slice_kind` VALUES — never a
  `TraderSliceStat` field reorder (sqlx `FromRow`).
- **Event-cluster by `COALESCE(event_slug, condition_id)` ALWAYS** (the within-match leak);
  event-day deflation is mandatory per slice.
- **D1 time-axis trap:** on the backfilled archive `resolved_at` is a bulk-ingest stamp — retrospective
  cuts MUST use the slug-parsed event date (`scripts/asof_slice_scores.sql`). `trader_slice_scores_asof`'s
  `resolved_at < cut` is correct ONLY on forward data. Item 5's trigger is forward-only by construction.
- **Non-regression is load-bearing:** `strict` + `default_portfolio` must be byte-identical with the
  trust map empty / `SLICE_TRUST` off / the new `*_only` flags false. Tests
  `default_strict_is_non_regressive` (consensus.rs:1172) and `trust_arms_registered_separately_and_silent`
  (:1199) are the pattern to extend, not break.

## Non-negotiable guardrails

1. **Reversibility.** Isolated git worktree off `main`, fresh branch, tag the pre-run state. Never
   work in the shared checkout; other Claude sessions run in parallel — check `git worktree list`,
   keep your file slice non-overlapping, smallest-possible additive changes to shared files.
2. **Gate every commit** (the CI gate, verbatim):
   `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace
   --all-targets && cargo test --workspace`. Python deliverables: `python3 -m py_compile` + the
   script's own self-test. **Re-run the FULL gate on `main` AFTER your merge lands** — main moves and
   the auto-deployer ships whatever is there (cross-merge breaks were caught exactly this way).
3. **Applied migrations are IMMUTABLE** (even a comment edit ⇒ sqlx checksum crash-loop in prod).
   Item 2 needs exactly ONE new migration (`ADD COLUMN IF NOT EXISTS bet_type TEXT`): next free number
   only, append-only, no backfill.
4. **Paper-only, additive-and-OFF, belief-blind.** No real money, no order placement, no alerting
   changes, no auto-promotion. Every new strategy variant is SILENT (`alerting: false`), registered in
   the **EXPERIMENTAL** family (`enrich::family`) so it can never tighten `strict`'s Bonferroni, and
   env-gated (`SLICE_TRUST`, default OFF). Budget = ONLY the arms named in the plan (`slice_sport_tail`);
   do not invent extra variants.
5. **Deploys only via `scripts/consensus-autoupdate.sh`** (never manual `docker compose up`), and any
   env/behavior flip on the live bot (turning `SLICE_TRUST` on, wiring the accrual cron) requires Tue's
   explicit go — **propose, don't apply.**
6. **Cost-zero** (Max only, no `ANTHROPIC_API_KEY`, no child `claude` spawns).
7. **Resumability.** Commit after every phase (gate-green). Background long-runs can be reaped; the
   worktree is the durable salvage point — a resumed session picks up from the last gate-green commit.

---

## Phases (each ends gate-green + committed; dependency-ordered exactly as FORGE_PLAN)

### Phase 0 — Setup & honesty check (~30 min)
Worktree + branch (`feat/trader-slice-profiling`) + tag the pre-run state. Read both companion Forge
docs + DECISIONS D1–D4. Confirm the baseline gate is green BEFORE touching anything. Reproduce the D2
null so you build on the real ground truth, not a hope: run `scripts/asof_preflight.py` (slug-date
axis, D1) and confirm it still reports **~0 capturable per-sport specialists** — if it does not,
STOP and reconcile with DECISIONS before proceeding (the whole "wired-but-inert" posture depends on
this being true). Print the resolved-fill record shape (events/day by sport) — the denominator of
every accrual claim.

### Phase 1 — Item 1: per-cell profiling display (SHIP FIRST — measurement, ZERO stat cost)
Build `SliceVerdict` + `TraderTrust.slice_verdicts` and surface it in `/profile`
(commands.rs) + the board (board.rs), exactly per FORGE_PLAN Item 1. Reuse `surplus_bounds` verbatim
with the wallet's existing `n_comparisons` and `eff_n = n_days.clamp(1, n_events)`. Keep
`best_slices`/`worst_slices` intact (safe-swap; existing test stays green). Footer copy MUST state the
verdict is wallet-local (per-wallet Bonferroni), NOT a fleet-certified bankable specialist.
**Tests:** a per-cell bound equals the overall-machinery bound for the same inputs; a thin cell
(`n_events < 30`) renders `[—]` + `thin`; `strict` scoring is untouched (extend the non-regression test).
This promotes nothing and is the immediate user-visible win.

### Phase 2 — Item 2 (bet-TYPE axis) + Item 3 (behavioral-ARCHETYPE axis)
- **Item 2 (the axis the user named):** new migration `0NN_trader_fills_bettype.sql`
  (`ADD COLUMN IF NOT EXISTS bet_type TEXT`, no backfill); `bet_type_bucket(title,slug)` sibling to
  `sport_bucket` (consensus_cycle.rs:133); freeze it in `trade_to_fill` + `NewTraderFill`; add the
  `bettype` UNION branch to BOTH `trader_slice_scores` and `_asof` (+ `COALESCE(bet_type,'other')` in
  both `adv` CTEs). Include `bettype` in the per-wallet `n_comparisons` (the documented conservative
  tightening). **Kill K1:** if the classifier confidently maps <80% of resolved favorite-band titles,
  report coverage and keep `bettype` **display-only** (do NOT wire it into any live selection axis) —
  never guess a market type.
- **Item 3 (the slate-collapse-beating axis):** SQL-only `archetype` slice_kind = entry-timing ×
  conviction (`percent_rank() OVER (PARTITION BY ev ORDER BY ts)` for fleet-relative earliness;
  `percentile_cont(0.5)` per-wallet stake median), added to `trader_slice_scores` and `_asof`. Verify
  it is leak-free in the `_asof` clone (ranks/medians computed only over fills inside the cut). No
  migration, no capture change. Display/accrual only (the live per-vote path can't see event-wide fill
  context — do NOT wire archetype into Item 4's per-vote selection).
**Tests:** classifier unit tests (moneyline/spread/totals/prop mappings + coverage); new slices appear
in `slice_verdicts` with correct N; `_asof` archetype leak-free (a fill after the cut can't move a
pre-cut rank).

### Phase 3 — Item 4: slice-aware selection wiring (SILENT, env-gated, INERT — promotes nothing)
Per FORGE_PLAN Item 4: `SliceCtx` (derived at the `books_from_window_votes` call site from
`v.title/v.slug/v.price` — WindowVote carries these, NOT `sport`/`bet_type`); extend `earned_quality`
with a `slice_ctx` param + `slice_earned_quality()` on the **pre-registered single axis = sport**
(one cell per vote = one hypothesis); add fail-closed `TraderVote.slice_certified` / `slice_earned`;
add `ConsensusParams.slice_certified_only` + the one `score_market` filter conjunct; register the
SILENT `slice_sport_tail` arm in `slice_arms()`, put its name in the **EXPERIMENTAL** const in
`family()`, and gate the whole thing behind `SLICE_TRUST` (default OFF) in `active_portfolio`.
**Non-regression proof (mandatory test):** with `SLICE_TRUST` off / empty map, `earned_quality`
returns `(qw, true, false)` and `strict`'s `net_count`/tier/score/alert are byte-identical; add
`slice_arms_registered_separately_and_silent`. **Kill K2:** if any change moves `strict` on a
representative book, STOP — that's a non-regression breach, not a passing build.

### Phase 4 — Item 5: accrual auto-trigger (forward permutation, D1-immune, family size 1)
Per FORGE_PLAN Item 5: `scripts/accrual_checkpoint.py` (house pattern: stdlib+numpy, seeded, JSON
artifact under `reports/accrual/`, append-only manifest à la `map_checkpoint.py`). It asks ONE forward
question per window — "does the as-of-cut slice-selection procedure predict positive surplus on the
picks it makes in `(C, C+Δ]`?" — via the `selection_null.py` permutation machinery (reuse, don't
reimplement; extract shared helpers if cleaner while keeping `selection_null.py`'s CLI byte-identical).
Forward-only ⇒ immune to the D1 `resolved_at` trap. Fires `ntfy` (the existing channel) ONLY on the
`<2 → ≥2` persistent-specialist transition across ≥2 disjoint windows at `p ≤ 0.01`.
**Self-test (mandatory, like `decay_analysis.py`):** a synthetic fixture with an injected forward edge
must trip the trigger; a pure-noise fixture must NOT. Ships only with self-test PASS. **Kill K3:** if
there isn't enough forward data to run the test yet, that's EXPECTED — ship the checkpoint wired +
document the accrual trigger; do NOT lower `p`/`lo`/floors to manufacture a specialist. Wiring it into
cron/housekeeping is a PROPOSAL for Tue, not applied here.

### Phase 5 — Ship & verify
`DECISIONS.md` += a new D-entry (what shipped: the instrument + the two axes + the inert selection arm
+ the forward trigger; why the multiplicity control is trustworthy; what stays OFF and why). Update
`REFINED-STRATEGY.md` only where this run's evidence sharpens a rule (cite the change). Merge `--no-ff`
to `main`; **re-run the full gate on post-merge main**; confirm the auto-deployer stays healthy
(doc/silent-arm/script changes should NOT rebuild live behavior — verify the updater log says so).
Final report to Tue: what's live (measurement only), what's wired-but-OFF, the exact flip-live
sequence (turn `SLICE_TRUST` on → wire the accrual cron → wait for the trigger → then and only then
discuss promotion), what was deliberately NOT done, and the exact rollback.

---

## Kill criteria (binding)
- **K1** — bet_type classifier <80% confident coverage ⇒ `bettype` stays display-only; never guess a type.
- **K2** — any change that moves `strict`'s net_count/tier/score/alert ⇒ STOP (non-regression breach).
- **K3** — insufficient forward data for the accrual test ⇒ ship the wired trigger + document it; never
  lower the bar to manufacture a "specialist." Correctly-established "not yet" IS the finding.
- **K4** — nothing in this run flips live behavior. Output = instrument + silent inert arm + forward
  trigger + DECISIONS entry. `SLICE_TRUST` and the cron stay OFF pending Tue.

## Rejected approaches (do not build)
- **A live per-slice specialist book that overrides the overall gate.** D2 forbids it (0 certified,
  slate collapse). The mechanism ships SILENT + forward-judged; it does not alert or promote.
- **Hierarchical / empirical-Bayes shrinkage in the GATE** (DerSimonian–Laird τ² etc.). It adds a new
  estimator to the judge; the charter says reuse `surplus_bounds` and add zero statistics. The one
  genuinely superior half of that design — the **forward permutation trigger** — IS adopted (Item 5).
  Shrinkage stays out of the gate; if ever wanted it's a generator-side display experiment, not a judge.
- **A composite "best cell across all axes" selector.** That is the multiple-comparisons inflation the
  DEAD premise is made of. One pre-registered axis (sport) per silent arm = one hypothesis per vote.
- **Certifying anything from this run's own data.** Exploration nominates; the forward permutation test
  confirms; only then (with Tue) does promotion get discussed. Different datasets by construction.
- **Tuning thresholds/keywords to make cells light up.** The classifier and the bars are frozen;
  "adaptive = re-reading, not re-tuning."

## Acceptance
Gate-green commits throughout. **Item 1** per-cell profiling live in `/profile` + board (measurement,
promotes nothing, footer states wallet-local). **Item 2** `bet_type` axis populated forward (or
display-only if K1) via one append-only migration + frozen bucket. **Item 3** `archetype` axis present
in both slice queries, leak-free in `_asof`. **Item 4** `slice_sport_tail` SILENT, EXPERIMENTAL,
`SLICE_TRUST`-gated OFF, with a PASSING non-regression test proving `strict` byte-identical. **Item 5**
`accrual_checkpoint.py` with PASSING self-test + append-only artifact + ntfy-on-transition, wired but
OFF. `DECISIONS.md` entry written; merged `--no-ff`; post-merge main re-gated; auto-deploy healthy;
live behavior unchanged; paper-only; **nothing promoted.** The output is a working instrument + a
mechanism that is ready to flip the instant the forward data earns it — not a live specialist book.
