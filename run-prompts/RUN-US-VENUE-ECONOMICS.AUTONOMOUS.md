# RUN — US-VENUE ECONOMICS: map every difference, and engineer the fee/rebate posture that keeps our money

**Type:** long autonomous run. **Repo:** `~/polymarket-bot`. **Owner:** Tue.
**Branch off:** `feat/us-venue` (the observability + two-book spine already built there).
**Prereqs already shipped:** live identity tape (`us_tape_ingest.py`), regulatory history
(`us_regulatory_backfill.py`), book-depth sampler (`us_book_sampler.py`), cross-venue basis
(`us_arb_scan.py`), and the verified intl→US mapper. **Read those + `reports/US-VENUE-OBSERVABILITY.md`
first.**

---

## 0. THE BRIEF IN ONE PARAGRAPH

Tue now trades **both** books: Polymarket US (KYC'd, fee-paying, direct) and the international CLOB
(via family abroad). US is a **genuinely different market** — different fees, different prices, different
depth, different coverage, and edges that transfer only partly (sports yes, weather no). This run does
two things. **(A) Finish the difference map** so we stop treating US as an intl clone. **(B) — the priority —
engineer the execution posture that minimizes fees and captures the rebates and incentive pools**, because
on US the fee/rebate/subsidy structure is large enough to *be* the edge, or to erase it. The headline
question: **for each arm we trade, should we be a taker or a maker on US, at what prices, and how much of
the fee do we actually pay after rebates and incentive rewards?** Answer it with measured numbers, not the
fee table alone — especially by **measuring adverse selection directly from the identity tape**, which is
the thing that killed market-making on intl and the thing we could never see there but can see here.

---

## 1. THE ECONOMIC MAP (real numbers, from `docs.polymarket.us/fees` + `/incentives`, eff. 2026-07-01)

**Trading fee is symmetric in price uncertainty:**  `Fee = Θ · C · p · (1−p)`  (p = trade price, C = contracts)

| | Θ | at p=0.50 (max) | at p=0.85 | at p=0.95 | at p=0.98 |
|---|---|---|---|---|---|
| **Taker fee** | +0.06 | 1.50¢/sh | 0.77¢/sh | 0.28¢/sh | 0.12¢/sh |
| **Maker rebate** | −0.0125 | −0.31¢/sh (paid) | −0.16¢/sh | −0.06¢/sh | −0.03¢/sh |

Two immediate consequences, both load-bearing:
- **Fees are smallest at the extremes.** Our champion favorite band (p 0.71–0.98) is *already* the
  cheapest place to be a taker (0.12–0.77¢). Coin-flips (p≈0.5, e.g. weather buckets) are the *most*
  expensive to take (up to 1.5¢) — which compounds the "weather doesn't transfer" finding.
- **The maker rebate is ~4.8× smaller than the taker fee** at any price (0.0125 vs 0.06). Making instead
  of taking swings ~0.93¢/sh at p=0.85. Meaningful on a 3–7¢ edge (~15–30% of it), but **the rebate alone
  is not the prize** — the incentive pools are.

**Three stacking subsidies beyond the base fee:**

1. **Taker-rebate tiers** (automatic, paid weekly): prior calendar-month taker notional
   **$250k→10% / $1M→25% / $10M→50%** fee rebate. **Accelerated Tier Placement:** show verifiable
   trailing-30-day volume *on another prediction market* → placed in that tier immediately. **We have intl
   volume.** This could cut the taker fee 25–50% from day one — price it out, and flag the exact evidence
   Tue would submit.
2. **Liquidity Incentive Program** (OPEN, no application): pays for **resting limit orders whether they
   fill or not**, scored every second by price-proximity + size, pool split pro-rata. Pools are large and
   published per event: **World Cup $75k/game, MLB $12.5k/game, PGA $50k/tournament, UFC $10k, ATP/WTA
   $1k/match, Climate $1k/day, Politics $250/day/event.** *This subsidy did not exist on intl.* It is the
   single biggest reason to revisit making on US.
3. **Volume Incentive Program** (OPEN): pays **takers** a pro-rata share of a per-contract pool (e.g. NBA
   playoff moneyline **$100k/market**), taker notional 3¢–97¢, min $500. So taking can *earn back* part or
   all of the fee on eligible contracts.

**Market Maker Program** (application, `institutional@qcex.com`) is a contractual tier on top — surface it
as a Tue decision, don't assume it.

---

## 2. THE CENTRAL TENSION — adverse selection, and why US may differ from the KILLED intl thesis

**Do not re-derive a known-dead idea naively.** Market-making was **KILLED on intl 2026-07-09**
([[project-polymarket-market-making]]): $0-falsified at **13× hazard/reward** (a resting quote fills
exactly when informed flow runs it over) and US-ToS-blocked. Carry that prior in.

But two things are genuinely different on US, and the run must test whether they flip the verdict:
- **The liquidity pool is a fill-independent subsidy.** You are paid for *resting near the touch*, not for
  being filled. If the per-second reward share exceeds the expected adverse-selection loss on the fraction
  that fills, making is positive *even against sharp flow*. That math was impossible on intl (no such pool).
- **We can now MEASURE adverse selection, not assume it.** The identity tape (`us_trade_tape`) records the
  taker username, side, intent, and price of every fill. So for any resting-order policy we can ask
  empirically: *when our quote would have filled, who hit it, and did the price move against us after?*
  On intl we were blind to this; here it is a column. **This is the measurement the intl thesis never had.**

The run's job is to resolve the tension with evidence, per-arm — not to declare making alive or dead by assertion.

---

## 3. THE OTHER DIFFERENCES TO FINISH MAPPING (context for the economics)

Build on what's known; quantify what's open. For each, state **what we do about it**.
- **Prices:** cross-venue basis is small but non-zero (measured mean −1.5¢, sd 5.9¢). Extend `us_arb_scan`
  over time/markets: is the basis ever reliably signed (one venue systematically cheaper for a family)? A
  persistent sign is a routing rule (enter the leg on the cheaper book), even absent risk-free arb.
- **Depth:** favorites deep, weather thin, time-varying (`reports/US-BOOK-DEPTH.md`). Run the depth sampler
  across a **full US trading day incl. near settlement** — the still-owed control. Depth gates clip size and
  taker-vs-maker choice per market.
- **Coverage:** only ~40 of ~536 live intl signals map to an open US market at conf ≥ 0.90. Quantify the
  mappable universe per arm; the un-mappable signals simply aren't US-actionable.
- **Edge transfer:** sports transfer, weather does not (the other chat's Phase A/B). Re-price the
  **transferable** edges *after US fees and at US depth* — the sibling `RUN-US-VENUE-PORT` question, now
  answerable with the fee map + the forward `us_quotes` basis capture. A signal that certifies on intl at
  ~0 fee but not after a 0.77¢ US taker fee is a real, quantified difference — say so.

---

## 4. WHAT TO BUILD / MEASURE (paper + read-only; no order placed)

Phase everything; commit incrementally on the branch; every claim obeys the evidence rule (§5).

1. **Fee-adjusted edge instrument.** A function `net_edge(arm, side_taker_or_maker, p, C)` = gross edge
   − taker_fee(p) (or + maker_rebate(p)) + expected incentive-reward share − adverse-selection cost. Wire
   it into the existing paper tracker / `us_quotes` so every candidate is scored at its *realizable* US
   economics, not gross. Deliver a per-arm table: taker-net vs maker-net.
2. **Liquidity-reward capture model.** From the published pool sizes + target sizes + discount factors +
   observed book (`us_book_tape`) + our own hypothetical resting size, estimate our **per-second reward
   share** for a given posture in the rich pools (World Cup, MLB, Climate for weather). This tells us
   whether reward-farming the pool beats, or subsidizes, our directional edge. Include a control: reward
   with vs without a directional lean.
3. **Adverse-selection measurement (the crux).** From `us_trade_tape`: build the empirical fill/adverse
   model. For resting orders at/near the touch, what fraction fills, who is the taker (cross-reference the
   per-trader tape — sharp vs noise), and how does mid move in the N seconds after? Produce the
   hazard/reward ratio *on US* to compare against intl's 13×. This is the number that decides making.
4. **Taker-rebate-tier path.** Model the fee after each rebate tier; compute the volume needed and what
   Accelerated Tier Placement (intl volume proof) would grant. Output the exact ask for Tue.
5. **Per-arm execution-posture recommendation.** The deliverable that ties it together: for each arm
   (favorite, weather, any transferable sport), the recommended posture — take at these prices / rest in
   these pools / skip — with the measured net economics and the n + dispersion behind it.

---

## 5. HARD RULES

1. **Read-only / paper only. No order is placed and no account funding is required for §§1–4.** An API key
   only enters when we validate our own-quote economics against reality — flag it as a Tue prerequisite, do
   not block on it.
2. **The evidence rule (binding):** no claim ships without **(a) a control, (b) a significance test,
   (c) explicit n + dispersion.** Two of our four retractions reversed sign when a control was finally
   added; the market-making $0 and the 15-min-latency phantom are the cautionary cases.
3. **Honor the KILLED prior.** Making is dead on intl until proven otherwise on US *by measured
   adverse-selection vs the pool subsidy* — never by "the rebate is positive so it must work."
4. **`merge to main == auto-deploy to prod`.** Work on the branch; anything runnable is default-OFF
   (no committed launch unit), following the sidecar pattern already in place.
5. **No ToS circumvention, no geoblock evasion, no defeating protections.** We are a KYC'd, fee-paying
   customer of US; act like one. Intl reading stays read-only.
6. **Do not overclaim.** A subsidy quoted from the docs is a *published schedule*, not realized income —
   reward pools are split pro-rata against competitors we don't observe; say what we can't yet measure.

---

## 6. DELIVERABLES

1. **`reports/US-VENUE-ECONOMICS.md`** — the fee/rebate/subsidy map with realized (not nominal) numbers,
   and the per-arm taker-vs-maker net-economics table.
2. **A verdict on the maker/liquidity-pool play**, with the measured US hazard/reward vs intl's 13×, per
   rich pool — alive, dead, or conditional, with evidence.
3. **The fee-adjusted edge instrument**, wired into the paper track so future candidates are scored at
   realizable US economics.
4. **The adverse-selection model** off the identity tape (the measurement intl never had).
5. **A `DECISIONS.md` entry** (UV-5…): every quantified US-vs-intl difference and the posture we take on it.
6. **The exact asks for Tue** (§7), each with the evidence to act on it.

## 7. WHAT NEEDS TUE (surface; don't block)

- **A US API key** (own-quote validation; §1–4 don't need it).
- **Accelerated Tier Placement**: whether to submit our intl trailing-30-day volume to jump straight to
  the 25–50% taker-rebate tier — provide the exact figure/proof the run identifies.
- **Market Maker Program**: a contractual application decision (`institutional@qcex.com`) — only if the
  run shows the liquidity-pool play is positive after measured adverse selection.
- **Funding a US account** — only once a posture is proven on paper.

## 8. THE FRAME

The rebate is not free money and the fee is not a fixed tax. Both are **functions of price, posture, volume,
and who is on the other side of your fill** — and for the first time, on US, we can *measure* the last one.
The win condition of this run is a per-arm answer to "take or make, at what price, for what net," backed by
measured adverse selection and realized (not nominal) subsidy — so that when real money goes on the US leg,
we are on the paid side of the fee schedule wherever the evidence says we can be, and honestly taking the
small taker fee where making would just feed the sharks.
