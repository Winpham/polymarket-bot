# PRE-REGISTRATION — `favorite_bysport` forward gate (FROZEN 2026-07-09T20:41:27Z)

**Frozen BEFORE any forward-outcome analysis of `favorite_bysport`.** In-sample the arm accrues
**zero** resolved rows (it does not exist on deployed main until this branch merges), so nothing
here is fit on outcomes. The in-sample certification that motivated the arm (0/7 cells certified)
is in `CELL-CERT-LOG.md` / `REJECTED-CELLS.md`; this document freezes the FORWARD rule that will
rule the arm certified-or-killed. The forward gate is the final arbiter (§2).

## What the arm is

`favorite_bysport` = champion `favorite` band (0.65–0.98) + an additive cell **gate** firing ONLY
in the NON-TOURNAMENT candidate sports **{mlb, nba/cbb, nfl/cfb, nhl, esports}** — sports where
blind-favorite softness ≈ 0, so any forward edge must be **selection SKILL**, not soft-market
softness. It DISCARDS the soft-tournament cells (soccer=World Cup, tennis=Wimbledon) whose
in-sample edge is expiring softness that will not transfer. `alerting=false`, promotes nothing,
arms nothing; `cell_gate=None` default keeps every incumbent arm byte-identical.

## Realizable metric (the ONLY basis)

Per resolved `favorite_bysport` pick in `consensus_signals` (the shadow scoreboard; the arm
deliberately is **not** in `LEDGER_STRATEGIES`, same as favorite_liq/v2):
- entry = `entry_ask` (pay the ask) when present, else at-fire `COALESCE(initial_mean_price,
  mean_price)`; ask-coverage reported every readout (never silently imputed).
- fee = corrected `0.03·p·(1−p)` (sports), entry-only, maker 0.
- **realizable ROI(ask)** = event-clustered mean pnl / turnover, flat 100 shares.
- **belief-blind skill** = event-clustered surplus over the (sport×band) `_blind` favorite, AND
  the within-cell selection-null `p_emp` (consensus vs a random same-cell blind favorite).

## Non-inferiority vs the champion

Primary comparison: `favorite_bysport` realizable ROI(ask) vs champion `favorite` realizable
ROI(ask) **on the SAME forward window, restricted to the arm's fired cells** (apples-to-apples:
compare where both fire). NI margin **−3pp**: the arm must not be worse than `favorite` by more
than 3pp of realizable ROI on the shared cells, OR it is de-registered.

## Certification (a cell / the arm promotes ONLY if ALL hold, FORWARD)

1. **Belief-blind:** within-cell selection-null `p_emp ≤ 0.01` **and** Bonferroni `p·C ≤ 0.05`
   across the cells scored that window. A positive realizable ROI with no belief-blind surplus is a
   favorite-longshot composition artifact — REJECTED, not certified.
2. **Realizable:** ROI(ask) **> 0** on the cell's ask-covered subset (coverage ≥ 50% of picks).
3. **Power floor:** per cell **≥ 30 forward events** / **≥ 10 day-clusters**, spanning **≥ 2
   disjoint NON-soccer regimes** (e.g. MLB + NBA, or MLB + NFL — never one tournament).
4. **Non-tournament:** the cell is a regular-season sport (already enforced by the gate).
5. **Pooled decides:** certification reads the K_POOL=40 pooled skill, never a raw per-cell mean.

## MLB-durability clause (the headline test)

MLB is the strongest non-tournament candidate and the first on the clock. In-sample it is
**INDETERMINATE-BY-POWER**: raw skill +14.1% → **pooled +8.0%**, bootstrap LB +3.3%, OOS late-half
+7.9%, but selection-null **p=0.06** (fails ≤0.01), only 20 events, and realizable ROI **−5.7%** on
26% ask coverage. The forward clause:

> **MLB certifies iff, forward past N≥30 MLB events, its pooled belief-blind skill LB > 0 AND its
> realizable ROI(ask) > 0 AND selection-null p_emp ≤ 0.01 (Bonferroni-adjusted).** At ~2 MLB
> events/day the durability verdict is **~2–3 weeks** out, minimum. Until then MLB is *watched, not
> certified*; the shadow arm merely isolates its forward accrual.

## Kill condition (de-certify / de-register)

- The arm is inferior to champion `favorite` by **> 3pp** realizable ROI on shared cells over a
  ≥30-event window ⇒ de-register the arm.
- Any cell's forward **belief-blind LB ≤ 0** OR realizable ROI(ask) ≤ 0 over its power window ⇒
  that cell is de-certified (removed from any future certified set).
- MLB fails the durability clause over the first ≥30-event window ⇒ MLB is **refuted as a durable
  non-tournament edge** and struck from the candidate set (honest negative — a valid outcome).

## Forward-accrual verification (done at freeze)

- `should_ledger`/scoreboard: `favorite_bysport` is scored by `default_portfolio` and resolved by
  the housekeeping loop like every non-blind arm ⇒ it accrues in `consensus_signals` (resolved
  surplus + `entry_ask`) the moment it deploys. Verified against the live path: `elite_fresh_fav`
  (deployed) has 155 resolved rows; favorite_liq/v2 have 0 only because they are pre-deploy — the
  identical fate/vehicle as favorite_bysport.
- No `.env` edit, no arming change, no real-money eligibility change. Paper/shadow only.
