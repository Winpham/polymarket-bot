# PRE-REGISTRATION — Maker-Copy G3: forward maker-fill simulator

**UTC stamp:** 2026-07-09T01:14:24Z · **Instrument:** `scripts/maker_copy_g3.py`
**Author:** autonomous run (RUN-MAKER-COPY-G3-FORWARD) · **Status:** frozen BEFORE any
outcome-correlated analysis. Paper-only, read-only, promotes nothing. Extends D26 (KILL+PARK).

This file is committed **before** the simulator is run against resolved outcomes. It exists so the
success criteria are chosen while blind to whether the idea succeeded — the discipline that would
have caught the G2 "+4.8% LB" artifact (2 bugs: units, backwards complement rule).

---

## 0. Thesis under test (the seductive trap)

We are **copiers**: we act *after* a followed sharp fills. Posting a maker BUY "at the sharp's
price" means resting a bid **below** the current market (the sharp already lifted the ask). A resting
bid only fills when price comes **back down** to it — i.e. when the position moves **against** us.
Mechanically this **fills the losers and misses the winners** (adverse selection). G3 measures
whether that is what actually happens, at live-trading fidelity, on the forward tape. **The
adverse-selection gap is the primary verdict.** A single flattering "maker = +X%" number is a
failure of the run regardless of sign.

## 1. Universe (frozen)

- **Primary universe:** `consensus_signals` with `strategy='favorite'`, `resolved=true`,
  `initial_mean_price IS NOT NULL`, `condition_id IS NOT NULL`, that additionally have
  (a) ≥1 followed-sharp **BUY** fill in `trader_fills` on the same `(condition_id, outcome_index)`
  within `[T−5m, T+5m]` (T = `first_detected_at`), **and** (b) ≥1 `clob_price_tape` row on that leg
  strictly after T. This is the set a maker-copier could actually have quoted on.
- **Rationale for `favorite`:** it is the only arm with a baselined edge anywhere
  (`regime_net_edge` maker LB +0.28% ≈ 0) and the arm all prior maker work (G2/G2b,
  `maker_fill_sim`) and the honest ledger use — apples-to-apples.
- **Observed universe size at freeze (structural only, NO outcome inspection):** N = **20** resolved
  fillable signals; **19** distinct event-clusters (`COALESCE(event_slug, condition_id)`); **2**
  distinct calendar days; all 20 carry a captured `entry_ask` (real decision-time ask, not fallback);
  mean anchor ≈ 0.79. **Win/loss composition was NOT inspected.**
- **Secondary (robustness) universe:** same construction but pooling all non-`_blind` strategies —
  reported for context/N only, never as the primary verdict (heterogeneous selection rules).

## 2. The resting-bid price P (frozen definition)

- **P (primary) = the price of the EARLIEST followed-sharp BUY fill** on `(condition_id,
  outcome_index)` in `[T−5m, T+5m]`. This is the fill our poll would copy — the literal "their
  entry." (`trader_fills.price`, 0–1 share scale.)
- **P (robustness variant) = size-weighted mean sharp BUY price** in the same window.
- Clock: `trader_fills.ts` = exchange clock, same domain as tape `exch_ts`. Anchor on those; never on
  `recv_at`/`ingested_at` for fill-timing decisions.

## 3. Fill models — reported as a MENU, side by side (never one number)

Queue position is unknowable from top-of-book tape, so we **bound** it. Rest window =
`[T + lag, T + cancel]`. Fill decision uses `clob_price_tape` rows in that window.

- **OPTIMISTIC (touch = fill):** filled if `best_ask ≤ P` occurs at any tape row in the window
  (`book` or `price_change`). Assumes 100% queue capture. Labeled the fantasy ceiling.
- **REALISTIC (trade-through with size):** filled only if `price_change` rows **print at
  `last_price ≤ P`** with cumulative notional `Σ(last_size × last_price) ≥ stake` while the order
  rests. Queue haircut: credited fill capped at pro-rata share of printed size (report fill-fraction).
  NOTE the tape is inflection-coalesced (≤1 row/asset/s), so printed size **understates** true
  volume ⇒ REALISTIC fill rates are a **lower bound**.
- **PESSIMISTIC (strict cross):** filled only if `best_ask < P` **strictly** with size ≥ stake
  (price moved *through* us). Approximates being last in queue.

## 4. Sweeps (frozen grids)

- **Decision lag** (we post *after* seeing the fill): `lag ∈ {0s, 12s, 60s}` (hot-lane vs poll
  cadence). Rest window starts at `T + lag`; any tape fill that occurred strictly before `T + lag` is
  **not capturable** and is dropped. (No look-ahead.)
- **Rest window / cancel-after:** `cancel ∈ {5m, 15m, 60m, until-resolution}`. Unfilled at cancel ⇒
  **no bet** (abstain; NOT a taker fallback — that would defeat the maker test).

## 5. Cost / P&L contract (matches the honest ledger for apples-to-apples)

- `flat_stake = 100`, `fee_pct = 0.02` (repo modeled buffer; also report `fee=0` since Polymarket's
  posted trading fee is currently zero — the 2% is a cushion, not an exchange charge). No maker
  rebate modeled (conservative for maker).
- Maker P&L on a **filled** signal: `pnl = stake × ((outcome_won − P)/P − fee)`. Booked **only** on
  signals a fill model says filled.
- Taker reference (what we pay today), on the **same** signals:
  `entry_taker = COALESCE(entry_ask, initial_mean_price + 0.01)`;
  `pnl_taker = stake × ((outcome_won − entry_taker)/entry_taker − fee)`.
- **Cluster-robust LB:** event-cluster on `COALESCE(event_slug, condition_id)` via
  `effective_n.cluster_robust`, read at small-cluster t(G−1) via `regime_edge.lb_small_cluster`
  (imported as `maker_capacity.py` does). A point estimate is not a verdict; the event-clustered LB
  is. Also surface the **day-cluster** LB (G≈2) as the persistence wall.

## 6. Metrics (frozen)

**Primary:**
1. **Adverse-selection gap**, per fill model: `ROI(filled) − ROI(missed)` and
   `win_rate(filled) − win_rate(missed)`, event-clustered. Materially negative ⇒ the trap; **say so.**
2. **Filled-subset ROI** and its cluster-robust LB (after fees), per fill model.

**Secondary:**
3. **Miss-the-winners fraction:** of signals with `outcome_won=1`, share whose resting bid failed to
   fill (per model). The mechanism made visible.
4. **Fill rate** and **mean fill-fraction** (partial fills), per model × lag × cancel.
5. **Head-to-head vs taker** on the same fillable signals: maker-filled ROI vs taker ROI
   (on the filled subset AND on all fillable signals with unfilled = abstain).

## 7. Verdict banding (frozen N-thresholds)

Let `n_filled` = resolved filled signals for a given fill model.

- **INDETERMINATE-BY-POWER** if `n_filled < 30` **OR** distinct day-clusters `< 5`. Report point
  estimates + CIs, state the power/persistence gap, set to accrue, **do NOT promote.** (Given the
  freeze-time structural read of 20 signals / 2 days, this is the expected outcome.)
- **GO** requires ALL of: (i) `n_filled ≥ 30` and ≥5 day-clusters; (ii) filled-subset cluster-robust
  LB clears zero **after** fees; (iii) adverse-selection gap **non-negative**; (iv) survives the §8
  adversarial audit; (v) maker-filled ROI **≥** taker ROI on the same fillable subset. Any failure ⇒
  not GO.
- **KILL (extend D26):** if, at adequate power, the adverse-selection gap is materially negative and
  filled-subset LB is ≤ 0 — the trap is confirmed forward.

## 8. Adversarial audit gate

Before any positive read is reported as real, spawn ≥3 **independent** Opus skeptic reviewers
(stance = "refute this result"), isolated. Minimum checks: look-ahead leakage, survivorship
(only-resolved bias), clock skew (`exch_ts`/`ts` vs `recv_at`), queue-capture optimism, event-cluster
correctness, units (SHARES vs USD), "filled" defined to require real crossing **volume** not a quote
flicker. **Default any unresolved doubt to REFUTED.** Only survivors are reported as real. Re-derive
the two 2026-07-05 bugs as a sanity check that the instrument would catch them.

## 9. Anti-regression fixtures (must be in `--selftest`, must fail loudly if a historical bug returns)

- **Units:** a fixture where treating `size` as USD vs SHARES flips the read; assert SHARES.
- **Complement direction (if complement flow modeled):** deep-longshot buy at `≤ 1−L` must NOT count
  as fill flow; only `≥ 1−L` mints against a resting BUY-fav @L.
- **No look-ahead:** no tape row at time `< T + lag` may produce a fill.
- **Clock domain:** alignment/fill-timing uses `exch_ts`/`ts`, never `recv_at`/`ingested_at`.
- **Adverse selection visible:** a fixture where the runaway winner is missed and the reverting loser
  fills ⇒ `win_rate(filled) < win_rate(all)`.

## 10. Guardrails (binding)

No real capital, no live Polymarket order under any outcome. D26 KILL+PARK and the legal-posture gate
stand. Never flip the P&L to a maker-assumed price on signals not proven to fill. Never report a
single maker number. If the run times out or the tape is too shallow: "incomplete + resumable,
INDETERMINATE-BY-POWER" with exactly what accrued — never "done."
