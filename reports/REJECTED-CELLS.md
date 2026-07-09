# REJECTED CELLS — why each candidate failed certification

_7 of 7 candidate cells rejected. Ranked by selection-null p (closest-to-real first)._

### `sport=mlb` — nEv=20, pooled skill +8.0%, null p=0.060
- raw skill +14.1% → pooled +8.0% (LB +3.3%); OOS early +20.3% / late +7.9%; realizable -5.7% (ask cov 26%, n=6)
  - ❌ selection-null p_emp=0.060 > 0.01 (no belief-blind skill)
  - ❌ fails Bonferroni across 7 cells (p·C=0.42 > 0.05)
  - ❌ realizable ROI(ask)=-5.7% ≤ 0 (spread eats the mid edge)
  - ❌ UNDERPOWERED n_ev=20 < floor 30

### `sport=tennis` — nEv=84, pooled skill +5.4%, null p=0.075
- raw skill +5.5% → pooled +5.4% (LB +0.5%); OOS early +6.7% / late +3.7%; realizable +4.2% (ask cov 40%, n=34)
  - ❌ selection-null p_emp=0.075 > 0.01 (no belief-blind skill)
  - ❌ fails Bonferroni across 7 cells (p·C=0.53 > 0.05)
  - ❌ pooled-skill LB=+0.5% ≤ +3% margin
  - ❌ TOURNAMENT-only (tennis=expiring); cannot clear non-tournament holdout

### `sport=tennis|mt=main` — nEv=84, pooled skill +5.4%, null p=0.101
- raw skill +5.5% → pooled +5.4% (LB +0.5%); OOS early +6.7% / late +3.7%; realizable +4.2% (ask cov 40%, n=34)
  - ❌ selection-null p_emp=0.101 > 0.01 (no belief-blind skill)
  - ❌ fails Bonferroni across 7 cells (p·C=0.70 > 0.05)
  - ❌ pooled-skill LB=+0.5% ≤ +3% margin
  - ❌ TOURNAMENT-only (tennis=expiring); cannot clear non-tournament holdout

### `sport=soccer` — nEv=35, pooled skill +1.9%, null p=0.702
- raw skill -1.6% → pooled +1.9% (LB -2.5%); OOS early +3.0% / late -5.3%; realizable +1.8% (ask cov 44%, n=138)
  - ❌ selection-null p_emp=0.702 > 0.01 (no belief-blind skill)
  - ❌ fails Bonferroni across 7 cells (p·C=4.91 > 0.05)
  - ❌ pooled-skill LB=-2.5% ≤ +3% margin
  - ❌ OOS late-half skill=-5.3% ≤ 0
  - ❌ TOURNAMENT-only (soccer=expiring); cannot clear non-tournament holdout

### `sport=soccer|mt=deriv` — nEv=30, pooled skill +1.9%, null p=0.722
- raw skill -2.1% → pooled +1.9% (LB -2.2%); OOS early +6.2% / late -6.5%; realizable +1.6% (ask cov 43%, n=114)
  - ❌ selection-null p_emp=0.722 > 0.01 (no belief-blind skill)
  - ❌ fails Bonferroni across 7 cells (p·C=5.05 > 0.05)
  - ❌ pooled-skill LB=-2.2% ≤ +3% margin
  - ❌ OOS late-half skill=-6.5% ≤ 0
  - ❌ TOURNAMENT-only (soccer=expiring); cannot clear non-tournament holdout

### `sport=soccer|mt=main` — nEv=26, pooled skill +6.4%, null p=n/a
- raw skill +8.5% → pooled +6.4% (LB +2.5%); OOS early +6.9% / late +9.7%; realizable +2.6% (ask cov 49%, n=24)
  - ❌ null unmeasurable (blind pool cannot match cell profile → power)
  - ❌ pooled-skill LB=+2.5% ≤ +3% margin
  - ❌ TOURNAMENT-only (soccer=expiring); cannot clear non-tournament holdout

### `sport=mlb|mt=main` — nEv=16, pooled skill +6.2%, null p=n/a
- raw skill +9.1% → pooled +6.2% (LB +1.4%); OOS early +16.9% / late +1.4%; realizable -9.8% (ask cov 31%, n=5)
  - ❌ null unmeasurable (blind pool cannot match cell profile → power)
  - ❌ pooled-skill LB=+1.4% ≤ +3% margin
  - ❌ realizable ROI(ask)=-9.8% ≤ 0 (spread eats the mid edge)
  - ❌ UNDERPOWERED n_ev=16 < floor 20

