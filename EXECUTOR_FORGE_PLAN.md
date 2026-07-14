# EXECUTOR FORGE PLAN — the Polymarket real-money execution layer

**Status:** blueprint, forged 2026-07-13 by a 4-agent forge (Dossier → Diagnostic → Designer A "direct" → Designer B "rethink" → Reality-Check + Synthesis). Every SDK fact below was re-verified against the `polymarket_client_sdk_v2` v0.6.0 crate source by the synthesizer, not taken from either designer.

**What the system does differently once this is built.** Today a signal ends in a phone notification and a Postgres row; nobody has ever placed an order. After this build, a signal becomes a *tradeable object* (token_id, tick size, neg-risk flag, a real book snapshot) that flows through a per-arm execution policy, a persistent per-arm cage, and an order state machine in which **the exchange is the only source of truth** — and which can be stopped, from a wedged process, in under two seconds. It ships **default-OFF at every one of three independent locks**, and the first three phases place **zero orders and cost zero dollars** while producing the measurements that decide whether a fourth phase should ever exist.

---

## § HONEST PREAMBLE — what this can and cannot promise

**No bot can promise "never negative."** A day on `weather_fav` is **one correlated bet** (a heat dome resolves ~20 cities together). Long losing streaks are the *expected behaviour of a thin real edge*, not evidence against it. Any system that promises otherwise is lying, and a system that *believes* it will blow up trying to make it true.

What is promised instead, and what this document is accountable for:

- **Bounded.** Per-signal cap ($50 hard), per-cluster budget (the *game* is the unit, not the market), daily deploy cap, day stop-loss, max-drawdown latch, slate stop — all latching, all persisted, all surviving a restart, all with a cancel-all-then-halt path.
- **Detected.** The *fill* degrading (the most likely quiet death) is caught in ~1 trading day by a slippage EWMA. The *pick* degrading is caught — **if and only if a pre-registered Phase-0 falsifier passes** — in 3–13 days by a ΔCLV change-point detector against a matched placebo pool.
- **Stood down from.** A graded ladder where detector confidence sets response severity: de-size → demote a rung → halt the arm → retire the arm. **Demotion is automatic and instant. Promotion is evidence-gated and human-approved.**

**The honest ceiling.** $50/signal × ~20 signals/day ≈ **$1,000/day deployed.** Against the only clean-basis edge measurement we have (mid-basis ~+8.0% of notional), and paying the measured taker-at-fire premium (+3.4¢ ≈ 4.0% of notional at p≈0.85) plus a fee of 0.75–2.08%, **net is ≈ +1.9% to +3.25% ⇒ $19–$33/day, before our own unmeasured market impact.** This is not a large business. The brief's "$85/day gross" is the **mid-basis** figure — the price we cannot trade at — and is **not achievable net.** Design for the real number.

**Four retractions, two of which reversed sign.** The binding evidence rule applies to this document as much as to any script: *no claim ships without (a) a control/placebo arm, (b) a significance test, (c) explicit n + dispersion.* Where a number below lacks those, it is labelled **HYPOTHESIS** and the thing that would falsify it is named.

**And the one thing this plan refuses to do:** it does not pick a winning execution policy. It builds the machine that *measures* them, ships the **cheapest-to-be-wrong default** (`take_at_fire` — the only policy whose cost is actually measured), and makes every alternative a one-row `UPDATE` away once it has earned it. Both designers wanted to pick a winner. Both picked different winners. Both proofs failed verification (§ Rejected approaches). That disagreement *is* the finding.

---

## § THE COST MODEL — recomputed from the measured numbers, not asserted

Anchor: p ≈ 0.85, $50/signal ⇒ **58.8 shares**. **1¢ of price = $0.588/turn = $11.8/day** across ~20 signals. $1,000/day deployed.

| Line | ¢/turn | % of notional | $/day | Basis / n |
|---|---|---|---|---|
| **Gross edge (mid basis)** | — | **+8.0%** | **+$80** | 324 resolved / 168 events / 10 days. ⚠️ **You cannot trade at mid.** This is the ceiling, not a plan. |
| − taker premium at fire (ask − mid₀) | **3.4¢** | −4.0% | **−$40** | prereg §0, n≈20–22/horizon |
| − fee (band, unresolved) | 0.6–1.8¢ | −0.75% … −2.08% | **−$7.5 … −$20.8** | docs `feeRate×(1−p)` = 0.75% vs on-chain `feeRateBps×min(p,1−p)/p` @1000bps = 2.08%. **See Item 3.** |
| **= net taker-at-fire** | | **+1.9% … +3.25%** | **+$19 … +$33** | ≈ the dossier's independently-stated "~+1.2% realizable at the fire ask" (same order of magnitude; bases differ) |
| **Prize A — the maker leg** (post-only fills at mid: pays **neither** the 3.4¢ **nor** the fee) | −3.4¢ … −5.2¢ | **+4.75% … +6.1%** | **+$47 … +$61** | **Fill rate is UNKNOWABLE before Rung 2.** No number about it may be believed. |
| **Prize B — `patient_take(15m)`** (ask decays 3.4¢→0.6¢ by +15m) | −2.8¢ | **+3.3%** | **+$33** | ⚠️ **This intervention has ALREADY been measured with a placebo: +2.05¢ ± 4.0¢, p = 0.36 (n=20 vs 72 placebo), and was RETRACTED as a lever.** See § Rejected approaches. |

**Read that table twice.** The two candidate levers are each **the size of the entire net business** — and both are unmeasured or measured-and-not-significant. **Execution policy is worth more than every selection refinement ever attempted** (four of which died at this same wall). It is also the thing we know least about. That is the whole reason this build exists, and it is why Phases 0–2 place no orders.

**Numbers that do NOT compose, and must not be added:** the "+3.4¢ taker premium", the "+1.09¢ spread crossed" (n=85), and the "2.2¢ slippage @ $50" (33 books) are **overlapping decompositions of the same cost**, on different bases (one of which, the historical at-fire mid, was the *vote-mean* — capture-defect D2, ~1.65¢ of understatement). Designer A's cost model added the spread *and* the book-walk and arrived at +0.7% "reproducing the measured +1.2% to within 0.5pp." **That agreement is a coincidence built on a double-count.** No $/day figure in this plan is load-bearing until Item 1 (`entry_ask_fire`) has accrued ≥2 clean weeks.

---

## § ITEMS — dependency-ordered

Each item: **Before → After**, **Implementation** (real types, real SQL, real API), **Integration points** (`file:line`), **Cost**, **Source** (direct = Designer A · rethink = Designer B · hybrid · refined).

---

### 1. Start the clock: `entry_ask_fire` — Current: the only basis the gate accepts is not being captured → Target: it is

**Before.** The frozen certification gate accepts exactly one basis: the executable **ask** — *the price WE pay*. The column it reads (`entry_ask`, migrations 030/032) is **D4-corrupt**: housekeeping prices only **172/399 (43%)** of in-band signals; priced signals win **87.8%**, missed signals win **96.5%** — a **+8.7pp selection gap** — because fast-resolving chalk (the winners) resolves *before* the pricing pass reaches it. Median capture lag **1,300s**; max **2.5 days**. Migration 042 on `feat/paper-executor` fixes this (`entry_ask_fire`, captured *inside* `consensus_cycle.rs` at the fire instant, paired with `entry_ask_fire_mid` = a TRUE `(bid+ask)/2` from ONE `/book` response — **never** the vote-mean, which was defect D2). **It is built, unmerged, and NOT ARMED** (`CAPTURE_ENTRY_ASK_AT_FIRE` is not set in `.env.consensus`).

**After.** Merged and armed. Every new signal carries the price we would actually have paid, at the instant we would have paid it.

**Implementation.** Merge `feat/paper-executor` (migration `042_entry_ask_at_fire.sql`) **alone, first, today**. Set `CAPTURE_ENTRY_ASK_AT_FIRE=1` in `.env.consensus`. Then re-point the ledger's basis:

```sql
-- common/src/storage/consensus.rs:900-945, append_paper_bet
-- WAS: COALESCE(entry_ask, initial_market_price + $5)      -- $5 = EXEC_HAIRCUT = 0.01
-- NOW:
COALESCE(entry_ask_fire, initial_market_price + $5) AS entry
```
`entry_ask` is dropped from the COALESCE chain entirely. **It is dead for measurement.** Do not filter on it, do not compute ROI on it, do not band-select on it — *filtering a band on a corrupt column bakes the corruption into sample selection, which is the error that produced retraction #4.*

**Integration points.**
- `common/src/storage/consensus.rs:900-945` — `append_paper_bet()` — basis becomes `entry_ask_fire`.
- `.env.consensus` — add `CAPTURE_ENTRY_ASK_AT_FIRE=1`.
- `migrations/042_entry_ask_at_fire.sql` — merges as-is.

**Cost.** $0. One extra `/book` GET per fired signal (~20/day; the `/book` rate limit is 1,500 per 10s — we are four orders of magnitude under it).

**Why this is Item 1 and not part of the executor.** **Backfill is impossible.** The at-fire book is gone the moment it moves; `clob_price_tape` only starts 2026-07-09 and holds a fire-time ask for **21 of 395** historical `favorite` signals. **Every day this flag stays off is a day whose true realizable edge can never be known.** It is the highest evidence-per-unit-risk action available, it requires zero executor code, and **nothing downstream of it means anything until it has run for ≥2 weeks.**

**Source:** hybrid — both designers independently made this their Phase 0.1, and the Diagnostic's C1 adjudicated the basis contradiction (the *column's data* was retracted, never the *concept* of an ask basis; `EXECUTION-READINESS.md` and commit `879a7d8` agree completely).

---

### 2. Fix the tape's universe — Current: `AND is_sports` → Target: the tape covers the markets we actually trade

**Before.** `clob_price_tape` has **ZERO weather rows**, so `weather_fav` — the strongest candidate arm (LODO survives, belief-blind null **p = 0.0005**, low day-correlation with the champion) — is **the one arm we are structurally blind to.** Root cause, read verbatim at `common/src/storage/consensus.rs:1629`:

```sql
SELECT DISTINCT condition_id, outcome_index
  FROM trader_fills
 WHERE ts > now() - ($1::text || ' hours')::interval
   AND is_sports                                                     -- ← BUG 1: literal exclusion
   AND condition_id IS NOT NULL
   AND wallet IN (SELECT lower(proxy_wallet) FROM followed_traders)  -- ← BUG 2: wrong source table
```

**Two independent bugs.** Deleting `is_sports` is **not sufficient**: the universe is derived from *tracked traders' fills*, not from *our own fired signals*, and `weather_fav`'s voter pool is rank ≤250 — far wider than the ~follow-set. There is no guarantee it covers the markets our arm fires on.

**After.**

```rust
/// Drive the tape universe from OUR OWN FIRED SIGNALS (the markets we actually execute),
/// UNIONed with tracked traders' fills (which the latency-curve substrate still needs).
/// When live_tape_max_subs (config.rs:236) binds, the consensus_signals half WINS —
/// our own markets matter more than a sharp's incidental fill.
pub async fn tracked_tape_assets(&self, lookback_hours: i64, arms: &[String])
    -> Result<Vec<(String, i32)>>
{
    sqlx::query_as(
        "SELECT DISTINCT condition_id, outcome_index FROM (
             SELECT condition_id, outcome_index, 0 AS pri FROM consensus_signals
              WHERE first_detected_at > now() - ($1::text || ' hours')::interval
                AND NOT resolved AND strategy = ANY($2) AND condition_id IS NOT NULL
             UNION ALL
             SELECT condition_id, outcome_index, 1 AS pri FROM trader_fills
              WHERE ts > now() - ($1::text || ' hours')::interval
                AND condition_id IS NOT NULL                    -- ← `AND is_sports` DELETED
                AND wallet IN (SELECT lower(proxy_wallet) FROM followed_traders)
         ) u ORDER BY pri")
        .bind(lookback_hours.to_string()).bind(arms)
        .fetch_all(&self.pool).await.context("tracked_tape_assets")
}
```

**Integration points.** `common/src/storage/consensus.rs:1629` — `tracked_tape_assets()` — rewritten. Caller `copy-trading-bot/src/cycles/live_tape.rs` passes the executed-arm list. Bounded by `config.rs:236` `live_tape_max_subs` as today.

**Cost.** $0. More WS subscriptions on an existing connection.

**Consequence.** Note that `entry_ask_fire` (Item 1) sources the at-fire ask from the `/book` endpoint **or** the tape — a tape-sourced capture on weather returns **nothing, silently**, and the column stays NULL. **Item 1 and Item 2 are load-bearing for each other.** ⇒ **`weather_fav` may not leave Rung 0 until this is fixed and ≥2 weeks of tape have accrued.**

**Source:** hybrid — the Diagnostic found the root cause; both designers wrote the same fix; Designer B correctly noted that once the executor reads the book from the SDK at decision time, the tape is a **measurement** dependency, not an **execution** one. That decoupling is kept.

---

### 3. Stop modelling the fee. Measure it. — Current: four fee models disagreeing by 5.5× → Target: one, read off the exchange

**Before.** Verified in the codebase:

| Site | Model | Fee per $ notional @ p=0.85 |
|---|---|---|
| The certification gate / `STRATEGY-HANDOFF` §2 | `0.03·p·(1−p)` | **0.38%** |
| Live docs today, sports/weather `feeRate = 0.05` ⇒ `feeRate×(1−p)` | | **0.75%** |
| `pilot.rs:23` `FEE = 0.02`; `config.rs:506` `FEE_PCT = 0.02` | flat 2% | **2.00%** |
| On-chain `CalculatorHelper.sol` @ 1000 bps (py-clob-client issue #326) | `feeRateBps × min(p,1−p) × C / (p × BPS)` | **≈2.08%** |

**The gate's model may understate the real fee by up to ~5.5×.** On the champion's +5.6% realizable floor that is **~1.7pp — roughly 30% of the entire certified edge, given away by an accounting constant.** And the irony worth stating plainly: **the "conservative 2% buffer" everyone has been apologising for is the closest of the four to the on-chain formula. The "corrected" `0.03·p(1−p)` is the optimistic one. The correction went the wrong way.**

**⇒ This changes what "certified" means.** Every ROI figure in this repo computed with `0.03·p(1−p)` — **including the +8.0% pooled and +5.2% LB headline in `STRATEGY-HANDOFF` §3** — is optimistic by an unquantified amount, and **the gate's pass/fail margin sits inside that error bar.** This is not a retraction (nobody has recomputed it). It **is** a hypothesis-not-a-result under the project's own evidence rule.

**After — three rules, in force from Rung 0.**

1. **Realized P&L charges `fees_paid`, read off the exchange's own trade event.** ✅VERIFIED in the SDK source: `TradeResponse.fee_rate_bps: Decimal` (`src/clob/types/response.rs`) and `TradeMessage.fee_rate_bps: Option<Decimal>` (`src/clob/ws/types/response.rs:379`), plus `trader_side: TraderSide` (`:386`). **Zero modelling. The data is pushed to us.** This is invariant I8 ("no fill model") applied to fees.
2. **Pre-trade EV check** (where an estimate is unavoidable): `client.fee_rate_bps(token_id)` (`src/clob/client.rs:932`), cached per `condition_id`. **Never hardcode a category rate.** CLOB V2 (2026-04-28) *removed `feeRateBps` from the signed order* — fees are set by the protocol at match time and are not modelable by the client at all.
3. **Until real fills exist, the gate uses the CONSERVATIVE bound — `FEE_PCT = 0.02` (or the on-chain formula) — NOT `0.03·p(1−p)`.** Anything else re-runs the exact failure mode this project has now suffered four times.

**THE $1 EXPERIMENT (do it first at Rung 2).** Issue #326 reports the `/fee-rate` endpoint returning **NHL `base_fee: 0`** and **NBA/MLB `base_fee: 1000`** (= 10%), matching *neither* 0.03 nor 0.05, with **no maintainer response on an archived repo.** The band is **0.75% → 2.08% of notional = $7.5 → $20.8/day = a ~$13/day uncertainty on a ~$19–33/day net book.** **Place one $1 order and read `fee_rate_bps` off the trade event.** A $1 experiment that resolves 40–70% of the net. It may be the highest-ROI single action in the entire project.

**Also do now, at $0:** `scripts/fee_schedule_sensitivity.py` already exists. Correct its rate table (sports **0.03 → 0.05**; weather is **0.05**, the *expensive* bucket, not the cheap one) and add a fourth column for the on-chain formula. **Run it before Rung 2 and report the corrected LB to Tue.**

**Integration points.** `copy-trading-bot/src/pilot.rs:23` (`FEE`), `copy-trading-bot/src/config.rs:506` (`FEE_PCT`) — both stay for the *modelled* paper path and are **removed from the executor's realized path**. `common/src/storage/consensus.rs:920` — `append_paper_bet`'s `fee_pct` term. New: `executor_fills.fee_rate_bps` (Item 6).

**Cost.** $0 to fix. **$13/day of standing uncertainty until the $1 experiment runs.**

**Source:** hybrid — the Diagnostic's C2 did the adjudication; both designers converged; the synthesizer verified `fee_rate_bps` and `trader_side` exist on both the REST and WS trade types.

---

### 4. `realizable_pnl()` double-charges a real fill — Current: an unconditional +1¢ inside the P&L function → Target: split modelled from realized

**Before.** `copy-trading-bot/src/pilot.rs:114-117`:
```rust
pub fn realizable_pnl(entry: f64, won: f64, notional: f64) -> f64 {
    let e = (entry + 0.01).min(0.999);        // ← +1¢ haircut, UNCONDITIONALLY
    notional * (won - e) - FEE * notional * e // ← FEE = 0.02, flat
}
```
Correct **for a paper model where `entry` is a proxy price** (the 1¢ stands in for the spread we'd cross). **Wrong the moment `entry` is a real fill price** — a real fill has *already paid* the spread. `PilotLedger::record` (`pilot.rs:261`) feeds `entry` straight in ⇒ the pilot's own ledger **over-charges every real fill by 1¢ + 2%.**

**~1¢ on a 3–7¢-wide edge is 14–33% of the entire edge, charged twice.** It biases the executor's self-measurement **pessimistic**, which would cause it to **demote a healthy arm** — feeding straight into the whipsaw failure mode of Item 8. **A pessimistic bias in a safety system is not "conservative"; it is a false-positive generator.**

**After — split the function, preserve the contract.**
```rust
/// The MODELLED P&L. Byte-identical to today's. `entry` is a PROXY price; the +1¢ stands
/// in for the spread we would have crossed. Test `realizable_pnl_matches_model`
/// (pilot.rs:383) still passes — the 8-test contract is preserved.
pub fn realizable_pnl_modeled(entry_proxy: f64, won: f64, notional: f64) -> f64 { /* verbatim */ }

/// The REALIZED P&L. Charges NOTHING it did not observe. (I8, applied to fees.)
/// `fill_px` is the exchange's fill price; `fees_paid` comes from TradeResponse.fee_rate_bps.
/// There is no haircut, because the fill price IS the haircut, already paid.
pub fn realized_pnl(fill_px: f64, won: f64, shares: f64, fees_paid: f64) -> f64 {
    shares * (won - fill_px) - fees_paid
}
```

**Integration points.** `copy-trading-bot/src/pilot.rs:114` — rename to `realizable_pnl_modeled`, add `realized_pnl`. `pilot.rs:261` — `PilotLedger::record()` — routes to `realized_pnl` when the entry came from an exchange fill (`executor_fills`), to `realizable_pnl_modeled` otherwise. `pilot.rs:383` — `realizable_pnl_matches_model` — unchanged, still green.

**Cost.** $0. Removes a ~1¢ + 2% pessimistic bias from every realized-fill measurement.

**Source:** hybrid — the Diagnostic (GAP-12) found it; both designers wrote the identical fix.

---

### 5. The CLOB write client — Current: zero crypto deps, zero POSTs → Target: the official SDK, in its own crate, behind a **cargo feature that is off by default**

**Before.** `grep -iE '^name = "(alloy|ethers|web3|secp256k1|k256|ecdsa|eip712)' Cargo.lock` → **no matches.** Zero crypto in the entire workspace. Zero POSTs to `clob.polymarket.com`. `DEPLOY.md:3` — *"No wallet, no private key, no funds, nothing at risk."*

**The scope deletion.** The brief asks for a hand-rolled `clob-client` crate: EIP-712 L1 auth, HMAC-SHA256 L2, a signed-order struct, cancel-all, an authed user-WS, approvals, proxy-wallet signature types. **That is ~3,000 lines of drifting crypto against an API that was replaced 11 weeks ago** (CLOB V2 shipped 2026-04-28: contracts rewritten, EIP-712 order domain version bumped to `"2"`, `nonce`/`feeRateBps`/`taker`/`expiration` **removed** from the signed order, `timestamp`/`metadata`/`builder` **added**, collateral changed to **pUSD**, all V1 resting orders wiped at cutover; `py-clob-client` archived 2026-05-25, `rs-clob-client` archived 2026-05-11 — both **non-functional against the live backend**). Hand-rolling this is not a one-time cost; it is a **standing liability that silently rots**, and its failure mode (a stale domain version) is *every order rejected*, discovered in production.

**An official Rust SDK exists.** ✅**VERIFIED BY THE SYNTHESIZER** — I downloaded `https://static.crates.io/crates/polymarket_client_sdk_v2/polymarket_client_sdk_v2-0.6.0.crate` and read the source:

- `Cargo.toml`: `edition = "2024"`, `rust-version = "1.88.0"`, **`reqwest = "0.13.2"`**, **`tokio = "1.50.0"`**, `alloy = "1.6.3"`, `rust_decimal = "1.41.0"`, `tokio-tungstenite = "0.29.0"`, rustls throughout.
- **The workspace pins `reqwest = "0.13.2"` and `tokio = "1.50"` — an EXACT match on both.** `tokio-tungstenite` resolves 0.29 alongside our 0.28 as a duplicate crate; the SDK's WS types never cross our API boundary, so this is a build-size cost, not a type conflict.
- ⇒ **The Diagnostic's "≤1-day blocking dependency spike" is CLOSED, GREEN. Delete it.** Both designers reached this independently; I confirmed it from the tarball.

**After — a new workspace member, gated at COMPILE time.**

```toml
# Cargo.toml (workspace root)
members = ["common", "trading-bot", "copy-trading-bot", "clob-exec"]   # NEW

# copy-trading-bot/Cargo.toml
[features]
default   = []
live-exec = ["dep:clob-exec"]                            # OFF ⇒ alloy is NOT COMPILED
[dependencies]
clob-exec = { path = "../clob-exec", optional = true }   # NEW

# clob-exec/Cargo.toml — NEW crate. The ONLY place a private key can exist.
[dependencies]
polymarket_client_sdk_v2 = { version = "=0.6.0", features = ["clob", "ws"], default-features = false }
alloy        = { version = "1.6", default-features = false, features = ["signer-local", "signers"] }
rust_decimal = "1.41"
async-trait  = "0.1"
tokio        = { workspace = true }
anyhow       = { workspace = true }
tracing      = { workspace = true }
```

**Why a crate and not a module — and this is the answer to "new crate vs module vs separate process".**

`ShadowPlacer` and `PaperPlacer` need **zero crypto**. Rungs 0 and 1 — the state machine, the policy layer, the cage, the cluster governor, the reconciler, the detectors — are **90% of the build**, and none of it needs `alloy`. So:

| | blast radius | latency | deploy surface | build time (autoupdater rebuilds on EVERY merge) |
|---|---|---|---|---|
| Module in `copy-trading-bot` | ✅ (detached spawn) | ✅ 0 IPC | ✅ 1 unit | ❌ `alloy`'s ~469-package tree in every prod build |
| **Crate + cargo feature, same process** ✅ **CHOSEN** | ✅ (detached spawn) | ✅ 0 IPC | ✅ 1 unit | ✅ **`alloy` compiled only when `live-exec` is on** |
| Separate process | ✅ | ❌ IPC + a 2nd DB pool | ❌ **the autoupdater does not know how to deploy it** | ✅ |

**A separate process buys isolation the codebase already has** — see Item 7's detached-spawn slot — **at the cost of a second deploy unit the autoupdater does not know about**, which is a *new* class of failure (a stale executor talking to a fresh schema) traded for an isolation property we get for free. **Rejected.** The crate split gets 100% of the dependency-hygiene benefit at zero operational cost, and it upgrades the repo's own `off ⇒ never spawned ⇒ byte-identical` guarantee to **`off ⇒ not compiled ⇒ byte-identical`, enforced by the linker.**

**The SDK surface we use — every line ✅VERIFIED against the v0.6.0 source:**

| Purpose | Call | file:line | Notes |
|---|---|---|---|
| Auth (L1 EIP-712 → API key → L2 HMAC) | `.authentication_builder(&signer).signature_type(..).funder(..).authenticate()` | `client.rs:165`, `:1534` | **Type-state machine: calling an authed endpoint unauthenticated is a COMPILE ERROR.** |
| Build + sign + post | `client.limit_order()…post_only(b).build()` → `client.sign(&signer, o)` → `client.post_order(signed)` | `order_builder.rs`, `client.rs:1703/1723/1852` | `PostOrderResponse { success, error_msg, order_id, status }` |
| **post-only** | `OrderBuilder::post_only(bool)` | `order_builder.rs:93-96, 326, 334` | ✅ **Rejected unless `order_type ∈ {GTC, GTD}` (`:334`). A post-only order CANNOT cross ⇒ "maker fee = 0" becomes EXCHANGE-ENFORCED, not an arithmetic assumption.** |
| Cancel one / all / by market | `cancel_order(id)` / `cancel_all_orders()` / `cancel_market_orders(cid)` | `client.rs:1941/1980/1992` | ✅ `CancelOrdersResponse { canceled: Vec<String>, not_canceled: HashMap<String,String> }` — **`not_canceled` is the cancel-race signal, handed to us by the API.** |
| Reconcile open orders | `orders(&OrdersRequest{ order_id, market, asset_id })` | `client.rs:1917` | ✅ `OpenOrderResponse { id, status, asset_id, side, original_size, size_matched, price, expiration, order_type, … }` |
| Reconcile fills | `trades(&TradesRequest{ asset_id, after, … })` | `client.rs:2018` | ✅ `TradeResponse { id, taker_order_id, asset_id, size, price, **fee_rate_bps**, status, **trader_side**, maker_orders, transaction_hash, … }` |
| Pushed fills / order events | `subscribe_trades([condition_id])` / `subscribe_orders(..)` | ws `client.rs:508/475` | **Subscribes by `condition_id`, NOT token_id.** |
| Book **with bids and sizes** | `order_book(token_id)` | `client.rs:1058` | ⇒ **`ClobBook` (`common/src/data/models.rs:334-344`, asks-only, price-only, no size) does NOT need extending. It needs BYPASSING.** Keep it for the research daemon; the executor uses the SDK's. **Delete that work item.** |
| Tick size (**never assume**) | `tick_size(token_id)` → `TickSize::{Tenth,Hundredth,HalfCent,QuarterCent,Thousandth,TenThousandth}` | `client.rs:856` | SDK-cached. **The enum includes 0.005, which the docs page does not list. Always fetch.** |
| Neg-risk routing | `neg_risk(token_id)` | `client.rs:896` | **A multi-city heat dome is exactly the neg-risk shape ⇒ the Neg-Risk CTF Exchange, a DIFFERENT contract. Wrong ⇒ every weather order rejected.** |
| Pre-trade fee estimate | `fee_rate_bps(token_id)` | `client.rs:932` | Item 3. |
| Jurisdiction | `check_geoblock()` | `client.rs:1037` | **Read it, report it to Tue, obey it. Do not design around it. Do not build evasion.** |

**Signature type — getting this wrong = 100% rejects.** SDK enum: `SignatureType { Eoa = 0, Proxy = 1, GnosisSafe = 2, Poly1271 = 3 }`. **Decision: `Eoa = 0` with a dedicated funding EOA.** `Proxy`/`GnosisSafe` mean the funds live in a Polymarket-managed proxy created by the *web UI*; signing for them requires the proxy's owner key and the correct proxy address, and a mismatch is a silent reject. `Poly1271` (the new deposit-wallet flow) has semantics neither designer could fully verify. A plain EOA we fund directly is the one path where we control every variable.
**And it is asserted, not assumed:** at startup, before any order, call `client.balance_allowance(AssetType::Collateral, signature_type)` and **assert the returned balance equals the on-chain pUSD balance of our address. If it does not, panic. No order is sent.** A one-line assert that converts a 100%-reject failure mode into a startup crash.

**Collateral & approvals — done ONCE, MANUALLY, not by the bot.** Collateral is **pUSD** (an ERC-20 on Polygon, backed 1:1 by USDC), **not USDC.e**. Required: pUSD `approve()` → CTF Exchange V2 **and** Neg-Risk CTF Exchange V2 (for buys); ConditionalTokens `setApprovalForAll()` → both exchanges (for sells/redeems). **The bot has no code path that writes to chain.** This is the highest-consequence, lowest-frequency action in the system; automating a 4-call one-time setup buys nothing and adds a chain-write surface to a trading daemon. Verified by reading the allowance back through the SDK at startup.

**Rate limits.** `POST /order`: 5,000/10s. `DELETE /cancel-all`: **250/10s**. `/book`: 1,500/10s. We fire ~20 signals/day with ≤2 legs each ⇒ **~40 orders/day. Four orders of magnitude under every limit. Rate limiting needs no design** — with one exception: the panic-button watcher must **fire cancel-all exactly once and latch**, never spin (Item 7).

**Cost.** $0/turn. One WS connection + ~40 REST calls/day. Build-time: `alloy` adds ~90s to the Docker image — **and is kept out of every Rung-0/1 prod build by the cargo feature.**

**Source:** hybrid — Designer A's cargo-feature compile-gate (the strongest idea in that document) + Designer B's SDK-source verification of the call surface. Both are adopted; the synthesizer re-verified every cited line.

---

### 6. The order lifecycle — Current: no order table, no states, no reconcile → Target: single-flight + GTD + exchange-is-truth

**⚠️ THIS IS THE HEART OF THE BUILD, AND IT IS WHERE THE TWO DESIGNS FLATLY CONTRADICT EACH OTHER. I read the SDK source to adjudicate.**

**The visceral failure this prevents.** The autoupdater **recreates the container on every merge to `main`.** A restart lands mid-`POST /order`. The intent row says `SENT`. The exchange has a resting **GTC** bid at 0.86 for $50. Nothing in the current design will ever look for it. That bid sits on the book and fills when the favourite collapses toward 0.86 — **precisely when the bet is going wrong** — and the position is invisible to the ledger, invisible to the kill-switch's equity, and invisible to the drawdown calc. **The kill-switch cannot halt on a loss it cannot see.** That is the single most likely way this system loses money it does not know it lost.

#### The adjudication: **there is NO client-order-id, and `metadata` is NOT echoed back.**

The brief (I2) and Designer A both build idempotency on a `client_order_key` stamped into the signed order's `metadata: bytes32` field, hash-joined against `GET /orders` and `GET /trades` on reconcile. Designer A itself flagged this as unverified and blocking. **I verified it. It does not work.**

```
$ grep -rn 'metadata' src/clob/types/response.rs src/clob/ws/types/response.rs
src/clob/types/response.rs:707:/// Generic wrapper structure that holds inner `data` with metadata designating how to query…
```
**That single hit is a doc-comment on a pagination wrapper.** `metadata` appears in the SDK **only** in the order *builder* (`order_builder.rs:53,100-103,213`), the `sol!` typehash (`types/mod.rs:513`), and the request payload (`types/mod.rs:772,837`). It is present in **`OpenOrderResponse`: no. `TradeResponse`: no. `OrderMessage`: no. `TradeMessage`: no.**

> **⇒ A `client_order_key` UNIQUE column gives idempotency of OUR OWN DB WRITES. It gives NOTHING for reconciling against the exchange, because the exchange has never heard of it. The crash-mid-send boundary CANNOT be resolved by key lookup. The brief's entire idempotency story rests on a field that does not exist.**

Designer B is right, and the primitive B reaches for instead is **better than the one it replaces.**

#### The three invariants that replace the key

**INV-1 — SINGLE-FLIGHT PER TOKEN. Enforced by Postgres, not by code.**
```sql
CREATE UNIQUE INDEX exec_one_live_per_token ON executor_orders (token_id)
    WHERE state IN ('INTENT','SENT','LIVE','CANCEL_REQ');
```
At most one non-terminal order per token, **ever**. Consequences, and they are the whole design:
- **B4 (partial fill → re-quote the remainder → two live orders → double position) becomes a constraint violation.** Structurally impossible, not "unlikely".
- **B2 (crash mid-send) becomes unambiguous WITHOUT a key.** On restart, for the (at most one) `SENT` row on token T, call `orders(&OrdersRequest{ asset_id: T })` (✅`client.rs:1917`, and `OpenOrderResponse.asset_id` exists). **Any open order on T is ours — there cannot be a second one, because we could never have sent one.** Reconcile-by-token is therefore **complete**. The key was never needed; the *uniqueness* was.
- **Fills → orders** still key cleanly: `TradeResponse.taker_order_id` and `TradeResponse.maker_orders[].order_id` (✅both verified) match the `exchange_order_id` we persist at ack. The only gap was the no-ack window, and INV-1 closes it.

**⚠️ Two consequences of INV-1 that Designer B did not state and that MUST be specified:**
1. **The take-fallback leg is a SECOND order on the SAME token.** It therefore cannot be placed until the rest leg is **terminal** (`CANCELLED` / `EXPIRED` / `FILLED`). That sequencing is correct and desirable — it is *exactly* the no-overlap property B4 wants — but it must be written down, because a naive implementation will hit a `23505` and treat it as a retryable error. **It is not. A `23505` on `exec_one_live_per_token` means `SkipConcurrent` and is never retried.**
2. **Two arms can fire on the same token** (e.g. `favorite` and `elite_fresh_fav` both hit Brazil). Under INV-1 only one gets an order. **The precedence rule is explicit and stored:** `exec_policy.arm_priority SMALLINT` — lowest wins; the loser records an `executor_orders` row in state `SKIPPED_CONTENDED` with the winning arm's id, so the shadow A/B still sees the signal and attribution stays honest.

**INV-2 — GTD ALWAYS. NEVER GTC. This is the orphan killer.**
`expiration` is **NOT `Option`** on `OrderIntent`, and **NOT NULL** in the schema, with a `CHECK (order_type IN ('GTD','FAK'))`. Every rest leg is `GTD` with `expiration = decision_ts + t_rest + 60s`. Every take leg is `FAK` (fill-and-kill — it cannot rest at all).

> **An order we forget about cannot rest forever. It expires.**

This is a **one-word design decision that neutralises the catastrophe above without depending on reconcile working at all.** Reconcile is the belt; GTD is the suspenders, and the suspenders hold even if the process never comes back up. (And `post_only` requires GTC/GTD — `order_builder.rs:334` — so GTD is *also* the only TIF compatible with a post-only maker leg. The constraints agree.)

**INV-3 — THE DANGEROUS ORPHAN IS A *POSITION*, NOT AN *ORDER*.**
The brief's I5 says "an unrecognised open order at startup ⇒ cancel it and HALT (loud)." That conflates two things of wildly different severity. An unrecognised **open order** is harmless the instant you cancel it, and `cancel_all_orders()` is one call. An unrecognised **fill** means **we own shares we cannot explain**, and no amount of cancelling fixes it. So the severity is assigned to the fill, not the order.

**⚠️ INV-4 (the synthesizer's addition — NEITHER designer has this, and Designer B's state machine is WRONG without it). A trade can FAIL after it MATCHES.**
✅VERIFIED, `src/clob/types/mod.rs:312`:
```rust
pub enum TradeStatusType { Matched, Mined, Confirmed, Retrying, Failed, /* + untagged unknown */ }
```
A Polymarket trade matches **off-chain**, then mines **on-chain — and it can `RETRYING` or `FAILED`.** Designer B's state machine treats a `TradeMessage` as terminal `Filled`. **That books P&L on a trade that never settled.** Designer A found this and is right. The rule:

> **RISK counts `MATCHED`. The LEDGER books only `CONFIRMED`.**

Asymmetric on purpose: *assume you own it the instant it matches* (so the kill-switch and the cluster budget see the exposure immediately), but *do not claim the P&L until the chain says so*. A `FAILED` **releases the exposure and increments the `RejectStorm` counter** — repeated failures mean something structural (allowance, balance, geoblock) and must **halt**, not retry.

#### The state machine

```rust
// copy-trading-bot/src/exec/state.rs — NEW
#[derive(Debug, Clone, Copy, PartialEq, Eq, sqlx::Type)]
#[sqlx(type_name = "text", rename_all = "UPPERCASE")]
pub enum OrderState {
    Intent,          // committed to DB, NOT sent                                   (B1)
    Sent,            // POST in flight, OR the response was lost. ⚠️ INDETERMINATE.  (B2)
    Live,            // exchange acked; resting. filled_shares may be in (0, size).
                     //   `Partial` is a QUANTITY, not a state — the exchange's own
                     //   OrderStatusType (types/mod.rs:292) is {Live,Matched,Canceled,
                     //   Delayed,Unmatched} and has no Partial. Mirror the exchange;
                     //   never invent a state it cannot confirm.
    CancelReq,       // we ASKED. The exchange has not yet told us the truth.       (B3)
                     //   The size budget is NOT released. No re-quote may be issued.
    Matched,         // TradeStatus::Matched|Mined — off-chain match, NOT settled.  (INV-4)
                     //   RISK COUNTS THIS. THE LEDGER DOES NOT.
    Filled,          // TERMINAL. TradeStatus::Confirmed. ONLY NOW is it booked.
    Failed,          // TERMINAL. TradeStatus::Failed — the match reverted on-chain.
                     //   Exposure released. RejectStorm counter incremented.
    Cancelled,       // TERMINAL — CONFIRMED BY EVENT. Never by the cancel's HTTP 200.
    Expired,         // TERMINAL — GTD elapsed, confirmed by a reconcile read. INV-2's landing.
    Rejected,        // TERMINAL — PostOrderResponse.success == false. Safe: exchange answered.
    Abandoned,       // TERMINAL — reconcile PROVED the exchange never got it.
    SkipContended,   // TERMINAL — INV-1 precedence: another arm owns this token today.
}
```

#### The four boundaries — where they live, exactly

| # | The precise instruction | What goes wrong | The handling |
|---|---|---|---|
| **B1** | after `COMMIT` of the `INTENT` row, **before** `post_order()` | intent exists; exchange knows nothing | **Benign.** Reconcile finds no open order on the token ⇒ `Abandoned`. Safe to retry with the same `attempt_seq`. |
| **B2** | **inside** `post_order()` — response lost (timeout / TCP reset / container SIGKILL / 5xx) | ⚠️ **THE ORDER MAY EXIST AND WE DO NOT KNOW.** The duplicate-position generator. | **NEVER retry blind.** `PlaceError::Indeterminate` ⇒ state stays `SENT`; hand to reconcile. Reconcile queries `orders(asset_id=T)` **and** `trades(asset_id=T, after=intent_ts)`. Found ⇒ **adopt** (`Live`/`Matched`). **Absent from BOTH, on two SUCCESSFUL reads ≥120s apart** ⇒ `Abandoned`. **If either read ERRORS ⇒ HALT the arm (`ReconcileFailed`). We NEVER infer absence from a failure.** *(The 120s two-read grace is Designer A's, and it is load-bearing: the SDK has `OrderStatusType::Delayed` — a POST can land and not yet be visible in `GET /orders`. A single empty read would produce a duplicate.)* |
| **B3** | after `cancel()` returns 200, **before** the `CANCELLATION` event — and a fill lands in between | we believe we cancelled; **we own shares** | **A cancel is a REQUEST, not a fact.** State → `CancelReq`. Budget **NOT** released. The API hands us the race directly: `CancelOrdersResponse.not_canceled: HashMap<order_id, reason>` (✅verified) ⇒ *almost certainly already matched*. **In neither case do we set `Cancelled`.** State advances only on a WS `OrderMessage{Cancellation}`, a `TradeMessage`, or a reconcile read. |
| **B4** | partial fill, then re-quote the remainder | **two live orders, double position** | **A constraint violation.** `exec_one_live_per_token` (INV-1) makes it impossible. The old order must be terminal *by event* before a new `attempt_seq` may be inserted. |

#### The write-ahead protocol (I1 + I2), as actual code

```rust
// copy-trading-bot/src/exec/machine.rs — NEW.
// This function is the single most dangerous ~40 lines in the system.
async fn send_one(pool: &PgPool, gate: &OrderGate<'_>, i: &OrderIntent) -> Result<()> {
    // ── I1: WRITE-AHEAD. Committed BEFORE the network call. If we crash on the next
    //    line, the INTENT row is our proof that an order MIGHT exist.
    //    Two independent locks here:
    //      · ON CONFLICT (client_order_key) DO NOTHING  — a crashed retry cannot double-INSERT
    //      · exec_one_live_per_token (INV-1)            — a second live order on this token
    //                                                     is a 23505, which is NOT retryable
    let r = sqlx::query(
        "INSERT INTO executor_orders
           (client_order_key, signal_id, leg, attempt_seq, arm, policy_version, mode, state,
            token_id, condition_id, neg_risk, side, order_type, post_only, limit_price,
            size_shares, expiration, decision_ask, decision_bid, decision_mid, decision_ts)
         VALUES ($1,$2,$3,$4,$5,$6,$7,'INTENT',$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
         ON CONFLICT (client_order_key) DO NOTHING")
        .bind(&i.client_order_key) /* … */ .execute(pool).await;

    match r {
        Err(e) if is_unique_violation(&e, "exec_one_live_per_token") => {
            // INV-1. Another order (or another ARM — see arm_priority) owns this token.
            // NOT AN ERROR. NOT A RETRY. Record the abstention honestly and move on.
            record_skip(pool, i, OrderState::SkipContended).await?;
            metrics::counter!("executor_skip_contended").increment(1);
            return Ok(());
        }
        Err(e) => return Err(e.into()),
        Ok(res) if res.rows_affected() == 0 => {
            // The client_order_key already exists ⇒ this is a RETRY of something we already
            // tried. We do NOT re-send. Reconcile owns it now and will tell us the truth. (I2)
            metrics::counter!("executor_duplicate_key_blocked").increment(1);
            reconcile_now.notify_one();
            return Ok(());
        }
        Ok(_) => {}
    }

    // ── B1 → B2. Everything between here and the next COMMIT is the danger zone.
    sqlx::query("UPDATE executor_orders SET state='SENT', sent_ts=NOW() WHERE client_order_key=$1")
        .bind(&i.client_order_key).execute(pool).await?;

    match gate.place(i).await {                       // ← pilot.rs:244, THE HOLE, FILLED
        Ok(ack) => {
            sqlx::query("UPDATE executor_orders SET exchange_order_id=$2, ack_ts=NOW()
                         WHERE client_order_key=$1 AND state='SENT'")
                .bind(&i.client_order_key).bind(&ack.exchange_order_id).execute(pool).await?;
            // NOTE: state STAYS 'SENT'. It advances to 'LIVE' ONLY on the WS
            // OrderMessage::Placement, or on a reconcile read. The HTTP 200 is a HINT,
            // NOT A FACT. This one rule kills B2 and B3 simultaneously.
        }
        Err(PlaceError::Rejected(r)) => {             // SAFE: the exchange answered "no"
            terminal(pool, &i.client_order_key, OrderState::Rejected, Some(&r)).await?;
            reject_storm.record();                   // → HaltReason::RejectStorm
        }
        Err(PlaceError::Indeterminate(e)) => {       // ⚠️ B2. DO NOT RETRY. DO NOT GUESS.
            tracing::error!(err=%e, key=%i.client_order_key, "INDETERMINATE SEND — reconciling");
            reconcile_now.notify_one();              // state stays SENT; reconcile owns it.
            // If reconcile cannot resolve it within RECONCILE_MAX_UNRESOLVED_SECS (=300),
            // the ARM HALTS (ReconcileFailed). An unresolved SENT is an unbounded position.
        }
        Err(PlaceError::Precondition(e)) => {        // never left the process
            terminal(pool, &i.client_order_key, OrderState::Abandoned, Some(&e)).await?;
        }
    }
    Ok(())
}
```

**`PlaceError::Indeterminate` is the load-bearing variant** and the reason `anyhow` is not good enough here. Mapping from the SDK's `error::Kind`:
- `Kind::Status{4xx}` → `Rejected` (safe — the exchange answered).
- `Kind::Status{5xx}` → **`Indeterminate`** (it may have accepted before failing).
- `Kind::Internal` (reqwest timeout / connection reset) → **`Indeterminate`**.
- `Kind::Validation` → `Precondition` (never sent).
- `Kind::Geoblock` → **halt master, alert Tue, never retry.** This is the ToS gate firing as a runtime error.

#### Reconcile (I5) — runs on every startup **before a single order may be sent**, then every 60s

```rust
// copy-trading-bot/src/exec/reconcile.rs — NEW
async fn reconcile_or_halt(pool: &PgPool, p: &dyn Placer, ks: &ArmGate) -> Result<()> {
    // 1. Cancel everything, unconditionally. Safe by INV-1 + INV-2: we never WANT to keep a
    //    resting order across a restart — the signal is re-derivable, the TTL is short, and a
    //    stale rest is an adversely-selected rest. If cancel_all FAILS ⇒ HALT (we are blind).
    p.cancel_all().await.map_err(|e| halt_master(HaltReason::ReconcileFailed, e))?;

    // 2. LOCAL → TRUTH. Every non-terminal row. Scoped by TOKEN (INV-1 makes this complete).
    for row in load_nonterminal(pool).await? {           // the partial index serves this scan
        let open   = p.open_orders(row.token_id).await
                      .map_err(|e| halt_arm(&row.arm, HaltReason::ReconcileFailed, e))?;
        let trades = p.fills_since(row.token_id, row.intent_ts).await
                      .map_err(|e| halt_arm(&row.arm, HaltReason::ReconcileFailed, e))?;
        //  ↑ NOTE THE DELIBERATE ASYMMETRY: a read that ERRORS propagates and HALTS.
        //    We only ever conclude "the order does not exist" from a SUCCESSFUL read that
        //    came back EMPTY, TWICE, ≥120s apart. We NEVER infer absence from a failure.

        match (open.first(), trades.is_empty()) {
            (_, false)      => adopt_trades(pool, &row, &trades).await?,  // it traded → Matched/Filled/Failed
            (Some(o), true) => adopt_open(pool, &row, o).await?,          // resting → Live (+ size_matched)
            (None, true)    => {
                if row.state == OrderState::Sent
                   && row.empty_reads < 2
                   && row.age() < Duration::seconds(120) {
                    bump_empty_read(pool, &row).await?;   // ← the Delayed-status grace. DO NOTHING YET.
                } else if row.past_expiration() {
                    terminal(pool, &row.key, OrderState::Expired, None).await?;   // INV-2 landed
                } else {
                    terminal(pool, &row.key, OrderState::Abandoned,
                             Some("reconcile: absent on two reads ≥120s apart")).await?;
                }
            }
        }
    }

    // 3. TRUTH → LOCAL. ⚠️ THE LOUD ONE (INV-3). A FILL we have no row for.
    for token in tokens_touched_since(pool, Utc::now() - Duration::hours(72)).await? {
        for t in p.fills_since(token, since).await
                  .map_err(|e| halt_master(HaltReason::ReconcileFailed, e))? {
            if executor_order_for_trade(pool, &t).await?.is_none() {
                //  WE OWN SHARES WE CANNOT EXPLAIN. Either a second bot instance is running,
                //  or our key scheme is broken. Both are unbounded-loss scenarios.
                ks.halt("__master__", HaltReason::OrphanPosition, "auto:reconcile").await?;
                ntfy.push("🛑 ORPHAN POSITION — MASTER HALTED", &t.id, 5, &["rotating_light"]).await;
                bail!("orphan position {} — executor refuses to start", t.id);
            }
        }
    }
    Ok(())
}
```

#### The tables (migration **043**)

```sql
-- 043_executor_orders.sql
CREATE TABLE executor_orders (
    id                BIGSERIAL PRIMARY KEY,
    client_order_key  TEXT NOT NULL UNIQUE,   -- sha256(signal_id‖policy_version‖leg‖attempt_seq).
                                              -- OUR key. NOT an exchange key — the exchange has
                                              -- none, and `metadata` is NOT echoed back (VERIFIED).
                                              -- It prevents a crashed retry from double-INSERTing.
                                              -- Nothing more. Do not build recovery logic on it.
    signal_id         BIGINT  NOT NULL REFERENCES consensus_signals(id),
    leg               TEXT    NOT NULL,       -- 'rest' | 'take' — the two legs of ONE quote
    attempt_seq       INTEGER NOT NULL,
    arm               TEXT    NOT NULL,
    policy_version    INTEGER NOT NULL,       -- I9: the EXACT config that produced this order
    mode              TEXT    NOT NULL,       -- 'shadow'|'paper'|'live'. I10 audit: a 'live' row
                                              -- in a paper rung is a P0 alarm, queryable in one line.
    state             TEXT    NOT NULL,
    token_id          TEXT    NOT NULL,
    condition_id      TEXT    NOT NULL,       -- the user-WS subscribes by condition_id, not token
    neg_risk          BOOLEAN NOT NULL,       -- wrong ⇒ wrong exchange contract ⇒ reject
    side              TEXT    NOT NULL,
    order_type        TEXT    NOT NULL,       -- 'GTD' | 'FAK'.  A 'GTC' row is a bug (INV-2).
    post_only         BOOLEAN NOT NULL,       -- proof we could not have paid a taker fee
    limit_price       NUMERIC(10,6) NOT NULL, -- tick-aligned
    size_shares       NUMERIC(18,6) NOT NULL, -- SHARES (flat-shares sizing), never flat-$
    expiration        TIMESTAMPTZ NOT NULL,   -- NOT NULL. INV-2 enforced by the SCHEMA.
    empty_reads       SMALLINT NOT NULL DEFAULT 0,  -- the B2 two-read grace counter

    -- the decision snapshot (I3, I9) = the counterfactual basis
    decision_ask      DOUBLE PRECISION NOT NULL,
    decision_bid      DOUBLE PRECISION NOT NULL,
    decision_mid      DOUBLE PRECISION NOT NULL,  -- TRUE book mid. NEVER the vote-mean (D2).
    decision_ts       TIMESTAMPTZ NOT NULL,

    intent_ts         TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- committed BEFORE the POST (I1)
    sent_ts           TIMESTAMPTZ,
    ack_ts            TIMESTAMPTZ,
    matched_ts        TIMESTAMPTZ,            -- off-chain match (INV-4). Risk counts from here.
    terminal_ts       TIMESTAMPTZ,            -- on-chain CONFIRMED / CANCELLED / EXPIRED / REJECTED
    exchange_order_id TEXT,

    -- REALIZED TRUTH — written ONLY from an exchange event (I8). Never modelled. Never inferred.
    filled_shares     NUMERIC(18,6) NOT NULL DEFAULT 0,
    avg_fill_price    DOUBLE PRECISION,
    fees_paid         DOUBLE PRECISION,       -- from TradeResponse.fee_rate_bps. MEASURED. (Item 3)
    trader_side       TEXT,                   -- 'maker'|'taker' — PROVES post_only worked
    reject_reason     TEXT,
    UNIQUE (signal_id, leg, attempt_seq)
);

-- INV-1. THE load-bearing line of the entire build.
CREATE UNIQUE INDEX exec_one_live_per_token ON executor_orders (token_id)
    WHERE state IN ('INTENT','SENT','LIVE','CANCEL_REQ');
-- INV-2, enforced by the schema.
ALTER TABLE executor_orders ADD CONSTRAINT no_gtc CHECK (order_type IN ('GTD','FAK'));
-- The reconcile scan: O(open orders), not O(all history).
CREATE INDEX exec_open ON executor_orders (state)
    WHERE state IN ('INTENT','SENT','LIVE','CANCEL_REQ','MATCHED');
CREATE INDEX exec_learn ON executor_orders (arm, policy_version, terminal_ts);

-- Every exchange event, appended, never updated. The audit trail AND the learning-loop source.
CREATE TABLE executor_fills (
    id                BIGSERIAL PRIMARY KEY,
    client_order_key  TEXT NOT NULL,
    exchange_trade_id TEXT NOT NULL,
    status            TEXT NOT NULL,          -- MATCHED|MINED|CONFIRMED|RETRYING|FAILED (INV-4)
    fill_price        NUMERIC(10,6) NOT NULL,
    fill_shares       NUMERIC(18,6) NOT NULL,
    fee_rate_bps      NUMERIC(10,4),          -- ⚠️ THE ONLY FEE NUMBER WE WILL EVER TRUST
    trader_side       TEXT,                   -- Maker|Taker — PROVES post_only worked
    transaction_hash  TEXT,
    event_ts          TIMESTAMPTZ NOT NULL,
    recv_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- OUR clock. Order by this, never event_ts.
    UNIQUE (exchange_trade_id, status)        -- idempotent under WS replay
);

-- Item 2 / capture-defect note. NEVER edit applied migration 040 (sqlx checksum ⇒ crash-loop).
COMMENT ON COLUMN clob_price_tape.last_size IS
  'ORDER-BOOK-LEVEL CHURN on a price_change — NOT executed trade volume. Migration 040''s comment
   ("trade size in SHARES") is WRONG. Do not use in any fill decision. See D31 and live_tape.rs:~224.';

-- The signal becomes a TRADEABLE OBJECT. Resolved at fire, from the ALREADY-PREFETCHED ClobMarket.
ALTER TABLE consensus_signals
  ADD COLUMN token_id  TEXT,
  ADD COLUMN neg_risk  BOOLEAN,
  ADD COLUMN tick_size NUMERIC(6,4);
```

`UNIQUE (exchange_trade_id, status)` is the WS-replay idempotency: a reconnect that re-delivers `MATCHED → MINED → CONFIRMED` inserts each status exactly once, and **the order state is a pure fold over the appended events.**

**The `token_id` hot-path problem — solved by moving it, not by making it faster.** The Diagnostic flags `condition_id + outcome_index → token_id` as "an unbudgeted network hop inside the decision path" on a ≲30s hot lane. **It is not in the decision path.** `consensus_cycle.rs:475-487` **already prefetches `ClobMarket` for every signal** (`prefetch_markets(...)` → `markets: HashMap<String, MarketContext>`), and `ClobMarket::outcome_token_id()` (`common/src/data/models.rs:321`) is a **pure function on data already in memory at the hook.** ⇒ write `token_id` in the same upsert. **Zero new network calls. A signal with no token_id is SKIPPED, never guessed (fail-closed).**

**Integration points.**
- `copy-trading-bot/src/pilot.rs:244` — `OrderGate::place()` — `Err(NoPlacer)` becomes `match self.placer { None => Err(NoPlacer), Some(p) => p.place(i).await }`. **`PilotError::NoPlacer` survives, and so does the test that proves it** (see § Invariants).
- `copy-trading-bot/src/cycles/consensus_cycle.rs:519` — after `portfolio.upsert_consensus_signal(&new)` returns `state.id` — **one new line:** `let _ = exec_tx.try_send(state.id);` A **non-blocking** send on a **bounded (cap 256)** `tokio::mpsc`. A full channel **drops the signal and increments `executor_signal_dropped_total`.** It cannot block, cannot panic, and cannot slow the research cycle by one microsecond. **Missing a trade is cheap; a wedged research cycle is not.** The same hook covers **both lanes** — `hot_lane.rs` calls the same `upsert_consensus_signal`.
- `common/src/storage/consensus.rs:29-53` — `NewConsensusSignal` — gains `token_id`, `neg_risk`, `tick_size`.
- `common/src/data/models.rs:334-344` — `ClobBook` — **unchanged. Bypassed, not extended.** The executor uses the SDK's `order_book()`.

**Cost.** $0/turn. One indexed query + ≤N SDK calls per restart. **The value is the loss it prevents:** at $50/signal, one orphan per 100 deploys is ~$50 of invisible, unbounded-in-time exposure — and, far worse, it corrupts the *measurement* the entire build exists to produce.

**Source:** **refined.** Designer B's single-flight + GTD is correct and is the strongest idea in either document — and it is *forced*, because Designer A's `metadata` key does not exist (I verified). Designer A's two-phase settlement (INV-4) is correct and Designer B's state machine is **wrong without it** — it would book P&L on a reverted trade. Designer A's 120s two-read grace and "never infer absence from a failure" are correct and Designer B lacks them (its single empty read would produce a duplicate against `OrderStatusType::Delayed`). The `SkipContended` precedence rule and the `23505`-is-not-retryable rule are the synthesizer's — **both designers left a `23505` from INV-1 undefined, and the naive handling of it is a retry loop against a real-money exchange.**

---

### 7. The cage: a per-arm kill-switch that survives a deploy, and a kill path that works from a wedged loop

**Before — three failures, all read from the code.**

1. **The latch does not survive a restart.** `pilot.rs:132` `KillSwitch::new()` sets `equity = cfg.bankroll`, `peak = equity`, `halted = None`, then calls `evaluate()`. A `MaxDrawdown` halt at −15% is **erased** by a container recreate: equity resets to the full bankroll, peak resets, drawdown recomputes as 0%, and the switch **un-halts itself.** `reset()` (`pilot.rs:195`) is documented as "the ONLY un-halt" — **but `docker restart` is a second, undocumented, automatic one.**
   **And the autoupdater recreates the container on every merge to `main`.** ⇒ **A max-drawdown halt at 08:00, an autoupdater rebuild at 08:05, and the bot is trading again at 08:06 with a clean slate and a real −15% hole in the account. Nobody is notified.**
   **⇒ These two hazards COMPOUND: merging the executor is the very event that erases the executor's halt state. GAP-4's persistence MUST ship in the SAME PR that wires the executor. Not the next one. The same one.** This is non-negotiable and both designers said so independently.
2. **`halted: Option<HaltReason>` is a single scalar.** There is **no arm dimension anywhere in the type**. Tue's §4b requirement ("one arm's halt must not silently halt the others") is **not expressible**.
3. `KillSwitch::new()` calls `evaluate()`, which latches `MasterOff` immediately when `master_on == false` (test `master_off_halts_by_default`, `pilot.rs:364`). **A naive persistence fix — "load state, then `new()` and restore the fields" — re-latches `MasterOff` on top of the restored reason, silently rewriting the halt cause in the audit log.**

**After — persist the DECISION, replay the MEASUREMENT.**

Designer A persists the whole struct (equity, peak, day_pnl, day, lambda) and then spends a paragraph warning about failure 3. **Designer B is right that failure 3 exists only because the design persists a cache.** `equity`, `peak`, `day_pnl`, `day` are **pure functions of the realized-fill ledger.** They are *measurements*, not *decisions*. Persisting them creates a second source of truth that can drift from the first — **which is the exact class of bug this project keeps having.**

> **Persist exactly one thing: the latch. Replay everything else through the existing, tested `on_fill()`.**
> There is then no restore path to get wrong, because **there is no restore.**

```sql
-- 043_executor_orders.sql (same migration as Item 6 — same PR, non-negotiable)
CREATE TABLE executor_halts (
    id         BIGSERIAL PRIMARY KEY,
    arm        TEXT NOT NULL,            -- '__master__' is the global row; MasterOff halts ALL
    reason     TEXT NOT NULL,            -- HaltReason
    detail     JSONB,                    -- the EVIDENCE: {equity, peak, dd, ewma_z, trade_id, …}
    halted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    halted_by  TEXT NOT NULL,            -- 'auto:MaxDrawdown' | 'auto:CUSUM' | 'human:tue'
    cleared_at TIMESTAMPTZ,              -- NULL ⇒ STILL LATCHED
    cleared_by TEXT                      -- HUMAN ONLY. There is no automatic un-halt.
);
-- THE LATCH, ATOMIC, IN THE DATABASE. Two concurrent halt causes race; the FIRST wins; the
-- audit log records the FIRST reason, not the last one to overwrite it.
CREATE UNIQUE INDEX one_open_halt_per_arm ON executor_halts (arm) WHERE cleared_at IS NULL;

-- HALTED FROM BIRTH. The seed IS the safety property, and it lives in the MIGRATION, not in code.
INSERT INTO executor_halts (arm, reason, halted_by)
VALUES ('__master__', 'MasterOff', 'seed:migration');
```

**One table. One fact. And the I6 audit log for free** — Designer A's design needs a *second* table (`executor_kill_log`) to get what this gets from `cleared_at`.

```rust
// copy-trading-bot/src/exec/gate.rs — NEW. WRAPS pilot.rs's KillSwitch; does not replace it.
// The existing KillSwitch is RIGHT about everything except WHERE IT LIVES: latching semantics,
// four correct reasons, halted-from-birth, and 6 of the 8 tests are all correct and reusable.

pub struct ArmGate {
    per_arm: HashMap<String, KillSwitch>,   // pilot.rs:114, UNCHANGED
    pool: PgPool,
    placer: Arc<dyn Placer>,
    /// The wedged-loop fast path (I7). Read Relaxed on every hot-path decision; set by the
    /// kill watch, which shares NO lock with the executor loop.
    master_halted: Arc<AtomicBool>,
}

impl ArmGate {
    /// REPLAY, not restore. Rebuilds equity/peak/day_pnl by feeding the arm's realized fills
    /// through THE SAME `on_fill()` the live path uses ⇒ the reconstruction CANNOT drift from
    /// the runtime, because it IS the runtime. This is why there is no restore trap to fall into.
    pub async fn rehydrate(pool: &PgPool, cfg: &PilotConfig, placer: Arc<dyn Placer>) -> Result<Self> {
        let mut per_arm = HashMap::new();
        for arm in executor_arms(pool).await? {
            let mut ks = KillSwitch::new(PilotConfig { master_on: cfg.master_on, ..cfg.clone() });
            for f in realized_fills_for_arm(pool, &arm).await? {   // ORDER BY resolved_at
                ks.on_fill(f.pnl, &f.utc_day);                     // pilot.rs:165 — UNCHANGED
            }
            per_arm.insert(arm, ks);
        }
        let master = open_halt(pool, "__master__").await?.is_some();
        Ok(Self { per_arm, pool: pool.clone(), placer,
                  master_halted: Arc::new(AtomicBool::new(master)) })
    }

    /// halted(arm) := the arm's OPEN HALT ROW  OR  the master's  OR  the in-memory latch.
    /// The DB row is AUTHORITATIVE for the reason; the in-memory latch is a safety
    /// OVER-approximation. An arm halt halts ONE arm; MasterOff halts everything. (Tue §4b.)
    pub async fn halted(&self, arm: &str) -> Option<HaltReason> {
        if self.master_halted.load(Ordering::Relaxed) { return Some(HaltReason::MasterOff); }
        if let Some(r) = open_halt(&self.pool, arm).await.ok().flatten() { return Some(r); }
        self.per_arm.get(arm).and_then(|ks| ks.halted())
    }

    /// DB FIRST, then memory, then cancel. If we die between the DB write and the cancel, the
    /// restart reloads a HALTED state and reconcile cancels the orders anyway. The ordering
    /// makes a crash mid-halt FAIL SAFE.
    pub async fn halt(&self, arm: &str, r: HaltReason, actor: &str, evidence: serde_json::Value)
        -> Result<()>
    {
        sqlx::query("INSERT INTO executor_halts (arm, reason, detail, halted_by)
                     VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING")   // ← the unique partial idx latches
            .bind(arm).bind(r.as_str()).bind(evidence).bind(actor)
            .execute(&self.pool).await?;
        if arm == "__master__" { self.master_halted.store(true, Ordering::SeqCst); }
        self.placer.cancel_all().await?;                              // ← THEN cancel
        ntfy_urgent(&format!("🛑 HALT {arm}: {r:?} ({actor})")).await; // ← THEN tell Tue
        Ok(())
    }
    // ⚠️ THERE IS NO `unhalt()` METHOD ON THIS TYPE. Un-halting is:
    //      UPDATE executor_halts SET cleared_at = NOW(), cleared_by = 'human:tue'
    //       WHERE arm = $1 AND cleared_at IS NULL;
    //    …run BY A HUMAN, from psql or the ops page, and permanently audit-logged.
    //    A restart is not an un-halt. THE ABSENCE OF THE METHOD IS THE DESIGN.
}

pub enum HaltReason {
    // EXISTING — the 8 tests at pilot.rs:289-396 depend on these four. DO NOT TOUCH.
    DayStopLoss, MaxDrawdown, EdgeDegraded, MasterOff,
    // NEW (brief §I6)
    DataStale,        // tape / ingestion heartbeat dead ⇒ DO NOT TRADE BLIND
    RejectStorm,      // N rejects, or N TradeStatus::Failed, in a window (INV-4)
    SlippageBreach,   // EWMA slippage over budget (Item 9)
    SpendBudget,      // daily notional or cluster budget exhausted
    SlateStop,        // −5 units
    ReconcileFailed,  // we could not READ the exchange ⇒ we are blind ⇒ stop
    OrphanPosition,   // ← THE LOUDEST. We own shares we cannot explain. (INV-3) Master-halts.
}
```

**⚠️ The synthesizer's correction to the replay — neither designer caught this.** Replay computes equity from **resolved** fills, and resolution lags entry by hours to days. **A drawdown on OPEN, unresolved exposure is invisible to a replay.** The fix is not to mark-to-market (that reintroduces a model). It is to split the two concerns cleanly:
- **The max-DD / day-stop latch operates on REALIZED equity only** (B's replay). It is honest, driftless, and lagging — and that lag is acceptable *because* of the second half:
- **Open exposure is bounded separately and hard**, by the per-signal cap ($50), the per-cluster budget (Item 10), and `daily_notional_cap_usd`. **The worst case is bounded ex ante by construction, not detected ex post by a drawdown calc.**
That is the correct division of labour, and it is why Item 10 is a *safety* control, not just a sizing one.

**I7 — the kill path that works from a wedged loop. Made STRUCTURAL, not aspirational.**

The executor is **three** detached tasks, not one (Designer B's refinement, and it is the right one):

```rust
// copy-trading-bot/src/live.rs — NEW, inserted at :508, immediately after the hot_lane block
// closes at :507 and immediately before `// Consensus detection loop.` at :509.
//
// ⚠️ NOT IN THE `select!` AT :552. That select! joins exactly five handles (command_loop,
//    copy_trade_loop, housekeeping_loop, tracker_loop, consensus_loop) and the FIRST TO EXIT
//    KILLS THE PROCESS. But dense_capture (:225), live_tape (:252), live_fills (:271) and
//    hot_lane (:475-507) are BARE tokio::spawn, NEVER JOINED — a panic in them is dropped,
//    not fatal. THE EXECUTOR BELONGS IN THAT SAME DETACHED SLOT. Verified by reading the file.
//
// off ⇒ never spawned ⇒ byte-identical (live.rs:225/252/475 pattern).
if cfg.executor_enabled {
    // (a) the decision / quote loop
    tokio::spawn(async move { exec::run_executor(ex_pool, ex_placer, ex_cfg, ex_rx).await });
    // (b) the fill listener — WS → DB. INDEPENDENT, so a wedged (a) cannot lose a fill.
    tokio::spawn(async move { exec::run_fill_listener(fl_pool, fl_placer).await });
    // (c) the KILL WATCH. Shares NO lock, NO channel, and NO state with (a) or (b). It holds
    //     its OWN Placer handle and its OWN dedicated DB connection.
    //     ⇒ "the kill path works even when the main loop is wedged" is a STRUCTURAL PROPERTY,
    //        not a tested hope.
    tokio::spawn(async move { exec::run_kill_watch(kw_conn, kw_placer, kw_halted).await });
}
```

```rust
// copy-trading-bot/src/exec/kill_watch.rs — NEW
pub async fn run_kill_watch(mut conn: PgConnection, placer: Arc<dyn Placer>,
                            halted: Arc<AtomicBool>, ntfy: Option<Ntfy>) {
    loop {
        tokio::time::sleep(Duration::from_secs(2)).await;

        // Trip 1: a FILESYSTEM SENTINEL. Works when POSTGRES IS DOWN. `touch /data/KILL`.
        let file_kill = tokio::fs::try_exists("/data/KILL").await.unwrap_or(false);

        // Trip 2: the DB row (so `psql -c "INSERT INTO executor_halts …"` works remotely).
        let db_kill: Option<String> = sqlx::query_scalar(
            "SELECT reason FROM executor_halts WHERE arm='__master__' AND cleared_at IS NULL")
            .fetch_optional(&mut conn).await
            .unwrap_or(Some("DataStale".into()));   // ← FAIL-CLOSED. If we cannot READ our own
            //                                          kill-switch, WE ASSUME WE ARE HALTED.
            //                                          A bot that cannot check its kill-switch
            //                                          must not be trading.

        if file_kill || db_kill.is_some() {
            if !halted.swap(true, Ordering::SeqCst) {   // FIRE EXACTLY ONCE AND LATCH.
                //                                         (cancel-all is rate-limited 250/10s —
                //                                          a spinning watcher would 429 itself.)
                match placer.cancel_all().await {
                    Ok(n)  => ntfy.push("🛑 HALTED", &format!("{n} orders cancelled"), 5, &["rotating_light"]).await,
                    Err(e) => ntfy.push("🛑🛑 HALT — CANCEL-ALL FAILED", &e.to_string(), 5, &["sos"]).await,
                    //        ^^^ HALTED, BUT WITH LIVE ORDERS. The worst state in the system.
                    //            It MUST page a human. It must not be a log line.
                }
            }
        }
    }
}
```

**Integration points.** `copy-trading-bot/src/pilot.rs:114` (`KillSwitch`) — **kept verbatim** as the pure state machine. `pilot.rs:132` (`new`), `:165` (`on_fill`), `:178` (`evaluate`, latching), `:195` (`reset`) — **all unchanged; 6 of the 8 tests pass untouched.** `copy-trading-bot/src/live.rs:508` — the three spawns. `copy-trading-bot/src/config.rs` — `executor_enabled: bool` (default `false`), `executor_mode: String` (default `"shadow"`).

**Cost.** $0 trading cost. `halted()` is one indexed query, ~40×/day. Replay is ~60 rows through a pure function at startup. **The 2-second poll means the maximum additional exposure after a kill request is ONE order — a bounded, quantified worst case.** (A `LISTEN/NOTIFY` push would be faster but dies with the connection, and the entire point is a path that survives a wedged process.)

**Source:** **hybrid.** Designer B's persist-the-decision/replay-the-measurement + `executor_halts` with `one_open_halt_per_arm` as the atomic latch (strictly better than A's 10-column cache + second log table). Designer B's three-detached-tasks (makes I7 structural). Designer A's file sentinel, fail-closed DB read, fire-once-and-latch, and the "cancel-all failed ⇒ page a human" escalation. The open-exposure/realized-equity split is the synthesizer's — **both designers' replay/restore designs are blind to unresolved exposure.**

---

### 8. The per-arm policy layer — Current: four process-global `const`s → Target: one continuous policy family, as versioned data

**Before.** `config.rs:519` `FLAT_STAKE = 100.0`; `:515` `EXEC_HAIRCUT = 0.01`; `:506` `FEE_PCT = 0.02`; `:501` `SLIPPAGE_PCT = 0.01`. All `confique` env vars: **one value, all arms, changeable only by a container recreate — which is also a kill-switch reset.** And `feat/exec-policy` hardcodes its own menu (`EXEC_PATIENT_DELAY_SECS: i64 = 15*60`, `EXEC_MAKER_CANCEL_SECS: i64 = 30*60`).

**The menu is deleted.** Both designers independently reached the same conclusion and it is correct: the brief's five "policies" (`take_at_fire` / `patient_take(delay)` / `maker_rest(δ,T)` / `capped_chase(δ_max,step,T)` / `skip`) are **four points in one 3-parameter space**, and naming them separately is what creates the illusion that the arms need *different code*. **They do not. They need different numbers.**

```
Quote(t_rest, δ_rest, take_fallback)
    t_rest = 0,    δ_rest = NULL, take_fallback = true   →  "take_at_fire"
    t_rest = 900,  δ_rest = NULL, take_fallback = true   →  "patient_take(15m)"
    t_rest = 1800, δ_rest = 0¢,   take_fallback = false  →  "maker_rest(mid, 30m)"
    t_rest = 300,  δ_rest = +1¢,  take_fallback = true   →  "capped_chase(1¢, 5m)"
    size  = 0                                            →  "skip"
```
**One state machine. One set of I1–I10 tests. Three rows in a table.** The learning loop walks a gradient instead of enumerating a set.

**After (migration 044).**

```sql
CREATE TABLE exec_policy (
    arm             TEXT    NOT NULL,
    version         INTEGER NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT FALSE,
    rung            SMALLINT NOT NULL DEFAULT 0,   -- 0..4, PER-ARM (Tue §4b). weather can sit at
                                                   -- Rung 0 while favorite is at Rung 1.
    arm_priority    SMALLINT NOT NULL,             -- INV-1 contention: LOWEST WINS. (Item 6.)

    -- THE QUOTE (one family, three numbers)
    t_rest_secs        INTEGER NOT NULL,           -- 0 ⇒ pure taker
    delta_rest_cents   NUMERIC(6,4),               -- rest limit = decision_mid + δ. NULL ⇒ no rest leg.
    take_fallback      BOOLEAN NOT NULL,           -- false ⇒ pure maker (abstain if unfilled)
    take_limit_cents   NUMERIC(6,4) NOT NULL,      -- take limit = ask_at_T + this (0 = at the ask)
    post_only          BOOLEAN NOT NULL,           -- TRUE on every rest leg — EXCHANGE-ENFORCED (Item 5)

    -- the anti-stale gate (I3)
    signal_ttl_secs    INTEGER NOT NULL,
    max_quote_age_ms   INTEGER NOT NULL,
    max_ask_drift      NUMERIC(6,4) NOT NULL,      -- ⚠️ SEE THE WARNING BELOW. This knob
                                                   --    REINTRODUCES ADVERSE SELECTION.
    min_secs_to_close  INTEGER NOT NULL,

    -- the cage (I4)
    entry_floor     NUMERIC(6,4) NOT NULL,
    band_lo         NUMERIC(6,4) NOT NULL,
    band_hi         NUMERIC(6,4) NOT NULL,
    hard_max_price  NUMERIC(6,4) NOT NULL DEFAULT 0.98,

    -- size / correlation (Item 10)
    size_cap_usd            NUMERIC(10,2) NOT NULL,   -- $50 HARD
    cluster_budget_frac     NUMERIC(6,4)  NOT NULL,   -- 0.02 of bankroll, PER CLUSTER
    cluster_split           TEXT          NOT NULL,   -- 'fcfs' | 'equal'
    cluster_expected_legs   INTEGER,                  -- 'equal' only. Pre-registered from history.
    daily_notional_cap_usd  NUMERIC(12,2) NOT NULL,
    max_concurrent          INTEGER       NOT NULL,

    -- detectors (Item 9)
    slip_mu0_cents  NUMERIC(6,4), slip_sigma0_cents NUMERIC(6,4), slip_L NUMERIC(4,2),
    slip_armed      BOOLEAN NOT NULL DEFAULT FALSE,   -- SHADOW until ≥100 real fills AT THIS SIZE
    clv_mu0 NUMERIC(6,4), clv_sigma0 NUMERIC(6,4), clv_k NUMERIC(4,2), clv_h NUMERIC(4,2),
    clv_armed       BOOLEAN NOT NULL DEFAULT FALSE,   -- SHADOW until the Phase-0 falsifier passes

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL,
    rationale  TEXT NOT NULL,        -- ⚠️ NOT NULL. Every config change MUST say WHY.
                                     --    This project has had four retractions. A row that
                                     --    changes real-money behaviour and cannot say why it
                                     --    exists SHOULD BE IMPOSSIBLE TO INSERT.
    PRIMARY KEY (arm, version)
);
CREATE UNIQUE INDEX one_active_policy_per_arm ON exec_policy (arm) WHERE active;
```

**Hot-reload.** The executor polls `SELECT * FROM exec_policy WHERE active` every 30s into an `ArcSwap<PolicyTable>`. **An in-flight order keeps the `policy_version` it was born with** — `OrderIntent.policy_version` is copied at construction, so a mid-flight reload cannot rewrite an order's attribution. **A parameter change never requires a redeploy** — which matters enormously, because **a redeploy is a kill-switch reset.**

> **⚠️ THE `max_ask_drift` TRAP — the synthesizer's finding, and neither designer saw it.**
> Designer B's central claim is that **waiting has no adverse selection, because you always fill.** That is true *only if you take unconditionally at T*. But B's own I3 gate says: *"if the ask has moved more than `max_ask_drift` from `decision_ask` by T, skip."* **That skips precisely the signals that ran away — i.e. the winners.** The freshness gate silently reintroduces the exact adverse selection the design claims to have escaped.
> **You must choose, explicitly, and the choice must be a column:** either take unconditionally at T (and eat the drift, which is what the unconditional decay curve actually prices), or gate on drift (and accept that you are selecting on the outcome). **`max_ask_drift` is therefore set GENEROUSLY (≥ the band width) for any policy with `t_rest > 0`, and the counterfactual logger records BOTH branches so the size of the selection effect is measured, not assumed.**

**Integration points.** `copy-trading-bot/src/config.rs:501/506/515/519` — the four constants **remain for the paper/modelled path** and are **removed from the executor's path**. New `copy-trading-bot/src/exec/policy.rs`.

**Cost.** One `SELECT` per 30s ≈ 0.03 queries/sec. **Free.**

**Source:** hybrid — both designers converged on collapsing the menu; Designer B's `Quote(t_rest, δ_rest, take_fallback)` parameterisation is the cleaner one. `rationale NOT NULL` is Designer A's and it is kept. `arm_priority` and the `max_ask_drift` trap are the synthesizer's.

---

### 9. Edge-decay detection without whipsaw — THE CRUX

**Before.** `pilot.rs:158` `KillSwitch::update_lambda(&mut self, lambda_est: f64)`. **Grep the whole workspace: nothing calls it.** The λ that would gate the Kelly ladder is a field that is never written. And `EdgeDegraded` halts **everything**, not one arm.

**The honest statement of the problem.** The champion's edge is thin (+3.27% honest ROI on 324 resolved / 168 events / **10 days**, per-bet outcomes ~93%-win Bernoulli at p≈0.88). A single day on `weather_fav` is **one correlated bet.** Long losing streaks are the **expected** behaviour of this edge. **A detector that demotes a healthy arm is worse than no detector** — it converts a real edge into zero, silently, and looks like prudence while doing it. And the asymmetry makes it worse: **demotion is instant and automatic, promotion is human-gated ⇒ a false demotion is STICKY.**

#### FINDING 1 (verified): **the brief's P&L CUSUM is not weak on `weather_fav` — it is STRUCTURALLY INCAPABLE OF FIRING.**

Designer B computed this and I re-derived it. It is the sharpest piece of statistics in the entire forge.

Per-bet: `SD(ROI) = √(0.93·0.07)/0.884 = 0.289`; `E[ROI] = (0.93−0.884)/0.884 = +0.052` ⇒ **per-bet SNR = 0.180.**
Day-cluster SD (the unit — bets within a day are not independent, D21):
- `favorite`: ~20 bets/day, ICC ≈ 0.1 ⇒ N_eff ≈ 10 ⇒ **day-SD ≈ 9.2%**
- `weather_fav`: **20 cities, ONE heat dome, ICC ≈ 1 ⇒ N_eff = 1** ⇒ **day-SD ≈ 28.9%**

If the edge goes to **ZERO**, the observable drops by:
- `favorite`: 5.6% / 9.2% = **0.61σ**
- `weather_fav`: 5.6% / 28.9% = **0.19σ**

| arm | observable | shift on edge→0 | k | H | **ARL₀ (false halt)** | **ARL₁ (detect)** |
|---|---|---|---|---|---|---|
| favorite | P&L | 0.61σ | 0.5 | 5.0 | 939 d | 25.4 d |
| **weather** | **P&L** | **0.19σ** | **0.5** | 5.0 | 939 d | **∞ — NEVER FIRES** |
| **weather** | **P&L** | 0.19σ | **0.1** | 5.0 | **60 d** | 27 d |

> **At `k = 0.5` the true shift (0.19σ) is SMALLER THAN THE REFERENCE VALUE**, so `E[increment] = 0.19 − 0.5 < 0`, the CUSUM statistic drifts to zero, and **it never fires — even on a TOTAL edge collapse.** Lower `k` to 0.1 to make it fire, and **ARL₀ collapses to 60 days**: it false-halts a perfectly healthy arm roughly **every two months** while taking 27 days to catch a real break. **The false-alarm rate is 2.2× the true-detection speed. That is not a detector; it is a coin flip with a spreadsheet.**
>
> **⇒ The P&L CUSUM is NEVER armed on `weather_fav`, at ANY n.** Designer A's proposal — "shadow it until ≥40 day-clusters accrue, then arm at H=5" — is right about the calibration problem and **wrong about the remedy**: A's ARL₁ = 10.4 days is the detection time for a **1σ** decay, but a **total** edge collapse on weather is only a **0.19σ** decay. **A's detector, even fully calibrated, would never detect the failure mode it was built for.**

#### FINDING 2 (verified against the SDK and the repo): **the detector must move UPSTREAM of P&L.**

Two things can decay, in different places:
1. **The pick decays** (the sharps stop being sharp) → shows up in the **closing line**, days before resolution. A continuous variable with far lower variance than a Bernoulli.
2. **The fill decays** (more copiers, thinner books, our own impact) → shows up in **realized slippage**, at fill time, **before** resolution.

**Neither is P&L. P&L is the CONFIRMATION, not the ALARM.** And `PilotLedger` (`pilot.rs:255-268`) **already tracks `clv_sum`** — the highest-power decay detector available is half-written in the codebase and wired to nothing.

#### DETECTOR A — **ΔCLV vs a matched placebo pool** (the *pick* detector)

```rust
// copy-trading-bot/src/exec/clv.rs — NEW. Runs per SIGNAL, in EVERY arm, at EVERY rung,
// INCLUDING SHADOW, from day one. Costs $0 and requires ZERO FILLS.
pub struct ClvObs {
    pub signal_id: i64,
    pub arm: String,
    pub cluster_key: String,   // super_event — ΔCLV IS DAY-CLUSTERED TOO. See the warning.
    /// TRUE book mid at fire (= entry_ask_fire_mid, Item 1). NOT the vote-mean (defect D2).
    pub mid_fire: f64,
    /// Mid at the CLOSE ANCHOR: kickoff for sports; resolution_ts − 1h for weather.
    pub mid_close: f64,
    pub clv: f64,              // mid_close − mid_fire, in ¢
    /// THE CONTROL. Mean CLV of M=200 markets drawn AT FIRE TIME from the SAME eligibility
    /// stratum — same arm predicate MINUS the consensus condition (same band, same family,
    /// same time-to-close bucket). This IS the belief-blind `selection_null`, run CONTINUOUSLY
    /// instead of once. It satisfies the evidence rule's clause (a) — "a control/placebo arm"
    /// — STRUCTURALLY, as a permanent runtime component rather than a script someone must
    /// remember to run.
    pub clv_placebo_mean: f64,
    pub delta: f64,            // clv − clv_placebo_mean.  E[Δ] = 0 under H0.
}
```

**Why ΔCLV is calibratable and P&L is not — and this is NOT the reason Designer B gave.**

> **⚠️ Designer B's stated reason is WRONG and I am correcting it rather than shipping it.** B claims the placebo pool "supplies σ₀ from 200 draws/day, on day one" and thereby solves the uncalibratable-σ₀ problem. **It does not.** `Var(Δ) = Var(clv_signal) + Var(placebo_mean) ≈ Var(clv_signal)` — averaging 200 placebo markets shrinks the variance *of the control*, not of Δ. **The placebo controls the MEAN (it removes market-wide drift, which is a genuine and important confound); it does not supply the day-level σ₀ the CUSUM needs.**
>
> **The REAL reason ΔCLV is calibratable, and it is sufficient: ΔCLV needs NO FILLS, so it can be computed RETROSPECTIVELY on the 395 historical `favorite` signals TODAY, at $0, using `fetch_price_history(token_id)` (`common/src/data/models.rs:~388`).** Real-fill ROI has **n = 0** historical observations and cannot be calibrated at any price. **That asymmetry — 395 vs 0 — is the entire argument, and it holds.**

**⚠️ And the second correction: ΔCLV is day-clustered TOO.** One forecast update moves all 20 heat-dome cities' lines *together* — plausibly with a **higher** ICC than P&L has. **⇒ the Phase-0 calibration MUST estimate `σ₀` at the DAY-CLUSTER level (`super_event`), not per-signal.** Designer B's weather power figure (0.86σ) was derived by scaling the per-bet SNR ratio, which implicitly assumes CLV's ICC equals P&L's ICC. **It probably does not, and the direction of the error is against us.** The falsifier below catches it.

**THE PRE-REGISTERED FALSIFIER — written before any executor code, and binding:**

```
PHASE 0.4, PRE-REGISTERED:
  Compute, on the 395 historical `favorite` signals, using fetch_price_history():
      Δ_d  = day-cluster mean ΔCLV (clustered by super_event), vs an M=200 matched placebo pool.
  Estimate  E[Δ]  and  σ₀ = SD of the DAY-CLUSTER mean Δ  (n = the number of day-clusters).
  Report:   n, dispersion, and a significance test vs the placebo. (The evidence rule, in full.)

  IF   SNR_day(ΔCLV) / SNR_day(P&L)  <  2.0×
  THEN the ΔCLV detector is DOWNGRADED to a diagnostic (LOG-ONLY, NEVER DEMOTES),
       `clv_armed` stays FALSE permanently,
       the ladder falls back to slippage-only + de-size + the mechanical cage,
       AND THE PLAN STATES PLAINLY:
         "We cannot detect selection decay on weather in under ~2 months, and no proposed
          detector can. We BOUND the loss. We do not pretend to detect it."
```
**That is the honest failure mode, written down in advance. If the number is not there, we say so.**

**If it passes**, the estimator is a day-clustered two-sided CUSUM on Δ, `k = 0.5`, `H = 5.0` (ARL₀ ≈ 939 days ≈ **one false halt per 2.6 years**), with `H` inflated to **6.5 for the first 20 day-clusters** as a burn-in that absorbs the residual σ̂ uncertainty. `μ₀`, `σ₀`, `k`, `H` are **pre-registered in `exec_policy` and NEVER re-fit on live data** — a detector that re-fits its own baseline chases its own tail.

**And the elegant collapse.** Set the placebo stratum to *"favourites that ONE sharp has already bought"* and **the same running statistic answers Rung 4 of the readiness ladder — "is the copy apparatus necessary at all?"** (the null is p=0.0005 vs a *random*-favourite pool but p≈0.5 vs a one-sharp pool). **One estimator, two questions, zero extra cost.** That is how the brief's requirement — *"build it so that discovering the copy apparatus is unnecessary is CHEAP"* — is satisfied **structurally.**

#### DETECTOR B — **EWMA on realized slippage** (the *fill* detector). Build it first; it is the one that will actually fire.

The most probable way this system goes quietly negative is **not** the pick decaying — it is **the fill degrading.** And unlike ROI, slippage is observable **per order** (n ≈ 20–40/day, not 1/day) and is **not confounded by outcome variance** (it is measured at fill time, before resolution). It is therefore **enormously** more powerful.

```rust
// copy-trading-bot/src/exec/slip.rs — NEW
/// slip_i = fill_price_i − decision_ask_i, in ¢. Positive = we paid MORE than we expected.
/// Both operands come from executor_orders + executor_fills. No model anywhere.
pub struct SlipEwma { z: f64, lambda: f64, mu0: f64, sigma0: f64, l: f64, n: u32 }

impl SlipEwma {
    pub fn update(&mut self, slip_cents: f64) -> bool {
        self.n += 1;
        let x = (slip_cents - self.mu0) / self.sigma0;             // standardized
        self.z = self.lambda * x + (1.0 - self.lambda) * self.z;   // λ = 0.10
        // One-sided upper control limit (slippage getting WORSE):
        //     limit = L · sqrt(λ / (2 − λ))
        self.z > self.l * (self.lambda / (2.0 - self.lambda)).sqrt()
    }
}
```

> **⚠️ THE TWO DESIGNERS DISAGREE ON σ₀ BY 2.2× AND NEITHER HAS AN ESTIMATE.** Designer A derives `σ₀ = 0.86¢` from the p90 (2.2¢) assuming normality; Designer B simply asserts `σ₀ = 2.0¢`. **The slippage distribution is a book-walk and is certainly right-skewed, so A's normal inversion is not sound either.** Their published ARL₀s (85 days vs 55 days) are therefore both **uncalibrated**, and an EWMA armed on a wrong σ₀ has the same sticky-false-demotion failure as the CUSUM.
>
> **⇒ `slip_armed = FALSE`. The EWMA runs in SHADOW (computing, logging, alerting Tue — demoting nothing) until ≥100 real fills establish `μ₀` and `σ₀` empirically. Then `L = 3.0` is set from the MEASURED σ̂ and written as a new `exec_policy` version with a rationale.**
>
> **⚠️ AND — neither designer said this — the book-walk is SIZE-DEPENDENT (slippage @$50 = 2.2¢; @$250 = 9.5¢). A σ₀ measured at Rung 2's $1–5 orders IS NOT VALID at Rung 3's $50 orders. `μ₀`/`σ₀` MUST be re-estimated at EVERY size rung, and `slip_armed` returns to FALSE on every size change.** This is a `CHECK`-able policy rule, not a note.

**Once armed (target parameters, to be confirmed against the measured σ̂):** `λ = 0.1`, `L = 3.0` ⇒ ARL₀ ≈ 1,700 orders ≈ **85 days**; ARL₁ on a +1σ degradation ≈ **11 orders — under one trading day.**

**And here is why arming it is safe even at a hot-ish ARL₀: its response is DE-SIZE, not HALT.** A false de-size costs half a day's gross on one arm and **auto-restores after 40 clean orders**. A false alarm every 85 days at ~$7 is **$0.08/day of expected cost** — whereas an undetected +1σ slippage degradation is **+0.9¢ = ~19% of the entire edge, forever.** The asymmetry is overwhelming. **Detector confidence sets response severity. That is the organising principle of the ladder.**

#### The graded ladder — **demotion automatic + instant; promotion evidence-gated + human**

| Trigger | Detector | ARL₀ | Response | Why not a halt |
|---|---|---|---|---|
| `SlipEwma` fires, **or** fill-rate halves | slippage (**shadow until ≥100 fills AT THIS SIZE**) | ~85 d | **Halve `size_cap_usd`** on that arm. Re-measure. | Cheap, reversible; a false positive costs half a day's size, not the arm. **AUTO-restores** after 40 orders with `z < 0`. |
| ΔCLV CUSUM fires (`k=0.5`, `H=5.0`) | ΔCLV (**shadow until the Phase-0.4 falsifier passes**) | **939 d** | **HALT that arm.** Cancel its resting orders. Write `executor_halts`. Alert Tue. **Human re-arm required.** | 1 false halt per 2.6 years buys a 3–13 day detection. A change-point is a structural claim and earns a structural response. |
| Day-clustered ROI **LB** crosses 0 over a rolling 20-cluster window | P&L (port `scripts/effective_n.py::cluster_robust()` :95 + `lb_at` :123 + `_t_ppf` :75 — **written, self-tested, ~150 lines of Rust port; DO NOT REINVENT THE STATISTICS**) | slow, by design | **Demote one rung** (live → paper). The arm keeps accruing evidence **at $0**. | P&L is the *confirmation*. It arrives late, and that is fine, **because it is not the alarm.** |
| θ LB ≤ 0 over ≥6 forward weeks, **or** LODO-by-week fails, **or** the belief-blind null fails | the frozen prereg gate | — | **RETIRE the arm.** | Pre-registered. Unchanged. That is what "retire" means. |
| `RejectStorm` / `DataStale` / `SpendBudget` / `SlateStop` | mechanical | — | **Halt that arm.** | Human re-arm. |
| Day stop (−5%) / max DD (−15%) / `OrphanPosition` / `ReconcileFailed` / `MasterOff` | mechanical | — | **HALT EVERYTHING.** `cancel_all()`. Latch. | The cage. |

**Cost.** ΔCLV: $0/turn, no fills needed. Compute: M=200 placebo mids × ~20 signals/day = 4,000 mid reads/day — **served from `clob_price_tape` (once Item 2 lands), NOT from the API.** Slippage EWMA: $0. Expected cost of the EWMA's false alarms once armed: **$0.08/day.**

**Source:** **refined.** Designer B's ΔCLV-with-placebo is the right instrument and B's proof that the P&L CUSUM cannot police weather is correct and decisive. But **B's justification for why ΔCLV is calibratable is wrong** (the placebo gives the mean, not the day-level σ₀) — the correct justification (395 historical signals vs 0 historical fills) is the synthesizer's, and it is what makes the design survive. Designer A's shadow-until-calibrated discipline is right and is applied to **both** detectors. The size-dependence of the slippage baseline, and the ΔCLV day-clustering caveat, are the synthesizer's — **neither designer had them, and both are the difference between a calibrated detector and a sticky false-demotion generator.**

---

### 10. Correlated sizing — "size the GAME" is a change of UNIT, not a formula

**Before.** `reports/risk_policy.json`: `"deploy_cap_per_day": 0.13`, `"deploy_hard_ceiling": 0.16`, `"per_bet_cap": 0.02`, **`"per_game_cap": null`**. `scripts/independence_sizing.py:11-16` states the bug in its own words: *"the risk policy deploys ≤13%/day spread flat-shares across the day's markets, which ASSUMES those markets are independent bets. They are not."* And `scripts/risk_engine.py:16`: *"It is NOT applied to anything."* **17 positions on one World-Cup game are, as far as any code is concerned, 17 independent bets.**

**After.** The Diagnostic and Designer A port `independence_sizing.py`'s `N_eff = nominal / (1 + (m̄−1)·ICC)`, with ICC pre-registered per family. **That is correct arithmetic — but it introduces a NEW PARAMETER THAT CAN BE WRONG, into a system whose defining failure mode is parameters that turned out to be wrong.** (Designer A's own `icc = 0.90` / `0.15` are admitted priors, unmeasured.)

**Designer B's move is better, and it gets the identical answer with zero parameters:** if **the game is the bet**, then **the notional cap applies to the game.**

```rust
// copy-trading-bot/src/exec/cluster.rs — NEW
/// The unit of risk is the CLUSTER (super_event), not the market.
/// `super_event()` already exists (scripts/superkey.py:43) — PORT IT, don't reinvent it.
pub struct ClusterGovernor { bankroll: f64 }

impl ClusterGovernor {
    /// Per-CLUSTER notional budget. risk_policy.json's `per_bet_cap = 0.02` — AND A CLUSTER IS
    /// ONE BET. That is the entire idea.
    fn cluster_budget_usd(&self, p: &ExecPolicy) -> f64 { p.cluster_budget_frac * self.bankroll }

    /// Size ONE leg. Returns 0 ⇒ SKIP. NEVER a silent shrink: path-dependent sizes are
    /// un-analyzable, and a skipped signal is an honest, recordable abstention.
    pub async fn size_usd(&self, sig: &Signal, p: &ExecPolicy, pool: &PgPool) -> f64 {
        let key      = super_event(sig);                        // ported from superkey.py:43
        let budget   = self.cluster_budget_usd(p);
        let deployed = cluster_deployed_today(pool, &key).await; // SUM(notional) WHERE cluster = key
                                                                 // over states NOT IN (REJECTED,
                                                                 // ABANDONED, CANCELLED, EXPIRED,
                                                                 // FAILED, SKIP_CONTENDED)
                                                                 // ⚠️ MATCHED COUNTS (INV-4).
        let per_leg = match p.cluster_split.as_str() {
            // SPORTS: a WC game's legs (moneyline + spread + …) ARE THE SAME BET.
            // Breadth within the cluster is FAKE diversification. First-come, first-served.
            "fcfs"  => p.size_cap_usd,
            // WEATHER: 20 cities in one heat dome are EXCHANGEABLE and NOT perfectly correlated.
            // 20 × $10 strictly dominates 4 × $50 in variance at identical total exposure.
            // `cluster_expected_legs` is pre-registered per family FROM HISTORY — a COUNT you
            // can observe, not a correlation coefficient you must estimate.
            "equal" => budget / p.cluster_expected_legs.unwrap_or(1) as f64,
            _       => unreachable!(),
        };
        per_leg.min(p.size_cap_usd).min((budget - deployed).max(0.0))   // 0 ⇒ SKIP
    }

    /// The daily cap is the OUTER bound; the cluster budgets are the INNER ones.
    pub async fn daily_room_usd(&self, pool: &PgPool) -> f64 {
        (0.13 * self.bankroll) - deployed_today(pool).await          // risk_policy.json
    }
}
```

**The budget check runs INSIDE the same transaction as the `INTENT` insert, with `SELECT … FOR UPDATE` on the cluster's budget row** — otherwise two concurrent signals on the same heat dome both read "budget available" and both deploy.

**The worked example that makes it concrete.** 20 cities, one heat dome, bankroll $10,000:

| Policy | Deployment | % of bankroll |
|---|---|---|
| **Cluster governor** (`equal`, `expected_legs=20`, `budget = 0.02·B = $200`) | **$10/city × 20 = $200** | **2.0%** |
| The ICC route (`m̄=20`, `ICC≈1` ⇒ `design_effect≈20` ⇒ `N_eff=1.0` ⇒ `min(0.13·B, 0.02·B·1.0)`) | $200 | 2.0% — **identical answer, one estimated parameter** |
| **Naive (today)** — 20 × $50 | **$1,000** | **10%** |

> **The naive policy puts 10% of bankroll on a single coin flip — which would trip the 15% max-drawdown halt IN ONE BAD DAY, on an arm that may be perfectly healthy.** The cluster governor is therefore **simultaneously a RISK control and a WHIPSAW control.** It is the piece of this build that most directly serves Tue's *"never negative for extended time"* requirement — **not by detecting anything, but by making the worst single day survivable.** And per Item 7, it is the *ex-ante* bound on open exposure that lets the max-DD latch safely operate on lagging realized equity.

Contrast a normal sports day: 8 games, ~1.5 positions each, `fcfs`, `$50` cap ⇒ the daily cap (`0.13·B = $1,300`) binds long before any cluster budget does. **The governor is inert exactly when the day is genuinely diversified.** Correct.

**Cost.** $0. One indexed `SUM()` per order. On a heat-dome day: forgone gross at +5.6% on the $800 not deployed = **−$45**; avoided worst-case loss = **$1,000 → $200 ⇒ $800 of tail risk removed.** And it prevents a healthy arm from tripping a **sticky** max-DD halt on one bad coin flip, which is worth more than the $800.

**⚠️ The one cheaper-to-be-wrong rule, and it must be a comment in the port:** if `super_event()` **merges** two clusters that are really distinct, we over-constrain (safe). If it **splits** one cluster into two, we over-deploy (dangerous). **WHEN IN DOUBT, MERGE. NEVER SPLIT.** Test the key against a real World-Cup day and a real heat-dome day from `consensus_signals` history before it governs a dollar.

**Source:** **rethink** (Designer B). "Assert the unit instead of estimating it — a parameter you never introduced cannot be wrong" is the correct instinct for this codebase, and it lands on the same number. The `FOR UPDATE` serialization is Designer A's and is kept; the `MATCHED`-counts rule is the synthesizer's (it follows from INV-4).

---

### 11. The shadow A/B — a REFUSAL, defended; and what CAN honestly run

**The brief §4.4 says:** *"Always run the alternatives in SHADOW alongside the live one (extend the `feat/exec-policy` evaluator) so the frontier keeps being estimated while we trade."*

**Half of that is impossible, and the impossible half is the half the maker thesis depends on.**

`feat/exec-policy`'s `common/src/storage/exec_policy.rs::tape_maker_fill()` (:160-188) decides a **"REALISTIC"** maker fill with:
```sql
MIN(recv_at) FILTER (WHERE event_type = 'price_change'
    AND last_price IS NOT NULL AND last_price > 0
    AND last_price <= $5 AND COALESCE(last_size, 0) > 0) AS print_at
```
…and books it into `honest_paper_ledger` — **the same table the certification gate reads.** Meanwhile `copy-trading-bot/src/cycles/live_tape.rs` (~:224), **the module that WRITES those very rows**, says in its own comment:

> *"`last_price` in a price_change is order-BOOK-LEVEL churn (**not a trade**), so it is NOT in the key."*

**The writer says it is not a trade. The reader treats it as one.** That is the whole finding. **It is the exact G2 bug that produced two false "+4.8%" results**, and the bias has a **direction**: book flicker is *more* frequent when the book is churning ⇒ when the price is moving ⇒ **preferentially at the moments a real resting maker would NOT have been filled.** It systematically **over-states the maker fill rate**, on **the exact policy the whole build wants to believe in.**

And it is **worse than that**: because `last_price`/`last_size` are **excluded from the tape's on-change dedup key** and rows are **keep-LAST-coalesced** per `coalesce_ms` bucket, the `last_size` values that reach the table are a **non-uniformly-sampled version of the wrong field.** **No correction factor rescues it.** (Third defect: `migrations/040_live_ingestion.sql` documents `last_size` as *"trade size in SHARES"* — **the schema comment is also wrong**, and it is the comment the next engineer will trust. Fixed by the `COMMENT ON COLUMN` in migration 043. **Never edit an applied migration — sqlx checksums ⇒ crash-loop.**)

**Designer A proposes fixing it with a DWELL model** (credit a fill only if the best ask *dwells* at or below the limit across ≥2 tape inflections spanning ≥30s; never read `last_price`/`last_size`). It is honest about being a model, and it is **an OPTIMISTIC UPPER BOUND** — it ignores queue position entirely: if the ask touches your price you are assumed filled, when in reality you are behind everyone who was already there.

**Designer B refuses to build it, and Designer B is right.**

> **An upper bound on the maker fill rate, published as a number, WILL be quoted as the fill rate.** That is precisely how this project produced two false "+4.8%" results. **So: do not merge `feat/exec-policy`. Do not fix `maker_print`. Do not build a DWELL model.**
>
> **The maker leg's fill rate is UNKNOWABLE before Rung 2. Full stop. Every number produced about it before then is a hypothesis, not a result, and must never be the basis for risking money.**
>
> **That single sentence is worth more than an 846-line evaluator that produces an optimistic bound.**

**What CAN honestly run in shadow, from day one, at $0:**

| Question | Shadow-observable? | Why |
|---|---|---|
| What would `take_at_fire` have paid? | ✅ **YES** | Taking is deterministic given the book. This is exactly `entry_ask_fire` (Item 1). |
| What would `patient_take(T)` have paid, for T ∈ {5m, 15m, 30m}? | ✅ **YES** | The ask at fire+T is a tape read. **This is the biggest open question in the build and it is FREE.** |
| Is the pick decaying? (ΔCLV) | ✅ **YES** | Pure market data. No fills needed. (Item 9.) |
| Does consensus beat "a pool of favourites one sharp already bought"? | ✅ **YES** | The same placebo pool. Readiness-ladder Rung 4, answered for $0. |
| **Would a resting bid at mid have filled?** | ❌ **NO** | Requires a trade tape we do not have, or a fill model we must not build. |
| **What is our own market impact?** | ❌ **NO** | Requires our own orders in the book. |

**⇒ The shadow A/B logs the deterministic counterfactuals ONLY.** For every fired signal, at every rung, a row per policy point: `take_at_fire`, `patient_take(5m/15m/30m)` — each with the real observed ask at that horizon, from the tape. **The maker leg produces NO shadow row. It produces an `unknowable` marker.** An honest hole beats a flattering number.

**Salvage from `feat/exec-policy` — the structure is genuinely good.** Lift `tape_quote_at()` (`exec_policy.rs:~130`) **verbatim** — it is correct and it is exactly what the `patient_take` counterfactual needs. Keep the pending-scan → freeze → book discipline, the `ON CONFLICT DO NOTHING`, the `EXEC_EVAL_MIN_AGE_SECS` window, and above all the clock discipline (**"order by `recv_at`, never `exch_ts`"** — the D1-E tape-clock lesson). **Leave `tape_maker_fill()` (:160-188) behind. Migration 041 is retired permanently (see Item 12).**

#### The learning loop — what makes it adapt

Once real fills exist, the question is **deleted, not answered better.** The executor writes back, per order:

| Metric | Formula | Answers |
|---|---|---|
| **Slippage** | `fill_price − decision_ask` | Is the fill degrading? (→ the EWMA, Item 9) |
| **Fill rate** | `COUNT(FILLED) / COUNT(FILLED + EXPIRED + CANCELLED)` grouped by `(arm, policy_version, price_band)` | **Is the maker leg real?** The only honest source. |
| **`trader_side`** | `Maker` \| `Taker` — ✅verified on `TradeResponse` | **PROVES `post_only` worked** ⇒ proves we paid zero fee on the maker rungs. |
| **`wr_filled` vs `wr_missed`** | **THE ADVERSE-SELECTION DETECTOR.** Join `executor_orders` → resolution. `wr_filled` = win rate on signals we filled; `wr_missed` = win rate on signals we quoted and did **not** fill. | **If `wr_missed` ≫ `wr_filled`, the maker leg is catching reverters and missing winners** — exactly what D31 measured (62–65% vs ~100% on long cancels) and exactly what would kill the maker thesis. **This is the single most important number the executor produces.** |
| **Our own market impact** | `best_ask(T+60s) − best_ask(T−1s)` around our order, vs a matched control of signals we did **not** trade | The capacity curve walks a *snapshot* book ⇒ real capacity **≤** measured. This is the only way to know by how much. |
| **Realized fee** | `TradeResponse.fee_rate_bps` | Settles the $13/day fee band (Item 3). |

**The weekly job** (`scripts/exec_frontier.py`, extending `feat/maker-copy-g3`'s existing δ×T_cancel sweep) re-estimates the frontier **on our own real fills** and **INSERTS a new `exec_policy` row with `active = FALSE`** and a filled-in `rationale`. **Tue flips `active = TRUE`.** Same evidence bar, always: **(a) a control/placebo arm, (b) a significance test, (c) explicit n + dispersion.**

**Source:** **rethink** (Designer B), with Designer A's salvage list. B's refusal is the harder call and the right one: *an open question is better than a biased answer — a bet this project has now lost four times in the other direction.*

---

### 12. Migration order and the auto-deploy hazard

**The hazard.** `scripts/consensus-autoupdate.sh` (launchd): ff-only pull, then *"rebuilds + recreates the stack whenever HEAD advances"*, gated at `:49` on `git diff --name-only "$LAST" "$HEAD" | grep -qE "$CODE_RE"`. **Rust source matches `$CODE_RE`. ⇒ merge to `main` == deploy to prod, minutes later, with a container recreate.**

**Migration ordering — sqlx checksums are immutable, and a duplicate number (or an edited applied migration) CRASH-LOOPS THE APP ON STARTUP, after the autoupdater has already deployed it. This is a deployment-halting bug, not a data bug.**

| # | Branch | Action |
|---|---|---|
| **041** | `feat/exec-policy` | **DO NOT MERGE. RETIRED PERMANENTLY.** Its fill model is poisoned (Item 11). ⚠️ **And once 043 is applied, 041 can NEVER be applied** — sqlx errors on an out-of-order version. **If its structure is ever wanted, lift the CODE and renumber the migration to 045+.** A gap is fine; a duplicate — or a backfill — is not. |
| **042** | `feat/paper-executor` | **MERGE FIRST, ALONE, TODAY.** (Item 1. Its own header already says: *"Version gaps are fine; a duplicate number is not."*) |
| **043** | executor | `executor_orders` + `executor_fills` + INV-1/INV-2 constraints + `executor_halts` + `consensus_signals.{token_id, neg_risk, tick_size}` + the `COMMENT ON COLUMN` fix. |
| **044** | executor | `exec_policy`. |

**The three independent locks — all must be turned off for an order to exist, and each is a separate human action:**

1. **Compile-time:** `live-exec` cargo feature **OFF** ⇒ `LivePlacer` **does not exist in the binary**, and `alloy` is not even compiled. *(Stronger than the repo's own runtime-flag pattern, and it also keeps a 469-package tree out of every prod rebuild.)*
2. **Spawn-time:** `EXECUTOR_ENABLED` **off** ⇒ the three tasks are **never spawned** ⇒ **byte-identical** (`live.rs:225/252/475`).
3. **Run-time:** `PILOT_ARMED != "1"` ⇒ `OrderGate::place` returns `NotArmed` (`pilot.rs:86`); **and** `executor_halts` is **seeded `MasterOff` by migration 043** ⇒ **halted from birth**, and only a human `UPDATE … SET cleared_at` can un-halt it.

**⚠️ AND THE COMPOUNDING HAZARD, ONE MORE TIME: a container recreate IS a kill-switch reset. Merging the executor is the very event that would erase the executor's halt state. ⇒ Item 7's `executor_halts` MUST ship in the SAME PR that wires the executor. Not the next one. The same one.**

**Source:** hybrid — Designer B's "retire 041" (which *removes* an ordering dependency rather than managing one) + Designer A's compile-time lock + the Diagnostic's Correction D on the spawn slot.

---

## § EXECUTION ORDER — dependency-ordered phases, each with a Verify gate

**No phase begins until the previous phase's Verify is green.**

### PHASE 0 — $0, no executor code, and it is where the money is
Ships to prod immediately. None of it requires the executor; **all of it is a prerequisite for anything downstream meaning anything.**

| # | Action | Verify |
|---|---|---|
| **0.1** | **Merge mig 042; set `CAPTURE_ENTRY_ASK_AT_FIRE=1`.** (Item 1.) **Backfill is impossible.** | `SELECT count(*) FILTER (WHERE entry_ask_fire IS NOT NULL) FROM consensus_signals WHERE first_detected_at > now() - interval '24 hours'` **> 90% of in-band fires.** Median capture lag **< 5s** (today: 1,300s). |
| **0.2** | **Fix the tape universe** (Item 2, `consensus.rs:1629`). | `SELECT count(DISTINCT condition_id) FROM clob_price_tape WHERE …weather…` **> 0.** And ≥90% of the last 24h of fired `weather_fav` signals have tape coverage within 60s of fire. |
| **0.3** | **Fix `realizable_pnl` split** (Item 4). Re-point `append_paper_bet` at `entry_ask_fire` (Item 1). Run `scripts/fee_schedule_sensitivity.py` with the corrected rate table (sports 0.03 → **0.05**) plus an on-chain-formula column (Item 3). | `cargo test -p copy-trading-bot pilot::` — **all 8 original tests green.** The corrected fee sensitivity is reported to Tue with the gate's pass/fail margin recomputed. |
| **0.4** | **THE ΔCLV FALSIFIER** (Item 9). Measure `E[Δ]` and **day-cluster** `σ₀` on the 395 historical `favorite` signals vs an M=200 matched placebo pool, via `fetch_price_history()`. | **Pre-registered:** if `SNR_day(ΔCLV) / SNR_day(P&L) < 2.0×`, **`clv_armed` stays FALSE permanently** and the plan says so plainly. Report n, dispersion, and the placebo significance test. |
| **0.5** | **THE `patient_take` MEASUREMENT** (see § Rejected approaches — this is the one that decides the execution posture). ROI at `ask(fire+T)` for T ∈ {0, 5m, 15m, 30m}, on real resolved signals, from `clob_price_tape` + `consensus_signals`. **WITH A MATCHED PLACEBO ARM OF UNTRADED MARKETS** — because the prior measurement of this exact intervention (+2.05¢ ± 4.0¢, **p = 0.36**, n=20 vs 72 placebo) found the **placebo drifted MORE**, and was **RETRACTED**. Pure SQL. No flag. No risk. No fill model. | **n ≥ 100 day-clustered signals AND placebo-corrected p ≤ 0.05** ⇒ `patient_take` may become a default. **Otherwise `take_at_fire` remains the default and `patient_take` stays a shadow counterfactual.** n today is ~21; it reaches ~300 in ~2 weeks once 0.1 + 0.2 land. |
| **0.6** | **Answer the ToS / jurisdiction gate.** (§ What needs Tue.) | A written answer in `DECISIONS.md`. **Rungs 2–4 do not start without it.** |

### PHASE 1 — the cage (Rung 0, Shadow, $0)
Migrations 043 + 044. `OrderIntent` + `Placer` + `ShadowPlacer`. The state machine + INV-1/2/3/4. The reconciler. `ArmGate` + `executor_halts` + the kill watch — **in the SAME PR** (Item 12). `ClusterGovernor`. `exec_policy` + the three seed rows. Three detached tasks at `live.rs:508`, `EXECUTOR_ENABLED` **default OFF**. **`live-exec` cargo feature OFF ⇒ zero crypto in the binary.** ΔCLV + placebo pool accruing. The deterministic shadow A/B accruing.
**Verify:** **all of I1–I10 green** (§ Invariants), *including* `crash_mid_send_recovers_by_token`, `cancel_race_fill_wins`, `matched_then_failed_books_nothing`, `wedged_loop_kill`, `restart_does_not_unhalt`, `orphan_position_halts_loudly`. Plus: **`git diff` of the released binary with `EXECUTOR_ENABLED` off is byte-identical in behaviour** (the task is never spawned), and `cargo tree | grep alloy` returns **nothing** in the default build.

### PHASE 2 — Rung 0 live in prod (Shadow, $0)
`EXECUTOR_ENABLED=1`, `PILOT_ARMED` unset, `executor_halts.__master__` still `MasterOff`. **Every decision is logged; nothing is sent.** The full policy → clamp → cluster-budget → gate → state-machine path executes on every real signal.
**Verify:** ≥2 weeks. **Zero** `SkipContended` mis-handling, **zero** unresolved `SENT` rows, **zero** orphans. `executor_orders.mode = 'shadow'` on 100% of rows. The shadow A/B has ≥100 day-clustered counterfactual rows per policy point.

### PHASE 3 — Rung 1 (Paper-at-real-ask, $0)
`PaperPlacer`. The **take** leg books at the **real observed ask** (deterministic given the book — fully honest). The **rest** leg **abstains and records `unknowable`. It does not simulate.**
**Unlocks on:** ≥2 disjoint weeks of clean `entry_ask_fire`; ask-capture lag p50 < 5s; **Item 2 fixed for `weather_fav`**.
**Verify:** `paper_and_live_traverse_identical_states` green. The frozen certification gate **re-run on `entry_ask_fire` with the CONSERVATIVE fee** — and its verdict reported honestly, whatever it is.

### PHASE 4 — Rung 2 (Micro-real, $1–5/order, ≤$50 total) — **BLOCKED ON TUE**
`clob-exec` crate + `LivePlacer`. `live-exec` on. **Purpose is PLUMBING TRUTH, NOT P&L.** Day one, in this order:
1. **THE $1 FEE EXPERIMENT.** Place one $1 order; read `fee_rate_bps` off the trade event. **Resolves the $13/day fee band (40–70% of net) that four documents have argued about.**
2. Verify `signature_type` (the startup balance assert), `neg_risk` routing, `tick_size`, **GTD expiration is actually honoured**, `post_only` rejects-on-cross, the WS fill push, and `not_canceled` semantics.
3. Fetch `min_order_size` per market. **If the minimum is $5, Rung 2 is $5/order, not $1. Never assume.**
4. **Enable the maker leg at $1** (`δ_rest = +0.5¢`, `post_only = true`) — **the ONLY way to measure the fill rate and `trader_side`. Its P&L is irrelevant; `filled/(filled+expired)` is the entire deliverable.**
**Verify:** 10 consecutive days of **100%-clean reconcile**: zero orphans, zero unresolved indeterminates, zero `Failed` trades. Slippage measured. `trader_side = 'Maker'` on 100% of post-only fills.

### PHASE 5 — Rung 3 (Pilot, $50/signal, ≤$1k/day)
**Unlocks on:** Phase 4's verify **and** our own market impact **measured** (book before/after vs a matched control of untraded signals) **and** `slip_armed` re-established **at the $50 size** (Item 9 — the baseline does not transfer across sizes).

### Rung 4 (Scaled) — **we do not expect it to exist.**
$250/signal ⇒ **9.5¢ slippage > the entire edge.** Turnover above capacity is negative EV. **Size is a risk, not a lever.**

---

## § THE PER-ARM POLICY TABLE — actual values, with the physics reasoning

**The adjudication first.** The brief asks: *"Is there ONE policy family that covers all three arms, or must they genuinely diverge?"*

> **ONE FAMILY. THREE PARAMETERIZATIONS. They diverge in `t_rest`, `δ_rest`, and `band_lo` — and in NOTHING ELSE.** One state machine, one set of clamps, one reconcile path, one set of I1–I10 tests, three rows in a table. Everything the brief calls "flexibility" is a `SELECT`.

**And the honest part.** Both designers derived a *winner* and **both proofs failed verification** (§ Rejected approaches). **Therefore the Rung-0/1 seed is the CHEAPEST-TO-BE-WRONG default — `take_at_fire`, the only policy whose cost is actually measured — with every alternative running as a $0 shadow counterfactual and earning its way in through Phase 0.5.** That is not indecision; it is the only posture the evidence supports.

| | **`favorite`** (CHAMPION) | **`weather_fav`** | **`proven_router`** (hot lane) |
|---|---|---|---|
| **centre price `p`** | ~0.85 | ~0.80 | ~0.70 (floor 0.45) |
| **the physics (verified)** | The executable ask decays toward mid₀ (+3.4¢@fire → +2.2¢@5m → +0.6¢@15m → ≈0@30m, **n≈20–22/horizon**) **while the favourite's true price drifts toward 1.0 as the match runs.** ⇒ a long rest is **adversely selected BY THE CLOCK**: you fill only when the price came back = when you are losing. (`wr_filled` 62–65% vs `wr_missed` → ~100% on long cancels.) | Daily markets, **no in-play events ⇒ price barely moves. The BOOK binds, not the clock.** A patient post-only rest is genuinely near-free, **and makers pay ZERO fees** (verified, exchange-enforced via `post_only`). | **The edge is FRONT-LOADED — only 28–36% of signals EVER retrace to the sharp's price** (`hot_lane.rs:7-8`). ⇒ **a resting bid STRUCTURALLY MISSES THE WINNERS.** |
| **`t_rest_secs`** | **0** (Rung 0–1) | **0** (Rung 0–1) | **0** |
| **`delta_rest_cents`** | **NULL** (no rest leg) | **NULL** (no rest leg) | **NULL** |
| **`take_fallback`** | true | true | true |
| **`post_only`** | (n/a until a rest leg exists) | (n/a) | false |
| **`band_lo` / `band_hi`** | 0.65 / 0.98 | **0.71 / 0.90** | **0.75** / 0.90 |
| **`entry_floor`** | 0.75 | 0.45 *(safe ONLY when a post-only rest leg exists — see below)* | **0.75** |
| **`size_cap_usd`** | **$50** | **$25** (half — uncertified on the only basis the gate accepts, and unmeasurable until Item 2) | $50 |
| **`cluster_split` / `expected_legs`** | `fcfs` / — | **`equal` / 20** | `fcfs` / — |
| **`cluster_budget_frac`** | 0.02 | 0.02 | 0.02 |
| **`max_ask_drift`** | generous (≥ band width) — see the `max_ask_drift` trap, Item 8 | generous | 1.0¢ (`t_rest=0` ⇒ no selection risk) |
| **`signal_ttl_secs`** | 1800 | 7200 | **600** |
| **`arm_priority`** | 1 | 2 | 0 (hot lane wins contention) |
| **`rung`** (per-arm, Tue §4b) | 0 | **0 — and it MAY NOT LEAVE Rung 0 until Item 2 is fixed and ≥2 weeks of tape have accrued** | 0 |

**The three genuine divergences, and why:**

1. **`weather_fav` gets the LONG post-only rest — but only at Rung 2, and only as an experiment.** Its physics is the one case where a patient rest is genuinely near-free (no in-play clock) *and* the maker fee is zero. **But `clob_price_tape` has ZERO weather rows, so NONE of this is measured.** Per the cheaper-to-be-wrong rule, its Rung-0/1 row is the conservative corner on every knob and is **labelled an ASSUMPTION, not a finding.**

2. **`proven_router`'s `band_lo` is RAISED 0.45 → 0.75, contradicting `risk_policy.json`'s global `entry_floor: 0.45` — and that contradiction is exactly what the per-arm table exists to express.** The router is caught in a vice: it **must take** (only 28–36% retrace ⇒ resting misses the winners) and it is the **low-price arm** (taker cost rises as `p` falls: the fee is `feeRate × (1−p)` of notional, and the spread is `spread¢ / p` of notional — **both blow up together**). **⚠️ HONESTY: Designer A "proved" this by extrapolating the 3.4¢ premium — measured on `favorite` at p≈0.85 — across the whole 0.45–0.90 range. The absolute spread is NOT a constant across bands, and nobody has measured it below 0.75. The DIRECTION of the argument is right and the fee leg is verified arithmetic; the MAGNITUDE is an extrapolation.** The decision to raise the floor stands **because it is the cheaper-to-be-wrong direction** (it removes turnover we have no measurement for), **not because the proof is sound.** The shadow A/B keeps measuring 0.45–0.75 at $0, and if the sub-0.75 mid-basis edge turns out to exceed the cost, **the config flips with one `UPDATE`. That is the right way to be wrong.**

3. **`entry_floor` is a property of the POLICY, not the arm.** A post-only maker pays **neither** the spread **nor** the fee, so `0.45` is safe for it. A taker at `p = 0.45` pays a fee of `0.05 × 0.55 = 2.75%` of notional *plus* the spread — **which is why every `t_rest = 0` row carries `entry_floor = 0.75`.** This is a real, verified asymmetry and it is why one global floor cannot be correct.

**What every seed row says in its mandatory `rationale` column:** *"D31's own verdict is INDETERMINATE-BY-POWER (N=20, 2 day-clusters vs the 5 required). Every δ and T value in this table is a PRIOR, NOT A MEASUREMENT."*

---

## § INVARIANTS I1–I10 → CONCRETE TESTS

**The 8 existing `pilot.rs` tests (`:289-396`) are a CONTRACT: `place_refuses_when_unarmed`, `place_refuses_even_when_armed_no_placer`, `armed_gate_still_blocked_by_halt`, `day_stop_loss_latches`, `max_drawdown_halts`, `edge_degradation_halts`, `master_off_halts_by_default`, `delevered_stake_is_twelfth_kelly`, `realizable_pnl_matches_model`, `ledger_tracks_clv_and_pnl`. EXTEND, NEVER BREAK.**

**Note on `place_refuses_even_when_armed_no_placer`:** the Diagnostic and Designer A proposed **rewriting** it. **Designer B is right that it should pass UNCHANGED** — because `placer: Option<Arc<dyn Placer>>` is `None` in the default-constructed gate, and `PilotError::NoPlacer` survives as a live branch. **Deleting or rewriting that test deletes the proof. Keeping it is strictly better.**

| # | Invariant | The test (name it exactly this) |
|---|---|---|
| **I1** | Write-ahead intent | `intent_row_exists_before_any_network_call` — a `Placer` that panics inside `place()`; assert `executor_orders` holds a row in state `SENT`, and the panic did **not** reach `live.rs` (detached spawn). |
| **I2** | Structural idempotency | `duplicate_client_order_key_is_impossible` — call `send_one` twice with identical `(signal_id, policy_version, leg, attempt_seq)`; assert **one** row and **one** `place()` call. **And** `single_flight_is_a_db_constraint` — two concurrent `INTENT` inserts for one token → the second gets a `23505` on `exec_one_live_per_token`; **assert it surfaces as `SkipContended`, NEVER as a retry.** |
| **I3** | Freshness precondition | `stale_quote_is_never_sent` — table-driven over 5 rejects: `quote_age > max_quote_age_ms`; `|ask − decision_ask| > max_ask_drift`; `signal_age > signal_ttl`; `secs_to_close < min_secs_to_close`; tape heartbeat dead. Assert `place()` is **never called**. |
| **I4** | Double price clamp | `policy_bug_cannot_pass_the_gate` — inject a policy layer emitting `limit_price = 0.99` and one emitting `0.30`; assert `OrderGate::place` returns `PriceClamp`. **The two clamps are deliberately duplicated, deliberately NOT factored into a shared helper — a shared helper has ONE bug; two clamps have two.** |
| **I4′** | Maker never crosses | `maker_rungs_are_post_only` — assert every `OrderIntent` with a rest leg has `post_only = true` and `order_type = GTD`. **And at Rung 2:** assert `executor_fills.trader_side = 'Maker'` on 100% of those fills. *(The exchange rejects a crossing post-only order — `order_builder.rs:334` — so this is EXCHANGE-ENFORCED, not merely asserted.)* |
| **I5** | **crash-mid-send** | **`crash_mid_send_recovers_by_token_not_by_key`** — seed a `SENT` row with no `exchange_order_id`; the mock exchange returns one order on `orders(asset_id=T)`. Assert: **adopted → `LIVE`, `place()` NEVER called again, exactly one position.** Then the mirror: `open_orders` → ∅ **and** `fills_since` → ∅, on **two reads ≥120s apart** ⇒ `ABANDONED` (**one empty read must NOT abandon** — `OrderStatusType::Delayed` is real). Then the asymmetry: `open_orders()` **ERRORS** ⇒ **HALT(`ReconcileFailed`), and NO order is placed.** |
| **I5b** | **orphan POSITION** | `orphan_position_halts_loudly` — `fills_since` returns a trade with no matching `executor_orders` row ⇒ `executor_halts` row `('__master__','OrphanPosition')` written, ntfy priority-5 fired, **and the executor loop REFUSES TO START.** *(An unrecognised open ORDER is merely cancelled — INV-3. Severity attaches to the fill, not the order.)* |
| **I5c** | **cancel-race** | **`cancel_race_fill_wins`** — `cancel()` returns `CancelOrdersResponse.not_canceled = {id: "already matched"}`; then a `TradeMessage` arrives. Assert: state → `MATCHED` (**never** `CANCELLED`), the cluster budget is **NOT** released, **no re-quote is issued**, and the position is counted **exactly once**. Replay the same trade event ⇒ **no second booking** (`UNIQUE(exchange_trade_id, status)`). |
| **I5d** | **two-phase settlement (INV-4)** | `matched_then_failed_releases_position_and_books_nothing` — deliver `MATCHED` then `FAILED`. Assert `honest_paper_ledger` has **ZERO** rows for it, the cluster budget **is** released, and the `RejectStorm` counter incremented. **And** `matched_then_confirmed_books_once` — deliver `MATCHED`, `MINED`, `CONFIRMED`; assert **exactly one** ledger row, booked only on `CONFIRMED`. |
| **I6** | Latching, per-arm, **restart-surviving** | `restart_does_not_unhalt` — write a `MaxDrawdown` halt; **drop the entire `ArmGate` and `rehydrate()` from the DB**; assert still halted, `halted_by` unchanged. **This is the test the current code FAILS.** **And** `arm_halt_does_not_halt_other_arms` — halt `weather_fav`; assert `favorite` still places. **And** `master_off_halts_everything`. |
| **I7** | **wedged-loop kill** | **`kill_works_when_the_executor_loop_is_wedged`** — replace `run_executor`'s body with `std::future::pending()`. `touch /data/KILL`. Assert `cancel_all()` is called within **3s** and `executor_halts.__master__` is open. *(Structurally guaranteed: `run_kill_watch` shares no lock, no channel, and no state with the executor loop, and holds its own DB connection and its own `Placer`.)* **And** `kill_watch_fails_closed` — make the DB read error; assert it halts anyway. |
| **I8** | **No fill model. Ever.** | `no_code_path_reads_last_size` — a **grep test in CI**: `! grep -rn 'last_size' --include='*.rs' copy-trading-bot/src/exec/`. Crude, and exactly right: **this bug has cost this project two false results and it must be STRUCTURALLY UNWRITABLE.** **And** `no_fill_without_an_event` — `filled_shares` / `avg_fill_price` / `fees_paid` are settable **only** through `pub(in crate::exec::fills)::apply_fill(TradeMessage)`. Enforced by the module boundary, not by discipline. |
| **I9** | Full attribution | `every_order_is_attributable` — property test: every `executor_orders` row has non-null `(signal_id, arm, policy_version, mode, decision_ask, decision_bid, decision_mid, decision_ts)`. **And** `hot_reload_does_not_rewrite_inflight_attribution` — flip the active config mid-flight; assert the in-flight order keeps its **original** `policy_version`. |
| **I10** | Paper and real share ONE path | `paper_and_live_traverse_identical_states` — run the same signal through `PaperPlacer` and a mocked `LivePlacer`; assert the **state-transition sequences are byte-identical** and **only `executor_orders.mode` differs.** **Divergent paths are how paper lies to you.** |
| **+** | Cluster governor | `heat_dome_caps_at_one_bet` — 20 city signals sharing a `super_event` key; assert total deployment = **$200 (2% of bankroll), not $1,000 (10%)**. **And** `super_event_merges_never_splits` — run the key against a real World-Cup day and a real heat-dome day from `consensus_signals` history. |

---

## § THE PROMOTION LADDER (5 rungs, PER-ARM, default OFF) and the DEMOTION LADDER (automatic, instant)

`exec_policy.rung` is **per-arm** (Tue §4b): `weather_fav` can sit at Rung 0 while `favorite` is at Rung 1.

| Rung | Mode | Money | Unlocks when | Locks that must be opened |
|---|---|---|---|---|
| **0 — Shadow** | `ShadowPlacer` | **$0** | I1–I10 green. Decisions logged; **nothing sent.** | `live-exec` **off** (not compiled) · `EXECUTOR_ENABLED=1` · `PILOT_ARMED` unset · `__master__` still `MasterOff` |
| **1 — Paper-at-real-ask** | `PaperPlacer` | **$0** | ≥2 disjoint weeks of clean `entry_ask_fire`; capture lag p50 < 5s; **Item 2 fixed for weather**. Take leg books at the real observed ask; **rest leg records `unknowable` and does NOT simulate.** | same |
| **2 — Micro-real** | `LivePlacer` | **$1–5/order, ≤$50 total** | Rung 1 green **AND** the frozen gate re-run on `entry_ask_fire` **with the conservative fee PASSES** **AND Tue's ToS answer is YES.** **Purpose is PLUMBING TRUTH — the $1 fee experiment, auth, neg-risk, GTD, post-only, WS fills, reconcile — NOT P&L.** | `live-exec` **on** · `EXECUTOR_ENABLED=1` · `PILOT_ARMED=1` · a human `UPDATE executor_halts SET cleared_at=NOW(), cleared_by='human:tue'` |
| **3 — Pilot** | `LivePlacer` | **$50/signal, ≤$1k/day** | Rung 2 reconciles **100% clean for 10 consecutive days** — zero orphans, zero unresolved indeterminates, zero `FAILED`. Slippage inside budget. **Our own market impact MEASURED.** `slip_armed` re-established **at the $50 size.** | same |
| **4 — Scaled** | `LivePlacer` | > pilot | **Only against MEASURED capacity INCLUDING our own impact. Never against a snapshot book.** ⚠️ **We do not expect this rung to exist: $250/signal ⇒ 9.5¢ slippage > the entire edge.** | same |

**THE DEMOTION LADDER — automatic, instant, and it needs no human:**

| Trigger | Response | Reversal |
|---|---|---|
| Slippage EWMA fires, or fill-rate halves | **Halve `size_cap_usd`** on that arm | **AUTO** after 40 clean orders |
| Day-clustered ROI LB crosses 0 (20-cluster window) | **Demote one rung** (live → paper). Keep accruing at $0. | Human, on evidence |
| ΔCLV CUSUM fires | **Halt that arm.** Cancel its orders. Alert Tue. | **Human re-arm only** |
| `RejectStorm` / `DataStale` / `SpendBudget` / `SlateStop` | **Halt that arm.** | Human |
| Day stop −5% / max DD −15% / `OrphanPosition` / `ReconcileFailed` | **HALT EVERYTHING.** `cancel_all()`. Latch. | Human |
| θ LB ≤ 0 over ≥6 forward weeks, or LODO fails, or the belief-blind null fails | **RETIRE the arm.** | Never |

**The asymmetry is deliberate: demotion is instant and automatic; promotion is evidence-gated and human. That makes a false demotion STICKY — which is why every detector in this build ships in SHADOW until it is calibrated on real data, and why the mechanical cage (not the statistics) is the arm's real protection for the first ~2 months.**

---

## § COST SUMMARY (trading cost — ¢/turn and $/day, NOT tokens)

At p ≈ 0.85, $50/signal (58.8 shares), ~20 signals/day, $1,000/day deployed. **1¢ = $0.588/turn = $11.8/day.**

| Line | ¢/turn | $/day | Status |
|---|---|---|---|
| Gross edge (mid basis — **you cannot trade here**) | — | +$80 | measured, n=324/10d |
| Taker premium at fire | **−3.4¢** | **−$40** | measured, n≈20–22 |
| Fee — docs (`0.05×(1−p)`) | −0.6¢ | −$7.5 | **UNRESOLVED BAND** |
| Fee — on-chain @1000bps | −1.8¢ | −$20.8 | **UNRESOLVED BAND** |
| **NET, `take_at_fire` (the shipped default)** | | **+$19 … +$33** | the honest business |
| Prize A — maker leg fills at mid (no spread, **no fee**) | +3.4¢…+5.2¢ | **+$47 … +$61** | **UNKNOWABLE before Rung 2** |
| Prize B — `patient_take(15m)` | +2.8¢ | **+$33** | **p = 0.36 with a placebo. NOT ESTABLISHED.** |
| Cluster governor, heat-dome day | — | −$45 gross | buys **$800** of tail-risk removal |
| Slippage-EWMA false alarms (once armed) | — | **−$0.08** | negligible |
| Every piece of infrastructure in this plan (state machine, cage, policy layer, detectors, reconciler) | — | **$0** | it is all plumbing |

**The one-line summary of the whole cost model:** *the edge is 3–7¢ wide; the execution-cost band is 0–3.4¢; therefore execution policy alone can swing the result between "no edge" and "the whole edge" — and nobody has measured which. That is what this build is for.*

---

## § EXISTING INFRASTRUCTURE LEVERAGED (extend; do not rebuild)

| Piece | Path | Reuse |
|---|---|---|
| Order gate + latching kill-switch + de-levered Kelly | `copy-trading-bot/src/pilot.rs` | **EXTEND.** The 4-check funnel and the latch semantics are RIGHT. `KillSwitch` kept **verbatim** as the pure state machine. 6 of 8 tests untouched. Fill `:244`. |
| The hook (covers **both** lanes) | `cycles/consensus_cycle.rs:519` (and `hot_lane.rs`, same fn) | **HOOK HERE.** `state.id` is a free, stable idempotency root. One new non-blocking line. |
| Flag-gated **detached-spawn** pattern | `live.rs:225 / 252 / 271 / 475` — **never joined into the `select!` at :552** | **THE pattern.** Blast-radius isolation for free. |
| CLOB read client | `common/src/data/models.rs:321` `outcome_token_id()` | **Reuse** for `condition_id + outcome_index → token_id`, at the *signal* path. `ClobBook` (`:334-344`) is **bypassed**, not extended — the SDK's `order_book()` has bids and sizes. |
| Honest paper ledger (idempotent) | `migrations/031` + `consensus.rs:900-945` | **Reuse verbatim for booking.** `ON CONFLICT DO NOTHING` is the idiom to copy. Basis → `entry_ask_fire`. |
| At-fire ask capture | `feat/paper-executor` mig 042 | **ARM IT. Item 1. This is the basis.** |
| Live tape (WS, top-of-book, 72h, self-pruning) | `cycles/live_tape.rs` + mig 040 | Reuse for the ΔCLV close-mid and the `patient_take` counterfactual. **Fix the universe (Item 2).** ⚠️ **`last_size` is NOT a trade.** |
| Exec-policy evaluator | `feat/exec-policy` `common/src/storage/exec_policy.rs` | **Salvage `tape_quote_at()` (~:130) and the clock discipline. LEAVE `tape_maker_fill()` (:160-188). DO NOT MERGE mig 041.** |
| Cluster key | `scripts/superkey.py::super_event()` (:43) | **PORT.** When in doubt, merge; never split. |
| Cluster-robust day LB | `scripts/effective_n.py::cluster_robust()` (:95), `lb_at` (:123), `_t_ppf` (:75) | **PORT (~150 lines).** Written, self-tested. **Do not reinvent the statistics.** |
| Risk policy (declarative) | `reports/risk_policy.json` | Wire as the base profile under `exec_policy`. **λ̂ ≈ 0.15 < the 0.25 floor ⇒ the Kelly ladder SELF-VETOES TO FLAT. That is CORRECT BEHAVIOUR. Do not "fix" it.** |
| Fee sensitivity | `scripts/fee_schedule_sensitivity.py` | **Run it with the corrected rate table (sports 0.03 → 0.05) + an on-chain column. Item 3.** |
| Maker frontier sweep | `feat/maker-copy-g3` `scripts/maker_copy_g3.py` | The weekly learning-loop job, re-pointed at **our own real fills**. |
| **Official V2 CLOB SDK** | crates.io `polymarket_client_sdk_v2` **=0.6.0** | **THE `LivePlacer`.** Deps are an **exact match** (verified). L1/L2 auth, order build/sign/post, cancel-all, user-WS, book-with-sizes, tick size, neg-risk, fee rate, geoblock, **type-state auth machine**, remote signers (KMS). |
| On-chain fill ingestion (precedent for chain reads with zero crypto deps) | `cycles/live_fills.rs` (raw `eth_getLogs` over reqwest) | Enable to kill the p90=94min ingestion tail. **Data quality, NOT edge.** |

---

## § OPEN QUESTIONS — resolvable ONLY during implementation

| # | Question | WHEN it resolves | HOW |
|---|---|---|---|
| **1** | **What fee are we actually charged?** Docs say 5% (⇒ 0.75% of notional). Issue #326 reports `/fee-rate` returning `base_fee: 1000` (10%) for NBA/MLB — **no maintainer response, archived repo.** The on-chain formula gives ~2.08%. **A $13/day band on a $19–33/day net book.** | **Rung 2, day one.** | **THE $1 EXPERIMENT.** Place one $1 order; read `fee_rate_bps` off the trade event. **Possibly the highest-ROI single action in the project.** |
| **2** | **Does the maker leg fill at all, and is it adversely selected?** The entire "Prize A" ($47–61/day) rests on it. **It is UNKNOWABLE before Rung 2** — there is no trade tape, and every fill model this project has built has been wrong in the flattering direction. | **Rung 2.** | Enable the rest leg at **$1**, `post_only=true`. Measure `filled/(filled+expired)` and `trader_side`. Then `wr_filled` vs `wr_missed` — **the adverse-selection detector.** P&L is irrelevant; the ratio is the deliverable. |
| **3** | **Is `patient_take` real?** Point estimate +2.8¢ ($33/day). **The same intervention was measured at +2.05¢ ± 4.0¢, p = 0.36, and RETRACTED.** | **Phase 0.5 — BEFORE any executor code.** | Pure SQL on `clob_price_tape` + `consensus_signals`, **with a matched placebo arm of untraded markets** (the prior work's placebo drifted MORE). Gate: n ≥ 100 day-clusters **and** placebo-corrected p ≤ 0.05. |
| **4** | **Does ΔCLV have the power to police `weather_fav`?** P&L provably cannot (0.19σ < k). | **Phase 0.4 — BEFORE any executor code.** | The pre-registered falsifier: SNR ratio ≥ 2.0× at the **day-cluster** level, on the 395 historical signals via `fetch_price_history()`. **If it fails, say so and bound the loss instead of pretending to detect it.** |
| **5** | **Is `weather_fav` neg-risk?** A multi-city heat dome is exactly that shape ⇒ a **different exchange contract.** Wrong ⇒ **every weather order rejected.** | **Rung 2.** | Read it off `neg_risk(token_id)`. **Never assume.** |
| **6** | **What is the minimum order size?** No universal constant exists. **If it is $5, Rung 2 is $5/order, not $1.** | **Rung 2, day one.** | `OrderBookSummaryResponse.min_order_size`, per market. |
| **7** | **Is the GTD expiration actually honoured?** INV-2 (the orphan killer) depends on it. | **Rung 2, day one.** | Place one $1 GTD order below the market; confirm it disappears at expiry. **One $1 test of the single most load-bearing invariant.** |
| **8** | **What is our own market impact?** The $50 → +8.6% capacity number walks a **snapshot** book. **Real capacity is ≤ that, by an unknown amount.** | **Rung 2 → 3 boundary.** | `best_ask(T+60s) − best_ask(T−1s)` around our orders, vs a matched control of signals we did not trade. **Rung 3 does not unlock without it.** |
| **9** | **What are the real ICC / `cluster_expected_legs` values?** | **Phase 0, ~1 hour.** | Run `portfolio_concentration.icc_oneway()` on existing `honest_paper_ledger` history. Seed the table with **measured** values + n + CI in the `rationale`. |
| **10** | **What is the true slippage σ₀, at each size?** The two designers' estimates differ by **2.2×** and neither is measured. **The book-walk is size-dependent** (2.2¢@$50, 9.5¢@$250). | **Rung 2 (≥100 fills), then AGAIN at Rung 3.** | `slip_armed` stays FALSE until measured, and **returns to FALSE on every size change.** |

---

## § REJECTED APPROACHES (so nobody re-litigates them)

1. **Hand-roll a `clob-client` crate** (the brief's §4.1). **REJECTED.** ~3,000 lines of EIP-712 + secp256k1 + HMAC against an API replaced 11 weeks ago whose doc tree is currently 404-ing. Not a one-time cost — **a standing liability that silently rots**, whose failure mode is *every order rejected, discovered in production.* An official, maintained, MIT-licensed SDK exists and its deps are an **exact match** for this workspace. The repo's own law: **extend, don't rebuild.**

2. **`client_order_key` in the signed order's `metadata: bytes32`, hash-joined on reconcile** (the brief's I2; Designer A's central mechanism). **REJECTED — IT IS UNIMPLEMENTABLE, AND I VERIFIED THIS FROM THE SOURCE.** `metadata` appears in the SDK's order **builder** and in the `sol!` typehash. It appears in **`OpenOrderResponse`: NO. `TradeResponse`: NO. `OrderMessage`: NO. `TradeMessage`: NO.** *The exchange never echoes it back.* A UNIQUE column on our own table stops **us** from double-writing; it tells us **nothing** about whether **the exchange** has an order. **The brief's entire idempotency story rested on a field that does not exist.** Replaced by **single-flight-per-token (INV-1) + GTD-always (INV-2)** — which is *better*, because it makes reconcile-by-token **complete** and makes a forgotten order **expire on its own**.

3. **A separate executor PROCESS.** **REJECTED.** It buys isolation the codebase **already has** (`live.rs`'s detached-spawn slot: `dense_capture`/`live_tape`/`live_fills`/`hot_lane` are never joined into the `select!` at `:552`), at the cost of **a second deploy unit the autoupdater does not know how to deploy** — a *new* failure class (a stale executor against a fresh schema). **Chosen instead: a separate CRATE behind a cargo feature, in the same process, in the detached slot.** The crate boundary and the process boundary are different questions, and the codebase has been conflating them.

4. **Merging `feat/exec-policy` (mig 041) and its `maker_print` fill model.** **REJECTED, and 041 is retired permanently.** It books maker fills on `last_price`/`last_size` — which `live_tape.rs`'s **own comment** says is *"order-BOOK-LEVEL churn (not a trade)"*, and which is additionally **non-uniformly sampled** (excluded from the dedup key, keep-LAST coalesced). **It is the G2 bug wearing a new hat**, it biases in the flattering direction, and it writes into **the same table the certification gate reads.** Zero rows have accrued, purely by luck (the flag was never set).

5. **Designer A's DWELL fill model** (as a "fixed" replacement for `maker_print`). **REJECTED.** It is honest about being a model and it is an **optimistic UPPER BOUND** (it ignores queue position entirely). **An upper bound on the maker fill rate, published as a number, will be quoted as the fill rate.** That is exactly how two false "+4.8%" results happened. **An open question beats a biased answer — a bet this project has now lost four times in the other direction.**

6. **Designer A's "the arms diverge because of `p`, and here is the proof" (the router floor at 0.75).** **The DECISION is adopted; the PROOF is rejected.** A extrapolates the **+3.4¢ premium — measured on `favorite` at p≈0.85** — across the entire 0.45–0.90 range to conclude the router below 0.75 is untradeable. **The absolute spread is not constant across bands, and nobody has measured it below 0.75.** The fee leg (`feeRate × (1−p)`) is verified arithmetic; the spread leg is an extrapolation. **The floor is raised because it is the cheaper-to-be-wrong direction, not because the proof holds.**

7. **Designer A's P&L CUSUM (shadow until 40 day-clusters, then arm at H=5).** **REJECTED for `weather_fav`, at ANY n.** A's ARL₁ = 10.4 days is the detection time for a **1σ** decay — but a **total edge collapse** on weather is only a **0.19σ** decay, which at `k = 0.5` is **smaller than the reference value**, so the statistic drifts to zero and **the detector never fires.** **A fully-calibrated version of A's detector would never detect the failure mode it was built for.** (Lower `k` to 0.1 and ARL₀ collapses to 60 days — false-halting a healthy arm every two months while taking 27 days to catch a real break. **The false-alarm rate is 2.2× the true-detection speed.**)

8. **Designer B's "the placebo pool supplies σ₀ on day one."** **REJECTED AS STATED — but the CONCLUSION survives on a different argument.** `Var(Δ) = Var(clv_signal) + Var(placebo_mean) ≈ Var(clv_signal)`: averaging 200 controls shrinks the variance *of the control*, not of Δ. The placebo removes a **mean** confound (genuinely valuable), **not** the day-level σ₀ the CUSUM needs. **The real reason ΔCLV is calibratable and P&L is not: ΔCLV needs no fills, so it is computable RETROSPECTIVELY on 395 historical signals TODAY. Real-fill ROI has n = 0. That asymmetry — 395 vs 0 — is the whole argument, and it holds.**

9. **Designer B's `patient_take(15m)` as the DEFAULT and "the single largest number in this build" ($32/day).** **REJECTED AS A DEFAULT; ADOPTED AS THE #1 PHASE-0 EXPERIMENT.** ⚠️ **This exact intervention has already been measured, with a placebo, and retracted:** *"Latency (15-min delay): +2.05¢ ± 4.0¢, **p = 0.36**, n=20 vs 72 placebo. **RETRACTED as a lever. NOT significant. Placebo median drifts MORE.**"* **B cites the prereg §0 decay curve (n≈20–22, no placebo) and never reconciles it with the placebo-controlled measurement that killed it.** B's $32/day is a point estimate whose CI includes **zero and a loss**, from a design with **no control arm and no significance test** — **a direct violation of the project's own binding evidence rule, in a document that invokes that rule against everyone else.** It is not refuted; it is **not established**. **Phase 0.5 measures it properly (n ≈ 300, with a placebo). If it clears, it ships with one `UPDATE`.**

10. **Designer B's state machine without INV-4 (`Filled` terminal on a `TradeMessage`).** **REJECTED.** ✅VERIFIED: `TradeStatusType { Matched, Mined, Confirmed, Retrying, Failed }`. **A trade can FAIL after it MATCHES.** B's machine would **book P&L on a trade that never settled** — and, worse, could double-deploy if the budget were released on `FAILED` without a re-check. **Risk counts `MATCHED`; the ledger books only `CONFIRMED`.**

11. **Designer B's single-empty-read `Abandoned` transition.** **REJECTED.** The SDK has `OrderStatusType::Delayed` — **a POST can land and not yet be visible in `GET /orders`.** One empty read that abandons produces a **duplicate real-money position.** Replaced by Designer A's **two successful empty reads ≥120s apart**, plus the binding asymmetry: **we NEVER infer absence from a read FAILURE — a failed read HALTS.**

12. **A naive per-day stop-loss / P&L-based demotion on any arm.** **REJECTED.** Long losing streaks are the *expected* behaviour of a thin, day-clustered edge. **A detector that demotes a healthy arm is worse than no detector**, and because promotion is human-gated, **a false demotion is sticky.** P&L is the **confirmation**, never the **alarm**.

13. **"Latency as edge" / optimising the median decision time.** **REJECTED — already retracted** (+2.05¢ ± 4.0¢, p = 0.36). Optimise the **tail** (a bounded worst-case decision latency and a hard signal TTL), never the median (already 1.6 min). **Never sell speed as edge.**

14. **Rung 4 (scaled, $250/signal).** **PRE-REJECTED.** 9.5¢ slippage at $250 **exceeds the entire edge.** Turnover above capacity is negative EV. **Size is a risk, not a lever.** If Rung 4 is ever proposed, it must first defeat this number.

---

## § WHAT NEEDS TUE (the human gates)

1. **⚠️ THE ToS / JURISDICTION ANSWER — and it is a STANDING NO.** `DECISIONS.md` D26 (2026-07-03) records: *"Tue answered: live Polymarket deployment is off the table (US-person ToS)."* **Unless that has been explicitly revisited, RUNGS 2–4 ARE BLOCKED ON A HUMAN ANSWER, NOT ON ENGINEERING.** This blueprint says so rather than assuming it away. **Rungs 0 and 1 are unblocked, are ~90% of the code, and produce 100% of the evidence needed to know whether Rung 2 is even worth asking about. Build those.** The SDK's `check_geoblock()` exists: **read it, report it, obey it. Do not design around restrictions. Do not build evasion.**

2. **Arming.** Three independent locks, three separate human actions: the `live-exec` cargo feature, `PILOT_ARMED=1`, and a human `UPDATE executor_halts SET cleared_at = NOW(), cleared_by = 'human:tue'`. **There is no `unhalt()` method in the codebase. The absence of the method is the design.**

3. **The preconditions that start the clock — and the highest-value thing available today.** **Arm `CAPTURE_ENTRY_ASK_AT_FIRE` (Item 1) and fix the tape universe (Item 2).** Neither requires a line of executor code. **Backfill is impossible — every day the flag stays off is a day whose true realizable edge can never be known.** Do this first, alone, today.

4. **Every policy promotion.** The learning loop can only **propose** — it INSERTs an `exec_policy` row with `active = FALSE` and a mandatory `rationale`. **Tue flips `active = TRUE`.** The evidence bar never moves: **(a) a control/placebo arm, (b) a significance test, (c) explicit n + dispersion.**

5. **Two honest reports Tue must read and act on before any money moves:**
   - **The corrected fee sensitivity** (Item 3). Every ROI in this repo computed with `0.03·p(1−p)` — **including the +8.0% pooled and +5.2% LB headline** — is optimistic by an unquantified amount, and **the certification gate's pass/fail margin sits inside that error bar.** This is not a retraction; it **is** a hypothesis-not-a-result, and it changes what "certified" means.
   - **The Phase-0.5 `patient_take` result and the Phase-0.4 ΔCLV falsifier.** If either fails, **we say so plainly** — and, in the ΔCLV case, we state that *we cannot detect selection decay on weather in under ~2 months, and no proposed detector can. We bound the loss. We do not pretend to detect it.*

6. **Be willing to hear NO at Rung 2.** **If the frozen gate fails at the price we actually pay, the answer is RETIRE THE ARM, not re-analyse it.** This project has re-analysed four times and reversed sign twice.
