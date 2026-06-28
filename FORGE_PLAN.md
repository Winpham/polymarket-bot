# Implementation Blueprint: Forward-Tested Strategy Portfolio

After this ships, the consensus engine no longer runs one hard-coded definition. It scores the
**same per-cycle fetched data under N named strategies simultaneously**, tags every signal with
its strategy, forward-tracks each separately (per-strategy hit-rate + edge-vs-entry-price), and —
critically, because there is **no backtest** — **logs the raw vote atoms so any strategy invented
later can be scored over data already collected.** Only one strategy (`strict`) pushes Telegram;
the rest accrue silent forward evidence. The user gets a self-documenting edge-discovery engine at
near-zero marginal cost and zero new alert noise.

> Produced by the Forge pipeline (diagnostician + 2 parallel designers, all Opus). Both designers
> independently concluded multi-strategy-forward is the right call. This blueprint = synthesis:
> **Direct's simple spine + Rethink's atom-log retroactivity.** Provenance noted per item.

---

## The verdict (is this the right approach?)
**Yes.** With no backtest, you cannot rank strategies offline, and the expensive work (polling N
traders, building per-market books) is *already paid once per cycle*. So each extra strategy is a
pure-function pass + a DB upsert — a free, honest, forward-tracked hypothesis. The one real risk is
**alert spam**, fully contained by a single-alerter flag. The one discipline to hold:
`edge > 0` on a few resolved signals is **indeterminate by power** — show N prominently and
**never auto-promote** a strategy to alerting; that stays a deliberate gated human decision.

Rejected alternatives: single hand-tuned definition (no exploration); offline backtest sweep
(impossible + look-ahead leak); A/B at alert layer (can't compare silent variants, pollutes feed).
Rethink's pure "strategies = SQL views over scalar features" is rejected — the scorer's
MM-drop/opposer/coherence/tier logic isn't SQL-expressible and scalar columns bake in `strict`'s
choices; the correct retroactivity unit is **raw vote atoms replayed through the real Rust scorer.**

---

## Items (dependency-ordered)

### 1. Strategy abstraction in the (still-pure) scorer  — *source: Direct, + Rethink's `pnl` plumbing*
**Before:** `score_all(books, now, &ConsensusParams)` — one definition; `ConsensusSignal` has no strategy.
**After:** enriched params cover 9/10 variants; `StrategyDef{name, params, alerting}`; `score_all_strategies` tags each signal.

Add to `scanner/consensus.rs`:
```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SportsMode { Include, Only, Exclude }
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WeightMode { Count, Quality, Dollars } // Quality = incumbent

// ConsensusParams gains 4 additive no-op-default fields:
//   require_elite: bool          (default false)
//   price_band: Option<(f64,f64)> (default None)   // gate on mean_price
//   sports_mode: SportsMode      (default Include)
//   weight_mode: WeightMode      (default Quality)
// Default() stays behaviorally identical → all 9 existing scorer tests pass untouched.

pub struct StrategyDef { pub name: &'static str, pub params: ConsensusParams, pub alerting: bool }
// ConsensusSignal gains: pub strategy: String  (score_market sets ""; wrapper sets it)
// TraderVote gains: pub pnl: Option<f64>   (for future smart-money; FollowedTrader.pnl already exists)

pub fn score_all_strategies(books, now, portfolio: &[StrategyDef]) -> Vec<ConsensusSignal>
// loops strategies over the SAME books, tags signal.strategy = def.name
```
Three additive branches in `score_market` (only scorer-logic change): sports early-out (`sports_mode`),
price-band gate on `mean_price`, `require_elite` gate; and `score` base term selectable by `weight_mode`
(`Count`→net_count, `Quality`→net_quality [incumbent], `Dollars`→log-money). **Tiering stays net_count-based
for ALL modes** so STRONG/ELITE remain comparable across strategies.

New `#[cfg(test)]` tests: price-band gate, require_elite gate, sports_mode, weight_mode, and a
**non-regression test** asserting `strict` == legacy default on the existing fixtures.

### 2. Atom log for retroactive replay  — *source: Rethink (the key "no-backtest" graft)*
**Before:** nothing records the raw votes; a strategy invented later can never be scored on past data.
**After:** every observed `(market, outcome)` stores its full vote vector as JSONB → future strategies
replay over already-collected forward data (recovers "backtesting" over forward data).

Migration 022 adds `observed_votes JSONB` to `consensus_signals`. The cycle serializes the per-outcome
`Vec<TraderVote>` (wallet, name, rank, quality, pnl, price, size_usd, ts) into it on upsert. **Storage
only this run** — the `replay_strategy` job is Phase 2 (documented), but the data is captured from day one.

### 3. DB schema: per-strategy signals + dedup  — *source: Direct (simple), Rethink's normalization deferred*
**Before:** `UNIQUE (condition_id, outcome_index)` — one strict row per market/outcome.
**After:** `UNIQUE (strategy, condition_id, outcome_index)`; existing rows backfill to `'strict'`.

`migrations/022_consensus_strategies.sql` (additive, idempotent, picked up by `sqlx::migrate!`):
```sql
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS strategy TEXT NOT NULL DEFAULT 'strict';
ALTER TABLE consensus_signals ADD COLUMN IF NOT EXISTS observed_votes JSONB;          -- item 2
ALTER TABLE consensus_signals DROP CONSTRAINT IF EXISTS consensus_signals_condition_id_outcome_index_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_consensus_signals_strategy_cond_outcome
    ON consensus_signals (strategy, condition_id, outcome_index);
CREATE INDEX IF NOT EXISTS idx_consensus_signals_strategy ON consensus_signals (strategy);
ALTER TABLE consensus_alerts ADD COLUMN IF NOT EXISTS strategy TEXT NOT NULL DEFAULT 'strict';
```
> VERIFY the dropped constraint's real name against a live PG during impl (spin up Docker PG); the
> inline `UNIQUE` in 021 yields the conventional `_key` name, but confirm. ON CONFLICT infers from the
> new unique index.

`NewConsensusSignal` + `to_new_signal` gain `strategy` + `observed_votes`; `upsert_consensus_signal`
ON CONFLICT target becomes `(strategy, condition_id, outcome_index)`; `record_consensus_alert` INSERT
gains `strategy`; `UnresolvedConsensus` gains `strategy`; its SELECT adds `strategy`. Dedup columns
(`last_alert_tier/net`) automatically become per-(strategy,market,outcome) once strategy is in the key.

### 4. Cycle reuses ONE fetch across N strategies  — *source: Direct*
**Before:** fetch+books once (lines 66-141), then score+upsert+alert for ONE params (142-191).
**After:** head unchanged; tail loops the portfolio. Drop the cycle-level sports filter (now per-strategy).
Only `alerting` strategies push Telegram; ALL strategies upsert for forward tracking.
```rust
let portfolio = active_portfolio(cfg);                 // honors CONSENSUS_STRATEGIES allowlist
let signals = score_all_strategies(&book_vec, now, &portfolio);
let alerting: HashSet<&str> = portfolio.iter().filter(|d| d.alerting).map(|d| d.name).collect();
for sig in &signals {
    upsert (sig incl. sig.strategy + observed_votes);  // every strategy, for forward tracking
    if !alerting.contains(sig.strategy) || sig.tier == Watch { continue; }
    // existing per-(strategy,signal) dedup → broadcast → record_consensus_alert(&sig.strategy, ...)
}
```
Add `pnl: trader.pnl` to the `TraderVote` build. `default_portfolio(base)` derives every variant from
the cfg base so global env tuning still moves the whole portfolio coherently.

### 5. Resolution dedupe by slug + per-strategy reporting/metrics  — *source: Rethink (slug-dedupe) + Direct (scoreboard)*
**Before:** housekeeping resolves each unresolved row independently → N strategies on one market = N Gamma fetches; scoreboard has no strategy axis.
**After:** housekeeping groups unresolved signals by `slug`, fetches each market **once**, applies the
result to all rows sharing that slug. Scoreboard groups by strategy with **edge = AVG(outcome_won::int − mean_price)**.
```rust
// storage:
pub struct StrategyScore { strategy: String, resolved: i64, won: i64, edge: Option<f64> }
async fn consensus_scoreboard_by_strategy(&self) -> Vec<StrategyScore>
//   SELECT strategy, COUNT(*) FILTER(resolved), COUNT(*) FILTER(resolved AND outcome_won),
//          AVG(outcome_won::int - mean_price) FILTER(resolved) GROUP BY strategy ORDER BY edge DESC NULLS LAST
// metrics: record_consensus_alert(strategy, tier); record_consensus_resolution(strategy, won, is_sports)
// /consensus: render per-strategy board (filter resolved>0 so it stays short until data accrues)
```

### 6. Initial portfolio (10 strategies, factorial probe)  — *source: Direct's set + Rethink's start-small steer*
Code-defined `default_portfolio(base)`; all `alerting=false` except `strict`. Each isolates ONE lever:

| name | delta from base | hypothesis |
|------|-----------------|-----------|
| `strict` ✅alert | none (= cfg) | incumbent; only Telegram pusher |
| `loose` | min_backers=2, max_opposers=2, max_price_std=0.15, strong_net=3, elite_net=5 | is the strict gate over-tight? |
| `fresh2h` | max_age_mins=120 | freshness premium (live conviction) |
| `longshot` | price_band=(0.02,0.35) | smart-money on underdogs beats entry? |
| `favorite` | price_band=(0.65,0.98) | consensus on favorites (control/likely-priced) |
| `sports_only` | sports_mode=Only | isolate sports-segment edge |
| `nonsports` | sports_mode=Exclude | isolate non-sports (cleaner resolution) |
| `elite_gated` | require_elite=true | ≥1 top-10 backer required |
| `whales` | weight_mode=Dollars | rank by $ committed not head-count |
| `count` | weight_mode=Count | ablation: does quality-weighting beat plain count? |

Env `CONSENSUS_STRATEGIES="strict,whales"` filters which run (empty = all). `smart_money`
(QualityPnl tiering) deferred until param-only/filter variants prove the plumbing.

---

## Execution order
1. **Item 1** (scorer abstraction) — pure, unit-testable in isolation. Verify: `cargo test` incl. new gate tests + non-regression test green.
2. **Item 3 + 2** (migration 022 + atom column) — Verify: apply against Docker PG; confirm dropped-constraint name; insert two strategies on one (cond,outcome) without conflict.
3. **Item 4** (cycle loop) — Verify: live run tracks traders, scores N strategies, persists per-strategy rows + observed_votes.
4. **Item 5** (resolution dedupe + scoreboard + metrics) — Verify: SQL runs on live PG; `/consensus` renders board; resolution fetches each slug once.
5. **Item 6** (portfolio set) — Verify: live run shows 10 strategies, only `strict` alerts.
6. CI gate after each: `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`.

## Existing infrastructure leveraged
Pure `score_market`/`score_all` + `MarketBook`/`TraderVote`/`ConsensusParams`/`Tier`; `upsert_consensus_signal`
+ `ConsensusAlertState` dedup; `unresolved_consensus_signals`/`resolve_consensus_signal`; `consensus_scoreboard`;
`record_consensus_*` metrics; `sqlx::migrate!` embed; `FollowedTrader.pnl` (already selected). The fetch+book
assembly already runs exactly once — only the scoring tail loops.

## Open questions (resolved during impl)
- Exact name of 021's inline unique constraint → confirm on live PG in step 2.
- Whether `get_active_traders` SELECT already returns `pnl` for the `TraderVote.pnl` plumb → grep/confirm in step 1 (it's in `FollowedTrader`).
- Alert volume if a future second strategy becomes `alerting` → keep single-alerter until a gated promotion decision.

## Phase 2 (documented, not built now) — Rethink's heavier ideas, de-risked by capturing atoms now
- `replay_strategy(def)`: rebuild books from `observed_votes`, score a newly-invented strategy over all
  collected observations, materialize its rows → instant scoreboard without waiting for new data.
- Full parent/child normalization (resolution once per market structurally) — only if slug-dedupe proves insufficient.
- DB strategy registry + `/strategy add <json>` live add/kill (needs `StrategyDef: Serialize`).
- Smart-money `WeightMode`/`TierRule` with PnL-derived weighting (atoms already carry `pnl`).
