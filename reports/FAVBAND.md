# FAVBAND — the liquid, tight-spread US favourite band

**Status: NOT CERTIFIED, k=0. 4/6 pre-registered criteria. One implementable candidate, two open blockers.**
Instrument: `scripts/favband.py` (self-testing, read-only, never trades).
Gate: `~/winmon/PREREG-2026-07-18-GRAVEYARD-RESWEEP.md`. Written before scanning.

---

## The strategy, precisely

Buy the favourite in the **0.80–0.98** band on the **US venue**, at a **fresh pre-game entry**
(< 30 min to game start), restricted to markets that are **liquid** (≥ 20 pre-game trades) **and
quoted no wider than 1¢ at the moment of entry**.

Settle on the venue's own market record. Cost = real fee `0.05·p·(1−p)` + the actual half-spread paid.

## What it earns

| basis | net ROI-on-turnover | 95% CI (event-clustered) |
|---|---|---|
| Roll estimate (archive-only) | +1.52% | [+0.41, +2.64] |
| **pay the MEAN quoted spread (3.71¢)** | **+0.23%** | [−0.87, +1.33] |
| **SELECTIVE — trade only the 1¢ book** | **+1.52%** | [+0.41, +2.64] |

4,159 entries, 1,035 events, 27 leagues. Gross calibration gap **+2.54pp** at a mean price of 0.8887.

**The whole strategy lives or dies on that last row.** The quoted spread is heavily skewed — 70% of
quotes sit at 1¢ but a wide tail drags the mean to 3.71¢. Because the spread is *observable before
you trade*, you can select into the tight book. Passively accepting whatever is quoted earns nothing.

## Gate scorecard

| # | criterion | result | |
|---|---|---|---|
| 1 | fresh executable entry | 3,640/4,159 within 30min, gap +2.50pp | **PASS** |
| 2 | survives +1¢ cost | +0.41%, LB −0.69 | **FAIL** |
| 3 | ≥2 regimes, both positive | fwc 61.1% (<80% ✓); H1 LB +0.06, **H2 LB −0.24** | **FAIL** |
| 4 | leave-one-league-out | all 6 drops significant (+1.30% … +1.81%) | **PASS** |
| 5 | capacity ≥500 contracts | median pre-game volume 8,838 | **PASS** |
| 6 | not stale-driven | fresh +2.50pp carries it (3,640 of 4,159) | **PASS** |

Criterion 4 is the one that killed every predecessor, and this is the first arm to pass it.
Criteria 2 and 3 are why it is not certified.

## Why this is not the previous five false positives

- **Complete universe.** 199,411 cleanly-resolved markets, not a 776-event slice.
- **No imputed prices.** 16,026 symbols with no real pre-game trade are DROPPED and counted. The
  retracted "+6.95%" came from `COALESCE(entry_ask, initial_market_price + haircut)`, where the
  picks *without* a real price were the profitable ones (98.7% win vs 87.8%).
- **Orientation validated at 100.00%** against official DMR settlement on 3,389 symbols, and the
  guard raises rather than emitting an inverted result.
- **Real fee schedule**, not the 3% phantom still wired into `board.rs::render`.
- **True event clustering** — a game bundles ~3.7 correlated submarkets; the self-test asserts that
  clustering *widens* the CI on correlated rows.
- **Not one tournament.** This is what the World Cup soccer arm (54 events, 100% `fwc`) failed, and
  what `favorite_v2` failed before it.

## The two blockers

### 1. Cost — mostly resolved, and it is the reason for the selective rule
Roll's estimator gave a 0.96¢ mean half-spread; the true quoted spread is **1.86¢ mean / 0.50¢
median**. Roll understated by ~2×, exactly as its bias direction predicts. This is now measured,
not assumed — and it converts the strategy from "buy the band" to "buy the band **when it is tight**."

### 2. Capacity — semantics RESOLVED, instrument BUILT, measurement pending market hours
**`us_quotes.bid_depth_usd` / `ask_depth_usd` are LEVEL COUNTS, not dollars.** Verified 2026-07-19
against the full order book on **19/19 live markets, 100% agreement**. Reading them as money
understates real depth by ~500×: a favourite-band market showing `bidDepth 9` actually had
**$3,180 resting at the touch**.

The real book is at `/v1/markets/{slug}/book` (px *and* qty per level). `scripts/us_book_capture.py`
now records dollars at the touch, dollars in the book, and slippage to lift $50/$100/$500 into
`us_book_depth`. Verified: 1,136 books written per sweep, ~0.14s capture lag.

**Three venue facts that will bite anyone who assumes** (all now self-tested):
1. The ask side is called **`offers`**, NOT `asks`. A consumer looking for `asks` sees an empty book
   and reports "no liquidity" — indistinguishable from a dead feed. This cost a run.
2. `bidDepth`/`askDepth` on `/bbo` are level counts.
3. `qty` is in **shares**; notional = `px * qty`.

**The venue also emits corrupt levels**, observed live:
`{"px": {"value": "USD", "currency": ""}, "qty": "\b"}` — value/currency transposed and qty
carrying raw bytes, an upstream protobuf field-mapping bug. A tolerant parser would coerce that into
"liquidity". Levels are strictly validated (`0<px<1`, qty finite and positive) and rejects are
COUNTED, never dropped silently.

**Still pending:** every sweep so far has run off-hours (4 band markets, 13.5¢ median spread — the
dregs). The capture must run **during active sports hours** before capacity can be stated. Nothing
here yet contradicts or confirms tradeable size.

## The forward test (built 2026-07-19, `scripts/favband_forward.py`)

**This is the only thing that can answer "is it profitable."** Two reasons:

1. **The retrospective window cannot be extended.** Nothing in the repo fetches the venue's
   time-and-sales or daily market report, and there is no public URL — `polymarket.us/reports/...`
   returns the Next.js catch-all. Those archive files were obtained externally. So H2 instability
   (criterion 3) is **unresolvable retrospectively**; only forward accrual settles it.
2. **The strategy needs a live quote.** It only trades a tight book, which a backtest can only
   approximate — and the Roll approximation understated the true spread by ~2×.

The harness records the **executed basis this project has never had**: the VWAP to fill $50 walking
the real offer side, the quoted spread, dollars at the touch, slippage, and lead time — at the
moment of decision. A market without a live two-sided book is a **SKIP with a reason**, never a
synthetic fill.

**Orientation is explicit and tested both ways.** If the favourite is side 1, our ask is
`1 − side0_bid` (*not* `1 − side0_offer`, a price we could never get) and our size is the side-0 bid
depth. The self-test asserts the wrong branch is not taken.

**A bug the self-test caught before it shipped:** `0.90 − 0.89 == 0.010000000000000009` in binary
float, so `spread > MAX_SPREAD` rejected an *exactly*-1¢ book. 1¢ books are ~70% of the tradeable
set — the strategy would have silently traded nothing while reporting no edge. Fixed with an
explicit epsilon.

### Pre-registered forward gate — nothing is certified until ALL are met
- ≥ 60 settled events
- ROI lower bound > 0 **at the executed VWAP**, event-clustered
- ≥ 2 distinct competitions, each individually positive
- ≥ 2 disjoint weeks, each individually positive

`./favband_forward.py --report` prints this with unticked boxes. **A positive mean is not a result.**

## Operations (local, reversible — nothing is committed)

Two launchd agents are loaded locally and accruing:

| job | script | interval |
|---|---|---|
| `com.tue.favband.book` | `us_book_capture.py --once` | 600s |
| `com.tue.favband.forward` | `favband_forward.py --once` | 300s |

Logs: `~/Library/Logs/favband/{book,forward}.{log,err}`.

**To stop:**
```
launchctl unload ~/Library/LaunchAgents/com.tue.favband.{book,forward}.plist
```

⚠️ **They run out of `wt/favband`, a feature worktree.** This is the pattern that killed the tape on
2026-07-16 (a writer living only on a feature branch, so `main` had no writer at all). It is safe
only while this worktree is never switched off `feat/favband`. **The durable fix is to merge these
scripts to `main` and repoint the agents at `wt/capture`.** Until then, treat this as temporary.

## Refinement round 2 (2026-07-19) — four things learned without waiting

### 1. The intl archive CANNOT validate this. Contaminated, not underpowered.
`trader_fills` spans 903 day-partitions, so it looked like a 3.5-year out-of-sample test of the
mechanism. It is not. **The resolution backfill covers only 8.3% of 2025–26 fills, and coverage
varies 4.4% → 10.8% across price bands** — a 2.5× swing on the exact axis being measured. The
resolved subset is not a random sample, so any calibration computed on it inherits the selection.
Measured gap there was +0.09pp [−2.70, +2.89] on 474 events — a CI wide enough to *contain* the US
estimate, so it neither confirms nor refutes. **Conclusion: this asset is not a validator. Do not
use it as one.**

### 2. The tight-spread rule IS executable — vulnerability cleared
The whole economics depend on trading only the 1¢ book, and the backtest could only approximate
that with a market-level Roll average. If spreads flickered, the rule would be fiction. They don't:
a market quoted ≤1¢ is **still ≤1¢ with 95–99.7% probability over 5–40 minutes**, mean widening
0.00–0.11¢. 69.9% of band quotes are tight. **You can see the tight book and still be trading it
when you act.**

### 3. H2 weakness is NOT composition — but it is also not decay
The market mix shifted hard between halves (fwc 71.7% → 49.6%, mlb 8.4% → 16.4%). That was the
obvious explanation, and it is **wrong**: reweighting H2 to H1's league mix moves the result by
**−0.04pp** of a −0.58pp gap. The weakening is within-league (fwc −0.61pp, mlb −2.42pp, itfwo
−0.78pp).

But the magnitudes are small and the CIs overlap almost entirely: **H1 +1.61% [+0.02, +3.07],
H2 +1.03% [−0.45, +2.46]**. Both halves are positive. The gate criterion fails on H2's lower bound,
but the H1→H2 *difference* is well inside noise. **This is a power problem (10 days per half), not
evidence of an arm dying.** It cannot be resolved with more slicing — only with more events.

### 4. It is NOT a World Cup artifact
Excluding `fwc` entirely: **+1.22% [−0.35, +2.72] on 1,016 events.** The tournament is not carrying
the result — which is what killed `favorite_v2` and the earlier soccer arm.

### ⚠️ Reproducibility defect found and fixed
`us_markets.parquet` is a **live file** refreshed by the `com.tue.consensus.usquotes` launchd chain.
It grew **224,614 → 247,847 rows mid-session**. Every measurement above was read off a moving
target. `favband.py` now stamps the snapshot (sha256, mtime, size) on every run. On the refreshed
snapshot the arm reads **+1.33% [+0.24, +2.39]** vs +1.52% before — **the estimate drifted toward
zero as power grew**, which is the direction that warrants caution, not comfort.

## Next actions, in order

1. **Accrue during active sports hours.** Both agents are running but every sweep so far has hit
   off-hours dregs (4–5 band markets, 6–13.5¢ median spread, 1 tradeable). Capacity and the forward
   gate both need real sessions. This is calendar-bound: nothing to engineer, only to wait.
2. **Merge to `main` and repoint the agents at `wt/capture`** — remove the feature-worktree hazard.
3. **Re-run the gate at the executed VWAP** once ≥60 events have settled. H2 stability is answered
   here or not at all.
4. **Decide sizing** only after depth data exists. `STAKE_USD = 50` is currently an assumption the
   harness *prices*, not a capacity claim.

## Standing warnings

- The tape can die silently. Consumers of a dead feed **fail CLOSED** — a dead tape reports "no
  signals qualified", which is indistinguishable from "no edge". This cost 2d17h of tape on
  2026-07-16. `favband.py` raises on a broken universe, settlement or orientation rather than
  returning an empty result.
- `docker compose up -d postgres` **only**. A bare `up` starts the live trading containers.
- Do not switch `wt/capture` off main. Running capture from a feature worktree is how it died.
