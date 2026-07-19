# PRE-REGISTRATION v3 — final-hour favourite late-convergence, forward paper test

**Frozen 2026-07-19. Supersedes v2 (2026-07-18) and v1 (2026-07-15). Paper/analysis only.
No live order, ever.**

**Legitimacy:** amended before any signal accrued — `SELECT count(*) FROM finalhour_paper_signals`
= **0**, verified at time of writing. No outcome-dependent choice was possible.

**What changed and why, in one line each:**
1. **`≥2 sports` DROPPED** (owner decision, Tue) — it was unsatisfiable and it was the wrong bar.
2. **`≥60` → `≥250` events** (forced by power analysis — the old gate could not detect its own effect).
3. **Reliability metrics defined, and explicitly NON-gating** (they do not discriminate; §5).
4. **Six anti-self-deception controls made binding** (§6).
5. **Settlement semantics corrected** — payouts are continuous, not binary (§4.3).
6. **A futility stop added**, so a dead arm cannot silently consume months (§7).

---

## 1. The claim, stated honestly

A thin US book underprices the LEADING favourite in the final ~30 minutes of a near-decided match.

**This is NOT "a 7% edge that clears the toll 6×".** The retrospective measurement is
**maturity-anchored**: the window is located by a timestamp knowable only *after* the fact, and
**every live-knowable price anchor is negative**. The honest statement is:

> There is a +6.29¢ effect in a retrospectively-defined 30-minute window. It is invisible to
> anything price-based in real time. Whether it is capturable rests entirely on an **untested
> assumption** — that a live game-state feed locates the same instant hindsight locates. That
> assumption is the product. This test measures it.

Supporting facts, carried forward: λ = **0.44 (LB 0.22)** at −30min, **0.10 (LB 0.00)** at −45min
(λ=0.73 is RETRACTED); profit survives a 3¢ haircut (+3.4¢, p=0.025); not concentration-driven;
anchor not circular; **exploratory-search derived**, so nominal p-values overstate.

**Prior:** the source docs' own read is *"one tournament-window away from being another
`favorite_v2`."* This project has produced five arms with better retrospective numbers, all dead.

## 2. Why `≥2 sports` was dropped — and what replaces it

v1/v2 required ≥2 sports. It became unsatisfiable when esports was ToS-held (bo3.gg `robots.txt`
disallows `/api/`, `b1e7d93`), leaving tennis the only admissible free feed.

It was also the **wrong instrument**. The bar existed as a proxy for durability, but the
cross-sport evidence is already established *retrospectively* (ATP/WTA + ITF + esports share the
same horizon signature). What the forward test must establish is different: **capturability at a
realizable price**. Two sports forward adds no durability evidence; it only makes the test
unrunnable.

**The artifact risk is retained where it actually lives** — *within* tennis, which is the
`favorite_v2` failure mode. **R3 and `≥2 tournament weeks incl. ≥1 non-Wimbledon` are UNCHANGED.**

## 3. Power — why `≥60` was never viable

Simulated against the **empirical** in-band ask distribution (463 liquid tennis markets, favourite
price at −30min, band [0.65,0.92]; per-event sd **0.3843**), one-sided 95% bootstrap LB:

| N events | power @ +6.29¢ | @ +4¢ | @ +2¢ |
|---|---|---|---|
| **60** (v1/v2) | **0.38** | 0.20 | 0.11 |
| 150 | 0.64 | 0.30 | 0.12 |
| **250 (v3)** | **0.80** | 0.41 | 0.13 |
| 700 | 1.00 | 0.74 | 0.22 |

Minimum detectable effect at N=60 is **+10.82¢** — *larger than the +6.29¢ the gate was built to
find*. False-positive rate is correctly calibrated (0.057 at N=60), so the test was not broken,
only far too small: **it was ~62% likely to kill a real, full-strength edge.** Every other guard in
this project aims at false positives; this one failed in the opposite direction.

**N is therefore ≥250 gate-eligible events.** Stated plainly: even at 250, power is only 0.41 if
the true forward edge is +4¢, and negligible at +2¢. A PASS is meaningful; a FAIL at N=250 does
**not** prove absence of a small edge, and must never be reported as if it did.

## 4. Universe, trigger, entry, settlement

### 4.1 Universe
US `aec-` tennis ATP/WTA game-winner markets; standard (non-exotic); liquid (≥50 prints / active
book). ITF opt-in, logged separately. Esports ToS-held, excluded.

### 4.2 Trigger (unchanged from v2 — live-verified)
Fire at most ONCE per market when ALL hold:
1. **Near-decided** per `match_state`: bo3 — leader has ≥1 completed set AND leads the in-progress
   set by ≥3 games; bo5 — leader up ≥2 completed sets with net set lead ≥1 and at least level in
   the in-progress set. Leader = more completed sets, ties broken on in-progress game lead.
2. **`best_ask` in [0.65, 0.92]** — the price actually paid, never the mid.
3. Fresh quote (< 10 min).
4. **Orientation:** the YES contract's player (`outcomes[i]` where `side_long[i]`) must equal the
   ESPN leader. Never inferred from slug order — 23% of markets list `outcomes[0]` as the *second*
   player named in the question.
5. **Market identity is DATE-BOUND** and requires each player to claim a *different* outcome (§6.3).

### 4.3 Settlement — payouts are continuous
Settlement = the venue's official per-market endpoint, **used at its raw value**.
**5.3% of expired tennis markets settle NON-binary** (observed 0.35/0.42/0.45/0.48/0.56/0.68):
voided or abandoned matches return a mark, not a verdict. Binarising them is an error of up to
~0.5 per event in **both** directions. A terminal mark is **PROVISIONAL**, recorded raw, and
**excluded from the gate** — a guessed payout must never drive a pre-registered verdict.

### 4.4 Costs — measured, not assumed
- Taker fee **θ = 0.06·p(1−p)**, verified: `feeCoefficient = 0.06` on all 247,847 markets.
- **No exit spread.** This is buy-and-hold-to-settlement; the round-trip toll that killed the maker
  arms does not apply. You cross once.
- Measured tennis in-band spread: median **1.00¢** (mean 1.32¢) → half-spread ~0.5¢.
  **One-way toll ≈ 1.43¢ ≈ 1.77% of stake.**
- **Depth-aware fill required.** Median touch depth 9,314 shares (a $50 ticket ≈ 61 shares = 0.65%
  of the touch) — but **p10 = 10 shares**. Both the naive top-of-book fill and the depth-walked
  fill are recorded; if the verdict differs between them the result is **cost-fragile and fails**.

## 5. Reliability — measured, reported, and explicitly NON-GATING

The payoff shape is brutal: at mean ask 0.809 a win pays +0.191 and a loss costs −0.809 —
**hazard/reward 4.24×, break-even hit rate 80.9%.** Simulated at N=250:

| true edge | ROI p50 | P(ROI<0) | maxDD p50 | loss streak p95 | % blocks + |
|---|---|---|---|---|---|
| +6.29¢ | 5.48% | 0.01 | 3.11 | **4** | 80% |
| +4.00¢ | 3.18% | 0.08 | 4.05 | **4** | 70% |
| +2.00¢ | 1.20% | 0.30 | 5.36 | **4** | 60% |
| **+0.00¢** | −0.92% | 0.64 | 7.63 | **4** | **50%** |

**The intuitive reliability metrics carry almost no information.** Longest losing streak is 4
whether the edge is +6.29¢ or exactly zero. "Percent of periods green" moves only 50%→80% across
the entire range — a **zero-edge** strategy still shows half its weeks profitable. Anyone watching
a live equity curve and feeling reassured by green weeks and short losing runs would feel
*identically* reassured with no edge at all.

Therefore: positive-window fraction, max clustered-loss-streak, max drawdown, Ulcer index and
downside deviation are **recorded and reported every run, and gate NOTHING.** Their purpose is
**sizing and endurance** — expect a ~3-stake drawdown and 4-loss runs *even when the edge is
entirely real* — not detection. **Detection is ROI LB and λ. Nothing else.**

## 6. Anti-self-deception controls (BINDING)

**6.1 Paired placebo, identical cost path.** Non-near-decided matches in the same band flow through
the same fee, spread, depth and fill logic. A misspecified cost model hits both arms equally, so the
**difference** survives it. If the placebo also prints positive, we have measured our cost model,
not an edge. *Two of this project's four retractions reversed sign the moment a control was added.*

**6.2 λ as a cost-free cross-check.** λ is computed from mids and is therefore **immune** to
fee/spread misspecification. The joint reading separates three states that otherwise look identical:

| | ROI > 0 | ROI ≤ 0 |
|---|---|---|
| **λ > 0** | real and capturable | real information, eaten by costs — honest "no business" |
| **λ ≈ 0** | **variance or cost-model error → DO NOT SIZE** | dead |

**6.3 Market identity, date-bound.** Loose name matching mapped live matches onto months-old
markets *with the wrong opponent* (observed 2026-07-19: Darderi v Rublev → a 2026-03-20 market).
That does not lose an edge, it **buys a different match**. Matching is now date-bound (±1 day) and
requires each player to claim a distinct outcome.

**6.4 Instrument liveness.** Every consumer **fails closed, not loud**: a dead tape or stale markets
snapshot yields "no signals qualified", indistinguishable from "no edge". A signal counts only if,
at fire time, the tape wrote < 10 min ago and the markets snapshot covers the match date. Days
failing either are **excluded from the denominator and logged as an outage**. *Absence of signals is
not evidence of absence of edge unless the instruments are provably live.*

**6.5 Cost-sensitivity grid.** ROI reported at 0/1/2/3¢ haircut. Sign flip inside that range ⇒
**cost-fragile, fails**.

**6.6 Latency, measured not assumed.** The recorder logs ESPN poll time, quote `recv_at`, quote age
and the price at +1/+5/+10 min. λ→0 by −45min, so if the book re-rates before ESPN publishes we are
late **by construction**. This is the single number the thesis turns on and it is currently
**UNMEASURED**.

## 7. Gate, futility, and retraction

**PASS requires ALL, over ≥250 gate-eligible events (warmup=false, official settlement only),
spanning ≥2 tournament weeks including ≥1 non-Wimbledon week:**
1. event-clustered ROI **lower bound > 0**;
2. point ROI **≥ +2.0%** (must clear the ~1.77% measured toll);
3. **λ CI lower bound > 0**;
4. the **placebo arm's** ROI LB ≤ 0 (else the "edge" is the cost model);
5. verdict **unchanged** between naive and depth-walked fills, and across the 0–3¢ grid.

**FUTILITY STOP (pre-registered):** at ≥150 gate-eligible events, if point ROI < −2.0%, stop. That
is inconsistent with the hypothesised effect at this N and continuing wastes months.

**RETRACT:** R1 ROI LB ≤ 0 at ≥250 · R2 λ CI includes 0 at ≥250 · R3 edge only in one tournament /
fails the non-Wimbledon requirement · R4 measured slippage+fee drives ROI LB ≤ 0 · **R5 placebo
ROI LB > 0** · **R6 instrument outage on >20% of days** (the series cannot support a verdict).

## 8. Declined (recorded so the freeze is auditable)
1. **Widening [0.65,0.92]** — declined; near-decided states often price above 0.92 and widening
   would raise the event rate post-hoc.
2. **Relaxing the non-Wimbledon / ≥2-week bars** — declined; that is the `favorite_v2` failure.
3. **Firing when the ESPN leader is the NO side** — halves the universe and roughly doubles calendar
   time. Outcome-neutral and symmetric, so defensible, but it materially changes the universe and
   requires **Tue's explicit sign-off before any signal accrues**. **Left OFF.**

## 9. What this test cannot establish
**Paper is not a fill.** Every control above still assumes we would have been filled at a price we
observed but never took. Only a deliberately tiny live pilot — sized so its sole purpose is
measuring fill realism — resolves that, and it is a **separate, explicit, Tue-only decision**.
A green gate here does **not** authorise an order. **k=0 remains correct.**
