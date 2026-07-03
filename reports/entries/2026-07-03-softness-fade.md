# 2026-07-03 · WS-4 — two-sided softness / FADE probe (the underdog complement to D24)

> **Multi-chat note:** a parallel run shipped the richer favorite-SIDE softness×skill map (D24 —
> category×type×band, softness/skill/ROI separated, map-integrated). This instrument
> (`softness_fade.py`, renamed from a colliding `softness_map.py`) is the **two-sided complement**: it
> surfaces NO-side / underdog softness (overpriced favorites you FADE) that a favorite-only (entry≥0.60)
> map cannot see. Keep both — D24 *aims* the favorite edge; this finds where the favorite is *overpriced*.

**One line:** on the rich blind universe (10,106 rows / ~5,116 events), the softest FDR-surviving
pocket is **`soccer/directional/band5` — FADE the heavy favorite, net +8.2%, z −4.57, p=0.000** — the
*opposite* of copy-tailing. A cluster of suggestive same-direction "fade" cells backs it. The generic
favorite-longshot curve is confirmed, but only ONE cell's softness beats it after FDR — the realer
thesis has a real *lead*, not yet a *bankable edge* (same accrual/persistence wall).

## What was built
`scripts/softness_map.py` — measures market softness = the calibration gap (realized WR − price) over
the **blind universe** (every tracked-trader market, not just consensus picks), per
(sport × market-type × band). Two reads kept separate: **RAW gap** (the blind edge) and **EXCESS** =
gap − the band-level FLB baseline (softness *beyond* the generic favorite-longshot curve). Null =
within-band label permutation (preserves the band FLB, destroys cell structure), **two-sided** (the
bettable side is data-chosen), BH-FDR q=0.10 over 34 tested cells (≥30 events). Bettable = best side
(YES/NO) net of 1¢ haircut + 2% fee > 0. `--selftest` PASS (soft cell detected, calibrated not
flagged, NO-side logic, degenerate-null regime documented).

*Self-caught correctness fix (recorded):* the first cut tested only positive excess (YES-side
softness) and silently dropped every NO-side (overpriced-favorite) signal at p≈1.0 — it would have
missed the single strongest finding. Fixed to a two-sided test.

## The generic favorite-longshot curve (confirmed, 10k rows)
`band gap = realized WR − price`: **b1 −2.3% · b2 −1.2% · b3 +1.0% · b4 +2.2% · b5 +0.1%**.
Textbook FLB — longshots overpriced, mid-favorites underpriced, extreme favorites ~flat. This is the
*static bias* the copy-consensus edge mostly harvests (WS-A), now mapped directly.

## The finding: fade specific-sport heavy favorites

| cell | events | gap | excess | z | p | side | net | verdict |
|---|---:|---:|---:|---:|---:|:--:|---:|:--|
| **soccer / directional / band5** | 49 | −9.4% | −9.5% | **−4.57** | **0.000** | **NO** | **+8.2%** | **SOFT ✓ (FDR)** |
| soccer / total / band5 | 37 | −5.3% | −5.4% | −3.24 | 0.006 | NO | +4.1% | suggestive |
| mlb / spread / band4 | 39 | −8.4% | −10.7% | −2.35 | 0.020 | NO | +6.7% | suggestive |
| other / directional / band5 | 147 | −2.4% | −2.5% | −2.40 | 0.032 | NO | +1.3% | suggestive |
| cs2 / directional / band3 | 36 | −13.9% | −14.9% | −1.71 | 0.099 | NO | +11.9% | suggestive |
| soccer / directional / band4 | 86 | +10.5% | +8.2% | +1.88 | 0.060 | YES | +8.1% | suggestive (YES) |
| soccer / total / band3 | 63 | +8.9% | +8.0% | +1.92 | 0.048 | YES | +7.0% | suggestive (YES) |

- **The one FDR-robust soft cell is a FADE:** soccer heavy-favorites (price >0.8) are **overpriced by
  ~9.4pp** — betting the underdog nets **+8.2%** after cost over 49 events, and it survives BH-FDR
  across 34 cells. **This is the anti-copycat direction** — bet *against* the favorite the sharps
  pile into, not tail them.
- **The suggestive cluster points the same way:** 5 of the 7 leading cells are NO-side fades of
  overpriced favorites (soccer, mlb, cs2, "other"). The lone YES-side leads are soccer band-3/4
  (mid-favorites underpriced — that's the copy-consensus edge's home turf, consistent with WS-A).

## Honest caveats (this maps where to LOOK; it certifies nothing)
1. **World-Cup concentration.** band-5 soccer = WC heavy-favorites; the +8.2% fade may be
   **tournament-specific favorite over-hype**, not a durable structural edge. It needs to persist
   post-WC across non-expiring regimes — the same D18 wall as everything else.
2. **One cell survives FDR; the rest are leads, not edges.** 34 cells tested; the multiplicity is
   real. Treat the suggestive cluster as a pre-registered watch-list, re-run as data accrues.
3. **Excess is conservative** — a soft cell inflates its own band baseline, shrinking its measured
   excess. So the true softness is if anything *understated*.
4. **Not cost-of-fill tested.** Net uses a flat 1¢+2% model; the underdog side's real liquidity/fill
   at our price is untested (that's WS-3's question, and it's data-starved too).

## What it means for the realer thesis
The softness map turns "don't be a lazy copycat" from a slogan into a testable direction: **the
market's exploitable mispricing, where it's strongest, is FADING overhyped favorites in specific
sports — the opposite of tailing sharps into favorites.** That is a genuinely different (and
data-supported-as-a-lead) thesis than copy-consensus. It is NOT yet bankable (one FDR cell, WC-heavy,
unproven post-tournament) — but it is the first evidence pointing somewhere other than copy-tailing,
and it re-runs itself as the blind universe grows.
