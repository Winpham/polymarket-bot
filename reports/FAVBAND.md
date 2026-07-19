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

## Next actions, in order

1. **Capture real dollar depth.** Extend `us_quote_capture.py` to record the full book (or at least
   size at the touch) and rename the misleading columns. Until this exists, sizing is unanswerable.
2. **Forward-test the selective rule.** The strategy needs a live quote at decision time, which the
   backtest could only approximate. Pre-register: ROI LB > 0 at the *executed* spread, ≥ 60 events,
   ≥ 2 competitions, ≥ 2 disjoint weeks.
3. **Re-measure H2 instability** on a longer window. The second-half LB of −0.24 may be a 10-day
   power artifact or may be the arm decaying; 21 days cannot distinguish these.

## Standing warnings

- The tape can die silently. Consumers of a dead feed **fail CLOSED** — a dead tape reports "no
  signals qualified", which is indistinguishable from "no edge". This cost 2d17h of tape on
  2026-07-16. `favband.py` raises on a broken universe, settlement or orientation rather than
  returning an empty result.
- `docker compose up -d postgres` **only**. A bare `up` starts the live trading containers.
- Do not switch `wt/capture` off main. Running capture from a feature worktree is how it died.
