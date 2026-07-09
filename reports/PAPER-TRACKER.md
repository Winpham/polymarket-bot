# PAPER-TRACKER — champion vs favorite_liq vs favorite_v2 (read-only)

_Generated: 2026-07-09T19:50:16.896125+00:00 (UTC). Paper-only. Read-only DB. No rows written; nothing armed, deployed, or merged._

## Champion anchor self-test: TIED OUT

- ledger-native ROI-on-turnover (favorite, N=219): **+2.21%**
- audit_pnl_books.py formula, SAME population: **+1.62%**

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

**Status: live**  ·  power flag: readable (N=219 >= 30 power floor)

| basis | N | turnover | net P&L | ROI-on-turnover | win% | days |
|---|---:|---:|---:|---:|---:|---:|
| cash (resolved_at) | 219 | $21900.00 | $484.97 | +2.21% | +84.9% | 9 |
| detection (first_detected_at) | 219 | $21900.00 | $484.97 | +2.21% | +84.9% | 11 |

basis-flip days (red in one basis, not the other): 2026-06-29, 2026-06-30, 2026-07-05, 2026-07-06, 2026-07-07

**Rolling window** (`last_7d` vs since-first-row):

| window | N | ROI-on-turnover | win% |
|---|---:|---:|---:|
| last_7d | 183 | -0.52% | +82.5% |
| since_first_row | 219 | +2.21% | +84.9% |

**Throughput:** 24.33 bets/day · turnover $2433.33/day · peak concurrent capital $3200.0 (32 positions) · turnover-multiple 0.76

**Realizable/CLV** (event-clustered, honest_pnl_by_strategy convention): 180 distinct events · hit-rate +84.6% · CLV-ROI +6.39% · honest-ROI +4.55% (sd +0.472)

**Open positions (MTM):** 16 open, 15 with a mark, total open MTM $-80.96, 10 losers, 11 fresh (<24h)

> Winners resolve roughly 2x faster than losers (see audit_pnl_books.py's B3 hold-time asymmetry, reproduced live in this report's cross-check) -- so a FRESH day's still-open book is winner-enriched almost by construction. Never read a fresh day's open-MTM as a floor on eventual resolved P&L; it is a snapshot mid-flight, not a settled record.

**By-regime split** (softness = blind-favorite edge, skill = surplus over blind):

| sport | events | win% | softness | skill | total |
|---|---:|---:|---:|---:|---:|
| tennis | 83 | 86% | +3.35% | +5.47% | +8.09% |
| soccer | 24 | 91% | +6.41% | +5.59% | +7.10% |
| mlb | 20 | 91% | +2.84% | +14.01% | +15.71% |
| other | 16 | 83% | +0.70% | -7.06% | -5.77% |
| nba/cbb | 6 | 67% | +4.36% | -8.04% | -3.82% |

**Belief-blind reference (champion):** 211 ev · surplus +6.48% · LB +3.66% · 2 non-soccer regimes+ · SELECTION-REAL
Regression status: **HEALTHY** -- belief-blind LB +3.66% > +0.00%, p_emp 0.0000, 211 ev

---

## `favorite_liq`

**Status: awaiting-forward-data (deploy pending)**

> favorite_liq / favorite_v2 have ZERO honest_paper_ledger rows: they are built on the unmerged feat/garbage-policy branch and have not been deployed, so no signals for them exist yet. This tracker deliberately does NOT backfill-evaluate them on favorite's pre-snapshot history -- doing so is the exact coverage artifact that already inflated an in-sample '+9.66%' for this family. Their honest scope is forward-from-first-row-only, once Tue deploys feat/garbage-policy.

Belief-blind challenger check: **CHAMPION-STANDS** -- challenger not measurable (below readout floor / no rows)

## `favorite_v2`

**Status: awaiting-forward-data (deploy pending)**

> favorite_liq / favorite_v2 have ZERO honest_paper_ledger rows: they are built on the unmerged feat/garbage-policy branch and have not been deployed, so no signals for them exist yet. This tracker deliberately does NOT backfill-evaluate them on favorite's pre-snapshot history -- doing so is the exact coverage artifact that already inflated an in-sample '+9.66%' for this family. Their honest scope is forward-from-first-row-only, once Tue deploys feat/garbage-policy.

Belief-blind challenger check: **CHAMPION-STANDS** -- challenger not measurable (below readout floor / no rows)

## `favorite_tail`

**Status: awaiting-forward-data (deploy pending)**

> 'favorite_tail' has ZERO honest_paper_ledger rows (0 resolved bets have ever been appended for it). No ROI is computed -- a fake/backfilled number would repeat the known coverage-artifact mistake. If this strategy is expected to be live, check should_ledger()/LEDGER_STRATEGIES and whether it has ever resolved a signal.

Belief-blind challenger check: **CHAMPION-STANDS** -- challenger not measurable (below readout floor / no rows)

## Capacity / rarity flag (favorite_v2 deployability)

> rarity of the favorite_liq/favorite_v2 gates, measured on the CHAMPION's own forward-snapshot-covered signal pool -- NOT a P&L estimate for the new arms

Clean snapshot window: 2026-07-03, 2026-07-04, 2026-07-05, 2026-07-06, 2026-07-07, 2026-07-08, 2026-07-09 (N=227 snapshotted signals)

- clears favorite_liq gate ($1k total): +85% (193/227)
- clears favorite_v2 gate (+top-5-backer): +40% (91/227)

**Verdict:** not a bench-sitter -- roughly 40% of the champion's forward-snapshotted signals would also clear favorite_v2's top-5-backer+$1k gate

---

_Next step for the new arms: Tue deploys/merges `feat/garbage-policy`. The moment favorite_liq/favorite_v2 start ledgering, this tracker lights them up automatically on the next refresh -- no code change needed._
