# Long Autonomous Run — Reliable DECISION-TIME fill/ask capture (turn modeled ROI into realized ROI)

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace + Python), in a dedicated git worktree off
`feat/consensus-engine`. Gate-green + commit after EVERY phase; at the end `merge --no-ff`
into `feat/consensus-engine`, then bring it onto `main` (the deploy branch the launchd
autoupdater builds) via the sanctioned path so it redeploys.
Companion reading (same house style): `run-prompts/RUN-MARKET-RESID-HARDENING.md`,
`DATA-MODEL.md`, `migrations/030_consensus_entry_ask.sql`, `migrations/031_honest_paper_ledger.sql`.

---

## Philosophy — read first, it overrides everything
- **The one number that gates real money is realizable ROI, and today it is MODELED, not
  measured.** The honest-P&L panel computes entry as `COALESCE(entry_ask, initial_market_price
  + haircut)`. Live `ask_coverage = 0%` everywhere → EVERY strategy's ROI currently uses the
  `mid + 1% haircut` FALLBACK, never a real executable ask. This run replaces the assumption
  with a measured, decision-time CLOB best-ask so the ROI (and the $500-bankroll projection
  that rests on it) becomes something we can trust with actual capital.
- **Decision-time or it doesn't count.** A realizable entry is the ask a bettor could have
  hit AT THE ALERT (first detection), not an ask fetched hours later in housekeeping. The
  existing capture fires in `housekeeping.rs` whenever it next sees the open signal → LAGGED,
  and for `elite_fresh_fav` (median 3h to resolve) that lag corrupts the number. Capture the
  ask at the SAME instant `initial_market_price` (the decision-time mid) is set, so ask and
  mid are from one moment — mirrors the market_resid `first_features` decision-time discipline.
- **Pure instrumentation, never the live path.** Ask capture must NEVER change which signals
  fire, the tiering, the alert text, or any strategy's score. It only writes `entry_ask`
  (+ new measurement columns) on signals that would have fired anyway. Leak-free: set-once,
  `resolved = FALSE` guarded, pre-resolution only — exactly like `initial_market_price`.
- **Paper/measurement only. No wallet, no order placement, NO real money.** We are recording
  what the market WAS asking, not sending an order.
- **Extend, don't rebuild.** `fetch_best_ask`, `set_entry_ask`, the config knobs, the compose
  passthrough, and the housekeeping fallback ALL exist. Do not reimplement them — fix the
  capture POINT (decision-time), enable it, make it reliable + observable, then measure.

---

## The results that motivate this run (verified on the live prod DB, 2026-07-01)
`elite_fresh_fav` is the repo's real edge and the only strategy positive on every honest
filter at once — but its ROI is modeled:

| metric | value | note |
|---|---|---|
| surplus over blind | +8.1% (z 5.5, LB +5.7%) | event-clustered, real |
| **realizable ROI** | **+6.9% mean / +3.6% LB95** | **MODELED at mid+1% — the number this run must make real** |
| avg entry price | 0.90 (favorites) | real ask likely 0.90→0.92-0.95; the haircut is a GUESS |
| resolve time | median 3h | asks move fast → decision-time capture matters |
| ask_coverage | **0%** | capture is OFF; nothing realized yet |

If the real decision-time ask spread is materially worse than the assumed 1% haircut, the
+3.6% LB shrinks — and we need to know that BEFORE risking $500, not after.

---

## The gaps this run closes (from the live audit)
1. **Capture is DISABLED.** `CAPTURE_ENTRY_ASK` defaults `false` and the live container has
   it `false`. Nothing is ever written to `entry_ask`.
2. **When enabled, capture is LAGGED, not decision-time.** The only capture site is the
   housekeeping snapshot loop (`copy-trading-bot/src/cycles/housekeeping.rs`), which runs on
   open signals on its own cadence — it grabs whatever ask exists whenever it next runs, not
   the ask at first detection. `entry_ask` is meant to be the executable price a real bettor
   got at the alert.
3. **The real haircut is unmeasured.** We assume `mid + 1%`. Nothing records the actual
   ask−mid spread at decision time, so we can't validate (or replace) the 1% assumption, and
   can't prove capture happened at decision-time vs late.

---

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a synthetic smoke run.
Live-verify DB-touching changes on a **throwaway Docker Postgres** (own port, e.g. 55432;
apply migrations via the repo's `run_migrations`, exercise the path, inspect rows). Do NOT
touch the live prod stack (`polymarket-bot-postgres-1`, `polymarket-bot-copy-trading-bot-1`)
for verification. **Migrations are append-only; next free number is 032.** Env vars reach the
container ONLY via the `environment:` allowlist in `docker-compose.consensus.yml` (NOT
`env_file`) — `CAPTURE_ENTRY_ASK` / `ENTRY_ASK_MAX_PER_CYCLE` are already there; add any NEW
tunable as `VAR: ${VAR:-default}` and ALWAYS verify a config change reached the container.

---

## Context (extend, don't rebuild — verified `file:line`, current tree)
- `common/src/data/models.rs` — `fetch_best_ask(http, token_id) -> Result<Option<f64>>` (:322,
  GETs `{CLOB_API}/book?token_id=`, returns the LOWEST ask price in (0,1]; `Ok(None)` on empty
  book) and `Market::outcome_token_id(outcome_index) -> Option<&str>` (:293). **Both exist and
  are correct — reuse them; do not touch the fetch logic.**
- `common/src/storage/consensus.rs` —
  - `snapshot_consensus_signal(signal_id, net_count, n_backers, mean_price, market_price)`
    (~:410): inserts a snapshot row, then `UPDATE … SET last_market_price=$2,
    initial_market_price = COALESCE(initial_market_price,$2)` (:428-430). **This COALESCE-once
    UPDATE is the decision-time hook: the first market_price a signal ever sees becomes its
    `initial_market_price`. Capture the ask at THIS point.**
  - `set_entry_ask(signal_id, ask) -> Result<bool>` (:447): `UPDATE … SET entry_ask=$2 WHERE
    id=$1 AND entry_ask IS NULL AND resolved=FALSE` — set-once, resolved-guarded, leak-free.
    Returns whether newly written. **Reuse verbatim.**
  - `honest_pnl_by_strategy(exec_haircut, fee_pct)` (~:660): entry = `COALESCE(entry_ask,
    initial_market_price + $1)`; also reports `ask_coverage = ask_rows/resolved` (:633).
    Once `entry_ask` flows at decision-time, this panel becomes realized automatically.
  - `StrategyScore`/`HonestPnl` structs + the CLV block (`initial_market_price − mean_price`).
- `copy-trading-bot/src/cycles/housekeeping.rs` (:200-224) — the EXISTING lagged capture:
  `if cfg.capture_entry_ask && sig.entry_ask.is_none() && asks_captured < cfg.entry_ask_max_per_cycle
  && let Some(tid)=market.outcome_token_id(sig.outcome_index) { sleep(80ms); fetch_best_ask; set_entry_ask }`.
  Keep this as the FALLBACK for already-open signals that missed their detection moment, but
  it must be tagged lagged (see Phase 1) so the headline ROI can filter to decision-time only.
- `copy-trading-bot/src/cycles/consensus_cycle.rs` — `prefetch_markets` (:687, bounded by
  `cfg.market_prefetch_max`, throttled, `record_consensus_prefetch` timing at :276); the upsert
  loop that creates/updates signals; where snapshots/prices are recorded per cycle. **This is
  where NEW signals are born → the decision-time ask belongs here (or in the snapshot fn it
  calls), reusing the bounded/throttled prefetch pattern.**
- `copy-trading-bot/src/config.rs` — `#[config(env="CAPTURE_ENTRY_ASK", default=false)]` (:281),
  `#[config(env="ENTRY_ASK_MAX_PER_CYCLE", default=40)]` (:286). Both already in the compose
  allowlist. Add new knobs here with the same derive.
- `common/src/metrics.rs` — Prometheus registry + `record_consensus_*`; add ask counters/gauges here.
- `copy-trading-bot/src/board.rs` — `render_honest` panel (honest ROI, corrected LB, regimes,
  ask haircut note at ~:334). Surface ask coverage + realized-vs-modeled here.

---

## Rejected approaches (do not build these)
- **Placing real orders / any wallet or signing path.** We record the market's ask, we do not
  transact. No private keys, no order API, no real money — ever.
- **Replacing `mid + haircut` blindly.** Keep the fallback for rows without a real ask; only
  PREFER a real `entry_ask`. A missing ask must degrade to the modeled entry, never to a crash
  or a dropped signal.
- **Fetching an ask for every open signal every cycle.** That hammers the CLOB `/book` endpoint
  and can slow the alert cycle. Bounded + set-once + throttled only; decision-time for NEW
  signals, best-effort lagged for the backlog.
- **Letting ask capture gate/alter firing, tiering, scoring, or alert text.** It is write-only
  instrumentation on signals that already fired. If capture fails, the live path is byte-identical.
- **Editing `fetch_best_ask`'s parse/selection logic.** It already returns the lowest valid ask.

---

## Phase 0 — Reliability probe + honest doc (no behavior change)
Prove the fetch primitive works against the LIVE CLOB before wiring it in, and write down the
two gaps so the design is legible.
- Add a unit/integration test (or an `#[ignore]` live probe) that calls `fetch_best_ask` for a
  couple of known open token_ids and asserts a plausible ask in (0,1] (and `Ok(None)` on a
  bogus token). Confirm `/book` shape hasn't drifted.
- Document in `DATA-MODEL.md` (and the housekeeping capture comment) the CURRENT state:
  capture is default-OFF and, when on, LAGGED (housekeeping-only); the target is decision-time.
- No logic change. Gate, commit.

## Phase 1 — Decision-time ask capture (the core), additively + leak-free
**Goal:** capture the executable best-ask at the moment a signal is first detected (when
`initial_market_price` is set), set-once, resolved-guarded — so `entry_ask` is the price a
bettor could have hit at the alert.
- Migration `032_*.sql` (append-only, additive, nullable): add to `consensus_signals`
  `entry_ask_at TIMESTAMPTZ` (when the ask was captured) and `entry_ask_mid DOUBLE PRECISION`
  (the mid at the SAME instant). These let us (a) PROVE decision-time (`entry_ask_at ≈
  first_detected_at`) and (b) MEASURE the real haircut (`entry_ask − entry_ask_mid`), replacing
  the 1% guess. Do NOT alter/overwrite any existing column or the accrued rows.
- Extend `set_entry_ask` (or add a sibling `set_entry_ask_decision(signal_id, ask, mid)`) to
  also write `entry_ask_at = NOW()` and `entry_ask_mid = $mid` under the SAME set-once +
  `resolved=FALSE` guard (COALESCE-once semantics; never overwrite a decision-time capture).
- In the DETECTION path (`consensus_cycle.rs`, at/adjacent to where a new signal's
  `initial_market_price` is first set via `snapshot_consensus_signal`), for signals whose
  `entry_ask` is still NULL and that just fired, fetch `fetch_best_ask(http,
  outcome_token_id(outcome_index))` and write it via the decision-time setter, gated by
  `cfg.capture_entry_ask`. Reuse the existing bounded/throttled prefetch pattern
  (`market_prefetch_max`, the prefetch timing metric) so it can't blow the cycle budget.
- Keep the housekeeping capture as the FALLBACK for already-open backlog signals, but route it
  through the same setter so `entry_ask_at` is recorded there too (its lag will show as
  `entry_ask_at − first_detected_at`, letting the headline ROI filter to decision-time-only).
**Verify:** throwaway-PG — a new signal gets `entry_ask`, `entry_ask_at`, `entry_ask_mid` set
once at detection; a second capture attempt is a no-op; a post-resolution attempt is refused;
missing ask leaves all three NULL and the honest query falls back to mid+haircut. Gate, commit.

## Phase 2 — Reliability + observability (bounded, retry, measured)
**Goal:** capture as many decision-time asks as possible without hammering the API or slowing
alerts, and expose how well it's working.
- Retry-on-empty-book across cycles (already implicit via set-once + `Ok(None)` no-op — confirm
  a signal that had an empty book at detection gets a lagged fallback later, tagged by
  `entry_ask_at`). Bound decision-time fetches per cycle (reuse `entry_ask_max_per_cycle` or a
  new `ENTRY_ASK_DECISION_MAX_PER_CYCLE`) and keep the throttle; `log()` when capped.
- `common/src/metrics.rs`: add `entry_ask_captured_total` (decision vs lagged labels if easy),
  `entry_ask_fetch_failed_total`, an `entry_ask_spread` histogram (`entry_ask − entry_ask_mid`),
  and an `entry_ask_capture_lag_seconds` histogram (`entry_ask_at − first_detected_at`).
  Increment from the capture sites.
- Ensure a fetch failure/timeout NEVER blocks the alert path: best-effort, short timeout,
  errors logged and swallowed. Prove (test or reasoning) the live cycle is unaffected when the
  CLOB `/book` endpoint is down.
**Verify:** metrics endpoint exposes the new series; a throttled/capped run still completes and
logs the cap; simulated fetch failure leaves the signal alive with NULL ask. Gate, commit.

## Phase 3 — Enable + measure the realized-vs-modeled delta
**Goal:** turn it on and quantify how the real ask changes the ROI (the whole point).
- Add a query/method (sibling of `honest_pnl_by_strategy`) or extend the board's honest panel
  to show, per strategy: `ask_coverage`, median real haircut (`entry_ask − entry_ask_mid`,
  vs the assumed 1%), and honest ROI computed TWO ways — modeled (mid+haircut) vs realized
  (real decision-time `entry_ask` only, i.e. rows with `entry_ask_at` near `first_detected_at`)
  — side by side, event-clustered, with the corrected LB for each.
- Surface it on `board.rs` `render_honest` (a "realized" column + coverage/haircut line) so the
  delta is visible without SQL.
- Do NOT tune anything to the result; report it honestly. A realized ROI materially below the
  modeled +3.6% LB for `elite_fresh_fav` is a real, valuable finding (the haircut assumption
  was too kind) — surface it, don't hide it.
**Verify:** synthetic rows with known asks produce the expected modeled-vs-realized split;
board renders both. Gate, commit.

## Phase 4 — Merge, deploy, verify capture is real + decision-time
- `merge --no-ff` into `feat/consensus-engine`; then bring it onto `main` (the branch the
  launchd autoupdater builds/deploys) the same way the last integration reached main. Rebase
  onto the FRESH tip first (this repo is shared; another chat may have advanced it) and re-run
  the gate. Do NOT `docker compose up -d` by hand — let `scripts/consensus-autoupdate.sh`
  rebuild + redeploy on the HEAD advance (the sanctioned path).
- Set `CAPTURE_ENTRY_ASK=true` (and any new max) in `.env.consensus`, verify it reached the
  container (`compose exec … env | grep ENTRY_ASK`).
- **Post-deploy VERIFY (do not skip), report the numbers:** migration 032 applied; within a few
  cycles `entry_ask` coverage is climbing on NEW signals; `entry_ask_at ≈ first_detected_at`
  for decision-time captures (prove the lag is seconds/minutes, not hours); the real ask−mid
  spread distribution; and the realized vs modeled honest ROI + corrected LB for `elite_fresh_fav`
  and `favorite`. Arm/scoring paths unchanged; 0 restarts; cycle time sane.

---

## Acceptance
Every phase gate-green + committed; final `merge --no-ff` and deployed via the autoupdater.
Deliverables: decision-time `entry_ask` capture (set-once, resolved-guarded, leak-free) hooked
where `initial_market_price` is set, reusing `fetch_best_ask`/`set_entry_ask`; migration 032
adding `entry_ask_at` + `entry_ask_mid` (additive, accrued rows intact); a lagged housekeeping
FALLBACK for the open backlog, tagged by capture time; bounded/throttled fetching that never
slows or gates the live alert path; metrics for coverage/spread/lag/failures; a board panel and
query showing REALIZED vs MODELED ROI + the real haircut per strategy; `CAPTURE_ENTRY_ASK`
enabled and verified accruing in prod. The live firing/tiering/scoring paths are byte-identical
when no ask is captured. Paper/measurement only, no wallet, NO real money.

## Standing disciplines
Instrumentation only, never the live path; decision-time (capture the ask WHEN `initial_market_price`
is set), not lagged; leak-free (pre-resolution, set-once, `resolved=FALSE`, COALESCE-once);
missing ask degrades to the modeled entry, never a crash or dropped signal; bounded + throttled
CLOB `/book` fetches (respect the API); SQL/pool in `common`, cycle wiring in the binary;
migrations append-only (next 032); every new tunable in the compose `environment:` allowlist and
verified in the container; report REALIZED-vs-MODELED honestly (a worse-than-assumed haircut is a
finding, not a failure); commit per phase; `merge --no-ff` → main → autoupdater; NO real money.
