# Per-Niche Trader Rosters — Report

**2026-07-14 · branch `feat/niche-rosters` · paper/analysis-only · nothing deployed, no live path touched**

## The question

> "Find specific profitable traders *within* markets/niches, rather than randomly finding them
> from the overall top-1000 — get the top 50–100 of each space, so we can specialize instead of
> sourcing a small group from the overall top traders, who are likely all from the same
> high-volume spaces."

The premise is **correct and was verified**. The answer to the question, after building the thing,
is **no — and the reason is not the one anybody expected.**

---

## 1. The premise was right: we were sampling whales, not niches

The Polymarket leaderboard ranks by **absolute PnL** — a bankroll-and-volume sort, not a skill
sort (`corr(rank, ROI) = −0.05` on our own pool). So the 3,085 wallets we had ever seen were
whales, and the "niches" we covered were just wherever whales had volume.

The scale of what that hid, measured live:

| | |
|---|---|
| distinct wallets in our **entire** database | **3,085** |
| distinct wallets in **one median esports market** | **447** |
| distinct wallets in **one median weather market** | **170** |

A single market held a seventh of our entire universe.

**The fix works.** `/trades?market=<condition_id>` enumerates every participant and costs
**O(markets), not O(wallets)**. Final harvest: **51,006 resolved markets, 57.2M fills, 11 niches**,
at ~10 markets/sec with zero failures.

| | |
|---|---|
| wallets the leaderboard ever showed us | **3,089** |
| wallets in the harvested population | **423,813** |
| **the leaderboard was showing us** | **0.7% of the traders** |

So the premise was not just right, it was an understatement — and the machinery does exactly what
was asked. The problem is what it found.

## 2. Two API facts that decided the run (both found only by measuring)

- **`/trades` silently defaults to `takerOnly=TRUE`.** It serves only the taker side of each
  trade — **~60% of all fills, the entire maker-side population, were invisible.** One market
  returned 272 rows by default and 671 with `takerOnly=false`. This broke the K1 fidelity gate
  (wallets we *knew* traded a market were missing from its tape), which is how it was caught.
  *The previously-built `feat/market-harvest` branch harvests taker-only — it has this bug.*

  Silver lining: differencing the two tapes recovers a per-fill **maker/taker label** — the
  cleanest possible classifier for uncopyable (spread-capture) profit.

- **`offset` hard-caps at 3000** (~4000 rows/market), and **every time-window parameter is
  silently ignored** — `before`, `after`, `startTs`, `endTs`, and even an invented
  `bogusParamXYZ` all return the byte-identical page. There is no time-slicing escape.
  Since the tape is newest-first, truncation drops the **earliest** entrants — the informed
  money — so truncated markets (0.3% of weather → 22% of esports) are **excluded from scoring**
  while still counting for population discovery.

  This is the same class of bug as the `startTs` failure that once cost 96.8% of history: this
  API returns `200 OK` for parameters it ignores. **Never trust an unverified filter param here.**

## 3. The result: the population was never the constraint

Ranking a niche's traders by past performance and taking the top-50 is the procedure this project
has already refuted five ways. The obvious hope was that it failed only because we were looking at
the wrong (whale) population. **With the complete population, it still fails.**

**An 8-ranker panel, evaluated out-of-sample** (rank in window A → measure realized copyable
surplus in a disjoint later window B, with **market-clustered** confidence intervals, because many
wallets share the same market and one resolution moves them all together):

| ranker | result |
|---|---|
| past surplus, raw advantage, win rate, avg size, entry earliness, n_markets | fail |
| **CLV** | **fails — and this resolves a standing question** |
| **concentration** (the literal "specialist of this space" test) | fail |

**0 of 40 (ranker × niche) cells** clear the pre-registered bar, across **four independently
scored niches** (esports, tennis, weather, mlb). Every niche returns the same verdict:
*"NOTHING ranks traders within a niche out-of-sample."*

Two findings inside that deserve to be called out:

- **CLV is now resolved, and it's negative.** The project's own record called CLV *"the only
  forward-shaped lead"* — real but **indeterminate-by-power**, with an **ETA of 3–6 months of
  forward accrual** to decide. That ETA assumed CLV could only be accrued *forward*, on the ~3k
  wallets we could poll. The market-side harvest makes the closing line computable
  **retrospectively, for the entire population, today.** The 3–6 month wait collapsed into an
  answer: in esports, CLV's rank correlation is **−0.029** and its top-50 goes on to earn
  **−2.0% [−3.4%, −0.6%]** out of sample. In mlb, rho = **+0.001**. **Stop waiting on CLV.**

  *This overturns a standing project belief, so the metric itself was validated before the
  verdict was accepted:* the tape-derived closing line is **unbiased against outcomes**
  (`mean(close − won) = +0.0003` — a well-calibrated benchmark, as efficiency predicts), and
  `corr(CLV, realized advantage) = +0.675` — strongly positive, so CLV genuinely measures what
  it claims to. It is computed correctly **and it still does not rank traders.** The null is a
  finding, not a bug.

- **"The hidden population is better" is refuted.** The prior weather probe reported hidden
  traders 36% positive vs 15% for tracked. On a same-footing gate (same N-floor, non-MM, fine
  price bands, complete tapes, maker fills included), the hidden pool is **slightly *worse***:

  | niche | tracked (leaderboard) | hidden (harvest-only) |
  |---|---|---|
  | esports | 48% positive | 46% |
  | tennis | 47% | 38% |
  | weather | 42% | 32% |

  The earlier number came from an ungated scan. Widening the net does not, by itself, find better
  traders.

## 4. The one real signal — and why it still doesn't pay

Every negative invites the objection *"you were just underpowered."* The **attenuation test**
settles it: if skill were real but noisily measured, the A→B rank correlation must **rise** with
per-wallet N. **It does.**

| markets per wallet (window A) | esports rho(A,B) | tennis rho(A,B) |
|---|---|---|
| 8–14 | −0.008 | +0.095 |
| 15–24 | −0.022 | +0.074 |
| 25–49 | +0.069 | +0.044 |
| **50+** | **+0.188 [+0.05, +0.32]** | **+0.193 [+0.09, +0.29]** |

**So trader quality IS persistently rankable.** But in those same high-N strata the **top-50's
out-of-sample edge is ≈ 0** (esports −0.07%, tennis +1.4%), while the *rest of the field* runs at
−1.5% to −1.8%.

The ranking persists **because the bad reliably stay bad — not because the good make money.**

### So we tested the inversion: fade them

Fading is *not* copying with a minus sign. **The follower tax flips sign** — the single most
important piece of economics here. When you copy, their buy pushes their side *up* and you pay
~1.3¢ worse; that tax has killed every copy strategy tested. When you **fade**, their buy pushes
their side up, which pushes **your** side (the complement) **down** — you buy ~1.3¢ *cheaper*.
The same market impact that taxes a copier **subsidises a fader**: a ~2.6¢ swing.

| | esports | tennis | weather |
|---|---|---|---|
| fade surplus **over blind** (out-of-sample) | **+1.27%** [+0.15, +2.45] | **+2.13%** [+0.20, +4.08] | +1.70% [−0.01, +3.41] |
| control (fading everyone else) | +0.22% | +0.29% | −0.31% |
| **fade RAW P&L — the money** | **−0.11%** [−1.28, +1.11] | **+0.68%** [−1.24, +2.62] | **+1.03%** [−0.67, +2.74] |
| net after 3% capture cost (incl. 1.3% fade subsidy) | **−1.81%** | **−1.02%** | **−0.67%** |

**The selection is real** — the CI on fade-surplus excludes zero in two niches and the control is
flat, so picking *these specific* traders genuinely does work. **But it does not pay.**

> ⚠️ **An error I made, and the finding hiding inside it.** I first computed bankability on
> *surplus-over-blind* and got a near-positive number. That is **wrong**: if you fade, your
> realized P&L is exactly `p − won` = the **raw** number. The blind baseline is a *benchmark*, not
> something you are paid — crediting it books money you never receive.
>
> The disagreement between the two numbers **is the finding.** These traders lose badly *relative
> to the blind favourite baseline* while being **roughly fairly priced in absolute terms.** They
> are **mediocre, not donors.** There is no donor pool to harvest.

## 5. Bottom line

**Trader-level skill dispersion in these niches — measured on the complete population, not a
whale sample — is too narrow to pay the ~3% capture cost in either direction.**

- Copying the top of a niche: **≈ 0**.
- Fading the bottom of a niche: **≈ 0**.
- And we had the power to see a bankable edge: the market-clustered CI half-widths are
  ~1.2–2.5%, i.e. **narrower than the ~3% we would need to profit.** The region we cannot
  resolve is entirely *below* the region where money lives — so the null is **decision-complete**,
  not merely inconclusive.

This closes the last escape hatch. "We just weren't seeing the right traders" was a real,
testable hypothesis, and the honest way to kill it was to *go see all of them*. We did. They
aren't there.

**Do not re-open this by widening the trader pool again — the pool is now complete.** Widening is
finished as a lever. If edge exists, it is on the **market/price** axis (softness, the favourite
band), not on the question of **who** is trading.

## 6. What was built (all self-testing, `scripts/niche/`)

| script | what it does | its own gate |
|---|---|---|
| `harvest.py` | market-side population harvest | **K1**: the market-side tape must *contain* our wallet-side tape — this is what caught the `takerOnly` bug |
| `roster.py` | per-niche rosters + the certification gate | **K0**: certifies 0 of a 300-wallet pure-noise fleet, excludes a +30% market-maker, blocks the "+0.69 on 2 markets" artifact, kills sub-tax edge — *and still detects an injected true specialist* |
| `rankers.py` | the 8-ranker out-of-sample panel | BH-FDR across the whole (ranker × niche) family — a panel this wide will always crown someone if uncorrected |
| `power_check.py` | attenuation: is the null real or underpowered? | reports the detectable effect size against the 3% bankable bar |
| `fade.py` | the inversion | raw-P&L bankability + a "fade everyone else" control |

## 7. Scope and honest limits

- **Scored niches: esports, tennis, weather, mlb** (4 independent, all null). **Harvested but not
  yet scored: crypto, soccer, other, nba, politics, ufc, nhl** — the population is on disk; the
  scoring query on crypto (14k markets / 26M trades) exceeds practical runtime and needs
  pre-aggregation in SQL before it will finish. This is **incomplete, not done** — but the four
  scored niches agree unanimously, and they include the two the project's own record flagged as
  most promising (esports = softest venue; weather = the niche with the prior positive claim).
- **BUY fills only.** A trader whose skill lives in *exits* (selling before a collapse) is
  invisible here. Copying entries is the use case, so this is a deliberate limit, not an oversight.
- **Truncated markets excluded from scoring** (0.3% of weather → 22% of esports → 28% of crypto).
  Those are the busiest markets, so the scored sample tilts toward less-liquid ones — which, if
  anything, is where edge should be *easier* to find, so it does not rescue the null.
- **~6 weeks of tape** (markets resolving late-May → mid-July), split into two ~3-week windows.
  A skill that only manifests over longer horizons would be missed.

**Safety:** harvested wallets are written to `harvest_fills`, a **separate table the live consensus
path does not read.** This is deliberate and structural — in the live schema `consensus_eligible`
**defaults TRUE** (a naive insert would hand ~90k strangers a vote in the live engine) and
`active=TRUE` would drag them into the per-cycle wallet poll (~167 req/s, 4× the API ceiling).
Writing to a separate table makes that entire class of landmine *impossible*, rather than merely
avoided.
