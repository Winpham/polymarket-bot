# VERDICT — Expand the universe + play to strengths (the honest version)

**Bottom line, unhedged:** We can get **far more than the top 250** — behavioral discovery surfaces
**~3,300 recurring non-MM co-traders** of our own markets (≈3× our tracked universe), the *right*
way (by what they bet with us, not by past-PnL trophies), with market-makers cleanly locked out.
But **"play to each trader's strengths" does not certify at current power**: of 1,029 (trader ×
strength-cell) candidates, the apparent winners are *fewer* than a label-permutation null
manufactures by chance — i.e. per-trader specialization is a winner's-curse artifact today. The
descriptive strength-map is fine to *read*; betting on it would regress the system. The only real
path to specialization is forward CLV-at-our-price per cell **plus** the expansion that gives it
power. Nothing deployed; MM-lock still held; candidate pool silent. Read-only, paper.

## 1. Expansion — SOLVED, supply is large (`discover.py`)
Scanned 100 recent resolved markets we trade (3 tape pages each, throttled, 0 fetch errors) via
the data-api `/trades` tape (exposes `proxyWallet`):

| metric | value |
|---|---|
| distinct wallets seen | **11,745** |
| new (untracked) wallets | 11,553 |
| … non-MM (churn-locked) | **9,751** |
| … non-MM **recurring** (co-trade ≥2 of our markets) | **3,326** |
| market-makers locked out (churn ≥ 0.70) | 1,802 |
| currently tracked (all leaderboard) | 1,023 |

The top co-trader overlaps **53 of 100** markets (1,059 fills, churn 0.0 — pure directional). This
is behavioral discovery: it escapes the leaderboard's past-PnL survivor bias, which is the source
of the winner's curse. **Supply is not the constraint** — quality certification is.

## 2. Specialization — NO edge beyond chance at current power (`specialize.py`)
Per (trader × cell) copyable-surplus, cells = sport / market-type / favorite-vs-longshot /
early-vs-late, MM-locked, event-clustered, at OUR price (tax+spread+fee):

| | value |
|---|---|
| eligible (trader × cell) strengths (≥15 events) | 1,029 |
| cells with positive copyable-surplus lower bound (look "skilled") | **57** (≈5.5%) |
| **label-permutation null (1000×): survivors by chance** | mean **64.3**, 95th pct **82** |
| p(observed ≥ null) | **0.79** |
| verdict | **NO SPECIALIZATION BEYOND CHANCE** |

57 apparent specialists out of 1,029 is exactly the ~5% false-positive rate you get from one-sided
95% bounds on noise — and the null produces *more* (63). Ranking traders by "their best sport/
market/band" would have handed us 57 phantom specialists to bet on. The permutation null is the
guardrail that stops that. **This is why slicing finer makes it worse, not better** — more cells =
more max-of-noise.

## 3. What this means for the mission
- **Do expand** — add the ~3,300 recurring non-MM co-traders to a silent candidate pool and start
  capturing their fills. It strengthens the aggregate consensus edge (our real edge) and, crucially,
  multiplies CLV-event supply — the binding constraint on certifying *any* skill or specialization.
- **Do not** assign strengths from past performance — it's phantom. Let **forward CLV-at-our-price
  per cell** accrue; certify only cells that beat the permutation null. Expansion is what makes that
  decidable in a reasonable horizon instead of never.
- **No regression:** aggregate edge untouched, MM-lock held, nothing deployed, candidate pool
  silent, real money gated.

## Next deliberate step (Tue's call, not auto-done)
Wire the recurring non-MM candidate pool into forward fill-capture (a silent poll extension, not
the live alert path), so CLV-at-our-price per (trader × cell) starts accruing across a ~4× larger,
behaviorally-discovered universe. That is the single move that turns "play to strengths" from a
noise map into a certifiable engine.
