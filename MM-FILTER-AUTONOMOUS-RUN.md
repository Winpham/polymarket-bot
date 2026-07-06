# Autonomous Run: Calibrate & Validate the Market-Maker Screen (MM-FILTER, re-scoped)

> **Read this whole brief before touching anything.** You are an autonomous build worker operating
> on `~/polymarket-bot` (Rust + SQL Polymarket consensus/copy-trading bot). This brief SUPERSEDES a
> literal reading of `FORGE_PLAN_MM_FILTER.md` — that blueprint was written before the D27/D28
> **proven-router** merge (current `main`, HEAD `8cb9fab`) already shipped its Item-1 foundation.
> Your job is to **validate, calibrate, and extend** the microstructure screen that already exists —
> **not rebuild it**. When this brief and `FORGE_PLAN_MM_FILTER.md` disagree, this brief wins.

---

## 0. The one-paragraph truth

The proven-router merge already computes the position-grain microstructure the blueprint's Item 1
proposed as "new" (`round_trip_rate`, `sell_buy_ratio`, `two_sided_rate`) inside
`refresh_router_followset` (`common/src/storage/consensus.rs:1576`, CTEs at `:1600-1609`), persists
them to `router_followset` (migration `039_router_followset.sql`, cols 21-23), and **already uses them
as a live (paper) churn screen**: `round_trip_rate < 0.30 AND two_sided_rate < 0.25 AND
sell_buy_ratio < 0.50 AND NOT trader_type='bot'` (`:1649-1651`). Those thresholds were **frozen by
pre-registration with ZERO measured FP/FN and ZERO downstream-effect validation** — the docstring at
`:1569-1574` literally calls them *"interim pending FORGE_PLAN_MM_FILTER's calibrated verdict."*
**That deferred, un-built calibration + validation + reconciliation is your entire mission.**

## 1. Mission, in order of priority

1. **Answer the gating question first (Phase 1):** Is the live `0.30 / 0.25 / 0.50` screen *correct
   and useful*? Measure its FP/FN against a labeled set with a permutation null; and — the binding
   test — does excluding the wallets it flags actually make the survivor pool **more persistent
   out-of-sample**, beyond a matched-subset null? **HARD STOP and report after Phase 1.**
2. **Only if Phase 1 clears (Phase 2, conditional):** produce the calibrated, cross-referenced,
   fail-open **verdict** the docstring is waiting for, refactor the inline microstructure into a
   shared method (extend, not duplicate), persist an append-only audit + reconciliation of the 115
   `fpd` flags, and wire a **shadow-only** consensus-path arm that never touches the live alert path.

**"Indeterminate" is a valid, expected terminal outcome.** At n≈29 humans this is very likely
power-limited. You are FORBIDDEN from goal-seeking a positive result. A rigorous "we cannot decide
this yet, here is exactly why and what N it would take" is a SUCCESS, not a failure. Do not tune
until something looks green.

## 2. Hard constraints (non-negotiable)

- **No real money. Paper-only. Ever.** Nothing you build may place, size, or enable a real order.
- **Cost-zero / Max-subscription only.** Do NOT set or use `ANTHROPIC_API_KEY`. Do NOT spawn child
  `claude` processes. Pure Rust + SQL + local Python; no paid API, no LLM calls in the pipeline.
- **Do NOT touch the live `strict` alert path.** The consensus book filter
  (`consensus_eligible OR earned_eligible`, `storage/consensus.rs:1403`) stays byte-identical.
- **Do NOT overwrite `trader_type`.** `classify_trader_types` (`:1327`) and its 115 flags are an
  artifact to reconcile against, never destroy. All new verdicts go in a NEW append-only table.
- **Do NOT re-implement the microstructure.** It exists (`:1600-1609`). If Phase 2 needs it as a
  reusable unit, REFACTOR the inline CTE into one shared method both callers use — no second copy,
  no behavior change to `refresh_router_followset` (assert its output byte-identical).
- **Migration number is `040`.** `039_router_followset.sql` is taken. Migrations live in
  `/migrations/` (repo root), not `common/migrations/`.
- **Resolve every code anchor by SYMBOL NAME, then read the surrounding code — never patch by raw
  line number.** The blueprint's line anchors have drifted (see §7). Grep the symbol, confirm the
  logic, then edit.
- **Isolate in a polymarket-bot worktree.** This repo uses its own `wt/<slug>/` convention (NOT the
  winmon `coord/` toolkit — that governs a different repo). Create `wt/mm-calibrate/` off fresh
  `main`, work there. The autoupdater deploys LOCAL `main` on HEAD advance, so do NOT merge to `main`
  until the gate is green AND you have summarized for Tue; if another chat holds a migration number,
  renumber rather than collide.
- **Gate after every code change: `cargo build && cargo test` must be green.** There is no
  Makefile/justfile; that command IS the gate. Default behavior must stay byte-identical (existing
  tests green, `ConsensusParams::default()` unchanged).

## 3. Pre-flight (do this before writing anything)

1. `git -C ~/polymarket-bot rev-parse HEAD` — confirm you are on/based on `8cb9fab` (or later `main`).
   If `main` has advanced, re-read `refresh_router_followset` and this brief's anchors before trusting them.
2. Create the worktree: branch `mm/calibrate-validate` off fresh `main`, in `wt/mm-calibrate/`.
3. Re-verify by symbol (grep, don't trust these lines) that all §7 anchors still resolve. If any
   symbol is gone or fundamentally changed, STOP and report — do not guess a replacement.
4. Confirm the three validation scripts exist and skim them so you clone their machinery, not reinvent:
   `scripts/selection_null.py` (permutation-null pattern, `SELECTION_NULL_P_BAR=0.01`),
   `scripts/specialist_mining.py` (`MECH_SQL`, `two_sided_frac>=0.30`),
   `scripts/persistence_tracker.py` (`--cutoff`, match-key clustering, `PERSIST_MIN_CLUSTERS=10`).
5. Sanity-read the data: run the existing `refresh_router_followset` microstructure sub-query
   read-only against the live DB and confirm a known churner (the $36.6M wallet) reads high
   `round_trip_rate` + `two_sided_rate≥0.6`, and a known soccer human reads both ≈0. If the data
   contradicts the premise, STOP and report — the whole plan rests on this separation being real.

## 4. PHASE 1 — Validation harness (the decision gate). Build ONLY this first.

All Phase-1 work is **offline Python** reading the live DB read-only (mirror the existing scripts;
paste operating points via env, exactly like `selection_null_p_for` reads `SELECTION_NULL_P`,
`promotion.rs:197-198`). No Rust changes in Phase 1.

### 4a. `scripts/mm_calibrate.py` — Tier-1, labeled, measure the EXISTING thresholds
- Build a labeled set (~40): MMs = the $36.6M churner + the D23 crypto up-down two-sided wallets +
  D23 tennis wallets; Humans = `0xe9a6ed2e4d…`, `0x56f0321917…` (≈0% two-sided, DECISIONS.md:734) +
  hand-verified cleanest survivors. **Record provenance of every label in the report.**
- Compute per-axis and ensemble **FP/FN of the LIVE `0.30/0.25/0.50` thresholds as they stand** —
  the first deliverable is "how good is what's already deployed," not a new boundary.
- Then sweep `tau_rt / tau_sb / V` on a grid; run the **label-permutation null** (shuffle labels
  ≥1000×, require real separation in the right tail, `p ≤ 0.01`). Freeze `tau_2s` at 0.30 (precedent).
- **Anti-overfit discipline:** with ~40 labels, do NOT free-tune three knobs to a boundary. Prefer
  freezing `tau_rt`/`tau_sb` near the interim values and floating at most ONE knob, and report
  leave-one-out stability of any chosen operating point. State explicitly if the labeled set is too
  small to calibrate at all (it may be) — that is a finding, not a blocker.
- **Circularity caveat (must be stated in the report):** the labeled set partly derives from the same
  `two_sided≥0.30` heuristic under test, so Tier-1 AUC is partly circular. Tier-1 is necessary but
  **NOT sufficient.** Tier-2 is the binding validation.

### 4b. `scripts/mm_persistence_effect.py` — Tier-2, label-free, the BINDING test
Clone `persistence_tracker.py`'s cutoff + event-clustering. Core measurement: split the human pool
early/late by fill-day; compute the top-pick early→late surplus correlation **with vs without** the
screen-flagged wallets; the baseline early→late corr is ≈ **−0.10**.

Two methodology requirements the blueprint MISSED — both mandatory:
1. **Matched-subset permutation null (this is the crux).** A positive Δcorr from removing a chosen
   subset of a ~29-wallet pool is *mechanically expected* — removing high-variance/high-volume points
   raises correlation regardless of whether they are MMs. So: remove **random equal-N subsets matched
   on volume / n_positions** ≥1000×, build the null distribution of Δcorr, and require the REAL
   removal's Δcorr to sit in the right tail (`p ≤ 0.05`). **Without this null, Tier-2 rubber-stamps
   noise — do not report a bare Δcorr as evidence.**
2. **As-of discipline (leakage).** The MM verdict used to decide who to remove MUST be computed from
   **early-period data only** (as-of the early/late cutoff). If the verdict sees late fills, the
   classification leaks future info into the early→late correlation. `two_sided_rate` at lifetime
   grain is the specific offender — compute it as-of the cutoff for this test.
- **Power report (mandatory):** report the correlation's CI at the actual N (at n≈29 it's roughly
  ±0.37). If Δcorr is inside the null's bulk OR the CI swamps the effect, the verdict is
  **INDETERMINATE-BY-POWER** — say so plainly and state the N (months of independent clusters) that
  would be needed. Do NOT dress an indeterminate result as a pass.

### 4c. `scripts/mm_reconcile.py` — Item 6 reconciliation (the literal "cross-reference" ask)
Produce the disagreement set of the 115 `fpd` flags vs the microstructure screen:
`(trader_type='bot') != (screen flags as churner)`. Surface (a) old-`bot`/screen-`clean` =
burst-human **FPs the `fpd` rule wrongly deleted → candidates to restore** to the 29–72 pool;
(b) old-`human`/screen-`churner` = patient-MM **FNs polluting the pool → candidates to exclude**.
Output a human-reviewable table (wallet, old label, screen verdict, driver, the three rates, surplus,
n_positions). This is READ-ONLY analysis — it recommends, it does not mutate `trader_type`.

### 4d. PHASE-1 DECISION GATE — stop here and report
Write a report to `reports/entries/` and a `DECISIONS.md` entry with, at minimum:
- Measured FP/FN of the live `0.30/0.25/0.50` screen + Tier-1 null p-value (or "uncalibratable at N").
- Tier-2 Δcorr, its matched-subset null p-value, and the power/CI verdict.
- The reconciliation table (FP-restore / FN-exclude candidates).
- **A one-line GO / NO-GO / INDETERMINATE verdict** on whether the screen is validated.

**Then STOP.** Do not start Phase 2 unless Tier-2 is GO (Δcorr positive AND beyond its matched-subset
null AND not swamped by power). If NO-GO or INDETERMINATE, the deliverable is the honest Phase-1
report + a recommended next data-collection step, and the system stays an offline audit. Surface the
verdict to Tue for the Phase-2 decision — do not self-authorize continuation.

## 5. PHASE 2 — Calibrated verdict + audit + shadow arm (CONDITIONAL on Phase-1 GO)

Build in the execution order below, `cargo build && cargo test` green after each, default behavior
byte-identical throughout.

1. **Refactor, don't rebuild:** extract the inline `pos → two → micro` CTE from
   `refresh_router_followset` into a shared `wallet_microstructure()` method (sibling to
   `trader_slice_scores`, `storage/consensus.rs:1497`), and have `refresh_router_followset` call it —
   assert its follow-set output is byte-identical before/after (this is a pure refactor).
2. **Migration `040_mm_verdicts.sql`** — append-only, idempotent, additive: per-wallet signal vector +
   verdict history keyed `(wallet, computed_at)`. NEVER edit once applied (sqlx checksum). Written by
   an `upsert_mm_verdicts` alongside (never over) `trader_type`.
3. **The verdict** `MmVerdict{Mm,Unknown,Human}` (next to `TrustVerdict`, `trader_trust.rs:67`):
   MM only when the STRUCTURAL axis (S1 churn `round_trip_rate≥τ_rt AND sell_buy_ratio≥τ_sb`, OR S2
   `two_sided_rate≥τ_2s`) AND the EDGE axis (S3 `TrustVerdict::Indeterminate AND n_positions≥V`) agree
   AND `!Trusted` (fail-open for proven predictors). Human only when `!structural AND n_days≥floor AND
   !Indeterminate`. Else **Unknown → fails OPEN (stays in pool)**. Operating point comes from §4a — do
   not hand-tune for signal. Populate an `MmMap` in the existing slow refresh (S3 reuses cached slice
   scores → 0 extra queries).
   - *Verdict caveat to honor in code comments:* a break-even MM and an unlucky-skilled human both read
     Indeterminate; the conjunction with structural is what separates them, and `sell_buy_ratio` (not
     `round_trip_rate` alone) is the axis that spares the human who occasionally sells to lock profit.
4. **Weight-cap seam** (dormant; weighted arms are OFF today): at the per-vote `earned_quality` stamp
   (`consensus_cycle.rs:648`, stamp region `:646-672`), cap by `MmMap` using the existing
   `.clamp(...)` idiom (`consensus_cycle.rs:77/:117`) — `Mm→0.5`, `structural→1.0`, else no-op
   (`f64::INFINITY` cap ⇒ byte-identical when the map is empty/absent). Keep `score_market` pure — the
   cap arrives on the vote from the impure layer.
5. **Shadow-only consensus arm** (NEVER live): add `is_mm` to `TraderVote` (default false; update all
   constructor sites, keep `ConsensusParams::default()` byte-identical), `exclude_mm` to
   `ConsensusParams` (default false, mirrors `trusted_only`/`certified_only`), an `mm_arms` silent arm
   registered only under NEW env `CONSENSUS_MM_ARMS` (default false, mirror `CONSENSUS_TRUST_ARMS`,
   `config.rs:243`), and a shadow test (mirror `deep_pool_excluded_..._shadow_differs`,
   `consensus_cycle.rs:1410`) proving a seeded MM vote makes the MM-excluding book differ. A SEPARATE
   `EXCLUDE_MM` flag (default false) would gate ever touching the live `strict` filter — **do not flip
   it; that is Tue's call, after forward-proof.**

**Gate before the live `strict` filter is ever touched (a later, separate decision — NOT this run):**
Tier-1 null passed + Tier-2 Δcorr positive beyond its null + shadow arm forward-proven over independent
clusters (months) + Tue's explicit sign-off.

## 6. Reporting (how to finish)

- One `reports/entries/` markdown + one `DECISIONS.md` entry, in the honest style of the existing D-log:
  what was measured, the verdicts (with p-values and power), what was built, what was DEFERRED and why,
  and the single GO/NO-GO/INDETERMINATE headline.
- If you stopped at the Phase-1 gate, say so plainly and state the exact next step (usually: collect N
  months of forward clusters before this is decidable).
- Do not claim "done" for anything not `cargo test`-green and driven end-to-end. If a step was skipped,
  say it was skipped.

## 7. Anchor corrections (verified against HEAD 8cb9fab — resolve by symbol, confirm, then edit)

| Symbol / thing | Correct location | Blueprint said | Note |
|---|---|---|---|
| microstructure CTE (ALREADY EXISTS) | `storage/consensus.rs:1600-1609` in `refresh_router_followset` (`:1576`) | "new work" | docstring `:1569-1574` = "interim pending FORGE_PLAN_MM_FILTER's calibrated verdict" |
| migration number | **`040`** | `039` | `039_router_followset.sql` TAKEN — build-breaking if not renumbered |
| `TraderSliceStat` | `:2018` | `:1907` | ~111 lines off |
| `slice_pooled_quality` | `consensus_cycle.rs:111` | `trader_trust.rs` | wrong FILE |
| `.clamp(0.5,1.0)` Avoid idiom | `consensus_cycle.rs:77` & `:117` | `consensus.rs:76` | `:76` is `pub title: String` — wrong file |
| `trust_arms` | scanner `consensus.rs:765` | `:750` | off 15 |
| `active_portfolio` | `consensus_cycle.rs:979` | `:977` | off 2 |
| shadow test | `deep_pool_excluded_from_signals_shadow_differs` `:1410` | `:1398` | off 12 |
| `keep` closure | `consensus.rs:369` | `:361-363` | off 6 |
| `TraderVote` / `ConsensusParams` | `:31` / `:150` (`trusted_only:178`, `certified_only:189`) | `:30-69` / `:149-189` | close |
| `earned_quality` | fn `:70`, call `:648`, stamp `:646-672` | `:69/:646` | close |
| `quality_weight` | fn `:325` (rank20 = 1.6) | `:317-322` (=1.8) | value 1.6 not 1.8 |
| `laddering_one_wallet_counts_once` | scanner `consensus.rs:1069` | storage `:1028` | wrong file+line |
| default-behavior test `:1206` | is `sports_mode_filters_market` (`:1192`) | "default behavior test" | mislabeled — assert byte-identical via full suite green instead |
| migrations dir | `/migrations/` | `common/migrations/` | path |

Core SQL columns are ALL EXACT (verified): `trader_fills` has `wallet, condition_id, outcome_index,
side ('BUY'|'SELL'), size_usd, ts`; `advantage` is NULL-for-SELL; `idx_tf_wallet` / `idx_tf_cond_outcome`
at `026:46-47`. The core query is safe.

## 8. Rejected approaches (do NOT do these)
- **Rebuilding `wallet_microstructure` from scratch** — it exists; refactor/extend only.
- **Reporting a bare Tier-2 Δcorr as validation** — meaningless without the matched-subset null.
- **Computing the Tier-2 verdict from full history** — leaks; use early-period-only as-of.
- **Free-tuning 3 thresholds on ~40 labels** — overfits; freeze most, float ≤1, report LOO.
- **Overwriting `trader_type` / auto-deleting flagged wallets** — append-only + human-reviewed only.
- **Flipping `EXCLUDE_MM` or touching the live `strict` path** — Tue's call, post forward-proof.
- **Goal-seeking a GO** — INDETERMINATE is an acceptable, honest terminal outcome.
