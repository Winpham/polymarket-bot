# EXECUTOR FORGE RUN — the real-money execution layer for `~/polymarket-bot`

**Status:** build brief / run prompt. Not yet started.
**Owner:** Tue. **Repo:** `~/polymarket-bot` (Rust workspace, Postgres, Docker, launchd autoupdater).
**Read before you plan:** `reports/EXECUTION-READINESS.md` (branch `feat/evergreen-portfolio`),
`reports/PREREG_20260709T020500Z_exec_policy.md`, `DECISIONS.md` D21/D26/D29/D30/D31,
`copy-trading-bot/src/pilot.rs`, `common/src/storage/exec_policy.rs` (branch `feat/exec-policy`).

---

## 0. THE ONE-PARAGRAPH TRUTH (do not skip)

We have never placed a single order. Every "P&L" in this repo is a Postgres row. The research stack
(signals, arms, ledger, kill-switch, sizing, risk engines) is **built**; the order client is
**physically absent** — there is not one crypto dependency in `Cargo.lock` and not one POST to
`clob.polymarket.com`. Simultaneously, our own audits say the thing that kills us is **not** pick
quality and **not** speed: the champion is `+6.95%/turn` at a `+1¢` proxy but only **`~+1.2%`
realizable at the fire-time ask**, because a taker-at-fire pays **~3.4¢ over mid** and the whole edge
is 3–7¢ wide. **The edge is in the FILL, not the pick.** Therefore this build is not "a fast copy
bot." It is **a fill-quality engine with a safety cage**, and it is simultaneously **Rung 5** of the
readiness ladder — the rung nobody has ever attempted.

---

## 1. MISSION

Build the execution layer that turns a fired consensus signal into a **real, correctly-priced,
never-stale, never-duplicated, always-stoppable** order on the Polymarket CLOB — and that **measures
its own fills** so the δ×cancel execution frontier stops being a simulation and becomes a
measurement.

Ship it **dark**: default OFF, arming behind a latching gate, with a monotone promotion ladder
(§7) where each rung is unlocked by evidence, not by enthusiasm.

---

## 2. FOUR REFRAMES YOU MUST INTERNALISE (each overrides a plausible-sounding instinct)

**(a) "Fastest" is the wrong target — but the TAIL is a real target.**
`scripts/latency_cost.py`, audited: a 15-min delay costs **+2.05¢ ± 4.0¢, p = 0.36** — statistically
indistinguishable from generic favourite drift. The earlier "15 min = 8¢" claim is **RETRACTED**.
Detect **p50 is already 1.6 min**; detect **p90 is 94 min**. So: *optimising the median buys nothing;
killing the tail buys a lot.* Build for **bounded worst-case decision latency** (a hard signal TTL +
`LIVE_FILLS` on-chain ingestion to kill the sweep-rate tail), **not** for microseconds. Speed is a
*staleness-safety* property here, not an alpha source. **Never sell speed as edge.**

**(b) "Maximize turnover" is a trap at our capacity.**
Measured on 33 live books: **$50/signal → net +8.6% at the p90 book**; $250/signal → **9.5¢
slippage**, which is larger than the entire edge. The book binds — not the spread (1.2¢), not latency
(~2¢, n.s.). Turnover above capacity is **negative EV**: every extra dollar buys worse fills. The bot
must have a **hard per-signal size cap** and treat size as a *risk*, not a *lever*. Realistic ceiling
today: **~$1k/day deployed, ~$85/day gross** — and a weather day is **ONE correlated bet** (a heat
dome resolves ~20 cities together). Design for that, not for a dream.

**(c) A fire-time taker is the one execution policy we KNOW loses.**
Prereg §0: executable ask sits at ~mid₀ **+3.4¢ at fire**, +2.2¢ at +5 min, +0.6¢ at +15 min, ≈mid₀
at +30 min. The naive "copy bot" — see signal, cross the spread — hands back most of the edge. The
executor's default posture is **maker / capped-chase**, with taking as a *fallback*, not a default.
**But** the named enemy is **adverse selection** (D31): a resting bid fills only when price comes
back to you ⇒ you catch reverters and miss winners (`wr_filled` 62–65% vs `wr_missed` → 100% on long
cancels). Tue's power-limited lean: **small δ (0.5–1¢) + SHORT cancel (~5 min)**. Long cancels just
fill more losers. The policy is therefore a **frontier to be measured on real fills**, not a constant.

**(d) Nothing is certified at the price we pay. The bot's first job is to EARN the certification.**
`weather_fav` LODO-survives with belief-blind null **p = 0.0005**, but the frozen gate accepts exactly
one basis — the captured `entry_ask` — and that column was captured wrong until D4. **The clock on
clean data has not started.** So the executor is **not** "deploy the findings." It is the instrument
that produces the only evidence that can license real money: **our own fills, at our own price, with
our own market impact.**

---

## 3. NON-NEGOTIABLE INVARIANTS ("accurately, never mistaken or stale")

Every one of these is a hard requirement with a test. A violation is a P0 bug, not a tuning issue.

**I1 — Write-ahead intent.** An order is a DB state machine *before* it is a network call:
`INTENT → SENT → ACKED → (FILLED | PARTIAL | CANCELLED | REJECTED | ORPHANED)`. The intent row is
committed **before** the POST. A crash between commit and POST must be recoverable on restart by
reconciling against the exchange, never by guessing.

**I2 — Idempotency, structurally.** A deterministic client order key = `hash(signal_id, policy_id,
attempt_seq)` with a `UNIQUE` constraint. Double-send must be *impossible*, not *unlikely*. Retries
reuse the key; the exchange's dedup (or our own reconcile) resolves the truth.

**I3 — Freshness precondition (the anti-stale gate).** Immediately before sending, re-read
top-of-book. **Reject the send** if any of: quote age > `MAX_QUOTE_AGE_MS`; ask moved more than
`MAX_ASK_DRIFT` from the decision ask; signal age > `SIGNAL_TTL` (hard); market is closed / resolving
/ within `MIN_TIME_TO_CLOSE`; the tape/WS heartbeat is stale. **Stale ⇒ skip. Never a blind send.**

**I4 — Price clamp, always.** `limit_price ≤ min(decision_ask + δ_max, band_ceiling, HARD_MAX_PRICE)`.
Reject any price ≥ 0.98 (dead chalk) and any entry < `entry_floor = 0.45` (skip longshots —
`reports/risk_policy.json`). The clamp is enforced in **two independent places** (policy layer and
the order gate) so a bug in one cannot pass a bad price.

**I5 — Reconcile before act.** On every startup and on a fixed cadence: pull open orders, fills, and
positions **from the exchange**, diff against local DB, and repair. Local state is never authoritative.
An unrecognised open order at startup ⇒ **cancel it and HALT** (loud), do not assume it's ours-and-fine.

**I6 — The kill-switch is latching and default-halted.** `pilot.rs::KillSwitch` already implements
`DayStopLoss(5%)`, `MaxDrawdown(15%)`, `EdgeDegraded(λ̂ < 0.25)`, `MasterOff`, halted-from-birth.
Wire it. **Add:** `DataStale` (ingestion/tape heartbeat dead ⇒ halt, do not trade blind),
`RejectStorm` (N rejects/errors in a window), `SlippageBreach` (realized slippage vs decision ask
exceeds budget), `SpendBudget` (daily notional cap), `SlateStop` (−5 units). A halt **cancels all
resting orders**, then latches. Un-halting is a **human action**, never automatic, and is audit-logged.

**I7 — One kill path that always works.** A single command / file / env flag that cancels everything
and halts, which works even if the main loop is wedged. Test it under a wedged loop. This is the
"stops anytime necessary" requirement, and it must be provable, not aspirational.

**I8 — No fill model, ever again.** D31/G2: `last_size > 0` on a `price_change` is **order-book
churn, not an executed trade** — a volume-based fill model is the exact bug that produced two false
"+4.8%" results. Migration `041_exec_policy.sql`'s "REALISTIC" maker-print fill **inherits this bug
and must be fixed or justified in writing before any number from it is trusted.** In the real
executor there is no fill model at all: **a fill is an exchange fill event.** This build's core value
is that it *replaces simulation with observation*.

**I9 — Every order is attributable.** Persist `signal_id, arm, policy_id, policy_version,
decision_ask, decision_mid, decision_ts, sent_ts, ack_ts, fill_ts, fill_px, size, fees, and the
counterfactual (ask at +5/+15/+30 min)`. Without this the learning loop (§6) is impossible and we're
back to guessing.

**I10 — Paper and real share ONE code path.** The mode flag changes only the final `Placer` impl.
A paper run must exercise the identical state machine, clamps, and reconcile logic. Divergent paths
are how paper lies to you.

---

## 4. ARCHITECTURE — extend, do not rebuild

What exists (verified): `pilot.rs` (order gate + latching kill-switch + de-levered Kelly `1/12`, cap
5%, **unwired**, `place()` returns `NoPlacer`); `honest_paper_ledger` (idempotent); the consensus
signal producer (hook at `consensus_cycle.rs:519`, and the ≲30s `hot_lane.rs`); CLOB **read** clients
(`data/models.rs:350` best-ask, `live_tape.rs` WS); the exec-policy shadow evaluator (branch
`feat/exec-policy`, `common/src/storage/exec_policy.rs`, 846 L). The Python risk engines
(`corr_risk_*.py`, `risk_engine.py`) are **built but "applied to nothing."**

**Build these, and only these:**

1. **`clob-client` crate (new)** — the missing leg.
   - L1 auth: EIP-712 signing → derive/create API key. L2 auth: HMAC-SHA256 request headers.
   - Signed order struct → `POST /order` (GTC/GTD/FOK), `DELETE /order`, cancel-all.
   - Authed **user WebSocket** for order/trade events (fills must be *pushed*, not polled).
   - Balance / allowance reads; USDC + CTF approvals (one-time, on-chain).
   - Proxy-wallet correctness: signature type must match how the funds are actually held
     (EOA vs email/magic proxy vs browser proxy) — **getting this wrong = every order rejected.**
   - ⚠️ **Verify every API detail against the live docs and the official client source. Do not trust
     this brief's API sketch, and do not trust your training data — this API drifts.**

2. **`Placer` trait + three impls** — `ShadowPlacer` (decide + log, send nothing), `PaperPlacer`
   (books at the *real observed* ask/fill events, no fill model), `LivePlacer` (the real client).
   Slot behind `pilot.rs::OrderGate::place` (the `NoPlacer` branch, `pilot.rs:238`). Wire `pilot` into
   `live.rs` and delete the `#![allow(dead_code)]` at `pilot.rs:20`.

3. **The order lifecycle state machine** — the actual heart of this build. Per signal:
   `decide policy → quote → rest → (chase within δ_max, bounded re-quotes) → cancel at T →
   (fallback take | abandon) → reconcile → book`. Must handle partial fills, re-quote laddering,
   cancel-races (cancel arrives after fill), and exchange rejects. **Cancel-race handling is the
   #1 source of real-money duplicate positions — design it first, test it hardest.**

4. **The execution policy layer (the "flexibility" you asked for).** Policy is **declarative config,
   not code**: `{arm → policy}` where policy ∈ `{take_at_fire, patient_take(delay), maker_rest(δ,
   T_cancel), capped_chase(δ_max, step, T_cancel), skip_as_untailable}`. Versioned, hot-reloadable,
   stored in DB, with every order stamped with `policy_version`. **Always run the alternatives in
   SHADOW alongside the live one** (extend the `feat/exec-policy` evaluator) so the frontier keeps
   being estimated while we trade — behaviour evolves on evidence, automatically, without a redeploy.

5. **Risk gate (wire the orphans).** Before sizing: per-signal cap (**$50**, hard); flat-**shares**
   sizing (not flat-$); `entry_floor 0.45`; daily deploy cap 13% (hard ceiling 16%), governed by
   **N_eff, not nominal market count** — *size the GAME, not the position* (a heat dome or a stacked
   World-Cup game is one bet, and 17 positions on one game is one bet). Kelly ladder stays
   **λ-gated**: `1/16` only if λ CI-lower ≥ 0.25; `1/12` only if ≥ 0.50. Today λ̂ ≈ 0.15, **so the
   ladder self-vetoes to flat — that is correct behaviour, not a bug to fix.**

6. **Ops surface** — board page + ntfy: armed/halted state, open orders, today's notional, realized
   vs decision-ask slippage, fill rate, halt reason. Per the noise policy: **push only when Tue must
   act** (halt fired, arming expired, reconcile mismatch). Silence otherwise.

---

## 4b. PER-ARM NUANCE — one engine, N configured strategies (Tue, explicit requirement)

**There is no global setting.** A single hard-coded execution posture is a design error: the arms have
*different physics*, and the same policy that earns money on one loses it on another.

- **Weather** — daily markets, no in-play events ⇒ **price barely moves; latency is cheap and the BOOK
  binds.** A patient maker rest is nearly free here. Cancel windows can be long. Size is the risk.
- **Sports (`favorite`, `elite_fresh_fav`)** — a favourite's ask drifts toward 1.0 *as the match runs*
  ⇒ **a patient rest is adversely selected by the clock itself**: wait and you fill only when the
  price came back, i.e. when the bet is going wrong. Short cancels, small δ, tighter TTL.
- **`proven_router` / hot-lane** — the edge is **FRONT-LOADED**: only **28–36%** of signals ever
  retrace to the sharp's price. A resting bid here *structurally misses the winners.* This is the one
  arm where a fast(er) taker or a very small δ chase may genuinely dominate.

⇒ Every execution parameter is a **per-arm** (and where warranted, per-`family × band`) field, not a
global: `policy_kind, δ_max, chase_step, T_cancel, signal_TTL, max_quote_age, max_ask_drift,
size_cap, entry_floor, band, take_fallback (yes/no), max_concurrent, daily_notional_cap`. Defaults
inherit from a base profile; an arm overrides only what it needs. **Each arm carries its own
promotion rung (§7) independently** — weather can be at paper while the router is still shadow, and
one arm's halt must not silently halt the others (though `MasterOff` halts everything).

**And each arm's policy must be *earned*, not assumed:** the shadow A/B (§4.4) runs the alternative
policies per-arm continuously, so the per-arm frontier is re-measured on that arm's own fills. Where
an arm has too little data to choose, the config must **default to the cheaper-to-be-wrong policy**
(skip / small size), and say so in the report.

## 4c. EDGE MAINTENANCE — the "never negative for long" machinery (Tue, explicit requirement)

The honest constraint first: **no bot can promise it is never negative.** With ~20 correlated weather
signals resolving together, a losing *day* is a single coin flip, and long losing streaks are the
*expected* behaviour of a thin real edge. What a bot **can** guarantee is that (a) losses are
**bounded**, (b) a **decayed edge is detected and stood down from quickly**, and (c) we do not keep
paying a tax to a strategy that has stopped working. Anything stronger than that is a lie, and a bot
that promises it will blow up. **Build (a)-(b)-(c); refuse to promise more.**

**Bounded loss (hard, mechanical):** per-signal cap, N_eff-governed daily notional cap, day stop-loss
(5%), max drawdown (15%), slate stop (−5 units) — all latching, all cancel-then-halt.

**Edge-decay detection (per arm, continuous):** each arm carries a live, one-sided lower-bound estimate
of realizable ROI on **its own real fills** (cluster-robust at the resolution DAY, not the market —
one heat dome is one cluster). Plus a **CUSUM / sequential change-point detector** on realized
per-turn P&L to catch a *break* faster than a CI can, and a **live slippage monitor** (realized fill
vs decision ask) — because the most likely way we go quietly negative is **not** the pick decaying
but **the fill getting worse** (more competition, thinner books, our own impact).

**Graded, automatic response (a ladder, not a cliff):**

| Trigger | Response |
|---|---|
| Slippage over budget, or fill rate collapses | **De-size** that arm (halve), re-measure |
| Rolling ROI LB crosses 0 | **Demote a rung** (real → paper) automatically; keep accruing |
| CUSUM change-point fires | **Halt that arm**, alert Tue, require human re-arm |
| θ LB ≤ 0 over ≥6 forward weeks, or LODO fails, or the belief-blind null fails | **RETIRE the arm** (the frozen kill rule — already prereg'd) |
| Day stop / max DD / master-off | **Halt everything**, cancel all resting orders, latch |

**Demotion is automatic and instant; promotion is evidence-gated and human-approved.** Asymmetric on
purpose. An arm that halts itself keeps running in **shadow**, so if the edge returns we can see it
without risking money to find out.

**The portfolio view:** arms must be sized against **N_eff, not arm count** — `favorite` and
`weather_fav` were selected partly *because* their day-level correlation is low (|corr| < 0.3 is a
frozen gate condition). Diversification here is a real, measurable lever against long negative
stretches, and it is the **only** honest one we have. Track and report N_eff continuously; if the arms
converge (correlation rises), the daily cap must fall automatically.

## 5. PRECONDITIONS (blocked on Tue — do these first, they "start the clock")

- Merge/rebase **`feat/exec-policy`** (it is the only forward instrument that says which policy is
  viable; its `041` migration number now **collides** with main's next free slot — renumber).
- Deploy the **D4 fresh-first ask capture** (`e74f4e7`) and the **`startTs` ingestion fix**.
- **Add weather to the `clob_price_tape` subscription set** — the tape has **ZERO weather rows**, so
  our live arm's realizable price is currently *unmeasurable*.
- Add `seen_at DEFAULT now()` to `trader_fills` (the cheapest instrument in the system).
- Enable `LIVE_FILLS` (kills the ingestion tail — a *data-quality* win, **not** an edge).
- ⚠️ **The autoupdater auto-deploys `main` to prod within minutes of a merge.** Any executor code
  merged to main lands in the running container automatically. **Default-OFF flags are therefore a
  safety-critical requirement, not a style choice.**
- **Jurisdiction / ToS / tax:** confirm eligibility to trade and to trade *programmatically*, and how
  fills are reported. This is a **human decision and a hard gate** — the bot must not be armed until
  it is answered. Do not design around restrictions.

---

## 6. THE LEARNING LOOP (what makes this "future-proof")

Real fills are the only thing that can close our three open unknowns: **(1) our own market impact**
(the capacity curve walks a *snapshot* book ⇒ real capacity ≤ measured), **(2) the true maker fill
rate and its adverse selection**, **(3) the real δ×cancel frontier.**

So the executor must, on every order, write back: realized fill px vs decision ask (**slippage**),
fill rate by (δ, T_cancel, band, family), `wr_filled` vs `wr_missed` (**the adverse-selection
detector**), and impact (book before vs after our order). A weekly job re-estimates the frontier and
**proposes** a policy-config change — Tue approves. Same evidence bar as always:
**(a) a control/placebo arm, (b) a significance test, (c) explicit n + dispersion.** A number without
those is a hypothesis, and **must never be the basis for risking money.**

---

## 7. THE PROMOTION LADDER (monotone; each rung needs evidence, and any rung can demote)

| Rung | Mode | Money | Unlocks when |
|---|---|---|---|
| 0 | **Shadow** | $0 | The state machine, clamps, reconcile, and kill-switch all pass their tests. Decisions logged, nothing sent. |
| 1 | **Paper-at-real-ask** | $0 | ≥2 disjoint weeks of clean decision-time asks; ask-lag p50 < 15 min. This is what the frozen gate actually needs. |
| 2 | **Micro-real** ($1–5) | ~$50 total | Rung 1 green **and** the frozen gate re-run at the captured `entry_ask` **passes**. Purpose is *plumbing truth* (auth, fills, reconcile, settlement), **not** P&L. |
| 3 | **Pilot** ($50/signal cap) | ≤ $1k/day | Micro-real reconciles 100% clean for N days; measured slippage within budget; impact measured. |
| 4 | **Scaled** | > pilot | Only against *measured* capacity including our own impact. Never against a snapshot book. |

**Be willing to hear NO at Rung 2.** If the gate fails at the price we actually pay, the answer is
**retire the arm**, not re-analyse it. And the open thesis risk stands (Rung 4 of the readiness
ladder): the nulls bracket us — **p=0.0005** vs a random-favourite pool but **p≈0.5** vs a pool of
favourites one sharp already bought. If consensus adds ~nothing over one sharp, the entire copy
apparatus is unnecessary and the "edge" may be **favourite-longshot bias, not alpha.** The executor
should be built so that discovering this is *cheap*, not so that it's *unthinkable*.

---

## 8. WHAT IS LICENSED TO TRADE (today)

- **`favorite`** (the champion): band 0.65–0.98, ≥3 one-sided top-40 backers, ≤1 opposer,
  `price_std ≤ 0.10`, ≤48h. Standing realizable floor **+5.6%**. Caveat: regime-persistence read is
  **`SOCCER-ARTIFACT`**.
- **`weather_fav`**: the strongest candidate — LODO survives, null p=0.0005, low correlation with the
  champion — **but uncertified on the only basis the gate accepts.** Trade it **in paper at the real
  ask, $50/signal, flat-shares, certification band 0.71–0.90** (capture is 0.71–0.98; 0.90–0.98 is
  the **"win-rate trap"**, LB −2.1%). This *is* Rung 5.
- Everything else — `favorite_v2`, `favorite_liq`, `elite_fresh_fav`, `frontier_k3e/k2a`, `soft_*` —
  **shadow only.**
- **DO NOT RESURRECT** (each killed with evidence): market-making (falsified + unfieldable),
  MM-filter *as an arm* (keep the screen, kill the arm), congregation / per-sport specialists,
  favorite-consensus "certified", leaderboard rank as skill (**refuted 5 ways** — this is why
  `favorite_v2`'s rank gate is "fraught"), latency-as-edge, `weather_low_fav` (**LODO fails**,
  retired), and the 9 removed noise arms.

---

## 9. ANTI-GOALS (say no to these, loudly)

Chasing turnover for its own sake. Crossing the spread by default. Sizing up on a hot streak.
Martingale/recovery sizing. Auto-arming. Auto-un-halting. Trading an uncertified arm with real money
because it "looks good." A fill model. Trusting local state over the exchange. Trading while the data
pipeline is stale. Rebuilding what `pilot.rs` / `exec_policy.rs` / the risk engines already do.

---

## 10. DEFINITION OF DONE (this run)

1. `clob-client` crate: authed, signs, places, cancels, reads fills over the user WS. **Proven against
   the real API in Rung-2 micro-real mode** — an unproven client is not done.
2. `pilot` wired into `live.rs`; `Placer` trait with Shadow/Paper/Live impls; **default OFF**.
3. The order lifecycle state machine, with I1–I10 each covered by a test — including a **crash-mid-send
   recovery test**, a **cancel-race test**, and a **wedged-loop kill test**.
4. The declarative, versioned, hot-reloadable policy layer + shadow A/B of alternative policies.
5. The risk gate wired (per-signal cap, flat-shares, N_eff-governed daily cap, λ-gated Kelly ladder).
6. The learning loop writing back real slippage / fill-rate / adverse-selection / impact.
7. `reports/EXECUTOR-READINESS.md`: honest rung, what's proven, what's assumed, what would falsify it.
8. Green `cargo test` + `cargo clippy`. Nothing merged to `main` that can place an order while
   un-flagged — remember, **merge = deploy**.

**Report honestly.** A timed-out or partial run is *incomplete + resumable*, never "done." And a
number without a control, a significance test, and an explicit n is a **hypothesis** — never a reason
to risk money.
