# FORGE DEBATES — Live Fill Ingestion

Compressed record of the two designs, the reality-verification findings (all of them), the per-gap
synthesis decisions, and the insights that emerged.

---

## The two designs in one line each

- **Design A (Direct).** We own ~80% of the machinery; wire the last 20%: an `eth_subscribe(logs)`
  on-chain fills client (`live_fills.rs` cloned from `hot_lane.rs`), a 17-col cloned
  `insert_trader_fills_live`, migration 040 (`source`+`ingest_lag_ms`), a live F1 consumer +
  `fill_price_trajectory` table for the curve, two `--self-test` Python instruments. Deliverable
  (curve) rides on the on-chain build. **Its own key finding, and it's correct:** the tx-index does NOT
  auto-dedup live vs poll because the poller's `price` is a full-precision VWAP — so A builds a
  three-layer dedup defense.
- **Design B (Rethink).** Attack the dependency chain. The curve needs low-latency **price
  observation** + each fill's **true time** — and `trader_fills.ts` already IS that time. So store the
  CLOB **price tape** (wallet-blindness irrelevant for price) and anchor the drift curve **offline**
  against `ts`. The curve then ships **regardless of whether the on-chain fills client is ever built**.
  Two independent STOP gates (measurement vs ingestion); F2 demoted to optional `newHeads+getLogs`
  accelerator; GAP-2 trajectory fixed offline from the tape.

---

## Verification findings (all, by severity)

### BROKEN

- **B-dedup-1 | Design B's "round live price to 2dp for tx-index byte-compat" double-counts ~half the
  fills.** B's appendix checklist item #1 asserts *"trader_fills.price stores 2dp values [DB:mine: 0.5,
  0.92, 0.6, 0.4, 0.75…]"* and rounds the live price to 2dp. **This is a sampling artifact.** My query:
  ```
  SELECT length(split_part(price::text,'.',2)) dec_len, count(*)
  FROM trader_fills WHERE ts > now()-interval '24 hours' GROUP BY 1 ORDER BY 1;
   1|29030  2|151036  3|50422 ... 10|42301 ... 16|50499  17|18492  18|2474 ...
  count(*) FILTER (>2dp) = 181336 / 361368 total  ==> 50.2% carry MORE than 2 decimals.
  sample >4dp: 0.9969990269270036, 0.5300000067680002, 0.16181060606060607 ...
  ```
  `trade_to_fill` (`consensus_cycle.rs:319`) sets `price: tr.price`, and `TraderTrade.price` is the
  data-api's `usdcSize/size` **VWAP** — full precision, not a tick grid. Migration 027's unique index is
  `(tx_hash, condition_id, outcome_index, side, price)`. Rounding the live price to 2dp yields a
  different index key from half of poller rows → no conflict → **double-count**. *Fix:* adopt Design A's
  three-layer dedup (source-scoped `WHERE source='live_onchain'` index + app pre-check +
  poll-over-live collapse). **This is the price-precision verdict: Design A wins the dispute outright,
  with query evidence.**
  - **Mitigating fact that reshapes the risk assessment:** Design B's **tape/curve path never writes
    into `trader_fills`** (the tape is a separate append-only `clob_price_tape`). So B-dedup-1 damages
    **only** B's optional F2 build — **not** its deliverable. A's deliverable, by contrast, rides on the
    F2 build whose dedup is the load-bearing risk. Net: adopt B's decoupled spine, A's F2 dedup.

### WEAK

- **A-coupling-1 | Design A couples the deliverable to the fragile on-chain build.** A's chain is
  P1(on-chain)→P2→P3(curve), all behind one STOP rule on the on-chain feed. If no free RPC holds a
  30-min subscription (a real possibility A itself flags), A **ships nothing**. Verified root cause is
  removable: `trader_fills.ts = tr.timestamp` (`consensus_cycle.rs:334`) is the clean exchange/fill
  clock — the curve is not downstream of ingestion. *Fix:* Design B's decoupling.
- **A-insert-clone | Design A clones `insert_trader_fills` into a 17-column `insert_trader_fills_live`.**
  Unnecessary divergence from the single write gate the run prompt mandates ("the EXISTING dedup path").
  `NewTraderFill` (`consensus.rs:108`) is constructed in prod only at `trade_to_fill:319` (+3 test
  sites: `consensus.rs:2257/2498/2881`); `hot_lane`/`capture_dropped`/`backfill` all route through
  `trade_to_fill`, so adding two appended `Option` fields + binding them in the one `insert_trader_fills`
  is a small, contained change that keeps a single gate. *Fix:* extend, don't clone.
- **A-lag-column | Design A stores `ingest_lag_ms` (a duration).** A precomputed duration bakes in
  whatever clock was used. Design B's `live_seen_at TIMESTAMPTZ` is strictly more information (lag =
  `live_seen_at − ts` at read, recomputable against any defended clock). *Fix:* B's timestamp column.
- **A-transport | `eth_subscribe(logs)` wss as sole F2 transport.** Free-RPC wss log subs are the first
  thing silently dropped, and a silent drop is a survivorship hole the adversarial pass will hunt. B's
  `newHeads + eth_getLogs(HTTP)` is idempotent/gap-free (a missed block just widens the next range).
  *Fix:* prefer getLogs, keep wss as fallback; probe both.

### INCOMPLETE (both designs — flagged as to-be-probed, correctly)

- **ws.rs does NOT parse `best_ask` or any `timestamp` today.** Verified by reading `handle_message`
  (`ws.rs:199-295`): `best_bid_ask` reads only `json["best_bid"]` (`:213`); `last_trade_price` reads
  `price`,`size` (`:264`); **no `best_ask`, no `timestamp`, no maker/taker anywhere.** Both designs
  correctly label `best_ask`/`exch_ts` presence as **to-be-confirmed in P0**. Confirms F1 is wallet-blind
  *in code* (not just suspicion). Blueprint carries the `last_trade_price + fetch_best_ask` fallback if
  `best_ask` is absent.
- **`MAX_SUBSCRIPTIONS=200` is an untested constant** (`ws.rs:14`). Both correctly make it a P0 probe.
- **F2 contract addresses / `OrderFilled` topic0 / maker=proxy?** Both correctly treat as P0-B
  hypotheses to confirm by decoding a known `tx_hash` (100% coverage verified: 361328/361328 last 24h).
- **Tape `events/s` (storage sizing)** unknown; both make it a P0-A output, bound by tracked-only +
  retention. B calls out the unbounded-growth risk explicitly; carried into the blueprint.

### CONFIRMED (claims both relied on — spot-checked, all hold)

- Migration 027 index = `(tx_hash, condition_id, outcome_index, side, price) WHERE tx_hash IS NOT NULL`
  ✓ (read `migrations/027`). Migration 026: `price DOUBLE PRECISION`, `ts NOT NULL`,
  `ingested_at DEFAULT NOW()` ✓.
- `ingested_at` contamination: median `ingested_at−ts` = 90.4s, **5.19% of 24h rows >1h**
  (18771/361389) ✓ — matches the Diagnostic's finding; `ingested_at` is not a clean clock.
- `trade_to_fill:307`, `trade_to_window_vote:593`, `insert_trader_fills:1270`, `record_capture:1353`,
  `fetch_clob_market:352`, `outcome_token_id:301`, `fetch_best_ask:330`, `superkey.super_event:43`,
  `live.rs` spawn gates (`dense_capture:227`, `hot_lane:440`) — all exist at claimed lines ✓.
- `NewTraderFill` construction: prod only at `trade_to_fill:319` + 3 test sites; downstream lanes route
  through `trade_to_fill` — so adding fields does not break `hot_lane`/`capture_dropped`/`backfill` ✓.
- `trader_fills.ts` is the clean fill clock (`ts: tr.timestamp`) — **the load-bearing premise of
  Design B's decoupling** ✓.

---

## Per-gap synthesis decisions

| Gap | Choice | One-line rationale |
|---|---|---|
| **GAP-0** probe + STOP | **rethink (B)** + A's JSON rigor | Two-gate split (measurement vs ingestion) so an F2 failure can't abort a deliverable that never needed it; A's price-byte-match probe kept because it selects the F2 dedup layer. |
| **GAP-1** fast fills | **hybrid** | B's reframe (F2 optional, decoupled) + B's `newHeads+getLogs` transport (gap-free) — but **A's three-layer dedup** because B's 2dp rounding is broken (proven double-count). |
| **GAP-2** trajectory hole | **rethink (B)** | Store the tape, anchor offline on the fill's `ts`; lower-risk than A's new live F1 consumer + `fill_price_trajectory` table + FK gymnastics. The tape IS the substrate. |
| **GAP-3** F1 limits / lift | **hybrid** | Probe the real max-subs before broad subscribe (both) + **copy** `ws.rs` into copy-trading-bot, don't generalize into `common` (A's reasoning: F1≠F2 protocol). |
| **GAP-4** reconciliation | **hybrid** | B's tape-as-oracle + fuzzy WS↔poll join (attribution-latency floor with zero on-chain client, a real pre-F2 input) + **A's throwaway-PG dedup proof** (load-bearing given the price verdict). |
| **GAP-5** the curve | **rethink (B) + refined estimator** | Anchor on clean `ts` against the stored tape (independent of F2); A's and B's event-clustered/within-category/prereg estimator is near-identical — carry the observable-denominator + dual-clock skew reporting explicitly. |
| **GAP-6** event-time | **refined** | B's `live_seen_at` timestamp beats A's `ingest_lag_ms` duration; **plus** a correction both got slightly wrong — extend the single `insert_trader_fills`, don't clone (A) or leave ambiguous (B). |
| **GAP-7** wire-in | **rethink (B)** | Trajectory fix delivered offline from the tape (no `strict` byte-identity risk); live-vote wiring doubly-gated (F2 built AND P3 positive), reusing hot-lane scoped scoring. |

**Key tension resolved (per the lead's charge):** does B's curve-decoupling better satisfy the run
prompt (which calls the curve "the measurement that decides everything")? **Yes.** The run prompt's own
STOP rule conflates the measurement and ingestion feeds; verification shows the curve's true dependency
(`ts` + a price tape) is cheaper, zero-new-dep, and survives the free-RPC worst case. A's tighter
fills-first path is more elegant *if* a free RPC cooperates, but it stakes the entire deliverable on the
one thing the run prompt is most worried about. B's reshape ships **something honest** (the curve, or a
measured negative on tape coverage) even if every free RPC fails.

**Resolved sub-decisions:** ws.rs → **copy** into copy-trading-bot (not generalize); F2 transport →
**`newHeads+getLogs`** (not `eth_subscribe(logs)`); trajectory → **offline tape backfill** (not live
capture); insert path → **extend the one gate** (not clone); event-time → **`live_seen_at` timestamp**
(not `ingest_lag_ms`).

---

## Insights that emerged

1. **The tape-decoupling reframe (B's central move).** The deliverable was never downstream of
   ingestion. `trader_fills.ts` is the clean fill clock; a wallet-blind price tape + offline join
   answers the ¢/s question with zero on-chain build. This is the single highest-leverage decision and
   it inverts the run prompt's phase order (tape-first, fills-optional).
2. **The price-precision verdict (kills B's dedup, vindicates A's).** Half the fills carry >2dp; the
   poller price is a full-precision VWAP. 2dp rounding double-counts; cross-source tx-index dedup is not
   free. A's three-layer defense is mandatory *for the F2 build* — but the F2 build is now optional, so
   the risk is contained to an accelerator, not the deliverable. The two insights compose: **use B's
   spine, A's F2 dedup.**
3. **`ingested_at` contamination (both surfaced; verified 5.19% >1h).** Event-time must be `ts`, not
   `ingested_at`; latency = `live_seen_at − ts`. Store a timestamp, not a duration, so a mis-defended
   clock is recoverable.
4. **The `ws.rs` discovery.** A working CLOB WS client + `tokio-tungstenite=0.28` already in the
   workspace makes the tape a copy-not-write job (the run prompt's "no websocket dependency exists" is
   false at workspace level). But it parses only `best_bid` today — `best_ask`/`exch_ts` are genuine P0
   unknowns with a REST fallback.
5. **The fuzzy-join latency floor (B).** Matching the anonymous trade tape to polled fills measures
   "how much earlier could we have seen it" **before** committing to the F2 build — turning a build
   decision into a measured one.
6. **Two-gate STOP as a 0-line conceptual fix.** Splitting one STOP into measurement + ingestion gates
   saves the run from a false negative at no code cost.

Both deliverable files written:
- `FORGE_PLAN_LIVE_INGESTION.md`
- `FORGE_DEBATES_LIVE_INGESTION.md`
