# Long Autonomous Run — Continuous capture + earned trader-trust profiles ("who to actually follow")

Paste this whole file as the task for a fresh long-running session. Self-contained.
Work in `~/polymarket-bot` (Rust workspace), on a branch off `feat/consensus-engine`
(e.g. `feat/trader-profiles`). Gate-green + commit after EVERY phase; at the end
`merge --no-ff` into `feat/consensus-engine` (rebase → gate → merge) so the launchd
auto-updater deploys it. Companion reading: `RUN-CHAINED.md` (the prior run, same house
style), `DATA-MODEL.md`, `CONSENSUS-ENGINE-PLAN.md`.

## Philosophy — read first, it overrides everything
- **The generator is bold; rigor lives ONLY at the belief-blind gate.** Build every
  measurement; do not pre-judge. A trader looking good on 8 fills is NOT trustworthy — the
  *gate* (sample-floored, event-clustered, surplus-over-blind, Bonferroni-corrected,
  one-sided-bounded) decides who is trustworthy, not our hope. Per [[feedback-edge-exists-prior]].
- **Trust is EARNED, leak-free, event-clustered, sample-floored.** Every profitability
  number is computed on fills we captured *before* they resolved (forward, by construction),
  at the distinct-**EVENT** level (`COALESCE(event_slug, condition_id)` — never per-fill,
  never per-row), measured as **surplus over the trader's-own-band blind baseline**
  (favorite-longshot-neutralized), judged on a **one-sided confidence bound** after a
  **Bonferroni** split across that wallet's slices, with a **≥30 distinct-event floor ⇒
  INDETERMINATE**. `edge = won − entry_price` (mirrors the gate) — never hit-rate, never
  round-trip PnL (that's a documented v2 enhancement).
- **One conservatism at the gate, not two.** The blind baseline removes structural bias; the
  one-sided bound removes small-sample optimism. Do **not** also shrink the point estimate
  *before* the verdict — that double-penalizes N. Shrink-toward-0 belongs only on the
  continuous `earned_quality` weight (P4), where it regularizes a multiplier, not a test.
- **Paper/alert-only. Free data only.** No wallet, no funds. Forward-test everything.
- **Anything touching live `strict` alerting stays default-OFF + silent + non-regressive**
  until explicitly enabled. New consensus weightings are silent strategy variants the
  existing gate judges in the **experimental** family — never edits to `strict`. Tiering is
  `net_count`-based, so quality/trust changes are provably **alert**-non-regressive.
- **Capture is continuous and gap-honest.** Where capture is gappy (see the API reality),
  the profile says so — it never silently lies about completeness.

## The three mission pillars (in the user's words)
1. **Never stop updating / capture all the data.** One durable, continuously-growing, deduped
   archive of every tracked trader's fills (both sides) — not a throwaway rolling buffer.
2. **As many finds as we can — gated on rate-limit headroom.** Widen the funnel (more of the
   leaderboard, more silent strategy cells) only after measuring the data-api can take the
   `N × cadence` call rate. The gate still arbitrates quality.
3. **A profitability profile per followed trader → who to actually follow:** how profitable,
   **when** (recency/trend), and **with what games** (sport, price band, market type) — surfaced
   so we follow earned skill, not leaderboard rank.

## AUDITED API REALITY you MUST design around (2026-06-29, decisive)
The data-api `/activity?user=<wallet>&type=TRADE` endpoint:
- returns a **hard 100-row page** (no `limit` honored beyond that),
- **ignores `startTs`** — `no-filter`, `startTs=now−60s`, `startTs=now−48h` all return the same
  newest 100 rows. So you **cannot** fetch history in one call and you **cannot** rely on
  `since` to page backward. The ONLY mechanism is **poll frequently + accumulate + dedup on
  `transactionHash`** (this is *why* pillar #1 is the mechanism, not a nicety).
- a single active trader can do **100 trades in ~3 minutes** (verified). If a trader trades
  faster than `100 / poll_interval`, consecutive full pages don't overlap and trades are lost
  forever ⇒ **gaps are real and must be detected**.
- **No `category` field in activity.** `is_sports` + a sport bucket are derivable from
  `slug`/`title` (the existing heuristic). Finer Gamma `category` requires a per-market fetch —
  **deferred (cost-zero); do NOT build a lazy Gamma cache this run.**
- `fetch_leaderboard_n` **clamps to 50** (`copy-trading-bot/.../copy_trader.rs:243`,
  `limit.clamp(1,50)`). To track >50 traders, **widen across periods** (DAY/WEEK/MONTH/ALL),
  never raise N past 50.
- The consensus engine already polls these same traders every cycle — **capture once, use
  twice**: one poll feeds both the consensus window and the durable ledger. Do NOT double calls.
- **Durability:** a daily `pg_dump` backup **already exists** — `scripts/consensus-backup.sh`
  (run by launchd `com.tue.consensus.backup`, rotates 14 gzipped dumps; documented in
  `DATA-MODEL.md:44`). `trader_fills` lives in the same DB and is captured by it. Keep
  `trader_fills` **durable — never prune by default**; add a retention knob.

## Context (extend, don't rebuild — with real `file:fn`)
`~/polymarket-bot`: `common` (lib) + `copy-trading-bot` (the running consensus engine) +
`trading-bot`. **Layering rule (load-bearing):** `copy-trading-bot` depends only on `common`;
`common` cannot see the binary. So **all SQL + the connection pool live in `common`; ALL
statistics + the scorer live in the binary.** The shipped pattern is exactly this:
`common/.../storage/consensus.rs::consensus_scoreboard_by_strategy` returns aggregates only,
and `scanner/promotion.rs::promotion_verdict` (in the binary) consumes them. **No probit / no
promotion math in SQL.**

What exists to reuse:
- `common/src/storage/consensus.rs::insert_window_votes` (consensus.rs:559) — the UNNEST
  ON-CONFLICT batch-insert template; copy its shape for `insert_trader_fills`.
- `common/src/storage/consensus.rs::consensus_scoreboard_by_strategy` (consensus.rs:444) — the
  **canonical surplus-over-blind, event-clustered** SQL (`adv`→`blind`→`sig`→`evt`→`es` CTEs).
  Your trader-trust SQL is a wallet/slice-keyed clone of this. `StrategyScore` is the result
  shape to mirror.
- `scanner/promotion.rs::promotion_verdict(distinct_events, surplus, surplus_sd, n_strategies,
  &PromotionParams)` (promotion.rs:102) — the gate. `probit` (promotion.rs:16) is **private** and
  must stay private. Reuse `promotion_verdict` verbatim; add a sibling `surplus_bounds` (below).
- `scanner/consensus.rs`: `TraderVote` (l.30), `MarketBook`, `score_market` (l.288), `WeightMode`
  (l.105), `ConsensusParams` (l.117), `quality_weight(rank)` (l.268), `default_portfolio`
  (l.519). **Tiering is `net_count`-based** (l.421), so weight/trust changes can't move a tier.
- `scanner/enrich/mod.rs::family(strategy)` (mod.rs:228) — the Bonferroni family split; new arms
  go in its `EXPERIMENTAL` list. `EnrichModels`/`load_models` (mod.rs:34/67) — the
  flag+model-file load pattern.
- `cycles/consensus_cycle.rs`: `ingest_incremental` (l.336), `books_from_window_votes` (l.261,
  the SINGLE shared book builder), `trade_to_window_vote` (l.223), `is_sports` (l.55).
- `cycles/housekeeping.rs` (l.93-137) — resolves each open market once per cycle via
  `fetch_clob_market` → `ClobMarket::outcome_won(idx)` / `outcome_price(idx)`
  (`common/src/data/models.rs:273/281`; `ClobToken.winner` at models.rs:254). Reuse this exact
  loop to resolve `trader_fills`.
- `scanner/copy_trader.rs::poll_trader_activity` (l.413) returns `Result<Vec<TraderTrade>>`;
  `parse_activity_events` (l.363) **already returns BOTH sides** (the BUY-only doc comment is
  stale). 3 production callers: `ingest_legacy` (cycle.rs:301), `ingest_incremental`
  (cycle.rs:352), `detect_new_trades` (copy_trader.rs:479).
- `telegram/commands.rs::handle_command` (l.13) — arm dispatch; wallet args parsed via
  `full_text.split_whitespace().nth(1)` (l.159). `board.rs::render` (l.55) — the `:9002` board;
  reuse `pct()` (l.50), `family`, `promotion_verdict`, the dark `<table>` + `✅/⏳` style.
- Config flags use the derive macro: `#[config(env = "NAME", default = …)] pub field: T,`
  (config.rs). New flags follow this exactly, defaulting OFF.

**Gate (run before every commit):**
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a smoke run on a tiny synthetic fixture.
Live-verify on a **throwaway Docker Postgres** each phase (apply migrations, exercise the path,
inspect rows) — the established pattern. Migrations are append-only; **next free number is 026.**

---

## Phase 0 — Durable, never-stop capture spine (data + gap + throttle + flagged book source)
**Pillar #1.** One continuously-growing, deduped archive of every tracked trader's fills.

**Migration `026_trader_fills.sql`** (append-only, `IF NOT EXISTS`):
```sql
CREATE TABLE IF NOT EXISTS trader_fills (
    id            BIGSERIAL PRIMARY KEY,
    wallet        TEXT             NOT NULL,
    tx_hash       TEXT,                         -- dedup key when present
    condition_id  TEXT             NOT NULL,
    outcome_index INTEGER          NOT NULL,
    outcome       TEXT             NOT NULL,
    side          TEXT             NOT NULL,     -- 'BUY' | 'SELL'
    price         DOUBLE PRECISION NOT NULL,
    size_usd      DOUBLE PRECISION NOT NULL,
    title         TEXT             NOT NULL,
    slug          TEXT             NOT NULL,
    event_slug    TEXT,
    is_sports     BOOLEAN          NOT NULL DEFAULT FALSE,
    sport         TEXT,                          -- FROZEN slug-derived bucket (P2 single source of truth)
    ts            TIMESTAMPTZ      NOT NULL,
    ingested_at   TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    -- resolution (filled in P1)
    resolved      BOOLEAN          NOT NULL DEFAULT FALSE,
    outcome_won   BOOLEAN,
    advantage     DOUBLE PRECISION,              -- BUY: won::int - price ; SELL: NULL
    resolved_at   TIMESTAMPTZ
);
-- Two PARTIAL unique indexes: tx-level dedup when tx_hash present, content dedup when null.
CREATE UNIQUE INDEX IF NOT EXISTS trader_fills_tx_uniq
    ON trader_fills (tx_hash, condition_id, outcome_index) WHERE tx_hash IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS trader_fills_content_uniq
    ON trader_fills (wallet, condition_id, outcome_index, ts, price, side) WHERE tx_hash IS NULL;
CREATE INDEX IF NOT EXISTS idx_tf_wallet        ON trader_fills (wallet);
CREATE INDEX IF NOT EXISTS idx_tf_cond_outcome  ON trader_fills (condition_id, outcome_index);
CREATE INDEX IF NOT EXISTS idx_tf_ts            ON trader_fills (ts);
CREATE INDEX IF NOT EXISTS idx_tf_unresolved    ON trader_fills (resolved) WHERE resolved = FALSE;

ALTER TABLE followed_traders
    ADD COLUMN IF NOT EXISTS last_capture_newest_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS capture_gap_count      INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS capture_started_at     TIMESTAMPTZ;
```

**`PollResult` signature change** (`copy_trader.rs`): change `poll_trader_activity` to return
`Result<PollResult>` where
```rust
pub struct PollResult { pub trades: Vec<TraderTrade>, pub raw_count: usize }
```
`raw_count = events.len()` (the **page length pre-parse** — the gap test keys on the real page
size, not the post-filter count). **429 metric:** before `.error_for_status()` (which discards
the status), capture `let status = resp.status();` and on `status == 429` call a new
`crate::metrics::record_data_api_429()` then return the error. **Do NOT carry a `got_429` bool
out in the Ok struct** — a 429 must surface as `Err` so the cursor is *not* advanced and the gap
is re-fetched next cycle. Update all **3 callers** to destructure `.trades` (and `.raw_count`
where gap detection runs).

**Semaphore (no throttle today — `join_all` bursts):** wrap the poll fan-out in
`tokio::sync::Semaphore::new(cfg.consensus_max_concurrency)` (new flag, `#[config(env =
"CONSENSUS_MAX_CONCURRENCY", default = 8)]`) in both `ingest_incremental` and `ingest_legacy`,
acquiring a permit per `poll_trader_activity`.

**Capture once, use twice** — in `ingest_incremental`, from the SAME poll results that build the
window votes, also build `NewTraderFill` rows for **both sides** and persist them:
- `common/src/storage/consensus.rs`: add `insert_trader_fills(&[NewTraderFill]) -> Result<u64>` —
  a **single UNNEST batch with bare `ON CONFLICT DO NOTHING`** (no conflict target). Bare
  DO-NOTHING arbitrates per-row against whichever partial index applies (tx-present vs tx-null)
  and dedups intra-batch — proven by the existing `insert_window_votes` test. **Do not split the
  batch** (splitting is only needed if you used inference-with-predicate targets; you don't).
- `record_capture(wallet, min_ts, max_ts, raw_count)` — one atomic UPDATE:
```sql
UPDATE followed_traders SET
  capture_gap_count = capture_gap_count
      + CASE WHEN $4 >= 100 AND last_capture_newest_ts IS NOT NULL
                  AND $2 > last_capture_newest_ts          -- full page AND no overlap ⇒ gap
             THEN 1 ELSE 0 END,
  last_capture_newest_ts = GREATEST(COALESCE(last_capture_newest_ts, $3), $3),
  capture_started_at     = COALESCE(capture_started_at, NOW())
WHERE proxy_wallet = $1
```
  Gap iff **`raw_count == 100` AND `min_ts > last_capture_newest_ts`** (full page whose oldest
  row is newer than everything we'd seen ⇒ we skipped the in-between trades). First poll
  (`last_capture_newest_ts IS NULL`) never counts a gap.

**Flagged book-source cutover (NO hard swap):** add `#[config(env =
"CONSENSUS_BOOKS_FROM_FILLS", default = false)] pub consensus_books_from_fills: bool`. When
**false** (default), keep building consensus `MarketBook`s from `load_window_votes` exactly as
today (byte-identical). When **true**, build them from a new
`load_buy_fills_since(since) -> Vec<WindowVote>` that selects BUY `trader_fills` in-window,
`LEFT JOIN followed_traders` to re-derive `quality_weight(rank)` at load, and returns the
**existing `WindowVote` shape** so `books_from_window_votes` is reused unchanged. **Dual-write
this phase** (write both `consensus_vote_window` AND `trader_fills`); retiring `vote_window`
writes is a LATER migration after the flag has run true in prod. Tiering is `net_count`-based ⇒
`strict` alerts identical under either source. (Note: re-derived `quality` can shift the *ranking*
`score` slightly vs the frozen-`quality` window path; **alerts are unaffected** because tiers key
on `net_count`. Document this; do not "fix" it.)

**Verify live:** window accumulates across cycles; `trader_fills` dedups a re-seen tx and a
null-tx content dup; `capture_gap_count` increments on a simulated 100-row fast-trader poll and
NOT on a partial page; consensus books reproduced from fills under the flag match the window
path's tier/net_count. Gate, commit.

## Phase 1 — Resolution ledger (leak-free, independent source, multi-outcome)
**The survivorship fix:** `trader_fills` includes fills on markets that never became consensus
signals; if you resolve only consensus conditions, those markets never resolve and profiles are
biased toward the markets that happened to trigger consensus. So add an **independent unresolved
source** and UNION it into housekeeping.

- `common/src/storage/consensus.rs`:
  - `trader_fill_unresolved_conditions(min_age: Duration, cap: i64) -> Vec<String>`:
    ```sql
    SELECT condition_id FROM trader_fills
    WHERE resolved = FALSE AND side = 'BUY' AND ts < NOW() - $1
    GROUP BY condition_id ORDER BY MIN(ts) LIMIT $2
    ```
  - `resolve_trader_fills(condition_id, winner_index: i32) -> Result<u64>`:
    ```sql
    UPDATE trader_fills SET
      resolved    = TRUE,
      outcome_won = (outcome_index = $2),
      advantage   = CASE WHEN side = 'BUY'
                         THEN ((outcome_index = $2)::int)::double precision - price
                         ELSE NULL END,
      resolved_at = NOW()
    WHERE condition_id = $1 AND resolved = FALSE
    ```
    (Multi-outcome is correct: `winner_index` is the winning token index, not a single bool.
    Both sides are marked resolved so they stop re-appearing; SELL `advantage` is NULL.)
- `cycles/housekeeping.rs`: build the cond set = **(consensus `by_cond` keys) ∪
  (`trader_fill_unresolved_conditions(min_age = 6h, cap = cfg.trader_fills_resolve_per_cycle`
  default 200))**, deduped. For each cond, fetch `fetch_clob_market` **once** (reuse the existing
  120ms-throttled loop) and:
  - resolve consensus signals exactly as today (`outcome_won(idx)` per signal), AND
  - compute `winner_index = market.tokens.iter().position(|t| t.winner)`; if `market.closed &&
    winner_index.is_some()` ⇒ `resolve_trader_fills(cond, winner_index)`. **If closed but NO
    winner token (void/refund), SKIP** — do not charge every BUY a loss (this is more correct
    than blanket-resolving; document voids as a rare edge mirroring the consensus path).
- Flag: `#[config(env = "TRADER_FILLS_RESOLVE_PER_CYCLE", default = 200)]`.

**Verify live:** synthetic resolved + voided + multi-outcome markets; a non-consensus market's
fills resolve via the independent source; `advantage` matches `won::int − price` for BUY and is
NULL for SELL; voided market leaves rows unresolved. Gate, commit.

## Phase 2 — Earned trust = ONE surplus-over-own-blind query + gate reuse (the collapse)
**Pillar #3.** A trader's edge is a pseudo-strategy — reuse the gate, add **zero new
statistics**. **Do NOT insert fills as `consensus_signals` rows** (its unique
`(strategy,condition_id,outcome_index)` + NOT-NULL columns would collapse multiple fills and
break every signal consumer — rejected, correctly).

**Frozen `category`/sport (single source of truth):** populate `trader_fills.sport` and
`is_sports` **at capture** (P0) using the Rust `is_sports()` heuristic + a small slug→bucket
helper (nba/nfl/mlb/nhl/soccer/cs2/lol/dota/tennis/ufc/crypto/politics/other). This is the same
heuristic the consensus path uses (consistency) and avoids SQL slug-CASE drift across query
sites. Gamma `category` stays deferred (no fetch, no lazy cache).

**The aggregate (in `common`, returns numbers only):**
`trader_slice_scores() -> Vec<TraderSliceStat>` where
```rust
#[derive(sqlx::FromRow)]
pub struct TraderSliceStat {
    pub wallet: String,
    pub slice_kind: String,   // 'overall' | 'sport' | 'band' | 'recency7d' | 'recency30d'
    pub slice_key: String,    // '' | 'nba' | 'favorite'…
    pub n_events: i64,        // distinct COALESCE(event_slug,condition_id) — the gate's N
    pub n_resolved: i64,
    pub surplus: Option<f64>, // event-clustered AVG of (a - band_blind)
    pub surplus_sd: Option<f64>,
    pub mean_adv: Option<f64>,
    pub hit_rate: Option<f64>,
}
```
SQL mirrors `consensus_scoreboard_by_strategy` exactly, keyed by wallet×slice with a
**trader_fills-NATIVE band-blind baseline** (strictly better than raw `mean_adv` — it
neutralizes favorite-loading natively):
```sql
WITH adv AS (
  SELECT wallet, COALESCE(event_slug, condition_id) AS ev,
         width_bucket(price, 0.0, 1.0, 5) AS band,         -- IDENTICAL bucketing to the gate
         (outcome_won::int)::double precision - price AS a,
         is_sports, sport, ts
  FROM trader_fills
  WHERE resolved AND side = 'BUY' AND outcome_won IS NOT NULL
),
blind AS ( SELECT band, AVG(a) AS blind_edge FROM adv GROUP BY band ),   -- the favorite-longshot baseline
surp AS ( SELECT a.*, a.a - COALESCE(b.blind_edge, 0) AS s
          FROM adv a LEFT JOIN blind b USING (band) )
-- then per (wallet, slice): GROUP to ev → AVG(s) per ev → COUNT(DISTINCT ev) AS n_events,
--   AVG(ev_s) AS surplus, STDDEV_SAMP(ev_s) AS surplus_sd. One UNION ALL per slice_kind.
```

**The verdict (in the BINARY — new `scanner/trader_trust.rs`), zero new stats:**
- Add to `scanner/promotion.rs` a sibling that keeps `probit` private:
```rust
/// Two-sided Bonferroni-corrected confidence interval on surplus, reusing the
/// gate's exact z/SE machinery (probit stays private to this module).
pub fn surplus_bounds(
    distinct_events: i64, surplus: f64, surplus_sd: Option<f64>,
    n_comparisons: usize, p: &PromotionParams,
) -> (f64, f64) {
    let sd = surplus_sd.unwrap_or(0.0).max(1e-9);
    let alpha_corr = (p.alpha / n_comparisons.max(1) as f64).clamp(1e-6, 0.5);
    let z = probit(1.0 - alpha_corr);
    let se = sd / (distinct_events as f64).sqrt();
    (surplus - z * se, surplus + z * se)   // (lower, upper)
}
```
- `trust_verdict(slices: &[TraderSliceStat]) -> TraderTrust`: `n_comparisons` = number of slices
  evaluated for that wallet (**Bonferroni across the wallet's slices**). For the `overall`
  slice (the headline): `n_events < min_events (30) ⇒ INDETERMINATE`; else
  `(lo, hi) = surplus_bounds(...)`; `lo > margin ⇒ Trusted`; `hi < -margin ⇒ Avoid`; else
  `Indeterminate`. **Use the RAW event-clustered surplus + sd — do NOT shrink the point estimate
  here** (the blind baseline + one-sided bound are the rigor; shrinking too would double-penalize
  N). Reuse `promotion_verdict` verbatim for the lower-bound/`reason` string of the trusted side.
```rust
pub enum TrustVerdict { Trusted, Indeterminate, Avoid }
pub struct TraderTrust {
    pub wallet: String, pub verdict: TrustVerdict,
    pub n_events: i64, pub lower_bound: f64, pub upper_bound: f64,
    pub best_slices: Vec<(String,String,f64)>, pub worst_slices: Vec<(String,String,f64)>,
}
```

**Verify live:** synthetic wallets — a high-N skilled wallet ⇒ Trusted; a high-N negative wallet
⇒ Avoid; a 10-event wallet ⇒ Indeterminate regardless of point estimate; a wallet that only
looks good because it loads favorites ⇒ surplus ≈ 0 (blind baseline neutralizes it). Unit-test
`surplus_bounds` (lo<hi, symmetric, tighter with more events). Gate, commit.

## Phase 3 — Surfacing: who to actually follow
- `common/src/storage/consensus.rs`: `trader_profile(wallet) -> ...` (overall + slice rows +
  `capture_gap_count` from `followed_traders`).
- `telegram/commands.rs`: `/trader <wallet>` (parse via `full_text.split_whitespace().nth(1)`,
  like `/follow` l.159) → overall edge + lower bound + verdict, best/worst sport & price-band
  slices, 7d/30d trend, and **capture completeness** (`capture_gap_count > 0 ⇒ "⚠ partial
  capture"`). Plain-English, honesty-first (grey = indeterminate; always print `n` and the bound,
  never a thin slice as fact). `/traders-by-trust` — ranked by earned trust (not leaderboard
  rank), with `n + verdict`.
- `board.rs`: a **second table** beneath the strategy scoreboard reusing `pct()`, the dark
  `<table>` CSS, and the `✅/⏳` (and a grey `⏸` for INDETERMINATE) convention: each tracked
  trader, verdict, best games, edge ± bound, completeness.
- Verify on the throwaway PG with seeded profiles; eyeball `/trader` text + the board HTML. Gate,
  commit.

## Phase 4 — Earned trust feeds consensus (silent, flag-gated, non-regression-proven)
**Pillar #2/#3.** Trust rides ON THE VOTE via a cached map; the shared book builder forbids
"leave the scorer untouched."

- **Cached slow-refresh trust map** (trust changes only as markets resolve, ~daily):
  `Arc<RwLock<HashMap<String, TraderTrust>>>` refreshed every `#[config(env =
  "TRUST_REFRESH_MINS", default = 60)]` (lazy-on-stale or a background task in `live.rs`) — NOT
  recomputed every 1-min cycle.
- `scanner/consensus.rs`:
  - `TraderVote` gains `pub earned_quality: f64` (defaults to `quality`) and `pub trusted: bool`
    (defaults to `true`). **Update every `TraderVote` literal** (`books_from_window_votes`
    cycle.rs:276; the two test `vote()` helpers) so defaults preserve current behavior.
  - `WeightMode::TrustWeighted` (new variant — handle it in the `score_market` `base` match,
    l.413: `WeightMode::TrustWeighted => backers.values().map(|v| v.earned_quality).sum()`).
  - `ConsensusParams` gains `pub trusted_only: bool` (default `false`); when set, `score_market`
    skips backers with `!trusted` before counting.
- `books_from_window_votes(votes, &trust_map)`: set
  `earned_quality = trust_map.get(w).map(|t| f(t)).unwrap_or(quality_weight(rank))` and
  `trusted = trust_map.get(w).map(|t| matches!(t.verdict, Trusted)).unwrap_or(true)`.
  **INDETERMINATE / absent ⇒ `quality_weight(rank)` fallback (never 0)** so `trust_weighted`
  never silently zeroes new traders. `f(trust)` is where **shrink-toward-0** lives:
  `earned = (1.0 + shrink).clamp(0.5, 2.0)`, `shrink = t.lower_bound * n/(n+20)` for Trusted
  (toward 0 for low N), negative toward 0.5 for Avoid.
- New silent strategies in `default_portfolio`, `alerting: false`: `trust_weighted` (WeightMode
  ::TrustWeighted) and `trusted_only` (`trusted_only: true`). Add both to **`family()`'s
  `EXPERIMENTAL` list** so they never tighten core's Bonferroni bar. Gate them behind
  `#[config(env = "CONSENSUS_TRUST_ARMS", default = false)]` — when off, they aren't registered,
  so the portfolio is identical.
- **Non-regression proof:** arms off ⇒ not registered ⇒ identical. With `earned_quality ==
  quality` and `trusted == true`, `TrustWeighted` scores == `Quality` and `trusted_only` drops
  nothing. Extend `default_strict_is_non_regressive` to assert this; confirm `strict` tier/score
  byte-identical with arms OFF.
- **More finds (gated):** only after P5's 429 measurement shows headroom, document raising
  `TRACK_TOP_N` / adding `TRACK_PERIODS` (widen via periods, never N>50). Gate, commit.

## Phase 5 — Cutover, scale-gated, retention, verify, report
- **Flag flip:** with capture proven, document flipping `CONSENSUS_BOOKS_FROM_FILLS=true` in
  `.env.consensus`; keep `consensus_vote_window` dual-written one more release as instant
  rollback (its write-retirement is a future migration, not this run).
- **Scale gated on 429:** surface `record_data_api_429` on the board / `/consensus`; only widen
  the universe/cadence when the 429 rate ≈ 0. Document the rate-limit/gap tradeoff.
- **Retention knob:** `#[config(env = "TRADER_FILLS_RETENTION_DAYS", default = 0)]` (0 =
  keep-all, the default). Prune only when `> 0`. Durability is the same-DB daily
  `scripts/consensus-backup.sh` dump (already live) — `trader_fills` is included automatically;
  no new backup machinery this run.
- **End-to-end** on a throwaway PG + tiny fixtures: capture → resolve (incl. a non-consensus
  market via the independent source) → slice scores → trust verdict → `/trader` + board → the
  silent `trust_weighted`/`trusted_only` arms emit and appear in the scoreboard's **experimental**
  family. Confirm live `strict` + the existing core strategies are byte-identical with the new
  arms OFF.
- **Report** (`reports/entries/NN-…md`): what each profile dimension means; that trust is the
  gate's call (surplus-over-own-blind, ≥30 events, Bonferroni across slices, one-sided bound),
  not ours; capture-completeness caveats; how to read `/trader`, `/traders-by-trust`, the board;
  the honest note that profitability is forward-measured and accrues. Update the plan progress
  log. `merge --no-ff`.

## Acceptance
Every phase gate-green and committed; final `merge --no-ff` to `feat/consensus-engine`
(auto-deploys). A durable, deduped, gap-aware `trader_fills` archive growing every cycle with NO
extra API calls and a Semaphore + 429 metric on the fan-out; a leak-free, multi-outcome
resolution ledger fed by an INDEPENDENT unresolved-condition source (no survivorship bias);
event-clustered, surplus-over-own-blind, sample-floored, Bonferroni-corrected, one-sided-bounded
trust verdicts surfaced via `/trader`, `/traders-by-trust`, and the board; earned-trust consensus
arms that are silent, default-OFF, judged in the experimental family, with INDETERMINATE→
`quality_weight(rank)` fallback; live `strict` non-regressive (tiering is `net_count`); book
source behind `CONSENSUS_BOOKS_FROM_FILLS` with instant rollback; data-api 429 headroom verified
before any scale-up.

## Standing disciplines
Generator bold, rigor only at the belief-blind gate; trust EARNED — distinct-EVENT clustered,
surplus over the trader's-own-band blind baseline, ≥30 events else INDETERMINATE, Bonferroni
across the wallet's slices, one-sided bound, shrink-toward-0 only on the continuous weight (never
double-penalize N at the verdict), `edge = won − entry_price`; capture continuous + gap-honest;
free data; paper/alert-only; default-OFF + silent + non-regressive for anything touching live
`strict`; SQL/pool in `common`, all stats in the binary, no probit-in-SQL; migrations append-only
(next 026); commit per phase; `merge --no-ff` at the end.
