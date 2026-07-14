# US-EXEC-API-SEMANTICS — the verified write-path fact base

**2026-07-14, `feat/us-autotrader`. Phase 0 of RUN-US-AUTOTRADER.**

Every claim below is tagged. **VERIFIED** = read off `docs.polymarket.us` this session.
**UNVERIFIED** = asserted somewhere (brief, blog, third party) and *not* confirmed on the venue's own
docs — it may be true, but **no design may depend on it** until a live probe confirms it.
**REFUTED** = the brief or the intl plan assumed it; the venue's own schema says otherwise.

The prior US work (`US-API-SURFACE.md`, 62 probes) mapped the **read** surface. This maps the **write**
surface — the one that spends money. It exists because the run's law is: *verify the venue's real API
semantics before a single line of execution code.*

---

## 0. THE FOUR FINDINGS THAT CHANGE THE DESIGN

| # | Finding | Status | Consequence |
|---|---|---|---|
| **F1** | **There is NO client-order-id on the REST/gRPC order path.** `CreateOrderRequest` has no `clOrdId`. The canonical `Order` object (23 fields) has no `clOrdId`. | **REFUTED** (the brief's Phase-0 Q1 hoped US would give us server-side idempotency intl couldn't) | **US is NO better than intl on idempotency.** The intl cage's INV-1 (single-flight per instrument, enforced by a Postgres partial unique index) is **not optional here — it is the only mechanism we have.** Carry it over intact. |
| **F2** | **An IOC order that fills leaves NOTHING in `get-open-orders`.** It never rests; it is terminal on arrival. | **VERIFIED** (TIF semantics + order lifecycle) | **This INVERTS the intl reconcile.** Intl could reconcile a lost send by looking for a *resting* order on the token. On US, absence from open-orders proves **nothing at all** — a filled IOC and a never-arrived IOC look **identical** from the order side. ⇒ **Reconcile MUST be driven by TRADES/POSITIONS, never by open-orders.** See §4. |
| **F3** | **The auth signature does not cover the request BODY.** Signature = `base64(Ed25519(timestamp ‖ method ‖ path))`. | **VERIFIED** | Two consequences. (a) Any signed POST to `/v1/orders` is, within its 30s window, a valid signature for *a different order body*. (b) **The venue therefore cannot dedup our retries even in principle** — F1 has no back door. This hardens the "never retry a send blind" rule from a discipline into a physical necessity. |
| **F4** | **`cancel-all-open-orders` returns only `canceledOrderIds`. There is no `not_canceled` map.** | **VERIFIED** | A **regression vs intl**, where `CancelOrdersResponse.not_canceled` was the cancel-race signal *handed to us by the API*. On US we do not get it. The B3 cancel-race must be resolved **purely by event/reconcile**. (Mitigated: a take-only IOC book has no resting orders to race — cancel-all is only the kill-switch's belt.) |

**The net:** the brief hoped US would be *safer* than intl (clordId dedup + FAK dissolving the orphan
problem). **Half of that is true and half is backwards.** The orphan-*order* problem really does mostly
dissolve (F2, and it is a genuine win). But the orphan-*position* problem gets **strictly worse**, because
the one instrument intl used to detect it — a resting order you can go look for — **does not exist on an
IOC venue**, and there is no client key to join on (F1) and no way for the venue to dedup us (F3).

> **The single most dangerous object in this system is an IOC order whose HTTP response we lost.**
> It may have filled. It leaves no resting trace. It carries no key we chose. The venue will not dedup a
> retry. **The only evidence it ever existed is a trade/position delta — so that is what reconcile must read.**

---

## 1. AUTH — **VERIFIED**

- **Algorithm:** Ed25519.
- **Headers:** `X-PM-Access-Key` (Key ID) · `X-PM-Timestamp` (ms) · `X-PM-Signature` (base64) · `Content-Type: application/json`.
- **Payload:** `"{timestamp}{method}{path}"` → bytes → Ed25519-sign → base64.
- **Window:** timestamp must be within **30 seconds** of server time.
- **Keys:** created at `polymarket.us/developer`; Key ID + Secret (**shown once**); revocable immediately.

**Design consequences.**
1. **Clock skew is an availability risk.** >30s drift ⇒ 100% of orders rejected. Assert clock sanity at
   startup and treat a systematic 401-storm as `RejectStorm` ⇒ halt, never retry.
2. **Ed25519 is a ~15-line dependency (`ed25519-dalek`), not a crypto liability.** This is the decisive
   difference from intl: the intl plan rejected hand-rolling its client because EIP-712 + secp256k1 +
   a domain version that silently rots is ~3,000 lines of drifting crypto. **None of that applies here.**
   Signing `timestamp‖method‖path` with a fixed, standard, non-versioned algorithm is stable by
   construction. ⇒ **A hand-rolled Rust US write client is CHEAP and SAFE, and the intl plan's "use the
   SDK, never hand-roll" reasoning does not transfer.** (Official SDKs are **Python + TypeScript only —
   there is NO Rust SDK.** **VERIFIED.**)
3. **The key is the whole account.** One crate, off by default, never logged, never committed.

---

## 2. ORDER PLACEMENT — **VERIFIED**

`POST /v1/orders` — `CreateOrderRequest`:

| Field | Meaning |
|---|---|
| `marketSlug` | **required** — the instrument. *(US identifies by SLUG, not by a token_id.)* |
| `type` | `ORDER_TYPE_LIMIT` \| `ORDER_TYPE_MARKET` |
| `price` | `Amount` — required for limit |
| `quantity` | contracts; decimals allowed |
| `tif` | see below |
| `intent` | `ORDER_INTENT_BUY_LONG` \| `SELL_LONG` \| `BUY_SHORT` \| `SELL_SHORT` (or `outcomeSide`+`action`) |
| `goodTillTime` | for GTD |
| `participateDontInitiate` | **post-only** (maker-only; rejects immediate matches) |
| `cashOrderQty` | market orders, in $ instead of contracts |
| `synchronousExecution` | **block until filled/rejected/canceled** |
| `maxBlockTime` | max block, seconds |
| `slippageTolerance` | `bips` \| `ticks` \| `currentPrice` (market/close orders) |
| `manualOrderIndicator` | `MANUAL` \| `AUTOMATIC` — **we are AUTOMATIC. Declare it honestly.** |

**`CreateOrderResponse`:** `id` (exchange order id) + `executions[]` (**only if `synchronousExecution=true`**).

**Time-in-force — VERIFIED, and the brief's "FAK" is not a literal value:**

| TIF | Semantics |
|---|---|
| `TIME_IN_FORCE_IMMEDIATE_OR_CANCEL` | **IOC** — fill what's available now, cancel the rest. **Partial fills possible.** ← *this is the brief's "FAK"* |
| `TIME_IN_FORCE_FILL_OR_KILL` | **FOK** — all-or-nothing, no partials |
| `TIME_IN_FORCE_DAY` / `GOOD_TILL_CANCEL` / `GOOD_TILL_DATE` | resting orders — **we never use these** |

> **INV-2 (US form): every order is `ORDER_TYPE_LIMIT` + `IOC` or `FOK`. A GTC/GTD/DAY row is a bug.**
> Enforced by a schema `CHECK`, exactly as intl enforced `no_gtc`.

**Never `ORDER_TYPE_MARKET`.** The backtest assumed *ask + 0.5¢*. A market order accepts an unbounded
price. **The executor computes a max price it will pay and submits a LIMIT IOC at/under it; if the book
has moved past the cap, it SKIPS. It never chases.** (`slippageTolerance` is not a substitute — it is a
server-side convenience whose reference price we do not control.)

**IOC vs FOK is a real, open design choice** (see §6, Q1) — IOC risks a partial (we own less than we sized,
which perturbs cluster accounting); FOK risks no fill at all (we skip more). Not yet decided.

---

## 3. FEES — **VERIFIED, and the invariant is satisfiable**

The canonical `Order` object carries:
- `commissionNotionalTotalCollected` — **the realized fee, in notional, collected by the venue**
- `commissionsBasisPoints`, `makerCommissionsBasisPoints`
- plus `cumQuantity`, `avgPx`, `leavesQuantity`, `state`

⇒ **"Read the fee off the exchange, never model it" (cage invariant I8) is ACHIEVABLE on US.**
Realized P&L charges `commissionNotionalTotalCollected`. `scripts/us_fees.py`'s `Θ·C·p·(1−p)` model
survives **only** as the *pre-trade EV estimate*, and is **removed from the realized path** — exactly the
`realizable_pnl_modeled` / `realized_pnl` split of intl Item 4.

`preview_order` (`POST /v1/orders/preview`) returns a full `Order` including **`avgPx`, `cumQuantity`, and
the commission fields** — i.e. **a pre-trade quote of the exact fill and the exact fee, with no side
effects on the book.** This is a genuinely better safety primitive than intl had. See §6, Q2.

⚠️ **The `Order` object has NO per-execution `fills[]` array** — only aggregates (`cumQuantity`, `avgPx`).
Individual executions come from the **private WS** exec events (`execId`, `tradeId`, `lastShares`, `lastPx`,
`execType`) and from `POST /v1/report/trades/search`. **The per-fill fee field is NOT confirmed on either.**
⇒ **OPEN: fee attribution is confirmed at the ORDER level, not yet at the FILL level.** For a take-only
IOC book — where one order is one immediate execution event — the order-level aggregate **is** the fill,
so this is very likely sufficient. **It must be confirmed on the first live order, not assumed.**

---

## 4. RECONCILE — the US shape, and why it is NOT intl's

**Private WS — VERIFIED.** `wss://api.polymarket.us/v1/ws/private`, authed. Channels:
- **Orders** — lifecycle events (new / filled / canceled)
- **Order Snapshot** — all open orders on subscribe, terminated by an **EOF flag**
- **Positions** — before/after net position, cost basis, entry type
- **Account Balance** — before/after, buying power

Exec events carry: `execId`, parent order, `lastShares` (string), `lastPx`, `execType`, `tradeId`.

**Order states — VERIFIED:** `PENDING_NEW`, `NEW`, `PENDING_REPLACE`, `PENDING_CANCEL`, `PENDING_RISK`,
`PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `REPLACED`, `REJECTED`, `EXPIRED`.

> **⚠️ THE INVERSION (F2), stated as a rule.**
> **Intl:** a lost send left a *resting GTC* ⇒ `orders(asset_id=T)` finds it ⇒ adopt. Absence (on two reads
> ≥120s apart) ⇒ `Abandoned`.
> **US:** a lost IOC send leaves **no resting order in either case.** `get-open-orders` returns empty
> whether it **filled** or **never arrived**. **The order side carries ZERO information.**
> ⇒ **The US reconciler reads POSITIONS and TRADES, not open orders.**
> - `POST /v1/report/trades/search` (filters: symbols, accounts, date ranges, order states) — the audited
>   REST backstop.
> - `GET /v1/positions/...` + the position ledger (`quantityChange`, `netPosition`, `costChange`, `realized`).
> - The private-WS **Positions** channel — the live feed.
> **The question reconcile asks is not "is my order there?" It is "did my position change?"**
> `get-open-orders` is retained for exactly one purpose: proving the book is clean (no resting orders) —
> which, under INV-2, must **always** be true, and any resting order is itself an alarm.

**Position snapshot on connect is the truth anchor.** On every startup, before a single order may be sent:
subscribe, take the position + order snapshot to EOF, compare against our ledger. Divergence ⇒ **HALT**.
A position we cannot explain is `OrphanPosition` — the loudest halt in the system (intl INV-3, unchanged).

**And the deliberate asymmetry survives verbatim from intl:** a read that **ERRORS** ⇒ **HALT**.
We conclude "the order never arrived" **only** from *successful* reads that came back clean, twice,
≥120s apart. **We never infer absence from a failure.**

---

## 5. REJECTS, LIMITS, AND THE 5-SECOND STOPGAP

- **Rate limit — VERIFIED:** **20 requests/second per API key**, enforced at the edge (Cloudflare),
  `429 Too Many Requests` on breach. *(Note: far tighter than intl's 5,000/10s. We fire ~tens of orders/day
  — three orders of magnitude under it. But the **kill-switch's cancel-all must still fire once and latch,
  never spin.**)*
- **The 5-second stopgap — UNVERIFIED on the venue's own docs; corroborated by a third-party rate-limit
  guide.** The claim: *during elevated latency, an order not processed within 5s is rejected to protect
  against fills at stale prices, and the reject carries the message **"Global Rate Limit Exceeded"** — which
  is **NOT** a real rate limit and **must not** be backed off on.*
  **Treat as PROBABLY TRUE and design for it, but do not trust the string.** The policy:
  - It is a **REJECT** — the exchange *answered*. ⇒ it maps to `PlaceError::Rejected`, the **SAFE** branch.
    No order exists. This is the good case and it needs no reconcile.
  - **Do NOT exponential-back-off on it** (that is the trap the message sets).
  - **Do NOT blind-retry it either.** It is a *stale-price* reject: by definition the book moved. The
    correct response is **re-decide from a fresh book, or skip.** Re-sending the same limit price into a
    market that just told us it is too slow to price it is exactly how you get filled at a bad price.
  - **A storm of them ⇒ `RejectStorm` ⇒ halt the arm.** Structural, not transient.
  - ⚠️ **The string is our only discriminator between a real 429 and a stopgap reject, and it is
    load-bearing. CONFIRM IT ON A LIVE ORDER before it governs a dollar.** If we cannot distinguish them,
    **fail closed: treat an ambiguous 429 as a halt-worthy reject, not as "retry later".**

---

## 6. OPEN QUESTIONS — resolvable only with the key / a live order

| # | Question | Why it matters | How it resolves |
|---|---|---|---|
| **Q1** | **IOC or FOK?** | IOC ⇒ partial fills ⇒ we own less than we sized (perturbs cluster budget + slippage stats). FOK ⇒ no partials, but a higher skip rate, and **FOK against a thin book may skip constantly.** | Decide in design (§ red-team). Measure the partial-fill rate at micro-real. **Leaning FOK for the first live orders** — it makes "what did I get?" unambiguous while we are proving the plumbing — then IOC once accounting is trusted. |
| **Q2** | **Preview before every order, or only near the cap?** | `preview_order` gives the exact expected `avgPx` + fee with no book side effect — a cheap, strong pre-trade check. Cost: one extra request (20/s limit is not binding) and **latency**, and a preview is *stale by the time the real order lands*. | Preview is a **validation**, never a **guarantee**. Design: preview at micro-real for plumbing truth; decide at ramp whether it earns its latency. |
| **Q3** | **Is the per-FILL fee readable, or only per-ORDER?** | I8 ("never model the fee") depends on it. Order-level is confirmed; fill-level is not. | Read `commissionNotionalTotalCollected` off the order after the first live fill; cross-check against `report/trades/search`. **If they disagree, HALT and re-derive.** |
| **Q4** | **Does the "Global Rate Limit Exceeded" string really mean the 5s stopgap and not a 429?** | We must not back off on it, and must not confuse it with a real limit. | First live order under load. Until confirmed: **fail closed.** |
| **Q5** | **Minimum order size / tick size, per market?** | Wrong ⇒ every order rejected. Intl's lesson: **never assume.** | Read off the market object / a $1 probe. |
| **Q6** | **Does `synchronousExecution` change the indeterminate-send picture?** | If the server blocks until the order is terminal and returns `executions[]`, a **successful** sync response is *self-reconciling*. But a **lost** sync response is **worse** — a longer window in which the order landed and we don't know. | Test at micro-real. **Do not adopt sync execution as a safety mechanism without proving the timeout path.** |

---

## 7. WHAT CARRIES OVER FROM THE INTL CAGE, UNCHANGED

The invariants are law and the venue does not weaken any of them:

- **The exchange is the only source of truth.** HTTP 200 is a hint. State advances on a venue event or a
  reconcile read. — **unchanged.**
- **Never retry a send blind.** `Indeterminate` ⇒ state stays `SENT`; reconcile owns it. **F1 + F3 make
  this stronger on US than on intl** (no key, no server-side dedup).
- **A failed read HALTS.** Never infer absence from a failure. — **unchanged.**
- **INV-1 single-flight per instrument, enforced by Postgres.** — **unchanged, and now load-bearing**,
  because F1 removed the alternative.
- **INV-4 two-phase settlement.** Intl: `MATCHED` (off-chain) → `CONFIRMED` (on-chain), and a trade can
  **FAIL after it matches**. US is a CFTC-regulated central book with no chain leg — **so INV-4 may
  genuinely not apply.** ⚠️ **But this is exactly the kind of "the new venue is simpler" assumption that
  costs money. Until a live fill proves the state machine has no post-match failure mode, keep the
  MATCHED/CONFIRMED split and let it collapse to a no-op.** Cheap to keep; expensive to have been wrong about.
- **Default-OFF at three independent locks; the kill-switch latches; a restart is not an un-halt.** — **unchanged.**
- **Size the GAME, not the market.** — **unchanged.**

## 8. WHAT IS GENUINELY BETTER ON US

1. **No resting orders ⇒ the orphan-GTC catastrophe (the single worst failure in the intl plan) mostly
   dissolves.** Real, and it is the biggest safety win of the venue swap.
2. **`preview_order`** — a pre-trade fill+fee quote with no side effects. Intl had nothing like it.
3. **Ed25519 over a fixed payload** — a stable, tiny, non-rotting crypto surface. No EIP-712 domain to drift.
4. **Fees are a first-class field on the Order**, not an on-chain formula argued about in four documents.
5. **A regulated venue with a real audit trail** (`report/trades/search`, the daily regulatory CSVs) — an
   independent backstop for reconcile that intl simply did not have.

**And what is genuinely worse:** F1 (no client order id), F2 (a lost IOC is invisible from the order side),
F4 (no `not_canceled` cancel-race signal), and a **20 req/s** ceiling. **None of these are fatal; all of
them must be designed for rather than discovered.**
