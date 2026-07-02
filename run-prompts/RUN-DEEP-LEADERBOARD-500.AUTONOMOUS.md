# Long Autonomous Run — Deep Leaderboard Ingestion (top-500 via offset pagination)

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace + Python), in a dedicated git worktree off
`feat/consensus-engine`. Gate-green + commit after EVERY phase; at the end
`merge --no-ff` into `feat/consensus-engine` so the launchd auto-updater deploys it.
Companion reading (same house style, read for conventions): `run-prompts/RUN-TRADER-PROFILES.md`
(the earned-trust spine — this run FEEDS it), `run-prompts/RUN-HONEST-PNL-TRACKER.md`,
`DATA-MODEL.md`, `model/README.md`.

---

## 0. The one-sentence mission
Widen the tracked-trader universe from the **top ~40 by absolute PnL** to the **top ~500**,
by adding **offset pagination** to the leaderboard fetch — done as an **additive, flag-gated,
rate-budgeted, belief-blind** change that **captures and profiles** the deeper pool **without
letting it regress the live consensus engine** (alert rate, tiering, 429 rate, cycle latency),
so we finally have the candidate universe needed to find the efficient small-bankroll sharps —
not just the whales.

The motto: **depth is a candidate pool, not automatic trust. Capture wide, promote narrow.
Additive and reversible. A widening that floods alerts or starves the poller is a regression,
not a feature — prove it doesn't.**

---

## Philosophy — read first, it overrides everything
- **More data is strictly good; using it naively is not.** The user's instruction is "more data
  is always better — we just need to know how to *use* it." Ingesting ranks 51–500 gives us the
  candidate pool. But **rank is PnL — a whale signal**. Deep traders must enter the system as
  **captured + profiled candidates**, NOT as instantly-trusted consensus backers. What earns a
  deep trader a vote in consensus is the **belief-blind earned-trust gate** (`RUN-TRADER-PROFILES.md`
  Phase 2 / `scanner/trader_trust.rs`), never their mere presence on the board.
- **Additive, never destructive.** The current top-40 behavior must be the exact default until a
  flag is flipped. Every new knob defaults to today's value. `git`-revertible in one commit.
- **The regression surface is the fan-out, not the fetch.** Fetching 500 rows is 10 cheap HTTP
  calls. The cost is that the consensus cycle polls **every active trader's `/activity` every
  cycle** (`consensus_cycle.rs:506-515` legacy, `:561-575` incremental — `join_all` bounded by
  `Semaphore(consensus_max_concurrency)`, default 8). 40→500 is a **~12× poll load** and a **~12×
  jump in candidate backers per market**. Both must be governed before the universe grows.
- **Belief-blind at the gate.** Do not hand-pick who's "good." Widen the pool; let the existing
  event-clustered, surplus-over-blind gate decide who feeds consensus. An honest NULL (deep pool
  adds no certified edge) is a real, valuable result — report it, don't bury it.
- **Cost-zero, paper-only, no real money.** Same standing rules as every run here.

---

## THE DECISIVE API CORRECTION (verified live 2026-07-01 — supersedes prior guidance)
`RUN-TRADER-PROFILES.md:58-60` and the 2026-06-29 audit concluded: *"`fetch_leaderboard_n`
clamps to 50 … To track >50 traders, widen across periods, never raise N past 50."* **That
guidance is now OVERTURNED for depth (keep it for a single `limit`).** Verified against
`https://data-api.polymarket.com/v1/leaderboard`:

- `limit` **is** hard-capped server-side at 50 (sending `limit=100` returns 50 rows). The
  `limit.clamp(1,50)` in `copy_trader.rs::fetch_leaderboard_n` correctly mirrors that. **Do not
  try to raise `limit` past 50 — it does nothing.**
- **`offset` IS honored and paginates cleanly.** Evidence (WEEK period):
  - `offset=0,  limit=50` → ranks 1–50, tail PnL ≈ **$127,383**.
  - `offset=50, limit=50` → ranks 51–100, head PnL ≈ **$126,053** (continuous, **no overlap**).
  - `offset=200` → head ≈ $24k; `offset=500` → ≈ $9k; `offset=1000` → ≈ $4.1k; `offset=2000` →
    ≈ $1.8k. The board is thousands deep, monotone-descending by PnL.
- **⇒ top-500 = 10 sequential pages** (`offset = 0,50,…,450`) per period. It is an **unauthenticated
  public GET** — depth is NOT gated by identity, so **do NOT** create multiple accounts/bots; a
  single caller paginating is the correct and complete mechanism.
- **Full-depth proof (2026-07-01):** all 10 pages fetched for WEEK, MONTH, AND ALL → **500 rows
  each, 500 unique wallets, 0 dups, 0 null wallet/pnl, PnL monotone-decreasing across the whole
  concatenation** (clean, no gaps/overlap). Top-500 is confirmed real. `TRACK_DEPTH=250` is a strict
  subset (first 5 pages) and therefore also guaranteed — the knob, not the code, picks deployed depth.
- **⚠️ Cloudflare/User-Agent:** a header-less client 403s on this host; a browser `User-Agent`
  returns 200. The production `reqwest` client already fetches the leaderboard fine today (so its
  headers are acceptable) and `offset` doesn't change that — but **Phase 0 must confirm the
  PRODUCTION `http` client (not a bare `curl`/`urllib`) gets 200s on offset pages** before building.
- **Re-verify at the start of Phase 0** (2 offsets via the production client: assert no head/tail
  overlap and descending PnL). If the API has changed, STOP and report.

The `/activity` reality from the prior audit **still holds** and constrains the poller: hard
100-row page, `startTs` ignored, gaps are real (`RUN-TRADER-PROFILES.md:45-66`). This is why deep
traders need a **cadence budget** (Phase 2), not naive every-cycle polling.

---

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a smoke run on a tiny synthetic fixture.
Live-verify each phase on a **throwaway Docker Postgres** (apply migrations, exercise the path,
inspect rows) — the established pattern. Migrations are append-only; **grep `migrations/` for the
next free number** (026 is taken by `trader_fills`; pick the next).

---

## Context (extend, don't rebuild — verified file:fn, grep to pin exact lines)
`~/polymarket-bot`: `common` (lib: all SQL + pool) + `copy-trading-bot` (the running consensus
engine: all stats/scoring) + `trading-bot`. **Layering rule:** `copy-trading-bot` depends only on
`common`; keep SQL in `common`, math in the binary.

The exact surfaces this run touches:
- **Fetch:** `copy-trading-bot/src/scanner/copy_trader.rs::fetch_leaderboard_n` (≈l.250) — URL
  `{DATA_API}/v1/leaderboard?timePeriod={P}&limit={n}`, `limit.clamp(1,50)`, sorts `pnl` desc,
  `take(n)`, assigns `rank = i+1`. `LeaderboardRaw` (≈l.240) is the row shape. `DATA_API` const
  (l.19). **This is where pagination is added** (new fn, don't break the existing one).
- **Universe refresh:** `copy-trading-bot/src/scanner/leaderboard_tracker.rs::refresh_universe`
  (l.27) — unions periods into `HashMap<wallet,Merged>` keeping best rank, upserts ALL, then
  drop-grace `deactivate_stale_tracked`. **This is where depth is wired in.**
- **Storage:** `common/src/storage/consensus.rs` — `upsert_tracked_trader` (l.141, INSERT …
  `followed_traders` ON CONFLICT), `deactivate_stale_tracked` (l.171), `count_tracked_traders`
  (l.185). Table `followed_traders` (migration `015_copy_trading.sql` + `021_consensus.sql` adds
  `last_seen_on_lb`, `periods`): `proxy_wallet UNIQUE, username, source, rank, pnl, volume,
  win_rate, active, last_seen_on_lb, periods, consensus_polled_at, capture_gap_count`. **No index
  on `active`/`source`** — fine at 500 rows, add one only if the read gets hot.
- **The read-back (single source of the scanned set):** `common/src/storage/copy_trade.rs::get_active_traders`
  (l.53-65) — `SELECT … FROM followed_traders WHERE active = TRUE ORDER BY rank ASC NULLS LAST`.
  Returns **both** `'leaderboard'` and `'manual'` rows and does **not** currently select any
  eligibility column. **This is the exact query that must learn about `consensus_eligible`** (Phase
  3). `consensus_cycle.rs:233` calls it each cycle.
- **The fan-out (regression surface):** `copy-trading-bot/src/cycles/consensus_cycle.rs` —
  `Semaphore::new(cfg.consensus_max_concurrency.max(1))` then `join_all` over ALL traders
  (l.506-515 legacy `ingest_legacy`, l.561-575 incremental `ingest_incremental`). Each calls
  `monitor.poll_trader_activity(&wallet, since)` (`copy_trader.rs::poll_trader_activity` ≈l.432,
  429 → `Err`, no backoff). Math: 500 polls / cycle at 8 concurrent ≈ 63 serial batches ≈ 13–30 s
  per ~2-min cycle (`CONSENSUS_INTERVAL_MINS`) — **the semaphore alone probably clears 500/cycle
  without a 429 storm**; cadence tiering (Phase 2) is the guardrail, not a certainty.
- **⚠️ The real landmine — UNBOUNDED legacy loop:** `copy_trader.rs::detect_new_trades` (l.493-513)
  does a `join_all` over all active traders with **no semaphore** → at 500 traders that's 500
  simultaneous requests. It's masked only because `COPY_TRADE_ENABLED=false` (default). **Phase 2
  must add a semaphore here** so widening the universe can never turn `COPY_TRADE_ENABLED=true`
  into a 500-request burst.
- **Consensus scoring (the other regression surface):** `copy-trading-bot/src/scanner/consensus.rs`
  — `score_market` (≈l.288), `quality_weight(rank)` (l.284-289: `1.0 + (50 − r.min(50)).max(0)/50`
  — **already safe & monotone; saturates to 1.0 for rank>50**, no div-by-zero, so deep traders just
  carry baseline weight — no hardening needed, but the quality signal is flat past rank 50).
  `ConsensusParams` (l.117: `min_backers=3`, `strong_net=4`, `elite_net=6`, `elite_rank=10`,
  `require_elite_backer`). **All tiers are ABSOLUTE counts on `net_count`** (l.408-454) — so every
  extra eligible backer makes signals fire *more often*. Deep traders MUST stay
  `consensus_eligible=FALSE` or alert volume regresses immediately.
- **Earned trust (where deep traders must go to earn a vote):** `scanner/trader_trust.rs`
  (`trust_verdict`, `min_events`), `cycles/consensus_cycle.rs:96`. Read `RUN-TRADER-PROFILES.md`
  Phase 2/4 — this run is its **upstream widener**; do not duplicate its gate, feed it.
- **Config:** `copy-trading-bot/src/config.rs` — `track_top_n` (=40), `track_periods`
  (="WEEK,MONTH"), `track_refresh_mins` (=60), `track_drop_grace` (=6), `consensus_max_concurrency`
  (=8). New flags use `#[config(env="NAME", default=…)]` and **default to today's behavior**.
- **Metrics/board:** `common/src/metrics.rs::record_tracked_traders`; the `:9002` board (`board.rs`)
  and `telegram/commands.rs`.

---

## Rejected approaches (do not build these)
- ❌ Raising `limit` past 50 (server ignores it — proven).
- ❌ Multiple accounts/bots/proxies to fetch depth (unauthenticated GET; offset alone suffices).
- ❌ Letting rank-51–500 traders vote in consensus by default (imports the whale bias 12× and
  floods `net_count` tiers). Deep = captured/profiled candidate, gated OUT of tiering until earned.
- ❌ Polling all 500 every cycle at the same cadence (12× the 429 exposure and cycle latency).
- ❌ Deleting/replacing `fetch_leaderboard_n` or changing the top-40 default in place. Additive only.
- ❌ Hand-picking "good" small traders. Widen the pool; the belief-blind gate decides.
- ❌ Any real-money action. Paper/measurement only.

---

## Phase 0 — Verify API + paginated fetch (additive fn, read-only)
Re-verify offset pagination with a throwaway `curl` (2 offsets: assert descending PnL and zero
head/tail overlap; if broken, STOP + report). Add a **new** `fetch_leaderboard_paged(http,
period, depth) -> Vec<LeaderboardRaw>` alongside `fetch_leaderboard_n` (do not modify the latter):
loops `offset = 0,50,…` until `depth` rows or a short/empty page, **paces requests** (small delay
+ reuse the 429-as-Err discipline so a rate-limited page doesn't silently truncate the universe),
dedups by wallet, sorts `pnl` desc, re-derives global `rank = i+1` across the merged pages. Unit
test on a synthetic 3-page fixture (dedup + continuous rank + short-page stop). Gate, commit.
(No live-path change yet — nothing calls it.)

## Phase 1 — Wire depth into the universe (capture-only, flag-gated, default-off)
Add config `TRACK_DEPTH` (default **40** = today's behavior; when >50, `refresh_universe` calls
`fetch_leaderboard_paged` instead of `fetch_leaderboard_n`). Add provenance so we can tell deep
from hot: a `consensus_eligible BOOLEAN` column on `followed_traders` (migration; default TRUE to
preserve existing rows) set at upsert = `rank <= TRACK_CONSENSUS_RANK_CUTOFF` (new config, default
**50**). Deep traders (rank 51–depth) are upserted `active=TRUE, consensus_eligible=FALSE`. Update
`count_tracked_traders` + `record_tracked_traders` to report hot/deep split. Live-verify on Docker
PG: run refresh at depth=200, assert ~200 active rows, ~50 eligible, ranks contiguous, re-running
is idempotent (ON CONFLICT). Gate, commit. **Still no consensus change** — eligible set unchanged.

## Phase 2 — Poll-cadence budget + close the unbounded-loop landmine
Two jobs. **(a) Safety fix (do first):** add a `Semaphore` to the legacy `detect_new_trades`
fan-out (`copy_trader.rs:493-513`) mirroring the consensus one, so a future `COPY_TRADE_ENABLED=true`
can't burst 500 concurrent requests. This is a strict hardening, valid regardless of depth.
**(b) Cadence budget:** the consensus fan-out is already semaphore-bounded and may clear 500/cycle
fine — so **measure first**. Add a board/metric for **429 rate** and **cycle poll count/latency**,
run at depth=200, and read them. If 429 rate stays ≈ 0 and latency is comfortably inside the cycle,
the semaphore suffices — note it and keep cadence tiering as an off-by-default option. If 429s
appear or latency approaches the cycle window, add tiered cadence: **hot** (eligible/rank≤cutoff)
every cycle; **deep** every `TRACK_DEEP_POLL_EVERY_N` cycles (default chosen to hold polls/min ≈
today's — compute it), staggered by `id % N` **inside** the existing `join_all`+`Semaphore` (never
remove the semaphore). Gate, commit.

## Phase 3 — Consensus non-regression proof (the tiering surface)
Deep traders (Phase 1: `consensus_eligible=FALSE`) must be excluded from `net_count`/tiering. The
clean seam: teach `get_active_traders` (`copy_trade.rs:53`) to **select `consensus_eligible`**, then
have the consensus vote path (`consensus_cycle.rs` → `score_market`) **only count eligible traders
as backers/opposers**, while STILL polling+capturing the ineligible ones (capture is decoupled from
voting). Add the SQL filter and the vote-path guard; keep manual `'manual'` follows eligible as
today. Then **shadow-measure**: a parallel, non-alerting computation of what consensus *would* look
like if deep traders voted — study impact without shipping it. Prove on a live/replayed window:
**alert rate, tier distribution, and emitted signals are byte-for-byte identical to `TRACK_DEPTH=40`**
when the flag is on at depth=200. (`quality_weight` needs no change — it already saturates safely at
rank>50.) Gate, commit. PASS = "widening changed nothing the engine acts on."

Note for later (not this run): once deep traders start earning eligibility via the Phase-4 gate, the
absolute-count thresholds (`min_backers/strong_net/elite_net`) may need re-tuning upward to hold
selectivity as the eligible set grows. Flag it in the report; don't pre-tune.

## Phase 4 — Efficiency re-rank over the deep pool (the actual point)
Now use the depth. Build a **read-only** efficiency view over the captured pool: per-trader ROI /
per-bet edge / surplus, **event-clustered, sample-floored, and shrunk** toward the pool mean
(reuse the `consensus_scoreboard_by_strategy` / `promotion_verdict` machinery from
`RUN-TRADER-PROFILES.md` — do NOT invent a new gate). Surface a "who's efficient below the whales"
list (the small-bankroll sharps the user asked for) with N, ROI, shrunk edge, and the gate verdict.
**Nothing auto-promotes** — a deep trader becomes `consensus_eligible` ONLY by clearing the
belief-blind earned-trust gate (flag-gated, default off). Report the honest finding: does the
depth-51–500 pool contain certified edge the top-50 lacked, or is it NULL? Gate, commit.

## Phase 5 — Cutover (scale-gated), retention, verify, report
Choose the shipped default `TRACK_DEPTH` from evidence (e.g. 100/200/500) balancing candidate
richness against poll budget — justify it with the Phase 2 numbers. Keep deep-trader capture
**durable** (it feeds the profiles/ledger; the daily `pg_dump` already covers `followed_traders`;
add a retention knob if row growth warrants). Final `merge --no-ff` into `feat/consensus-engine`;
deploy via the autoupdater script (not a manual restart). Write a short report: the API correction,
the depth chosen + why, the non-regression proof, the efficiency-pool finding (or honest NULL),
and exactly which flags are on/off in production.

---

## Acceptance
Every phase gate-green + committed; final `merge --no-ff`. Deliverables:
1. `fetch_leaderboard_paged` + tests (offset pagination, dedup, contiguous rank).
2. Depth-configurable universe with hot/deep split + `consensus_eligible` provenance, **default =
   today's top-40 behavior** until flags flipped.
3. A poll-cadence budget that keeps 429 rate ≈ 0 and cycle latency bounded at depth.
4. A **byte-for-byte non-regression proof** that widening the pool does not change any signal the
   consensus engine emits, until a deep trader is *earned* in.
5. An efficiency re-rank surfacing the small-bankroll sharps + the honest verdict on whether the
   deep pool carries certified edge.
6. A production config record and a short report.

## Standing disciplines
Extend, don't rebuild. Additive + reversible; every new flag defaults to today's behavior. Belief-
blind at the gate; depth is a candidate pool, not trust. Capture wide, promote narrow. Event-
clustered, sample-floored, shrunk — no pooled or small-sample green numbers. Cost-zero, paper-only,
**NO real money**. `merge --no-ff` at the end; deploy via the autoupdater. An honest NULL beats a
flattering number.
