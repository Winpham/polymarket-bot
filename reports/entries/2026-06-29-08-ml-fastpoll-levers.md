# 08 — ML cross-check arms + every-minute polling + CLV (the "levers" run)

**Date:** 2026-06-29   **Branch:** `lever/ml-fastpoll` → merged to `feat/consensus-engine`

This run makes highest use of the repo's two unused assets — the ML ensemble /
pure-Rust `XgbModel` + Bayesian anchoring, and "every-minute" polling — integrating
them into the consensus engine and letting the **existing belief-blind promotion
gate** forward-test them. Built in six gate-green phases, committed per phase.

## Discipline (unchanged, and the whole point)
The generator is bold: **every** ML path is built and given a fair forward test —
none pre-judged, none tuned to look good. Skepticism lives **only** at the gate
(`scanner/promotion.rs`: surplus-over-blind, event-clustered, Bonferroni, ≥30-event
floor). Every arm is **silent** (`alerting=false`), **default-OFF**, **forward-only**
(respects `trained_through`), uses **free** data, and is **paper/alert-only**. With
nothing enabled the live `strict` path + 14 core strategies are byte-identical.

## What shipped

### Phase 0 — CLV instrumentation (measurement)
Two event-clustered columns on `consensus_scoreboard_by_strategy`, over resolved
rows with a captured `initial_market_price`:
- `our_clv = AVG_event(outcome_won − initial_market_price)` — edge if we'd entered
  at the first live mid we saw.
- `capture_lag = AVG_event(initial_market_price − mean_price)` — gap between the mid
  when we *noticed* and the price the sharps paid. **Materially negative ⇒ faster
  polling has real value.** Rendered on the `:9002` board + `/consensus`.

### Phase 1 — enabling refactor
`xgb.rs` + `bayesian.rs` moved into `polymarket-common` (`model::xgb`, `model::bayesian`);
the trading bot re-exports them, so the consensus path (which depends only on
`common`) can reuse them. Pure code move, tests moved with them.

### Phase 2 — L1 every-minute incremental polling
Per-trader `consensus_polled_at` cursor + a `consensus_vote_window` store
(migration 025). Each cycle polls only the **delta** since the cursor, appends it
(dedup on the atom key), stamps the cursor (only on a successful insert → self-
healing), prunes older than the window, and **rebuilds books from the stored
window** — book assembly moves off the network onto an indexed DB read. Behind
`CONSENSUS_INCREMENTAL` (default true); the legacy path is retained and **both
share one `books_from_window_votes` builder**, so books are equivalent and `strict`
is non-regressive. `CONSENSUS_INTERVAL_MINS=1` in compose.

### Phase 3 — enricher seam + Bonferroni family split
`scanner/enrich/` — `EnrichCtx{now, models, margins, markets}`, an `Enricher` fn
registry, and `enrich_all` called once in `consensus_cycle`. `family(strategy)`
tags **experimental** arms vs the **core** portfolio; the gate's Bonferroni
denominator is computed **per family** at both call sites, so adding arms never
tightens core's (incl. `strict`'s) bar.

### Phase 4 — the arms (build ALL; each silent, forward-tested)
| Arm | What it does | Needs |
|-----|--------------|-------|
| `consensus_logit` | logistic on our OWN signal features → keeps strict picks where `p_win − price > margin` | `model/consensus_win.json` |
| `consensus_ens` | same selection via the pure-Rust XGBoost ensemble | `model/consensus_ens.json` |
| `market_ml` / `market_veto` | imported market-outcome XGBoost (Gamma + CLOB mid + price-history per strict market, deduped/throttled) — confirm vs strong-disagree | `model/xgb_model.json` |
| `bayes_anchor` | prior = live CLOB mid, evidence = consensus conviction LR (+ logit LR) → posterior beats mid | none (live mid) |

Each re-emits a strict pick cloned under its tag at WATCH (can never alert) and is
judged by the gate in the experimental family. Each no-ops unless its flag is ON
**and** its model loads.

### Phase 5 — training + verification
- `scripts/consensus_train.py`: reads resolved `_blind` rows (features + `outcome_won`,
  grouped by event), trains the logistic (`consensus_win.json`) + XGBoost
  (`consensus_ens.json`) with `GroupKFold(event)` (leak-free), reports OOF AUC/Brier,
  stamps `trained_through`. `--input fixture.json` for dry runs.
- `market_ml` uses the existing `fetch_data.py` → `train_model.py` → `xgb_model.json`.
- `Dockerfile.consensus` bakes `model/` (placeholder tracked; trained JSONs local).

## How to enable an arm (deliberate)
1. Train: `python3 scripts/consensus_train.py --out-dir model` (after `_blind` rows
   resolve), and/or `fetch_data.py`+`train_model.py` for the market model.
2. Set the flag in `.env.consensus` (e.g. `CONSENSUS_ARM_LOGIT=true`). See
   `.env.consensus.example` + `model/README.md`.
3. Watch the `:9002` board: the arm appears in the *experimental* family with its
   own surplus, lower bound, CLV, and ⏳/✅ gate verdict.

## Verified
- CLV SQL + math on a throwaway Postgres (Phase 0).
- Window store: `#[ignore]`d live-DB integration test — UNNEST batch insert + dedup
  (NULL array elements), `since`-cutoff load, prune, cursor round-trip (Phase 2).
- Arm emit logic: pure unit tests (logit + bayes: silent WATCH rows, margin gate,
  forward guard, no-op when disabled/absent); passthrough test proves non-regression.
- End-to-end (`arm_pipeline_e2e`, ignored): trained `consensus_win.json` +
  `consensus_ens.json` **load in Rust** (Python→Rust format compat), the logit arm
  emits from the real model, and arm-tagged resolved rows appear in the scoreboard
  with CLV + a **per-family** gate verdict that's no tighter than pooling.
- Full gate (`fmt --check`, `clippy -Dwarnings`, `test`) green at every phase;
  `consensus_train.py` `py_compile` + smoke run on a synthetic fixture.

## The honest note
Nothing here is an edge claim. The Foresight CS2-*prediction* null is **not**
evidence about this domain (Polymarket leaderboard-*consensus*), so every path was
built and given a fair forward test. As silent forward data accrues, the belief-
blind gate — surplus over the blind baseline, event-clustered, Bonferroni-corrected,
≥30 distinct events — decides which arm (if any) has edge. Promotion to alerting
stays a deliberate human call. No real money.
