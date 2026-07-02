# Long Autonomous Run — The Archive Flywheel: replay-search + findings registry + standing accrual refresh

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace + Python), in a dedicated git worktree off `main`.
Gate-green + commit after EVERY phase; at the end `merge --no-ff` into `main` (the branch the
launchd auto-updater deploys). Companion reading (REQUIRED — this run *inherits* their doctrine,
it does not duplicate them): `run-prompts/RUN-STRATEGY-SEARCH-BACKTEST.md` (the anti-overfit
search discipline — every deflator there applies here verbatim), `REPORT-DEEP-EDGE.md` (the
current frontier + honest state), `run-prompts/RUN-DEEP-DATA-EDGE.AUTONOMOUS.md` (house style +
the earned-eligibility machinery this builds on), `scripts/asof_slice_scores.sql` +
`scripts/asof_preflight.py` (the leak-free as-of pattern and its time-axis hazard),
`DATA-MODEL.md`, `DECISIONS.md` (D1 time-axis, D6 at-fire entry, D7 promotion rules).

---

## 0. The one-sentence mission
Build the **archive flywheel**: an as-of **replay engine** over the full 400k-resolved-fill
archive that evaluates strategy candidates at ~10× the event-N of any forward record, a
**corrected search** over a pre-registered candidate grid whose survivors auto-register into
pre-allocated **forward-confirmation arm slots**, a single **findings registry** where every
hypothesis/verdict this system has ever produced lives with its current N/bound/status, and a
**standing refresh** that re-scores everything against each new snapshot — so every additional
day of accrual (and we only get more from here) automatically sharpens every open question
without anyone re-deriving anything.

The motto: **replay is the generator's microscope, never the certifier. Every config tried
counts against us. Event-DAYS are the power currency and they accrue at +1/day — the flywheel's
job is to be ready the moment power arrives. The forward gate — belief-blind, event-clustered,
day-deflated, selection-null-checked — is the only promoter. Findings compound in ONE registry
or they don't compound at all. An honest NULL is a real result. NO real money.**

---

## Philosophy — read first, it overrides everything
- **Why this run exists (Tue's directive):** the certified winners sit at N=38–92 *forward*
  events while the archive holds **2,625 distinct resolved events / 403,742 resolved BUY fills
  across 341 wallets**. That asymmetry is structural: strategies are judged only on forward
  emissions, so every new idea starts its clock at zero. Replay closes the asymmetry for the
  *evaluation* step: an idea can be scored over the whole archive in minutes. What replay can
  NEVER close is the calendar: the gate's SE deflates N to distinct event-days, and the live
  era holds only **~14 of them** (+1/day). So replay's honest job is (a) kill bad ideas cheaply,
  (b) rank survivors with pre-registered, deflated effect sizes, (c) queue them for forward
  confirmation — and the flywheel's job is to re-run all of it automatically as days accrue.
- **Inherit the anti-overfit doctrine wholesale** (`RUN-STRATEGY-SEARCH-BACKTEST.md`): a
  bounded, PRE-REGISTERED grid (mining inflates the correction); Bonferroni over the FULL
  search size; a **shuffled-outcome ghost floor** (re-run the entire search on permuted
  outcomes — the best ghost is the noise the search manufactures by construction; a real
  candidate must beat its own ghost); selection-matched nulls for compositional effects. The
  likely honest output of the first sweep is "the top candidates are mostly noise; here are
  the 2–5 that survive deflation, queued forward." That is success, not failure.
- **Two time axes, one hazard (D1 — do not rediscover this the hard way):** on the BACKFILLED
  portion of the archive, `ts` and `resolved_at` are crawl/bulk timestamps and are UNUSABLE
  for as-of cuts or freshness gates; the slug-parsed **event date** is the only axis of
  record there (see `asof_slice_scores.sql` — 365k of 404k fills carry one). In the LIVE era
  (incremental capture, `ts ≳ 2026-06-20`) `ts` is genuine intraday capture time, so full-
  fidelity replay (freshness/recency gates, fill ordering) is valid **only there** (2,353
  events / 14 event-days and growing). Every replay result must be tagged with which axis and
  era produced it; freshness-gated variants restricted to the live era, freshness-free
  variants may use the event-date axis across the whole archive.
- **Rank history does not exist** — `followed_traders.rank` is current-only; `trader_fills`
  carries no rank. Two honest paths, use both where they apply: (1) `consensus_signals.
  observed_votes` stores the RAW vote atoms per emitted signal (the no-backtest superpower) —
  exact replay including ranks for anything the engine already emitted (this is the parity
  path); (2) for the broad archive replay, rank-dependent gates use CURRENT rank as an
  explicit, documented approximation — and any candidate whose edge *depends* on the rank
  approximation is flagged and cannot survive to a forward slot on replay evidence alone.
- **Findings must compound.** Today's verdicts are scattered across a dozen REPORT-*.md files
  and memory entries. The registry (Phase 1) becomes the single canonical surface: every
  hypothesis with its pre-registration, definition, status, latest numbers, and what unblocks
  it. Every future run appends to it; the refresh re-scores it. No more N=38 sitting unexamined
  because nobody re-ran a script.
- **Scalability is a design input, not a hope:** the archive grows ~70k fills/week at depth
  200 and more if depth widens to 500 later — the replay SQL must stay index-backed, the
  refresh must stay O(new data), the sweep bounded by config, and the forward slots must
  absorb new survivors WITHOUT code changes (pre-allocated, env-parameterized).
- **Non-regression is sacred.** `strict` alerting, the voter set, and every live-emitted
  signal stay byte-for-byte. Everything ships silent + flag-gated, defaults = today.
- **Cost-zero, paper-only, Max-subscription only. NO real money, ever.**

---

## The data we have (verified 2026-07-02 04:00 snapshot — Phase 0 re-measures)
- **Archive:** 561,907 fills · 403,742 resolved BUY · 341 wallets · 2,625 distinct resolved
  events · 4,225 markets. Event-date axis: 365k dated fills, 70 distinct event-days total.
- **Live era (ts ≥ ~2026-06-20, genuine intraday ts):** 2,353 events over **14 event-days**
  (~170 events/day of breadth vs strict's ~15/day forward emission — the 10× evaluation lever).
- **Per-sport event budgets:** crypto 1,259 ev (no slug dates — ts-day clustering, live era
  only) · other 618 · soccer 249/36d · tennis 233/14d · mlb 137/19d · cs2 53/19d.
- **Forward records to reproduce for parity:** `favorite` (LB +3.3%, N=92), `elite_fresh_fav`
  (LB +4.8%, N=38) and the rest of the scoreboard, all judged at at-fire entry (D6).
- **Deep-edge state:** 0/13 gate-ready deep traders certified; Tier-B thesis +15.8pp at
  p=0.29 (power-pending); tail/cross-cohort/retuned arms accruing silently since 2026-07-02.

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a smoke run on a tiny synthetic fixture.
**All snapshot analysis on a THROWAWAY restore of the daily backup — NEVER the prod container**
(prod psql access is not available to the run; the backup restore pattern is proven):
`docker run -d --name pg-flywheel -e POSTGRES_DB=polymarket -e POSTGRES_USER=bot -e POSTGRES_PASSWORD=bot -p 55497:5432 postgres:17-alpine`
`gunzip -c ~/polymarket-bot/backups/consensus-<latest>.sql.gz | docker exec -i pg-flywheel psql -U bot -d polymarket -q`
Live-verify Rust DB tests on a separate migrated throwaway (port 55496), `-- --ignored`.

### Deploy + coordination gotchas (heed them)
Autoupdater deploys **local `main`** on HEAD advance; `merge --no-ff`; never merge by hand
elsewhere. Multiple chats work this repo — re-check the next free **migration number** right
before adding one (036 was free at authoring time), and **never edit an applied migration**.
Container env vars go in BOTH `.env.consensus` AND the compose `environment:` block. `wt/` is
in `.dockerignore` — keep it there. Docs-only commits skip the rebuild (the autoupdater greps
changed paths) — use that for registry/report updates.

---

## Context (extend, don't rebuild — grep to pin exact lines)
- **The scorer is pure and reusable:** `scanner/consensus.rs` (`score_market`,
  `score_all_strategies`, `MarketBook`, `TraderVote`, `ConsensusParams` — incl. the deep-edge
  knobs `trusted_only`/`certified_only`/`cross_cohort_cutoff`) and the single book builder
  `cycles/consensus_cycle.rs::books_from_window_votes` (pub(crate)). The replay engine MUST
  assemble books through these exact functions — a parallel scorer is how replay lies.
- **The gate is one place:** `scanner/promotion.rs` (`promotion_verdict`, `surplus_bounds`,
  `PromotionParams`, `SELECTION_NULL_P_BAR`) + `scripts/selection_null.py`. Replay verdicts
  reuse it with the search-family Bonferroni denominator. Do NOT invent a second gate.
- **As-of pattern + hazard:** `scripts/asof_slice_scores.sql` (event-date windowing, D1).
- **Raw atoms for exact parity:** `consensus_signals.observed_votes` (JSON vote atoms per
  emitted signal) + `initial_mean_price`/`mean_price` (at-fire entry, D6).
- **Report/analysis harness pattern:** `scanner/earned.rs::report_deep_sharp_pass` (`#[ignore]`d
  read-only harness against `$DATABASE_URL`) — the house pattern for running REAL Rust gate
  code over a snapshot; `scripts/deep_edge_thesis.py`, `scripts/tail_records.py`,
  `scripts/relational_probes.py` (the instruments the refresh will orchestrate; all take
  `PG_CONTAINER`).
- **Arm registration seams:** `cycles/consensus_cycle.rs::active_portfolio` (flag-gated arm
  appending; see `CONSENSUS_TRUST_ARMS` + `parse_retuned`/`retuned_arm` for the fail-closed
  env-parameterized-arm pattern the survivor slots generalize), `scanner/enrich/mod.rs::family`
  (experimental Bonferroni family), `config.rs` (`#[config(env=…, default=…)]`, defaults =
  today).
- **Board:** `board.rs` — surface the registry/flywheel status like the earned panel
  (TTL-cached, read-only, never alerting).
- **Backups:** `scripts/consensus-backup.sh` (daily 04:00 pg_dump the refresh restores from);
  `scripts/consensus-autoupdate.sh` (deploy mechanics).

## Rejected approaches (do not build these)
- ❌ Promoting anything to alerting (or eligibility) on replay evidence. Replay survivors go to
  SILENT forward slots; the forward gate + a deliberate human flip promote. No exceptions.
- ❌ An unbounded/adaptive search ("keep mining until something clears"). The grid is
  pre-registered in Phase 2 BEFORE scoring; its size is the Bonferroni denominator; extending
  it mid-run restarts the correction at the larger size.
- ❌ A second scorer, gate, baseline, or trust metric. Reuse `score_market` +
  `promotion_verdict` + the band-blind construction. Parity (Phase 0) exists precisely to
  prove the replay path equals the live path.
- ❌ Trusting backfill-era `ts` for anything time-ordered (D1), or letting the current-rank
  approximation silently carry a rank-dependent candidate to a forward slot.
- ❌ Per-candidate DB schema, per-candidate reports, or any findings surface OUTSIDE the
  registry. One registry; reports link into it.
- ❌ Raising `TRACK_DEPTH` in THIS run (separate scale-gated change — but design the flywheel
  so depth 500 is absorbed with zero changes: no hardcoded universe sizes anywhere).
- ❌ Editing applied migrations; touching prod postgres directly; concurrent write-agents;
  real money or live betting.

---

## Phase 0 — Snapshot infra + span audit + REPLAY PARITY (the honesty hard-stop)
Build `scripts/flywheel/restore.sh` (restore the latest backup into `pg-flywheel`,
idempotent, prints the snapshot date) and `scripts/flywheel/span_audit.py` (re-measure and
print the substrate table above: fills/events/wallets, per-axis spans, live-era event-days,
per-sport budgets — the numbers every later phase parameterizes on). Then **parity**: a
replay harness (house pattern: `#[ignore]`d Rust test or small bin using `score_market` +
`books_from_window_votes`) that (a) replays the stored `observed_votes` atoms of resolved
signals and reproduces each forward strategy's scoreboard record — hit-rate, at-fire surplus,
event/day counts — within a stated tolerance (document any residual and its cause: alert
dedup, eligibility filtering, window boundaries); (b) reconstructs books from `trader_fills`
over the live era and reproduces the SAME records from raw fills (the harder parity — this
validates the archive→book path the sweep depends on). **If (b) parity fails and cannot be
explained + fixed, STOP the sweep phases and report why** — a replay that can't reproduce
known forward records must not be allowed to evaluate new candidates. Gate, commit.

## Phase 1 — The findings registry (make everything we know one queryable surface)
`REGISTRY.md` at repo root (human-readable, git-versioned, machine-parseable table blocks —
keep it grep-able; no external tooling). One row per hypothesis/arm/finding: stable id,
pre-registration date + definition (or pointer), evaluation basis (forward / replay-live /
replay-eventdate), current status ∈ {CERTIFIED, FORWARD-CONFIRMING, REPLAY-SURVIVOR,
POWER-PENDING, INDETERMINATE, NULL, REFUTED, RETIRED}, latest N events / event-days / LB /
p_sel, snapshot date of last re-score, and **unblock condition** (e.g. "N≥30 deep-backed
events" — the thing the refresh checks). **Migrate every existing finding**: the certified
winners (favorite, elite_fresh_fav), the strict/loose/portfolio records, market_resid
(REFUTED), congregation (NULL), deep-edge results (0/13, Tier-B p=0.29 POWER-PENDING), tail
arms (accruing), relational probes (NULLs), co-under/capture findings referenced in
REPORT-*.md. Add a small board section (read-only, TTL-cached) showing registry counts by
status + the nearest unblock conditions. From this phase on, EVERY result this run produces
is a registry row first, prose second. Gate, commit.

## Phase 2 — The corrected replay sweep (generator at scale)
**Pre-register the grid in the registry BEFORE scoring** (one commit with the full grid, then
scoring — the commit order is the audit trail). Grid dimensions (bounded; suggested ~300–600
configs total): price bands × sports modes × backer/opposer thresholds × price-coherence ×
freshness tiers (live-era only) × cohort/trust dimensions (`trusted_only`, `certified_only`,
cross-cohort, quality vs count weighting) × the existing named variants as anchors. Replay
each config over as-of books (live era for freshness-gated; event-date axis for
freshness-free), judged EXACTLY as the scoreboard judges: at-fire surplus over the band-blind
baseline, event-clustered, day-deflated, `promotion_verdict` with **n_strategies = the full
grid size**, plus the two doctrine deflators: **shuffled-outcome ghost floor** (entire search
re-run on permuted outcomes ≥3×; report the best ghost LB — candidates below it are noise by
construction) and **selection-matched null** (`selection_null.py` pattern) for each surviving
candidate. Output: every config's deflated record into the registry (survivors as
REPLAY-SURVIVOR with effect size + which era/axis; everything else NULL/INDETERMINATE with
numbers). Cap survivors advanced to Phase 3 at the top **K=5** by deflated LB. Expect few or
zero survivors at 14 event-days — that is an honest, registry-recorded outcome; the sweep
re-runs on every refresh as days accrue. Gate, commit.

## Phase 3 — Forward-confirmation slots (survivors flow without code changes)
Generalize the `CONSENSUS_RETUNED` pattern: pre-allocate **5 silent arm slots**
(`replay_a`…`replay_e`, experimental family, never alert) whose FULL `ConsensusParams` parse
fail-closed from env (`REPLAY_ARM_A="band=0.65:0.98,min_backers=4,…"`; unparseable/empty ⇒
slot not registered ⇒ portfolio byte-identical). Slot specs are recorded in the registry row
(id ↔ slot). Pure param-parser unit tests + a live test proving empty slots = today's
portfolio. Update compose + `.env.consensus` pass-throughs (both files). Wire the top
survivors (if any) into slots; status → FORWARD-CONFIRMING. From now on the pipeline is:
sweep → registry → slot → forward gate → (human flip) — no code edits per candidate. Gate,
commit.

## Phase 4 — The standing refresh (the flywheel's motor)
`scripts/flywheel/refresh.sh` — ONE idempotent entrypoint that: restores the latest backup →
span audit → parity smoke (fast subset; abort refresh on parity break) → re-runs every
registry-relevant instrument (`report_deep_sharp_pass`, `deep_edge_thesis.py` (+ `--certified`
feed from the pass), `tail_records.py`, `relational_probes.py`, the Phase-2 sweep re-score,
forward-slot scoreboard read) → updates registry rows (numbers + any status transitions) →
writes `reports/flywheel/<date>.md` (dated, append-only directory) → prints a one-screen
delta summary (status changes + nearest unblocks only). Design constraints: O(new data) where
possible (era-windowed queries), bounded runtime (~minutes), zero prod access, and **silent
by default** — an ntfy push ONLY when a status CHANGES to REPLAY-SURVIVOR / promotable /
CERTIFIED-adjacent (minimal-noise policy). Add a launchd plist (`~/Library/LaunchAgents`,
weekly, e.g. Sunday 05:00 after the 04:00 backup) + a README line on running it manually.
The refresh is what turns "we only get more accrual from here" into automatic sharpening.
Gate, commit.

## Phase 5 — Consolidate, verify, ship, report
Full gate; live-verify on throwaway PG (parity suite, slot registration, refresh end-to-end
against the latest backup). `merge --no-ff` into local `main`; autoupdater deploys; verify
container healthy, portfolio unchanged unless slots configured, board shows the registry
panel, `strict` byte-for-byte (alert config untouched; zero new alerting strategies).
Final report `REPORT-ARCHIVE-FLYWHEEL.md`: parity result (with tolerances), the pre-registered
grid + ghost floor + survivor list (or the honest zero), registry census (rows by status),
refresh cadence + how to read its delta reports, exact prod flag/env record, and what
unblocks each POWER-PENDING row. Update the memory index pattern via the session that runs
this (registry supersedes scattered findings as the canonical surface). Gate, commit, done.

---

## Acceptance
1. **Parity proven or honestly failed-and-stopped**: replay reproduces the forward scoreboard
   from both stored atoms and raw fills, tolerances documented.
2. **REGISTRY.md** exists, holds ALL migrated findings + everything this run produced, each
   row with status, numbers, snapshot date, unblock condition; board surfaces it.
3. **A pre-registered, fully-corrected sweep** ran end-to-end (grid committed before scoring;
   family-size Bonferroni + ghost floor + selection nulls), results in the registry; ≤5
   survivors wired to slots (zero survivors is acceptable and expected at ~14 event-days).
4. **5 env-parameterized silent forward slots**, fail-closed, byte-identical when empty,
   dual-declared in compose + env.
5. **`flywheel/refresh.sh` + weekly launchd**: one command re-scores the entire registry
   against a fresh snapshot, appends a dated delta report, pushes only on material status
   changes; proven by running it twice (second run = clean no-change delta).
6. Final `merge --no-ff` + autoupdater deploy verified; `strict` and all live alerting
   byte-for-byte unchanged; production flag record in the report; nothing promoted that
   didn't clear the forward gate (i.e., nothing promoted).

## Standing disciplines
Extend, don't rebuild — the scorer, the gate, the harness patterns, and the backup/restore
loop all exist; the flywheel composes them. Additive + reversible; every flag/slot defaults
to today's behavior. Pre-register before scoring; correct for the whole family; beat the
ghost; event-cluster and day-deflate everything; tag every number with its era/axis. Replay
generates, the forward gate certifies, a human flip promotes. One registry, dated delta
reports, minimal noise. Cost-zero, paper-only, **NO real money**. An honest NULL beats a
flattering number — and with the refresh in place, today's NULL re-argues its case every week
for free.
