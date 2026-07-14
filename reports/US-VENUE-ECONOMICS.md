# US-VENUE ECONOMICS — the fee/rebate/subsidy map, and the posture that keeps our money

**Date:** 2026-07-14. **Branch:** `feat/us-economics`. **All read-only. No order was placed; no
account funded.** Client identified honestly on every request; public/unauthenticated throughout.

Sibling: `reports/US-VENUE-OBSERVABILITY.md` (the eyes). This is the economics: *for each arm we
trade, should we be a taker or a maker on US, at what prices, and what do we actually net?*

---

## 0. THE VERDICT IN SIX LINES

1. **TAKE, don't make — on every arm, at every price we trade.** Taking beats making everywhere in
   the table, and making forfeits the arm's alpha entirely.
2. **Making is DEAD on US too — but for a completely different reason than intl.** The intl killer
   (13× hazard/reward) **does not transfer**: US measures **0.91–0.99×**. Making dies here instead
   because its net markout is **statistically zero** (+0.01¢/share), it is **significantly negative
   in the coin-flip band**, and the subsidy that was the only reason to reopen the thesis **cannot
   be reached at our size**.
3. **The liquidity pool is real, works exactly as designed, and is already competed away.** It pays
   **only at the touch** — the exact place you get picked off. There is no safe distance that earns.
4. **The fee is not a flat tax — it is a gradient across our own champion band.** It eats **62% of
   the favorite edge at p=0.71 and 4% at p=0.98.**
5. **Accelerated Tier Placement is the single highest-value, zero-risk ask.** Our intl volume may
   buy a 25–50% taker-fee rebate from day one. That is a pure discount on the posture we are
   already taking.
6. **No reliable cross-venue basis.** The mean is significant; the **median is 0.00¢ and the sign is
   a coin flip.** No routing rule.

---

## 1. THE FEE MAP — verified at source AND on the venue

`Fee = Θ · C · p · (1−p)` — **taker Θ = +0.06, maker Θ = −0.0125** (the maker is *paid*).
Verified at `docs.polymarket.us/fees`, and independently confirmed on the venue itself: **all 2,999
live markets return `feeCoefficient: 0.06`.** Not a docs aspiration — the real coefficient.

| p | taker fee | maker rebate | make-vs-take swing | taker @25% tier | taker @50% tier | volume-incentive eligible |
|---|---|---|---|---|---|---|
| 0.50 | 1.50¢ | +0.31¢ | 1.81¢ | 1.12¢ | 0.75¢ | yes |
| 0.71 | 1.24¢ | +0.26¢ | 1.49¢ | 0.93¢ | 0.62¢ | yes |
| 0.85 | 0.77¢ | +0.16¢ | 0.92¢ | 0.57¢ | 0.38¢ | yes |
| 0.95 | 0.29¢ | +0.06¢ | 0.34¢ | 0.21¢ | 0.14¢ | yes |
| 0.98 | 0.12¢ | +0.02¢ | 0.14¢ | 0.09¢ | 0.06¢ | **NO** |

Two consequences, both load-bearing:

- **Fees are cheapest at the extremes.** Our champion favorite band (0.71–0.98) is *already* the
  cheapest place on the venue to take. Coin-flips are the most expensive (1.50¢) — which compounds,
  on pure cost grounds, the finding that weather doesn't transfer.
- **The maker rebate is 4.8× smaller than the taker fee at every price.** It is nowhere near large
  enough to pay for being picked off. **The rebate alone was never going to be the prize.**

**Correction to the brief:** the Volume Incentive Program pays **"maker or taker"** (not takers
only), and only on trades **between 3¢ and 97¢**. So **p=0.98 — the cheapest place to take — is
*outside* the volume subsidy.** The MM-program contact is **institutional@polymarket.us**, not
`@qcex.com`.

**Tiers** (prior-month taker notional, paid weekly): **$250k → 10% | $1M → 25% | $10M → 50%.**
**Accelerated Tier Placement** is real and quoted verbatim: *"A Participant may provide verifiable
proof of their trailing-30-day notional trading volume on another prediction market and be assigned
to the rebate tier corresponding to that volume."*

---

## 2. THE CRUX — ADVERSE SELECTION, MEASURED (not assumed)

Market-making was **KILLED on intl** (2026-07-09) at a **13× hazard/reward** ratio. We could never
*see* that on intl; we inferred it. **On US we measured it**, because the live tape publishes
`maker_username` on ~48% of prints. We did not simulate a resting order and assume its fate — **we
watched 7,049 real maker fills and priced what happened to them next.**

**Method, and the trap it avoids.** Markout is measured against the **MID**, never against
subsequent trade prices. Prints alternate between bid and ask, so a trade-price markout hands the
maker the half-spread as fake profit and makes *every* maker look good no matter how hard they are
picked off — **that is the error class behind the retracted "+4.8% maker-copy."** The sign was
verified empirically before use (maker BUY prints sit at the bid 95–96% of the time; no YES/NO
inversion). CIs are **cluster-bootstrapped by market**, because one informed sweep is dozens of
correlated prints and an iid bootstrap would manufacture significance out of correlation.

**n = 7,049 maker fills / 173 markets / 3,930 distinct takers / 148 min of tape.**

| horizon | markout (fills) | drift = ADVERSE SELECTION | p | placebo drift (artifact control) |
|---|---|---|---|---|
| 1s | +0.685¢ [+0.11,+1.03] | −0.707¢ | 0.000 | +0.001¢ |
| 5s | +0.470¢ [−0.20,+0.83] | −0.923¢ | 0.000 | +0.024¢ |
| 30s | **−0.088¢** [−0.57,+0.21] | **−1.480¢** | 0.000 | −0.022¢ |
| 60s | **−0.213¢** [−0.54,+0.09] | **−1.607¢** | 0.000 | −0.011¢ |
| 300s | −0.110¢ [−1.31,+0.76] | −1.496¢ | 0.000 | −0.030¢ |

**The artifact control passes.** The same asof machinery, at random times with a random side, gives
drift ≈ **0.00¢ at every horizon**. So the −1.6¢ on real fills is informed flow, not a broken join,
a stale mid series, or a sign slip. *(Two of our four retractions reversed sign when a control was
finally added. This is that control, and it clears.)*

### 2.1 The number that faces intl's 13×

> **HAZARD / REWARD = 0.91× at 30s, 0.99× at 60s.**
> (hazard = |drift| 1.48–1.61¢ · reward = spread capture 1.392¢ + rebate 0.228¢ = 1.619¢)

**Intl was 13×. US is ~1×.** A maker here is paid almost exactly what they are picked off for.
**This is a genuinely different market** — the intl killer does not transfer, and any claim that it
does is now falsified by measurement.

But ~1× is a knife-edge, not a business:

> **Net maker economics = markout(60s) −0.213¢ + rebate +0.228¢ = +0.014¢/share.**
> **CI [−0.54, +0.09] on the markout. Statistically indistinguishable from zero.**

### 2.2 We attacked our own positive result, and it died

The favorite band first came back **significantly positive** (markout +1.375¢, p=0.005). We tried to
kill it, and succeeded:

| test | result |
|---|---|
| **side composition** | maker BUY **−0.02¢ (p=0.96)**, maker SELL +2.15¢ (p=0.18) — **only one side.** A real spread-capture edge is positive on *both* sides; a one-sided result is a directional drift in a trending sample. |
| **concentration** | **top-3 markets = 118%** of the total mass. Two ITF women's tennis matches carried 95% of it. |
| **leave-one-market-out** | +1.375¢ → **+0.417¢, p=0.477. NOT SIGNIFICANT.** |

The wide, asymmetric CI ([+0.42,+4.15]) was the tell. **The longshot band dies the same way**
(leave-one-out p=0.365). **No band shows a maker edge that survives.**

The one result that **does** survive is a *negative* one:

> **Midrange (coin-flip) 0.30–0.71: makers lose −0.52¢/share after leave-one-out
> (CI [−1.06,−0.23], p=0.005), and maker BUY is −1.31¢ (p=0.009).**

That is exactly where the taker fee is highest and where coin-flip/weather-shaped markets live.

### 2.3 Identification bias — stated, not buried

The venue names the maker on only 48% of prints. Those two halves are **not the same animal**:

| maker sample | drift@30s | markout@30s | markout@60s | avg size |
|---|---|---|---|---|
| named (48%) | −1.52¢ | −0.06¢ | −0.12¢ | 48 contracts |
| anonymous (52%) | −0.58¢ | +0.64¢ | +0.45¢ | **103 contracts** |

Anonymous makers are **2.1× larger** and get picked off **2.6× less** — the signature of
institutional/designated MMs whose identity the venue hides. **A KYC'd retail account resting modest
size *is* a named maker**, so we adopt the **named (worse) cohort as our reference class.** The
flattering number is the one we do not get to use.

---

## 3. THE LIQUIDITY SUBSIDY — real, working, and already competed away

This was **the only reason to reopen a killed thesis**: a *fill-independent* subsidy that intl never
had. We priced it against the venue's own published parameters, pulled live from the **public,
unauthenticated** `/v1/incentives` endpoint — not from the brief's figures.

**First, the brief's numbers are event-level sums, not per-market pools.** `rewardPool` is a
**program-level** figure, constant across every market the program covers and split among them:

| program | pool | markets | **$/market** |
|---|---|---|---|
| worldcup_moneyline_live | $24,700 | 6 | **$4,117** |
| ufc_main_moneyline_live | $8,000 | 5 | $1,600 |
| worldcup_playerprops_live | $9,000 | 616 | $15 |
| **pga_round_1** | **$15,000** | **1,172** | **$13** |

The World Cup game's programs sum to **exactly $75,000** and PGA's to **exactly $50,000** — so the
brief's "$75k/game, $50k/tournament" reconcile *to the cent*, but they are **event aggregates**. Real
venue-wide live incentive spend is **$191,185 across 80 programs** — not the $69M you get by
naively summing the pool per market. **Ranking markets by raw pool is wrong by ~300×.**

### 3.1 The tick is the punchline

**Score = discountFactor^(ticks from best price) × size**, snapshotted every second, each side
normalized to 1.0, split pro-rata.

The tick is **0.001 venue-wide** (3,998/3,999 markets) — but **93.2% of real quotes sit on whole
cents.** So an order **one cent** off the touch is **ten ticks** away and scores `0.3^10 = 0.000006`
— **zero**.

> **THE SUBSIDY IS ONLY PAID AT THE TOUCH — the exact place adverse selection lives.**
> It does not buy you a hiding spot. **It pays you to stand in the line of fire.**
> (And a rival can outbid you by 0.1¢ to cut your score to 30%.)

This is the fact that collapses the reward thesis. The fill-independent subsidy is *not* separable
from the fill-dependent hazard: **to earn one you must accept the other.**

### 3.2 We cannot reach it anyway

Reward share therefore reduces to a queue-share problem — and the queues are enormous:

| program | median touch depth (bid / ask) | our share resting 1,000 | reward (conservative) |
|---|---|---|---|
| worldcup_moneyline_live | **61,974 / 537,241** contracts | **0.9%** | **$0.13/hour** |
| mlb_moneyline_live | 129,180 / 32,102 | 1.9% | $0.24/hour |
| worldcup_winnerfutures | 854,359 / 625,527 | 0.1% | $0.01/hour |

*(Verified the touch qty is the **best level**, not the whole book: bid 0.100 × 1,377 against 109,790
total book. The deep queues are real, not an aggregation bug.)*

### 3.3 Why the queues are deep: the subsidy works

**Natural experiment** — at matched traded notional, rewarded vs unrewarded markets:

| traded notional | rewarded? | median touch qty | median spread |
|---|---|---|---|
| <$1k | no | 328 | 4.00¢ |
| <$1k | **yes** | **3,067 (9.3×)** | **1.00¢** |
| $10–100k | no | 697 | 1.00¢ |
| $10–100k | **yes** | **1,896 (2.7×)** | 1.00¢ |
| >$100k | no | 1,443 | 2.00¢ |
| >$100k | yes | 989 | 1.00¢ |

The subsidy does exactly what it is designed to do: it pulls liquidity into thin markets and
compresses spreads from 4¢ to 1¢. **Which is precisely the bad news.** The pool is **already
capitalized** into tighter spreads and deeper queues. We would be a **late entrant joining a queue
that exists *because* of the pool**, capturing a 1¢ spread where *unsubsidized* markets still pay 2¢.

*(Honest caveat: the venue **chooses** which markets to subsidize, so this is not random assignment.
Suggestive, not causal. The direction is unambiguous; the magnitude is not identified.)*

### 3.4 The one bound we cannot close from outside

Whether score accrues across a `live` program's **full published window** (World Cup: 288h) or **only
during live play** is a **~115× swing** in the payout rate. We report **both bounds and pick
neither**. Closing it requires the authenticated `GET /v1/incentives/earnings` for our own account —
i.e. **Tue's API key**. Until then it is a stated bound, not a number we pretend to know.

**Even the optimistic bound does not rescue the thesis**, because §3.1 stands regardless: the reward
is only payable at the touch, and §2.2 says the touch is where we are (at best) flat.

---

## 4. PER-ARM POSTURE — the deliverable

`net_edge()` ships in `scripts/us_fees.py`. Edge/share = **ROI × p** (our arm ROIs are on *stake*,
and stake per share *is* p).

### 4.1 The fee is a gradient, not a tax

| p | favorite edge/share | taker fee | **fee as % of edge** | net (no tier) | net @25% |
|---|---|---|---|---|---|
| 0.71 | 2.00¢ | 1.24¢ | **62%** | 0.76¢ | 1.07¢ |
| 0.80 | 2.25¢ | 0.96¢ | 43% | 1.29¢ | 1.53¢ |
| 0.85 | 2.39¢ | 0.77¢ | 32% | 1.62¢ | 1.81¢ |
| 0.90 | 2.53¢ | 0.54¢ | 21% | 1.99¢ | 2.12¢ |
| 0.95 | 2.67¢ | 0.29¢ | 11% | 2.38¢ | 2.46¢ |
| 0.98 | 2.75¢ | 0.12¢ | **4%** | **2.64¢** | 2.67¢ |

Edge/share **rises** with p; fee ∝ p(1−p) **collapses** toward 1.0. **Our champion band is not
economically uniform on US** — after fees the deep end is worth **3.5× the shallow end**.

> **CAVEAT, stated not buried:** this assumes the arm's ROI is **flat across the band**, which our
> records do **not** establish. **The fee gradient is certain; the location of the optimum is not.**
> Measuring ROI(p) *within* the band on intl is a prerequisite before acting on the deep-tilt.
> **Do not read "maximised at 0.98" as validated.**

### 4.2 Take or make

| arm | p | TAKER net | TAKER @25% | MAKER net | **posture** |
|---|---|---|---|---|---|
| favorite (full book, ROI +2.81%) | 0.85 | 1.62¢ | 1.81¢ | 0.55¢ | **TAKE** |
| favorite (+liquidity gate, +4.17%) | 0.85 | 2.78¢ | 2.97¢ | 0.55¢ | **TAKE** |
| favorite (+liquidity gate) | 0.95 | 3.68¢ | 3.75¢ | 0.45¢ | **TAKE** |
| weather 0.71–0.98 (LB +2.89%) | 0.85 | 1.69¢ | 1.88¢ | 0.55¢ | **skip on US** (doesn't transfer; thin book) |
| coin-flip / midrange | ~0.50 | — | — | **−0.52¢ (p=0.005)** | **NEVER make** |

**Taking wins at every price in every arm**, and the gap is not close. The maker column also
**forfeits the arm's gross edge entirely**: a resting order does not select its fills, so it does not
keep the arm's alpha — it gets whatever the flow hands it. **That asymmetry, not the rebate
arithmetic, is what settles take-vs-make.**

---

## 5. THE REST OF THE DIFFERENCE MAP

- **Basis: NO routing rule.** Market-level mean −2.43¢ (CI [−5.50,−0.30], p=0.007) looks signed — but
  the **median is exactly 0.00¢ and only 9/19 markets are negative (a coin flip).** The significant
  mean is a few outliers; the mean/median divergence is the tell. **n=19 markets is thin.** Scanner
  now loops at 300s to accrue; revisit with real n.
- **Coverage: ~7%.** 570 live intl signals → **40 mapped + priced** on US. The other 93% are simply
  **not US-actionable**, whatever their edge.
- **Depth:** favorites deep, weather thin, time-varying (`US-BOOK-DEPTH.md`). Depth gates clip size;
  it does not change the take-vs-make verdict.

---

## 6. WHAT NEEDS TUE

1. **Accelerated Tier Placement — the highest-value, zero-risk ask.** Submit our **trailing-30-day
   intl notional** to be assigned the matching tier immediately.
   - **$250k → 10% | $1M → 25% | $10M → 50%** off every taker fee, from day one.
   - Worth **+0.19¢/share at p=0.85** (25% tier) on the posture we are *already* taking. Pure
     discount, no strategy change, no new risk.
   - **The exact figure to submit is our trailing-30-day intl notional** — the run could not compute
     it (the intl ledger is on another branch); it is a one-query ask.
2. **A US API key** (iOS app → verify → `polymarket.us/developer`). Unlocks the authenticated
   earnings endpoint, which is **the only way to close the 115× reward-rate bound** in §3.4 and to
   validate our own-quote economics. **Nothing in §§1–5 needed it.**
3. **Market Maker Program — DO NOT APPLY YET.** Contact is **institutional@polymarket.us** (not
   `@qcex.com`). The run's condition for applying — *"only if the liquidity-pool play is positive
   after measured adverse selection"* — is **NOT met**. Applying now would be applying to lose money
   more efficiently.
4. **Funding a US account: only for the TAKER posture**, and only on the favorite arm.

---

## 7. LIMITS — what this run does NOT establish

- **Time-of-day is uncovered.** The entire tape is **148 minutes of overnight (03:00–05:30 ET)**
  flow: ITF tennis, World Cup, NPB. **MLB, NBA and politics were asleep.** US prime-time flow is
  plausibly sharper (or duller) and **the maker verdict could move**. The tapes are running and
  accrue irreversibly — **re-run `us_adverse_selection.py` after a full US trading day before any
  money moves.** This is the single biggest open item.
- **Markout ≠ realized P&L.** It prices a fill at fair value, assuming the mid is unbiased. A maker
  holding to resolution has inventory risk and capital lockup this does not charge for.
- **The reward model assumes we join at the best price** and that the touch queue is the whole
  competition (justified by df^10 ≈ 0, but it is a model).
- **`n=19` markets on the basis; `n=30` on the favorite-band maker cells.** Both thin.
- **Rung-2 fragility:** the identity tape is an undocumented WS. It can change without notice.

---

## 8. THE FRAME, ANSWERED

The brief asked whether the fee/rebate/subsidy structure is *"large enough to **be** the edge, or to
erase it."* Measured: **it is large enough to erase a marginal edge, and nowhere near large enough to
be one.**

The subsidy that looked like a reason to become a market maker turns out to be **paid only where the
sharks are**, and **already competed away** by makers with more size and better information than us.
The fee we pay as a taker is **small precisely where our champion arm lives** — and can be cut
another 25–50% by asking.

**So: take the small taker fee where the edge is real, tilt deep where the fee gets cheap, ask for the
tier rebate, and do not go stand at the touch to collect $0.13/hour from people who are better at this
than we are.**

---

## 9. US BACKTEST 06/29–07/14 — the arm ON the US venue (added after the fee map)

**This is a real US backtest, not an intl backtest wearing a US hat.** The live identity tape only
accrues forward, but Polymarket US is a CFTC DCM and a DCM must *publish* its tape:

- **ENTRY** = the first **real US print** at/after our signal fired, from the statutory Time & Sales
  tape (1.3–1.9M prints/day) — **plus a 0.5¢ ask haircut**, because we are the TAKER and buy at the
  **ask**, while a print sits at the bid as often as the ask. (Median US spread = 1.0¢, measured.)
  Omitting that haircut is exactly how an edge certifies on a print and then dies at the ask.
- **EXIT** = the US Daily Market Report **settlement** (0.0/1.0). 102,374 rows, 100% settled.
- **FEE** = US taker fee Θ·q·(1−q). Clustered by **EVENT** (the unit of risk is the game).

### 9.1 The arm survives US fees comfortably

| sample | n / events | ROI gross | **ROI net of fee** | fee drag |
|---|---|---|---|---|
| all mapped favorite-band | 2,098 / 381 | +17.69% | **+16.70%** [+11.36,+22.59] p=0.000 | 1.0pp = **5% of edge** |
| favorite_v2 gates | 535 / 79 | +8.39% | +7.54% [−0.02,+15.44] p=0.051 | 10% of edge |
| favorite_v2, non-FIFWC | 186 / 48 | +6.18% | +5.03% [−12.62,+19.50] p=0.554 | 19% of edge |

Sensitivity to the haircut: print +17.60% → half-spread **+16.69%** → full-spread +15.62%. **The edge
is not an execution artifact.** *(The fee is NOT the binding constraint — do not reshape the strategy
around it.)*

### 9.2 ROI IS NOT FLAT ACROSS THE BAND — and the World Cup was hiding it

**60% of the US-mappable universe is World Cup.** Split it out and the picture inverts:

| band | ALL (net) | **non-World-Cup (net)** | verdict (non-WC) |
|---|---|---|---|
| 0.71–0.80 | +11.56% | +7.69% [−7.76,+20.10] | no edge |
| 0.80–0.90 | +0.64% | +5.89% [−5.26,+14.96] | no edge |
| **0.90–0.95** | +4.28% | **+6.78%** [+3.24,+8.58] p=0.003 | **EDGE** |
| **0.95–0.98** | **−1.74%** | **+3.87%** [+3.10,+4.19] p=0.000 | **EDGE — but see 9.3** |

So the naive read ("deep end is dead, ROI −1.74%") is a **World Cup artifact**, and the naive
*opposite* read ("tilt as deep as possible") is refuted by the tail:

### 9.3 We attacked the deep-end edge. 0.95–0.98 does not survive; 0.90–0.95 does.

| non-WC band | picks/events | **losses** | leave-one-event-out | **stress: flip 1 winner→loser** |
|---|---|---|---|---|
| 0.90–0.95 | 82 / 42 | 1 | +6.40% p=0.004 **survives** | **+5.45% [+1.22,+8.55] HOLDS** |
| 0.95–0.98 | 49 / 18 | **0** | +3.70% survives | **+1.77% [−5.69,+4.16] DIES** |

**The 0.95–0.98 CI is tight only because the sample contains ZERO upsets.** At a ~96% favorite you
expect ~2 losses in 49 picks; we observed none. That is not a measured edge — it is **an unobserved
tail**. One upset (−100% on that pick) collapses it to insignificance. **Do NOT concentrate into
0.95–0.98.**

**0.90–0.95 is the band that actually holds up** — it survives dropping its worst event *and* an
injected upset.

### 9.4 Verdict on "prioritize the higher-confidence / higher-p bets"

**Half right, and right for the wrong reason.**
- **Wrong reason:** fees are NOT eating the edge (5–10% of it). There is no fee emergency to solve,
  and reshaping the arm to dodge the fee would be optimizing the smallest term.
- **Half right:** outside the World Cup, the **only bands that certify are the deep ones** — but the
  *deepest* (0.95–0.98) is a zero-loss sample whose edge dies on one upset. **The defensible tilt is
  0.90–0.95, not "as deep as possible."**

**STATUS: SUGGESTIVE, NOT CERTIFIED.** This is a **post-hoc slice** (4 bands × WC/non-WC = 8 cells;
we then reported the significant ones). At 8 cells, ~0.4 false positives are expected at p<0.05.
0.90–0.95 non-WC (p=0.003) clears a Bonferroni bar (0.05/8 = 0.00625) — *barely*. **It needs a
PRE-REGISTERED forward test before it sizes real money.** Coverage is also only **18.2%** (11,497
band signals → 2,098 priced): most of the arm is simply not US-actionable.
