# PRE-REGISTRATION — Soft-market (esports) consensus edge, forward gate

**Frozen:** 2026-07-10T05:04:30Z (UTC). **Branch:** `feat/soft-market-edge`. **Paper-only,
read-only, promotes nothing, arms nothing, real-money eligibility UNCHANGED.** Belief-blind: every
rule / threshold / verdict below is frozen HERE, BEFORE any forward data accrues. Inherits the audited
conventions of the merged consensus work: small-cluster **t(G−1)** cluster-robust LBs at the
match super-key (`superkey.super_event`, `effective_n.cluster_robust`), at-fire entry, the
`selection_null` belief-blind gate, and the `sport_edge_tracker` softness/skill split.

## 0. The thesis and what the in-sample run already settled

The Soft-Market Edge Hunt asked whether steering to the SOFTEST market we track (esports) yields a
**fatter, more-CONSISTENT, more-profitable-PER-DOLLAR** edge than the crowded soccer favorites.

Phase 1 (`ESPORTS-CONVERSION-GAP.json`) diagnosed why we barely act there: the dominant cause is the
**rank-40 `consensus_eligible` gate**, not fragmentation/liquidity/band. Esports converges 3-deep
within 48h at ~soccer rate, but the esports sharps sit at median global rank ~170, so their stored
votes are filtered out of backer counts (on the live store the gate drops esports 3-backer
convergence 102 → 1). Phase 2 built the shadow arm `soft_fav` / `soft_fav_liq` (wider-eligibility
esports book; default-off; champion byte-identical). Phase 3 (`SOFT-MARKET-EDGE.json`) measured the
replayed edge and found: the conversion gap IS closed (118 replayed resolved in-band picks vs the
champion's 10), but **the realizable edge is NOT durable** — the fat realizable LB (+0.116 over 40
match-clusters) is a short-window, single-discipline (dota2) favorite-chalk artifact: the
leave-one-discipline-out jackknife drops dota2 and the LB collapses to **−0.102**. Realizable-entry
coverage is only 49% (12 `entry_ask` + 46 72h-tape asks) because the arm never ran live. **The
in-sample answer is INDETERMINATE. This prereg makes the forward record the arbiter.**

## 1. What accrues forward (enablement)

On merge, the integrator sets `CONSENSUS_SOFT_MARKET_ARM=true` (and keeps `SOFT_MARKET_RANK_CUTOFF=250`)
in `.env.consensus`. From that instant the cycle scores `soft_fav` / `soft_fav_liq` on the
esports-only wider-eligibility book and upserts their signals like any other arm — capturing
`entry_ask` / `entry_ask_mid` at the first housekeeping pass (the REALIZABLE, leak-free entry the
in-sample replay lacked). No other behavior changes; every incumbent arm stays byte-identical.
Nothing here arms real money or auto-promotes.

## 2. The locked objective (identical to the run objective; no re-derivation permitted)

For a cell (esports overall, and per discipline lol / cs2 / dota2 / val):

> **θ = cluster-robust one-sided 95% LOWER BOUND of realizable ROI-on-turnover**, clustered at the
> match super-key, read at small-cluster **t(G−1)**. Realizable entry = **`entry_ask`** (the captured
> executable ask); fee = `0.03·p·(1−p)`; ROI-turn = Σpnl / Σstake, stake = entry. Win rate is a
> DIAGNOSTIC only (the win-rate trap: a 0.97 favorite winning 96% is negative per dollar).

Forward measurement uses **only `entry_ask`** captured on live `soft_fav` signals — NOT the 72h clob
tape, NOT mid, NOT the sharps' fill. A pick with no captured `entry_ask` is excluded from θ.

## 3. Floors — a cell reads INDETERMINATE until ALL are met (frozen)

1. **Volume floor:** ≥ **20** distinct match-clusters with a captured `entry_ask` AND resolution.
2. **Deployment floor:** ≥ **3** signals per active esports-day (else the cell is not deployable).
3. **Duration floor:** the clusters span ≥ **7** distinct active days AND ≥ **2 disjoint
   non-expiring regimes** — operationalized as ≥2 esports disciplines each clearing an **8-cluster**
   sub-floor. (One tournament weekend is not a regime.)
4. **Disjoint-regime robustness (the decisive in-sample failure):** the θ LB must stay **> 0** under
   the **leave-one-discipline-out jackknife** — drop the discipline with the most clusters and
   recompute. An edge that only survives WITH its dominant discipline is that discipline's streak.

## 4. Belief-blind + skill (frozen, both required)

- **`selection_null`** on the soft-arm selection: p_emp ≤ **0.01** with ≥ **1000** draws, matched to
  the arm's (band × UTC-day) pick profile — the surplus must not be a composition artifact.
- **Skill over softness (`sport_edge_tracker`):** the soft cell's surplus over the esports
  **blind-favorite** baseline at the same band must be **> 0**. A soft cell that adds no skill over
  the blind favorite is just riding softness (like soccer) and will not transfer.
- **Multiple testing:** Bonferroni/BH over the number of cells tested (≤5: esports-all + 4
  disciplines) — reported explicitly.

## 5. Head-to-head (the run's actual question)

The soft cell WINS only if its realizable θ LB (clearing §3 + §4) **exceeds the champion `favorite`
θ LB by a non-inferiority margin of +2.0 percentage points**, measured on the SAME realizable
`entry_ask` metric over the SAME forward window. (In-sample, champion favorite realizable LB = −0.065;
the soft cell must beat it durably, not just point-wise.) `soft_fav_liq` is scored identically so the
thin-book spread tax is ruled on independently of the raw arm.

## 6. Decision (frozen) — what each outcome means

- **PASS** (soft cell clears §3+§4+§5, ≥2 disjoint non-expiring regimes): the softer market yields a
  fatter, more-consistent per-dollar edge than the crowded favorites. Earns a deliberate human
  promotion review — NOT an automatic arm.
- **FAIL / INDETERMINATE** (any floor unmet, LODO collapses it, no skill over blind, or does not beat
  champion by the margin): esports softness is eaten by its wider spreads / too thin to realize —
  a fully valid result that tells Tue the better edge is NOT there and saves real money.
- The forward record supersedes the in-sample replay either way. No goal-seeking; a green is only
  green if §3–§5 are ALL satisfied on data collected AFTER this timestamp.

## 7. Kill condition (frozen)

Retire `soft_fav` / `soft_fav_liq` if, after **≥ 6 forward weeks** with the volume floor met, the
realizable θ LB is **≤ 0** OR fails the LODO jackknife OR does not beat champion `favorite` by the
+2.0pp margin. A dead soft arm is a valid, money-saving outcome — do not keep it on hope.

## 8. Guardrails (unchanged from the run brief)

Paper-only; arms nothing; real-money eligibility unchanged; `soft_fav`/`soft_fav_liq` alerting=false;
no `.env` ARMING edits (only the `CONSENSUS_SOFT_MARKET_ARM` capture flag on merge); cost-zero; DB
read-only except the bot's normal accrual writes; `clob_price_tape`/`trader_fills` SELECT-only.
