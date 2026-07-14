# GATE A — THE PRE-REGISTERED FORWARD TEST (FROZEN)

**Status:** FROZEN on **2026-07-14**, before one day of forward US executor data has been read.
**Binding on:** any decision to place real capital on the US favorite arm.
**Authored by:** the RUN-US-AUTOTRADER Phase-0 forge. **Reviewed by:** Tue (pending).

> **Why this document exists.** The US backtest is **post-hoc**, and the audit
> (`reports/US-EDGE-EVIDENCE-AUDIT.md`) showed it is **weaker than it was reported to be**: on the unit
> we actually bet — the **event** — it is **one loss in 41 where the market prices 3.2**, which has a
> **15.8% probability if the market is simply right.** That is **not significant.**
>
> **⇒ The backtest earns this arm ZERO dollars. This forward test is the entire evidence base.**
>
> This program has produced **four retractions, two of which reversed sign**, every one of them because a
> result was interrogated *after* the data was seen. **Everything below is frozen. Changing any frozen
> field VOIDS the gate and restarts the forward clock at zero.**

---

## 1. THE RULE (frozen — this is exactly what the executor will trade)

A signal is **ELIGIBLE** iff **all** hold at the decision instant:

| # | Clause | Note |
|---|---|---|
| R1 | `strategy = 'favorite'` (the existing consensus predicate, unchanged) | |
| R2 | a `us_market_map` row exists with `mapper_conf ≥ 0.90` | fail-closed; a signal we cannot map is a signal we do not trade |
| R3 | the event is **NOT** the FIFA World Cup | 60% of the US-mappable universe, and it hides the signal |
| R4 | **`us_ask ∈ [0.90, 0.95)`** — **the US ASK we would PAY, from a FRESH public `/book`** | ⚠️ **NOT the intl `mean_price`.** The certified cell is defined on the **US price paid** (`us_backtest.py:324` bands on `q`, the US entry incl. haircut). The intl↔US basis has **sd 5.9¢** — wider than the band itself. **Banding on the intl price would trade a cell nobody has ever certified.** |
| R5 | **depth-sufficient**: the clip fills **entirely** on resting asks at prices ≤ `cap` | from the live book. Never from a band, never from a tape. |
| R6 | `cap = round_DOWN_to_tick( us_mid + 0.5¢ )` and `us_ask ≤ cap` | **the certified basis, made executable** (see §2) |
| R7 | `net_edge(...) > 0` after the US taker fee (`Θ=0.06`) and the assigned tier rebate | `scripts/us_fees.py` |
| R8 | `secs_to_close ≥ 300` | |
| R9 | the event's **cluster budget** is not exhausted | **fcfs — ONE order per `super_event`.** The GAME is the bet. |

**Size:** flat, hard, per-signal dollar cap. **No Kelly.** One clip per **event**.

---

## 2. THE PRICE BASIS — derived, not chosen

The backtest's entry is **the first real US PRINT within 60 minutes, + 0.5¢** (`us_backtest.py:64,75,139`).
**A print sits at the bid as often as the ask** ⇒ `E[print] ≈ mid` ⇒ **the certified basis is `mid + 0.5¢`.**

**Measured:** in the traded band, **254 of 256 sports markets (99.2%) are on a 1¢ tick grid.** On a 1-tick
book, `mid + 0.5¢` **is exactly the ask** — so the cap is "trade only when the spread is one tick, and pay
the ask." On a wider book the cap sits **below** the ask and **we skip.**

> **⇒ THE EXECUTOR SYSTEMATICALLY REFUSES TO TRADE WIDE BOOKS.** That is correct and it is deliberate:
> on a wide book **the price the backtest assumed is not available**, and taking the ask would be trading
> an edge we never measured.

**Three invariants, because this is where a rounding bug silently pays the ask:**
1. **The limit price is quantized to the tick grid and ROUNDED DOWN.** A naive `round()` on a 2-tick book
   turns `0.935` into `0.94` — **the full ask — silently reintroducing the exact error the cap exists to
   prevent, via a rounding function.**
2. **The cap is computed in INTEGER TICKS, never floats.** `cap == ask` is an exact-equality boundary and
   it is the *only* case that ever fills. A float refactor away is a silent 100% skip rate that looks like
   "the market was never tight enough."
3. **`ORDER_TYPE_MARKET` and the venue's `slippageTolerance` are NEVER used.** We compute our own cap and
   send a **LIMIT** price. One source of truth.

---

## 3. THE METRIC (frozen)

**The unit of observation is the EVENT.** One order per event; one outcome per event.

### PRIMARY — the loss count vs a PRICE-MATCHED PLACEBO

> **⚠️ THE CONTROL IS NOT OPTIONAL, AND THE EXISTING ONE IS BROKEN.**
> Buying 0.92 favorites and winning 97.6% beats the price — but that could be **the favorite–longshot
> bias, not our signal.** The only thing that can tell those apart is **a pool of US favorites at the same
> price, on the same day, that we did NOT signal.**
>
> **The current `us_quotes.is_placebo` pool CANNOT serve** (red-team F5, confirmed at
> `us_quote_capture.py:167-184`): it is matched on **(league, date) only — NOT on price**; it carries **no
> `us_side`**, so no ROI is computable for it; and it is **reshuffled every sweep**, so it is a quote
> sampler, not a cohort. **A control that cannot produce an ROI means GATE A cannot fail honestly.**
>
> **⇒ BLOCKING PRE-REQUISITE: rebuild the placebo as a FIXED, PRICE-BAND-MATCHED, SIDE-ASSIGNED cohort —
> US favorites with `us_ask ∈ [0.90,0.95)`, non-WC, same day, same depth gate, NO consensus signal —
> captured through the IDENTICAL code path at the IDENTICAL instant. GATE A does not start until it exists.**

```
PRIMARY STATISTIC:   Δ = loss_rate(placebo) − loss_rate(signal)     over matched events
PRIMARY TEST:        one-sided; H0: Δ ≤ 0  (our signal adds nothing over a same-priced favorite)
```

### SECONDARY (reported always, never used to move the gate)
- **The absolute loss count vs the market-implied rate.** `H0: loss_rate = 1 − mean(us_ask)`. This is the
  *"is the favorite underpriced at all"* question. **It is NOT the primary, because it cannot separate our
  signal from the favorite–longshot bias.**
- **Net ROI**, event-clustered bootstrap (10,000 resamples, **seed frozen at 20260714**), reported with
  **n, dispersion, and the placebo delta** — never a bare point estimate.

### THE INPUTS — measured, never modeled
| input | source |
|---|---|
| `fill_px` | **PAPER:** the VWAP the depth-walk pays on the **real** book at the decision instant. **LIVE:** the venue's `avgPx`. |
| `fee` | **LIVE:** `commissionNotionalTotalCollected`, **read off the Order**. Never modeled. (Invariant I8.) **PAPER:** `us_fees.taker_fee`. |
| `won` | the US **TERMINAL** settlement (`settlement_price ∈ {0,1}` — **a fractional mark is NOT an outcome**), **cross-checked against the intl `outcome_won`.** **A disagreement is a MAPPER ALARM: halt and investigate. Never average it in.** |

---

## 4. THE THRESHOLD (frozen, one-sided, pre-committed)

**PASS** iff **all** of:

| | |
|---|---|
| **T1** | one-sided exact test on the PRIMARY (Δ > 0) at **α = 0.05** |
| **T2** | **N_events ≥ 115** (see §5 — this is the honest power requirement, not a round number) |
| **T3** | the window spans **≥ 30 calendar days** — so it cannot be one hot tournament regime ([[project-polymarket-regime-persistence]] found a SOCCER-ARTIFACT) |
| **T4** | **leave-one-EVENT-out**: the verdict survives dropping any single event |
| **T5** | **stress**: inject **one additional loss** at the largest clip ⇒ the point estimate of Δ is still > 0 |
| **T6** | **zero** unexplained positions, **zero** `ReconcileFailed`, **zero** mapper alarms over the window |

**FAIL** otherwise. **A FAIL IS A FAIL.** No "close enough." No re-slicing. No new cell.
**INDETERMINATE** (N < 115 at the 30-day mark) ⇒ **KEEP RUNNING AT $0. DO NOT LOWER N.**

---

## 5. N, DURATION, AND THE POWER STATEMENT (written before the data)

The forward test is a test of the **loss count** (the sufficient statistic for a Bernoulli edge).
`H0: loss rate = 0.078` (the market is right at a mean price of 0.9216):

| edge we must be able to detect | events | reject if losses ≤ | α | **power** |
|---|---|---|---|---|
| **the observed edge (loss rate 0.024)** | **115** | **4** | 0.048 | **0.86** |
| half the edge (0.039) | 229 | 11 | 0.049 | 0.81 |
| a modest edge (0.050) | **> 400 — UNREACHABLE in any sane window** | | | |

> **⇒ N = 115 EVENTS.** At the **pre-gate** rate of ~3 events/day that is **~38 trading days**.
>
> ⚠️ **THE POST-GATE RATE IS LOWER AND IS NOT YET KNOWN.** R5/R6 (depth + the 1-tick cap) will skip some
> events. **The shadow rung MUST measure the post-gate event rate, and T2's calendar expectation is set
> from that measurement — but N = 115 EVENTS DOES NOT MOVE.** Realistically **6–10 weeks.**
>
> **⇒ THIS GATE CAN CERTIFY A BIG EDGE AND CANNOT CERTIFY A SMALL ONE.** If the forward loss count lands
> at 5–8 in 115, the verdict is **INDETERMINATE**, and **we keep running at $0.** That is written here,
> before the data, so it cannot be argued about afterwards.

---

## 6. WHAT GATE A DOES **NOT** CERTIFY

> **GATE A CERTIFIES THE PICK, AT A REALIZABLE PRICE. IT DOES NOT CERTIFY THE FILL.**
>
> The paper track's fill is a **deterministic read of a real book** ("was there ≥ clip of depth at ≤ cap?"),
> not a fill model — which is why it can certify anything at all. But **two residuals remain unmeasured and
> BOTH bias us optimistic**: **(a) our own market impact** (we are not in the book we are reading), and
> **(b) latency** between our book read and the venue's match (assumed zero).
>
> ⇒ **The rung after GATE A is NOT "ramp." It is "spend $5 to measure (a) and (b)."**
> **Two gates, two claims. Neither may launder the other.**

⚠️ **And the shared-mode failure, named:** the paper track and the live executor **walk the same book with
the same depth-walk code.** A bug in that code corrupts both **in the same direction**, and GATE A would
cheerfully certify the bug. **Mitigation (binding): `preview_order` is an INDEPENDENT, venue-side
computation of the same quantity. Before GATE A may return a verdict, the paper VWAP must match
`preview.avgPx` on ≥50 signals.**

---

## 7. WHAT VOIDS THIS PRE-REGISTRATION

Any change to §1 (the rule), §3 (the metric or the control), §4 (the threshold), or §5 (N).
**Voiding restarts the forward clock at ZERO.** If we want a different test, we pre-register a **new** one
**before** looking at anything.

**Explicitly closed, so it cannot be quietly re-opened later:** the rule is the **band slice on the
UNGATED sample.** It does **NOT** include the `favorite_v2` garbage gates (liquidity ≥ $1k, rank < 5),
which on US across the band give **+5.03% [−12.62,+19.50] p=0.554 — no edge.** The v2 flags are **LOGGED
on every decision** and may be analyzed **only** as a pre-declared **secondary** question.
**GATE A may not be rescued by re-slicing.**

---

## 8. THE SKIP-COUNTERFACTUAL LOG (mandatory, $0, and it may overturn everything)

For **every** skipped signal and **every** no-fill, record the signal, the book we saw, and the reason;
join to settlement afterwards and compare **ROI(skipped) vs ROI(traded)**.

> **If ROI(skipped) ≫ ROI(traded), our own eligibility gate is destroying the edge** — the copy-trading
> equivalent of a survivorship filter. The gate (R5/R6) is a **selection of unknown sign**: the US markets
> that have not yet tightened may be precisely the ones whose book has not yet absorbed the sharp's
> information — i.e. plausibly the ones with the **most** edge.
>
> **This is the highest evidence-per-dollar object in the build, and it costs nothing.**
