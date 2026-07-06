# RUN — Live Fill Ingestion: event-driven sharps feed + latency→edge curve (AUTONOMOUS long-run)

> Paste as a fresh long-running Claude Code session in `~/polymarket-bot`. Self-contained.
> Read `run-prompts/README.md` §"Shared workflow", `DATA-MODEL.md`, and
> `reports/FAVCONSENSUS-DEEPEN_2026-07-06.md` (esp. the P&L-realism audit addendum) first.
> This is an **engineering + measurement** run. Paper-only. No real money. Alerts stay OFF.

---

## 0. One-paragraph mission

Today we SEE the sharps' fills by polling `data-api /activity` per wallet on a ~2-minute cycle
(12s `HOT_LANE` for the ~4-wallet follow-set only). An auto-trader is coming; its entry price is
set by how fast we see a fill, and the entry-realism audit showed the at-fire price drifts
adversely (+0.28¢ median on winners) before our first observation ~10–15 min later — with 22% of
picks never showing an observable follower price at all. **Build an event-driven LIVE ingestion
path for the tracked wallets' fills (target: fill→ingested in ~1–5s across the whole 560-wallet
universe), keep the existing poller as the reconciliation spine, and deliver the measured
latency→price-drift curve that finally tells us, in ¢-per-second, what speed is actually worth.**
The deliverable is a merge-ready branch + a numbers-first report — not a promise that speed = edge
(prior evidence says most of the edge survives 30 min; the drift lives in the first minutes and
has never been measured at second granularity — measuring it IS the point).

## 1. Where we are (facts you inherit — verify what you rely on)

- **Ingestion today:** `consensus_cycle` polls activity ~2 min/wallet (Semaphore
  `CONSENSUS_MAX_CONCURRENCY=8`); `leaderboard_tracker` refreshes the wallet UNIVERSE hourly
  (that cadence is fine — universe churn is slow; the LIVE need is FILLS, not ranks);
  `HOT_LANE` (12s, floored 5s) fast-polls only the router follow-set. Fill→signal is ~90–180s
  best case, minutes typically, and data-api gives 100-row pages, no startTs, 429s under load
  (gap-detection exists: `record_capture`).
- **Why speed might pay (and might not):** truth-audit attack B found NO in-poll-window latency
  sensitivity and decay analysis found no material edge decay <30 min — but both were measured at
  coarse (≥5 min) grain. The entry audit (2026-07-06, `reports/audit_entry_realism.json`) shows
  the adverse move happens BEFORE our first observation: at-fire → first-observed-mid ≈ +0.3–1.7¢
  on favorites, and `signal_price_trajectory` (dense capture, 45s loop, `DENSE_CAPTURE`) has only
  3 points in the 60–120s window ever. The 0.4–1.7¢ between "sharp's fill" and "our first sight"
  is the copyability tax; ~1–5s sight is the only way to bound its floor.
- **Deploy reality:** `main` auto-deploys on HEAD advance (launchd updater; rebuild only on code
  paths). Postgres 17 in Docker (`polymarket-bot-postgres-1`). Rust workspace, tokio, gate =
  `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace
  --all-targets && cargo test --workspace`. **Next free migration = 040** (check again at build
  time — concurrent chats have collided on numbers before). No websocket dependency exists in the
  workspace yet — adding one (e.g. `tokio-tungstenite`) is a deliberate, justified choice.
- Wallet identities in `trader_fills`/`followed_traders` are Polymarket **proxy wallets** (the
  address the data-api reports). Any on-chain source must be mapped/verified against these.

## 2. Candidate live feeds — investigate ALL, then commit to the best (Phase 1 decides)

Probe each live (cheap, read-only, throwaway scripts first) and write a decision memo with
measured numbers before building. Free/public endpoints ONLY — cost-zero is a hard rule.

- **F1: Polymarket CLOB WebSocket (market channel)** — real-time book + trade events per asset.
  Questions to answer live: max subscriptions per connection; can we subscribe to the ~2–5k open
  sports assets we track (sharding across N connections?); do trade events carry the
  maker/taker proxy addresses (if not, it's a price feed, not a fills feed — still valuable for
  the drift curve and auto-trader entry, but it does not replace wallet polling)?
- **F2: On-chain `OrderFilled` events, Polygon** — the CTF Exchange contract emits every fill
  with maker/taker addresses, asset id, amounts ⇒ the TRUE firehose: watch the 560 wallets
  directly, ~2s after the block. Questions: reliable FREE wss RPC (public endpoints: rate limits,
  reconnect behavior — measure, don't assume); do the event addresses match data-api proxy
  wallets 1:1 (verify on ≥50 known fills from `trader_fills` by tx_hash); parse price/size from
  the event (or pair with the CLOB feed).
- **F3: any other public real-time channel** (Polymarket RTDS/user channels, Goldsky subgraph
  websockets) — probe what exists; user channels need auth we don't have, subgraphs may lag.
  Document and rule in/out with numbers.
- **F0 (spine, keep):** the existing poller stays as the completeness/reconciliation source of
  truth. The live feed is an ACCELERATOR, never a replacement — extend, don't rebuild.

## 3. Build plan (phases; gate-green + live-verified + committed at each seam)

**P0 — Probes + decision memo.** Throwaway scripts (scripts/probe_*.py or a small Rust bin) that
connect to F1/F2/F3, run ≥30 min each, and measure: event latency vs block/exchange timestamp,
disconnect/reconnect rate, coverage vs `trader_fills` ground truth over the same window, address
match rate. Output `reports/live_ingestion_probe.json` + a decision: which feed(s), what sharding.
**STOP the run here if no feed achieves <10s latency with ≥95% coverage on free endpoints** —
write the negative honestly and deliver the probe report; do not build on a broken foundation.

**P1 — Live ingestion task (Rust, additive, default-OFF).** New tokio task (e.g.
`cycles/live_fills.rs`) behind `LIVE_FILLS=false`: subscribes to the chosen feed(s), filters to
tracked wallets, writes rows via the EXISTING `trader_fills` dedup path (tx-uniq index) with a
provenance marker (new nullable column or source tag, migration 040 — additive, idempotent) plus
`ingest_lag_ms` (event time → DB write). Backpressure-safe (bounded channel, drop-to-poller on
overflow — the poller catches anything dropped), reconnect with jittered backoff, metrics
(connected, events/s, lag p50/p99, dropped). ZERO behavior change while OFF; alert path untouched.

**P2 — Reconciliation + completeness instrument.** `scripts/live_reconcile.py` (self-testing):
over a shared window, live-ingested vs polled rows — coverage each way, dedup correctness (no
double-count through the unique indexes: prove it with an injected duplicate), latency
distribution per feed, per-wallet blind spots. Run it on ≥24h of dual capture. The completeness
claim is a SINGLE-PASS POSITIVE until this instrument confirms it — treat accordingly.

**P3 — The latency→edge curve (the measurement that decides everything).** With live fills + the
CLOB price feed, build `scripts/latency_edge_curve.py`: for each sharp fill on a favorite-band
market, the executable price path at t = fill+{1s, 5s, 15s, 30s, 60s, 120s, 300s, 900s} →
drift-vs-t curve by band × sport, event-clustered CIs, and the ¢-per-second answer including
"how much of the 0.4–1.7¢ measured tax is recoverable at 5s vs 60s vs 10min." Also replay: for
each historical `favorite` signal, how much EARLIER would consensus have formed on live timing
(consensus-formation latency, at-fire price delta). This inherits the prereg discipline: write
the small prereg (thresholds, grains, CIs) BEFORE looking at the curve.

**P4 — Wire-in (still paper).** If P3 shows recoverable drift: feed live fills into the consensus
cycle's vote window (flag-gated `LIVE_FILLS_TO_CONSENSUS=false` initially), so signals form
seconds after the sharps act; dense-capture trajectory gets a point at signal-fire (fixes the
favorite 895s-lag coarseness found by the tax audit). If P3 shows nothing recoverable — say so,
keep the feed as a capture-robustness win only, and scope P4 down to the trajectory fix.

## 4. Hard constraints (non-negotiable)

- **Paper-only. No real money. No live-alert changes** (all new flags default OFF, fail-closed).
  The auto-trader is a SEPARATE future run — build its data substrate, not the trader.
- **Cost-zero:** free public endpoints only; no paid RPC/infra; no `ANTHROPIC_API_KEY`; no child
  `claude` spawns. Be a good API citizen: measured backoff, connection counts documented, never
  hammer (429/bans hurt the standing capture spine).
- **Coordination + isolation:** `main` auto-deploys — work in a git worktree
  (`git worktree add wt/live-ingestion -b feat/live-ingestion main`), commit at every phase seam
  (reap-safety), ship only after the FULL gate is green; never merge/rebase by hand if
  `coord/merge.sh`-style flow exists for this repo — otherwise rebase onto fresh main, re-gate,
  `merge --no-ff`. Check migration numbers against main at merge time (collision history).
  Never bump the winmon→brainstem pointer.
- **Extend, don't rebuild:** the poller, dedup indexes, gap detection, hot lane, and dense capture
  all stay; the live feed slots beside them with provenance. Reuse `superkey.py`,
  `market_taxonomy.py`, the event-clustered stats conventions for every measurement.
- **Adversarial verification is mandatory:** after P2 and P3, an independent verify pass (fresh
  code, own SQL) attacks the completeness and latency claims — clock-skew (whose timestamp is
  "event time"? block time vs exchange time vs ingest time — define and defend), duplicate
  masking, survivorship (fills during disconnects), and the curve's leak classes (whole-event
  clustering, no within-event splits). Single-pass positives are headlines, not facts.
- **Self-testing instruments:** every script has `--self-test` on a synthetic fixture; Rust gets
  unit tests + a live integration test on the throwaway Docker PG (port 55432 pattern).
- **Checkpoint discipline:** write intermediate findings to `reports/` after each phase — long
  background runs get reaped; persist as you go.

## 5. Deliverables

- **Probe decision memo** (`reports/live_ingestion_probe.json` + entry in `reports/entries/`):
  per-feed measured latency/coverage/limits, the chosen architecture, and the STOP verdict if no
  feed qualifies.
- **Merge-ready `feat/live-ingestion` branch** (or merged if the gate + verify pass are green and
  the merge flow allows): live ingestion task default-OFF, migration 040, reconciliation + curve
  instruments, all self-tests green.
- **The latency→edge curve report** (`reports/entries/<date>-latency-edge-curve.md`): drift vs
  seconds by band × sport with CIs, the ¢/s answer, consensus-formation-latency replay, and an
  explicit verdict: what does 1–5s sight buy over 60s and over the status quo, in expected
  edge-per-bet — stated against the audit's honest +3–5%/bet baseline.
- **Docs:** DATA-MODEL.md section for the new source/provenance; PROGRESS.md entry;
  ≤10-line memory-update note for [[project-polymarket-consensus]] +
  [[project-polymarket-refined-strategy]] (what was built, the measured latency, the curve verdict).
- **Explicit next-step line for the auto-trader run:** which entry convention it should assume
  (at-fire? fill+5s? first-ask?), backed by the curve.

## 6. Anti-patterns — do NOT (we have paid for each)

- ❌ Rip out or bypass the poller ("live is better") — it is the completeness spine and the
  reconciliation ground truth.
- ❌ Trust a single-pass completeness/latency claim (the +4.8% maker read, the +10.2% router read,
  and the "no losing day" claim all died under verify — this run's claims get the same treatment).
- ❌ Subscribe-to-everything without measuring connection limits first; get the capture IP
  rate-limited and damage the standing spine.
- ❌ Paid infra "just for the run". Cost-zero.
- ❌ Claim "speed = edge" without the P3 curve; prior coarse-grain evidence says most edge
  survives 30 min — the honest question is the first-minutes drift, and the answer may be "little".
- ❌ Touch alerts, real money, the winmon pointer, or applied migrations (edit NOTHING in
  `migrations/0{01..39}_*` — append 040+ only).
- ❌ Leave results only in context — checkpoint to `reports/` at every seam.
