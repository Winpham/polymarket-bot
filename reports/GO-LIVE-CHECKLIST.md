# Weather go-live — pre-flight checklist (real money)

Aligned to the frozen `GO-LIVE-PREREG.md` (G1–G6) on `feat/evergreen-portfolio`. **This file adds
evidence + two cleared blockers; it LOOSENS NOTHING.** Anything not ticked is a reason not to trade.

## Integrity of the measurement substrate (CLEARED this run — both were open blockers)

| check | result | gate | status |
|---|---|---|---|
| **Historical price source validated** (`basis_validate.py`) | MAE **0.0080** vs clean captured mids (median 0.0000, n=67) | ≤3¢ | ✅ **PASS** |
| **Token-index mapping** (CLOB `tokens[]` position == our `outcome_index`) | **100.00%** agreement vs DB-resolved outcomes, n=**9,302** | 100% | ✅ **PASS** |
| Grader survivorship (does the grader delete losers?) | dropped picks win 94.1% vs kept 95.8% → **+0.3pp** lift | no material lift | ✅ **PASS** |
| Decay curve not a stale-tick artifact | 0/485 picks have zero new ticks in the 30-min window | — | ✅ **PASS** |

> The parallel session's rejection of CLOB `prices-history` (MAE 22¢) was measured against the
> **PRE-FIX, loser-tilted ask lane** (D4: ~173 min late). It was a corrupt yardstick, **not** a
> token-index bug — the mapping is exactly right. **The historical price source is usable.**
> ⇒ The MIRAGE test (G3) is now legitimately runnable. That is `weather_neutral.py`.

## The gates that are still RED

| gate | what it needs | status |
|---|---|---|
| **G1** clean decision-time `entry_ask`, ≥2 disjoint weeks | D4 fix deployed ✅ (`1e199a5`) but **clock started 2026-07-12** | 🔴 ~2 weeks of TIME |
| **G2** frozen gate passes **at our price** after slippage | needs `entry_vwap` (mig 043) — **flag not enabled, ZERO rows** | 🔴 blocked on merge+flag |
| **G3** the MIRAGE ruled out | `weather_neutral.py` — **running now**; price source finally validated | 🟡 in flight |
| **G4** re-run after `deep-universe` re-ingest | branch **unmerged, undeployed**; universe still rank≤200 | 🔴 |
| **G5** execution proven — **we have never placed ONE order** | our own market impact is UNMEASURED; capacity walks a SNAPSHOT book ⇒ **real capacity ≤ measured** | 🔴 requires small real money |
| **G6** legal/ToS settled **by a human** | US real-money automated trading on Polymarket | 🔴 **not an engineering question** |

## Risk limits (INHERITED FROM THE FROZEN PREREG — do not loosen)

- **$50/signal** (my slippage curve says $100 is the LB sweet spot; the frozen $50 is stricter — **keep $50**)
- **$1,000/day — and treat it as ONE CORRELATED BET.** A heat dome resolves ~20 cities together, so a
  day is not 20 diversified bets; it is one.
- **$300 daily loss cap** · **−$1,500 cumulative KILL-SWITCH** (human review to resume)
- **flat SHARES, not flat-$** · **⅛-Kelly**
- Expected economics: **~$85/day gross**, before our own unmeasured impact. **This is a small business.**

## The thing that will feel like failure but isn't

The observed record is **13/13 winning days, day-Sharpe 2.20 (~42 annualized)**. **A Sharpe of 42 does
not exist.** Either the entry price still flatters us, or this is favourite-longshot bias. **Expect the
live record to be far worse than the backtest.** Long losing streaks are EXPECTED and are
*indistinguishable from a dead edge* — that is precisely why the kill-switch is pre-committed **now**,
while nothing is at stake, and not renegotiated later while losing.

## Pre-commit (sign before the first order)

1. I accept ~$85/day gross expected, not the $475/day the turnover model suggests.
2. I accept that one bad correlated day wipes ~5–10 good days, and that we have **never observed one**.
3. I will not raise the stake, the daily cap, or the kill-switch after a losing streak.
4. G6 (legal) is settled by me, a human, in writing, before a single order.
