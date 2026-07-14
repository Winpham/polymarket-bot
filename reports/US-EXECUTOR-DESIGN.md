# US EXECUTOR — THE DESIGN (the synthesis that governs the build)

**2026-07-14, `feat/us-autotrader`.** Inputs: `US-EXEC-API-SEMANTICS.md` (verified facts),
`US-EXECUTOR-FORGE-DEBATES.md` (two designs + nine adjudications), a red-team pass, and
`US-EDGE-EVIDENCE-AUDIT.md` (what the edge is actually worth). `EXECUTOR_FORGE_PLAN.md`'s invariants
are **law**; this document carries them onto a different machine.

> **THE ONE-LINE POSTURE.** The cage is sound. **The EDGE is weaker than advertised and the EXIT was never
> designed.** Rungs 1–3 place zero orders, need **no API key** (the US book is public — verified), and
> produce 100% of the evidence that decides whether a real order should ever exist.

---

## 0. THE SHAPE

```
consensus_cycle.rs:523  ──(bounded mpsc, non-blocking; a full channel DROPS the signal)──►
   ┌──────────────────────────────────────────────────────────────────────────────────┐
   │ us-exec  (NEW Rust crate · cargo feature `us-live-exec` · DEFAULT OFF)            │
   │                                                                                   │
   │  run_decider     signal → map → band/WC/TTC → FRESH public /book → cap → depth    │
   │                  → cluster budget → DECIDED → (send) → SENT                       │
   │  run_listener    the authed private WS. INDEPENDENT — a wedged decider            │
   │                  cannot lose a fill.                                              │
   │  run_kill_watch  own DB conn, own placer, NO shared lock. 2s poll. Fail-closed.   │
   └──────────────────────────────────────────────────────────────────────────────────┘
        three DETACHED tokio::spawn at live.rs:508 — NOT in the select! at :552
        (that select joins 5 handles and the FIRST TO EXIT KILLS THE PROCESS)
        off ⇒ never spawned ⇒ the binary is BYTE-IDENTICAL
```

**Why Rust, in-process, not a Python sidecar** — this is deploy topology, not taste, and every link is
verified: `consensus-autoupdate.sh:40`'s `CODE_RE` **excludes `scripts/`** ⇒ a Python sidecar **never
deploys**; the compose stack has **only** `postgres` + `copy-trading-bot`; `us_keepalive.sh`'s own header
says *"NOT a launch unit: nothing schedules this."* **A Python executor would be an unsupervised,
undeployed, stale binary running against a freshly-migrated schema — while holding a private WS and a
real-money key.** The intl plan rejected a second deploy unit for weaker reasons than these.

**Ed25519 is a ~15-line dependency**, not intl's 3,000-line EIP-712 liability — a fixed, unversioned
payload that cannot rot. There is **no Rust SDK** (Python/TS only). Hand-rolling here is cheap and safe,
and the intl "never hand-roll" rule does not transfer.

---

## 1. THE INVARIANTS (law; each names the failure it prevents)

| | Invariant | Prevents |
|---|---|---|
| **INV-1** | **Single-flight per instrument, enforced by Postgres** — `UNIQUE INDEX ON us_exec_orders(us_slug) WHERE state IN ('DECIDED','SENT')` | F1 denies us a join key; **uniqueness manufactures one.** If at most one of our orders can be outstanding on slug S, then **any unattributed trade on S in the send window IS that order.** Reconcile-by-slug becomes *complete*. |
| **INV-1b** | **`UNIQUE(signal_id)` — one signal, one decision, FOREVER.** A skip is a decision. **There is no retry path.** | The duplicate-position generator. A lagging position feed ⇒ a false `ABANDONED` ⇒ a retry ⇒ **two real positions**. Under this index that path **does not exist**. Worst case degrades from *"a duplicate position"* (unbounded) to *"we missed one trade"* ($0 at ~3 events/day). |
| **INV-2** | **Nothing rests.** `CHECK (order_type='LIMIT' AND tif IN ('IOC','FOK'))`. A GTC/GTD/DAY row is a bug. | The orphan-GTC catastrophe — the intl plan's single most-feared failure. **Genuinely dead on US, and it is the real prize of the venue swap.** |
| **INV-3** | **A position we cannot explain is the loudest halt in the system.** | We own shares we cannot explain ⇒ either a second instance is running or our key scheme is broken. Both unbounded. |
| **INV-4** | **RISK counts `FILLED`. The LEDGER books `RECONCILED`** (an *independent* read confirms it). | Booking P&L on a trade the venue later unwinds — **and the drawdown latch reads our ledger.** The `RECONCILED` state is also the hook where the venue's fee is cross-checked against `report/trades/search`. |
| **INV-5** | **The exchange is the only source of truth.** HTTP 200 is a hint. **Never retry a send. Never infer absence from a failed read — a failed read HALTS.** | F1+F3: **the venue cannot dedup our retries even in principle.** |
| **INV-6** | **Fees and fills are READ, never modeled.** `commissionNotionalTotalCollected` off the Order. | Four documents arguing about a fee. |

---

## 2. THE STATE MACHINE — 8 states; exactly ONE is dangerous

```rust
pub enum UsOrderState {
    Decided,     // committed to DB. Nothing sent.                          (B1)
    Sent,        // POST in flight, OR its response was lost. ⚠️ THE ONLY DANGEROUS STATE. (B2)
    Filled,      // the venue says it traded. RISK COUNTS THIS.
    Reconciled,  // TERMINAL. An INDEPENDENT read confirms it. THE LEDGER BOOKS THIS.
    Rejected,    // TERMINAL, SAFE. The venue answered "no". No order exists.
    NoFill,      // TERMINAL, SAFE. Accepted, filled ZERO (IOC/FOK cancelled out).
                 //   ⚠️ THE NORMAL NO-FILL. Not an error. Conflating it with Rejected
                 //   would fire RejectStorm on a quiet book and halt a healthy arm.
    Abandoned,   // TERMINAL. Reconcile PROVED the venue never got it.
    Skipped,     // TERMINAL AT BIRTH. skip_reason NOT NULL. An honest, recorded abstention.
}
```

**Deleted (each proven unreachable):** `LIVE`, `CANCEL_REQ`, `EXPIRED`, `leg`, `attempt_seq` — all rest on
**F2: an IOC/FOK is terminal on arrival.** And the entire maker/policy family, because UV-6/7/9/10
**measured it dead on US** with 7,049 real maker fills (net maker `+0.014¢, CI [−0.54,+0.09]`).

### The send boundaries

| | Handling |
|---|---|
| **B1** crash after `DECIDED`, before the POST | We write `sent_ts` **before** the POST. So `sent_ts IS NULL` **proves** the POST never started ⇒ `ABANDONED`. **Fail closed.** |
| **B2** ⚠️ **response lost inside the POST** | **THE most dangerous object in the system.** It may have filled; it leaves **no resting trace** (F2); it carries **no key we chose** (F1); **the venue will not dedup a retry** (F3). ⇒ state stays `SENT`; **reconcile owns it**; a retry is **physically impossible** (INV-1b makes it a `23505`). Unresolved > **300s ⇒ HALT the arm.** |
| **B3** cancel/fill race | **PROVEN GONE.** Nothing rests ⇒ we issue no per-order cancels ⇒ **F4's missing `not_canceled` map costs us nothing.** We designed the race out rather than detecting it. |
| **B4** partial → re-quote → double | **PROVEN GONE.** No re-quote, by policy. Under FOK, no partials at all. |
| **B5** ⚠️ **US-only** | **`synchronousExecution = FALSE` at every rung.** It converts a fast indeterminate into a **slow** one, and under INV-5 its `executions[]` would still need confirmation ⇒ **it buys nothing while lengthening B2.** |

**FOK, not IOC, for every live rung.** It turns the reconcile predicate from an inequality
(`0 ≤ Δpos ≤ size`) into an **equality** (`Δpos ∈ {0, size}`). **An equality has no tuning parameter to get
wrong**, and on a venue where the position delta is the *only* evidence an order existed, that is worth
more than a few extra fills. It is also free: the depth gate already requires what FOK requires.

---

## 3. RECONCILE — position-driven, because F2 left us nothing else

> **Intl asked: "is my order there?" US asks: "DID MY POSITION CHANGE?"** — the only question with an answer.

- **Read the position LEDGER (deltas), never the snapshot.** A snapshot says *what I own*; only a ledger
  says *what CHANGED and WHEN* — and **only a delta is attributable** when we may already hold a prior
  position in the same slug. (Intl never faces this; F1 took its `taker_order_id` join away.)
- **`get-open-orders` is NOT a reconcile input.** Under INV-2 it must **always** be empty. **Any resting
  order is itself an alarm** (`OrphanOrder` ⇒ MASTER HALT). **On intl a non-empty cancel list is normal; on
  US it is an ALARM.** That inversion is free and it is the belt that makes the deletions safe.
- **The three-way tie-out:** private WS (live) · `report/trades/search` (audited) · **Time & Sales**
  (statutory). ⚠️ **NOT the DMR for fills** — red-team F6, confirmed: the DMR's offer and trade-price
  columns are **identically zero** even on rows with volume. **The DMR's role is SETTLEMENT ONLY**, and
  only once `settlement_price ∈ {0,1}`.
- ⚠️ **SETTLEMENT IS NOT AN ORPHAN.** Intl positions redeem on-chain; **US positions SETTLE.** Our ledger
  and the venue's will **legitimately diverge every settlement window.** A naive *"venue == ours, else
  HALT"* check **halts every single day.** **A cage that cries wolf gets disarmed by its owner.**
  ⇒ settlement is recognized via the venue's own `realized` ledger field; **until that shape is CONFIRMED
  with a key, we HALT on divergence and resolve BY HAND** (tractable at ~3 events/day, and it is how we
  learn the shape **without guessing**).

**The boot gate — no order may be sent until every step is green** (the autoupdater recreates the
container on **every merge to main**, so this path runs constantly):
`clock skew ≤5s` → `order snapshot has no RESTING order` → `position snapshot == our ledger` →
`resolve every non-terminal row` → `replay the fills through KillSwitch::on_fill` → `read the halt latch`.
**A read that ERRORS at any step ⇒ HALT. We never boot into trading on a failed read.**

---

## 4. THE CAGE

**Four independent default-OFF locks.** Each is a separate human action; **a merge cannot arm trading.**

| # | Lock | Off state |
|---|---|---|
| **0** | **THE KEY** *(US-only, and better than anything intl has)* | absent ⇒ the placer is `PaperPlacer` regardless of locks 1–3. **And Tue can REVOKE it from a phone in 30 seconds** — an out-of-band kill that works even if the machine is compromised. Revoking an intl EOA key is *impossible*. |
| **1** | **Compile** | `us-live-exec` OFF ⇒ the live placer **does not exist in the binary**. Enforced by the linker. |
| **2** | **Spawn** | `US_EXEC_ENABLED=false` ⇒ the three tasks are never spawned ⇒ **byte-identical**. |
| **3** | **Runtime latch** | `us_exec_halts` seeded **`MasterOff` by migration 049** ⇒ **HALTED FROM BIRTH.** **There is no `unhalt()` method. The absence of the method is the design.** |

⚠️ **THE COMPOUNDING HAZARD: a container recreate IS a kill-switch reset, and merging the executor is the
very event that erases its halt state.** ⇒ **`us_exec_halts` ships in the SAME PR that wires the executor.
Not the next one. The same one.** Non-negotiable.

⚠️ **THE HALT NAMESPACE MUST BE `(venue, arm)`.** The intl paper arm and the US executor **both trade an
arm named `favorite`.** A halt written by one would silently halt — or silently fail to halt — the other.
**A namespace collision in a kill-switch is exactly the bug that reads as "the kill-switch didn't fire."**

### ⚠️ 4b. THE EXIT — the shared blind spot. Neither designer wrote one. **Decided here.**

> **`cancel-all` on a take-only book is a NO-OP. There is nothing resting to cancel.**
> **The kill-switch's only real power is REFUSING TO SEND.**
> ⇒ **Maximum exposure after a halt request = ONE in-flight order, at the per-signal cap.** Bounded,
> quantified, and **unfixable by any cancel design.** A drawdown breaker that cannot cut a position is a
> **logger**, and it must be described as one.

**DECIDED: HALT = STOP OPENING. WE NEVER FLATTEN.** Flattening a 0.92 favorite means selling into the bid
— paying the ~1¢ spread **plus the taker fee again**, ≈**1.5% of notional per halt** — on a position whose
expected ROI is +5.4%, in a system **designed to halt often.** **Delete "flatten" from the brief.**
Positions are **held to settlement.** `close_position` exists and is **not used** by the executor; it is a
**manual, human-only** tool.

**Two consequences that must be built, not assumed:**
1. **P&L — and therefore every breaker — is BLIND for ≥1 day**, because settlement lands on the DMR at
   T+1. **The day-stop, the max-drawdown latch, and the loss-count monitor all see nothing until
   tomorrow.** ⇒ **risk reads an INTRADAY MARK (the venue's position feed), the settled ledger is the
   AUDIT.** This is INV-4's RISK/LEDGER split, **extended to the exit side.**
2. **Open exposure is bounded EX ANTE — per-signal cap × cluster budget × daily cap — never detected ex
   post by a drawdown calc.** With multi-day settlement lockup, positions accumulate across days, so the
   **total-open cap is the binding control** and it must have a number.
3. **Void / postponed contracts** lock capital indefinitely and can never be retired by the reconciler.
   **At ~3 events/day this will happen within the first month.** Needs an explicit `VOID` path.

---

## 5. RISK

- **Size the GAME.** `super_event` (port `scripts/superkey.py:43`). **fcfs — ONE order per event.**
  **When in doubt MERGE clusters, never SPLIT** (a merge over-constrains = safe; a split over-deploys).
  ⚠️ **This CHANGES THE STATISTICS**: one order per event ⇒ `n(picks) = n(events)` ⇒ **it is why the
  certified +6.78% is really +5.40%** (see the evidence audit).
- **NO KELLY.** At p≈0.925 the `(1−p)/r_win` term is a ratio of two small numbers: `f*` swings **10% → 65%
  — a 6.5× swing from a 4pp move in an input we barely know.** **A parameter that amplifies its own
  uncertainty by 6.5× has no place in a system whose defining failure is parameters that turned out
  wrong.** ⇒ **flat, hard, per-signal dollar cap, ratcheted by rung.**
- **ALL SIZING USES THE LOWER BOUND**, never the point estimate, and **never the brief's "+16.70%"** —
  which is a **different, World-Cup-inclusive sample** and overstates the traded rule by **~3×**.
- **Capacity is RE-MEASURED on US.** Intl's $50–250/signal **does not transfer.** The **depth gate is the
  real capacity control**; `size_cap_usd` is only an outer bound. **$50 is a hard ceiling** pending a new
  pre-registered capacity test.
- **Halts:** `DayStopLoss`, `MaxDrawdown`, `RejectStorm`, `DataStale`, `ReconcileFailed`,
  **`OrphanPosition`** (loudest), **`OrphanOrder`**, **`PhantomPosition`**, **`ClockSkew`**,
  **`MapperBasis`**, **`SettlementMismatch`**, `MasterOff`. All latching, all in the DB, all surviving a
  restart.

---

## 6. THE MAPPER — the highest-consequence bug class, and it has no intl analogue

On intl, instrument resolution is a **pure in-memory function**: it can only be **absent** ⇒ we skip.
On US it is a **fuzzy title matcher**: it can be **WRONG** ⇒ **we buy the wrong instrument, confidently,
with real money — reconcile ties out perfectly, and the loss looks like variance.** **A mis-map does not
lose the edge; it INVERTS it.**

**Four controls, all mandatory:**
1. `mapper_conf ≥ 0.90` as a **schema `CHECK`** — a low-confidence row **cannot exist**.
2. **The basis guard:** `|us_mid − intl_implied| > 0.10 ⇒ SKIP`. An *independent, numeric* check. *(10¢ ≈
   1.7sd of the measured basis. **HYPOTHESIS — calibrate against `cross_venue_basis` before it governs a
   dollar.**)*
3. **A human-reviewed allowlist to trade:** `us_market_map.reviewed_by IS NOT NULL`. At ~3 events/day the
   universe is small. **Costs nothing; kills the class.**
4. **The post-settlement cross-check:** assert `us_settlement == intl_outcome_won` on every traded pair.
   **A disagreement is a mapping error that has already cost money ⇒ MASTER HALT + retire the pair.**

> ✅ **AND IT NOW HAS EVIDENCE:** with the settlement fixed to terminal-only, the US settlement and the intl
> resolution **agree on 100% of ~2,100 historical picks.** The mapper validates clean against an
> independent source. *(This is a floor, not a guarantee — the mapper runs on titles, and titles change.)*

---

## 7. THE RUNG LADDER

| Rung | Capital | Key? | Entry gate |
|---|---|---|---|
| **0 — SHADOW** | $0 | ✗ | *(default)* Decisions logged; nothing sent. **Measures the POST-GATE event rate** (which GATE A's calendar expectation depends on). |
| **1 — PAPER** | $0 | ✗ | R0 ≥7 days, every `skip_reason` populated. Deterministic FOK fill on the **real** book. **Accrues the GATE-A forward track.** |
| **2 — CAGE** | $0 | ✗ | State machine + reconciler + kill-watch, exercised against a **fault-injected** placer. **The crash-restart drill passes: SIGKILL mid-send, restart, reconcile correctly ABANDONS — proven by an automated test, not by hope.** |
| **GATE A** | — | ✗ | **≥115 events AND ≥30 days AND the pre-registered test CLEARS.** Tue reviews. **FAIL or INDETERMINATE ⇒ stay at $0.** |
| **3 — PREVIEW-ONLY** ⭐ | **$0** | ✓ | GATE A cleared + key + clock assert + WS connects + snapshots EMPTY. **Not one dollar can move — `preview_order` has no side effects.** Closes the fee question, tick/min-size, and the **paper-vs-preview cross-check that breaks the shared-mode failure.** **Intl could not offer this rung.** |
| **4 — TINY-REAL** | **$5/signal** | ✓ | R3 exit + funded + **Tue's explicit go-live. First 10 orders require Tue's per-order confirmation.** ⚠️ **And the test nobody proposed: DELIBERATELY INDUCE THE INDETERMINATE SEND — `docker kill` mid-POST, on purpose, and prove reconcile adopts the fill. B2 is the only dangerous boundary; exercise it ON PURPOSE at $5 before it happens BY ACCIDENT at $50.** |
| **5 — RAMP** | $5→$10→$25→**$50 ceiling** | ✓ | One step per ≥30 fills at the current size, slippage EWMA in-band, event-clustered ROI LB > 0. **`slip_armed` returns to FALSE on every size change** (the book-walk is size-dependent). |

**Demotion is automatic and instant. Promotion is evidence-gated and human.** A false demotion is
therefore **sticky** — which is why every detector ships in **shadow** until calibrated on real data, and
why **the mechanical cage, not the statistics, is the arm's real protection for the first two months.**

**The primary detector is the LOSS COUNT, not P&L.** The edge *is* a loss-rate effect; a 1-loss-in-41
process emits almost no P&L information per day. *(The same mathematics that made intl's P&L CUSUM
structurally incapable of firing on `weather_fav`.)*
**ΔCLV is LOG-ONLY and never demotes**: intl could calibrate `σ₀` on 395 historical signals; **Polymarket
US publishes no price history at all**, so a US ΔCLV detector has **n=0** and cannot be calibrated at any
price. Deleting it would be wrong; **arming it would be worse.**

---

## 8. OPEN — fail-closed until answered. **No design clause depends on any of these.**

| # | Question | Posture until answered |
|---|---|---|
| **O1** | Does a US IOC transit through `PENDING_NEW`/`NEW`? *(The venue's state enum has both.)* | ⚠️ **The single most likely place this state machine is wrong.** If it does, a restart mid-flight finds a non-empty snapshot and a naive boot gate **MASTER-HALTS a perfectly healthy order** — a self-inflicted halt on every unlucky deploy. ⇒ **the boot assertion is "no order in a RESTING tif", NOT "the snapshot is empty"; a `NEW` order on a slug we hold a `SENT` row for is ADOPTED, not halted on.** **If F2 is softer than the docs imply, `LIVE` comes back.** |
| **O2** | The **position-feed LATENCY**. | Every safety property reduces to *"the position delta arrives promptly."* If it lags >120s, the two-read grace manufactures a **false ABANDONED** (harmless under INV-1b — but it still **costs a false halt**). ⇒ **R4 must MEASURE the latency distribution; the 120s grace and 300s halt are RE-SET from it. Until then every number in §3 is a HYPOTHESIS.** |
| **O3** | Is the **per-FILL** fee readable, or only per-ORDER? | Order-level is VERIFIED. **Cross-check against `report/trades/search` on the first live fill. Disagree ⇒ HALT and re-derive.** |
| **O4** | Can a write-`429` follow *acceptance*? | Treat every write-429 as **`Indeterminate`** (hand to reconcile). **Costs nothing — we were never going to retry.** ⚠️ **And we do not need the "Global Rate Limit Exceeded" string at all: we self-cap at 10 req/s against a venue limit of 20/s while our real load is ~8 requests/DAY ⇒ a legitimate 429 is structurally impossible unless our own limiter is broken.** |
| **O5** | Tick size / min order size, per market. | **Read it. Never assume.** *(Measured: 99.2% of the traded band is a 1¢ tick.)* |
| **O6** | The venue's settlement representation in the position ledger. | **HALT on divergence and resolve by hand at R4.** |

---

## 9. WHAT MUST BE BUILT BEFORE GATE A CAN EVEN START

1. ⚠️ **THE STALENESS WATCHDOG.** *(Red-team F8 — and it fired for real during this very run: Postgres was
   down for ~2 hours, `docker ps` reported it "healthy", and **nothing noticed**.)* GATE A's premise is
   *"the tapes accrue; forward data is cheap."* **A 30-day forward window with a silent multi-hour hole in
   it is not a forward window.** ⇒ **`max(us_quotes.ts) > now() − 15min`, else HALT the arm and page Tue.**
   *"Fail closed on stale data"* is already Hard Rule 2 of the brief. **It was not implemented, and the
   very first real outage went undetected. This is the shape of every quiet death in this program.**
2. **THE PRICE-MATCHED PLACEBO.** The current pool is matched on (league, date) **only — not price** — and
   carries **no side**, so **no ROI is computable for it.** **A control that cannot produce an ROI means
   GATE A cannot fail honestly.** Rebuild it as a fixed, price-band-matched, side-assigned cohort.
3. **THE SKIP-COUNTERFACTUAL LOG.** $0, and it may overturn everything (see the prereg §8).
