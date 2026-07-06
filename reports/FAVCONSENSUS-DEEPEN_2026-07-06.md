# FAVORITE-CONSENSUS: DEEPEN / RE-VERIFY / DIVERSIFY — final report (2026-07-06)

**Honest headline: the favorite-consensus edge re-verified STRONGER on 3× the data — pooled
surplus +8.4% over 101 super-events, selection-null p=0.0005 (the seed's binding p=0.034 failure
now clears), positive in both disjoint time blocks and 4 sport-categories — but NOTHING CERTIFIES:
the pooled Bonferroni lower bound (+2.0%) is still under the +3% tax margin, every single cell is
under the 30-event floor, and the durable (recurring-regime) supply is only ~2.6 events/day.
The binding constraint is unchanged and now precisely priced: ACCRUAL, led by MLB (~8 days to its
floor). The relational layer was tested at frozen parameters and KILLED. [H3/H5: see below.]**

Prereg (frozen before outcomes): `PREREG_20260706T000604Z_favconsensus_deepen.md`. Statistic:
`a = won − at-fire entry`, surplus over 5-band-matched `_blind`, super-event clustered
(`superkey.py`), UTC-day reads alongside. Paper-only; alerts untouched; branch
`research/favconsensus-deepen`.

## 0. Data inventory (deltas vs seed)

| Quantity | Seed | Now | Δ |
|---|---|---|---|
| Distinct graded days | ~2.4 | **7** | ×2.9 |
| favorite graded / super-events | 220 / 78 | **325 / 101** | +48% / +29% |
| favorite soccer share (super-events) | ~89% | **22%** | de-soccered |
| Wallet universe | handful | **560 followed / 284 active / 506 scored** | top-250+ live |
| Dense capture rows | 0 | **3,345 / 186 signals** | accruing since 07-03 |
| Historical mine | — | 2.6M fills / 517 fill-days | scorecard substrate |

favorite super-event mix now: tennis 55 (Wimbledon, EXPIRING), soccer 23 (mostly WC, EXPIRING),
mlb 14 (recurring), esports 5, nba/cbb 4 (incl. WNBA), politics 2, other 1.

## Verdicts per hypothesis (gate: as-of · ev-clustered · Bonferroni LB>3% after tax · ≥30 ev · ≥2 disjoint regimes · null p≤0.01)

### H1.1 Core favorite surplus — **INDETERMINATE-BY-POWER** (failing gate: LB vs margin)
+8.39% surplus, 101 super-events, ev-clustered Bonferroni(4) **LB +1.96%** (day-grain +1.42%),
selection-null **p=0.0005**, block-B-only null p=0.0095. Battery: mirror symmetric (−8.24%),
placebo flat (+0.19%), halves +6.68%/+10.49%, odd/even +5.93%/+11.34%. Regime-persistent in sign:
blocks A +8.45% / B +7.19%; mlb/esports/soccer/tennis all point-positive. The ONLY failing gate is
LB > 3%: closes at ~143 super-events at current surplus/SD (~3-4 days at tournament supply,
~2 months at recurring-only supply). Seed comparison: proven-router-era read was LB −9.8%,
p=0.034, "SOCCER-CARRIED" — all three defects resolved on the fuller record (soccer is now 20% of
the record and block B is majority non-soccer).

### H1.2 60–80¢ sweet spot — **CONFIRMED as ordering, uncertified as cell**
band4 +9.32% (66 ev, LB −0.20%) ≥ band5 +7.28% (55 ev, LB +2.75%). The premium ordering holds on
3× data; neither band cell individually clears the margin yet.

### H1.3 Longshot block — **seed claim WEAKENED to INDETERMINATE**
Consensus-on-longshots (<45¢) is no longer reliably losing: raw edge **+2.3%**, surplus-over-blind
+4.7% (LB **−2.7%**, 93 super-events), flat-shares after costs −$428. The rule "SKIP <45¢" STANDS
(negative LB, negative realizable $), but its stated basis changes from "structurally overpriced,
lost hard" to "unproven and cost-negative" — do not quote the −$5,821 seed number as current.

### H1.4 flat-SHARES vs flat-$ — **CONFIRMED (sign flip reproduces)**
On the longshot-bearing `strict` stream: flat-$ **−$4,575** vs flat-shares **+$2,654** (after 1¢
haircut + 2% fee buffer). On favorite-only both are positive (+$2,280 / +$1,751) — the flat-$
catastrophe is specifically a longshot-inclusion artifact; sizing rule 3 unchanged.

### H2 Regime cells — **0 CERTIFIED; 2 near-misses; abstention adds NOTHING**
Family = 6 counted cells (Bonferroni 6). No cell reaches the 30-event floor.
- `soccer|band4|B` **+17.0%, LB +5.7%, p=0.0065, 14 ev** — only the floor fails; BUT 16/45 block-B
  events are still World Cup: this cell largely dies with the tournament. Not a durable target.
- `tennis|band5|A` +12.9%, LB +10.3%, p=0.0005, 16 ev — Wimbledon = expiring; cannot certify by rule.
- `mlb` pooled: **+22.4%, LB +16.3%, 14 ev** — every MLB sub-cell point-positive (+11..+31%).
  The prime recurring target: ~16 more events ≈ **8 days** at the measured 2.0 ev/day.
- **Abstention (frozen rule): NO LIFT.** Full LB 2.80% vs abstained 2.74%; positive days 7/7 both
  ways. It dropped mostly-positive thin cells (esports). Reliability is SUPPLY, confirmed again.

### H4 Relational layer — **KILLED at frozen parameters (honest negative)**
m=20, β=1, K=5, primary top-50%; L_ij learned from `loose` (2.1–2.6k pairs, 95–98% pick coverage —
no longer data-starved). odd→even lift +0.53pp, even→odd **−0.10pp** → fails the both-halves rule.
Sensitivity (top-25/75%) shows the same inconsistency. Co-agreement adds no ordering signal beyond
rank-weighted consensus on this record; re-test only after a genuinely larger multi-tournament record.

### H3 Routing enrichments — [PENDING agent]

### H5 Copyability tax — **MEASURED (first real number); small, and NOT sharp-sport-graded**
(`scripts/copy_tax.py`, `reports/copy_tax.json`; measurement only.)
- **True ~60–80s executable tax ≈ +0.4¢ pooled** (strict stream: N=169 signals, 16.7% coverage,
  median lag 81s; band4 −0.33¢ / band5 +0.82¢). The favorite stream's own read is **+1.74¢ but at a
  median 895s lag** (N=7, all soccer/tennis) — that is capture DRIFT (favorites firming over ~15
  min), not spread: on the same subset the ask-haircut proxy ≈ 0¢. Bounds: real copy tax sits
  between +0.4¢ (60s) and +1.7¢ (15-min drift read).
- **Tax-adjusted LBs (using the conservative, drift-inflated 1.74¢):** pooled favorite +1.96% →
  **+0.23%** (gate 3 fails harder — the pooled cell needs both accrual AND the tax bound tightened);
  `soccer|band4|B` +5.69% → **+3.96%** and `tennis|band5|A` +10.26% → **+8.53%** — both SURVIVE the
  tax and still fail only the 30-event floor; mlb +16.27% → **+14.54%** (soccer-derived tax; no MLB
  trajectory yet).
- **Directional claim REFUTED on this data:** no band gradient (1.72¢≈1.75¢), and mlb/esports taxes
  are *smaller/negative* (−1.12¢/−2.20¢ on strict) vs soccer +0.43¢ — the "sharp-market copyability
  wall" does not show up in the dense-capture tax at this coverage. (Seed's MLB ~3¢ tax came from the
  historical-mine repricing, different instrument — reconcile as coverage accrues.)
- **Coverage is the limiter:** favorite trajectory coverage 2.2% (7 signals, 0 MLB). The capture
  cadence on favorite must tighten before its tax is trustworthy.

### Adversarial verify pass — [PENDING agent]

## What to accrue next (the specific closers)
1. **MLB**: 16 more favorite super-events ≈ 8 days. If the +22% surplus holds at n=30 it would clear
   LB>3% with room — the first plausible CERTIFIED non-soccer cell.
2. **Recurring pooled**: at 2.6 recurring ev/day (MLB 2.0 + WNBA 0.6), a 143-event recurring-only
   pooled record needs ~2 months — or new venues: esports (0.7/day now, softest non-summer venue)
   and NFL/NBA onboarding Sept/Oct.
3. **Dense capture**: keep `DENSE_CAPTURE` on — 186 signals covered in 2 days; λ̂ and the measured
   tax become trustworthy at ~2 weeks of coverage.
4. Wimbledon ends ~Jul 12: expect favorite supply to drop from ~14 to ~3-5 ev/day; do not read the
   volume cliff as edge decay.
