# US-EXECUTOR FORGE — the debates, and the adjudications

**2026-07-14, `feat/us-autotrader`. Phase 0 of RUN-US-AUTOTRADER.**
Two independent designs, opposed stances, one shared fact base (`reports/US-EXEC-API-SEMANTICS.md`).
**Designer A ("direct port"):** carry the intl cage over literally; a new design is a new bug.
**Designer B ("rethink"):** the intl cage was forged for a different machine; prove every deletion.

This document records where they **agree** (which is where confidence is highest), where they **conflict**
(which is where the thinking actually happened), and **what I adjudicated and why**. The synthesis that
governs the build is `reports/US-EXECUTOR-DESIGN.md`.

---

## 0. WHAT BOTH CONVERGED ON INDEPENDENTLY — treat as settled

Convergence from opposed stances is the strongest signal available. Both designers, working separately:

1. **The cage is RUST**, a new `us-exec` workspace crate, behind a **cargo feature, default OFF**.
   Not a Python sidecar. **The argument is not taste — it is deploy topology, and I verified every link:**
   `scripts/consensus-autoupdate.sh:40`'s `CODE_RE` **excludes `scripts/`** ⇒ a Python sidecar **never
   deploys**; `docker-compose.consensus.yml` has exactly two services (`postgres`, `copy-trading-bot`)
   ⇒ **no Python is in the deployed stack**; and `scripts/us_keepalive.sh`'s own header says
   *"NOT a launch unit: nothing schedules this."*
   ⇒ **A Python executor would be an unsupervised, undeployed, stale binary running against a
   freshly-migrated schema — while holding a private WS and a real-money key.** Rejected by both.
2. **Migrations are `049`/`050`, not the intl plan's `043`/`044`.** `042–048` are **already applied** on
   this branch by the US read-spine. A duplicate number **crash-loops the app on startup, after the
   autoupdater has already deployed it** ([[feedback-applied-migrations-immutable]]). Literal porting of
   the intl numbers is a **deployment-halting bug**, and both designers caught it.
3. **FOK before IOC.** Both, for the same reason: it turns the reconcile predicate from an inequality
   (`0 ≤ Δpos ≤ size`) into an **equality** (`Δpos ∈ {0, size}`). **An equality has no tuning parameter
   to get wrong** — and on a venue where the position delta is the *only* evidence an order existed (F2),
   that is worth more than a few extra fills.
4. **`executor_halts` ships in the SAME PR that wires the executor.** A container recreate **is** a
   kill-switch reset, and merging the executor is the very event that erases its halt state.
5. **Never retry a send. Never infer absence from a failed read. A failed read HALTS.** Inherited verbatim.
6. **The three default-OFF locks** (compile / spawn / runtime latch), and **there is no `unhalt()` method —
   the absence of the method is the design.**
7. **`super_event` is ported, not reinvented** (`scripts/superkey.py:43`). **When in doubt, MERGE clusters,
   never SPLIT** — a merge over-constrains (safe), a split over-deploys (dangerous).

---

## 1. THE FINDING THAT REFRAMES THE BUILD — B's W1: **the mapper is in the money path**

**Designer A did not see this. It is the highest-consequence bug class in the system.**

| | intl | **US** |
|---|---|---|
| how a signal becomes a tradeable instrument | `ClobMarket::outcome_token_id()` — a **pure in-memory function** on prefetched data | **a fuzzy title matcher with a confidence score** (`scripts/us_mapper.py`, `THRESHOLD = 0.90`) |
| its failure mode | it can be **absent** ⇒ we skip | it can be **WRONG** ⇒ **we buy the wrong instrument, confidently, with real money — and it looks like a perfectly normal fill** |

> **The intl cage has no analogue of a mapper, and therefore no defense against one.** Every safety
> mechanism we inherited is designed to catch *"did the order I sent do what I think?"* — **none of them
> can catch *"the order I sent was for the wrong market."*** A mis-map does not lose the edge; **it
> inverts it.** We buy the dog at favorite prices, the reconcile ties out perfectly, the kill-switch sees
> nothing wrong, and the loss looks like variance.

**ADJUDICATED: all four of B's controls are adopted, and they are mandatory.**
1. `mapper_conf ≥ 0.90` enforced by a **schema `CHECK`** on `us_market_map` — a low-confidence row
   **cannot exist**. (Fail-closed in the schema, not in code.)
2. **The basis guard** — an *independent, numeric* check on the mapping: `|us_mid − intl_implied| > 0.10
   ⇒ SKIP`. **A wrong mapping will almost always show a wild basis.** (Threshold is a **HYPOTHESIS**:
   UV-4 measured basis mean −1.5¢, **sd 5.9¢**; 10¢ ≈ 1.7sd. **Calibrate against `cross_venue_basis`
   (mig 046) before it governs a dollar.**)
3. **A human-reviewed allowlist for any live rung**: `us_market_map.reviewed_by IS NOT NULL` to trade.
   At ~3 events/day the universe is small. **Costs nothing; kills the class.**
4. **The post-settlement cross-check**: assert `us_settlement == intl_outcome_won` on every traded pair
   (the DMR, mig 044, is 100% settled). **A disagreement is a mapping error that has already cost money
   ⇒ MASTER HALT + retire the pair.**

---

## 2. THE NINE CONFLICTS, AND HOW I RULED

### C1 — Idempotency: A's `attempt_seq` partial index vs B's `UNIQUE(signal_id)`
**A:** a partial unique index on `signal_id` excluding *provably-dead* states (`REJECTED`, `ABANDONED`,
`SKIPPED`) — so a signal whose order provably never existed **may be retried**.
**B:** a plain **`UNIQUE(signal_id)`**. One signal, one decision, **forever**. A skip is a decision. No retry, ever.

> **RULING: B, and it is not close — because B's rule structurally eliminates A's own worst weakness.**
>
> A's self-identified Attack #1 is that the venue's position feed might **lag**, so reconcile could
> **falsely conclude `ABANDONED`** — and under A's index, **`ABANDONED` is retryable**, so a false abandon
> **manufactures the duplicate real-money position** that the entire cage exists to prevent. A named the
> hazard and then left the door it walks through standing open.
>
> **Under `UNIQUE(signal_id)`, a false `ABANDONED` is harmless: there is no path from it to a second
> order.** The worst outcome degrades from *"a duplicate position"* to *"we missed one trade."*
> **At ~3 events/day, missing a trade costs $0. A duplicate position is unbounded.**
>
> B's second argument is also correct and A's design has the latent bug: A's key is
> `sha256(signal_id‖policy_version‖leg‖attempt_seq)` — **if `exec_policy` hot-reloads between the crash and
> the restart, `policy_version` changes, the hash changes, and `ON CONFLICT` silently does not fire.**
> **A natural key cannot drift.**

**Both keep the single-flight-per-slug index** (`WHERE state IN ('DECIDED','SENT')`), and B's framing of
*why* is the sharpest sentence in either document: **F1 denies us a join key, so uniqueness manufactures
one.** If at most one of our orders can be outstanding on slug S, then **any unattributed trade on S in the
send window IS that order.** Reconcile-by-slug becomes *complete*.

### C2 — ⚠️ The price cap: A's `ask + 0.5¢` vs B's `mid + 0.5¢`. **This one is worth real money.**

**A** caps at `decision_ask + 0.5¢`, reading the brief's *"entry = first real US print + 0.5¢ ask haircut."*
**B read `scripts/us_backtest.py` and found the brief mis-states its own backtest.**

```python
us_backtest.py:139   """The FIRST real US print at/after the signal fired = our realizable US entry."""
us_backtest.py:64    MAX_ENTRY_LAG_MIN = 60      # a print up to SIXTY MINUTES after the signal fires
us_backtest.py:193   q = q + haircut_c / 100.0   # HAIRCUT_C = 0.5
```

> **A print is not an ask. A print is somebody else's trade, and it sits at the bid as often as the ask.**
> ⇒ **E[print] ≈ mid** ⇒ **the certified entry basis is `mid + 0.5¢`, NOT `ask + 0.5¢`.**
>
> **RULING: B.** And note *why* the two designers didn't notice they disagreed: **at the median US spread
> of 1.0¢ (measured), `ask ≈ mid + 0.5¢` — the two caps COINCIDE.** They diverge **only on wide books** —
> and on a wide book, **A's cap silently pays more than the price the edge was ever measured at.**
>
> **The consequence is uncomfortable and it is the correct kind of uncomfortable:** `cap = mid + 0.5¢`
> means **we skip whenever the spread exceeds ~1¢.** The executor **systematically refuses to trade wide
> books** — because on a wide book, *the price the backtest assumed is not available*, and taking the ask
> would be trading an edge we never measured. **The cap is DERIVED from the certified basis, not chosen.**

### C3 — ⚠️ B's W2: **the backtest's universe is not the universe we will trade.** Neither of us can sign this off.

`MAX_ENTRY_LAG_MIN = 60` means **signals whose US market never printed within an hour were silently dropped
from the sample.** So the certified +6.78% is **conditioned on a market somebody else traded within the
hour** — the liquid tail. **An executor taking at t=0 faces exactly the markets the backtest excluded.**

We gate for that (C2's cap + a depth gate). **But the gate is itself a selection, and its sign is unknown.**
B states the worrying hypothesis honestly, and I cannot refute it:

> *"Our edge is copying sharps. The US markets that have NOT yet printed are precisely the ones whose book
> has not yet absorbed the sharp's information — i.e. plausibly the ones with the MOST edge. Selecting only
> the already-printed, already-liquid markets could be selecting exactly the ones where the information is
> already in the price."*

**RULING: this cannot be resolved by argument, only by measurement — so it becomes a MANDATORY, $0
instrument.** `us_exec_skips` logs, for **every** skip and every `NoFill`, the signal, the book we saw, and
the reason; after resolution we compare **ROI(skipped) vs ROI(traded)**.
**If ROI(skipped) ≫ ROI(traded), our own gate is destroying the edge.** This is the highest
evidence-per-dollar object in the build and it costs nothing.

**And the honest consequence, which I am writing down before the data:** ⇒ **GATE A must be pre-registered
on the EXECUTABLE universe, and the +6.78% is CONTEXT, NOT AN ANCHOR. The backtest earns this arm exactly
zero dollars. The real evidence base starts at n = 0.**

### C4 — The 5-second stopgap: A's `Rejected` (safe) vs B's `Indeterminate` (fail closed)
Both agree on the essentials: **never back off** (the message is a trap), **never retry**, **a storm halts**.
Both independently invented the same discriminator, and it is better than the string the fact base worried
about: **we self-cap at 10 req/s against a venue limit of 20/s, while our real load is ~8 requests/day.**
⇒ **a legitimate 429 is structurally impossible unless our own limiter is broken** ⇒ **no string parsing
required.** *(Adopt this; it retires fact-base Q4.)*

Where they split: A maps the 429 to `Rejected` (terminal, safe — *"the exchange answered"*). B maps it to
`Indeterminate` (hand to reconcile), because *"a 429 always precedes acceptance"* is an **assumption**, not
a VERIFIED fact.

> **RULING: B.** It is strictly more conservative and **it costs us literally nothing** — we were never
> going to retry, and reconcile resolves it either way. A's version is *probably* right and B's is *safe
> even if A is wrong*. On the write path, that asymmetry decides it.

### C5 — `preview_order`: A's "veto, never permit" vs B's PREVIEW-ONLY rung
**Both are right and they compose.** A supplies the **rule**; B supplies the **rung**.

- **A's rule (adopted):** **preview is a VETO, never a PERMIT.** It may only ever *remove* orders from the
  set we place. It may **never** authorize a price the gate would have declined. This structurally forbids
  the seductive bug *"preview said avgPx 0.93, so raise the cap."* **The LIMIT price is the guarantee; the
  preview is a diagnostic.** If they ever disagree in production, we **HALT**.
- **B's rung (adopted, and it is the best idea in either document):** **a PREVIEW-ONLY rung — key present,
  private WS live, auth/clock/signing proven, and NOT ONE DOLLAR CAN MOVE, because the endpoint has no side
  effects.** It closes fact-base **Q3** (is the fee readable?) and **Q5** (tick / min-size) **at $0, at zero
  risk.** **Intl could not offer this rung. It is the highest-value $0 step in the ladder.**

### C6 — INV-4 (two-phase settlement) on a venue with no chain leg
**A** keeps intl's `MATCHED`/`CONFIRMED` verbatim, citing the venue's `PENDING_RISK` state as evidence a
post-acceptance reject may exist.
**B** keeps the *split* but **re-bases it**: `FILLED` (the order says so) → `RECONCILED` (an **independent**
read says so). **RISK counts `FILLED`. The LEDGER books `RECONCILED`.**

> **RULING: B's re-basing.** Same asymmetry, honest new justification, **and it pays for itself**: the
> `RECONCILED` state is exactly the hook where fact-base **Q3** gets its fee cross-check
> (`commissionNotionalTotalCollected` vs `report/trades/search` — *"if they disagree, HALT and re-derive"*).
> **The state is not insurance; it is the instrument.** Cost of keeping: one enum value, ≤60s of ledger lag.

### C7 — Kelly: A keeps it (fixing the fee bug) vs B deletes it
Both caught a real bug: **`pilot.rs:23` `pub const FEE: f64 = 0.02`** is intl's flat 2% and is **wrong on
US** (US taker fee is `Θ·p·(1−p)`, Θ=0.06 ⇒ ~0.45% of notional at p=0.925 — **4.4× smaller**).

B goes further and shows Kelly is **unstable on this arm**: at p≈0.925 the `(1−p)/r_win` term is a ratio of
two small numbers, so `f*` = **65%** at the point estimate but **10%** at the certified lower bound — **a
6.5× swing from a 4pp move in an input we barely know.**

> **RULING: B.** **A parameter that amplifies its own uncertainty by 6.5× has no place in a system whose
> defining failure mode is parameters that turned out to be wrong.** ⇒ **flat, hard, per-signal dollar cap,
> ratcheted by rung. A flat cap cannot be wrong by 6.5×.** *(And it is moot in practice: the rung's
> `size_cap_usd` binds long before Kelly does. Deleting it removes a landmine, not a lever.)*
> `pilot.rs` stays **untouched** — the US executor does not route through the intl `OrderGate`, so all
> **10** of its tests stay green. *(The brief said "8 tests." **The file has 10.** Planning for 8 would have
> silently dropped two.)*

### C8 — Reconcile: position **snapshots** (A) vs position **LEDGER deltas** (B)
> **RULING: B, on a point A missed entirely.** A snapshot answers *"what do I own?"*. Only a **ledger**
> answers *"what CHANGED, and WHEN"* — and **only a delta is attributable when we may already hold a prior
> position in the same slug.** Intl never faces this because it joins on `taker_order_id`; **F1 took that
> join key away from us.**

**And B's W5 — a daily false-halt generator that A's design would have walked straight into:**
**intl positions redeem on-chain; US positions SETTLE.** ⇒ our ledger and the venue's will **legitimately
diverge during every settlement window** ⇒ a naive *"venue positions == our positions, else HALT"* check
**halts every single day at settlement.** **A cage that cries wolf gets disarmed by its owner** — this is
exactly how the whole thing dies quietly. **Adopted: settlement is recognized via the venue's own
`realized` ledger field; the DMR (mig 044) is the audit, not the trigger; and until the ledger's settlement
shape is CONFIRMED with a key, we HALT on divergence and resolve BY HAND** (tractable at ~3 events/day, and
it is how we learn the shape **without guessing**).

**Also adopted (B):** the **three-way tie-out** — private WS / `report/trades/search` / the **CFTC-statutory
regulatory CSVs**. **Any disagreement involving the statutory record ⇒ HALT, because if we disagree with the
statutory record, WE are wrong.** Intl had exactly **one** source of truth. **This is the single biggest
genuine safety upgrade of the venue, and the design should USE it, not merely note it.**

### C9 — GATE A's N and duration: A's 60 events / 21 days vs B's 65 events / 30 days
> **RULING: B**, on two arguments A does not make.
> 1. **The cluster budget CHANGES THE STATISTICS.** Under `fcfs` (the game is the bet ⇒ the game gets one
>    bet's worth of money), **we place ONE order per event** ⇒ `n(picks) = n(events)`. **The risk policy
>    determines the sample size, which determines the gate.** A's table implicitly assumed ~2 picks/event.
> 2. **A ≥30-CALENDAR-DAY floor, independent of n.** The backtest window (06/29–07/14) contains **one
>    tournament regime**, and [[project-polymarket-regime-persistence]] found a SOCCER-ARTIFACT. **30 days
>    is the minimum window that can straddle a regime change.** n alone cannot buy this.
>
> **And B's binding failure clause is adopted verbatim:** *"If, after 65 events AND 30 days, LB ≤ 0: the arm
> is NOT CERTIFIED. **WE DO NOT EXTEND THE WINDOW.** Extending the window is the goalpost move that produced
> four retractions in this program."*

---

## 3. THE FRAGILITY BOTH B AND I FOUND INDEPENDENTLY — and it is the real headline

**The economics report attacked the 0.95–0.98 band for having ZERO losses in 49 picks** — *"an unobserved
tail, not a measured edge."* **It never turned that lens on the band we are about to trade.**

The 0.90–0.95 non-WC cell is **82 picks / 42 events with ONE loss.** At p≈0.925 the market prices **~6.2**
losses in 82. I reconstructed their P&L from first principles and it reproduces **+6.78% exactly at L=1**,
which means the model is right and the sensitivity is trustworthy:

| losses | 0 | **1** | 2 | 3 | 4 | 5 | **6** |
|---|---|---|---|---|---|---|---|
| **net ROI** | +8.11% | **+6.79% ← observed** | +5.47% | +4.15% | +2.83% | +1.52% | **+0.20% ← market-implied** |

> **The certified edge's entire content is: "in the 0.90–0.95 band, the favorite loses ~1 time in 82 where
> the market priced ~6."**
> **The edge is FIVE losses from zero, and the market expects SIX.**
>
> This is **not** a reason to abandon it — the deviation is real (P(≤1 loss | market is right) ≈ **1.3%**,
> consistent with the reported clustered p=0.003). **It is the reason the forward test must be
> pre-registered, the size must start near zero, and the loss count — not P&L — must be the primary
> detector.**

**Two consequences, both adopted:**
1. **⭐ THE LOSS-COUNT MONITOR (B's, and it is the right instrument for THIS arm).** The edge *is* a
   loss-rate effect ⇒ **the highest-power observable is the LOSS COUNT, not P&L.** A P&L detector on a
   1-loss-in-82 process emits almost no information per day — **which is precisely why intl's P&L CUSUM
   was structurally incapable of firing on `weather_fav`, and the same mathematics condemns it here.**
2. **The sizing number in the brief is WRONG, and it overstates the edge ~2.5×.** The brief says
   **"+16.70% net."** That belongs to **a different sample** — all-band, **World-Cup-inclusive**, n=2,098.
   **The rule we will actually trade is +6.78% (n=82/42), and +5.45% [+1.22,+8.55] after the stress.**
   ⇒ **ALL SIZING USES THE LOWER BOUND. Forever.**

**And a fork I am closing explicitly so it cannot be quietly re-sliced later:** the pre-registered rule is
the **band slice on the UNGATED sample**. It does **NOT** include the `favorite_v2` garbage gates
(liquidity ≥ $1k, rank < 5) — which on US, applied across the band, give **+5.03% [−12.62,+19.50] p=0.554,
i.e. NO EDGE**. Nobody has tested the intersection, and **GATE A must not resolve that fork by re-slicing
after the fact.** ⇒ **the v2 flags are LOGGED on every decision, and analyzed only as a pre-declared
SECONDARY question. The primary test is the rule as written.**

---

## 4. THE THREE ATTACKS THAT SURVIVE — carried into the design as OPEN, not closed by argument

1. **⚠️ OPEN-2 (B's weakness #3, and it can bite on any deploy).** Every deletion (`LIVE`, `CANCEL_REQ`,
   `EXPIRED`) rests on **F2 — which is VERIFIED FROM DOCS, NOT FROM A LIVE ORDER.** The venue's own state
   enum contains **`PENDING_NEW` and `NEW`**. **If a US IOC transits through `NEW` even transiently, a
   restart landing mid-flight finds a NON-EMPTY order snapshot — and a naive boot gate MASTER-HALTS on a
   perfectly healthy order.** A self-inflicted halt on every unlucky deploy.
   ⇒ **Mitigation adopted:** the boot assertion is **"no order in a RESTING tif"**, *not* "the snapshot is
   empty"; a `PENDING_NEW`/`NEW` order on a slug we hold a `SENT` row for is **ADOPTED, not halted on**.
   ⇒ **Must be settled by a live order before the deletions can be fully trusted. If F2 is softer than the
   fact base believes, `LIVE` comes back.**
2. **⚠️ The position feed's LATENCY is unverified (A's weakness #1).** Every safety property reduces to
   *"the venue's position delta is correct and arrives promptly."* If it lags a fill by >120s, the two-read
   grace manufactures a **false `ABANDONED`**. *(Danger largely closed by C1's `UNIQUE(signal_id)` — a false
   abandon can no longer produce a duplicate — but it still costs us a **false halt**, and a cage that cries
   wolf gets disarmed.)* ⇒ **R3 must MEASURE the position-feed latency distribution, and the 120s grace and
   300s halt must be RE-SET from that measurement. Until then every number in reconcile is a HYPOTHESIS.**
3. **⚠️ The shared-mode failure (A's weakness #2) — and I am adopting A's own proposed fix, which A left
   unresolved.** The paper track (which GATE A scores) and the live executor **walk the same book with the
   same depth-walk code**. ⇒ **a bug in the depth-walk corrupts the paper track and the live orders IN THE
   SAME DIRECTION, and GATE A will cheerfully certify the bug.** This is the shape of the `tape_maker_fill()`
   disaster (*"the writer says it is not a trade; the reader treats it as one"*).
   ⇒ **`preview_order` is an INDEPENDENT, venue-side computation of the same quantity.** **Adopted: in the
   PREVIEW-ONLY rung, require the paper VWAP to match `preview.avgPx` within tolerance on ≥50 signals
   BEFORE GATE A may return a verdict.** This is the cross-check that breaks the shared mode — and it is
   free.

---

## 5. THE HONEST STATEMENT OF WHAT GATE A CAN AND CANNOT DO

Both designers converged here, and it is the line the whole rollout hangs on:

> **Our take-only FOK "fill model" is not a model.** It is a **deterministic read of a REAL book**: *"was
> there ≥ clip of depth at ≤ cap, at the decision instant?"* That is why paper can certify something here
> when intl's maker leg could not (intl had to guess queue position, and every fill model this project
> built was wrong in the flattering direction).
>
> **But exactly two residuals remain unmeasured, and both bias us OPTIMISTIC:**
> **(a) our own market impact** (we are not in the book we are reading), and
> **(b) latency** between our book read and the venue's match (assumed zero).
>
> ⇒ **GATE A CERTIFIES THE PICK, AT A REALIZABLE PRICE. IT DOES NOT CERTIFY THE FILL.**
> ⇒ **The rung after GATE A is therefore NOT "ramp." It is "spend $5 to measure (a) and (b)."**
> **Two gates, two claims. Neither is allowed to launder the other.**
