# FORGE DEBATES — The Archive Flywheel

*Compressed record of the two-path design debate and the reality-checked synthesis. Companion to
`RUN-ARCHIVE-FLYWHEEL.FORGE_PLAN.md`. "A" = Direct Path, "B" = Rethink Path. Every finding below was
grep/Read-verified against the live tree 2026-07-02; load-bearing facts carry file:line.*

---

## The verification that reframed the whole debate

Both agents built their designs on the same substrate assumption or its inverse. Two verified facts
settle most of the disagreements:

- **`observed_votes` is overwritten every cycle.** `upsert_consensus_signal` sets
  `observed_votes = EXCLUDED.observed_votes` on conflict (`common/src/storage/consensus.rs:253`,
  verified verbatim). So the stored atoms are the **last-fire** book, and earlier windows are gone.
  → B's "the atoms ARE the as-of book" is true only for the *last* fire and only for markets `_blind`
  emitted — it cannot support as-of cuts or a first-fire entry.
- **The gate judges on at-fire `initial_mean_price`, stored in neither substrate.**
  `consensus_scoreboard_by_strategy` computes surplus on `COALESCE(initial_mean_price, mean_price)`
  with day axis `(first_detected_at AT TIME ZONE 'UTC')::date` and a `_blind` band baseline
  (`:640-648`); `initial_mean_price` is set once at insert, never updated (`:610`); the post-fire
  drift is ~+1.2¢ (`:613`). `observed_votes` carries no `initial_mean_price`; `trader_fills` carries
  no rank. → **No replay path can reproduce the judged surplus exactly.** Parity must be a per-column
  ledger, not a tolerance; the decision point must be first-fire, not peak.

These two facts convert the "A vs B" question from "which substrate" into "fills for the sweep
(durable, as-of-capable), atoms for parity path (a) (frozen rank)" — a synthesis, not a pick.

---

## Per-gap: both designs' essence · verification · decision

### GAP-1 — As-of reconstruction spec
- **A:** new bounded loader `load_live_era_buy_fills` + Rust-side windowing; decision point
  `now = max(ts)` (peak) per market.
- **B:** dissolve it — "the atoms are the as-of book"; per-event `now = max(atom ts)`; reuse
  `trader_slice_scores_asof` for the trust frontier.
- **Verify:** A's `load_buy_fills_since` critique is correct (`:1360`: no upper bound, current-rank
  quality, current eligibility). B's atom reframe is **undercut by `:253`** (last-fire, lossy). A's
  **peak choice is self-contradictory**: the scoreboard judges at-fire (`:610`), drift ~+1.2¢
  (`:613`) > A's own ±0.5pp parity tolerance.
- **Decision — refined.** Substrate = `trader_fills` (A's loader, kept). Decision point = **first-fire**
  (earliest window whose gate fires), replacing A's peak — it mirrors the at-fire entry the gate
  actually judges and is what makes parity possible. Day axis = event-date for freshness-free (D1),
  ts for live-era freshness.

### GAP-2 — Parity
- **A:** enumerate five structural residuals; assert count/surplus columns within ±1 event / ±0.5pp
  on count-based strategies, live era; CLV/day columns N/A.
- **B:** a checked-in per-column signed **ledger** (STOP only on a column declared *exact* drifting)
  + reframe path (b) from number-match to **set-coverage** (scorer is pure ⇒ match inputs, not the
  un-storable output); adds a verified **sixth** residual (last-fire vs first-fire entry).
- **Verify:** B's ledger is strictly better than A's scalar tolerance for a heterogeneous 8-column
  record; B's sixth residual is real (`:253`). B's coverage reframe is sound but validates *membership*,
  not the judged surplus. A's residual enumeration is accurate.
- **Decision — hybrid.** B's ledger + coverage reframe as the frame; A's residual list as its rows;
  the sixth (`last_fire_entry`) row explains why path (a) is claimed on stored `mean_price` while path
  (b) fills carry at-fire surplus via first-fire. STOP only on an exact-declared count column drifting.

### GAP-3 — Registry format
- **A:** hand-authored fenced TSV (diff-clean, greppable), migrate ~25 findings by hand.
- **B:** split source from view — tiny hand-authored `findings-source.tsv` (human fields only) +
  a stdlib generator + a Rust `verdict_cli` that **derives status from the one gate**; `REGISTRY.md`
  is a regenerated artifact that can't lie about numbers.
- **Verify:** both converge on fenced TSV (rejecting GFM tables). The brief itself names the failure A
  risks ("N=38 sitting unexamined because nobody re-ran a script"). B's generator honors the one-gate
  rule *only* because status routes through `verdict_cli` (`promotion_verdict:168`) — not re-derived
  in Python.
- **Decision — rethink (B).** The generated view is the design that makes the *unattended* refresh
  trustworthy (user requirement b); the `verdict_cli` guard keeps `promotion_verdict` the only promoter.

### GAP-4 — Sweep shape + checkpoint
- **A:** replay in-memory → **insert rows into a throwaway `consensus_signals`** tagged by config →
  judge the whole grid in **one** reused scoreboard query; per-config JSONL; `TRUNCATE` after
  capturing the forward scoreboard to a file. Arithmetic: ~8s scoring, restore ~1 min dominates.
- **B:** replay `_blind` atoms in-memory (no fill-load, no restore for the sweep); per-config JSONL.
  Arithmetic: ~13s, no restore.
- **Verify:** B's atom-sweep is **disqualified** by `:253` (last-fire/lossy → wrong entry & timing for
  threshold configs). A's insert-and-reuse is the **strongest anti-`market_resid` mechanism** (reuses
  the exact band-blind/event-cluster/day-deflate SQL). Confirmed feasible: the 12 no-default NOT NULL
  columns of `consensus_signals` (`migrations/021_consensus.sql`) are all scalar → UNNEST works;
  scoreboard reads exactly the columns a replay row supplies (`:637-690`). **New risk found:** an
  `#[ignore]`d test reading `$DATABASE_URL` that `TRUNCATE`s `consensus_signals` **destroys prod** if
  misdirected (`honest_pnl_by_strategy` reads only that table, verified). A's `first_detected_at=now_m`
  also corrupts `distinct_days` on backfill (crawl-ts).
- **Decision — hybrid + refined.** A's insert-and-reuse mechanism + first-fire (GAP-1) + per-config
  JSONL + **day-axis fix** (event-date for freshness-free) + **mandated `assert_throwaway` guard** and
  `run.sh`-only invocation. `TRUNCATE` is justified (baseline consistency: the replay `_blind` must
  share the candidates' first-fire entry basis). Bonferroni denom = own `GRID_SIZE`.

### GAP-5 — Ghost floor
- **A:** event-level permutation of `outcome_won` via the throwaway scoreboard (UPDATE + re-run),
  GHOST_N=5, keep both deflators.
- **B:** don't build a permutation — **reuse `selection_null.py`** so the event-clustered level is
  structural; ghost = max null draw of the winning config.
- **Verify:** both correctly reject fill-level permutation (collapses clustered SE → certifies noise,
  the `market_resid` class). B's reuse is elegant and eliminates a bespoke loop, **but** the
  per-winner selection null is **not** the max-of-K empirical floor the search doctrine mandates —
  Bonferroni corrects the threshold, not the effect-size null. Both flag the `selection_null.py:41`
  prod hardcode (verified).
- **Decision — hybrid.** Keep A's **event-level shuffled-outcome ghost floor** (the max-of-K empirical
  deflator) via the reused scoreboard, **and** B's `selection_null.py` reuse for the *separate*
  per-survivor compositional null (rule b). Two distinct deflators; don't let B's simplification drop
  one. `PG_CONTAINER` patch adopted.

### GAP-6 — Slot grammar
- **A:** generalize `parse_retuned` to a hand-rolled `key=value` parser (14 keys, enum spellings,
  per-token fail-closed) across `REPLAY_ARM_A..E` × 2 files.
- **B:** one `REPLAY_ARMS` JSON var → **serde** `Vec<ReplayArmSpec>` with `deny_unknown_fields`;
  grammar = the type; empty ⇒ [] ⇒ byte-identical; collapses 5×2 declarations to 1×2.
- **Verify:** `serde_json` is already a dep (`observed_votes: serde_json::Value`). Serde makes
  fail-closed structural (unknown key, one-bound band, bad enum all reject for free) — strictly safer
  than a bespoke parser and easier to prove "empty ⇒ byte-identical." **B omitted** the coherence
  invariant `parse_retuned` enforces (`min_backers≥1 && strong_net≥min_backers && elite_net≥strong_net`,
  verified `:812-826`).
- **Decision — rethink (B) + refined.** Serde JSON, `&'static str` NAMES pool retained; **add** the
  coherence guard in `into_params` (return `None`/drop on violation).

### GAP-7 — Autonomy
- **A:** phase-state file + per-config JSONL; concrete `refresh.sh` (`flock`, `set -euo pipefail`,
  atomic `mv`, `trap ERR`, disk guard); launchd plist with logging + `|| ntfy`; `PG_CONTAINER` patch;
  board staleness panel.
- **B:** three reframes — a **target dispatcher** (build + refresh share one resumability mechanism);
  the refresh is just another target; the **always-on bot is the watchdog** (renders staleness),
  removing "the scheduler failed silently" as a class; honest board-native assessment (bot can't
  docker/cargo → restore+sweep stay host-side).
- **Verify:** A's crash-safety block is correct and matches the audit-log `flock` precedent from
  memory. B's dispatcher is cleaner (one correct mechanism, not two) and its watchdog pins liveness to
  the autoupdater-kept-healthy bot. Both agree on `PG_CONTAINER` + pre-declared paths. Verified:
  `com.tue.consensus.backup.plist` structure (model), `CODE_RE:40` (docs skip rebuild), `wt/`
  gitignored + `.dockerignore`.
- **Decision — hybrid.** B's target dispatcher + bot-as-watchdog + A's concrete `flock`/atomic/`trap`
  refresh, with launchd failure push kept as the primary signal and the board panel as backstop.

### GAP-8 — Use the archive to its fullest
- **A:** wire `report_deep_sharp_pass` + `deep_edge_thesis.py` as registry rows with a pre-registered
  target N; report progress below N, run once at N.
- **B:** a **latch** — the registry's existing `unblock`/`target_n` field *is* the stopping rule;
  below N compute **no** p (nothing to peek), at first N-crossing evaluate once, stamp `evaluated_at`,
  thereafter report the latched verdict.
- **Verify:** both fix the peeking problem the diagnostic flags. B's latch is crisper and needs zero
  alpha-spending machinery, reusing a field GAP-3 already carries. The generator write-back to
  `findings-source.tsv` is safe under the refresh `flock`. `trader_slice_scores_asof` (`:1526`) is the
  leak-free trust query.
- **Decision — rethink (B) latch**, wired via two `run.sh` targets; the reused pure functions
  (`earned.rs:46/75/366`) stay unchanged.

---

## Key insights that emerged

1. **The substrate question isn't "fills vs atoms" — it's "which for which job."** `trader_fills` is
   the durable, as-of-capable archive (the sweep); `observed_votes` is the frozen-rank record of what
   was emitted (parity path a). The overwrite semantics (`:253`) make the atoms unfit for the sweep
   and the missing rank makes fills unfit for exact parity — so both are needed, for different jobs.
2. **"Reproduce the forward record" was never possible.** The judged number (`initial_mean_price`,
   at-fire) is stored in neither substrate. Once that is verified, the entire parity design changes
   from a tolerance to a per-column ledger, and the decision point changes from peak to first-fire.
3. **The most correct sweep mechanism is also the most dangerous.** Inserting replay rows into the
   real `consensus_signals` and reusing the real scoreboard is the strongest guarantee against a
   parallel-baseline false-promote — but a `TRUNCATE` on that table against prod is catastrophic. The
   design is only safe with a hard throwaway-assertion guard; neither agent added it.
4. **Generation beats maintenance for autonomy.** A hand-kept registry drifts; a registry generated
   from (human intent + the live gate) cannot. The user's reliability requirement tips GAP-3/8 toward
   B's generated view + latch.
5. **Reuse can go too far.** B's instinct to reuse `selection_null.py` for the ghost floor is right in
   spirit but would silently drop the max-of-K empirical deflator the search doctrine mandates. Keep
   both deflators; reuse the null for rule (b), not for the floor.
6. **Autonomy is composition, not new infrastructure.** `flock` (audit-log precedent), the backup
   launchd pattern, `PG_CONTAINER` scripts, worktree per-target commits, and the `render_earned` TTL
   panel already exist — the flywheel's reliability is ~6 shell scripts + a state file + a one-line
   patch + a board panel, plus the one guard that makes the whole thing safe to run unattended.

---

## Scorecard (source of each item in the plan)

| Gap | Winner | Why |
|---|---|---|
| 1 as-of | refined | fills substrate (A) but first-fire, not peak (verified drift > A's tolerance) |
| 2 parity | hybrid | B's ledger + coverage, A's residuals, verified 6th (last-fire entry) |
| 3 registry | rethink (B) | generated view → numbers can't drift (autonomy) |
| 4 sweep | hybrid+refined | A's insert-and-reuse + JSONL + day-axis fix + throwaway guard |
| 5 ghost | hybrid | A's event-level floor + B's selection_null for rule (b) — keep both deflators |
| 6 slots | rethink (B)+refined | serde deny_unknown_fields + added coherence guard |
| 7 autonomy | hybrid | B dispatcher + watchdog + A crash-safe refresh |
| 8 fullest | rethink (B) | latch on pre-registered N reuses existing field |
