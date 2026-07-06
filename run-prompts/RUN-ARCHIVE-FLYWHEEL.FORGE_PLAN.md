# FORGE PLAN — The Archive Flywheel

*Implementation blueprint. Supersedes the design sections of
`RUN-ARCHIVE-FLYWHEEL.AUTONOMOUS.md` (which remains the mission/philosophy source of truth).
Every code fact below was grep/Read-verified against the live tree on 2026-07-02; the
load-bearing ones carry file:line. Build in a dedicated worktree off `main`; gate + commit
per phase; `merge --no-ff` at the end.*

---

## VERDICT (read first — answers "is this the best/most reliable way?")

**The architecture is right; the brief as written is not directly buildable and hides one
data-loss foot-gun.** What *survives* unchanged: replay-as-microscope (never certifier), one
findings registry, a pre-registered/family-corrected sweep, pre-allocated env-parameterized
silent slots, a weekly O(minutes) refresh, and the non-negotiable **reuse of `score_market` +
`books_from_window_votes` + `promotion_verdict` + the `_blind` band baseline** (no second
scorer/gate/baseline — the `market_resid` false-promote memory). What is *overturned or
hardened*: (1) "reconstruct books and reproduce the forward record within a tolerance" is
**provably impossible** — the gate judges on `initial_mean_price` (at-fire, set once,
`consensus.rs:610`), which is **stored in neither substrate**; `observed_votes` is **overwritten
every cycle** (`consensus.rs:253`, verified) so it is a *last-fire, lossy* snapshot, and
`trader_fills` carries no rank. Parity therefore becomes a **checked-in per-column ledger** over
count-based strategies in the live era, not a scalar tolerance. (2) The replay decision point
**must be first-fire, not peak `max(ts)`** — peak drifts entry ~+1.2¢ (`consensus.rs:613`), which
*exceeds the brief's own parity tolerance*. (3) The sweep substrate is **`trader_fills`, not the
atoms** (the atoms cannot support as-of cuts and drift entry late); the atoms are kept only for
the frozen-rank parity path. (4) The registry becomes a **generated view** (tiny hand-authored
source + a Rust `verdict_cli` that reuses `promotion_verdict`) so numbers/status can never drift —
essential for unattended reliability. (5) The ghost floor **must permute at the event level**
(fill-level silently understates noise) and the slot grammar becomes a **typed serde JSON spec**
(fail-closed by construction). (6) Autonomy — the user's escalated requirement — was named but
never engineered; this plan adds a target dispatcher, `flock`/atomic/`trap`-ERR refresh, a
bot-hosted staleness watchdog, the `PG_CONTAINER` patch, and a **hard throwaway-assertion guard**
that makes the insert-and-`TRUNCATE` sweep incapable of touching prod. Net: the flywheel is the
best available design **once these six corrections are applied**; shipped verbatim from the brief
it would produce silently-wrong effect sizes and carries a latent prod-`TRUNCATE` risk.

---

## Outcome

An as-of **replay engine** over the 400k-fill archive that scores strategy candidates at ~10× the
event-N of any forward record, a **pre-registered, family-corrected sweep** whose survivors flow
into pre-allocated **silent forward slots** with zero code changes, a **generated findings
registry** that re-derives every number/verdict from the live gate on each snapshot, and a
**crash-safe weekly refresh** that runs unattended (flock, atomic writes, failure-only push,
board-hosted staleness) so every accrued day sharpens every open question automatically. Replay
generates; the forward gate certifies; a human flips. No new scorer, gate, baseline, migration, or
schema. `strict` and all live alerting stay byte-for-byte.

---

## Item 1 — Snapshot infra: idempotent restore + span audit + a hard throwaway guard

**Before.** The brief gives raw `docker run`/`gunzip` lines inline; no idempotency, no re-measure
script, and nothing prevents a later DB-writing step from targeting prod.

**After.** Two scripts + a shared guard function that every DB-mutating step sources.

**Implementation.**
`scripts/flywheel/restore.sh` (idempotent; drops first so a reap can just re-run):
```bash
#!/bin/bash
set -euo pipefail
REPO="$HOME/polymarket-bot"
docker rm -f pg-flywheel >/dev/null 2>&1 || true            # idempotent
docker run -d --name pg-flywheel -e POSTGRES_DB=polymarket -e POSTGRES_USER=bot \
  -e POSTGRES_PASSWORD=bot -p 55497:5432 postgres:17-alpine >/dev/null
until docker exec pg-flywheel pg_isready -U bot -d polymarket >/dev/null 2>&1; do sleep 1; done
latest=$(ls -1t "$REPO"/backups/consensus-*.sql.gz | head -1)
gunzip -c "$latest" | docker exec -i pg-flywheel psql -U bot -d polymarket -q
echo "restored $(basename "$latest")"                       # prints snapshot date every phase reads
```
`scripts/flywheel/_guard.sh` (sourced by every step that writes/reads a flywheel DB — the
prod-`TRUNCATE` foot-gun killer; see Item 5):
```bash
# Refuse to proceed unless DATABASE_URL points at the throwaway (port 55497) OR pg-flywheel.
flywheel_db_guard() {
  case "${DATABASE_URL:-}" in
    *:55497/*|*@pg-flywheel*) return 0 ;;
    *) echo "FATAL: DATABASE_URL is not the pg-flywheel throwaway ($DATABASE_URL)"; exit 3 ;;
  esac
}
```
`scripts/flywheel/span_audit.py` (stdlib, `PG_CONTAINER` env, `--csv`): re-emits the substrate
table (fills / resolved BUY / wallets / distinct events / per-axis spans / live-era event-days /
per-sport budgets) that every later phase parameterizes on. Model verbatim on
`scripts/deep_edge_thesis.py` (which already reads `PG_CONTAINER=os.environ.get("PG_CONTAINER","pg-report")`).

The **Rust** harnesses (parity, sweep) carry the same guard in-process, because a `#[ignore]`d test
that reads `$DATABASE_URL` and later `TRUNCATE`s is the actual risk:
```rust
/// Refuse to run destructive replay against anything but the throwaway snapshot.
fn assert_throwaway(pf: &PgPortfolio) {
    // current_database() is 'polymarket' on both; discriminate on the sentinel: the throwaway
    // is a FRESH restore with NO 'flywheel_prod_marker' table (prod has one we add once).
    // Cheapest robust check: the connection port. We read it from DATABASE_URL at construction.
    assert!(std::env::var("DATABASE_URL").unwrap_or_default().contains(":55497/"),
        "FLYWHEEL SAFETY: replay/sweep may only run against the :55497 throwaway");
}
```

**Integration points.** New `scripts/flywheel/{restore.sh,_guard.sh,span_audit.py}`. Backup source
= `scripts/consensus-backup.sh` (verified: 04:00, gz, keep-14 via `ls -1t … | tail -n +15 | xargs rm`).
Throwaway ports 55497 (analysis) / 55496 (migrated Rust live-test), per the brief.

**Runtime/cost.** Restore ≈ 1 min (76 MB gz, dossier-measured) — the single largest block; span
audit seconds.

**Source.** hybrid (A+B restore, identical) **+ refined** (the `_guard.sh`/`assert_throwaway`
foot-gun killer — neither agent added it; it is required by the Item-5 insert-and-`TRUNCATE` design).

---

## Item 2 — As-of replay engine: bounded fills loader + FIRST-FIRE decision point

**Before.** "Reconstruct books from `trader_fills`" → an implementer calls
`load_buy_fills_since(t)` (`consensus.rs:1360`, verified: **no upper bound**, re-derives quality
from **current** rank, applies **current** `consensus_eligible OR earned_eligible`) and silently
scores "as of 2026-06-22" with 2026-07-02 state. Agent A then scores each market at `now=max(ts)`
(peak) — which drifts entry ~+1.2¢ (`consensus.rs:613`) and **contradicts its own ±0.5pp parity
tolerance**.

**After.** A bounded, eligibility-free as-of loader + a **first-fire** windowing pass: for each
config, the decision point is the *earliest* 48h window in which that config's gate fires — mirroring
the live cycle's at-fire entry (`initial_mean_price`), which is the number the gate judges on.

**Implementation.**
New loader in `common/src/storage/consensus.rs` (twin of `load_buy_fills_since:1360`; drop the
current-state eligibility clause, add an era floor; returns `WindowVote` so
`books_from_window_votes` is reused unchanged):
```rust
/// As-of BUY-fill loader for replay. vs load_buy_fills_since: (1) era floor so backfill-era
/// crawl-`ts` (D1) never forms a freshness book; (2) NO current-eligibility filter — replay
/// applies eligibility itself. One indexed read over the whole live era.
pub async fn load_live_era_buy_fills(&self, era_start: DateTime<Utc>) -> Result<Vec<WindowVote>> {
    sqlx::query_as(
        "SELECT tf.wallet AS trader_wallet, \
                COALESCE(ft.username, LEFT(tf.wallet,8)) AS name, ft.rank AS rank, ft.pnl AS pnl, \
                CASE WHEN ft.rank>=1 THEN 1.0+GREATEST(0,50-LEAST(ft.rank,50))::float8/50.0 ELSE 1.0 END AS quality, \
                tf.condition_id, tf.outcome_index, tf.outcome, tf.title, tf.slug, tf.event_slug, \
                tf.is_sports, tf.price, tf.size_usd, tf.ts \
         FROM trader_fills tf LEFT JOIN followed_traders ft ON LOWER(ft.proxy_wallet)=tf.wallet \
         WHERE tf.side='BUY' AND tf.ts >= $1")
      .bind(era_start).fetch_all(&self.pool).await.context("load_live_era_buy_fills")
}
```
New pure module `copy-trading-bot/src/scanner/replay.rs` — **first-fire** cuts. Per market,
precompute the *window-change breakpoints* once (each fill entering or leaving the trailing 48h
window is a breakpoint; there are O(fills-in-market) of them, tens typically). Then per config,
walk breakpoints in time order and stop at the first where `score_market` emits a signal:
```rust
/// For one market's votes (time-sorted), the ascending set of candidate decision points:
/// each fill's ts (a fill enters the window) — the book only changes at these instants.
fn breakpoints(votes: &[WindowVote]) -> Vec<DateTime<Utc>> {
    let mut ts: Vec<_> = votes.iter().map(|v| v.ts).collect(); ts.sort(); ts.dedup(); ts
}
/// FIRST-FIRE cut for `params` in one market: earliest window whose book fires. Returns the
/// firing (book, now) or None. Reuses the single builder + pure scorer verbatim.
fn first_fire(votes: &[WindowVote], trust: &TrustMap, w: Duration, params: &ConsensusParams)
    -> Option<(MarketBook, DateTime<Utc>)>
{
    for now in breakpoints(votes) {
        let lo = now - w;
        let win: Vec<WindowVote> = votes.iter().filter(|v| v.ts > lo && v.ts <= now).cloned().collect();
        if let Some(book) = books_from_window_votes(&win, trust).into_iter().next() {
            if !score_market(&book, now, params).is_empty() { return Some((book, now)); }
        }
    }
    None
}
```
For the **coarse kill** pass only (cheaply eliminating configs that never fire at all), a
`peak`-cut variant (`now = *breakpoints.last()`) is an allowed pre-filter — but every effect size
that ranks a survivor or feeds a slot uses `first_fire`. Freshness clock = `trader_fills.ts`, valid
only in the live era (`REPLAY_ERA_START = 2026-06-20T00:00Z`); every result row tagged
`era ∈ {live,backfill}` and `axis ∈ {ts, event-date}`. Freshness-gated configs (`max_age_mins <
i64::MAX`) are **live-era only**; freshness-free configs additionally use the slug event-date axis
across the whole archive (D1, `asof_slice_scores.sql`).

**Integration points.** New `load_live_era_buy_fills` (beside `:1360`); new
`scanner/replay.rs` + `mod replay;` in `scanner/mod.rs`; calls `books_from_window_votes`
(`consensus_cycle.rs:522`, `pub(crate)`) and `score_market` (`consensus.rs:325`) unchanged. Template
= `trader_slice_scores_asof` (`:1526`, verified `resolved_at < $1` as-of pattern).

**Runtime/cost.** One indexed read (~tens of MB); breakpoints precomputed once per market; first-fire
is O(configs × events × breakpoints) with tens of breakpoints → seconds-to-low-minutes CPU
(arithmetic in Item 5).

**Source.** hybrid (A's bounded loader + Rust-side windowing) **+ refined** (first-fire replaces A's
peak `max(ts)`; the peak choice was verified to violate A's own parity tolerance).

---

## Item 3 — Parity: a checked-in per-column ledger over count-based strategies (not a tolerance)

**Before.** "Reproduce the scoreboard record within a stated tolerance; if (b) fails and can't be
explained, STOP." The scoreboard record is 8+ heterogeneous columns that fail for **six different
structural reasons**; one scalar tolerance makes STOP a coin-flip.

**After.** A committed `reports/flywheel/parity-ledger.tsv` pre-declares every column's rule; the
harness asserts column-by-column and STOPs only when a column *declared exact* drifts. Two paths:
**(a)** atoms (frozen rank) reproduce membership + count columns exactly; **(b)** fills reproduce the
at-fire surplus via first-fire entry within a data-derived bound, reframed as a **set-coverage**
check (the scorer is a pure function of the atom set, so matching the *inputs* is stronger than
chasing an un-storable output number).

**The ledger (committed before the harness runs):**
```
# column           basis        rule                 expected_break                                   stop_if
net_count          atom-replay  exact                none                                             delta!=0
n_backers          atom-replay  exact                none                                             delta!=0
tier               atom-replay  exact                none                                             delta!=0
distinct_events    atom-replay  exact                none                                             delta!=0
mean_price         atom-replay  exact                none                                             delta!=0
surplus            fills-replay bounded              entry=first-fire ~= initial_mean_price(at-fire)  |Δ|>0.005 in live era
distinct_days      *            N/A                  forward axis=first_detected_at (no replay source) never
our_clv            *            N/A                  needs live initial_market_price                  never
capture_lag        *            N/A                  needs live capture timing                        never
eligibility_set    fills-cov    bounded              rank churn drops wallets ineligible-as-of-now    coverage<0.98 live era
last_fire_entry    atom-replay  documented           observed_votes overwritten each cycle (=253)     never
```
The six residuals map to ledger rows: (1) eligibility/rank history not stored → `eligibility_set`;
(2) window append+prune vs durable fills → `eligibility_set` boundary; (3) trust/certified
re-derived from *current* TrustMap → trust arms marked `forward-only`, not parity-tested; (4)
alert-time capture → the three `N/A` rows; (5) all-MM-outcome corner → coverage hole; (6) **verified
sixth: `observed_votes` is last-fire (`:253`), so atom-replay entry = drifted `mean_price`, not
at-fire `initial_mean_price`** → the `last_fire_entry` documented row, and the reason path-(a)
parity is claimed on `mean_price` (the stored, drifted column) while path-(b) fills carry the
at-fire surplus.

**Harness** (house pattern: `#[ignore]`d read-only tokio test, model = `report_deep_sharp_pass`
`earned.rs:366`):
```rust
#[tokio::test]
#[ignore = "parity: run against restored snapshot at $DATABASE_URL (:55497)"]
async fn replay_parity() {
    let pf = connect_snapshot().await;              // assert_throwaway(&pf) — Item 1
    let fwd = pf.consensus_scoreboard_by_strategy().await.unwrap();       // reused baseline, :607
    let ledger = load_parity_ledger("reports/flywheel/parity-ledger.tsv");
    // Path (a): atom-replay reproduces COUNT columns exactly (frozen rank).
    let rep = replay_scoreboard_from_atoms(&pf).await;                    // Item 2 pipeline on _blind atoms
    for s in ["favorite","elite_fresh_fav","strict"] {
        for col in ledger.exact_cols() {                                 // net_count,n_backers,tier,distinct_events,mean_price
            assert_eq!(fwd.get(s,col), rep.get(s,col), "PARITY STOP: {s}.{col} declared exact drifted");
        }
    }
    // Path (b): COVERAGE, not number-match — atom SET from fills ⊇ set in observed_votes.
    let cov = fills_atom_coverage(&pf, Era::Live).await;                  // |fills∩observed|/|observed|
    assert!(cov >= 0.98, "PARITY STOP: fills→book coverage {cov:.3} < 0.98 live era");
}
```
`replay_scoreboard_from_atoms` re-uses the **exact** `consensus_scoreboard_by_strategy` aggregation
(event-cluster, `_blind` band-blind, `first_detected_at` day count) by inserting replayed rows and
calling the real function (Item 5) — never a re-implemented formula.

**Integration points.** Reuses `consensus_scoreboard_by_strategy` (`:607`, verified columns/axis);
atom shape fixed by `atom_log` (`consensus_cycle.rs:920-928`, verified 7 fields, `ts`=epoch sec,
no quality/trust); proof template = `deep_pool_excluded_from_signals_shadow_differs`
(`consensus_cycle.rs:1156`).

**Runtime/cost.** Subset (2–3 strategies, live era): one read + in-memory pass — seconds. The
`refresh.sh` "parity smoke" runs the same count-column subset and aborts on STOP.

**Source.** hybrid — Agent A's residual enumeration + Agent B's checked-in signed ledger and
coverage-reframe; the `last_fire_entry` row is the verified sixth residual both under-stated.

---

## Item 4 — Findings registry as a GENERATED view (numbers/status can't drift)

**Before.** "Human-readable, git-versioned, machine-parseable table blocks" — three fighting
adjectives, no schema, and hand-maintained numbers that drift the instant a script isn't re-run
(the exact failure the brief itself names: "N=38 sitting unexamined").

**After.** Split source from view. A tiny hand-authored `findings-source.tsv` (human fields only,
append-only) is JOINed by a stdlib generator with live snapshot numbers, and **status is derived
from the one gate** via a thin Rust `verdict_cli` — so `REGISTRY.md` is a build artifact that cannot
lie about the numbers. This is the design that makes the *unattended* refresh trustworthy.

**Implementation.**
`findings-source.tsv` (hand-authored; the pre-registration audit trail lives in *its* git history):
```
# id              preregistered  basis            definition_ptr                 target_n  evaluated_at  human_verdict  unblock
favorite          2026-06-28     forward          REPORT-DEEP-EDGE.md#favorite   —         —             —              N>=50-post-wimbledon
elite_fresh_fav   2026-06-28     forward          consensus.rs:705               —         —             —              N>=50
market_resid      2026-06-28     forward          project-polymarket-market-resid —        2026-07-01    REFUTED        permanently:label-perm-z=-0.10
tierB_deep        2026-07-02     replay-live       REPORT-DEEP-EDGE.md#tierB      30        —             —              N>=30-deep-backed-events
```
`verdict_cli` — a `[NEW]` 30-line bin (or `--json` mode on the existing report harness) that loads
the snapshot, calls `promotion_verdict(distinct_events, distinct_days, surplus, surplus_sd,
n_strategies, selection_null_p, &PromotionParams::default())` (`promotion.rs:168`, verified sig)
per strategy with the correct Bonferroni denominator + `family()` class (`enrich/mod.rs:338`), and
prints `id,promotable,lb,n_events,p_sel` CSV. **Status is never derived in Python** — the one-gate
constraint holds.
`scripts/flywheel/render_registry.py` (stdlib, `PG_CONTAINER`, atomic write): reads the source,
calls `verdict_cli`, derives status (human latch `REFUTED/RETIRED` wins; else the gate verdict;
`POWER-PENDING` when `n_events < target_n`), writes `REGISTRY.md` with a fenced TSV block:
```
# id              status          n_events n_days  lb       p_sel   snapshot    unblock
favorite          CERTIFIED       92       —       +0.033   0.0000  2026-07-02  N>=50-post-wimbledon
elite_fresh_fav   CERTIFIED       38       —       +0.048   0.0000  2026-07-02  N>=50
market_resid      REFUTED         —        —       —        —       2026-07-02  permanently:label-perm-z=-0.10
tierB_deep        POWER-PENDING   22       —       +0.158   —       2026-07-02  N>=30-deep-backed-events
```
Fenced TSV = diff-clean (row-scoped diffs, append = line-add), `cut -f4`/`awk`-parseable, prose
wraps it. **Board parser** (`board.rs`, ~12 lines): split on `\t`, skip `#`/non-tab lines, tally by
status. Migration of ~25 findings = ~25 short *source* lines (human fields only; numbers auto-fill).

**Integration points.** `REGISTRY.md` + `findings-source.tsv` at repo root — **docs-only paths**;
verified the autoupdater `CODE_RE`
(`^(common/|copy-trading-bot/|migrations/|Cargo\.|Dockerfile\.consensus|docker-compose\.consensus\.yml)`,
`consensus-autoupdate.sh:40`) matches neither, so refresh commits skip the rebuild. Status source =
`promotion_verdict` + `family` only.

**Runtime/cost.** One scoreboard query + one `verdict_cli` + a text write — sub-second.

**Source.** rethink (Agent B) — the generated view directly serves the user's reliability
requirement (numbers are always the current snapshot's); Agent A's hand-maintained TSV is rejected
because it can silently drift, the very failure mode the brief names.

---

## Item 5 — The corrected sweep: insert replay rows → reuse the real scoreboard (one query), per-config checkpoint

**Before.** "~300–600 configs," no runtime, no checkpoint, no permutation unit. Can't tell if it is
a reap hotspot; a reap re-does everything.

**After.** Replay every config in-memory (Item 2 first-fire), **insert the resulting signals into a
throwaway `consensus_signals` tagged by config id**, and judge the *entire grid in one*
`consensus_scoreboard_by_strategy` pass — so the sweep literally cannot drift from the gate's math
(the strongest possible anti-`market_resid` guarantee). Per-config JSONL makes a reap cost <1s.

**Implementation.** Pipeline (ordering is load-bearing — see the guard):
```
0. restore (Item 1) → assert_throwaway
1. parity (Item 3) captures the FORWARD scoreboard to reports/flywheel/<snap>.forward.tsv
2. TRUNCATE consensus_signals          # throwaway ONLY; guarded; forward already on disk
3. for cfg in PRE_REGISTERED_GRID:      # Rust loop, resumable
     rows = []
     for (book, now) in first_fire_all(&votes,&trust,W,&cfg.params):   # Item 2
        for sig in score_market(&book, now, &cfg.params):
           rows.push(ReplaySignalRow{ strategy: cfg.id, condition_id, outcome_index,
                     event_slug, initial_mean_price: sig.mean_price, first_detected_at: day_axis(now,cfg),
                     resolved:true, outcome_won })
     insert_replay_signals(&rows)                                       # UNNEST
     append_line("reports/flywheel/sweep-<snap>.jsonl", {cfg:cfg.id, n_picks:rows.len()})  # checkpoint
   # ALWAYS include a replay `_blind` (min_backers:1) so the scoreboard has its band baseline
   # built from the SAME first-fire entry basis as the candidates (baseline consistency — why TRUNCATE).
4. board = consensus_scoreboard_by_strategy()          # ONE query, GROUP BY strategy → all configs
5. for row in board: promotion_verdict(row.distinct_events, row.distinct_days, row.surplus,
                        row.surplus_sd, GRID_SIZE, sel_null_p[row], &PromotionParams::default())
```
`day_axis(now,cfg)` = `now` for freshness/live-era configs; the **slug event-date** for
freshness-free configs (D1 — a crawl-`ts` `first_detected_at` would corrupt `distinct_days`; this is
the one place Agent A's `first_detected_at=now_m` was incomplete).
`[NEW] insert_replay_signals` — UNNEST twin of `insert_trader_fills` (`:1267/1290`, verified). Must
supply the **12 no-default NOT NULL columns** (verified from `migrations/021_consensus.sql`):
`condition_id, outcome_index, n_backers, n_opposers, net_count, net_quality, mean_price, price_std,
recency_mins, total_usd, score, tier` — neutral literals for the non-judging ones (`n_backers=0,…,
score=0, tier='WATCH'`) — plus override the defaulted `strategy` (default `'strict'`), `resolved`
(→TRUE), `first_detected_at` (→day axis), and set `initial_mean_price` (→first-fire entry) +
`outcome_won` + `event_slug`. The scoreboard reads exactly
`{strategy, event_slug|condition_id, resolved, outcome_won, COALESCE(initial_mean_price,mean_price),
first_detected_at, initial_market_price(NULL→CLV skipped)}` (verified `:637-690`).

**Arithmetic (binding cost = restore, not scoring).** 403,742 resolved BUY fills; 2,353 live events;
`score_market` is pure µs-scale. First-fire ≈ `600 configs × 2,625 events × ~tens of breakpoints ≈
low tens of millions of calls ≈ tens of seconds CPU`. One UNNEST of ~180k rows and one scoreboard
query ≈ seconds. Ghost floor (Item 6) ≈ +24s. `selection_null.py` per survivor (≤5) ≈ seconds each.
Restore ≈ 1 min. **Total: single-digit minutes, dominated by restore.**

**Checkpoint.** `sweep-<snap>.jsonl`, one flushed line per config; resume = `wc -l` → skip the first
N pre-registered configs (grid is committed + ordered). Reap loss <1 config.

**SAFETY (the foot-gun killer).** `TRUNCATE consensus_signals` against **prod** would destroy the
live record. Mitigations, all required: (i) `assert_throwaway` (Item 1) in the harness *before* any
write; (ii) the sweep only ever runs via `run.sh sweep`, which exports `DATABASE_URL=…:55497…`;
(iii) the permission classifier already denies prod `psql`. Order is enforced: parity/forward-capture
**before** TRUNCATE.

**Integration points.** `[NEW] insert_replay_signals` (`common/…/consensus.rs`); reuses
`consensus_scoreboard_by_strategy` (`:607`) + `promotion_verdict` (`:168`, `n_strategies=GRID_SIZE`);
`[NEW] PRE_REGISTERED_GRID` + `run_replay_sweep` `#[ignore]`d harness in `scanner/replay.rs`. The grid
stanza is appended to `findings-source.tsv` and committed **before** the scoring commit
(pre-registration = commit order). The sweep's Bonferroni denominator is its **own** `GRID_SIZE`, not
`family()`.

**Runtime/cost.** Above.

**Source.** hybrid — Agent A's insert-and-reuse mechanism (best correctness + baseline consistency
via TRUNCATE) + both agents' per-config JSONL + Item-2 first-fire + the refined day-axis fix and the
throwaway guard.

---

## Item 6 — Event-level ghost floor + selection-null per survivor (two distinct deflators)

**Before.** "Shuffled-outcome ghost floor (entire search re-run on permuted outcomes ≥3×)" with no
permutation *unit* → the natural (wrong) reading shuffles `outcome_won` across individual fills,
destroying within-event correlation, collapsing the clustered SE, and certifying noise (the
`market_resid` class).

**After.** Keep **both** doctrine deflators, each at the correct level: (1) an **event-level**
shuffled-outcome ghost floor — the empirical max-of-K null the Bonferroni denominator does *not*
replace; (2) the per-survivor **selection-matched null** via `selection_null.py`, reused so the
event-clustering is structural, not remembered.

**Implementation.** Because the sweep already lands rows in the throwaway `consensus_signals`
(Item 5), the ghost is the same pipeline with a permuted event→won map:
```
for i in 0..GHOST_N (>=5):
   rng = seed(GHOST_SEED + i)                                   # index-varied (Date/rand banned in scripts)
   # event-level truth, matched within price band:
   events = SELECT COALESCE(event_slug,condition_id) ev, width_bucket(COALESCE(initial_mean_price,mean_price),0,1,5) band,
                   bool_or(outcome_won) ev_won FROM consensus_signals GROUP BY ev, band
   for band in bands: permute ev_won across events IN THAT BAND (fills stay together)
   UPDATE consensus_signals SET outcome_won = perm[ev]          # event-keyed
   board_ghost = consensus_scoreboard_by_strategy()             # reused verbatim
   append reports/flywheel/ghost-<snap>.jsonl {seed, best_ghost_lb = max_config promotion_verdict(...).lb}
deflated(cfg) = candidate_lb(cfg) - mean(best_ghost_lb)         # real candidate sits in the ghost tail
```
Per-survivor null (rule b) reuses `selection_null.py` verbatim (`clustered_surplus:95`,
`null_pvalue:106`, `band:79`, `--calibrate:147`, `N_PERM=2000`, `SEED=20260702`) fed into
`promotion_verdict`'s `selection_null_p` (bar `SELECTION_NULL_P_BAR=0.01`, verified `:97`). The
**one required edit** to that file (Item 8d): honor `PG_CONTAINER`, default preserving current
behavior.

**Integration points.** `[NEW] scripts/flywheel/ghost_floor.py` (the event-level permutation via the
reused scoreboard) writes `ghost-<snap>.jsonl`; `selection_null.py` imported for rule (b). Both read
`PG_CONTAINER=pg-flywheel`.

**Runtime/cost.** GHOST_N=5 × (one UPDATE + one scoreboard query) ≈ ~24s; per-survivor null seconds.
Each shuffle appends → a reap restarts at the next shuffle.

**Source.** hybrid — event-level permutation via Agent A's scoreboard mechanism (keeps the
empirical max-of-K floor the doctrine mandates) **+** Agent B's `selection_null.py` reuse for the
compositional null. Rejected Agent B's proposal to *replace* the ghost floor with the per-winner
selection null alone — that drops the max-of-K empirical deflator the search discipline requires
(Bonferroni corrects the threshold, not the effect-size null).

---

## Item 7 — Survivor slots: one typed serde JSON env var (fail-closed by construction)

**Before.** Generalize `parse_retuned` (3 positional ints, `consensus.rs:812`) to a hand-rolled
`key=value` parser over 15 `ConsensusParams` fields incl. an `Option<(f64,f64)>` band and three
enums, across `REPLAY_ARM_A..E` × 2 files — with hand-specified enum spellings and a fail-closed
rule per token.

**After.** Keep the pre-allocated `&'static str` name pool (required — verified
`StrategyDef.name:&'static str` `:205`), but feed it from **one** `REPLAY_ARMS` var holding a JSON
array parsed by **serde**. Serde *is* the grammar: field spelling = struct, enum spelling =
`#[serde(rename_all="lowercase")]`, unknown key = `deny_unknown_fields`, one-bound band = a type
error, empty/absent ⇒ empty vec ⇒ byte-identical portfolio.

**Implementation.**
```rust
#[derive(serde::Deserialize)] #[serde(deny_unknown_fields)]
struct ReplayArmSpec {
    #[serde(default)] band: Option<(f64,f64)>,
    #[serde(default)] min_backers: Option<usize>,   #[serde(default)] max_opposers: Option<usize>,
    #[serde(default)] max_price_std: Option<f64>,    #[serde(default)] max_age_mins: Option<i64>,
    #[serde(default)] strong_net: Option<i64>,       #[serde(default)] elite_net: Option<i64>,
    #[serde(default)] elite_rank: Option<i32>,       #[serde(default)] require_elite: Option<bool>,
    #[serde(default)] trusted_only: Option<bool>,    #[serde(default)] certified_only: Option<bool>,
    #[serde(default)] cross_cohort: Option<i32>,
    #[serde(default)] sports: Option<SportsSpec>,    #[serde(default)] weight: Option<WeightSpec>,
}
#[derive(serde::Deserialize)] #[serde(rename_all="lowercase")] enum SportsSpec { Include, Only, Exclude }
#[derive(serde::Deserialize)] #[serde(rename_all="lowercase")] enum WeightSpec { Count, Quality, Dollars, Trust }

impl ReplayArmSpec {
    /// Apply over `base` (=strict params); returns None if the coherence invariant fails
    /// (the SAME guard parse_retuned enforces: min_backers>=1 && strong_net>=min_backers && elite_net>=strong_net).
    fn into_params(self, base: &ConsensusParams) -> Option<ConsensusParams> {
        let mut p = base.clone();
        if let Some(v)=self.band { p.price_band=Some(v); }
        if let Some(v)=self.min_backers { p.min_backers=v; }
        /* … one line per field … */
        if let Some(w)=self.weight { p.weight_mode=match w { WeightSpec::Trust=>WeightMode::TrustWeighted,
            WeightSpec::Count=>WeightMode::Count, WeightSpec::Quality=>WeightMode::Quality, WeightSpec::Dollars=>WeightMode::Dollars }; }
        (p.min_backers>=1 && p.strong_net>=p.min_backers as i64 && p.elite_net>=p.strong_net).then_some(p)
    }
}
/// Fail-closed: any parse error OR coherence violation ⇒ that arm dropped. "" ⇒ [].
pub fn parse_replay_arms(spec: &str, base: &ConsensusParams) -> Vec<StrategyDef> {
    const NAMES: [&str;5] = ["replay_a","replay_b","replay_c","replay_d","replay_e"];
    let specs: Vec<ReplayArmSpec> = serde_json::from_str(spec.trim()).unwrap_or_default();  // ""→[]
    specs.into_iter().zip(NAMES)
        .filter_map(|(s,name)| s.into_params(base).map(|params| StrategyDef{ name, params, alerting:false }))
        .collect()
}
```
Registration — one line in `active_portfolio` next to the verified `if let Some(t)=parse_retuned`
seam (`consensus_cycle.rs:864`): `all.extend(parse_replay_arms(&cfg.replay_arms, &base));`
Config — one field (`config.rs`, beside `consensus_retuned:252`): `#[config(env="REPLAY_ARMS",
default="")] pub replay_arms: String,`. Family — add `replay_a..e` to the `EXPERIMENTAL` const in
`enrich/mod.rs:339-351` (verified: new arms must be listed or they default to `"core"` and would
tighten the core bar). Tests: `parse_replay_arms("")==[]`; malformed JSON → `[]`; unknown key → `[]`
(deny_unknown_fields); one-bound band → `[]`; a live test proving empty `REPLAY_ARMS` = today's
portfolio by name-set.

**Integration points.** `serde_json` already a dependency (verified: `observed_votes:
serde_json::Value`). Dual-declare `REPLAY_ARMS` in **both** `.env.consensus` and the compose
`environment:` block (verified pattern: `CONSENSUS_RETUNED: ${CONSENSUS_RETUNED:-}`) — one entry,
not five.

**Runtime/cost.** Startup string parse; zero runtime when empty.

**Source.** rethink (Agent B) — serde makes fail-closed structural and collapses 5×2 declarations to
1×2 **+ refined** (add the coherence-invariant guard Agent B omitted but `parse_retuned` enforces).

---

## Item 8 — Autonomy engineering (the user's escalated requirement)

**Before.** "Commit after every phase"; no run-level resume, no `refresh.sh` crash-safety, no
launchd failure visibility, no permission-safe inventory. A reap mid-sweep loses the sweep; a silent
launchd failure = the flywheel silently stops.

**After.** One resumability mechanism shared by build and refresh; a crash-safe refresh; a watchdog
pinned to the always-healthy bot; a permission-safe command inventory.

**(a) Target dispatcher + state.** `[NEW] scripts/flywheel/run.sh` — idempotent, individually-gated
targets, each ≤ one gate cycle:
```bash
#!/bin/bash
set -euo pipefail
STATE="$HOME/polymarket-bot/wt/flywheel/.flywheel-state.json"   # in the worktree → survives a reap
t="${1:?usage: run.sh <target>}"
case "$t" in
  restore)  scripts/flywheel/restore.sh ;;
  span)     PG_CONTAINER=pg-flywheel python3 scripts/flywheel/span_audit.py ;;
  parity)   DATABASE_URL="$SNAP" cargo test -p copy-trading-bot replay_parity -- --ignored --nocapture ;;
  sweep)    DATABASE_URL="$SNAP" scripts/flywheel/sweep.sh ;;      # resumes from wc -l of the JSONL
  ghost)    PG_CONTAINER=pg-flywheel python3 scripts/flywheel/ghost_floor.py ;;
  nulls)    PG_CONTAINER=pg-flywheel python3 scripts/selection_null.py ;;
  deepsharp) DATABASE_URL="$SNAP" cargo test -p copy-trading-bot report_deep_sharp_pass -- --ignored --nocapture ;;
  registry) PG_CONTAINER=pg-flywheel scripts/flywheel/render_registry.py ;;
  report)   scripts/flywheel/write_report.sh ;;
  refresh)  for x in restore span parity deepsharp registry report; do "$0" "$x"; done ;;
esac
printf '{"last_target":"%s","at":"%s"}\n' "$t" "$STAMP" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
```
(`SNAP=postgres://bot:bot@localhost:55497/polymarket`; `STAMP` passed in — `date` is fine in bash,
only workflow *scripts* ban `Date.now`.) The build loop the session runs (and a reap re-runs):
```bash
for t in restore span parity registry sweep ghost slots refresh; do
  grep -q "^$t$" .flywheel-done 2>/dev/null && continue
  scripts/flywheel/run.sh "$t" && echo "$t" >> .flywheel-done && git commit -qam "flywheel: $t" || break
done
```

**(b) `refresh.sh` crash-safety** (the audit-log `flock` precedent from memory):
```bash
#!/bin/bash
set -euo pipefail
REPO="$HOME/polymarket-bot"; cd "$REPO"
NTFY_SRV=$(grep -m1 '^NTFY_SERVER=' .env.consensus | cut -d= -f2); NTFY=$(grep -m1 '^NTFY_TOPIC=' .env.consensus | cut -d= -f2)
notify_fail(){ curl -s -H "Title: flywheel" -d "$1" "${NTFY_SRV%/}/$NTFY" >/dev/null 2>&1 || true; }
exec 9>"$REPO/.flywheel.lock"
flock -n 9 || { echo "$(date '+%F %T') refresh already running — skip" >> "$REPO/.flywheel.log"; exit 0; }
trap 'notify_fail "flywheel refresh FAILED at line $LINENO (see .flywheel.log)"' ERR
avail=$(df -Pk "$REPO" | awk 'NR==2{print $4}')                # a restore needs ~1GB uncompressed
[ "$avail" -gt 2000000 ] || { notify_fail "flywheel: low disk (${avail}KB)"; exit 1; }
scripts/flywheel/run.sh refresh
report="reports/flywheel/$(date +%F).md"                       # write $report.tmp then:
mv "$report.tmp" "$report"                                     # atomic publish
git add REGISTRY.md findings-source.tsv "$report" && git commit -qm "flywheel refresh $(date +%F)" || true
```
`flock -n` on fd 9 = never overlaps the 04:00 backup or a manual run; kernel releases on death → no
stale-lock state. `set -euo pipefail` + `trap ERR` = every failure pushes.

**(c) launchd + watchdog.** `~/Library/LaunchAgents/com.tue.consensus.flywheel.plist` (model =
verified `com.tue.consensus.backup.plist` structure), Sunday 05:00 (after the 04:00 backup), with
`StandardErrorPath`/`StandardOutPath` → `.flywheel.log` (the backup plist has none — the flywheel
adds them). **Watchdog = the always-on bot**, not a second scheduler: a `[NEW] render_flywheel_staleness`
panel in `board.rs` reuses the verified `EARNED_CACHE` TTL pattern (`board.rs:407`, 300s
`OnceLock<Mutex<Option<(Instant,String)>>>`; appended in `render()` near `:1120`) to show
`now − mtime(latest report)` with a red badge > 8 days. A stalled flywheel is visible on the
already-monitored board even if the failure push is missed.
```rust
fn render_flywheel_staleness() -> String {
    let latest = std::fs::read_dir("reports/flywheel").ok()
        .and_then(|d| d.flatten().filter_map(|e| e.metadata().ok()?.modified().ok()).max());
    match latest {
        Some(t) => { let d = t.elapsed().map(|e| e.as_secs()/86_400).unwrap_or(u64::MAX);
            format!("<p class=accrual>flywheel last refresh: <b class={}>{d}d ago</b></p>", if d>8 {"neg"} else {"pos"}) }
        None => "<p class=accrual>flywheel: <b class=neg>no refresh yet</b></p>".into(),
    }
}
```

**(d) Permission-safe inventory.** Every DB read targets `pg-flywheel` (55497) via the restore.
The one landmine — `selection_null.py:41` hardcodes the **prod** container
`polymarket-bot-postgres-1` (verified; the classifier denies it) — is fixed by the one-line patch,
default preserving current behavior:
```python
PG = ["docker","exec","-i", os.environ.get("PG_CONTAINER","polymarket-bot-postgres-1"),
      "psql","-U","bot","-d","polymarket","--csv","-q"]
```
Pre-declare every written path so no step needs interactive approval: `reports/flywheel/`,
`REGISTRY.md`, `findings-source.tsv`, `.flywheel-state.json`, `.flywheel-done`, `.flywheel.lock`,
`.flywheel.log`, `scripts/flywheel/`.

**(e) Silent-by-default.** Push only on a status *transition* to REPLAY-SURVIVOR / promotable /
CERTIFIED-adjacent. Because status is *generated* (Item 4), a transition is a diff of the `status`
column between `git show HEAD:REGISTRY.md` and the new one; a clean no-change refresh writes the
dated report and pushes nothing (Acceptance #5).

**(f) Reap-hotspot map.** With first-fire-on-fills the sweep is checkpointed per config; the
remaining hotspots are `restore` (~1 min, idempotent) and the deep-sharp snapshot scan — each is its
own `run.sh` target with a state entry, so a reap costs ≤ one target.

**Integration points.** `scripts/flywheel/{run.sh,refresh.sh,restore.sh,sweep.sh,write_report.sh}`,
`.flywheel*` in `wt/flywheel/` (worktree survives reap; `wt/` verified gitignored + `.dockerignore`);
`com.tue.consensus.flywheel.plist`; `board.rs` panel; `selection_null.py:41` patch. All write paths
are docs/report/lock → autoupdater skips rebuild.

**Runtime/cost.** Refresh = restore (~1 min) + instruments + one sweep re-score ≈ single-digit
minutes weekly, bounded/O(new data). Watchdog: one `stat` behind a 300s TTL.

**Source.** hybrid — Agent A's concrete `flock`/atomic/`trap`/disk-guard refresh + Agent B's target
dispatcher (one mechanism for build + refresh) and bot-as-watchdog (liveness pinned to the healthy
bot); both agree on the `PG_CONTAINER` patch and pre-declared paths.

---

## Item 9 — Use the archive to its fullest: deep-sharp + thesis as latched registry rows

**Before.** The refresh "re-runs instruments." Deep-sharp certification (`report_deep_sharp_pass`,
`earned.rs:366`; 0/13) and the Tier-B thesis (`deep_edge_thesis.py`; +15.8pp at p=0.29) are not
registry-tracked questions, and re-testing p=0.29 weekly is unguarded peeking that eventually
crosses 0.05 by chance.

**After.** Both become generated registry rows with a **latch on a pre-registered N**: below N the
refresh reports only `N=X/target, accruing` and computes **no** p (nothing to peek at); the instant
N first crosses the target it evaluates **once** via the one gate, stamps `evaluated_at` in
`findings-source.tsv`, and thereafter reports the latched verdict. One pre-registered analysis at one
pre-registered N — the minimal honest group-sequential form — reusing the `unblock`/`target_n` fields
Item 4 already has.

**Implementation.** The `render_registry.py` generator gates evaluation:
```python
def evaluate_or_accrue(f, live):
    if f["evaluated_at"] != "—":                       # latched — report the frozen verdict
        return f["latched_status"], f["latched_lb"], f["latched_p"]
    n = live.get("n_events", 0)
    if n < int(f["target_n"]):                          # below N: compute NO p
        return "POWER-PENDING", None, None              # "N=%d/%s accruing"
    v = verdict_cli(f["id"])                             # first crossing: evaluate ONCE via the gate
    stamp_source(f["id"], evaluated_at=SNAP_DATE, latched=v)   # append-only edit under the refresh flock
    return v.status, v.lb, v.p
```
Wiring is two `run.sh` targets: `deepsharp` runs `report_deep_sharp_pass` against the snapshot (pure
`deep_sharp_pass`/`promotable_deep_sharps` `earned.rs:46/75`, reused unchanged) and lands its
promotable set as generated rows; the `tierB_deep` thesis row carries the latch so
`deep_edge_thesis.py` (fed `--certified` from the deep-sharp pass) runs only at N-crossing. The
per-trader archive — the 400k-fill asset the flywheel exists to exploit — is thus re-scored every
accrual day without inflating false positives. `trader_slice_scores_asof` (`:1526`, verified
`resolved_at < $1`) is the leak-free as-of trust query, reused as-is.

**Integration points.** `report_deep_sharp_pass`/`deep_sharp_pass`/`promotable_deep_sharps`,
`deep_edge_thesis.py`, `trader_slice_scores_asof` — all read-only, all `PG_CONTAINER` after the
Item-8d patch; `findings-source.tsv` gains `target_n`/`evaluated_at`/`latched_*`; the `evaluated_at`
stamp (git-versioned) is the latch's durable audit trail.

**Runtime/cost.** One snapshot scan for the trust frontier per refresh (seconds); below-N rows
compute no null (cheaper than the brief's weekly re-p).

**Source.** rethink (Agent B latch) — reuses an existing field as the stopping rule with zero
alpha-spending machinery; Agent A's "report progress, run at target" is the same idea, less crisply
specified. The generator's write-back to `findings-source.tsv` is safe under the refresh `flock`.

---

## Execution Order (dependency-ordered; gate + commit each; each carries a Verify)

Gate before every commit:
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace` (+ `py_compile` + smoke for touched Python).

1. **Item 1 — infra + guard.** *Verify:* `run.sh restore` prints a snapshot date; `flywheel_db_guard`
   exits 3 when `DATABASE_URL` lacks `:55497`; `span_audit.py` reproduces the substrate table.
2. **Item 4 (source + verdict_cli + generator, migrate ~25 findings).** *Verify:* `render_registry.py`
   emits a `REGISTRY.md` whose `favorite`/`elite_fresh_fav` numbers match the live scoreboard; board
   parser tallies statuses; a re-run is a byte-identical diff.
3. **Item 2 — as-of loader + first-fire.** *Verify:* unit test that first-fire on a synthetic 3-fill
   market picks the earliest firing window; `load_live_era_buy_fills` returns only `ts≥era_start`.
4. **Item 5 — `insert_replay_signals` + sweep harness** (grid stanza committed to `findings-source.tsv`
   **before** this scoring commit). *Verify:* insert satisfies all NOT NULL columns; the reused
   scoreboard returns one row per config; `assert_throwaway` aborts against a non-55497 URL; JSONL
   resume skips `wc -l` configs.
5. **Item 3 — parity ledger + harness.** *Verify:* `replay_parity` passes the count-column subset on
   `favorite`/`elite_fresh_fav`; coverage ≥0.98; an injected count perturbation trips a STOP; a
   `distinct_days` difference does **not**. **Gate: if path-(b) coverage/count parity fails and can't
   be explained, STOP the sweep phases and report** (honesty hard-stop).
6. **Item 6 — event-level ghost + `selection_null` reuse + `PG_CONTAINER` patch.** *Verify:*
   `selection_null.py --calibrate` still passes; ghost run on a null (shuffled) world yields
   deflated ≈ 0; the patch's default still targets prod (behavior-preserving).
7. **Item 7 — serde slots.** *Verify:* the five fail-closed unit tests; the live test proving empty
   `REPLAY_ARMS` = today's portfolio byte-for-byte; `replay_a..e` in `family()`.
8. **Item 8 — dispatcher + refresh + plist + watchdog.** *Verify:* two consecutive `refresh.sh` runs
   → second is a clean no-change delta, pushes nothing; `flock` blocks a concurrent run; board shows
   the staleness panel; kill mid-sweep then re-run → resumes from the JSONL.
9. **Item 9 — deep-sharp + thesis latch.** *Verify:* a below-target row reports `accruing` with no p;
   a synthetic N-crossing evaluates once and stamps `evaluated_at`; a re-run reports the latched
   verdict, not a fresh p.
10. **Consolidate + ship.** Full gate; live-verify on the 55496 migrated throwaway (parity, slot
    registration, refresh E2E). `merge --no-ff` → autoupdater deploys local `main`. *Verify:*
    container healthy; portfolio unchanged (empty slots); board shows the registry panel; `strict`
    byte-for-byte; nothing promoted. Write `REPORT-ARCHIVE-FLYWHEEL.md`.

---

## RUN AUTONOMY — checkpoint/resume protocol for the implementing session

- **Worktree + branch** (survives a reap; `wt/` gitignored + `.dockerignore`). All state files live
  in `wt/flywheel/`: `.flywheel-done` (completed build targets, one per line), `.flywheel-state.json`
  (`{last_target, at}`), and the per-run `reports/flywheel/*.jsonl` sweep/ghost checkpoints.
- **Per-target commits** (finer than per-phase): the build loop commits after each `run.sh` target
  and appends to `.flywheel-done`; re-entry skips done targets. A reap loses ≤ one target.
- **Reap-recovery instructions** (put these verbatim in the resume prompt): (1) `cd wt/flywheel`;
  (2) re-run the build loop — it skips `.flywheel-done` targets; (3) for a half-done **sweep**, resume
  is automatic (`sweep.sh` reads `wc -l reports/flywheel/sweep-<snap>.jsonl` and skips those configs);
  (4) for a half-done **ghost**, resume at the next shuffle (JSONL line count); (5) re-run
  `run.sh restore` freely — it is idempotent (`docker rm -f` first); (6) verify the pre-registered
  `grid_sha` in `.flywheel-state.json` matches HEAD's `findings-source.tsv` grid stanza — if it was
  edited, the pre-registration was violated → STOP.
- **Reap hotspots** and their ≤5-min restart: `restore` (idempotent re-run); `sweep` book-load+score
  (per-config JSONL); `ghost` (per-shuffle JSONL); `deepsharp`/`nulls` (≤5 idempotent items).
- **Permission-safe command inventory** (nothing needs interactive approval): `docker run/rm/exec`
  on `pg-flywheel` (55497) and the 55496 migrated throwaway; `gunzip`; `cargo test … -- --ignored`;
  `python3 scripts/flywheel/*` and the patched `selection_null.py` (all `PG_CONTAINER`); `git`
  add/commit/merge in the worktree; writes confined to the pre-declared paths. **Never** `docker exec
  polymarket-bot-postgres-1 psql` (prod — classifier-denied) and **never** run the sweep/parity
  harness with `DATABASE_URL` unset or pointing off :55497 (`assert_throwaway` aborts).
- **Refresh crash-safety** (the standing motor after the run merges): `flock -n` fd 9 (no overlap,
  no stale lock), `set -euo pipefail`, `trap ERR → notify_fail`, disk guard (>2 GB), atomic `mv` of
  the report, docs-only commit (skips rebuild). launchd Sunday 05:00 with `StandardError/OutPath` →
  `.flywheel.log`; the board staleness panel is the backstop if a push is missed.

---

## Existing Infrastructure Leveraged (reused verbatim unless noted)

| Capability | Location (verified) | Use |
|---|---|---|
| Pure scorer | `scanner/consensus.rs:325` `score_market` | replay + sweep score through it |
| Single book builder | `consensus_cycle.rs:522` `books_from_window_votes` (pub(crate)) | both replay paths assemble here |
| The one gate | `promotion.rs:168` `promotion_verdict`; defaults `min_events:30/margin:0.03/alpha:0.05`; `SELECTION_NULL_P_BAR:0.01` (`:97`) | sweep passes `n_strategies=GRID_SIZE`; verdict_cli reuses |
| Reused baseline | `consensus.rs:607` `consensus_scoreboard_by_strategy` (`_blind` band-blind, event-cluster, `first_detected_at` day axis) | parity + sweep judged by it, unchanged |
| As-of template | `consensus.rs:1526` `trader_slice_scores_asof` (`resolved_at<$1`) | Item 2 loader + Item 9 trust query |
| Archive loader | `consensus.rs:1360` `load_buy_fills_since` | template for `load_live_era_buy_fills` |
| Selection null | `scripts/selection_null.py` (`clustered_surplus:95`,`null_pvalue:106`,`--calibrate:147`,`N_PERM=2000`,`SEED=20260702`) | rule (b) + ghost engine; **patch `:41`→`PG_CONTAINER`** |
| Atom source | `consensus_cycle.rs:920-928` `atom_log` (7 fields, epoch-sec `ts`, pre-gate, no quality/trust) | parity path (a), frozen rank |
| Slot pattern | `consensus.rs:812` `parse_retuned`/`:831` `retuned_arm`/`consensus_cycle.rs:864` registration seam | generalize to `parse_replay_arms` |
| Config passthrough | `config.rs:252/253` `#[config(env="CONSENSUS_RETUNED",default="")]` | `REPLAY_ARMS` field; dual-declare |
| Bonferroni family | `enrich/mod.rs:338` `family()` (EXPERIMENTAL const) | add `replay_a..e`; sweep uses own K |
| Board TTL panel | `board.rs:407` `EARNED_CACHE`/`:428` `render_earned`/`:1120` render | registry + staleness panels |
| Backup / autoupdate | `consensus-backup.sh` (04:00,gz,keep-14); `consensus-autoupdate.sh:40` `CODE_RE` (docs skip rebuild) | restore source; docs-only commits |
| Deep-sharp / thesis | `earned.rs:366/46/75`; `deep_edge_thesis.py` | Item 9 latched rows |
| launchd precedent | `com.tue.consensus.backup.plist` (verified structure) | flywheel plist |
| UNNEST insert | `consensus.rs:1267/1290/1294` `insert_trader_fills` | template for `insert_replay_signals` |

---

## Open Questions (each resolved during implementation, not before)

1. **First-fire vs a coarse peak pre-filter.** Item 2 mandates first-fire for effect sizes; whether a
   cheap peak pre-filter is worth adding to skip never-firing configs is decided in Item 5 once the
   measured sweep wall-clock is known (if <2 min, skip the pre-filter). *Resolved by the Item-5 timing.*
2. **Throwaway assertion mechanism.** `assert_throwaway` uses the `:55497` URL check; if a future
   refresh needs forward + replay in one container, switch to a sentinel-table marker (prod gets a
   `flywheel_prod_marker` table once; the harness refuses if present). *Resolved when/if a second
   container is introduced.*
3. **`distinct_days` for freshness-free replay.** The day axis is the slug event-date; crypto has no
   slug date (event-date axis unusable) so crypto configs are live-era `ts`-day only. Confirm the
   per-sport tag during the sweep. *Resolved by `span_audit.py` output.*
4. **Ghost vs Bonferroni double-penalty.** Both deflate; this is intentionally conservative. If the
   sweep yields zero survivors purely from double-penalty, relax by dropping the ghost for configs
   already Bonferroni-dead. *Resolved by the first sweep's survivor count (expected few/zero at 14
   event-days — an honest outcome, not a bug).*
5. **Generator write-back concurrency.** The Item-9 latch stamps `findings-source.tsv`; under the
   refresh `flock` this is single-writer. If a manual `render_registry.py` is ever run outside the
   lock, it must take the same `flock`. *Resolved by routing all registry writes through `run.sh registry`.*

---

## Rejected Approaches (with the verification finding that killed each)

- **❌ Atom-replay (`observed_votes`) as the SWEEP substrate** (Agent B's central reframe). Verified
  `upsert_consensus_signal` sets `observed_votes = EXCLUDED.observed_votes` on conflict
  (`consensus.rs:253`) — the atoms are a **last-fire, lossy** snapshot: earlier windows are gone, so
  they cannot support as-of cuts or a first-fire decision point, and their entry is the drifted
  late-book mean, not at-fire. Kept atoms **only** for parity path (a) (frozen rank, which
  `trader_fills` lacks). Substrate for the sweep = `trader_fills`.
- **❌ Peak `max(ts)` decision point** (Agent A). Verified the scoreboard judges on at-fire
  `initial_mean_price` and the post-fire drift is ~+1.2¢ (`consensus.rs:613`) — peak entry exceeds
  Agent A's own ±0.5pp parity tolerance. Replaced by first-fire.
- **❌ Scalar parity tolerance / "reproduce the SAME record."** The gate's judged column
  (`initial_mean_price`, at-fire) is stored in **neither** substrate (`observed_votes` overwritten;
  `trader_fills` rankless) — a byte-match is structurally impossible. Replaced by a per-column ledger
  + coverage check; parity claimed on count-based strategies, live era.
- **❌ Hand-maintained registry TSV** (Agent A). It re-introduces the exact drift the brief names
  ("N=38 unexamined"). Replaced by a generated view whose numbers are always the current snapshot's.
- **❌ Deriving status in Python** (a naive read of Agent B). Would be a second gate. Routed through
  a Rust `verdict_cli` wrapping `promotion_verdict` — the one gate stays the only promoter.
- **❌ Replacing the ghost floor with a per-winner selection null alone** (Agent B). Bonferroni
  corrects the threshold, not the max-of-K effect-size null; dropping the event-level shuffled-outcome
  floor loses a doctrine deflator. Kept both.
- **❌ Fill-level outcome permutation for the ghost.** Destroys within-event correlation → clustered
  SE too small → certifies noise (the `market_resid` class). Event-level only.
- **❌ Hand-rolled `key=value` slot parser across 5 env vars** (Agent A). Serde `deny_unknown_fields`
  makes fail-closed structural and collapses 5×2 declarations to 1×2.
- **❌ Insert-and-`TRUNCATE` without a throwaway guard** (latent in Agent A). A `#[ignore]`d test that
  reads `$DATABASE_URL` and `TRUNCATE`s `consensus_signals` would **destroy prod** if misconfigured
  (`honest_pnl_by_strategy` and the scoreboard both read that table — verified). Mandated
  `assert_throwaway` + `_guard.sh` + `run.sh`-only invocation.
- **❌ (from the brief, retained) ** promoting on replay evidence; a second scorer/gate/baseline; an
  unbounded/adaptive search; trusting backfill-era `ts`; a per-candidate schema; editing applied
  migrations (next free is **037**, not 036 — `036_initial_atfire_shape.sql` already exists — but the
  flywheel needs **no** migration); touching prod postgres; concurrent write-agents; real money.
