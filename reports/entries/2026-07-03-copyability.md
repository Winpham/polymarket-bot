# 2026-07-03 · WS-3 — copyability-at-our-price: can we fill the edge, or only see it?

**One line:** favorites are **~69% copyable at our price** — the bid/ask spread (2.6¢ at band5) plus
fee eats only ~1/3 of the paper edge, leaving **+7.3% modeled realizable**. So **copyability is NOT
the binding constraint for favorites** — the killers remain edge-REALITY (λ≈0.15, WS-A: the paper edge
is mostly favorite-longshot bias) and persistence (D7). The direct at-ask read is INDETERMINATE (favorite
n=5), so this is a modeled bound from the better-powered per-band spreads.

## What was built
`scripts/copyability.py` — decomposes the favorite edge along the full copy path
`sharp fill →(follower tax ~1.3¢)→ our at-fire mid →(spread)→ our achievable ask → resolution`, and
asks whether the edge survives to a price we can actually hit. `--selftest` PASS (zero-spread ⇒ ~full
copyability; wide spread ⇒ eroded; event-clustering).

## The reads

Decision-time ask spread by band (pooled, ≥0-clamped): **b1 1.2¢ · b2 0.7¢ · b3 1.9¢ · b4 0.7¢ ·
b5 2.6¢** — heavy favorites (band5) have the *widest* spread (thin book near 1.0), but still small.

| strategy | events | price | paper edge | @ask direct (n) | spread | modeled realizable | **copyable** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **favorite** | 115 | 0.82 | +10.6% | +0.4% (5) ⚠ | 2.6¢ | **+7.3%** | **69%** |
| elite_fresh_fav | 48 | 0.89 | +8.7% | −20.3% (3) ⚠ | 2.6¢ | +4.3% | 50% |
| strict | 271 | 0.50 | +3.6% | −5.9% (21) ⚠ | 1.9¢ | +1.2% | 32% |

## What it means
1. **Favorites survive to a fillable price.** ~69% of the paper edge (+10.6% → +7.3% net) remains
   after the spread + 2% fee. The market is liquid enough at high-price favorites that copyability is
   **not** what's stopping us. This directly answers half the "lazy copycat" critique: for favorites,
   we *can* copy at our price.
2. **The binding constraints are elsewhere.** (a) **Edge-reality** — WS-A shows λ≈0.15, i.e. the
   +10.6% is mostly favorite-longshot *bias*, not information; a copyable bias is only money if it
   *persists*. (b) **Persistence (D7)** — the standing wall. Copyability removes one worry, not these.
3. **Longshots/strict erode more** (32% copyable at price 0.50) — the relative spread is bigger and the
   paper edge smaller. Consistent with skip-longshots; and `strict`'s direct @ask read (−5.9%, n=21) is
   the DODGE-containing stream losing at the ask.
4. **The direct at-ask read is INDETERMINATE-BY-DATA** (favorite n=5, elite n=3) — the same accrual
   gap as CLV. `CAPTURE_ENTRY_ASK` is on; the number sharpens as decision-time asks accrue. The
   modeled bound is the honest stand-in until then.

## Strategic read (with WS-4)
The copycat critique isn't primarily a *slippage* problem for favorites — they're liquid and ~69%
copyable. It's a *what-are-we-copying* problem: tailing sharps into favorites rides a bias (λ low),
while WS-4 finds the stronger FDR-robust signal is the **opposite** — fading overhyped favorites. So
"don't be a lazy copycat" resolves to: **the fillability is fine; the direction and the edge-reality
are the question.** Both point away from naive copy-tailing.
