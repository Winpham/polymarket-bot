# PRE-REGISTRATION — Generalize-the-Band-Strategy cell scan, forward gate

**Frozen:** 2026-07-11T18:53:04Z (UTC). **Branch:** `feat/cell-scan`. **Paper-only, read-only,
promotes nothing, arms nothing, real-money eligibility UNCHANGED, `consensus.rs` + every incumbent
arm + `.env` BYTE-IDENTICAL (verified: zero Rust/env diff vs `main`).** Belief-blind: every rule,
threshold, and verdict below is frozen HERE, before any forward data accrues. Inherits the audited
conventions of the merged consensus work: match super-key clustering (`superkey.super_event`),
small-cluster t(G−1) cluster-robust LBs (`effective_n.cluster_robust`), the `selection_null`
belief-blind gate, the `_blind` softness/skill split, and the corrected fee `0.03·p·(1−p)`.

## 0. What the in-sample scan settled (do not re-derive)

The run asked: does ANY other cell (category × sport × price-band × trader-cohort) beat or usefully
complement the champion `favorite` 0.71–0.98 on realizable, copyable, anti-overfit-survived,
per-dollar ROI? Instruments: `scripts/cell_lib.py`, `cell_map.py`, `cell_scan.py`, `cell_verdict.py`
(all `--selftest` green). Reports: `CELL-MAP.json`, `CELL-EDGE-MAP.json`, `CELL-VERDICT.json`,
`CELL-SCAN-FINDINGS.md`.

**The answer is: NO other cell generalizes. The champion 0.71–0.98 is the singular validated edge.**

Load-bearing in-sample results (at-fire full-population basis; `entry_ask ≈ at-fire mid` confirmed
per cell — capture-haircut ≈ 0, so the at-fire population is the unbiased realizable measure and the
copyable-`entry_ask`-only sample is a capture-biased loser-tilted bracket, all negative):

- **Champion `favorite` 0.71–0.98 SURVIVES the full anti-overfit battery** — objective LB **+0.056**,
  skill-over-blind **+0.050**, LODO (drop dominant regime) **+0.041**, late-half **+0.044**,
  Bonferroni@α=0.05/14 **+0.035**, selection_null **p=0.0005**, G=130 match-clusters, 13 days, ≥2
  disjoint regimes. Its documented "late-half fade" was largely a **capture-bias artifact** (it fades
  on the 58-cluster ask sample, holds on the 130-cluster at-fire population).
- **Tennis 0.71–0.98 FAILS** — fatter in-sample (+0.075, skill +0.092) but the edge is carried by ONE
  Wimbledon week: LODO collapses it to **−0.048**. Its three "regimes" are all Wimbledon 2026. The
  soft-week/single-tournament trap the run rejects. Also misses the +2.0pp head-to-head margin.
- **Soccer 0.71–0.98 FAILS** — selection_null **p=0.44**: the consensus adds NO skill over random
  soccer favorites; its positive LB is pure structural favorite-longshot underpricing. Fails Bonferroni.
- **0.71–0.82 band survives the battery but is a REFINEMENT of the champion**, not a new/disjoint cell:
  it is the champion pool's own softest sub-band (handoff: 0.71–0.82 = +13% vs pooled +11%), reachable
  only by a finer band cut the handoff already refused; its +3.0pp in-sample beat is within
  selection-reward from choosing the best sub-band on the same data. **No new arm is warranted or
  built** — it is a post-hoc band filter on the EXISTING `favorite` signals, so the forward gate
  measures it directly; a "0.71–0.82 arm" would emit a strict subset of what the champion already
  captures (pure redundancy).
- **No other CATEGORY is powered** (baseball/basketball/esports/nonsport ≤ 12 match-clusters →
  INDETERMINATE; crypto/politics/econ never fire). **No wider trader COHORT is copyable**: replay
  cohorts 41–100 / 101–250 / wide 1–250 show FATTER *directional* edge (+0.076 / +0.104 / +0.107, up
  to 680 clusters) but only at the sharps' own non-copyable fill; the 72h `clob_price_tape` gives 4–25%
  realizable coverage over 3 days, so none is certifiable and all read INDETERMINATE-by-duration.

**Durability is pooled across TWO summer tournaments** (World Cup + Wimbledon): the champion and its
sub-band survive LODO only because they pool soccer + tennis; each sport alone fails. Transfer to
fall / regular-season / efficient markets is UNTESTED — the standing open question.

## 1. What accrues forward (no enablement, no code change)

Nothing is enabled. The live `favorite` arm keeps capturing `entry_ask` / `entry_ask_mid` on its
0.71–0.98 signals as it already does. The forward gate is measured entirely from the champion arm's
own forward signals; there is no new arm, flag, or `.env` edit. The **highest-value forward
improvement is the capture-at-detection fix** (STRATEGY-HANDOFF §4) — until it lands, the copyable
`entry_ask` remains the loser-tilted bracket and the at-fire mid remains the unbiased proxy.

## 2. The locked objective (identical to the run objective; no re-derivation permitted)

For each cell below:
> **θ = cluster-robust one-sided 95% LOWER BOUND of realizable ROI-on-turnover**, clustered at the
> match super-key, read at small-cluster t(G−1). Realizable entry = at-fire mid COALESCE(initial_mean_
> price, mean_price) as the unbiased-sample proxy (valid while capture-haircut ≈ 0; re-confirm per
> window), with copyable `entry_ask` reported as the conservative bracket. Fee = `0.03·p·(1−p)`.
> Win rate and total P&L are DIAGNOSTIC ONLY.

## 3. Floors — a cell reads INDETERMINATE until ALL are met (frozen)

1. **Volume:** ≥ **20** match-clusters (super-key), resolved.
2. **Deployment:** ≥ **3** signals per active day.
3. **Duration:** ≥ **7** distinct active days AND ≥ **2 disjoint non-expiring regimes** (each ≥ 8
   match-clusters). **For the transfer question, ≥2 regimes that are NOT both summer tournaments.**
4. **Disjoint-regime robustness (decisive):** the θ LB must stay **> 0** under the leave-one-
   regime-out jackknife (drop the regime with the most clusters). This is the test tennis failed.

## 4. Belief-blind + multiple testing (frozen, all required)

- **`selection_null`** ≤ **0.01** with ≥ **1000** matched draws (the test soccer failed at p=0.44).
- **Skill over blind** (`_blind` favorite at the same category×band) must be **> 0**.
- **Bonferroni/BH** over the cells forward-tested (in-sample family M=14) — reported explicitly; the
  θ LB must stay > 0 at α' = 0.05/M.

## 5. The forward questions (frozen) — what forward data must answer

- **Q1 — Champion durability:** does `favorite` 0.71–0.98 hold θ LB > 0 (Bonferroni, LODO,
  late-half) over ≥ 6 forward weeks? This is the primary arbiter.
- **Q2 — The transfer question (the real open one):** does the champion hold θ LB > 0 across ≥ 2
  disjoint regimes that are NOT both summer tournaments — i.e. through the transition OUT of
  World Cup + Wimbledon into fall / regular-season / more-efficient markets? If it collapses when the
  summer tournaments end, the edge was summer-softness, not a durable strategy.
- **Q3 — The 0.71–0.82 refinement:** does restricting the champion to 0.71–0.82 beat the pooled
  0.71–0.98 champion by ≥ **+2.0pp** on θ LB over ≥ 6 forward weeks (measured from the champion arm's
  own signals; a-priori mechanism = mid-favorites have more casual-money underpricing room than deep
  chalk which earns ~0/$)? If yes AND it clears §3–§4 forward, it earns a deliberate human review to
  narrow the band — NOT an automatic arm. If it does not beat by the margin forward, the pooled band
  stays (its deep-favorite portion adds volume/capacity/diversification at thinner but positive edge).

## 6. Decision (frozen) — what each outcome means

- **Champion holds Q1+Q2 forward:** the singular edge is real and transfers — proceed to the
  STRATEGY-HANDOFF real-money staging (capture fix → paper executor → human review). 
- **Champion holds Q1 but FAILS Q2 (collapses post-tournament):** the edge was summer-softness;
  a valid, money-saving result — do not deploy into fall.
- **Q3 refinement beats forward:** narrow the band on a deliberate human call.
- **Nothing new certifies (expected):** confirms the champion is singular — the run's own conclusion.
  No cell scan re-slicing changes this; the binding constraint is forward data + the capture fix.

## 7. Kill / no-reopen conditions (frozen)

- Retire the **0.71–0.82 refinement question** if, after ≥ 6 forward weeks with the volume floor met,
  it does NOT beat the pooled champion by ≥ +2.0pp on θ LB.
- **Do NOT reopen** as generalizable edges (in-sample refuted here, re-listing them wastes runs):
  tennis-alone (LODO-fragile single tournament), soccer-consensus-skill (selection_null p=0.44),
  per-category conditioning into efficient markets (regressive — prior finding), wider trader cohorts
  as *copyable* edge (non-copyable at realizable entry on current data; only re-open if the tape gains
  multi-week retention OR capture-at-detection lands), finer-than-0.10 price bands, past-PnL trader
  ranking. These are settled negatives, not open questions.

## 8. Guardrails (unchanged)

Paper-only; arms nothing; real-money eligibility unchanged; no new arm/flag; `consensus.rs` +
`ConsensusParams::default` + every incumbent arm byte-identical (verified zero diff); cost-zero (no
`ANTHROPIC_API_KEY`, no child `claude`, numpy/pandas/psql/stdlib only); DB read-only except the bot's
normal accrual writes; `clob_price_tape` / `trader_fills` SELECT-only.
