# 11 — Adaptive slice overlay + market breadth: cuts as a strategy, not surgery

**Date:** 2026-07-02 · **Branch:** `feat/adaptive-overlay` (worktree off `main` 4d8f9c9,
tag `pre-adaptive-overlay-20260702`) · **Instruments:** `scripts/map_state.py`,
`scripts/map_checkpoint.py` · **Storage:** `reports/map/` (versioned JSON, no migration)
· **Paper-only, virtual, belief-blind — nothing changes live behavior (K3).**

Mission: turn the entry-10 slice map from a frozen PRIORITIZE/NEUTRAL/DODGE table into a
**living, adaptive overlay** — a versioned map state that re-reads itself at pre-registered
checkpoints with hysteresis (verdicts flip in BOTH directions as tournaments rotate and
data accrues), a shadow "mapped" variant of the fleet judged on **paired lift over its
parent**, and a checkpoint runner that also executes the two entry-10 forward nominations.
A cut that can't un-cut itself when the world changes is a scar, not a strategy.

Second mission (owner directive, same weight): **the system must not live and die with the
World Cup.** Audit market BREADTH — where consensus volume comes from as the calendar
rotates, whether anything structurally blocks non-WC markets, and the honest post-WC
frequency forecast. Breadth is measured here, **not manufactured** — no gate is loosened.

---

## PRE-REGISTRATION (frozen before any data was read)

### The map state machine

Each cell carries `state ∈ {DODGE, NEUTRAL, PRIORITIZE}` (+ flags STALE, THRASH).
Transitions happen ONLY at checkpoints. The entry/exit **window asymmetry is deliberate**:
enter on power (whole record), leave on adaptivity (recent window).

- **→ DODGE (enter, WHOLE record):** realizable-ROI bootstrap UB < 0 ∧ N ≥ 20 ∧ K2-stable
  ∧ at-fire-true. (Identical to entry 10.)
- **→ PRIORITIZE (enter, WHOLE record):** the entry-10 rule verbatim (FDR-surviving null ∧
  realizable-ROI LB > 0 ∧ N ≥ 20 ∧ ≥2 splits positive ∧ freq_recent ≥ 1/day ∧ K2-stable ∧
  at-fire-true).
- **DODGE → NEUTRAL (rehab, RECENT window):** the DODGE entry criterion FAILS on the recent
  window (max(last 14 UTC days, span of the last 100 population events)) with N_recent ≥ 20.
  **Silence is not rehabilitation:** N_recent < 20 ⇒ state HELD, flagged **STALE** (age
  shown; a stale DODGE still binds but is surfaced to the owner).
- **PRIORITIZE → NEUTRAL:** the PRIORITIZE entry criterion fails on the recent window,
  N_recent ≥ 20 (same anti-silence STALE rule).
- **Hysteresis / anti-thrash:** a cell that flips at two consecutive checkpoints is frozen
  at NEUTRAL and flagged **THRASH** (sticky) — noise-driven cells must not steer anything.
- **Drift dims** (σ, backer comp, freshness, liquidity — overwritten on upsert) are
  `at_fire_true = false` ⇒ they may nominate, never bind (the entry-10 †-cap, inherited).

### Checkpoint cadence

Every **+7 days or +300 new fleet events** (whichever first), plus one forced checkpoint
**after the World Cup final**. Each checkpoint recomputes the whole `slice_study.py` family
(same seed policy), applies the state machine, appends a **new immutable map version**
(never overwrite), logs every transition with its evidence. Reads at checkpoints ONLY — no
peeking between (optional-stopping discipline, D9). **The procedure is frozen; only the
data grows. Adaptive means re-reading, never re-tuning** (no threshold / window / FDR-q
refit at checkpoints — rejected).

### The overlay arm and its judgment (1 hypothesis slot — the only new experiment)

- **`fleet_mapped` (VIRTUAL, replay-scored):** the strict stream MINUS cells currently
  DODGE in the map version that was **effective at each signal's fire time** (no retroactive
  re-mapping — a signal is judged by the map that existed when it fired; map v1 effective
  2026-07-02T16:45Z).
- **Primary statistic — paired lift over parent:** on FORWARD rows only, (a) surplus(mapped)
  − surplus(strict) with an event-level paired bootstrap CI, and (b) the **counterfactual
  P&L of the excluded picks** (the direct test of "the DODGE cells might not be unprofitable
  forever").
- **Success bar (pre-registered):** WORKING iff excluded-pick P&L negative ∧ paired lift
  positive at 95% on ≥ 30 forward excluded events. REFUTED-for-regime iff excluded-pick P&L
  positive at 95% on the same floor (→ the map rehabilitates those cells at the next
  checkpoint by its own rules — a SUCCESS of the adaptive design, reported as such).
- Retro-replay on pre-run data is **descriptive only** (circular — the map was built on it);
  it NEVER feeds the gate. The gate reads forward-fired rows only.

### Kill criteria (binding)

- **K1:** if forward excluded accrual can't reach the 30-event floor in ~3 weeks, say so and
  define the accrual trigger — do NOT lower the floor.
- **K2:** if the checkpoint machinery flips >20% of cells between stable-noise runs, the
  state machine is noise-driven — widen floors, don't ship a thrashing overlay.
- **K3:** nothing here changes live behavior; the Rust surface (silent StrategyDef arm,
  board panel, alert annotation) is EARNED — built only after `fleet_mapped` clears its bar
  at a real checkpoint, in a LATER run.
- **K4:** if a nomination's forward read is due (N≥30) during this run, execute and report
  honestly — including "confirmation FAILED."

---

## RESULTS

### Phase 0 — reproduction (map is stable)

`slice_study.py --selftest` PASS. Live study reproduces the pinned entry-10 verdicts within
accrual noise: **both DODGE cells still DODGE** — strict/tennis −23.7% [−37.4, −8.2] N=110,
strict/moneyline −13.7% [−25.0, −2.0] N=179 — **0 UNSTABLE**, PRIORITIZE mass intact (family
grew 83→48 survivors from more resolved rows). No DODGE cell flipped ⇒ no Phase-0 pivot.

**K1 accrual math:** historical strict-DODGE (excluded-cell) accrual = **44.8
excluded-events/day** (moneyline 179 ∪ tennis 110 = 179 events over 4 days; tennis ⊂
moneyline). Forward past the 16:45Z cutoff = **0 events** — purely because the DB's latest
fire (17:21Z) is only ~36 min past the cutoff. So the 30-forward-excluded floor is reached
in **~1 day of live firing**, not weeks: the binding constraint is elapsed wall-clock since
deploy, not rate. (WC-inflated; post-WC lower, but tennis alone ~27/day clears 30 in ~1.1d
while Wimbledon runs.)

### Phase 1 — the map state (versioned, append-only, auditable)

`scripts/map_state.py`. **Storage decision:** versioned JSON under `reports/map/`
(`v001.json` + `manifest.json` with sha256), NOT a migration — a map version is a
git-tracked artifact, immutable by a no-overwrite guard, with effective-from lookup
(`current_map(at_ts)`) and per-transition evidence. Honors guardrail 3 (prefer zero
migrations). **Self-test PASS (7/7):** enter DODGE on injected loss; rehab on recent flip;
STALE (not rehab) on silence; THRASH freeze on alternation; THRASH sticky; 0 transitions on
stable-noise (the K2 bar); PRIORITIZE holds while recent still qualifies.

**Map v1 (seeded from entry 10, effective 2026-07-02T16:45Z):** 106 cells, 11 PRIORITIZE,
**2 DODGE** — `strict|regime|tennis` (roi_ub −8.7%, N=110) and `strict|mtype|moneyline`
(roi_ub −2.5%, N=179).

### Phase 2 — the checkpoint runner + virtual overlay

`scripts/map_checkpoint.py` (imports `slice_study.py` as a library — its CLI stays
byte-identical). **E2E self-test PASS:** a synthetic world that CHANGES between checkpoints
(a losing cell turns winning) — the runner enters DODGE (v1), holds while losing (v2,
excluded ROI −0.485), **rehabilitates when the recent window flips positive** (v3), and the
excluded counterfactual **flips sign** (+0.164). Exactly the adaptivity the owner asked for.

**Checkpoint #1 executed live (mostly-null, as expected):**
- 1 transition: `favorite|band3|0.65-0.80` NEUTRAL→PRIORITIZE (roi_lb +1.1%, N=55) — the
  cell entry-10 flagged as "not settled," now qualifying on accrued data. The map is
  genuinely adapting, not frozen.
- Overlay: 2 forward strict events, **0 excluded → PENDING 0/30** (floor not reached; K1).
- Nominations: favorite∩opp≥1 **NOT DUE** (2/30 forward), favorite∩tennis **NOT DUE**
  (0/30). Both wired; they fire automatically at 30 forward events.
- The seed v1 remains the version of record; checkpoint #1's live run was `--dry` (no
  version written) — the first version-advancing checkpoint fires at the real +7d/+300ev
  trigger, respecting optional-stopping (D9).

### Phase 3 — what the overlay WOULD have done (descriptive, CIRCULAR — never gates)

Retro-replay of map v1 over the whole record (labeled circular — the map was built on it):

| | strict (parent) | fleet_mapped | paired lift |
|---|---:|---:|---:|
| matched-blind surplus | +3.69% | +10.17% | **+6.48% [+1.70, +11.30]** |

Excluded picks (179 events, kept 49): realizable ROI **−13.71% [−25.22, −1.19]**, flat-$
P&L **−$2,454**. **But the excluded set is mixed by regime** — the honest caveat:

| excluded regime | events | ROI |
|---|---:|---:|
| tennis | 110 | **−23.70%** (correctly dumped — the non-favorite residue) |
| soccer | 20 | −9.54% |
| cs2 | 6 | −8.88% |
| mlb | 35 | **+3.63%** (excluded-yet-profitable) |
| other | 8 | **+33.73%** (excluded-yet-profitable) |

**The `strict/moneyline` DODGE is coarse:** it correctly dumps the tennis/soccer non-favorite
residue but also dumps profitable MLB and "other" moneyline favorites. This is *why the map
must be adaptive and measured forward*, and it dovetails with the breadth finding below:
post-WC the strict stream becomes MLB-moneyline-dominated (+3.6% ROI), so the moneyline
DODGE cell should **rehabilitate forward by its own rules** — the adaptive design is built to
catch precisely this over-broad cut. The circular +6.48% lift is *descriptive*, not
evidence; the forward gate is the real test.

**Recent-window sensitivity (7/14/21d):** the record spans 3.3 days, so all three windows
collapse to the whole record (228/228 strict events). Sensitivity is **untestable until >7
days accrue**; the pre-registered 14d stands (noted for the next pre-registration cycle).

---

## Phase 2.5 — Market-breadth audit (read-only; measurement, not manufacture)

### 1. Supply → consensus funnel (whole record, distinct events)

| regime | blind events (sharps active) | any-consensus | strict | conversion |
|---|---:|---:|---:|---:|
| crypto | 2,395 | 12 | 0 | **0.5%** |
| other (politics/misc) | 941 | 78 | 20 | 8% |
| tennis | 503 | 268 | 115 | 53% |
| soccer | 260 | 117 | 88 | 45% |
| mlb | 109 | 50 | 43 | 46% |
| cs2 | 81 | 17 | 7 | 21% |

**Crypto is the dog that doesn't bark:** 2,395 markets with sharp activity, essentially zero
consensus. Not a code filter (confirmed §3) — sharps spread across up/down threshold markets
and never produce ≥`min_backers` one-sided agreement. Sharp $ supply is overwhelmingly
soccer ($183M all-time) + tennis ($30M) + mlb ($13M); crypto is 32 wallets / $2.7M.

### 2. Rotation mechanics — self-healing, category-blind

The leaderboard poller (`leaderboard_tracker.rs`) fetches the **global** PnL leaderboard
(no sport param) and unions the top-40 across `TRACK_PERIODS` (default **"WEEK,MONTH"**;
DAY/ALL available, off). Eligibility is a **rank** gate (`TRACK_CONSENSUS_RANK_CUTOFF=40`),
never a category gate. Stale traders are deactivated after `TRACK_DROP_GRACE`(6) ×
`TRACK_REFRESH_MINS`(60) = **6h** off the leaderboard. So when tournament sharps' PnL fades,
whoever is hot (MLB/politics/esports sharps) auto-swaps in within ≤6h + a WEEK/MONTH
leaderboard climb. **Rotation lag can't be measured in-record** — the tracker is only 3–4
days old (oldest_add 2026-06-29); no tournament boundary has passed yet. 413 tracked, 285
active, 181 consensus-eligible.

### 3. Structural blockers — none for firing (EMERGENT/DATA-DRIVEN)

Full code audit: the only category filter is `SportsMode` on the scorer; the **only alerting
strategy `strict` runs `Include`** (fires on every category, crypto included). No slug
allow/deny lists, no per-strategy category scoping. `is_sports`/`sport_bucket`
(`consensus_cycle.rs:108-192`) hard-code prefix lists, but they only **label** fills for
analytics and the silent `sports_only`/`nonsports` arms — an unmatched category falls to
`"other"` and **still fires** under `strict/Include`. Nothing structurally blinds the engine
to non-WC markets. **Verdict: breadth is emergent (who's on the leaderboard × where sharps
agree), not code-blocked.**

### 4. Post-WC frequency forecast (WC ends ~Jul 19; Wimbledon ~Jul 13)

Per-strategy events/day by regime (resolved, distinct events, 4-day record):

| strategy | total/day | WC soccer | Wimbledon tennis | MLB (→Oct) | other | **post-tournament floor** |
|---|---:|---:|---:|---:|---:|---:|
| strict | ~57 | 14.8 | 27.5 | 10.5 | 4.3 | **~15/day (MLB-carried)** |
| favorite | ~24 | 8.5 | 11.5 | 2.3 | 1.5 | **~4/day (thin, alive)** |
| elite_fresh_fav | ~10 | 5.0 | 4.5 | 0.0 | 0.3 | **~0.3/day (goes near-silent)** |

**Honest forecast:** post-tournament, **strict survives** (~15/day, MLB is the structural
bridge — daily through October + playoffs; MLB sharps are *already* tracked and firing).
**favorite thins to ~4/day. elite_fresh_fav effectively goes silent** — it is 97%
WC+Wimbledon and has no MLB footprint. The engine will NOT go dark, but the higher-purity
winners contract sharply until the next dense block: US Open tennis (late Aug), NFL (Sept),
MLB playoffs (Oct), US-politics into the cycle. Because the leaderboard is category-blind and
self-healing, volume *follows* the calendar automatically — there is no structural dead zone,
only a purity contraction in favorite/elite_fresh_fav.

### The ONE breadth action proposed (for Tue's decision — proposed, NOT applied)

**Add `DAY` to `TRACK_PERIODS` (`"DAY,WEEK,MONTH"`).** Pure additive config (no code, no
migration, reversible via `.env.consensus`), and — critically — it does **not loosen any
consensus gate** (the rank cutoff, min-backers, capture margin all unchanged). It changes
*which leaderboard is polled*, surfacing the hottest current-slate sharps ~1 day faster than
the WEEK cohort, which shortens the post-tournament purity-contraction lag and diversifies
the voter mix toward whatever sport is live. **Tradeoff:** DAY-period ranks are noisier (one
lucky day → top rank); the belief-blind gate still judges them, but it adds churn.

**The genuine null alternative, which the evidence actually favors:** *do nothing* — breadth
is not code-blocked, MLB already carries strict's floor, and rotation self-heals in ~6h. The
DAY-period add is a marginal lag-shortener, not a fix for a broken thing. **Recommendation:
hold `TRACK_PERIODS` as-is; instead the highest-value forward measurement is to watch
elite_fresh_fav's fire-rate across the WC final** — if it goes silent as forecast, that
confirms the winners are tournament-purity plays, which is a strategy-scope finding worth
more than any config knob. This is a measurement, not a gate change.

---

## Nominations (entry-10 pre-registration — forward reads, executed if due)

Both wired into `map_checkpoint.py`, judged on FORWARD data only:
1. **favorite ∩ opp≥1** — NOT DUE (2/30 forward events). Bar: matched surplus LB > 3% ∧
   selection-null p ≤ 0.01 ∧ ≥2 regimes > 0 ∧ the opp≥1 − opp=0 difference > 0 at 95%.
2. **favorite ∩ tennis** — NOT DUE (0/30 forward events). Same bar; if it confirms, a
   tennis-moneyline variant discussion is earned, not before.

Both fire automatically at 30 forward events (then every +15). At ~4–24 favorite events/day,
opp≥1 is due in a few days; tennis while Wimbledon runs.

---

## When the answers arrive

| answer | trigger | ETA (at current pace) |
|---|---|---|
| overlay success/refute bar | 30 forward excluded strict events | ~1 day of live firing |
| favorite∩opp≥1 nomination | 30 forward favorite∩opp≥1 events | ~3–5 days |
| favorite∩tennis nomination | 30 forward favorite∩tennis events | while Wimbledon runs (~1 wk) |
| first version-advancing checkpoint | +7 days OR +300 fleet events | whichever first |
| forced WC-final checkpoint | after the WC final (~Jul 19) | ~2.5 weeks |
| moneyline-DODGE rehab test | post-WC MLB-dominated forward stream | the marquee adaptive test |

## The EARNED Rust surface (K3 — trigger + sketch, NOT built)

Build a real silent `fleet_mapped` StrategyDef arm (+ a board panel showing the live map
version, its DODGE cells, and the running excluded-pick counterfactual) **only after
`fleet_mapped` clears its success bar at a real checkpoint** (excluded P&L negative ∧ paired
lift positive at 95% on ≥30 forward excluded events). Sketch: a `StrategyDef` whose scorer
consults `current_map(fire_ts)` and drops signals in DODGE cells; alerting stays false until
a second, forward, D7-grade certification. Until then the overlay is a VIEW over the fleet
record, computed at checkpoints — never a mutation of the stream (which must keep firing on
everything, DODGE cells included, forever).

## What was deliberately NOT done

- No live Rust arm / alert filtering / board panel (unearned, K3). No promotion, no env
  change, no real money. No `.env.consensus` edit (the DAY-period action is *proposed*).
- No re-tuning of thresholds / window lengths / FDR-q at checkpoints (frozen procedure).
- No permanent edit to any StrategyDef or filtering of `strict` — the map is a VIEW.
- No second hypothesis slot — `fleet_mapped` is the one experiment; the nominations reuse
  entry-10's slots.
- No gate loosened to manufacture breadth (measurement only, per the owner directive).

## Ship note

`scripts/map_state.py` + `scripts/map_checkpoint.py` (both self-testing), map v1 under
`reports/map/`. No Rust change, no migration → the autoupdater skips the rebuild. Rollback:
`git revert` the merge; delete `reports/map/` (pure artifacts, nothing reads them live).
