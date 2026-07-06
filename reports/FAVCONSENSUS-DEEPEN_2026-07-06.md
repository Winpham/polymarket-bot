# FAVORITE-CONSENSUS: DEEPEN / RE-VERIFY / DIVERSIFY — final report (2026-07-06)

**Honest headline: the favorite-consensus edge re-verified STRONGER on 3× the data — pooled
surplus +8.4% over 101 super-events, selection-null p=0.0005 (the seed's binding p=0.034 failure
now clears), positive in both disjoint time blocks and 4 sport-categories — but NOTHING CERTIFIES:
the pooled Bonferroni lower bound (+2.0%, and it survives a within-category composition attack at
+1.8%) is still under the +3% tax margin, every cell is under the 30-event floor, the one
"near-certifying" cell (soccer|band4|B) was REFUTED by the verify pass as a composition artifact,
and the durable (recurring-regime) supply is only ~2.6 events/day.
The binding constraint is unchanged and now precisely priced: ACCRUAL, led by MLB (~8 days to its
floor). The relational layer was tested at frozen parameters and KILLED; all three routing
enrichments are power-starved at the follow-set level; the copy tax is finally measured and small
(~+0.4¢ at 60-80s). Certified: 0. No real money.**

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

### H2 Regime cells — **0 CERTIFIED; 1 REFUTED by verify, 1 halved; abstention adds NOTHING**
Family = 6 counted cells (Bonferroni 6). No cell reaches the 30-event floor. The verify pass (A6,
below) showed the per-cell reads MUST use a within-category blind baseline — the global band
baseline inflates any single-sport, derivative-heavy cell:
- `soccer|band4|B` — **REFUTED (composition artifact).** Headline +17.0%/LB+5.7%/p=0.0065 collapses
  against the soccer-derivatives blind baseline (+9.08% in that cell): surplus → +9.5%,
  **LB → −1.1%, cat-matched p=0.016** (fails the ≤0.01 gate). The elite_fresh_fav failure mode,
  caught before it entered the record. (Also mostly WC — expiring anyway.)
- `tennis|band5|A` — **WEAKENED, still real-but-expiring**: honest within-cat magnitude **+7.4%**
  (half the +12.9% headline), LB +5.0%, cat-matched p=0.001, 16 ev — Wimbledon; cannot certify by rule.
- `mlb` pooled: **+22.4%, LB +16.3%, 14 ev — survives the within-cat attack** (MLB blind baseline is
  NEGATIVE, so composition deflates, not inflates, this cell). But the record is 17-0 over 5 days —
  an extreme small sample. The prime recurring target: ~16 more events ≈ **8 days** at 2.0 ev/day.
- **Abstention (frozen rule): NO LIFT.** Full LB 2.80% vs abstained 2.74%; positive days 7/7 both
  ways. It dropped mostly-positive thin cells (esports). Reliability is SUPPLY, confirmed again.
- **Instrument lesson (structural):** `regime_cell_scoreboard.py` cells are honest only with
  within-category band baselines; adopt that before the next re-run.

### H4 Relational layer — **KILLED at frozen parameters (honest negative)**
m=20, β=1, K=5, primary top-50%; L_ij learned from `loose` (2.1–2.6k pairs, 95–98% pick coverage —
no longer data-starved). odd→even lift +0.53pp, even→odd **−0.10pp** → fails the both-halves rule.
Sensitivity (top-25/75%) shows the same inconsistency. Co-agreement adds no ordering signal beyond
rank-weighted consensus on this record; re-test only after a genuinely larger multi-tournament record.

### H3 Routing enrichments — **all three INDETERMINATE-BY-POWER; the constraint is follow-set size**
(`scripts/routing_enrich.py`, `reports/routing_enrich.json`; frozen scorecard ≥100 fills / ≥15 days /
≥+10% copy-return, UNION MM-exclusion, repriced entry +1.3¢+spread −2% fee, whole-super-event
median-time H1/H2 split, Bonferroni 3, seed 20260706. 838k in-band fills → 8,457 super-events.)
1. **Regime-conditional scorecard**: per-sport follow-set (6 wallet-sport pairs) H2 forward
   **−0.271** vs global (3 wallets) **+0.146**; D=−0.416, LB −0.96 / UB +0.13 on 9-11 super-events →
   indeterminate; if anything the per-sport split fragments an already tiny follow-set.
2. **Conviction ≥$1k**: +0.128 vs +0.146 all-fills; D=−0.018 ± 0.167 → pure noise; the mine's
   ">$10k fills were +8.7%" does not translate into a usable forward filter at follow-set scale.
3. **Survivorship correction** (measurement): bias is UPWARD +0.064 — but from 5 recovered fills of
   1 dropped wallet; directionally as feared, magnitudinally unmeasured. Keep recovered fills in all
   forward reads.
Root cause everywhere: the frozen bar admits ~3-4 wallets (= the deployed follow-set), whose forward
footprint is ~10 super-events per half. **Routing enrichments are supply-starved at the follow-set
level; no enrichment idea can be judged until the wallet universe × forward window grows.**
Data-quality find (flagged for ops): `trader_fills.resolved_at` is a recent backfill (~7 days) and
is UNUSABLE as an event clock — instruments must use per-super-event MAX(ts). Documented in the JSON.

### H5 Copyability tax — **MEASURED (first real number); small, and NOT sharp-sport-graded**
(`scripts/copy_tax.py`, `reports/copy_tax.json`; measurement only.)
- **True ~60–80s executable tax ≈ +0.4¢ pooled** (strict stream: N=169 signals, 16.7% coverage,
  median lag 81s; band4 −0.33¢ / band5 +0.82¢). The favorite stream's own read is **+1.74¢ but at a
  median 895s lag** (N=7, all soccer/tennis) — that is capture DRIFT (favorites firming over ~15
  min), not spread: on the same subset the ask-haircut proxy ≈ 0¢. Bounds: real copy tax sits
  between +0.4¢ (60s) and +1.7¢ (15-min drift read).
- **Tax-adjusted LBs (using the conservative, drift-inflated 1.74¢):** pooled favorite +1.96% →
  **+0.23%** (gate 3 fails harder — the pooled cell needs both accrual AND the tax bound tightened);
  `soccer|band4|B` +5.69% → +3.96% and `tennis|band5|A` +10.26% → +8.53% survive the tax
  arithmetically (but see verify pass: C3 is REFUTED on the within-category baseline regardless, and
  C4 halves); mlb +16.27% → **+14.54%** (soccer-derived tax; no MLB trajectory yet).
- **Directional claim REFUTED on this data:** no band gradient (1.72¢≈1.75¢), and mlb/esports taxes
  are *smaller/negative* (−1.12¢/−2.20¢ on strict) vs soccer +0.43¢ — the "sharp-market copyability
  wall" does not show up in the dense-capture tax at this coverage. (Seed's MLB ~3¢ tax came from the
  historical-mine repricing, different instrument — reconcile as coverage accrues.)
- **Coverage is the limiter:** favorite trajectory coverage 2.2% (7 signals, 0 MLB). The capture
  cadence on favorite must tighten before its tax is trustworthy.

### Adversarial verify pass — **run, and it changed the verdicts**
(`scripts/verify_favconsensus.py`, `reports/verify_favconsensus.json` — independent SQL, clustering,
banding, permutation null (fresh seed 987654321); no generation-code reuse.)
- A1 re-derivation: every headline number reproduces to <0.1pp (incl. exact n_ev).
- A2 grading: zero cross-strategy outcome conflicts; zero out-of-bounds entries; zero
  resolved-before-detected.
- A3 leave-one-out: no single event flips/halves C2 or C3; but C2 = 17-0 (14 ev/5 days), C3 = 36-6.
- A4 superkey honesty: no over-/under-merge on the mlb & soccer cells (derivatives collapse within
  match; distinct dates stay distinct).
- A5 fresh null: C1 p=0.0005 (identical), C3 p=0.005 (~claimed).
- **A6 within-category baseline — the kill shot**: pooled C1 survives (−2.6% only → +8.2%, LB +1.8%,
  still p=0.0005 → **CONFIRMED, thin**); `soccer|band4|B` **REFUTED** (LB −1.1%, p=0.016);
  `tennis|band5|A` halved to +7.4% (LB +5.0%, p=0.001 → WEAKENED); `mlb` **CONFIRMED artifact-free**
  (its blind baseline is negative) but power-limited.
Single-pass positives once again did not survive intact — the within-category null is now a standing
requirement for any cell-level claim.

## Verdict table (one line per hypothesis)

| Hypothesis | Verdict | Lower bound | Failing gate |
|---|---|---|---|
| H1.1 pooled favorite | **INDETERMINATE-BY-POWER** | LB +1.96% (within-cat +1.8%; after drift-tax +0.23%) | LB < +3% margin |
| H1.2 sweet-spot ordering | CONFIRMED (ordering only) | band5 LB +2.75% / band4 −0.20% | per-band LB < margin |
| H1.3 longshot block | seed claim WEAKENED → INDETERMINATE | LB −2.7% | (rule stands on LB<0) |
| H1.4 flat-shares vs flat-$ | CONFIRMED | sign flip reproduces (−$4,575 vs +$2,654) | — |
| H2 soccer\|band4\|B | **REFUTED** (composition) | within-cat LB −1.1%, p=0.016 | baseline honesty |
| H2 tennis\|band5\|A | INDETERMINATE + expiring | within-cat +7.4%, LB +5.0% | floor 16/30 + expiring rule |
| H2 mlb pooled | **INDETERMINATE-BY-POWER (prime target)** | LB +16.3% (within-cat-proof) | floor 14/30, 17-0 sample |
| H2 abstention | NO LIFT | ΔLB −0.06pp | — |
| H3.1 regime-conditional routing | INDETERMINATE-BY-POWER | LB −0.96 | N≈10 super-events |
| H3.2 conviction ≥$1k | INDETERMINATE-BY-POWER | LB −0.37 | N≈11, D≈0 |
| H3.3 survivorship bias | measured UPWARD (+0.064, N=5) | — | measurement only |
| H4 relational layer | **KILLED** | even→odd lift −0.10pp | both-halves rule |
| H5 copy tax | MEASURED: ~+0.4¢ @60-80s; +1.74¢ @15min drift | — | favorite coverage 2.2% |

**Certified: 0.** Nothing moves to real money. The gate held against three separate mirages this
run (composition cell, tennis magnitude, single-pass positives) — the process is doing its job.

## 5-dimension self-audit
- **Novelty**: first measured copy tax; first regime-typed supply rates; relational layer finally
  testable and tested; within-category baseline requirement discovered. No rebuilt wheels — every
  instrument extends superkey/selection_null/taxonomy conventions.
- **Rigor**: prereg frozen before outcomes; all thresholds frozen (one deviation: H1.3's longshot
  read used the `longshot` strategy arm as "consensus-on-longshots" — noted, faithful to intent);
  independent adversarial verify with fresh code/seed refuted one claim and halved another —
  generation and verification stayed separate.
- **Leak-safety**: whole-super-event splits everywhere; as-of entries; verify A2 found zero grading
  conflicts; H3 flagged and routed around the resolved_at backfill trap; no within-event splits.
- **Realizability**: every positive stated with tax-adjusted LB; fee kept as buffer; favorite tax
  read honestly labeled as drift-bounded; no paper headline promoted to "profit."
- **Reliability**: quantified as supply (2.6 recurring ev/day), not tuned into existence; abstention
  honestly reported as no-lift; MLB accrual distance stated in days, not vibes.

## P&L-realism audit addendum (2026-07-06, three independent adversarial auditors)
The per-day profit picture (349 picks, +$2,008 net, 91% wr, "7/8 days positive", $3.2k bankroll)
was itself audited (`scripts/audit_{pnl_books,entry_realism,risk_realism}.py` + JSONs). Verdicts:
- **Totals/bankroll VERIFIED** (independent re-derivation within 2%; zero voids, zero double-counts;
  the only exclusion = 16 open picks, mark-to-market −$6 — no hidden losers).
- **"No losing day" REFUTED** — detection-date accounting artifact. Cash-basis (settlement-date)
  rebuild flips Jul-05 to **−$281**; losses resolve ~3× slower than wins (mean 17.6h vs 6.4h), so
  recent days always read optimistically.
- **Entry realism: headline OVERSTATED.** Sign survives all four entry conventions, but at the
  honest follower entry (first observed price) the edge is **+4.8%/bet, +1.6%/day** (vs +7.6/+5.8
  claimed); worst-defensible +3.3%/bet ≈ breakeven/day; negative days 2→3. The 22% of picks with NO
  observable follower price are the best ones on paper (98.7% wr, +15.9%/bet) — the record leans on
  bets a follower likely couldn't place. Favorite fires silently (no alerts) — the record was never
  human-actionable in real time.
- **Risk realism:** at the measured edge, game-clustered bootstrap gives **P(negative day) ≈ 16%**
  (worst sim day −$800 at these units); ONE stacked game flipping makes the busiest day negative
  (K=1 → −$823; one WC exact-score game held 32% of bankroll); expected upsets ≈ 9/40 games — the
  benign week just landed them on small exposures. $3.2k bankroll breaches in 17% of −5pp-stress
  paths and peak capital doubles to ~$6.9k if resolutions lag +12h. Post-tournament (3-5 bets/day):
  expect **2-3 negative days/week** even with the edge intact (~+$17-24/day expected at 100sh).
- **Edge reality re-affirmed:** clustered no-edge null rejects at p=1.6e-5 (z 4.16); MLB is now
  18-0 (p=0.005 under null). The edge is real; the *presentation* was flattered by at-fire pricing,
  detection-date accounting, and a benign-sample tournament week.
**Honest deployable picture: ~+3-5%/bet, ~0-2%/day on turnover, several losing days per month,
bankroll buffer ~2× peak (≈$7k at 100sh units).**

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
5. **Follow-set growth** (H3's binding constraint): the +10% frozen bar admits 3-4 wallets; routing
   enrichments become judgeable only as more wallets accrue ≥100 fills/≥15 days — a function of the
   560-wallet capture universe aging, not of new ideas.
6. **Tighten favorite's capture cadence** so its tax read is a real 60s number (currently 895s
   median lag, 2.2% coverage) — ops change, paper-only, no alert path.
