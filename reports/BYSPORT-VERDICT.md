# BYSPORT VERDICT — is the consensus-favorite edge REAL where the market is efficient (MLB)?

**Run:** RUN-PER-SPORT-CONDITIONING · branch `feat/per-sport-conditioning` (off `feat/garbage-policy`) · 2026-07-09
**Instruments:** `cell_skill_map.py`, `cell_certify.py` (reuse `garbage_segments` / `sport_edge_tracker` /
`market_taxonomy` / `selection_null`), `favorite_bysport` Rust arm, `PREREG_20260709T204127Z_bysport.md`.

## The one-paragraph verdict

Under mandatory partial pooling (K_POOL=40), a within-cell belief-blind selection null, an OOS
time-split + non-tournament holdout, Bonferroni across all cells tested, **and realizable entry
(pay the `entry_ask`, corrected fee)**, **0 of 7 candidate cells certify.** MLB — the §0 lead — is
the strongest **non-tournament** candidate but is **INDETERMINATE-BY-POWER**, not a certified edge:
its raw +14.1% skill shrinks to **+8.0% pooled**, its selection-null **p=0.06 fails the ≤0.01 bar**
(and fails at every Bonferroni family size, C=7→0.45, down to C=1→0.06), it has only 20 events, and
its **realizable ROI is −5.7%** — the spread eats the mid edge. The residual scan then delivers the
decisive, non-obvious result: **the per-sport conditioning is REGRESSIVE at realizable entry.** The
full flat `favorite` book is belief-blind significant (**null p=0.002**) and realizable-**positive
(+1.2%)**; restricting to the "efficient-market" non-tournament cells that `favorite_bysport` fires
on *destroys* both (null p→0.05, realizable ROI→**−9.1%**), while the **discarded** soft-tournament
cells (soccer World Cup, tennis Wimbledon) are the ones carrying the realizable **+1.9%** — because
they are soft **and liquid**. Efficient-market skill looks real on paper (mid prices) but is
**un-harvestable through the wide spreads of thin books**; the soft-but-liquid markets are where the
realizable money is. So the honest answer to the run's question is: **no — the consensus edge is not
a certifiable realizable edge where the market is efficient; the champion's flat, sport-agnostic
rule beats every conditioned variant at the ask.** MLB is not refuted, only underpowered; it is put
**on the clock** via a pre-registered forward gate (~2–3 weeks of MLB events, minimum) as the first
possible non-tournament edge. This is the more-likely, fully valid outcome the run anticipated: a
trustworthy verdict, not a bigger in-sample number.

## What certified / what did not

| cell | nEv | pooled skill | LB | null p | OOS late | realizable ROI(ask) | verdict |
|------|----:|-------------:|---:|-------:|---------:|--------------------:|---------|
| `sport=mlb` | 20 | +8.0% | +3.3% | 0.060 | +7.9% | **−5.7%** (26% cov) | reject — null n.s., underpowered, realizable<0 |
| `sport=tennis` | 84 | +5.4% | +0.5% | 0.075 | +3.7% | +4.2% | reject — null n.s., LB<3%, **tournament** |
| `sport=soccer` | 35 | +1.9% | −2.5% | 0.702 | **−5.3%** | +1.8% | reject — **no skill** (soft-only, won't transfer) |
| `sport=soccer\|mt=main` | 26 | +6.4% | +2.5% | — | +9.7% | +2.6% | reject — null unmeasurable (power) + tournament |
| `sport=mlb\|mt=main` | 16 | +6.2% | +1.4% | — | +1.4% | −9.8% | reject — realizable<0, null unmeasurable |
| tennis\|main, soccer\|deriv | — | — | — | — | — | — | reject (see CELL-CERT-LOG.md) |

**0/7 certified.** Full detail: `CELL-CERT-LOG.md`, `REJECTED-CELLS.md`, `CELL-SKILL-MAP.json`.

## Residual scan (§1.6) — the regressive-conditioning finding

_As-of this run (`cell_certify.py --residual` → `RESIDUAL-SCAN.md`); figures drift ±0.5pp as the
live book accrues, but the ordering is stable._

| population | nEv | raw skill | LB | null p | realizable ROI(ask) |
|---|---:|---:|---:|---:|---:|
| **FULL `favorite` book** (flat, sport-agnostic) | 153 | +4.5% | +0.5% | **0.002** | **+1.2%** |
| **ARM subset** (non-tournament {mlb,nba/cbb,esports}) | 31 | +10.4% | +1.7% | 0.053 | **−9.1%** |
| **DISCARDED** (soccer+tennis tournament) | 120 | +2.8% | −1.2% | 0.088 | **+1.9%** |

Reading: the champion flat book is the belief-blind-significant, realizable-positive strategy.
Conditioning INTO efficient markets keeps the paper skill (+10.4% raw) but loses significance and
turns realizable ROI sharply negative (thin books, wide spreads). Conditioning OUT of the soft
tournaments discards the realizable-positive, liquid cells. **Per-sport conditioning subtracts
realizable value here.** The champion `favorite` remains the recommended live arm; no conditioned
arm should be promoted on this evidence.

## MLB — on the clock

MLB is the one cell worth forward observation: non-tournament, softness ≈ 0, high raw skill,
indeterminate-by-power (not refuted). The pre-registered clause (`PREREG_20260709T204127Z_bysport.md`):
MLB certifies iff, forward past **N≥30 MLB events**, its pooled belief-blind skill LB > 0 **AND**
realizable ROI(ask) > 0 **AND** selection-null p ≤ 0.01 (Bonferroni). At ~2 MLB events/day the
verdict is **~2–3 weeks out, minimum**. The in-sample evidence already **leans toward a kill**
(realizable −5.7%), but MLB is underpowered, so the forward gate rules — not this run. If MLB fails
the clause, it is struck as a durable non-tournament edge (an honest negative). The one path to a
real MLB edge: books deepen / spreads tighten as the season scales, making the paper skill
harvestable — the forward gate will detect that if it happens.

## The shadow arm (what shipped)

`favorite_bysport` (Rust): champion `favorite` band + additive `cell_gate` firing only in
{mlb, nba/cbb, nfl/cfb, nhl, esports}. `alerting=false`, promotes nothing, arms nothing.
`cell_gate=None` default ⇒ every incumbent arm (`favorite`, `favorite_liq`, `favorite_v2`,
`strict`, `_blind`, `elite_fresh_fav`) is **byte-identical**. Trader-quality is **NOT** raw rank
(REFUTED 5 ways; trader-tier power-shattered in DIM 3) — the sanctioned earned-trust cell path
(`slice_pooled_quality` / `CellPooled`, already wired, byte-identical when the trust map is empty)
is the only blessed quality feature, and the arm carries no rank gate. Accrues in `consensus_signals`
(resolved surplus + `entry_ask`) the moment it deploys — same shadow vehicle as favorite_liq/v2; no
`.env` edit, no real-money change. 4 unit tests + `cargo build`/`clippy`/132 tests green; Python
instruments self-test green.

## Honest status

**Incomplete-but-resumable → in-sample COMPLETE, forward-PENDING.** The certifiable per-sport
conditioning was DERIVED (pooled + OOS + non-tournament + belief-blind + realizable, not
sliced-to-taste) and the answer in-sample is: **none certifies, and conditioning is regressive at
realizable entry.** The arm is shadow-registered and will accrue forward; MLB is on the clock with a
frozen gate; the forward verdict is ~weeks out. No per-sport edge is claimed real.
