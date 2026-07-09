# Persistence Ledger — the binding gate (favorite arm)

> P1 deliverable of the harden-favorite-edge run. Per-regime OOS surplus + a concrete
> months/regimes-to-power estimate for the `persistence_non_soccer` gate. Re-generated live on the
> current record (2026-06-29 → 2026-07-09) from the frozen instruments (`regime_edge.py`,
> `regime_net_edge.py`, `regime_persistence.py`, `persistence_tracker.py`, all `--selftest` green).
> SOCCER-ARTIFACT lesson is law: **soccer alone never counts.**

## 1. Per-regime ledger (favorite arm, sport × month = one regime)

Gross = event-clustered surplus over the matched (category × band) blind-favorite baseline (the
composition-trap-safe convention). `net_taker` = after band spread + follower tax + fee. CR-LB =
one-sided cluster-robust 95% lower bound. **Recurring = non-expiring** (MLB, NBA/CBB); tennis/soccer
= expiring (World Cup ends ~07-19-2026, Wimbledon ~07-12); esports/politics = sporadic.

| regime | type | ev | clusters | gross | CR-LB | net_taker | net LB>0? |
|---|---|---|---|---|---|---|---|
| nba/cbb\|2026-07 | **REC** | 4 | 4 | +36.35% | +30.26% | **+32.75%** | ✅ TAKER+ |
| mlb\|2026-06 | **REC** | 2 | 1 | +33.21% | n/a | +29.68% | — (N=1 cluster) |
| esports\|2026-06 | exp | 2 | 1 | +19.47% | n/a | +15.75% | — |
| esports\|2026-07 | exp | 3 | 3 | +17.93% | +8.41% | +13.63% | ✅ TAKER+ |
| mlb\|2026-07 | **REC** | 16 | 7 | +11.23% | **−4.86%** | +7.42% | ✗ (LB straddles 0) |
| politics\|2026-07 | exp | 2 | 1 | +8.85% | n/a | +4.48% | — |
| soccer\|2026-07 | exp | 15 | 7 | +6.55% | +0.88% | +2.35% | — (expiring) |
| tennis\|2026-06 | exp | 33 | 2 | +6.17% | −12.93% | +2.32% | — (expiring) |
| soccer\|2026-06 | exp | 11 | 2 | +5.68% | −3.03% | +1.40% | — (expiring) |
| tennis\|2026-07 | exp | 43 | 7 | +4.60% | −7.59% | +0.73% | — (expiring) |
| other\|2026-07 | exp | 6 | 2 | −42.10% | −97.96% | −45.91% | — |
| nba/cbb\|2026-06 | **REC** | 1 | 1 | −57.85% | n/a | −61.33% | — (N=1) |

**Concentration:** HHI 0.118 (~8.4 eff regimes); **expiring regimes carry 67% of edge mass**
(tennis 43%, other 27%, soccer 17%); capital exposure is 71% soccer (the "soccer-carried" prior lives
in *bet count*, not event-grain edge). Pooled favorite: **+5.46% gross / +1.54% net_taker** over 138
ev / 10 clusters.

## 2. The three floors and where we stand

| floor | bar | current | gap |
|---|---|---|---|
| OOS day-clusters (`persistence_tracker`) | ≥10 independent OUT clusters | **5** | need +5 |
| recurring regimes clearing 10-cluster floor (`regime_edge`) | ≥2 | **0/4** | best is mlb\|07 at 7 clusters |
| recurring regimes net-positive after tax, LB>0 (`regime_net_edge`) | ≥2 | **1** (nba/cbb\|07, N=4) | need +1 |
| temporal OOS edge (`persistence_tracker`) | LB(recurring OUT) > +3% margin | recurring OUT +13.12% but **CR-LB −21.98%** | power-limited |
| cross-regime transfer null (`regime_persistence`) | perm-null p_conc ≤ 0.05 | **inert** (min achievable 0.353) | needs ≥5–6 regimes to fire |

**Every lens converges: `SOCCER-ARTIFACT` / INDETERMINATE-BY-POWER.** The recurring (non-expiring)
edge is *directionally real and net-positive after tax* (mlb +7.4% net, nba/cbb +32.8% net), but
CR-LBs straddle 0, only 1 recurring regime has LB>0, and the permutation null is structurally
non-discriminating below ~5–6 regimes. Temporally, the pooled OOS surplus is **−0.87% (flat)** —
so accruing count-power could still resolve **REFUTED**, not PERSISTS.

## 3. Months-to-power — the concrete answer

**Accrual rate (favorite arm, over the 11-day record):** soccer 1.0 clusters/active-day (EXPIRING),
tennis 0.9 (EXPIRING), **mlb 0.89 (RECURRING)**, nba/cbb 0.56 (July = offseason/summer-league,
fading), esports 0.57 (sporadic).

**Only one genuinely non-expiring sport is firing at volume right now: MLB.** So:

- **MLB alone → its own 10-cluster floor in ~1 week** (7 → 10 clusters; MLB plays ~daily through late
  Sept). But that is **one sport**, and the transfer test explicitly wants ≥2 *independent* sports —
  same-sport months are correlated, not independent.
- **The binding wall is a SECOND non-soccer/non-tennis sport in-season at volume.** The 2026 calendar:
  - World Cup ends **~07-19-2026** → soccer volume collapses to sparse club markets.
  - Wimbledon ends **~07-12** → tennis goes sparse until US hard-court (Aug) / US Open (late Aug–Sept).
  - NBA offseason until **~10-21-2026**; CBB until **~early Nov**; NFL starts **~09-10-2026**.
  - ⇒ The earliest a second independent non-soccer recurring regime reaches the 10-cluster floor is
    **NFL, ~early October 2026 (≈3 months out)**; a robust **≥5-regime non-expiring panel**
    (MLB-tail + NFL + NBA + CBB across months) is **~Nov 2026 – Feb 2027 (4–6 months)**.
- **Even then, PERSISTS is conditional, not automatic.** Current OOS pooled surplus ≈ 0 (−0.87%);
  the recurring net edge rests on N=4 (nba/cbb) and an LB that straddles 0 (mlb). If the edge is
  genuinely ~World-Cup-carried, the accrued verdict resolves **REFUTED** — which is the correct,
  valuable outcome, not a failure.

### Bottom line (P1)
> The favorite edge's **recurring, non-expiring regimes are directionally positive and net-positive
> after the copy tax** — that is the single most hopeful fact in the system. But the gate is
> **power**, not point-estimate: 0/4 recurring regimes clear the 10-cluster floor, only 1 has LB>0,
> the transfer null is inert, and OOS the pooled edge is flat. **No run can manufacture this** — it
> needs a **second non-soccer sport in-season (NFL ~Oct, NBA/CBB ~Nov), ~3–4 months**, and then a
> further verdict that the edge actually holds. Until then: **not real-money-eligible, binding
> constraint = non-soccer persistence over months.** Unchanged, re-confirmed, quantified.
