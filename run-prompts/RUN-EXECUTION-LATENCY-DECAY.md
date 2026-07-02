# Long Autonomous Run — Execution-Latency Decay & the Speed Budget

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot`. **Branch off the integration branch the launchd auto-updater
deploys** — check `scripts/consensus-autoupdate.sh` (`ENV_FILE`, the checked-out branch) and
recent merges; it is `feat/consensus-engine` unless it has been consolidated onto `main`
(the repo was recently merged to `main`). Work in a dedicated git worktree; gate-green +
commit after EVERY phase; at the end `merge --no-ff` back into that integration branch so the
auto-updater deploys it. Companion reading (same house style): `run-prompts/RUN-HONEST-PNL-TRACKER.md`,
`run-prompts/RUN-TRADING-BOT-EXPLOIT.md`, `DATA-MODEL.md`.

---

## 0. The one-sentence mission
Measure — **rigorously, confound-controlled** — how much of a consensus signal's edge is lost
per minute of delay after it fires, capture the **sub-5-minute** price trajectory needed to see
it, and turn that into a **speed budget**: per strategy, "you have ~X minutes before Y% of the
edge is gone → so you need [an auto-trader / a prompt manual process] and here's when to act."

The motto: **within-signal or it's a confound. A placebo must be flat. A number without a CI is
a guess. The output is a decision — how fast, and when — not a chart.**

---

## Why this run exists (the confound that broke the first look)
A naive "edge vs minutes-after-fire" query (bucket every price snapshot by minutes since
`first_detected_at`, average `outcome_won − market_price`) is **confounded**: late time-buckets
only contain markets that *happened* to resolve slowly, so "edge at 120 min" measures
long-lived markets, not "the same market, later." It produced a noisy, non-monotone curve that
even rose with time for `strict` — an artifact, not a signal. The ONLY honest way is
**within-signal**: track each signal's OWN edge at fixed offsets and average the *paired deltas*,
reporting how many signals survive to each offset. And the current snapshots are ~5 min apart
(housekeeping cadence), too coarse to resolve a 1–5 minute action window — so we must also
**capture a dense early-life trajectory** going forward.

## What we already know (verified — the anchors this run builds on)
- **Consensus does NOT grow after fire:** `initial_n_backers ≈ n_backers` (~3.1) at every time
  bucket out to 120+ min. So there is no "wait for more consensus" benefit — waiting only costs
  price. Optimize purely for promptness + fire-time selectivity.
- **A structural follower tax exists:** edge at the sharps' fill (`initial_mean_price`) is ~1–1.5
  pts higher than at our first observable mid (`initial_market_price`, i.e. CLV). No speed fixes
  that (we follow); speed protects the *rest* of the edge from further drift.
- **Leak-free by construction (preserve it):** selection never reads `outcome_won`; `outcome_won`
  is written only at resolution (`resolve_consensus_signal`, market closed); `initial_market_price`
  is captured only while OPEN. Every price used in a decay measurement MUST be pre-resolution.

---

## The rigorous method (implement exactly this)
Let a signal's fire time be `t0 = first_detected_at`, resolution `tR = resolved_at`, outcome
`w = outcome_won::int`. For offset `τ` minutes, `price(τ)` = the observed mid (Phase 0: also the
ask) nearest to `t0 + τ` from that signal's trajectory, defined only if `tR > t0 + τ` (still open).
- **Edge at offset:** `e(τ) = w − price(τ)`. **Fire edge:** `e0 = w − initial_market_price` (CLV
  anchor). **Paired decay:** `Δ(τ) = e(τ) − e0` (each signal is its own control — removes the
  resolution-time confound from the *delta*).
- **Curve:** for each `τ`, report `mean_event(Δ(τ))` (event-cluster by `COALESCE(event_slug,
  condition_id)`), a **bootstrap CI** (resample events), and **`n_surviving(τ)`** (how many signals
  were still open at `τ` — the honest, shrinking sample). Never plot a `τ` past where the sample
  is too thin (config `MIN_SURVIVORS`, default 20).
- **Two components, reported separately:** (a) the **structural tax** `e0 − (w − initial_mean_price)`
  (sharps' fill → our first mid — unavoidable); (b) the **delay decay** `Δ(τ)` (our first mid → `τ`
  later — what speed protects). Do NOT conflate them.
- **Placebo/QA:** recompute `Δ(τ)` with the per-signal offset→price mapping SHUFFLED (or with `w`
  permuted within band); a real decay curve trends, the placebo must be flat within CI. Ship the
  placebo result next to the real one every run.
- **Segment:** by strategy, price band (`width_bucket(initial_market_price,0,1,5)`), and horizon
  (same-day `<24h` vs multi-day) — decay differs for favorites vs mid-price and for fast vs slow
  markets.
- **Action window:** from the fitted curve, per strategy report `fire_edge`, `edge_half_life`
  (τ where half the *excess over the execution+fee breakeven* is gone), and `τ_breakeven` (τ where
  the edge net of the honest execution haircut hits zero). The **speed budget** = the τ at which a
  configured `EDGE_LOSS_TOLERANCE` (default 25%) of `e0` is gone. Then a verdict: compare the speed
  budget to a configured `ACHIEVABLE_LATENCY_MANUAL` (default 3 min) and `ACHIEVABLE_LATENCY_AUTO`
  (default 15 s) → "manual is fine" / "auto-trader materially worth it" / "needs low-latency auto."

---

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a smoke run on a tiny synthetic fixture.
Prefer **numpy only** (bootstrap + simple fits by hand) — do NOT add scipy unless already present
(`python3 -c "import scipy"`); avoid new deps. Live-verify DB changes on a **throwaway Docker
Postgres** (migrations via `run_migrations`, seed a fixture with a price trajectory + resolution,
run the analysis, inspect). **Migrations append-only — next free number = check `ls migrations/`.**
Every new tunable goes in the compose `environment:` allowlist as `VAR: ${VAR:-default}` AND is
verified in the container after deploy (env_file alone does NOT reach the container). Deploy ONLY
via the auto-updater script (a manual `docker compose up -d` is blocked as a prod deploy).

---

## Context (extend, don't rebuild — verified; grep to pin exact lines)
- `common/src/storage/consensus.rs` — `snapshot_consensus_signal` (writes `consensus_snapshots`
  {ts, net_count, n_backers, mean_entry, market_price}; sets `initial_market_price = COALESCE(...)`
  open-only); `consensus_trajectory(signal_id)` (reads the trajectory); `resolve_consensus_signal`
  (writes `outcome_won`, resolution only); the `insert_window_votes` UNNEST template for batch inserts.
- `copy-trading-bot/src/cycles/housekeeping.rs` — the per-cond loop (`fetch_clob_market`,
  `outcome_price` = mid, `outcome_won`, `snapshot_consensus_signal` in the still-open branch,
  ~120ms throttle, ~5-min cadence). The dense-capture task (Phase 0) mirrors this but for the
  early life of fresh tracked-strategy signals, and can capture the `/book` best-ask.
- `common/src/data/models.rs::ClobMarket` — `outcome_price(idx)` (mid), `tokens[].price`,
  `closed`, `outcome_won`. The CLOB `/book?token_id=` endpoint (see `scripts/fetch_data.py` +
  `common/src/model/features.rs::OrderBookStats`) yields best bid/ask for the executable price.
- `consensus_signals` columns: `first_detected_at`, `resolved_at`, `outcome_won`,
  `initial_market_price`, `initial_mean_price`, `mean_price`, `strategy`, `event_slug`,
  `condition_id`, `outcome_index`, `total_usd`.
- `copy-trading-bot/src/board.rs` — `render` (the HTML board on `BOARD_PORT` 9002); add the decay
  panel here, reading the analysis output JSON.
- `copy-trading-bot/src/config.rs` — `#[config(env=…, default=…)]` derive. `scripts/` — the Python
  analysis home (mirrors `train_market_resid.py` / `consensus_train.py`: argparse, `--input`
  fixture OR `$DATABASE_URL` via psycopg2, writes artifacts under `reports/` or `model/`).
- Scheduling/reliability: `~/Library/LaunchAgents/com.tue.consensus.*.plist` +
  `scripts/consensus-autoupdate.sh` — the launchd pattern (RunAtLoad + StartInterval) to add a
  periodic analysis re-run agent, and `caffeinate` keeps the host awake. DB persists in `pgdata`.

---

## Rejected approaches (do not build these)
- **The pooled/aggregate curve** (bucket all snapshots by minutes-after-fire). It's the confound
  this run exists to fix. Within-signal paired deltas + surviving-N only.
- **Claiming a decay rate without a placebo + CI.** A curve that the shuffled placebo reproduces
  is noise. Always ship real-vs-placebo and bootstrap CIs.
- **Conflating the follower tax with delay decay.** Report the sharps-fill→our-mid gap and the
  our-mid→τ decay as two separate, labeled quantities.
- **Unbounded dense capture.** Cap concurrent dense-tracked signals + per-cycle fetches + the
  capture window; flag-gated default OFF. Never let it grow cycle time or hammer the API.
- **New deps / scipy / a live betting arm.** numpy-only stats; read-only analytics; no real money.
- **Touching selection/alerting/betting.** Pure additive capture + read-only analysis. Live path
  byte-identical with flags off.

---

## Phase 0 — Dense early-life price + ask capture (the sub-5-min data foundation)
**Goal:** for fresh tracked-strategy signals, record a dense mid (and executable ask) trajectory
over the first minutes, so the decay curve can resolve a 1–5 min window. Additive, bounded,
flag-gated default-OFF; forward-only (helps future analysis; existing 5-min data still analyzed).
- Migration (next free): `signal_price_trajectory (id, signal_id BIGINT REFERENCES
  consensus_signals(id) ON DELETE CASCADE, ts TIMESTAMPTZ, secs_after_fire INT, mid DOUBLE
  PRECISION, ask DOUBLE PRECISION, n_backers INT)`, index on `(signal_id, secs_after_fire)`. (Or
  extend `consensus_snapshots` with `ask` + a denser source — a new table is cleaner and bounded.)
- A dense-capture task (new interval task in `live.rs`, or a sub-loop in the cycle): for signals
  whose `first_detected_at` is within `DENSE_WINDOW_MINS` (config, default 15) and strategy ∈
  `DENSE_STRATEGIES` (default the actionable set), fetch the CLOB mid + `/book` best-ask every
  `DENSE_INTERVAL_SECS` (default 45), bounded by `DENSE_MAX_SIGNALS` concurrent (default 40) and a
  per-tick fetch cap; throttled; best-effort (a failure just skips). Stop capturing a signal once
  it resolves or leaves the window.
- Config: `DENSE_CAPTURE` (default false) + the four knobs above; add all to the compose
  `environment:` allowlist.
**Verify:** throwaway-PG — with the flag ON and a seeded fresh signal, rows land at ~45s spacing
with mid+ask and correct `secs_after_fire`; cascade removes them with the signal; with the flag
OFF, no rows and the cycle path is unchanged. Gate, commit.

## Phase 1 — The rigorous decay analysis (`scripts/decay_analysis.py`) + speed budget
**Goal:** the confound-controlled instrument that turns trajectories into a trustworthy decay
curve + action window.
- Read from `$DATABASE_URL` (psycopg2) OR `--input fixture.json`. For each resolved signal, build
  its offset→price series from `signal_price_trajectory` (dense, preferred) falling back to
  `consensus_snapshots` (5-min), plus `initial_market_price`/`initial_mean_price` and `outcome_won`.
- Implement the METHOD above exactly: paired `Δ(τ)` on a fixed offset grid (e.g. 0.5,1,2,3,5,10,
  15,30,60 min), event-clustered mean, **numpy bootstrap CI** (resample events, e.g. 2000 draws),
  `n_surviving(τ)`, the **placebo** (shuffled offset→price and/or permuted `w`), the two components
  (structural tax vs delay decay), and segmentation (strategy × band × horizon).
- Compute per strategy: `fire_edge`, `edge_half_life`, `τ_breakeven` (net of `EXEC_HAIRCUT`+
  `FEE_PCT`), the **speed budget** (τ losing `EDGE_LOSS_TOLERANCE` of `e0`), and the auto-vs-manual
  **verdict** (speed budget vs `ACHIEVABLE_LATENCY_*`).
- Write `reports/decay_report.json` (curves + CIs + surviving-N + placebo + per-strategy speed
  budget + verdict + `generated_at`, resolution source, dense-coverage %) and a plain-text summary
  to stdout. numpy-only.
**Verify:** synthetic fixture with a KNOWN injected decay → the script recovers it within CI and
the placebo is flat; a no-decay fixture → real curve ≈ placebo ≈ 0. Coarse (5-min) vs dense inputs
both run; the report flags which resolution it used. Gate (`py_compile` + smoke), commit.

## Phase 2 — Surfacing + automated, reliable re-run
**Goal:** the speed budget is always-current and legible; the analysis runs itself.
- `copy-trading-bot/src/board.rs`: a "Speed Budget / Latency Decay" panel reading
  `reports/decay_report.json` — per strategy: fire edge, structural tax, the decay curve as a small
  inline sparkline (edge vs minutes) with the CI band, `n_surviving`, the speed-budget minutes, and
  the auto-vs-manual verdict; plus a one-line headline ("`favorite`: ~X min before 25% of edge is
  gone → [verdict]"). Clearly label read-only / paper. Fail-soft if the JSON is missing/stale
  (show "analysis pending").
- Automate the re-run: a launchd agent `com.tue.consensus.decay` (RunAtLoad + StartInterval, e.g.
  hourly) running `scripts/decay_analysis.py` against the prod DB and writing the JSON the container
  can read (a bind-mounted `reports/` dir, or write into the DB and have the board read from there —
  pick the simplest reliable path and document it). Idempotent, best-effort, logs to a file like the
  auto-updater. Ensure it survives restarts (RunAtLoad) and the host stays awake (existing caffeinate).
**Verify:** the board renders the panel from a fixture report; the launchd agent runs the script and
refreshes the JSON; a stale/missing report degrades gracefully. Gate, commit.

## Phase 3 — QA, reliability, merge, deploy, verify
- QA gates baked in: assert the placebo is flat within CI on real data before publishing a decay
  claim; assert `n_surviving` monotonically non-increasing and never below `MIN_SURVIVORS` in
  published buckets; assert the structural-tax and delay-decay components sum consistently; unit-test
  the Rust panel rendering + fail-soft. Confirm read-only + non-regressive: with `DENSE_CAPTURE=false`
  and no report present, live `strict`/alerting is byte-identical (existing passthrough tests + a
  "no dense rows written when off" check).
- Final `merge --no-ff` into the integration branch; deploy via the auto-updater script.
- **Post-deploy VERIFY (do not skip):** new env vars in the container; migration applied; dense
  capture writing rows (if enabled) at the right cadence; the launchd decay agent producing a fresh
  `decay_report.json`; the board panel live; ingestion + 0 restarts intact; cycle time sane. **Report
  the first real speed budget** per strategy (fire edge, structural tax, minutes-until-25%-gone,
  auto-vs-manual verdict) with its CI and surviving-N — the actual answer to "how fast, and when."

---

## Acceptance
Every phase gate-green + committed; final `merge --no-ff`. Deliverables: bounded, flag-gated dense
mid+ask capture; a numpy-only, confound-controlled within-signal decay analysis with bootstrap CIs,
surviving-N transparency, a placebo, the structural-tax vs delay-decay split, and per-strategy ×
band × horizon segmentation; a per-strategy **speed budget** + auto-vs-manual verdict; a board panel
+ a self-running launchd re-run; all read-only, default-safe, non-regressive, self-healing. The
output is a trustworthy decision — how important speed is, how fast to act, and when — not a noisy
chart. Paper/alert-only, NO real money.

## Standing disciplines
Within-signal paired deltas (never the pooled confound); a placebo beside every claim; bootstrap
CIs + surviving-N always shown; structural follower-tax reported separately from delay decay;
leak-free (outcome as label only, prices strictly pre-resolution); numpy-only, no new deps; dense
capture bounded + flag-gated + default-OFF; read-only + non-regressive (live path byte-identical);
promotion/verdict logic explicit and testable; migrations append-only (next free number); every new
tunable in the compose `environment:` allowlist and verified in the container; commit per phase;
`merge --no-ff` at the end; deploy via the auto-updater; NO real money.
