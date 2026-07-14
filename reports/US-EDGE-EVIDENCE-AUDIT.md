# US EDGE — the evidence audit. What the arm is actually worth, on the unit we actually bet.

**2026-07-14, `feat/us-autotrader`. Phase 0 of RUN-US-AUTOTRADER. Every number below was recomputed
from the live DB this session, not quoted.**

The run brief says the strategy is settled and the edge is **"+16.70% net, SUGGESTIVE NOT CERTIFIED."**
A red-team pass and four verification runs later, **three of those five words were wrong.** The edge is
smaller, the sample is half the size we thought, and on the unit of risk it is **not statistically
significant at all.** The arm is not dead — but it has earned **zero dollars**, and GATE A is not a
formality. It is the entire evidence base.

---

## 0. THE BOTTOM LINE

| claim | status |
|---|---|
| "+16.70% net" | ❌ **WRONG SAMPLE.** That is all-band, **World-Cup-inclusive**, n=2,098. It is not the rule we trade. |
| "+6.78%, 82 picks / 42 events" (the traded cell) | ⚠️ **REPRODUCED (+6.74%) — but it is the mean over PICKS.** |
| **the number we would actually trade** | **+5.40%, 41 events, ONE loss** — one order per event under the cluster budget. **Nobody had ever computed this.** |
| **is it significant on the unit of risk?** | ❌ **NO. p ≈ 0.16.** One loss in 41 events where the market prices 3.2. |
| the DMR "settlement" is a settlement | ❌ **FALSE — it is a daily mark.** Real defect. **Does not contaminate the traded cell** (verified). |
| the 60-min entry filter is survivorship-clean | ⚠️ **+2.3pp favorable, ~1.6σ.** Not established, not the D4 catastrophe, but not clean either. |

> **⇒ THE ARM IS SUGGESTIVE, AND WEAKER THAN ADVERTISED. The backtest earns it NOTHING.
> GATE A is the whole case, and it needs ~115 events ≈ 6–8 weeks — not the 3 weeks the design assumed.**

---

## 1. THE UNIT OF RISK — the finding that reframes everything

The certified statistic is the **mean over 82 picks**. But the cluster budget (**size the GAME**,
[[project-polymarket-correlated-risk]]) places **one order per event**. Recomputed under the exact fcfs
rule the executor will use:

| what | n | losses | net ROI |
|---|---|---|---|
| all picks (**as certified**) | 82 | 1 | **+6.77%** |
| **first pick per event (fcfs — WHAT WE TRADE)** | **41** | **1** | **+5.40%** |
| last pick per event | 41 | 1 | +5.40% |
| best-priced per event | 41 | 1 | +5.45% |

*(The red-team's specific fear — that fcfs adversely selects the bottom of the band — is **REFUTED**:
first-pick and last-pick have identical mean price, 0.9216. There is no within-event drift. The choice of
which pick to take is worth ~0.05pp. **But the choice to count picks instead of events was worth 1.4pp.**)*

### And now the part that matters

The 82 picks are **~2.00 per event and they resolve TOGETHER** — same game, same outcome, perfectly
correlated. **They are not 82 bets. They are 41 bets.** The loss count is the sufficient statistic:

```
events                        : 41
mean price paid               : 0.9216   ⇒ the market prices a 7.84% loss rate
losses the MARKET expects     : 3.2
losses we OBSERVED            : 1

P(≤1 loss in 41 | THE MARKET IS EXACTLY RIGHT) = 15.8%
```

> **⇒ p ≈ 0.16. NOT SIGNIFICANT.**
>
> The published **p = 0.003** comes from an ROI cluster-bootstrap over **82 picks** whose entire lower tail
> is governed by **how often a single observation gets resampled**. With one loss in the sample, 36% of
> bootstrap resamples contain **zero** losses. **That is not a confidence interval; it is a coin flip with
> a spreadsheet.**
>
> **`US-VENUE-ECONOMICS.md` §9.3 applied EXACTLY this critique to the 0.95–0.98 band** — *"the CI is tight
> only because the sample contains ZERO upsets… that is not a measured edge, it is an unobserved tail"* —
> **and then failed to apply it to the band it recommended.** 0.95–0.98 had 0 losses in 18 events.
> 0.90–0.95 has **1 loss in 41.** It is a **less extreme version of the same anomaly**, and it was reported
> as a certified edge.

**The edge is not refuted.** Winning 40/41 where the market prices ~38/41 is a real deviation, and the
point estimate is a healthy +5.40%. **It is simply not yet distinguishable from luck**, and the honest
sensitivity is brutal:

| losses in 41 | 0 | **1** | 2 | **3** | 4 |
|---|---|---|---|---|---|
| net ROI | +8.51% | **+5.86% ← observed** | +3.21% | **+0.57% ← what the market prices** | −2.08% |

**Two more upsets and the edge is zero.** That is the whole margin.

---

## 2. THE SETTLEMENT DEFECT — real, and it does NOT kill the arm (verified, not assumed)

**The red-team's #1 "FATAL" finding.** `us_backtest.py::settlements()` asserts in its own docstring:
*"a contract settles once, and earlier rows carry the pre-settlement 0.0 default."* **False.** A CFTC DCM
publishes a **daily settlement price for margining** — live contracts get a **MARK**. Measured on our own
table:

- **49.2%** of `us_daily_market_report` rows carry a **fractional** settlement_price.
- **11.6% of SYMBOLS (16,337)** have a **fractional LAST row** — precisely the row `settlements()` returns.

`price_it()` then does `payoff = st`, `gross = payoff − q`, `won = payoff > 0.5`. **So a favorite that
LOST, whose last published mark is 0.85, books as a WIN with a positive gross.** And the ground truth was
in the row the entire time: `us_backtest.py:87` **SELECTs `outcome_won` and `price_it()` never reads it.**

**THE VERDICT — I ran the cross-check the backtest never ran:**

| scoring of the traded cell | picks/events | losses | net ROI |
|---|---|---|---|
| as published (DMR mark, `won = payoff > 0.5`) | 82/42 | 1 | +6.74% |
| **same picks, scored on intl ground truth (`outcome_won`)** | 82/42 | **1** | **+6.76%** |
| clean (only picks whose DMR reached a terminal 0/1) | 81/41 | 1 | +6.73% |

> **The defect is REAL (13 of 2,101 picks are mis-scored) but it does NOT touch the traded cell, and every
> one of the 13 errors runs the CONSERVATIVE way** (the backtest scored a *winner* as a *loser*, because an
> unsettled contract defaults to 0.0). **The single loss in the traded cell is a real loss.**
>
> ⚠️ **It must still be fixed before GATE A, because it would corrupt FORWARD scoring** — where contracts
> are freshly opened and the fractional-mark rate is highest. **Fix: score on `outcome_won`, and require
> `settlement_price ∈ {0,1}` before a pick may be counted.** This doubles as a **mapper check**: a mis-map
> shows up as a settlement/ground-truth disagreement.

---

## 3. THE SURVIVORSHIP CHECK (the D4 anti-join) — mild, unproven, not clean

`MAX_ENTRY_LAG_MIN = 60`: signals whose US market never printed within an hour are **silently dropped**
(11,497 band signals → 2,098 priced = **18.2% coverage**). On intl, this exact class of filter produced a
**+8.7pp** selection gap (capture-defect D4) — discovered only when someone finally ran the anti-join.
**Nobody had run it here.**

| intl price 0.90–0.95, mapped to a US instrument | n | win rate |
|---|---|---|
| **PRICED** (kept by the backtest) | 561 | **97.9%** |
| **UNPRICED** (silently dropped) | 252 | **95.6%** |

**+2.3pp in favour of the kept sample — but only ~1.6σ (p ≈ 0.11), and the direction REVERSES in the full
mapped universe** (priced 91.5% vs unpriced 93.9%). ⇒ **Suggestive of mild favourable selection; not
established; NOT the D4 catastrophe.** Both subsets still beat the implied rate.

> ⚠️ **But note what it implies: the edge in the dropped set (95.6% vs a ~92.2% implied) is REAL TOO.**
> The filter is not manufacturing the edge. It may be mildly flattering it. **Since the executor will trade
> a DIFFERENT universe again (a fresh book at t=0, not "a market that printed within an hour"), the only
> honest resolution is the one the design already reached: GATE A runs on the EXECUTABLE universe, and the
> backtest is CONTEXT, NOT AN ANCHOR.**

---

## 4. GATE A, SIZED HONESTLY

The forward test is a test of the **loss count** (the sufficient statistic for a Bernoulli edge), one-sided
exact binomial, `H0: loss rate = 0.078` (the market is right):

| what we must be able to detect | events | reject if losses ≤ | α | power | ≈ days @ 3 events/day |
|---|---|---|---|---|---|
| **the observed edge (0.024)** | **115** | **4** | 0.048 | **0.86** | **~38** |
| half the edge (0.039) | 229 | 11 | 0.049 | 0.81 | ~76 |
| a modest edge (0.050) | **>400 — unreachable in any sane window** | | | | |

> **⇒ GATE A needs ~115 EVENTS ≈ 6–8 WEEKS** (and **longer** in practice: the executor's cap + depth gate
> will skip some events, so the *post-gate* event rate is strictly below 3/day and must be **measured in
> the shadow rung before N is frozen**).
>
> **Both designers proposed 60–65 events / 3–4 weeks. That is roughly HALF the honest requirement**, because
> both sized against an ROI bootstrap rather than the loss count.
>
> **AND THE PRE-REGISTERED POWER STATEMENT, WRITTEN BEFORE THE DATA:** this gate **can certify a big edge
> and CANNOT certify a small one.** If the forward loss count lands at 5–8 in 115, the verdict is
> **INDETERMINATE — and we keep running at $0. We do NOT extend the window.** Extending the window is the
> goalpost move that produced four retractions in this program.

---

## 5. WHAT THIS CHANGES

1. **Sizing uses +5.40%, and any Kelly-like computation uses the LOWER BOUND — never +16.70%.** The brief's
   headline overstates the traded rule by **~3×**.
2. **The primary detector is the LOSS COUNT, not P&L.** A 1-loss-in-41 process emits almost no P&L
   information per day. (Same mathematics that made intl's P&L CUSUM structurally incapable of firing on
   `weather_fav`.)
3. **GATE A is the whole case.** The backtest is not a certification; it is a *hypothesis with n=41 and
   p=0.16*. **No meaningful capital until the forward test clears.**
4. **The rollout gets longer, and that is the correct answer.** ~6–8 weeks of $0 forward paper before the
   first real dollar — and rungs 1–3 need **no API key at all** (the US book is public; verified HTTP 200
   unauthenticated), so **none of it is blocked on Tue.**

**The arm may well be real. It has simply not yet earned the right to be trusted, and the honest thing —
the thing this whole run exists to do — is to say so before the money moves, not after.**
