# CELL CERTIFICATION LOG — per-(sport×market-type) `favorite` conditioning

_7 candidate cells tested (n_events ≥ 10); Bonferroni family = 7._  
_Global favorite skill (pooling target) = +4.97%. K_POOL=40. Belief-blind bar p≤0.01, LB>+3%, OOS late-half>0, non-tournament, realizable>0, power floor._

## Certification criteria (ALL must hold)

1. within-cell selection-null `p_emp ≤ 0.01` **and** Bonferroni `p·C ≤ 0.05`  
2. event-clustered bootstrap **LB(pooled skill) > +3%**  
3. OOS **late-half skill > 0**  
4. **non-tournament** sport (tennis=Wimbledon / soccer=World Cup auto-reject)  
5. **realizable ROI(entry_ask) > 0**  
6. power **n_events ≥ floor**

| cell | nEv | skillRaw | skillPooled | LB(pool) | null p | p·C | OOS late | roiAsk(cov) | tourn | verdict |
|------|----:|---------:|------------:|---------:|-------:|----:|---------:|------------:|:-----:|---------|
| `sport=mlb` | 20 | +14.1% | +8.0% | +3.3% | 0.060 | 0.42 | +7.9% | -5.7%(26%) | n | ❌ reject |
| `sport=tennis` | 84 | +5.5% | +5.4% | +0.5% | 0.075 | 0.53 | +3.7% | +4.2%(40%) | Y | ❌ reject |
| `sport=tennis|mt=main` | 84 | +5.5% | +5.4% | +0.5% | 0.101 | 0.70 | +3.7% | +4.2%(40%) | Y | ❌ reject |
| `sport=soccer` | 35 | -1.6% | +1.9% | -2.5% | 0.702 | 4.91 | -5.3% | +1.8%(44%) | Y | ❌ reject |
| `sport=soccer|mt=deriv` | 30 | -2.1% | +1.9% | -2.2% | 0.722 | 5.05 | -6.5% | +1.6%(43%) | Y | ❌ reject |
| `sport=soccer|mt=main` | 26 | +8.5% | +6.4% | +2.5% | — | — | +9.7% | +2.6%(49%) | Y | ❌ reject |
| `sport=mlb|mt=main` | 16 | +9.1% | +6.2% | +1.4% | — | — | +1.4% | -9.8%(31%) | n | ❌ reject |

**Result: 0 of 7 cells certified.**

**No cell certified.** The per-sport structure in the map is soft-market softness and/or power-limited, not a belief-blind selection edge that clears the bar at realizable entry. This is a valid, honest outcome (the belief-blind gate is the judge, not the goal). Closest candidates and exactly why they fail are in REJECTED-CELLS.md.
