# PRE-REGISTRATION — Weather EXECUTABLE gate (size-aware)

**Frozen:** 2026-07-13T00:00:00Z. **Branch:** `feat/weather-deepen`. **Amends**
`PREREG_20260712T052717Z_weather.md` + its ADDENDUM by **ADDING size-aware floors ONLY**. Nothing is
loosened. Written BEFORE any `entry_vwap` has accrued, so it is belief-blind w.r.t. the record it judges.
Paper-only; arms nothing; places no orders.

## 0. What changed since the last gate

The last gate's θ was priced at the captured **`entry_ask` — the TOUCH**. That is the price only an
infinitesimal stake gets. Measured on 59 live cert-band books, the weather ladder holds a median
**~$54 within 1c of the touch**, so any stake we would really trade **walks the ladder** and pays a
strictly worse VWAP. **A forward record booked at the touch overstates P&L at every size that matters.**
Mig 043 (`entry_vwap`) records what a taker of a REAL stake actually pays. This gate is priced on it.

## 1. The locked objective (size-aware; supersedes the touch-priced θ)

> **θ(S) = cluster-robust one-sided 95% LOWER BOUND of realizable ROI-on-turnover, clustered at the
> resolution DAY, with entry = `entry_vwap` — the VWAP of buying a REAL stake `S` by walking the live
> ask ladder at DECISION TIME** (fee `0.03·p·(1−p)`). A signal with no captured `entry_vwap` is
> EXCLUDED. Every θ must report `entry_vwap` coverage % and the **fill ratio** (`entry_vwap_filled / S`).

**Certification cell:** the **BLIND BAND rule, 0.71–0.90** — NOT the consensus arm. Settled: the
≥3-backer consensus adds **+0.14pp** (nothing) over a single-sharp favorite while *costing* ~19% of the
signals; the null (p≈0.5) and the specialist scan (+2.1pp, not Bonferroni-significant over 1,507
screened) agree from two other directions. **The edge is the BAND, not the crowd.**

**Trading stake `S = $100`** (the measured sweet spot: LB +9.0%, LODO +7.8%, 100% fills).

## 2. ADDED floors — ALL required (nothing below is loosened)

- **E1 — SIZE-AWARE θ.** θ($100) LB **> +5.6%** (the champion's honest floor) on ≥2 disjoint FORWARD
  weeks. Priced at `entry_vwap`, never the touch.
- **E2 — FILL RATIO.** Mean `entry_vwap_filled / S` ≥ **0.98**. If the book cannot absorb $100 without
  partial fills, the strategy does not exist at that size — drop `S` and re-gate, do not fudge θ.
- **E3 — CAPACITY CURVE HONESTY.** Report θ at S ∈ {$50, $100, $250, $500}. The stake at which the LB
  stops clearing +5.6% **IS** the capacity ceiling (measured in-sample: ~$250). If forward capacity is
  materially below $100, weather is **NOT BANKABLE at a useful size** — a valid, money-saving kill.
- **E4 — SLIPPAGE-VS-MODEL.** The realized forward `entry_vwap` must not be worse than the in-sample
  modelled VWAP by **> 1.5c** at the same stake. A larger gap means the book shapes we measured do not
  generalise, and the whole capacity model is void.
- **E5 — the original gate STANDS**: ≥20 day-clusters, ≥2 disjoint forward weeks, LODO-by-week LB > 0,
  Bonferroni, and B1–B5 from the prior addendum.

## 3. Decision (frozen)

- **PASS** (E1–E5 + the original gate): weather is an executable, capacity-capped **SATELLITE** —
  earns a deliberate human promotion review to a paper executor at $100/signal. **It is NOT a champion
  replacement and must never be scaled into that role** (its book holds 0% >$1k vs the champion's 35%).
- **FAIL / RETIRE**: θ($100) LB ≤ +5.6%, or E2/E4 breached, or LODO collapses. A dead weather arm is a
  valid outcome — it saves the build.
- **INDETERMINATE** until `entry_vwap` coverage accrues. Expected for the next ≥2 weeks.

## 4. What is NOT claimed

Weather is **not** proven profitable. It is proven **promising and executable at small size** on a
validated basis, with a measured capacity ceiling. The forward `entry_vwap` record is the arbiter, and
it has not accrued. **No money moves on this until E1–E5 clear.**

## 5. Guardrails (unchanged)

Paper-only; no orders; arms nothing; real-money eligibility UNCHANGED; `CAPTURE_BOOK_DEPTH` is a
MEASUREMENT flag (reads the same public `/book` we already read; places nothing); every incumbent arm +
the champion + `ConsensusParams::default` + `honest_paper_ledger` BYTE-IDENTICAL (mig 043 is additive
and nullable; no incumbent read path touches the new columns).
