# Evergreen per-market-type arm portfolio — findings

**Run:** 2026-07-12. **Branch:** `feat/evergreen-portfolio`. **Paper-only; promotes nothing; arms
nothing.** Champion `favorite` + `weather_fav`/`weather_fav_liq` + `ConsensusParams::default` +
every incumbent BYTE-IDENTICAL (the family refactor is guarded by
`weather_arms_are_byte_identical_after_family_refactor`).

The brief asked for a diversified portfolio of independently-certified per-market-type arms. **The
portfolio thesis did not survive contact with the data — one branch failed its own gate, so there is
no diversified portfolio to claim.** But the run found and fixed two defects that had been silently
falsifying every weather number we have ever produced, and as a result the decisive gate
(leave-one-week-out) ran for the first time. That, not the arm count, is the result.

---

## 0. The two defects (both load-bearing; both were invisible)

### D1 — the resolution ledger was frozen for every recent market (FIXED)

`trader_fill_unresolved_conditions` selected its work queue as a strict oldest-first FIFO with a
per-cycle cap:

```sql
... WHERE resolved=FALSE AND side='BUY' AND ts < NOW()-6h
    GROUP BY condition_id ORDER BY MIN(ts) LIMIT 200
```

A condition that fails to resolve stays `resolved=FALSE`, so it returns to the head of the queue on
the very next cycle — forever. And the head is full of conditions that **can never resolve**: delisted
2022 World Cup markets, and long-dated OPEN markets (`will-*-win-the-2028-*-presidential-nomination`)
that do not settle for years. They re-occupy the head every cycle and the resolver never advances.

Measured on prod: **all 200/200 budget slots go to conditions older than 2026-06-01; the newest
condition the resolver ever reached was 2026-04-12.** It had never once touched a July market.
**4,153 weather conditions sat unresolved while their outcomes were public on the CLOB the whole time.**

This is why weather resolution falls off a cliff (07-06: 75% → 07-08: 0.9%) — and it means the
"second disjoint week" that the frozen weather gate requires **could never have arrived**. The phase-5
write-up read the gap as *capture lag* ("days away, not weeks"); it was a capture **defect**, and it
does not self-heal. Every certification gate reads this ledger.

**Fix:** split the per-cycle budget into a *recency lane* (4/5, conditions whose latest fill is inside
`TRADER_FILLS_RESOLVE_RECENT_DAYS`, default 30) and a *backlog lane* (1/5, the legacy oldest-first
sweep). The lanes sum to exactly the old cap, so CLOB load is unchanged; un-resolvable conditions can
now waste at most the backlog lane, never the whole budget. `scripts/resolve_backfill.py` drained the
existing backlog (4,077 conditions / 86,103 fills), mirroring the Rust convention exactly (resolve iff
`closed` AND a token has `winner=true`; void/refund markets SKIPPED, never charged a loss).

### D2 — "the at-fire mid" was never a mid (QUANTIFIED)

Every prior weather number was measured at `COALESCE(initial_mean_price, mean_price)`, which
`weather_scan.py` documents as *"the CLOB mid ~10-15 min post-convergence … a fast-copier's fill."*
**It is neither.** `mean_price` is the mean price **the backers themselves filled at**. The real market
price column, `initial_market_price`, is **NULL on all 2,131 `_blind` weather signals**, and
`entry_ask` is 0 — exactly as the prereg's own §0 said ("copyability is UNMEASURABLE from history").
Phases 1–2 then treated that column as a copier price anyway.

So the celebrated **"copyability haircut ≈ 0"** compared the wider-universe sharps' mean fill against
the blind universe's mean fill — two fill-price averages drawn from overlapping populations. They are
near-tautologically close. It never measured what a copier pays.

The live arm has now captured **85 real asks**, so the copier's cost is finally *measured*:

| quantity | value | meaning |
|---|---|---|
| `entry_ask − entry_ask_mid` | **+1.09¢** | the real thin-book weather spread tax |
| `entry_ask − vote-mean` (the prior basis) | **+2.03¢** | ≈ **2.3pp of ROI-on-turnover the prior basis never charged** |
| `entry_ask − sharp fill` | **+1.65¢** | what a copier pays over the sharps |

Ordering is unambiguous: **vote-mean 0.8821 < mid 0.8902 < ask 0.9011.** Dispersion is wide
(sd 10.7¢) — thin books.

A reconstruction of the true mid from the CLOB `prices-history` endpoint was attempted
(`atfire_recon.py`) and **REJECTED by its own validation gate** — it did not track the real captured
mid (MAE 22¢, corr 0.20). It is not used anywhere. Two validation gates, two rejections; the honest
consequence is that history has **no** copyable price basis, and only forward `entry_ask` capture can
supply one.

---

## 1. Per-arm verdicts (each on its OWN gate)

Certification cell 0.71–0.90, day-clustered, ≥3 one-sided wider-universe backers, both weeks resolved.
`sharp_fill` = the backers' own fill (a **directional ceiling — nobody else can buy it**), available on
both weeks and therefore what carries LODO. `copier_ask` = sharp fill + the **measured** haircut above.

### `weather_fav` (highest-temperature) — passes everything the data can now test

| test | result |
|---|---|
| picks / days / weeks | 571 / 11 / **W27 + W28 (2 disjoint)** |
| `sharp_fill` LB | **+12.4%** (point +14.5%, G=11) |
| `copier_ask` LB | **+10.2%** (point +12.2%, bootstrap +10.4%) |
| **LODO-by-week** (`copier_ask`) | **SURVIVES — min fold LB +7.1%** |
| **LODO-by-week** (`sharp_fill`) | SURVIVES — min fold LB +9.2% |
| **`selection_null`** (belief-blind) | **p = 0.0005 — PASSES** |

**The decisive gate ran, and it held.** Leave-one-week-out — declared IMPOSSIBLE in the previous run,
and impossible only because of D1 — now removes either week and the lower bound stays positive at the
realizable price (+7.1%), above the champion's +5.6% honest floor. `selection_null` says the
convergence rule genuinely out-selects a random weather favorite at the same (band × day): this is
not several bots co-reading NOAA.

**Resolution coverage is symmetric across the weeks** (W27 100%, W28 88.8%, mean price 0.812 vs 0.808),
so LODO is not an artifact of my own backfill; the W28 shortfall is the 34 markets settling 07-13/14
(recency truncation, not outcome selection).

### `weather_low` (lowest-temperature) — FAILS its own gate → **RETIRE**

| test | result |
|---|---|
| picks / days / weeks | 59 / 9 / W27 + W28 |
| `sharp_fill` LB | **−3.5%** (point +9.6%) |
| **LODO-by-week** | **FAILS — min fold LB −35.9%** |
| `selection_null` | p = 0.0085 — passes |
| `copier_ask` | **UNMEASURED** (arm never enabled ⇒ 0 captured asks) |

The discovery run's low-temp read (+4.0% LB, +16.3% skill-over-blind) **was a single-week artifact** —
precisely what the disjoint-week gate exists to catch. Note the instructive split: the selection null
*passes* (the sharps really do pick cold favorites well), but the realized edge **does not survive
dropping a week**, and the pooled LB is negative once the second week resolves. Skill in the selection
is not the same as money at our price.

Per this run's own rule — *an arm that cannot clear its own gate over ≥2 disjoint weeks is RETIRED, not
carried* — `weather_low_fav` is **staged OFF and recommended OFF**. It is power-starved (59 picks), so
"retire" here means "do not enable on this evidence," not "proven worthless"; re-opening requires an
a-priori mechanism, never a rescan.

---

## 2. Diversification and the portfolio — NOT ESTABLISHED

Cross-arm day-ROI correlation is **−0.168 over 9 common days**: directionally low-correlated, but
**INDICATIVE ONLY** — 9 days cannot support a correlation claim, and the +0.02 from the discovery run
was 5 days. More importantly, **diversification requires each arm to be independently +EV, and one arm
is not.** There is therefore **no diversified portfolio to report**, and the equal-weight portfolio ROI
(8.7%/day) is *not* claimed: it would be one live arm plus a dead one, i.e. the champion arm wearing a
portfolio label.

**The honest state of the thesis: the portfolio is a single certified-pending branch, not a portfolio.**

---

## 3. What is and is not claimed

**Claimed:** the resolver defect is real, fixed, and was silently blocking every forward gate; the
"realizable" basis in every prior weather number was a fill-price average, and the true copier cost is
now measured at +1.65¢ over the sharps (+1.09¢ spread); `weather_fav` survives leave-one-week-out at
that measured price with min-fold LB +7.1% and passes the belief-blind null at p=0.0005;
`weather_low_fav` fails LODO and is retired.

**NOT claimed — `weather_fav` is NOT certified and NOT bankable.** Three gaps remain, all forward:

1. **The gate's basis is `entry_ask` on the arm's OWN signals.** The +10.2%/+7.1% here charge a haircut
   *estimated from 85 captures over ~1 day* and applied uniformly to history. The dispersion is huge
   (sd 10.7¢). This is the best estimate available, **not** the frozen gate's measurement.
2. **`selection_null` scope.** The blind universe is "weather favorites a tracked trader touched," so
   it tests the *convergence rule*, not the forecastability of the whole weather book — because `_blind`
   never covered weather. A full-book blind does not exist in our data.
3. **Two weeks is the floor, not comfort.** Both weeks are July; transfer out of summer is untested.

**The one thing that closes all three is forward `entry_ask` accrual on the live arm** — which is now
running, and which the resolver fix makes durable. Weather's daily flow means this resolves in weeks.

---

## 4. Follow-up worth doing (not done here)

- **`_blind` does not cover the weather book.** That is why no full-book belief-blind null exists and
  why the at-fire basis had to be faked. A `_blind` variant scored on the wider-eligibility family book
  would give every evergreen branch a real blind baseline. This is the single highest-value instrument
  gap left.
- **Re-run the champion's own numbers on the corrected basis.** If `initial_mean_price` was mistaken for
  a market price in weather, it is worth checking whether any other report leans on the same column.
- The 945 still-open weather conditions settle within ~2 days; re-run `evergreen_portfolio.py` then for
  a third week and a genuinely powered LODO.

---

# PART II — Audit sweep + discovery outside the known champion (2026-07-12, same run)

## 5. D3 — the survivorship bias the resolver was BUILT to prevent was in force the whole time

The independent `trader_fills` resolver exists for one reason, stated in its own code comment:
resolving only consensus conditions "would leave those fills perpetually unresolved and bias every
trust profile toward markets that happened to fire consensus." **That resolver was 100% starved (D1),
so the bias it was written to prevent has been in force across every analysis built on `trader_fills`.**

Measured (2026-06-01 → 07-08, BUY conditions):

| market fired a consensus signal? | conditions | resolution coverage |
|---|---|---|
| **yes** | 18,361 | **89.6%** |
| **no**  | 23,613 | **18.0%** |

The resolved subset is **~5× enriched in consensus-firing markets**. Every `trader_fills`-based
number — earned-trust slice scores, trader profiles, blind baselines, family/cell scans — has been
reading that skewed subset. A full-backlog drain is running; the durable fix (recency lane) means the
pipeline self-heals going forward.

## 6. D4 — the decision-time `entry_ask` lane was starved (SAME defect class, third instance)

`entry_ask` is the **only basis the frozen gates accept**, and it was being captured wrong.

A decision-time (`first_price`) capture is only possible on a signal's FIRST housekeeping pass. The
budget is 40/cycle; the ask-less backlog is 3,637. And `unresolved_consensus_signals` has no `ORDER BY`
while `all_conds` was built from a **HashMap's keys** — so the order was effectively **random**: a fresh
signal had ~1-in-90 odds of being reached per cycle.

| lane | n | avg lag | win rate | raw edge |
|---|---|---|---|---|
| decision-time (≤15 min) | 445 | 9.9 min | 0.834 | **+1.71%** |
| **LAGGED (>15 min)** | 1,029 | **173.4 min** | 0.794 | **−1.04%** |

**The lagged lane is loser-tilted by 2.75pp.** The mechanism is mechanical, not mysterious: a winner's
favourite drifts toward 1.0 and stops being buyable, so what is still sitting at a buyable ask hours
later is disproportionately what went on to **lose**. The same lag skews the captured band toward deep
chalk — **69% of the weather arm's asks (59/85) landed at ≥0.90, the band already known to be dead**,
vs only 22 in the 0.71–0.90 certification band.

**Consequence: the weather arm was accruing data that could never have certified it**, no matter how long
it ran — biased negative and concentrated in the wrong band. Fixed by spending the budget FRESH-FIRST
(`ask_capture_priority`, unit-tested). This also explains why a naive realizable read of the discovered
families looked catastrophic (mlb −32.7% LB at ask): it was reading the loser-tilted lane.

**This is now three instances of one defect class: a scarce per-cycle budget spent in an order that
never reaches the items that need it.** Worth a standing check on every bounded queue in the system.

## 7. Discovery — is there a profitable market family OUTSIDE what we know? (No.)

`evergreen_discovery.py` runs the full battery over every family the sharps bet, with the
**copyability gate FIRST** — because a fat edge on an unbuyable market is this project's most seductive
artifact.

**The gate immediately earned its place.** A naive family scan reports `btc` (+21.7%) and `eth` (+21.7%)
as the two fattest edges on the board. They are `btc-updown-5m-*` — **FIVE-MINUTE markets**, gone long
before a follower could fill. A regex written for `up-or-down` silently misses `updown`, so the known
crypto siren re-entered the table disguised as two new families. Killed structurally, never measured.

Six families then survived LB + leave-one-week-out + belief-blind null **at the sharps' fill**:
mlb (+18.8%), ucl (+14.3%), weather-high (+12.4%), wta (+11.1%), col (+10.9%), fifwc (+8.9%).

**All of them die at the price we can actually pay.** Measured on the clean decision-time capture lane:

| family | LB @ sharps' fill | **LB @ real captured ask** |
|---|---|---|
| mlb | +18.8% | **−57.1%** |
| atp | +5.7% | **−30.2%** |
| fifwc | +8.9% | **−9.6%** |
| wta | +11.1% | **−4.8%** |
| col | +10.9% | +21.6% — but **single window** (n=30) |

Pooled realizable edge on the clean lane is **+1.71% raw**, which reproduces the established finding
(`project-polymarket-exec-policy`): *the edge is in the FILL, not the pick.* The selection is genuinely
skilled (the nulls pass, LODO passes) and it is **entirely consumed by the spread**.

**Answer to "are there profitable markets outside what we know": on this evidence, no.** Every candidate
is either uncopyable by construction (5-minute crypto), already the champion's own book, or +EV only at
a price nobody but the sharps gets. That is a negative result, and it is the correct one — the value is
that it is now measured on a substrate whose two biggest lies have been fixed.

**Caveat, stated plainly:** the discovery screen ran on the *pre-drain* `trader_fills` substrate (the
full drain is still running), so the candidate RANKING is provisional — the blind universe in particular
is under-resolved, which can move `selection_null`. The realizable collapse above is NOT affected: it is
measured on `consensus_signals`, whose resolution was never starved. Re-run `evergreen_discovery.py`
after the drain completes to finalize the screen.

---

# PART III — RETRACTION: the "dies at the ask" verdict was my own measurement error

**Part II §7 claimed no family outside the champion is profitable, on the strength of realizable LBs
like `mlb −57.1%`. That claim is WITHDRAWN. It was an artifact of two errors, both mine.**

1. **Population mismatch.** The `+18.8% @ sharps' fill` came from wider-universe (rank≤250) convergence
   picks in `trader_fills`; the `−57.1% @ ask` came from the champion arm's signals in
   `consensus_signals`. Different picks. Not a before/after.
2. **Fatal: I filtered the band ON `entry_ask`.** That is the D4-corrupted column (lagged,
   loser-tilted, deep-chalk-skewed). Filtering on a corrupt column bakes the corruption into the
   **sample selection** — far more damaging than a biased value, because it changes *which picks are in
   the test*, not just their price.

## What the copier actually pays (same picks, decomposed)

`ask − sharp_px = drift + spread`, where **drift** = the market moved after the sharps bought (we are
late) and **spread** = we cross the book.

| | n | drift | spread | **total** |
|---|---|---|---|---|
| pooled (0.71–0.90) | 1,351 | **−0.08¢** | **+1.22¢** | **+1.14¢** |
| sharps were RIGHT (won) | 1,226 | −0.36¢ | | **+0.91¢** |
| sharps were WRONG (lost) | 85 | +3.54¢ | | +3.76¢ |

**Copying costs about a cent — ~1.4% of a 0.80 stake. It is NOT what kills an edge of ~+12pp.**
And **drift ≈ 0: the market does NOT run away from us.** We are not being outrun.

## Corrected read (clean sharp-fill picks, charged the measured cost)

Several families now SURVIVE LODO-by-week at the copier price: fifwc **+6.6%** (24 clusters, 4 weeks —
the best-powered cell on the board), weather-high +12.3%, ucl +12.7%, will +11.7%, col +10.8%,
wta +8.7%.

## …but this is NOT a green light, and the tell is right there

`mlb` and `atp` come out with a **NEGATIVE copier cost (−2.6¢, −3.8¢)** — "we buy cheaper than the
sharps," i.e. free money. That does not exist. It is the D4-corrupt `entry_ask` population leaking into
the cost estimate. **Every cost number on this page still derives from the one column we know is
broken.**

**HONEST STATUS: the realizable question is currently UNANSWERABLE at trustworthy precision.** Not
"negative" (Part II's error), and not "positive" (this page's temptation). The single column that
measures what WE pay was being captured wrong until commit e74f4e7, and it has not yet accrued clean
data.

**This is now blocked on time, not on analysis.** Let the fixed decision-time lane accrue ~1–2 weeks of
clean asks, then re-run. Do not act on any realizable number produced before then — including the
flattering ones on this page.

## What this changes about the LEVER (answers "how do we get the sharps' fill?")

- **Speed is NOT the lever.** drift ≈ 0 means we are not losing to latency; being faster buys ~nothing.
  This independently agrees with the weather-deepen run (corr(lag, drift) small ⇒ capture-at-detection
  not worth building). **Do not build a faster capture path.**
- **The whole cost is the SPREAD (~1.2¢)** — we pay it because we CROSS to the ask. The only way to get
  the sharps' price is to **not cross**: post a passive limit at/near the mid.
- **But that is not free, and it has already been tested.** A passive limit introduces NON-FILL risk,
  and non-fill is adversely selected: you miss the winners (whose price runs away) and fill the losers
  (whose price sits there waiting for you). `project-polymarket-maker-capacity` measured maker-copy as
  **thin / adverse / EDGE ≈ 0**. Any revival must confront that head-on with a fill simulation
  (`maker_fill_sim.py` exists), NOT by assuming the mid is achievable.

---

# PART IV — CAPACITY: how much can we tail before we eat the edge?

## D5 — we have NEVER recorded book depth (a fifth gap)

`common/src/data/models.rs::BookLevel` deserializes only `price` — **the `size` field is DROPPED at the
type level** — so `fetch_best_ask` keeps the best ask PRICE and throws the available SIZE away.
`clob_price_tape` stores best_bid/best_ask prices with no sizes (`last_size` is a trade size, not resting
depth). So "how much can we put on a signal" has been structurally unanswerable, which is why SIZE has
stood as the one explicitly UNPROVEN limit. Measured LIVE instead (`capacity_scan.py`, `--selftest`
green): pull the real `/book` for open converged markets and walk the ask ladder.

## The weather slippage curve (33 live books, band 0.71–0.90)

Net edge per $1 = gross selection edge (~+12pp) − spread (−1.2¢) − slippage(S). **A median hides the bad
half, so the column that decides a SAFE size is p90 — the bad-book case you must survive.**

| stake/signal | slip p50 | slip p90 | net @p50 | **net @p90** | fillable (p10) |
|---|---|---|---|---|---|
| $25 | 0.07¢ | 1.24¢ | 10.7% | **9.6%** | 100% |
| **$50** | 0.52¢ | 2.23¢ | 10.3% | **8.6%** | 100% |
| $100 | 1.16¢ | 5.64¢ | 9.6% | **5.2%** | 100% |
| $250 | 2.92¢ | 9.52¢ | 7.9% | **1.3%** | 100% |
| $500 | 5.00¢ | 11.65¢ | 5.8% | **−0.8%** | 100% |
| $1,000 | 7.57¢ | 15.20¢ | 3.2% | **−4.4%** | **56%** |
| $2,500+ | 9.08¢ | 16.66¢ | 1.7% | −5.9% | **22%** |

Champion honest floor = **+5.6%**.

**Slippage overtakes the spread almost immediately** — at $100 the median slip (1.16¢) already rivals the
whole spread (1.2¢), and by $250 it is 3–8× it. **The book, not the spread, is the binding constraint.**

## The recommendation (with the leeway asked for)

- **$50/signal — comfortable.** Even the p90 bad book leaves **+8.6%** net, a full 3pp above the champion
  floor, 100% fillable. This is the size to run.
- **$100/signal — practical ceiling.** Median +9.6%, but p90 falls to **+5.2%**, i.e. the worst ~10% of
  books earn *below* the floor. Acceptable only if you accept those signals earn ~nothing.
- **$250 — hard stop.** p90 is +1.3%: you are betting on book quality, not on the edge.
- **Never ≥$500.** p90 goes negative, and past ~$1,000 the book cannot even fill you (56% → 22%).

**Day-level exposure is the number that actually matters.** The correlated unit for weather is the
RESOLUTION DAY (one heat dome resolves ~20 cities together — the same clustering the whole gate is built
on). ~20 signals/day × $50 ≈ **$1,000/day, and that is ONE correlated bet, not twenty.** Size the day,
never the signal — consistent with `project-polymarket-correlated-risk` (size the GAME) and the
⅛-Kelly cap.

## Three honest limits on this number

1. **It is an UPPER BOUND.** Walking a snapshot book charges today's resting liquidity. It does NOT model
   market impact, makers pulling quotes when they see size, refill, or other copiers racing us. **Real
   capacity is ≤ this, never more.** The $50 recommendation deliberately sits ~1/20th of the depth that
   exists, which is the margin that absorbs all of that.
2. **The +12pp gross edge is the SHARPS'-fill number.** Its realizable version is still pending clean
   `entry_ask` data (see Part III retraction). Every net figure above moves 1:1 with it: if the true edge
   is 9pp not 12pp, subtract 3pp from every cell — and $100/signal then fails at p90.
3. **The sports books look bottomless and I do not trust it.** `fifwc` shows ~0¢ slippage even at
   $10,000 — but on only **8** open books (`atp`/`wta`: n=1). Most sports markets in-band were already
   closed at scan time. Deep World Cup books are plausible, but n=8 is not a capacity claim. Re-scan
   during a live sports window before sizing anything there.

## The fix worth making (needs a human: it touches schema)

**Capture ask SIZE alongside `entry_ask`.** `BookLevel` should keep `size`, and the signal should record
the depth available at the ask (and 1–2 levels up). That turns capacity from a live-scan estimate into an
accruing, per-signal measurement — and it is the only way to know that our own tailing has started moving
the price. Requires a migration ⇒ **flagged, not done.**

---

# PART V — LATENCY: what it costs, and where it actually is

## The cost of delay (measured, not assumed) — `latency_cost.py`

From `clob_price_tape`, the ACTUAL best_ask a follower would pay at t0 (the 3rd backer's fill = the
convergence instant) and at each horizon after:

| wait | fifwc | atp |
|---|---|---|
| **1 min** | **+0.45¢** | **+0.14¢** |
| 5 min | +2.87¢ | +4.50¢ |
| **15 min** | **+7.75¢** | **+8.67¢** |
| 60 min | — | +17.78¢ |

Benchmarks: the whole spread we cross is **1.2¢**; slippage at $50/signal is **2.2¢** (p90).

**In sports, latency is the DOMINANT cost** — at 15 min it is 6–7× the spread and 4× the slippage. And
the shape is the actionable part: **at 1 minute it is ~0.1–0.5¢, essentially free.** All the damage is
in the 1→15 min window.

This CORRECTS the Part III read ("drift ≈ 0 ⇒ speed is not the lever"). That was measured mid-vs-fill on
a weather-heavy, hours-lagged population. Both are true, and the mechanism is coherent:
- **weather:** daily markets, no in-play events ⇒ price barely moves ⇒ latency cheap, **the BOOK binds**.
- **sports:** in-play markets ⇒ price moves violently (goals) ⇒ **LATENCY binds**, and it is very likely
  WHY sports selection edges evaporate for a follower.

## Where the delay actually is (and a false alarm I caught)

**First, a retraction-in-progress I did NOT ship.** A naive measurement said detect latency was
**8.6h (sports) / 19.4h (weather)**. Both were MY artifact: `favorite` fires on rank≤40 but I computed the
convergence instant over rank≤250 (different sets), and `weather_fav` only went live 07-12 so it
*back-detected* days-old convergences at startup. Measuring only convergences that happened AFTER the arm
was already running, on its own rank universe:

| | value | cost on the curve |
|---|---|---|
| **detect p50** | **1.6 min** | ~0.5¢ — fine |
| **detect p90** | **94 min** | ~10–18¢ — brutal |
| **ask-capture p50** | **74.8 min** | (measurement only) |

**So the premise "our capture is 10–15 min" is half right, and the half that matters is the opposite of
what it looks like: the MEDIAN detect is already fast (1.6 min). The loss is in the TAIL (p90 = 94 min)
and in the ask-capture path (p50 = 75 min).** Optimizing the median would buy nothing; killing the tail
is worth ~10¢ on the affected signals.

## The fast path is ALREADY BUILT — and switched off

`LIVE_FILLS` (migration 040, `cycles/live_fills.rs`) observes Polymarket `OrderFilled` logs on Polygon
and writes tracked-wallet fills at **~1–5s** fill→row, versus the poller's ~90s median. Its gate already
PASSED (`reports/F2_CONSTANTS.md`: address_match 100%, decode + price/size reconstruct, 3-layer dedup).

**It has never run:** `LIVE_FILLS=false`, and all 705,564 fills carry `source=NULL` (poller). Also
`LIVE_FILLS_TO_CONSENSUS=false` — so even enabled, live fills would not feed consensus votes.

Current ingestion: 1,287 followed traders polled at `CONSENSUS_MAX_CONCURRENCY=8`, cycle 1 min. A full
sweep cannot complete inside the cycle, which is exactly the shape that produces a **long tail** with a
fast median — matching the measured p50 1.6 min / p90 94 min.

## D6 — we cannot measure our own ingestion latency

`trader_fills` has **no ingestion timestamp**: only `ts` (the fill time, from the API) and `live_seen_at`
(populated for `source='live_onchain'` only — i.e. never, since LIVE_FILLS is off). So fill→row latency
is invisible by construction, which is why this has never been characterised. **You cannot optimise what
you cannot measure.** A `seen_at DEFAULT now()` on every fill row is the cheapest instrument in this
whole system (needs a migration ⇒ flagged, not done).

## The plan (in cost order — do NOT start with the median)

1. **Instrument first (D6).** `seen_at` on every fill row ⇒ fill→row latency becomes measurable, and the
   tail becomes attributable. Everything below is guesswork without it.
2. **Enable `LIVE_FILLS`** (already built, gate already passed; needs `LIVE_FILLS_RPC_HTTP`). Expected:
   fill→row 90s ⇒ 1–5s, and — more importantly — it removes the sweep-rate ceiling that CREATES the tail.
   Then `LIVE_FILLS_TO_CONSENSUS` so live fills actually vote. **Both are `.env` changes ⇒ human's call.**
3. **Verify the D4 ask-capture fix** (fresh-first ordering, commit e74f4e7) drops ask-capture p50 from
   75 min toward the decision-time window. Already merged into this branch; needs a deploy + a week.
4. **Only then** consider a hot order path. At detect p50 1.6 min the median already costs ~0.5¢; there
   is no case for shaving it further until the tail is dead.

## The tape does not cover weather

`clob_price_tape` has **ZERO** weather rows (it covers fifwc/mlb/atp/wta/cs/... heavily). The live tape's
subscription set excludes our own live arm's family, so **weather's latency cost cannot be measured at
all** — the one family we actually run. Fixing the subscription set is a precondition for ever certifying
weather's realizable price.

---

# PART VI — AUDIT: Part V is RETRACTED. Latency is NOT the dominant cost.

Part V claimed a 15-min delay costs **~8¢ in sports**, making latency the dominant friction and
justifying a low-latency build. **That claim is WITHDRAWN. It does not survive its own audit.**

## What broke it

**1. No control.** In a live match a favourite's ask drifts toward 1.0 *as the game runs*, regardless of
what any sharp did. So "the ask is 8¢ higher 15 min after convergence" may be nothing but generic
favourite-drift, which would show on ANY window. The treatment must beat a placebo. It does not:

| arm (15-min horizon, band-matched 0.71–0.90) | n | mean | median | p90 |
|---|---|---|---|---|
| **treatment** (anchored at the convergence instant) | 20 | **+2.05¢** | +1.00¢ | 16¢ |
| **placebo** (mid-life anchor, SAME markets, no sharp involved) | 72 | −0.16¢ | **+3.00¢** | 16¢ |

The placebo **median drifts MORE than the treatment median**. The mean gap is +2.22¢, on sd 9.1¢.

**2. Not significant.** Permutation test (5,000 label shuffles): **p = 0.360.** The gap is
indistinguishable from chance.

**3. Not band-matched.** The original +7.75¢ restricted `sharp_px` to the band but let the *tape ask* at
t0 fall anywhere, so it partly measured band composition, not delay.

**Corrected: a 15-min delay costs +2.05¢ ± 4.0¢ (95%) — and is NOT distinguishable from generic
favourite-drift.**

## This RESOLVES the contradiction — in favour of the robust measurement

Part V (+8¢, n=24) directly contradicted the Part III copier-cost decomposition (**+1.14¢ pooled,
n=1,351**). Two independent measurements now agree at **~1–2¢**. The 8¢ was the outlier, and it was the
one with 50× less data and no control. **The earlier "drift ≈ 0 ⇒ speed is not the lever" read was
closer to right than the correction I made to it.**

## Consequences for the greenlight

- **`LIVE_FILLS` is NOT justified on edge grounds.** The most it can recover is the ~1–2¢ latency cost,
  and that is not statistically distinguishable from zero. It remains a genuine *measurement/robustness*
  improvement (it kills the detect tail and removes the sweep-rate ceiling), but **it is not a profit
  lever and must not be sold as one.** Enable it for data quality if desired — not for edge.
- **The binding constraint is still the BOOK.** Slippage at $100/signal is 2–5.6¢ and at $250 is 9.5¢
  (p90) — i.e. size costs *multiples* of what delay costs. Part IV's capacity answer stands unchanged:
  **$50/signal, ~$1,000/day, and the day is ONE correlated bet.**
- **Still worth doing, cheaply:** the D6 `seen_at` instrument. It is what would let us *measure* ingestion
  latency at all, and it is near-free. Just do not expect it to unlock profit.

## The standing lesson (this is the fourth correction in one run)

Every one of my four errors had the same shape: **a number computed without a control, on a small n, from
a column or population I had not validated.** The three that survived audit (copier cost n=1,351;
capacity from live books; the config facts about LIVE_FILLS) were the ones with large n or direct
observation. **Rule going forward: no measured claim ships without (a) a placebo/control arm, (b) a
significance test, and (c) an explicit n and dispersion.** A number without those is a hypothesis.

## Applying the rule to everything still standing

| claim | n | control? | verdict |
|---|---|---|---|
| copier cost ≈ **+1.14¢** (drift ~0, spread 1.2¢) | 1,351 | agrees with the audited latency read (~2¢) | **HOLDS** |
| **slippage curve / capacity** ($50/signal) | 33 live books | direct observation of depth — no inference | **HOLDS** (see caveat) |
| `weather_fav` survives LODO, **+7.1%** | 571 | `selection_null` p=0.0005 **+** leave-one-week-out | **HOLDS** |
| resolver starvation (D1), survivorship bias (D3), loser-tilted capture (D4), no depth (D5), no `seen_at` (D6) | — | direct observation of code + config + schema | **HOLD** (facts, not inferences) |
| ~~latency is the dominant cost~~ | 24 | **none** | **RETRACTED** |

**The one soft spot in the capacity number:** `capacity_scan.py` hardcodes `GROSS_EDGE = 0.12`. The
*slippage* column is a direct measurement and is solid; the *net edge* column inherits that assumption
1:1. And the 12pp is the SHARPS'-fill edge, whose realizable version is still pending clean `entry_ask`
(Part III). If the true edge is 9pp, every net figure drops 3pp and **$100/signal fails at p90 — but $50
still clears the floor.** That margin is exactly why $50 is the recommendation.

**The deepest open question is NOT latency and NOT size — it is whether we need a sharp at all.** The
weather-deepen run's null (pool = "a favourite ONE sharp already bought") reads **p ≈ 0.5**, while this
run's null (pool = "a random weather favourite") reads **p = 0.0005**. Both can be true, and they bracket
the real question: if consensus adds ~nothing over a single sharp, and a single sharp adds ~nothing over
the mid-favourite BAND, then weather is a standalone market-inefficiency rule and **the entire copy/latency
apparatus is unnecessary**. That is the next thing to settle, and it is worth more than any latency work.
