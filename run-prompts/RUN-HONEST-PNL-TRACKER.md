# Long Autonomous Run — the Honest P&L Tracker (CLV-based, execution-haircut, multi-regime)

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace + Python), in a dedicated git worktree off
`feat/consensus-engine`. Gate-green + commit after EVERY phase; at the end
`merge --no-ff` into `feat/consensus-engine` so the launchd auto-updater deploys it.
Companion reading (same house style): `run-prompts/RUN-TRADING-BOT-EXPLOIT.md`,
`run-prompts/RUN-MARKET-RESID-HARDENING.md`, `DATA-MODEL.md`, `model/README.md`.

---

## 0. The one-sentence mission
Build a **durable, read-only "honest P&L" instrument** that measures the edge we could
*actually realize* — outcome vs the **price we observed while the market was open**
(`initial_market_price`, i.e. CLV), minus an **explicit execution haircut** (spread +
slippage + fees), event-clustered, **broken out by regime / price-band / horizon**, with a
**conservative go/no-go verdict for a real-money pilot** and a **paper equity curve** — so the
system's success becomes a trustworthy, self-updating signal we can act on and iterate from,
instead of a hand-run SQL query over a 1.7-day snapshot.

The motto: **realizable, not flattering. Persistent across regimes, not pooled. Read-only and
self-healing. A false "GO" is worse than a false "HOLD."**

---

## Philosophy — read first, it overrides everything
- **CLV is the truth; `edge` overstates it.** The live board's headline `edge = outcome_won −
  mean_price` measures the outcome against the SHARPS' average fill (`mean_price`) — a price we
  cannot get. The honest, realizable number is **CLV = outcome_won − `initial_market_price`**,
  the first live mid WE observed while the market was open (verified leak-free: see §"Why this
  is blind"). This run makes CLV-minus-execution the PRIMARY metric everywhere it reports.
- **Realizable means net of execution.** We buy at the ASK, not the mid, and we pay slippage
  (and any fee). The tracker applies an explicit, conservative, configurable haircut on top of
  CLV — and, where captured, the real book ask. We never report a gross edge as if it were
  spendable.
- **One regime is not evidence.** The current record is ~1.7 days of mostly same-day sports.
  The tracker must show whether an edge PERSISTS across day/week regimes, price bands, and
  horizons — a strategy that is only +EV in one band or one weekend is fragile, not bankable.
- **The gate is conservative and belief-blind.** "Pilot-ready" requires the Bonferroni-
  corrected honest-CLV lower bound to clear an execution-aware threshold, over a distinct-EVENT
  floor, AND positive across most recent regimes, AND enough market liquidity to place a
  minimum stake. A false GO risks real money; default to HOLD.
- **Read-only, non-regressive, self-healing.** The tracker only READS resolved rows + captured
  pre-resolution prices; it NEVER touches selection, alerting, betting, or the live `strict`
  path. With it present, live behavior is byte-identical. It computes automatically in-cycle,
  persists to Postgres, and survives restarts like the rest of the ingestion.
- **This is iteration fuel.** Beyond a number, the tracker must DECOMPOSE the edge (which
  bands / sports / horizons / backer-quality carry it), DETECT decay (rolling CLV trend), and
  SIZE capacity (how much can be deployed before the edge erodes) — so we know what to promote,
  prune, and improve next. Paper/alert-only. NO real money placed by this system.

---

## Why this is blind (verified — do not re-derive, but preserve it)
The measurement is leak-free by construction; every new query must keep it that way:
- **Selection never sees the outcome.** `copy-trading-bot/src/scanner/consensus.rs` (the
  scoring/`strict`-firing path) has ZERO references to `outcome_won`/`resolved`/`winner`.
- **`outcome_won` is a label, written once at resolution.** Only
  `common/src/storage/consensus.rs::resolve_consensus_signal` sets it, and housekeeping only
  calls it when `market.closed` (`ClobMarket::outcome_won` returns `None` unless closed).
- **`initial_market_price` is captured only while OPEN.** In
  `copy-trading-bot/src/cycles/housekeeping.rs`, the price snapshot
  (`snapshot_consensus_signal`, which does `initial_market_price = COALESCE(initial_market_price,
  $price)`) runs ONLY in the still-open branch (`market.outcome_won(idx) == None`). Once closed,
  we resolve and never touch the price. So CLV is outcome vs a genuinely pre-resolution mid.
Keep these invariants: the tracker reads `outcome_won` for scoring ONLY, always paired with a
price captured before resolution. Never introduce a post-resolution price into an entry field.

---

## The honest metrics (exact definitions — implement these, event-clustered)
Let `p0 = initial_market_price` (mid we saw while open), `w = outcome_won::int`, and
`band = width_bucket(p0, 0, 1, 5)`.
- **CLV (mid, realized):** `clv_share = w − p0`. Event-cluster: average within
  `COALESCE(event_slug, condition_id)` first, then across events (the within-match leak fix).
- **Execution haircut:** we buy at `entry = p0 + h`, where `h` = the captured half-spread if
  available (Phase 2), else `EXEC_HAIRCUT` (config, price units, default 0.01 = 1¢) — buy-side
  only. Optionally add `FEE_PCT` (config, Polymarket fee ≈ 0 today).
- **Honest realizable edge / ROI (per $ staked):**
  `honest_edge_share = clv_share − h`;  `honest_roi = honest_edge_share / entry − FEE_PCT`.
  (Buying `1/entry` shares per $1; each pays `w`; EV per $ = `(w − entry)/entry`.)
- **Confidence:** event-clustered mean + `STDDEV_SAMP` of per-event `honest_roi`; reuse the
  binary's `promotion.rs` machinery (`surplus_bounds` / the probit-based corrected lower bound)
  with the Bonferroni denominator = the strategy family size. **All promotion math stays in the
  binary; no probit-in-SQL.**
- **Regime consistency:** the same honest_roi computed per day-bucket (`date_trunc('day',
  resolved_at)`); report `regimes_positive / regimes_total` over the last N days.
- **Capacity:** `median_sharp_usd` (median `total_usd`) as a liquidity proxy;
  `suggested_stake = min(FLAT_STAKE, CAPACITY_FRAC × median_sharp_usd)`;
  `working_capital ≈ bets_per_day × (avg_hours_to_resolve/24) × suggested_stake`;
  `projected_weekly = bets_per_week × suggested_stake × honest_roi`.
- **Pilot-ready (GO) iff ALL:** corrected `honest_roi` lower bound > `MIN_PILOT_ROI`
  (config, default 0.02) AND `distinct_events ≥ PILOT_MIN_EVENTS` (default 50) AND
  `regimes_positive ≥ ceil(REGIME_FRAC × regimes_total)` (default 0.7, ≥ `PILOT_MIN_REGIMES`
  days, default 5) AND `median_sharp_usd ≥ MIN_LIQUIDITY_USD` (default 2000). Else HOLD with the
  binding reason.

---

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a smoke run. Live-verify DB changes on a
**throwaway Docker Postgres** (apply migrations via `run_migrations`, seed a small fixture with
resolved rows + `initial_market_price` set, exercise the queries, inspect output). **Migrations
append-only — use the next free number (`ls migrations/`; 028 is the last committed. If the
market_resid hardening run already merged its 029, use the next unused).** Every new tunable
goes in the compose `environment:` allowlist as `VAR: ${VAR:-default}` AND is verified in the
container after deploy (env_file alone does NOT reach the container).

---

## Context (extend, don't rebuild — verified, current tree; grep to pin exact lines)
- `common/src/storage/consensus.rs` — `consensus_scoreboard_by_strategy` (the existing
  surplus+CLV query; `our_clv = AVG_event(w − initial_market_price)`, `capture_lag =
  AVG_event(initial_market_price − mean_price)`, `band = width_bucket(mean_price,0,1,5)`);
  `StrategyScore` struct (the row type — extend or add a sibling `HonestPnl` struct);
  `resolve_consensus_signal` (writes `outcome_won`, resolution only);
  `snapshot_consensus_signal` (`initial_market_price = COALESCE(...)`, open-only);
  `insert_window_votes` (UNNEST template to copy for any batch insert).
- `copy-trading-bot/src/cycles/housekeeping.rs` — the resolve/snapshot loop (`fetch_clob_market`
  per cond, `outcome_price`, `outcome_won`, `snapshot_consensus_signal`); this is where an
  optional **book-ask capture** (Phase 2) belongs, and where a post-resolution **ledger append**
  can hook. `common/src/data/models.rs::ClobMarket` (`outcome_price`, `outcome_won`, `closed`,
  `tokens[].price`); the CLOB `/book?token_id=` endpoint (see `scripts/fetch_data.py` +
  `common/src/model/features.rs::OrderBookStats`) gives best bid/ask for a real spread.
- `copy-trading-bot/src/scanner/promotion.rs` — `promotion_verdict`, `surplus_bounds`, private
  `probit`, `PromotionParams {min_events, margin, alpha}`. REUSE this for the corrected honest
  lower bound (extend params if needed; keep probit private to this module).
- `copy-trading-bot/src/scanner/enrich/mod.rs::family` — the experimental/core split + the
  strategy family; the Bonferroni denominator source.
- `copy-trading-bot/src/board.rs` — `render` builds the HTML scoreboard (per-family Bonferroni
  denominator from rows-present; `promotion_verdict` per row; gate emoji). Add the honest-P&L
  panel + equity sparkline here; it's served on `BOARD_PORT` (9002).
- `copy-trading-bot/src/cycles/consensus_cycle.rs` — the 1-min cycle; `crate::metrics::*` calls;
  the ntfy push pattern (`if let Some(n) = ntfy { n.push(title, msg, priority, tags).await }`)
  for the digest. `common/src/ntfy.rs::Ntfy` (the phone-push channel; topic already configured).
- `common/src/metrics.rs` — Prometheus registry + `record_consensus_*`; add honest-P&L gauges.
- `copy-trading-bot/src/config.rs` — `#[config(env=…, default=…)]` derive; existing
  `SLIPPAGE_PCT` (0.01), `FEE_PCT` (0.02). Add the tracker knobs here.
- `docker-compose.consensus.yml` — `copy-trading-bot.environment:` allowlist (add every new
  knob as `${VAR:-default}`). `scripts/consensus-autoupdate.sh` — the sanctioned deploy path
  (RunAtLoad + every 300s; do NOT `docker compose up -d` by hand — it's blocked as a prod deploy).

---

## Rejected approaches (do not build these)
- **Reporting `edge` (vs `mean_price`) as the headline.** That's the sharps' fill, not ours.
  CLV-minus-haircut is the headline; show `edge` only as a secondary "sharp benchmark" column.
- **Pooling all history into one number.** Always event-cluster AND break out by regime/band/
  horizon; a pooled figure hides the fragility the tracker exists to expose.
- **A "GO" from one hot regime.** No pilot-ready without multi-regime persistence + the
  corrected lower bound + a liquidity floor. Conservative by design.
- **Touching the live path.** No change to selection, alerting, betting, or the arms. The
  tracker is pure read-only analytics + its own ledger table. Everything default-safe.
- **probit-in-SQL / promotion math in the DB.** Keep the SQL to sums/means/stddev/percentiles;
  do the corrected-bound + verdict in the binary (`promotion.rs`).
- **A live real-money betting arm.** Out of scope and against the standing rule. The ledger is
  a PAPER simulation only.

---

## Phase 0 — Honest-P&L query + config (the instrument core; read-only)
- `common/src/storage/consensus.rs`: add `honest_pnl_by_strategy(&self) -> Result<Vec<HonestPnl>>`
  and a `HonestPnl` row (strategy, resolved, distinct_events, hit_rate, clv_share, clv_roi,
  honest_edge_share, honest_roi, honest_roi_sd (per-event), median_sharp_usd, avg_hours_to_resolve,
  bets_per_day, sharp_edge (the old `edge`, for reference)). SQL: event-cluster `honest_roi`
  using `initial_market_price` + the `EXEC_HAIRCUT`/`FEE_PCT` passed as binds; exclude `_blind`;
  require `resolved AND initial_market_price IS NOT NULL`.
- `copy-trading-bot/src/config.rs`: `EXEC_HAIRCUT` (default 0.01), `FEE_PCT` (reuse),
  `FLAT_STAKE` (default 100.0), `CAPACITY_FRAC` (default 0.05), `MIN_PILOT_ROI` (default 0.02),
  `PILOT_MIN_EVENTS` (default 50), `PILOT_MIN_REGIMES` (default 5), `REGIME_FRAC` (default 0.7),
  `MIN_LIQUIDITY_USD` (default 2000). Add each to the compose `environment:` allowlist.
**Verify:** throwaway-PG fixture (a few strategies, resolved rows with `initial_market_price`,
varied bands): `honest_roi` = `clv_share − haircut over entry`, event-clustered; `_blind`
excluded; a hand-computed row matches. Gate, commit. (No live-path change; read-only.)

## Phase 1 — Regime / band / horizon breakdown + corrected verdict in the binary
- `common/src/storage/consensus.rs`: add `honest_pnl_segments(&self)` returning per (strategy ×
  segment) honest_roi + n_events, for segments = day-regime (`date_trunc('day',resolved_at)`),
  price-band (`width_bucket(initial_market_price,0,1,5)`), and horizon
  (`same_day` if `hours_to_resolve < 24` else `multi_day`).
- `copy-trading-bot/src/scanner/promotion.rs` (or a new `honest.rs` sibling in the binary):
  `pilot_verdict(honest_roi, sd, distinct_events, regimes_positive, regimes_total,
  median_sharp_usd, n_family, &params) -> PilotVerdict {go: bool, corrected_lower_bound, reason}`
  reusing the probit/`surplus_bounds` machinery + the GO conditions above. Pure, unit-tested.
**Verify:** unit tests — a strong+consistent strategy earns GO; the same edge in ONE regime
returns HOLD ("regimes 1/6 < floor"); below the event floor HOLD; thin liquidity HOLD; the
corrected bound tightens with the family size. Gate, commit.

## Phase 2 — Real book-ask capture (precision upgrade; additive, bounded)
- Migration (next free number): add `entry_ask DOUBLE PRECISION` (nullable) to
  `consensus_signals` — the executable buy price captured ONCE while open.
- `housekeeping.rs`: in the still-open branch, once per signal (COALESCE-once, like
  `initial_market_price`), fetch the CLOB `/book` for the outcome token and store the best ask
  (throttled; best-effort; a failure just leaves it NULL → the query falls back to the
  `EXEC_HAIRCUT` heuristic). Bound the extra fetches (only for signals whose `entry_ask IS NULL`
  and only for tracked strategies, capped per cycle).
- Honest query: prefer `entry_ask` when present (`entry = COALESCE(entry_ask, initial_market_price
  + EXEC_HAIRCUT)`), so the haircut becomes market-real where captured. Report coverage
  (`% rows with a real ask`).
**Verify:** throwaway-PG — `entry_ask` set once and not overwritten; the query uses it when
present and the heuristic when NULL; cascade/İnvariants intact. Gate, commit. (If the `/book`
fetch proves too costly at prod scale, keep it OFF behind a `CAPTURE_ENTRY_ASK` flag default
false and rely on the heuristic — document the trade-off.)

## Phase 3 — Paper equity ledger (the ongoing realization / track record)
- Migration (next free): `honest_paper_ledger (id, strategy, condition_id, outcome_index,
  resolved_at, stake, entry, outcome_won, pnl, cum_equity, UNIQUE(strategy,condition_id,outcome_index))`.
- On resolution (`housekeeping.rs`, after `resolve_consensus_signal`), for each tracked strategy
  (config `LEDGER_STRATEGIES`, default the family) append a paper bet: `stake = suggested_stake`
  (or `FLAT_STAKE`), `entry = COALESCE(entry_ask, initial_market_price + EXEC_HAIRCUT)`,
  `pnl = stake × (outcome_won − entry)/entry`; maintain `cum_equity` per strategy. Idempotent
  (ON CONFLICT DO NOTHING — resolve fires once).
- `common/src/storage/consensus.rs`: `equity_curve(strategy)` + `ledger_stats(strategy)` →
  cumulative P&L, peak, max drawdown, daily-returns mean/sd → a Sharpe-like ratio, win rate,
  bets, ROI on turnover.
**Verify:** throwaway-PG — resolving N seeded signals appends N ledger rows with a correct
cumulative curve; re-running resolution does NOT double-append; drawdown/Sharpe compute. Gate,
commit.

## Phase 4 — Surfacing: board panel + minimal-noise digest
- `board.rs`: an "Honest P&L" panel — per strategy a card with honest ROI (± corrected bound),
  CLV vs sharp-edge, hit%, distinct events, regimes-positive, GO/HOLD (+reason), median sharp $,
  suggested stake, working capital, projected $/week, and an equity-curve sparkline + max
  drawdown. Sort by GO then honest lower bound. Clearly label everything "realizable / paper".
- A scheduled digest (daily; optional weekly deep-dive) pushed to ntfy — **minimal-noise**: send
  ONLY on material change (a strategy crosses INTO or OUT of GO; a promoted strategy's rolling
  CLV decays past a threshold; a ledger drawdown breach). No push when nothing changed. Reuse
  the `Ntfy` channel + the existing push pattern; gate it behind `HONEST_DIGEST=true`
  (default false) so it's opt-in and silent by default.
**Verify:** board renders the panel from fixture data; the digest fires exactly on a simulated
GO-crossing and stays silent otherwise. Gate, commit.

## Phase 5 — Reliability, automation, deploy, verify
- Compute the honest tables on a sensible cadence (piggyback the existing cycle or a dedicated
  interval; the ledger appends at resolution). Ensure it is READ-ONLY w.r.t. the live path and
  fully idempotent; with all new flags at defaults the live `strict`/alerting path is
  byte-identical (assert via the existing passthrough tests + a new "tracker off ⇒ no writes"
  check).
- Final `merge --no-ff` into `feat/consensus-engine`; deploy via the autoupdater script (not a
  manual compose up). **Post-deploy VERIFY (do not skip):** new env vars in the container,
  migrations applied, the board panel renders live, the ledger begins appending as markets
  resolve, ingestion + 0 restarts intact, cycle time sane. Report the first real honest-P&L
  table (CLV-based, haircut-applied) and each strategy's GO/HOLD with its binding reason.

---

## Acceptance
Every phase gate-green + committed; final `merge --no-ff`. Deliverables: a read-only
`honest_pnl_by_strategy` (CLV-based, execution-haircut, event-clustered) + segment breakdown;
a conservative binary-side `pilot_verdict` (corrected lower bound + regime persistence +
liquidity floor); optional real book-ask capture with heuristic fallback; a durable paper
equity ledger with drawdown/Sharpe; a board panel + opt-in minimal-noise ntfy digest; all
default-safe and non-regressive (live path byte-identical), self-healing with the existing
ingestion. The tracker is the honest, ongoing go/no-go for a real-money pilot and the decomposition
that tells us what to promote, prune, and improve. Paper/alert-only, NO real money.

## Standing disciplines
CLV (realizable), not `edge` (sharp-fill); net of execution (ask + slippage + fee); event-
clustered at the distinct-EVENT level; multi-regime persistence over pooling; conservative GO
(false GO > false HOLD in cost); read-only + non-regressive (live path byte-identical); promotion
math in the binary, SQL stays sums/means/stddev/percentiles; leak-free (outcome for scoring only,
always paired with a pre-resolution price); migrations append-only (next free number); every new
tunable in the compose `environment:` allowlist and verified in the container; commit per phase;
`merge --no-ff` at the end; deploy via the autoupdater; NO real money.
