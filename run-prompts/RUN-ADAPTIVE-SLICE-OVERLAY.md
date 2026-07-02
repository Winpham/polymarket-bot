# Long Autonomous Run — Adaptive Slice Overlay + Market Breadth: cuts as a STRATEGY, not surgery

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust; deploy branch = `main`, auto-deploys ~5 min after merge).
Companion reading (house style + ground truth you must not relitigate): `DECISIONS.md`
(D1–D13), `REFINED-STRATEGY.md`, `reports/entries/2026-07-02-10-slice-study.md`,
`reports/slice_study.json`, `scripts/slice_study.py`, `scripts/selection_null.py`,
`run-prompts/README.md`.

---

## 0. The one-sentence mission

Turn the slice study's frozen PRIORITIZE/NEUTRAL/DODGE map into a **living, adaptive
overlay** — a versioned map state that re-reads itself at pre-registered checkpoints with
hysteresis (so verdicts can flip in BOTH directions as tournaments rotate and data
accrues), a shadow "mapped" variant of the fleet stream judged on **paired lift over its
parent**, and a checkpoint runner that also executes the two forward reads already
pre-registered in entry 10 — because a cut that can't un-cut itself when circumstances
change is not a strategy, it's a scar.

The owner's directive (2026-07-02, binding intent): **no permanent cuts.** The DODGE
cells might not be unprofitable forever (the residue is tournament-mix-dependent). Encode
the map as one of our adaptive approaches: it applies itself where the evidence binds
today, keeps measuring what it excludes, and rehabilitates a cell the moment the evidence
stops binding — always at the bar, never by vibes, in either direction.

Second owner directive (same date, same weight): **the system must not live and die with
the World Cup.** The record is ~89% WC soccer + Wimbledon; both end within weeks. This
run also audits MARKET BREADTH — where consensus volume actually comes from as the
calendar rotates, whether anything in our own config/mechanics structurally blocks
non-WC markets, and what the honest post-WC frequency forecast is. Breadth is the
sanctioned volume lever ("more MARKETS, not weaker GATES"); this phase measures it —
it does NOT loosen a single gate to manufacture it.

---

## Ground truth you must NOT relitigate (established; evidence in D1–D13 + entry 10)

- Gate judges the **AT-FIRE entry** (D6); event-cluster by `COALESCE(event_slug,
  condition_id)` ALWAYS; promotion rule D7 (gate LB > 3% ∧ selection-null p ≤ 0.01 ∧ ≥2
  regimes positive) is binding and unchanged by this run.
- **The slice map (entry 10, pinned in `reports/slice_study.json`):** 83 cells, BH-FDR
  q=0.10 → 45 survive. PRIORITIZE mass = favorite's favorite-band slices at 10–20 ev/day
  (horizon<6h, opp≥1, UTC 00–08, moneylines, band .80–.90). **DODGE (mirror test):
  strict-tennis −23.7% [−37.3, −8.7] N=110 and strict-moneyline-all-bands −13.7%
  [−25.8, −2.5] N=179 — verified mechanism = the NON-favorite residue (tennis band 1: 0%
  hit on 26 events). `favorite`/`elite_fresh_fav` contain NO DODGE cells** (so a "mapped
  favorite" is byte-identical to favorite today — build nothing there yet).
- strict/prop (+56.7%) is 100% World Cup → EXPIRING, not a target. Volume verdict: no
  volume-add clears the bar today; the winners are the right granularity at current N.
- **Nominations already pre-registered (entry 10, do not re-derive):** forward reads of
  (1) favorite∩opp≥1 (capital-efficiency; the opp≥1 − opp=0 DIFFERENCE must be > 0 at
  95%, not just the cell clearing) and (2) favorite∩tennis — first read at **30 NEW
  events fired after 2026-07-02 16:45 UTC**, then every +15, D7-equivalent bars on
  forward data only.
- **Migration 036** captures at-fire σ/recency/liquidity/best-rank on every NEW signal
  (confirmed live). `slice_study.py` auto-uncaps a drift dimension at ≥95% at-fire
  coverage — the map inherits this for free; do not rebuild it.
- Costs: measured haircut **0.5¢** median + 2% fee. Flat-SHARES sizing. `resolved_at` is
  processing time. Blind-tail loses; consensus fully formed at fire; market_resid OFF
  (refuted); loosening gates to buy frequency is the known failure mode.
- `strict` is an INSTRUMENT: it must keep firing on everything (including DODGE cells)
  forever — the overlay is a VIEW over the fleet record, never a mutation of it.

## Non-negotiable guardrails

1. **Reversibility.** Isolated git worktree off `main`, fresh branch, tag the pre-run
   state. Other Claude sessions run in parallel — check `git worktree list` + claims,
   keep your file slice non-overlapping, smallest-possible additive changes to shared
   files (DECISIONS.md is append-only at the end).
2. **Gate every commit:** `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check
   --all && cargo clippy --workspace --all-targets && cargo test --workspace`; Python =
   `python3 -m py_compile` + self-test/smoke on synthetic fixtures. **Re-run the FULL
   gate on main AFTER the merge lands** (main moves under you; the auto-deployer ships
   whatever is there).
3. **Applied migrations are IMMUTABLE.** This run needs at most ONE migration (the map
   state table); next free number only (037 at the time of writing — re-check), additive,
   append-only. If you can honestly avoid it (artifact-file-based state), prefer zero.
4. **Paper-only, additive-and-OFF, belief-blind.** No real money, no order placement, no
   alerting changes, no auto-promotion. The overlay arm is VIRTUAL first (see Phase 2) —
   it costs one hypothesis slot in the experimental-family bookkeeping; budget: **1 arm
   total** (a second only if the run proves the first can't answer the question).
5. **Deploys only via `scripts/consensus-autoupdate.sh`**; env/behavior flips on the live
   bot require Tue's explicit go — propose, don't apply.
6. Cost-zero (Max only, no ANTHROPIC_API_KEY, no child claude spawns).

---

## Pre-registration (write into the report BEFORE computing anything)

### The map state machine (frozen before any data is read)

Each cell carries one of three states; transitions happen ONLY at checkpoints:

- **→ DODGE (enter):** realizable-ROI bootstrap UB < 0 at N ≥ 20 events on the
  evaluation window ∧ K2-stable ∧ at-fire-true definition (†-capped dims can only
  nominate). Same rule as entry 10.
- **DODGE → NEUTRAL (rehabilitate):** at the checkpoint, the entry criterion FAILS on
  the **recent window** (last 14 days or last 100 cell-events, whichever is larger) with
  N_recent ≥ 20 — i.e. fresh evidence no longer supports the dodge. Silence is NOT
  rehabilitation: if N_recent < 20 the cell KEEPS its state and is marked **STALE**
  (age shown; a stale DODGE still binds but is flagged for the owner).
- **→ PRIORITIZE (enter):** the entry-10 rule verbatim (FDR-surviving null ∧ realizable
  LB > 0 ∧ N ≥ 20 ∧ ≥2 splits positive ∧ freq_recent ≥ 1/day ∧ K2-stable ∧
  at-fire-true). **PRIORITIZE → NEUTRAL:** any of the conditions fails at a checkpoint
  with N_recent ≥ 20 (same anti-silence rule).
- **Hysteresis / anti-thrash:** a cell that flips at two consecutive checkpoints is
  frozen at NEUTRAL and flagged THRASH — noise-driven cells must not steer anything
  (calibration discipline: plateau fine, thrash not). Report thrash count every
  checkpoint.
- **Dual-window read:** every checkpoint computes whole-record AND recent-window
  metrics; ENTRY uses the whole record (power), EXIT/rehab uses the recent window
  (adaptivity). This asymmetry is deliberate and frozen here.

### Checkpoint cadence (frozen)

Every **+7 days or +300 new fleet events** (whichever first), plus one forced checkpoint
**after the World Cup final**. Each checkpoint: recompute the full slice family with the
`slice_study.py` machinery (same seed policy: seed = checkpoint date), apply the state
machine, append a new **map version** (never overwrite), log every transition with its
evidence. Reads happen at checkpoints ONLY — no peeking between (optional-stopping
discipline, D9).

### The overlay arm and its judgment (frozen)

- **`fleet_mapped` (VIRTUAL, replay-scored):** the strict stream MINUS cells currently
  DODGE in the map version that was **effective at each signal's fire time** (no
  retroactive re-mapping — a signal is judged by the map that existed when it fired;
  map v1 = entry 10's verdicts, effective 2026-07-02).
- **Primary statistic — paired lift over parent:** at each checkpoint, on FORWARD rows
  only (fired after this run's deploy), report (a) surplus(fleet_mapped) −
  surplus(strict) with an event-level paired bootstrap CI, and (b) the **counterfactual
  P&L of the excluded picks** (what the dodged cells actually did — the money the map
  saved or cost, the direct test of the owner's "might not always be unprofitable").
- **Success bar (pre-registered):** the overlay is WORKING iff excluded-pick P&L is
  negative and the paired lift is positive at 95% on ≥ 30 forward excluded events;
  it is REFUTED for the current regime iff excluded-pick P&L is positive at 95% on the
  same floor (→ the map rehabilitates those cells at the next checkpoint by its own
  rules — that outcome is a SUCCESS of the adaptive design, report it as such).
- **Retro-replay of fleet_mapped on pre-run data is allowed ONLY as a descriptive
  counterfactual** (it's circular — the map was built on that data); it NEVER feeds the
  gate. The gate reads forward-fired rows only.
- The two entry-10 nominations are evaluated by the same checkpoint runner at their own
  pre-registered points (N=30 then +15), with their own bars, on forward data only.

### Kill criteria (binding)

- K1: if forward excluded-event accrual is too slow to ever reach the 30-event floor
  within ~3 weeks (measure it at Phase 2 end), say so and define the accrual trigger —
  do NOT lower the floor.
- K2: if the checkpoint machinery shows >20% of cells flipping between consecutive
  synthetic-stability runs (self-test), the state machine is noise-driven — widen floors,
  do not ship an overlay that thrashes.
- K3: nothing from this run changes live behavior; the Rust surface (a real silent
  StrategyDef arm, board panel, alert annotation) is EARNED — build it only after
  `fleet_mapped` clears its success bar at a real checkpoint, in a LATER run. If tempted
  to build it now anyway: don't; write the trigger instead.
- K4: if the two nominations' forward reads are due (N≥30 reached) during this run,
  execute them and report honestly — including "confirmation FAILED" if it did.

---

## Phases (each ends gate-green + committed)

### Phase 0 — Setup & reproduction (~30 min)
Worktree + branch + tag. Read the companion docs. Re-run `slice_study.py --selftest`
(must PASS) and the live study; confirm the pinned entry-10 verdicts reproduce within
accrual noise (DODGE cells still DODGE, no UNSTABLE). Print forward-accrual denominators:
events/day into the DODGE cells since 2026-07-02 16:45 UTC (the K1 input). If the map
does NOT reproduce (e.g. a DODGE cell already flipped on 4 more days of data), STOP and
report — that is itself a first-order finding about map stability, and the run pivots to
diagnosing it before building anything.

### Phase 1 — The map state: versioned, append-only, auditable
`scripts/map_state.py` (house pattern: stdlib+numpy, docker-exec psql or artifact files,
seeded, self-testing). Storage decision is yours (justify it): migration 037 table
`slice_map_state` (append-only versions) OR versioned JSON artifacts under
`reports/map/` committed to git — prefer the LIGHTER one that still gives: immutable
history, effective-from timestamps, per-transition evidence, and a `current_map(at_ts)`
lookup. Seed map v1 from `reports/slice_study.json` (entry-10 verdicts, effective
2026-07-02T16:45Z). **Self-test (mandatory):** synthetic checkpoint sequences must show
(a) a cell entering DODGE on injected reliable loss, (b) rehabilitating when the recent
window flips positive, (c) NOT rehabilitating on data silence (STALE instead), (d) the
THRASH freeze firing on alternating evidence, (e) zero transitions on stable-noise
fixtures (the K2 bar).

### Phase 2 — The checkpoint runner + virtual overlay
`scripts/map_checkpoint.py`: one command that (1) recomputes the slice family (reusing
`slice_study.py` as a library — keep its CLI byte-identical), (2) applies the state
machine → new map version + transition log, (3) scores `fleet_mapped` vs `strict`
(paired lift + excluded-pick counterfactual, forward rows only, at-fire entry,
event-clustered, measured costs), (4) runs any DUE nomination reads (K4), (5) emits a
single honest verdict block (map version, transitions + evidence, lift, excluded P&L,
nomination outcomes, STALE/THRASH flags, next checkpoint trigger). Self-test: an
end-to-end synthetic run where the injected world CHANGES between checkpoints (a losing
cell turns winning) — the runner must dodge it in v2 and rehabilitate it in v3, and the
excluded-counterfactual must flip sign accordingly. Run it live once (checkpoint #1 =
today): expect mostly "no transitions, forward-N too small, nominations not yet due" —
print exactly that with the real numbers; K1 verdict on accrual pace.

### Phase 2.5 — Market-breadth audit (read-only, measurement-first)
The question: **when the WC and Wimbledon end, where does consensus volume come from —
and are we structurally blind to any of it?** All read-only SQL + config reading; no
behavior change. Answer, with numbers:
1. **Supply side:** per-category (soccer/tennis/mlb/cs2+esports/crypto/politics/other)
   over the whole record: tracked-sharp fill volume (`trader_fills`), blind-event counts,
   and consensus fires per strategy — the funnel from "sharps bet there" to "consensus
   forms there". Where sharps bet but consensus never forms, say WHY (backers spread
   across outcomes? σ gate? <3 backers? opposition?) — measured, not guessed.
2. **Rotation mechanics:** the leaderboard tracker follows top-N per {DAY,WEEK,MONTH,
   ALL}. Quantify churn: how fast did the tracked set rotate around past tournament
   boundaries in the record? Does the union-of-periods design auto-rotate to MLB/NFL/
   politics sharps when the WC cohort goes quiet, and on what lag (the drop-grace)?
   That lag IS the post-tournament dead zone — measure it.
3. **Structural blockers:** audit config + code paths for anything that hard-limits
   breadth: `is_sports`/`sports_mode` filters per strategy, category assumptions in
   `sport_bucket`, slug/regime parsing that lumps everything non-sports into "other",
   crypto's known no-fire pattern (sharps are sports-concentrated — confirm it still
   holds at TRACK_DEPTH=200). Anything found = documented finding + smallest-additive
   fix PROPOSED (not applied unless it's a pure instrument/doc fix).
4. **Forecast:** given 1–3, the honest post-WC events/day forecast per strategy (with
   the WC rows excluded as the proxy), and which upcoming calendar blocks (MLB daily,
   NFL preseason→season, US politics into the cycle, esports majors) plausibly replace
   the volume. Output = a breadth table + the single highest-leverage breadth action
   (e.g. "extend the tracked union with a MONTH-period politics/esports slice" or
   "nothing — rotation self-heals in X days") for Tue to decide on. If the answer is
   "the engine will go near-silent for ~N weeks post-WC", say exactly that.

### Phase 3 — Study what the overlay would have done, write the map's operating doc
Descriptive (gate-exempt, labeled as such): retro-replay fleet_mapped over the whole
record (the circular counterfactual, clearly marked), per-regime; sensitivity of the
paired lift to the recent-window length (7/14/21d — report, do NOT tune-and-pick: the
pre-registered 14d stands unless the sensitivity table shows a qualitative break, in
which case report the break and keep 14d anyway, noting it for the next pre-registration
cycle). Write `reports/entries/NN-adaptive-overlay.md`: the state machine, map v1, the
first checkpoint's honest read, accrual math (when each answer arrives), and the exact
trigger + design sketch for the EARNED Rust surface (K3). Update REFINED-STRATEGY.md
only where this run's machinery sharpens the instruments section (cite the entry);
DECISIONS.md += D14 (the adaptive-overlay decision: why virtual-first, why the
asymmetric entry/exit windows, why hysteresis, what would earn the Rust arm).

### Phase 4 — Ship & verify
Merge `--no-ff` to main; **re-run the full gate on post-merge main**; confirm the
auto-deploy stays healthy (if you shipped no Rust/migration change, verify the updater
log says "no code change — skipped rebuild"; if you shipped migration 037, verify it
applied and the container is clean). Final report to Tue: map v1 + state machine in one
screen, checkpoint-1 verdict, the breadth table + post-WC frequency forecast + the one
breadth action proposed for his decision, when the next answers arrive
(dates/event-counts), what was deliberately NOT built, exact rollback.

---

## Rejected approaches (do not build)

- **Permanently editing strategy definitions or filtering `strict`** — the owner's
  directive and the instrument principle both forbid it. The map is a view.
- **A live Rust arm / alert filtering / board panel NOW** — unearned (K3). Virtual-first
  is the shadow-first house pattern (deep-edge precedent).
- **Re-fitting cell thresholds, window lengths, or FDR q at checkpoints** — the
  procedure is frozen; only the DATA grows. Adaptive means re-reading, not re-tuning.
- **Retro-scoring the overlay into the gate** — circular; descriptive only.
- **Per-cell bespoke rules** ("tennis needs a special window") — one state machine for
  all cells or the multiplicity guarantees die.
- **More than 1 new hypothesis slot** — fleet_mapped is the experiment; the nominations
  already have theirs from entry 10.

## Acceptance

Gate-green commits; `map_state.py` + `map_checkpoint.py` with PASSING self-tests
(including the world-changes-between-checkpoints end-to-end and the K2 stability bar);
map v1 seeded from entry 10 with immutable version history; checkpoint #1 executed live
with an honest (probably mostly-null) verdict incl. K1 accrual math; nominations wired
into the runner (executed if due); the market-breadth audit (funnel table, rotation-lag
measurement, structural-blocker findings, post-WC forecast, ONE proposed breadth action
— proposed, not applied); entry NN + D14 + REFINED-STRATEGY instrument note;
merged + post-merge re-gated; live behavior unchanged; paper-only. The output is a
LIVING MAP with a paper shadow — cuts that apply themselves only while the evidence
holds, measure what they exclude, and reverse themselves at the bar when the world
changes — not a scalpel taken to the fleet.
