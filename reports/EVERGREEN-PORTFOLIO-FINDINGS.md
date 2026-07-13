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
