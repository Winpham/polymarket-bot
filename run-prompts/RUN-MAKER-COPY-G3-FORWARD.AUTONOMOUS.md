# RUN — Maker-Copy G3: forward maker-fill simulator (measure, don't assume)

**Mode:** long autonomous run. Repo: `~/polymarket-bot` (Rust + Postgres + `scripts/` Python
instruments). **Paper-only. No real capital. Promotes nothing.** This run builds a *measurement
instrument*, not a trading path.

---

## 0. What you are being asked, in one sentence

Tue wants to copy the traders we follow using **maker orders only**, resting a bid at **the exact
price the sharp filled at**, so we get their entry instead of paying the taker spread. Your job is
**not** to assume that works and re-book the ledger at the better price. Your job is to **build G3 —
the forward maker-fill simulator — and let the measured fill-rate and adverse-selection decide**,
honestly, at the fidelity of what live trading would actually turn out to be.

This idea has a name in our own history and it has been **wrong twice**. Read §1 before you write a
line of code. If you finish this run having produced a single flattering "maker = +X%" number, you
have failed, regardless of how green it looks.

---

## 1. Why this is the most seductive trap in the project (read first)

We are **copiers**: we act *after* the sharp fills. When a sharp buys a favorite they typically lift
the ask and push the price up. By the time our poll sees their fill, the market is already **at or
above** their entry. To post a maker order "at their price" we must **rest a bid below the current
market**. A resting bid only fills when price comes **back down to it** — i.e. when the position
moves **against** us:

- Favorites that **win** drift toward $1.00 → our bid **never fills** → **we miss the winners**.
- Ones that **lose / revert** come back down → **our bid fills** → **we catch the losers**.

That is **adverse selection**, and it is the whole ballgame. The maker-only copier systematically
**fills the bad ones and misses the good ones**. This is exactly what the prior work found.

### The receipts you must not repeat
- **G2** (`scripts/maker_capacity.py`) and **G2b** (`scripts/maker_capacity_fulltape.py`) measured
  fill capacity for a resting maker copy. **v1 claimed +4.8% LB. An audit (3 reviewers, 2026-07-05)
  found 2 bugs that fully explained it:**
  1. **Backwards complement rule** — used `price ≤ 1−L` instead of `≥ 1−L`, counting deep-longshot
     buys that *cannot* mint against the resting bid. (fixed `maker_capacity_fulltape.py:127`)
  2. **Units error** — treated data-api `size` as USD when it is **SHARES**; deployable maker
     capital = `shares × L`. (fixed `maker_capacity_fulltape.py:130-131`)
  Corrected verdict: **thin / adverse / EDGE ≈ 0.** The only baselined maker edge anywhere is
  `regime_net_edge` at **+0.28% LB ≈ 0**.
- **D26** in `DECISIONS.md:869-900` ("Market-making Stage-0") is a settled **KILL + PARK**: half-spread
  median 0.50¢ vs adverse mid-drift 6.5¢ ⇒ net **−6.2¢, hazard 13× reward**.
- Both G2/G2b **explicitly punt the one unanswerable question to G3**: the realized **capture
  fraction** — what share of the flow *our* resting bid actually wins — is a **queue-position**
  question the historical tape could not answer. **G3 = forward live paper-quoting. It was never
  built.** (`maker_capacity_fulltape.py:13-15,166-172`)

### What changed — why G3 is buildable now
Since 2026-07-07 we ingest **`clob_price_tape`** (WS top-of-book, ~1 Hz inflection) and
**`signal_price_trajectory`** (45 s dense mid+ask). That is precisely the forward data G3 needed. So
this run **builds G3 to measure the idea** — it does not reopen D26's deploy decision (still KILL +
PARK, still gated on legal posture; **no live Polymarket capital under any outcome of this run**).

**Caveat that defines the whole run:** the tape is only ~2 days deep. This is a **forward-accruing**
measurement. You will likely finish **INDETERMINATE-BY-POWER** and that is a *correct, honest*
outcome — set it up to accrue and re-run, do not manufacture significance.

---

## 2. Data you have (verified — build against these exact facts)

All prices are **0–1 probability scale** (dollars-per-share), **not** cents. Postgres is inside the
compose container (no host port):
`docker compose -f docker-compose.consensus.yml exec postgres psql -U bot -d polymarket`

**`clob_price_tape`** (`migrations/040_live_ingestion.sql`, live since 07-07): `asset_id` (token_id),
`condition_id`, `outcome_index`, `event_type` (`'book'`|`'price_change'`), `best_bid`, `best_ask`,
`last_price`, `last_size` (SHARES, price_change only), `side`, `exch_ts` (**NULL on `book`
snapshots**), `recv_at`. Written by `copy-trading-bot/src/cycles/live_tape.rs`: **event-driven,
on-change dedup, coalesced to ≤1 row/asset/second (1 Hz), inflection-only** (not raw ticks). Universe
= assets a followed trader filled a sports pick on within the last 6 h.

**`trader_fills`** (`migrations/026`): `wallet`, `condition_id`, `outcome_index`, `side`
(`BUY`/`SELL`), `price` (**exact sharp entry, 0–1**), `size_usd`, `ts` (**exchange clock**),
`resolved`, `outcome_won`. Fed by the 1-min consensus poll **and** the 12-s hot lane.

**`signal_price_trajectory`** (`migrations/034`): `signal_id → consensus_signals(id)`,
`secs_after_fire`, `mid`, `ask` (executable best ask), `n_backers`. 45 s cadence, first ~15 min of a
signal's life.

**`consensus_signals`** (`migrations/021`, the join spine): `condition_id`+`outcome_index` (UNIQUE),
`first_detected_at` (**fire time T**), `entry_ask` / `entry_ask_mid` / `entry_ask_at` (real
decision-time ask, present only when `CAPTURE_ENTRY_ASK=true`), `initial_mean_price` (at-fire mid,
the CLV anchor), `resolved`, `outcome_won`, `event_slug`.

### Alignment recipe (the core join — get this exactly right or the whole run is garbage)
1. Signal fires at `T = consensus_signals.first_detected_at` on `(condition_id, outcome_index)`.
2. Sharp fill(s): `trader_fills` rows on the same `(condition_id, outcome_index)` with `ts ≈ T`,
   giving entry `P = price` and `side`.
3. Walk `clob_price_tape` for that leg **strictly after T** (join on `condition_id`+`outcome_index`;
   no token resolution needed). Order by `exch_ts` for `price_change` rows, **fall back to `recv_at`
   when `exch_ts` is NULL** (`book` snapshots). `trader_fills.ts` and tape `exch_ts` are the **same
   exchange clock** (≈zero skew) — anchor on those, never on ingest/write time.
4. A resting BUY at `P` is *candidate-fillable* when `best_ask ≤ P`, or a `price_change` trade prints
   at `≤ P`. **Whether it actually fills is the queue question — see §4.**

---

## 3. Cost / P&L contract (match the honest ledger exactly, for apples-to-apples)

Reuse the existing honest-P&L contract so maker output is directly comparable to the taker ledger:
- `flat_stake = 100`, `fee_pct = 0.02`, **event-cluster** on `COALESCE(event_slug, condition_id)`.
- `pnl = stake × ((outcome_won − entry)/entry − fee_pct)`.
- Taker reference entry (what we pay today): `COALESCE(entry_ask, initial_market_price + 0.01)`
  (`consensus.rs:752`). The **maker entry** you are testing is the sharp's `P` (the resting-bid
  price) — but **only booked on signals your fill model says actually filled**.
- Cluster-robust lower bound via the shared libs `effective_n.py` (`cluster_robust`) and
  `regime_edge.py` (`lb_small_cluster`, `FOLLOWER_TAX`), imported the way `maker_capacity.py:55-57`
  does. **A point estimate is not a verdict; the event-clustered LB is.**

---

## 4. The simulator — spec (build `scripts/maker_copy_g3.py`)

Follow the repo convention (template: `scripts/maker_fill_sim.py`): one self-contained
`#!/usr/bin/env python3` instrument in `scripts/`, Postgres via a `docker exec … psql --csv` helper,
long docstring stating thesis/method/caveats/invocation, a `--selftest` with fixtures, output = a
`reports/maker_copy_g3.json` artifact + printed table. **Read-only. No migration needed** for the
measurement (you only read existing tables). Do **not** touch Rust for the core deliverable.

### 4.1 Pre-register BEFORE you look at outcomes (belief-blind gate)
Freeze, in `reports/PREREG_<UTCstamp>_maker_copy_g3.md`, **before** running against resolved
outcomes: the policy menu, the fill models, the decision-lag values, the primary/secondary metrics,
and the N-thresholds for each verdict band. Commit that file first. This is the discipline that
would have caught the +4.8% — you decide what counts as success while blind to whether it succeeded.

### 4.2 Fill models — report a MENU side-by-side, never one number
The queue position is unknowable from top-of-book tape, so you **bound** it. Report all of these as
separate columns; the truth lives between them:
- **OPTIMISTIC (touch = fill):** filled if `best_ask ≤ P` ever occurs in the rest window. This is the
  old fantasy ceiling — label it as such. Assumes 100% queue capture.
- **REALISTIC (trade-through with size):** filled only if a `price_change` trade actually **prints at
  ≤ P** with cumulative `last_size × price ≥ stake` while our order rests — i.e. real volume crossed
  our price, not just a quote that flickered. Apply a **queue haircut**: we win at most our
  pro-rata share of that printed size.
- **PESSIMISTIC (strict cross):** filled only if `best_ask < P` strictly (price moved *through* us)
  with size ≥ stake. Approximates being last in queue.

### 4.3 The realism dimensions — model each or bound it explicitly; never assume it away
This is the "what live trading actually turns out to be" checklist. Each item is a way the naive
ledger lies:
1. **Adverse selection (PRIMARY VERDICT):** compute ROI/win-rate of the **filled** subset vs the
   **missed** (unfilled-by-resolution) subset, per fill model, event-clustered. If filled ROI is
   materially below missed ROI, the idea is the trap — **say so**. This single gap decides the run.
2. **Miss-the-winners asymmetry:** report, of signals whose favorite **won**, what fraction our
   resting bid **failed to fill** (because it drifted up). This is the mechanism made visible.
3. **Latency / decision lag:** we post *after* seeing the fill. Sweep `decision_lag ∈ {0, 12s,
   60s}` (hot-lane vs poll cadence) — start the rest-window at `T + lag`, and drop any fill that the
   tape shows already happened before `T + lag`. A maker fill that only existed in the pre-lag window
   is **not capturable**.
4. **Rest window / cancellation:** sweep cancel-after `T ∈ {5, 15, 60}` min and "rest until
   resolution". Unfilled at cancel ⇒ **no bet** (not a taker fallback — that would defeat the point).
5. **Partial fills & capacity:** stake is $100; check there is ≥ $100 of eligible printed size at ≤P.
   Report fill-fraction, not just a binary.
6. **Fee / rebate:** keep `fee_pct = 0.02` unless you can cite Polymarket's actual maker fee/rebate
   from a source in-repo; if maker fee differs, model it explicitly and note the citation.
7. **Book-snapshot NULL-clock:** `book` rows have NULL `exch_ts`; ordering on `recv_at` introduces
   local-latency skew. Prefer `price_change` rows for fill decisions; treat `book` as context only.
   Document this limitation.

### 4.4 Guard against the historical bugs — bake them in as unit tests
In `--selftest`, include fixtures that **fail loudly** if either 2026-07-05 bug returns:
- **Units:** a fixture where treating `size` as USD vs SHARES flips the verdict; assert SHARES.
- **Complement direction:** if you model complement/mint flow, assert `≥ 1−L` (a fixture with a
  deep-longshot buy at `≤ 1−L` must NOT count as fill flow).
- **No look-ahead:** a fixture proving no tape row at time `< T + lag` can produce a fill.
- **Clock domain:** a fixture proving alignment uses `exch_ts`/`ts`, not `recv_at`/`ingested_at`.

---

## 5. Adversarial audit gate (mandatory before any positive read is trusted)

The core lesson from G2: **a single-pass "positive" is untrustworthy until adversarially audited.**
Before writing the verdict, spawn **independent skeptic reviewers** (isolated, stance = "refute this
result") whose job is to find the bug that makes any favorable number fake. They must check, at
minimum: look-ahead leakage, survivorship (only-resolved bias), clock skew, queue-capture optimism,
event-clustering correctness, units, and whether "filled" was defined to include price flickers with
no real volume. **Default the finding to "refuted" on any unresolved doubt.** Only a result that
survives this gate may be reported as real. Re-derive the two historical bugs as a sanity check that
your instrument would have caught them.

---

## 6. Verdict, reporting, forward accrual

- **Verdict banding (pre-registered N-thresholds):** with < ~30 resolved filled signals per model,
  the honest verdict is **INDETERMINATE-BY-POWER** — report the point estimates and CIs, state the
  power gap, and set it to accrue. Do **not** promote. A GO requires: filled-subset LB clears zero
  **after** fees **and** the adverse-selection gap is non-negative **and** it survives §5.
- **Compare to the taker honest ledger** head-to-head on the *same signals*: maker-filled ROI vs the
  taker `COALESCE(entry_ask, mid+0.01)` ROI. The honest question is not "is maker positive" but "does
  maker-only beat what we already do, on the subset we can actually fill?"
- **Forward accrual:** the tape self-compresses and is ~2 days deep. Make the instrument idempotent
  and cheap to re-run as tape deepens (it reads accruing rows; nothing to persist for the
  measurement). Optionally add a `daily_run.sh` hook to re-emit the artifact.
- **Write-ups:** `reports/entries/2026-07-08-maker-copy-g3.md` (method, results, honest verdict,
  limitations) and append a **new `D##` record to `DECISIONS.md`** that **extends D26** — do not
  rewrite D26; add the forward evidence and the (almost certainly) still-parked decision.
- **Phase 2 (only if §5 survives with a real, non-adverse, better-than-taker read):** a persisted
  forward maker paper-ledger mirroring `honest_paper_ledger` (`UNIQUE(strategy,condition_id,
  outcome_index)`, running `cum_equity`, a distinct `strategy`/`fill_mode`) so it flows through
  `ledger_stats`/`equity_curve`/board `render_honest` unchanged. This needs **migration 041** —
  **coordinate the migration number first** (highest is 040; concurrent chats grabbing 041 diverge
  sqlx checksums and crash-loop the app; never edit an applied migration). Do **not** start Phase 2
  unless the measurement earns it.

---

## 7. Guardrails (hard constraints)

- **No real capital, no live Polymarket order, ever, under any result.** D26 KILL+PARK and the
  legal-posture gate stand. This run measures; it does not deploy.
- **Never flip the P&L to a maker-assumed price.** Booking the sharp's `P` on signals you did not
  prove would fill is the +4.8% / market_resid mistake again.
- **Never report a single maker number.** Always the fill-model menu + adverse-selection gap + LB.
- **Honesty of outcome:** if the run times out or the tape is too shallow, report
  **"incomplete + resumable, INDETERMINATE-BY-POWER"** with exactly what accrued — never "done."
- **Model discipline:** Opus for the audit/verdict reasoning; do not de-bias the skeptic reviewers
  with a weaker model. Fable at most one plan + one code pass if the join logic proves genuinely
  novel; otherwise Opus throughout.
- **Ship discipline (polymarket-bot conventions):** `scripts/` Python instrument, `--selftest` green,
  `reports/*.json` artifact, `reports/entries/` write-up, `DECISIONS.md` record, pre-reg committed
  first. Commit incrementally so a reaped long run is salvageable. Read-only against prod DB.

---

## 8. Definition of done

1. `reports/PREREG_*_maker_copy_g3.md` committed **before** outcome analysis.
2. `scripts/maker_copy_g3.py` exists, `--selftest` green (incl. the anti-regression fixtures of §4.4).
3. `reports/maker_copy_g3.json` emitted with the full fill-model menu, decision-lag/rest-window
   sweeps, the **adverse-selection gap**, the miss-the-winners fraction, cluster-robust LBs, and the
   head-to-head vs the taker ledger.
4. §5 adversarial audit run; only survivors reported as real.
5. `reports/entries/2026-07-08-maker-copy-g3.md` + a `DECISIONS.md` `D##` extending D26, with an
   **honest verdict** (expected: INDETERMINATE-BY-POWER, accruing) and the forward re-run path.
6. No real capital touched; nothing promoted.
