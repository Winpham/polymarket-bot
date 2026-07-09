# Residual-Negative Scan — after the converged `favorite_v2` policy

Direct answer to Tue's *"it still leaves some negative signal in there."* After applying the
converged policy (liquidity ≥ $1000 AND require top-5 backer), does any **structural** negative
slice remain in the clean book? Reproduce: `policy_search.py --residual`.

## Method
Apply the converged cuts to the champion book → keep-set (n=132, in-sample, at-fire fields). Scan
**every axis** (regime, category, league, market-type, price sub-band, freshness, backer volume,
#backers, rank, ask-divergence, event-cluster size). Flag a slice as a **structural negative** only
if ALL of: ROI(taker) < 0 **AND** belief-blind surplus < 0 **AND** support n ≥ 20 (the pre-set floor;
below it a negative is power-limited noise, not a defensible cut — cutting it would be overfitting).

## Result — 0 structural negative slices at power

| slice | n | ROIt | surplus | $drag | status |
|---|---|---|---|---|---|
| price 0.95–1.00 (extreme favorite) | 14 | −3.80% | −0.90% | −$53 | **below support** (n<20); surplus ≈0 ⇒ FLB composition tax, not a selection failure |
| ask − consensus ≥ 3¢ (extreme pay-up) | 9 | −7.51% | −8.43% | −$68 | **below support** (n<20); already mostly removed by the liquidity floor |

**Negative slices at power (n ≥ 20): 0.**

## Verdict (honest)
The converged policy leaves **no structural negative slice at current power**. The only residuals are
two below-support pockets:
1. the **extreme-favorite band top (0.95–1.00)** — a favorite-longshot *composition* tax (surplus
   ≈ 0, not a selection failure); cutting the band top is a knife-edge tune with no mechanism, and
   n=14 is below the support floor. Left in deliberately.
2. **extreme pay-up (ask ≥ 3¢ over consensus)** — n=9, already largely handled by the liquidity floor
   (wide asks live in thin books); the remainder is irreducible at this power.

Neither is a defensible cut: both are below the minimum-support floor and one has no mechanism. Per
the calibration philosophy (a plateau is a fine place to stop; thrashing for more is not), the search
**converges here**. Any further cut would be curve-fitting the in-sample noise.

**Do NOT claim the garbage is "gone."** The claim is: the optimal exclusion/refinement policy was
**derived** (swept + OOS-validated + mechanism-backed + confound-checked, not guessed); the residual
book has **no structural negative slice at current power**; the arm is **shadow-registered and will
accrue** on the forward path; and the **forward belief-blind gate** (PREREG_20260709T154254Z) delivers
the real verdict in ~2–3 weeks. The one residual *uncertainty at power* is the champion's own binding
constraint — **non-soccer persistence** (only tennis is non-soccer-positive at support today) — which
no in-sample analysis can settle and only forward accrual will.
