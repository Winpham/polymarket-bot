# RUN — US AUTO-TRADER: the real-money execution system, built to deserve the money it touches

**Type:** long autonomous run — the highest-stakes one in the program. **Repo:** `~/polymarket-bot`
(execute here; code lives here). **Owner:** Tue. **Branch off:** `feat/us-venue` (observability +
two-book spine) — the economics work is on `feat/us-economics`; **reconcile/rebase both first.**

**READ BEFORE ANYTHING (this run is an ADAPTATION, not a green field):**
- `EXECUTOR_FORGE_PLAN.md` — the adversarially-forged real-money cage. **Its invariants are law.** It is
  written for the *intl CLOB*; your job is to carry its safety architecture onto the *US venue*, not to
  reinvent it or water it down.
- `reports/US-VENUE-OBSERVABILITY.md`, `reports/US-VENUE-ECONOMICS.md`, `reports/US-BACKTEST.json`, and
  DECISIONS `UV-1..UV-13`. The strategy is already decided; do not relitigate it.
- Memories: [[project-polymarket-us-economics]], [[project-polymarket-us-venue]],
  [[project-polymarket-executor]], [[project-polymarket-market-making]], [[feedback-autonomous-trust-model]].

---

## 0. THE BRIEF IN ONE PARAGRAPH

We are going to place real orders with real money on Polymarket US for the first time. Everything until now
was read-only. This run builds the system that does it — and the entire point is that it is **built to
deserve the money**: certification *before* capital, an execution cage that fails closed at every boundary,
a staged rollout that starts near-zero and ramps only on proven forward performance, and a kill-switch that
halts a wedged process in under two seconds. The strategy is settled and deliberately narrow (take-only, a
favorite subset, tilt 0.90–0.95 non-World-Cup). The hard part is not the strategy — it is **never losing
money we cannot see**, and **never trading an edge we have not yet earned the right to trust.** Build it
slowly, adversarially, and reversibly. Nothing about "it touches real money" is a slogan here; it is the
design constraint that dominates every other.

---

## 1. WHAT WE ARE BUILDING (the decided spec — integrate, don't reopen)

From the economics run, the posture is fixed:
- **TAKE, don't make — every arm, every price.** Making is dead on US (net maker ≈ 0; the subsidy pays only
  at the touch where you get picked off, and is unreachable anyway). So **every order is a taker order**,
  and a taker order that must not rest is a **FAK (fill-and-kill / IOC)**. *This is also a safety win:* a
  FAK never sits on the book, so the orphan-GTC catastrophe that dominates the intl cage largely dissolves.
- **The arm:** favorite consensus, **US-mappable only** (mapper conf ≥ 0.90; ~18% of the band is
  US-actionable — this is a subset, not a venue swap), **World Cup EXCLUDED** (60% of the universe, and it
  hides the signal), **tilt 0.90–0.95** (NOT "as deep as possible" — 0.95–0.98's zero-loss record is an
  unobserved tail; one upset erases it).
- **Economics:** the edge **survives US fees** (+16.70% net backtest, fee ≈ 5% of edge), so **do not reshape
  the strategy around fees.** Fee = `Θ·C·p·(1−p)`, taker Θ=0.06, read the realized fee off the exchange's
  own trade event — never model it. Apply the **Accelerated Tier** rebate (25–50%) to `net_edge` once the
  venue assigns it.
- **STATUS: SUGGESTIVE, NOT CERTIFIED.** The backtest is post-hoc (8 cells, barely-Bonferroni). **This is
  the fact that governs the whole rollout: no meaningful capital until a pre-registered forward test
  certifies the rule.**

---

## 2. THE TWO NON-NEGOTIABLE GATES

**GATE A — CERTIFICATION BEFORE CAPITAL.** The edge is post-hoc. Placing real size on it now is gambling,
not trading.
- **Pre-register, blind:** the exact rule (0.90–0.95, non-WC, conf ≥ 0.90, depth-sufficient, `net_edge>0`),
  the exact success metric (net ROI clustered by event, vs a matched non-signal placebo pool), the exact
  decision threshold, and the exact N/duration — all written down and committed **before** looking at one
  day of forward data. No moving the goalposts; the program has four retractions that reversed sign when a
  control was finally added.
- The tapes already accrue (`us_tape_ingest.py`, `us_mid_tape.py`) — forward data is now cheap. Shadow and
  paper stages (below) run *during* the forward window; **real capital does not scale until the pre-registered
  test clears its threshold on out-of-sample forward days.**
- Re-validate the realism inputs the backtest leaned on (entry = first real US print + 0.5¢ ask haircut)
  against live fills once we have them, and re-run adverse-selection across a **full US trading day** (the
  economics tape was 148 min of overnight flow).

**GATE B — THE CAGE INVARIANTS (inherited from `EXECUTOR_FORGE_PLAN.md`, adapted to US).** These are not
optional and not negotiable. Port each one; where the US API differs, solve the *same failure*, not a
weaker version:
- **The exchange is the only source of truth.** An HTTP 200 is a HINT, not a fact. State advances only on a
  venue order/trade event (authed private WS) or a reconcile read.
- **Never retry a send blind.** An indeterminate POST (timeout / TCP reset / container SIGKILL mid-request)
  means *the order may exist and we do not know* — the duplicate-position generator. State stays `SENT`;
  reconcile owns it; **we never infer absence from a failed read — a failed reconcile read HALTS the arm.**
- **A cancel is a request, not a fact.** Budget is not released until a cancellation/trade event confirms it.
- **The container is recreated on every merge to `main` (auto-deploy).** A restart can land mid-send. The
  system must come back up, reconcile open orders/positions from the venue, and adopt or abandon them —
  *before* it is allowed to place anything new.
- **Fees and fills are read off the exchange, never modeled.** Realized P&L uses the venue's own fee on the
  trade event.
- **Default-OFF at independent locks.** Like the intl plan's three locks: a compile/feature gate, a runtime
  flag, and a per-arm enable — so no single mistake can arm live trading, and a merge never silently turns
  it on.
- **The kill-switch fires cancel-all/flatten exactly once and LATCHES** — never spins — and every order path
  checks it first. Reachable from a wedged process in < 2s.

---

## 3. PHASE 0 — DESIGN FIRST, ADVERSARIALLY (this is the "really think it through" mandate)

**Do not write execution code until the design has been red-teamed.** Produce a US-executor design doc that
*adapts* the intl cage, and then attack it. Use the Forge discipline: independent designs, an adversarial
critique pass, a synthesis. The questions that must be answered *in writing, with the venue's real API
semantics verified from `docs.polymarket.us`*, before any code:

1. **Idempotency on US — does US give us what intl couldn't?** The intl plan proved `client_order_key` is
   useless for exchange reconcile (the exchange never heard of it). But the US `Order` object carries a
   **`clordId` (client order id)** and `create_order` may honor it. *Verify:* does US dedup on `clordId`
   server-side? If yes, idempotency is genuinely stronger here — but prove it; do not assume. Either way,
   reconcile via `search_orders`/`search_trades`/`get_open_orders`/positions remains the belt.
2. **The FAK simplification — how far does it actually protect us?** A fill-and-kill never rests, so the
   orphan catastrophe is mostly gone. But enumerate what remains: a FAK that *partially* fills; a FAK whose
   response is lost (did it fill?); the private-WS `order_update`/`position_update` as the truth source.
   Design the take-only state machine (fewer states than the intl GTC/GTD one — exploit that, but prove the
   send-boundary cases B1/B2/B3 are all covered).
3. **The 5-second stopgap.** US rejects orders not processed in 5s with a message that *reads like* a rate
   limit but is not (`Global Rate Limit Exceeded`) — do NOT back off on it; treat as a transient latency
   reject. Design the retry/skip policy around it explicitly.
4. **Preview then place?** US exposes `preview_order` (validate + expected fills before submit). Decide
   whether every order previews first (cheap safety) or only on uncertainty.
5. **Slippage cap — limit-FAK, never market.** The backtest assumed ask + 0.5¢. The executor computes a
   **max price it will pay** from the live book and submits a limit FAK at/under it; if the book has moved
   past that, it **skips — never chases.** Where does the cap come from, and what's the skip logic?
6. **Reconcile + own-account truth.** Design the reconciler against US: authed private WS (`order_snapshot`/
   `position_snapshot` + updates) as the live feed, `search_trades`/positions REST as the audited backstop,
   and the divergence rule that HALTS on mismatch.
7. **Auth & key custody.** US uses Ed25519 signing (`X-PM-Access-Key`/`Timestamp`/`Signature`, 30s window).
   The private key lives in exactly one place, one crate, off by default (mirror the intl `clob-exec`
   isolation). Design key handling as if it were a life-stakes secret — because a leaked key is real money.

Deliverable of Phase 0: a design doc + a red-team critique + a synthesis, checked in, that a skeptical
reviewer would sign off on *before* a single order-placing line exists.

---

## 4. ARCHITECTURE & BUILD ORDER (rungs; each ships default-OFF; the first rungs place ZERO orders)

Mirror the intl plan's "Phases 0–2 place no orders" discipline. Build the whole machine and prove it in
shadow/paper long before it can spend a dollar.

1. **Decision engine (shadow) — no orders, no key.** Assemble the live gate: intl signal → mapper (conf ≥
   0.90) → band 0.90–0.95, non-WC → live US depth check (`us_book_tape`/fresh `/book`) → `net_edge()` after
   fee+rebate → **emit an intent** ("BUY slug X, size Y, ≤ price Z, because …"). Logs the full decision
   provenance; places nothing. Run it against the live tape; watch what it *would* do.
2. **Paper placer — simulated fills against the live book/tape, no key.** The intent hits a paper fill model
   driven by the real book (FAK semantics: fills what's actually there at/under the cap, else skips).
   Produces a forward paper track that feeds GATE A's pre-registered test.
3. **The cage — the 90% that needs no crypto.** Order state machine (take-only/FAK), the reconciler, the
   per-event cluster budget (size the GAME, §5), the kill-switch latch, the drawdown/loss detectors,
   the container-restart adoption path. All exercised with the paper placer. This is where the safety lives.
4. **The US write client — isolated crate, key, off by default.** Ed25519 signing, `create_order` (limit
   FAK), `cancel`, `preview_order`, `close_position`, private-WS subscriptions. The ONLY place a key exists.
5. **Tiny-real, then graduated ramp (GATE A must have cleared).** See §6.

---

## 5. RISK & MONEY MANAGEMENT (the part that decides whether a bad week is survivable)

- **Size the GAME, not the market.** Multiple US instruments in one event are ONE correlated bet
  ([[project-polymarket-correlated-risk]]). The cluster budget caps exposure per *event*, and the
  kill-switch/drawdown math sees event exposure the instant a leg matches (assume-you-own-it-on-match).
- **Capacity is RE-MEASURED on US, not inherited.** The intl $50–250/signal does not transfer. US favorites
  are deeper but time-varying (overnight thinning). Size to *live* depth; if depth is insufficient for the
  clip at the price cap, **skip** — fail closed.
- **Kelly-capped and small.** ⅛-Kelly at most, and *far* below that during the ramp. A suggestive edge gets
  minimum size until forward-certified.
- **Hard limits, all fail-closed:** per-event cap, per-day new-capital cap, total-open cap, daily-loss
  circuit-breaker, drawdown breaker → each trips the kill-switch latch. The system halts on unknown state,
  stale data, reconcile mismatch, or repeated rejects (RejectStorm ⇒ structural problem ⇒ halt, never retry).

## 6. THE STAGED ROLLOUT (reversible; each stage has explicit go/no-go)

| Stage | Capital | Gate to enter | Human-in-loop |
|---|---|---|---|
| Shadow | $0 | decision engine emits sane intents vs live tape | — |
| Paper | $0 | cage + paper placer green; forward paper track accruing | — |
| **GATE A** | — | **pre-registered forward test CLEARS its threshold on OOS days** | Tue reviews |
| Tiny-real | hard $ cap/signal, tiny | Gate A cleared + key + funded + reconcile proven on live | **first N orders require Tue confirmation** (confidence-banded approval) |
| Ramp | graduated | forward *realized* P&L + slippage EWMA stay in-band, per step | auto within caps; Tue notified on any breaker |

Confidence-banded approval ([[feedback-approval-policy]]): the first live orders are human-confirmed; auto
only after the system demonstrably behaves. Every stage is reversible — positions are closable
(`close_position`), the switch latches, and no stage's capital cap is raised except by an explicit,
evidence-backed step.

## 7. HARD RULES

1. **No real order until GATE A clears AND the cage is proven in paper AND Tue explicitly goes live.** Rungs
   1–3 place zero orders and need no key. Do not shortcut to placement.
2. **Fail closed, everywhere.** Stale data, unknown state, reconcile mismatch, failed read, repeated
   reject → HALT. Never trade through uncertainty.
3. **The evidence rule** (control, significance, n + dispersion) governs GATE A and every performance claim.
4. **`merge to main == auto-deploy`.** Work on a branch; default-OFF at independent locks; a merge must be
   incapable of arming live trading on its own.
5. **The key is life-stakes.** One crate, off by default, never logged, never committed, custody designed
   paranoically. A leaked key is real money and real identity.
6. **No ToS circumvention** anywhere; US is a KYC'd account we act honestly on. Intl stays read-only.
7. **Report honestly.** A partial/timed-out build is "incomplete + resumable." Paper ≠ live. Suggestive ≠
   certified. Commit incrementally so a reaped run is salvageable.

## 8. DELIVERABLES

1. **Phase-0 design doc + red-team + synthesis** (the adapted US cage, verified against the real US API).
2. **The pre-registered forward-test spec** (GATE A), committed before forward data is read, + its verdict
   when it clears.
3. **The decision engine + paper placer + cage + reconciler + kill-switch**, default-OFF, tests green,
   proven in shadow/paper — the real-money machine, unarmed.
4. **The US write-client crate** (signing, FAK, preview, cancel, close, private WS), isolated, off by default.
5. **A `DECISIONS.md` entry** (UV-14…) recording the design choices, the failure-mode coverage, and the
   go/no-go criteria for each rollout stage.
6. **A go-live checklist for Tue** — exactly what must be true, and what Tue must do, before the first dollar.

## 9. WHAT NEEDS TUE (surface; most of the build does NOT block on these)

- **US API key** — unblocks rungs 4–5 (own-account + placement); rungs 1–3 do not need it.
- **Accelerated Tier Placement** — submit trailing-30-day intl volume for the 25–50% taker rebate (bake the
  assigned tier into `net_edge`).
- **The go-live decision + funding + first-orders confirmation** — Tue's call, after GATE A clears and the
  cage is proven. The system proposes; Tue authorizes.

## 10. THE FRAME

The strategy is small and settled; the risk is entirely in the execution and in trusting an edge too early.
So this run is judged not by how fast it trades but by how faithfully it refuses to: it earns the right to
place an order by first proving, in paper and forward, that the edge is real and that the machine cannot lose
money it cannot see. Build the cage as if the first bug will cost real money on a real account with Tue's
name on it — because it will. When it is done, the deliverable is not "a bot that trades," it is **a bot we
can trust to trade, that starts tiny, ramps only on proof, and stops itself the instant anything is wrong.**
