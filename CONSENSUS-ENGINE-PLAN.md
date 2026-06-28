# Consensus Copy-Trading Alert Engine — Design & Build Plan

> Status: **living document.** Started 2026-06-28. This is the backbone for a multi-run
> autonomous build. Each run updates the "Progress log" at the bottom.

## 1. Mission

Turn `~/polymarket-bot` from a *manual, per-trader* copy bot into an automatic
**consensus-alert** product:

1. Continuously track the **top-N traders** on the Polymarket leaderboard (auto, configurable).
2. Detect when those traders **converge** on the same directional position.
3. **Alert** (Telegram) when a *good* consensus trade appears — rare, high-conviction, actionable.

Primary deliverable is **alerts** (human-in-the-loop). Paper bets only; **no real money**
(the repo is research-only). Profit orientation = surface the highest-edge consensus the
crowd of proven winners is making, before the market fully moves.

## 2. What already exists (do not rebuild — extend)

- `copy-trading-bot`: polls **manually `/follow`ed** wallets' `/activity`, dedups, staleness +
  price-drift filters, quarter-Kelly paper bet per `copy:<wallet>` strategy, Telegram alert,
  housekeeping resolves bets. Mirrors SELL as exit.
- Leaderboard fetch (`fetch_leaderboard`, `/v1/leaderboard`) is **read-only**, used only by the
  `/leaderboard` command. No auto-follow, **no consensus**.
- `common`: `PgPortfolio` (Postgres), `followed_traders` + `copy_trade_events` tables,
  Kelly, Telegram notifier, formatting, metrics.

**Gap = the entire consensus layer + auto-tracking of the top N.** That is what we build.

## 3. Validated reality (2026-06-28)

- `cargo check --workspace` is **green** at baseline.
- APIs live:
  - `GET /v1/leaderboard?timePeriod={DAY,WEEK,MONTH,ALL}&limit=N` (cap 50) →
    `rank, proxyWallet, userName, vol, pnl`.
  - `GET /activity?user=<wallet>&type=TRADE&limit=N` →
    `conditionId, outcomeIndex, outcome, side, price, usdcSize, slug, eventSlug, title, timestamp`.
- **A position must be keyed by `(conditionId, outcomeIndex)`** — buying "No" or a different
  outcome is the *opposite* bet. The existing copy cycle hardcodes `BetSide::Yes` and ignores
  `outcomeIndex` — a correctness bug for consensus. We key correctly.

### 3.1 The empirical pivot (why naive consensus is noise)

Live 3–7d probe of ~143 top traders:
- Raw "(market,outcome) with ≥2 top traders" = **138** hits — but **confounded**:
  - Top traders sit on **both sides** of popular markets (market-makers / opposing bettors).
    e.g. "Portugal win" had 13 BUY *No* **and** 8 BUY *Yes*.
  - Leaderboard is currently **~90% sports** (World Cup). The ML `trading-bot` blocks sports
    for *its* model, but copy-consensus is a different mechanism — top traders *do* earn on
    sports. **Sports is a config axis, decided by backtest, not assumed bad.**
  - "Same outcome" entries span **wild price ranges** (0.03–0.99) → not a coherent entry.
- **Strict gate that isolates signal:** NET directional (`backers − opposers ≥ 3`,
  `opposers ≤ 1`) + price-coherent (entry **σ ≤ ~0.10**) + fresh (**< 48h**).
  This collapsed 1021 raw positions → 55 (≥3 backers) → **8 clean** → 1 non-sports.
  That rarity is the feature: alerts should be few and high-conviction.

## 4. The consensus model

### 4.1 Tracked-trader universe
- Refresh from leaderboard every `TRACK_REFRESH_MINS` (default 60).
- Universe = union of top `TRACK_TOP_N` (default 40) across configurable periods
  (default `WEEK,MONTH` — recent + sustained skill; ALL skews to a few whales, DAY is noisy).
- Persist provenance: rank, pnl, vol, which periods, first_seen, last_seen. Mark inactive
  when they drop off for `TRACK_DROP_GRACE` refreshes (don't thrash).
- Per-trader **quality weight** `w_q` (see 4.3) and **directionality** score (see 4.4).

### 4.2 Trade ingestion
- Poll each tracked trader's `/activity` since `last_checked_at` (reuse existing dedup table,
  extended with `outcome_index`, `event_slug`, `title`).
- Keep BUY entries; SELLs feed exit/again-consensus logic later.
- Store into a rolling in-window store keyed by `(conditionId, outcomeIndex)`.

### 4.3 Consensus scoring (per candidate `(market, outcome)`)
A signal is scored, not boolean. Score components (each documented, tunable):
- **Net conviction**: `Σ w_q(backers) − Σ w_q(opposers on other outcomes of same market)`.
- **Breadth**: count of *distinct* backers (≥ `MIN_BACKERS`, default 3).
- **Opposition penalty**: hard cap `opposers ≤ MAX_OPPOSERS` (default 1), else reject.
- **Price coherence**: backers' entry-price σ ≤ `MAX_PRICE_STD` (default 0.10); tighter = higher.
- **Freshness**: most-recent backer < `MAX_AGE_MINS` (default 2880 = 48h); newer = higher.
- **Current-vs-entry drift**: current YES/outcome price still within `MAX_DRIFT` (default 0.06)
  of mean entry → still actionable (re-uses existing price-drift infra).
- **Money weight (soft)**: total `usdcSize`, log-scaled — informational, lightly weighted
  (whales already captured by quality weight; avoid double-counting).
- **Trader quality `w_q`**: from leaderboard rank/pnl + (later) realized win-rate of their
  copied trades. Down-weight MM-like wallets (4.4).

Output tiers (configurable thresholds):
- `WATCH` (forming) → digest only.
- `STRONG` → push alert.
- `ELITE` (high net + tight price + fresh + ≥1 elite trader) → priority push.

### 4.4 Anti-confounds (the hard part, this is where edge lives)
- **Directionality filter**: a wallet that appears on *both* outcomes of the same market within
  the window is a likely MM for that market → its votes there are discounted/ignored.
- **Per-trader global directionality score**: fraction of recent markets where the trader took
  both sides; chronically two-sided wallets get a low `w_q` everywhere.
- **De-dupe wash/laddering**: multiple fills by one wallet on one outcome = ONE backer (distinct
  wallets only, already enforced by keying backers as a set).
- **Sport tagging** via slug/title heuristics → `is_sports` flag on every signal; alerts and
  backtest can include/exclude by config.

## 5. Alerting
- Rich Telegram message: market title, outcome, # backers (net), named traders w/ rank,
  mean entry price & σ, current price & drift, total $, tier, Polymarket link, sport tag.
- Dedup: one alert per `(market, outcome, tier)`; re-alert only on tier upgrade or material
  new backer. Cooldown per market.
- Owner + subscribers broadcast (reuse `broadcast`).

## 6. Validation (Phase C — the part that decides if this is real)
- **Replay/backtest**: pull historical activity for tracked traders, reconstruct consensus
  signals at their formation time, then look up market **resolution** (Gamma) to compute:
  hit-rate, ROI at mean-entry price, CLV (entry vs price 1h/24h later and vs close).
- **Forward tracking**: log every live signal + outcome; calibrate score → realized hit-rate.
- Slice by: sports vs non-sports, tier, net size, price band, time-to-resolution.
- **Honest verdict**: if consensus has no edge over the market price it's entering at, say so
  and report what (if anything) does. (Mirrors the Foresight discipline.)

## 7. Architecture / where code goes
- `common/src/storage/`: migration `021_consensus.sql` (tracked-trader provenance cols +
  `consensus_signals`, `consensus_alerts`), methods in `copy_trade.rs` / new `consensus.rs`.
- `copy-trading-bot/src/scanner/leaderboard_tracker.rs`: auto-refresh universe.
- `copy-trading-bot/src/scanner/consensus.rs`: windowed store + scoring (pure, unit-tested).
- `copy-trading-bot/src/cycles/consensus_cycle.rs`: detect → score → alert.
- `copy-trading-bot/src/config.rs`: new env knobs (section 4 defaults).
- `copy-trading-bot/src/telegram/commands.rs`: `/consensus`, `/tracked`, `/track on|off`.
- Keep existing per-trader copy untouched & runnable in parallel.

## 8. Config knobs (env, defaults)
`TRACK_ENABLED=true TRACK_TOP_N=40 TRACK_PERIODS=WEEK,MONTH TRACK_REFRESH_MINS=60`
`CONSENSUS_INTERVAL_MINS=2 CONSENSUS_WINDOW_HOURS=48 MIN_BACKERS=3 MAX_OPPOSERS=1`
`MAX_PRICE_STD=0.10 MAX_AGE_MINS=2880 MAX_DRIFT=0.06`
`CONSENSUS_INCLUDE_SPORTS=true STRONG_NET=4 ELITE_NET=6`

## 9. Build phases (tasks #1–#4)
- **A** Reality check & spec — ✅ (this doc).
- **B** Consensus engine core — auto-track, scoring (pure+tested), migration, alerts.
- **C** Validation — backtest + forward tracking + calibration + honest verdict.
- **D** Productize — config, commands, metrics, docs, docker, fmt/clippy/test green.

## Progress log
- 2026-06-28 (run 1): Mapped repo; validated APIs live; baseline `cargo check` green; ran live
  consensus probes → established the net-directional/price-coherent design pivot; wrote this plan;
  created branch `feat/consensus-engine`.
- 2026-06-28 (run 1, cont.): **Phase B COMPLETE & verified working end-to-end.**
  - Built `scanner/consensus.rs` (pure scorer, 9 unit tests), `scanner/leaderboard_tracker.rs`
    (auto-track top-N), `cycles/consensus_cycle.rs` (poll→book→score→alert), migration
    `021_consensus.sql`, `storage/consensus.rs` (DB), config knobs, `/consensus` + `/tracked`
    commands, wired both new loops into `live.rs`. Extended activity parsing with
    `outcome_index/outcome/title/event_slug`.
  - **CI gate GREEN**: `cargo fmt --check`, `clippy --workspace --all-targets -Dwarnings`,
    `cargo test --workspace` (all pass).
  - **Live integration test** (Docker Postgres + live Polymarket API, dummy Telegram):
    migrations applied; tracker auto-followed **62 traders** (top-40 × WEEK,MONTH); consensus
    cycle polled 62, built **353 market books**, found 1 signal (WATCH: "Austria win → No",
    net 2, σ 0.074) → correctly *no* alert (below STRONG). Persistence confirmed in DB.
  - Docs: README consensus section + commands; `.env.example` knobs.
- 2026-06-28 (run 1, cont.): **Phase C foundation — forward self-validation wired.**
  - **Honest finding: a same-day historical backtest is NOT feasible.** The tracked traders'
    available recent activity is ~entirely on *live, unresolved* markets (World Cup period →
    sports-heavy; of 150 recent top-trader slugs, 78 in Gamma, **0 closed**). `startTs/endTs/
    offset` on the activity API are effectively ignored (always newest-first), and hyperactive
    whales bury older trades. So edge can only be measured **forward**.
  - Built `GammaMarket::resolved_outcome_won(idx)` (multi-outcome resolution via
    `outcomePrices[idx]`, +2 unit tests) and wired consensus resolution into the housekeeping
    loop → every signal auto-resolves as its market closes; `/consensus` shows accruing hit-rate
    (overall + non-sports). Validated all forward-tracking SQL against a live Docker Postgres.
  - CI gate GREEN (fmt/clippy-Dwarnings/test). Backtest harness kept at
    `scratchpad/backtest.py` (mirrors Rust gates; ready to re-run once resolved data exists).
- **NEXT (finish Phase C + Phase D):** (a) **deploy** with real Telegram creds + persistent PG
  and let signals accrue → read the forward hit-rate after markets resolve (the real edge test);
  (b) re-run `backtest.py` in ~1-2 weeks when current World-Cup markets have closed; (c) Prometheus
  consensus metrics + Grafana panel; (d) tune thresholds from forward data; (e) optional WATCH
  digest. Open questions still: is sports-consensus profitable or just the favorite the line
  already prices? does net size / price band predict hit-rate?
