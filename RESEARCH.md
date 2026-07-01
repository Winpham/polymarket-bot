# RESEARCH — Optimal Congregation Engine (§3 mandate)

Evidence-backed findings, each a falsifiable claim with the result beside it. Run
2026-06-30, branch `feat/congregation-engine`. All numbers from read-only SQL over the
live `polymarket` DB (`docker exec polymarket-bot-postgres-1 psql`), reproducible via
`scripts/asof_preflight.py` + `scripts/asof_slice_scores.sql`.

The mandate is to find the **most optimal model for congregating the fleet's best
traders into a signal measurably better, risk-adjusted, than any single one of them.**
The north star: assemble a diversified book of domain-certified specialists, size each by
its certified shrunk edge, and let genuinely uncorrelated edges combine into a higher
Sharpe than the best single member. That mechanism has **one empirical precondition**:
≥2 independent, capturable, persistent per-context specialists must actually exist on
this data. §3 tests that precondition first, because if it fails the whole model is moot.

---

## Pre-registration (H1) — the candidate set, fixed before looking

Certification math is frozen to the existing gate (zero new statistics): per
`(wallet, slice)`, event-clustered surplus over the fleet band-blind, Bonferroni
one-sided lower bound `lo = surplus − probit(1−0.05/nComp)·sd/√N`, `nComp` = that
wallet's slices-with-data. **Trusted@capture ⇔ N≥30 ∧ lo > margin**, `margin =
slippage(0.01)+fee(0.02) = 3%`. Routing dimension = `(sport, band)` only (H7). Time axis
= slug-parsed event date (D1). Cuts pre-registered: 2026-06-29 and 2026-06-30 (the only
region with any both-sided coverage). Weighting-scheme bake-off (headcount vs
quality-weight vs lower-bound weight vs log-odds pool vs correlation-discounted) was
pre-registered as the Phase-2 comparison **conditional on ≥2 specialists existing** —
that condition failed, so no scheme was selected (nothing to select over).

---

## Finding 1 (identification — the binding constraint): NO capturable per-sport specialist exists, in-sample or as-of. **PREMISE FALSIFIED.**

| test | result |
|---|---|
| Trusted@capture per-sport cells — as-of cut 2026-06-29 (train) | **0** |
| Trusted@capture per-sport cells — as-of cut 2026-06-30 (train) | **0** |
| Trusted@capture per-sport cells — **full window, in-sample** (most generous) | **0** |
| wallet-sport cells with ≥30 events on **both** sides of a cut | **0** |

The most generous possible test — all data, no walk-forward, no persistence requirement —
still certifies **nobody**. The frontier (full-window, N≥15, ranked by lower bound):

```
wallet         sport     N   surplus     lo      hi   verdict
0x65018f9f…    soccer   28   +0.274   +0.097  +0.452  INDET(floor)   <- big edge, sub-floor N
0x2117ae94…    soccer   20   +0.197   +0.024  +0.371  INDET(floor)
0x204f72f3…    tennis  112   +0.042   +0.002  +0.081  INDET          <- N ok, edge < margin
0x2005d16a…    tennis  107   +0.041   +0.001  +0.080  INDET
0xe9a6ed2e…    soccer   58   +0.108   -0.034  +0.250  INDET          <- N ok, variance kills lo
```

**Why (both Forge-predicted binding constraints, confirmed):** (a) the wallets showing an
edge are below the 30-event floor (short tournaments); (b) the wallets clearing the floor
have surplus below the 3% capture margin (tennis ~4%) or too much variance (soccer). No
combination clears `lo > 3%`.

## Finding 2 (independence — the diversification driver): the record is ONE slate. Diversification is impossible by construction.

- The entire meaningful forward record is **~two adjacent days of one tournament**: World
  Cup soccer 2026-06-29 (156 events, 77 wallets) + 2026-06-30 (121 events, 61 wallets),
  which hold ≈89% of all resolved buys. Tennis is 166 events across just **9** Grand-Slam
  event-days.
- Dated independent event-days per sport (the ceiling on any wallet's independent-N):
  **soccer 21, tennis 9, mlb 12**, else ≤4. Crypto: 237 events, **0** dated days.
- Consequence: the few wallets that nominally clear N≥30 do so via correlated
  within-tournament markets (effective independent-N ≪ 30), and any two candidate
  "specialists" are co-active on the *same* World Cup matches. The free lunch of the north
  star — combining *uncorrelated* certified edges — has no uncorrelated edges to combine.

## Finding 3 (combination): untestable, and moot. There is nothing to weight.

Every weighting/aggregation question in §3 (headcount vs quality vs lower-bound weight vs
log-odds opinion pool vs correlation-discounted) presupposes ≥2 certified specialists to
weight. With **0**, all schemes collapse to the same empty signal. The correlation
structure that would drive any diversification benefit is degenerate (one slate). No
scheme is selected; selecting one on this data would be selection on noise (H1 violation).

## Finding 4 (capture & honesty): the capture margin is not the limiting factor — the edge is absent *before* fees.

Certifying at `margin = 0` (the sharp's own edge, ignoring the follower's fees/slippage)
still yields **0** per-sport Trusted cells with N≥30 (the N≥30 cells sit at lo ≈ +0.002 to
−0.034). So the follower-capture haircut is not what kills the thesis — there is no
sharp-side edge to haircut. The honest abstention frontier is therefore **total**: on this
data, silence is the correct output everywhere; no context supports a certified signal.

---

## Conclusion

The precondition for "better than the best of them" — ≥2 independent, capturable,
persistent per-context specialists — is **falsified on the current data**, from every
angle (as-of, in-sample, margin-free), for a structural reason (the record is one
tournament weekend of mostly one sport). Per charter §0.5 the diversification premise is
**DEAD ON THIS DATA**; Phases 2/5 are not built. The deliverables are the leak-free as-of
instrument, this honest null, and the accrual plan (DECISIONS.md D4 / REPORT.md). This is
a successful run: the correctly-built instrument correctly reports that the edge is not
yet identifiable, rather than a green number that could not survive the nulls or the
capture margin.
