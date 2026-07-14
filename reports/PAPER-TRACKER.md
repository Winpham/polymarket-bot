# PAPER-TRACKER — champion vs favorite_liq vs favorite_v2 (read-only)

_Generated: 2026-07-12T16:46:22.007189+00:00 (UTC). Paper-only. Read-only DB. No rows written; nothing armed, deployed, or merged._

## Champion anchor self-test: TIED OUT

- ledger-native ROI-on-turnover (favorite, N=267): **+1.30%**
- audit_pnl_books.py formula, SAME population: **+1.44%**

> Both computed over the IDENTICAL 'favorite' resolved-bet population from honest_paper_ledger. They use different haircut/entry conventions (ledger: entry_ask or mkt+1c, audit: mean+0.5c) so an exact match isn't expected -- both positive and within a few points of each other is the honest bar. A separate, much LARGER population figure from running audit_pnl_books.py standalone (reports/audit_pnl_books.json) is NOT expected to match either: it includes pre-Phase-3 history (before the ledger existed) that never got appended to honest_paper_ledger -- a real, understood, documented population gap, not a bug.

---

## Honesty guards baked into this surface

- **Accounting basis is always labeled** (cash-day = `resolved_at`, i.e. when the paper bet was appended to the ledger, vs detection-day = `first_detected_at`, i.e. when the signal first fired). They can disagree on which days are red -- see `day_table_basis_divergence.days_flip_sign_between_bases` per arm.
- **Zero-row arms show `awaiting-forward-data (deploy pending)`, N=0, no ROI computed.** favorite_liq / favorite_v2 have ZERO honest_paper_ledger rows: they are built on the unmerged feat/garbage-policy branch and have not been deployed, so no signals for them exist yet. This tracker deliberately does NOT backfill-evaluate them on favorite's pre-snapshot history -- doing so is the exact coverage artifact that already inflated an in-sample '+9.66%' for this family. Their honest scope is forward-from-first-row-only, once Tue deploys feat/garbage-policy.
- **Open positions are MTM-labeled and censoring-flagged.** Winners resolve roughly 2x faster than losers (see audit_pnl_books.py's B3 hold-time asymmetry, reproduced live in this report's cross-check) -- so a FRESH day's still-open book is winner-enriched almost by construction. Never read a fresh day's open-MTM as a floor on eventual resolved P&L; it is a snapshot mid-flight, not a settled record.
- **Every arm is judged against the same belief-blind gate the champion is** (`standard_guard.py` measure/challenger), not a vanity P&L.
- **Power floor: N < 30 resolved events reads `not yet readable`.**

---

## `favorite`

**Status: live**  ·  power flag: readable (N=267 >= 30 power floor)

| basis | N | turnover | net P&L | ROI-on-turnover | win% | days |
|---|---:|---:|---:|---:|---:|---:|
| cash (resolved_at) | 267 | $26700.00 | $347.36 | +1.30% | +84.3% | 12 |
| detection (first_detected_at) | 267 | $26700.00 | $347.36 | +1.30% | +84.3% | 14 |

basis-flip days (red in one basis, not the other): 2026-06-29, 2026-06-30, 2026-07-05, 2026-07-06, 2026-07-11, 2026-07-12

**Rolling window** (`last_7d` vs since-first-row):

| window | N | ROI-on-turnover | win% |
|---|---:|---:|---:|
| last_7d | 144 | -2.01% | +81.9% |
| since_first_row | 267 | +1.30% | +84.3% |

**Throughput:** 22.25 bets/day · turnover $2225.0/day · peak concurrent capital $3200.0 (32 positions) · turnover-multiple 0.695

**Realizable/CLV** (event-clustered, honest_pnl_by_strategy convention): 213 distinct events · hit-rate +83.3% · CLV-ROI +4.20% · honest-ROI +2.32% (sd +0.480)

**Open positions (MTM):** 2 open, 2 with a mark, total open MTM $-50.31, 2 losers, 2 fresh (<24h)

> Winners resolve roughly 2x faster than losers (see audit_pnl_books.py's B3 hold-time asymmetry, reproduced live in this report's cross-check) -- so a FRESH day's still-open book is winner-enriched almost by construction. Never read a fresh day's open-MTM as a floor on eventual resolved P&L; it is a snapshot mid-flight, not a settled record.

**By-regime split** (softness = blind-favorite edge, skill = surplus over blind):

| sport | events | win% | softness | skill | total |
|---|---:|---:|---:|---:|---:|
| tennis | 96 | 85% | +4.10% | +4.37% | +7.67% |
| soccer | 45 | 90% | +2.62% | -1.49% | +0.61% |
| mlb | 22 | 92% | +3.71% | +14.21% | +16.80% |
| nba/cbb | 8 | 62% | +4.00% | -16.95% | -10.04% |
| esports | 7 | 92% | +6.11% | +2.63% | +4.20% |
| other | 6 | 67% | -0.56% | -19.52% | -18.68% |

**Belief-blind reference (champion):** 256 ev · surplus +4.77% · LB +2.16% · 2 non-soccer regimes+ · SELECTION-REAL
Regression status: **HEALTHY** -- belief-blind LB +2.16% > +0.00%, p_emp 0.0010, 256 ev

---

## `favorite_liq`

**Status: awaiting-forward-data (deploy pending)**

> favorite_liq / favorite_v2 have ZERO honest_paper_ledger rows: they are built on the unmerged feat/garbage-policy branch and have not been deployed, so no signals for them exist yet. This tracker deliberately does NOT backfill-evaluate them on favorite's pre-snapshot history -- doing so is the exact coverage artifact that already inflated an in-sample '+9.66%' for this family. Their honest scope is forward-from-first-row-only, once Tue deploys feat/garbage-policy.

Belief-blind challenger check: **CHAMPION-STANDS** -- beats champion realizable edge: -0.0628316705170042 > 0.014510603501443646 = False; selection_null p<= 0.01: False (p=0.632); --calibrate PASS: True; promotion_verdict LB> 3%: False (LB=-9.61%); >=2 disjoint NON-soccer regimes: False (1)

## `favorite_v2`

**Status: awaiting-forward-data (deploy pending)**

> favorite_liq / favorite_v2 have ZERO honest_paper_ledger rows: they are built on the unmerged feat/garbage-policy branch and have not been deployed, so no signals for them exist yet. This tracker deliberately does NOT backfill-evaluate them on favorite's pre-snapshot history -- doing so is the exact coverage artifact that already inflated an in-sample '+9.66%' for this family. Their honest scope is forward-from-first-row-only, once Tue deploys feat/garbage-policy.

Belief-blind challenger check: **CHAMPION-STANDS** -- beats champion realizable edge: -0.10005815514138448 > 0.014510603501443646 = False; selection_null p<= 0.01: False (p=0.5465); --calibrate PASS: True; promotion_verdict LB> 3%: False (LB=-10.70%); >=2 disjoint NON-soccer regimes: False (1)

## `favorite_tail`

**Status: awaiting-forward-data (deploy pending)**

> 'favorite_tail' has ZERO honest_paper_ledger rows (0 resolved bets have ever been appended for it). No ROI is computed -- a fake/backfilled number would repeat the known coverage-artifact mistake. If this strategy is expected to be live, check should_ledger()/LEDGER_STRATEGIES and whether it has ever resolved a signal.

Belief-blind challenger check: **CHAMPION-STANDS** -- challenger not measurable (below readout floor / no rows)

## Capacity / rarity flag (favorite_v2 deployability)

> rarity of the favorite_liq/favorite_v2 gates, measured on the CHAMPION's own forward-snapshot-covered signal pool -- NOT a P&L estimate for the new arms

Clean snapshot window: 2026-07-03, 2026-07-04, 2026-07-05, 2026-07-06, 2026-07-07, 2026-07-08, 2026-07-09, 2026-07-10, 2026-07-11, 2026-07-12 (N=278 snapshotted signals)

- clears favorite_liq gate ($1k total): +84% (234/278)
- clears favorite_v2 gate (+top-5-backer): +42% (117/278)

**Verdict:** not a bench-sitter -- roughly 42% of the champion's forward-snapshotted signals would also clear favorite_v2's top-5-backer+$1k gate

---

_Next step for the new arms: Tue deploys/merges `feat/garbage-policy`. The moment favorite_liq/favorite_v2 start ledgering, this tracker lights them up automatically on the next refresh -- no code change needed._
