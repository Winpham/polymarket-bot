# Reliability effectiveness — did it work, what's the tradeoff, and how to run it better (2026-07-02, entry 17)

Branch `feat/reliability-effectiveness` (worktree off `main` 577f4c1, tag
`pre-reliability-effectiveness-20260702`). **Convergent with the concurrent bad-days stress test
(D18, sibling session):** that run independently found the D17 `kelly_eighth_capped` sizing
OVER-sizes (band-5 ≈7%/bet, DD>30% in 44% of years at half-edge → NO-GO on real money, fix =
de-lever). This run reaches the same place from the wait-vs-bet angle: at ⅛-Kelly a full fade
loses ~57% of bankroll (99% P(loss)), and the dominant posture is the DE-LEVERED PILOT, not
bet-all-now. Two independent analyses ⇒ **de-lever the band-5 Kelly before any pilot.** The
tradeoff numbers below are at the (too-hot) ⅛-Kelly and should be re-run at D18's de-levered
sizing; the STRUCTURE of the tradeoff (and the PILOT dominance) is sizing-robust. Paper-only, read-only, **zero migrations, no Rust**.
Answers three blunt questions about the reliability-first program (entries 12–15 / D15–D17):
how successful was it, what is the risk/profitability tradeoff **as a number**, and what
iterations make the system work better. Three self-testing instruments, each reusing the gate
machinery byte-identically.

## The honest effectiveness verdict (lead with it)

**Realized risk reduction ≈ 0. Realized profitability change ≈ 0.** The reliability program
(D15–D17) changed nothing live — it sized no money, added no edge, flipped no switch. Judged on
P&L it moved nothing, and this entry says so plainly. What it bought is **epistemic / decision
risk**: it stopped the board reading a real edge as dead (−20% → honest +4.6% within-sample),
proved there is no free diversification to chase (0/12), and named the true wall (out-of-sample
persistence, a cluster COUNT). Those reduce the chance of a *wrong decision*, not variance on a
bet nobody has placed.

The uncomfortable corollary this run surfaces: **the biggest lever on realized profitability is
not another instrument — it is that the live bot alerts the losing strategy while silencing the
winners.** (See Pillar B.)

## Pillar A — the tradeoff, quantified (`scripts/reliability_tradeoff.py`)

Until now "wait for persistence vs bet the real edge now" was a posture. This is a transparent
decision model that prices it. Two states of the world mixed by the **persistence probability π**
(your belief the edge is durable selection skill, not a soft-summer artifact): persists (λ=1) or
fades (λ = ¼ or 0). Crucially the forward model **forecasts a SHARP fall market** — forward
advantage = FALL_BLIND(≈0) + λ·skill, EXCLUDING the summer soft-favorite edge (+1.3% blind) as
non-persistent (entry-15 sport_edge_tracker: fall markets are efficient/overpriced). That removes
the no-losing-slate artifact of bootstrapping only-positive summer days, so a skill-fade genuinely
loses. Three postures over a 30-day (independent-cluster) horizon, ⅛-Kelly-capped; the WAIT/PILOT
postures run the D17 certification test (cluster-robust LB > margin AND ≥10 clusters) after a
12-day accrual window. Self-test PASS (π=1 ⇒ BET_NOW dominates; π=0 sharp-fall ⇒ WAIT avoids the
loss; cert has power + the accrual floor; break-even π is interior).

**The numbers (conditional on the model — it schedules and sizes an edge, it does not create one):**

| quantity | value | reading |
|---|---|---|
| **cost of waiting** (edge real, π≈1) | **−1.22 log-growth** over 30d | BET_NOW +3.07 vs WAIT +1.82 median — waiting ~12d forgoes real compounding |
| **loss avoided** (edge fully fades, π≈0) | **+0.83 log-growth** | BET_NOW −0.86 (P(loss) **99%**) vs WAIT 0 — betting a dead edge at ⅛-Kelly loses ~57% of bankroll |
| **break-even π** (bet-now beats wait) | **5% / 42% / 63%** | partial fade / full fade fair-market / full fade overpriced-fall |
| **PILOT** (tiny during wait, full after cert) | dominates | caps the fade-loss tail (P(loss) ≤6%, ≤0.4% at π=0.95) while keeping most of the real-edge upside |

**What this says about the tradeoff:** the answer depends entirely on two beliefs — how badly
the edge could fade, and how sharp the fall market is. If a fade only partially degrades the skill
(retains ¼), betting now wins for almost any π (break-even 5%). If a full fade into a fairly-priced
or overpriced fall market is plausible, waiting wins unless you're **>42–63% sure** the edge
persists. **The dominant answer is neither extreme: PILOT** — a small stake that learns the one
thing paper cannot (real fill probability at size) and bounds the fade loss, scaling only after the
persistence test certifies. Caveat: the −1.22 "cost of waiting" is specific to a 30-day horizon; a
fixed 12-day wait is a *one-time* cost that shrinks over a longer betting life, while the fade risk
is permanent — which tilts the honest recommendation further toward PILOT-then-certify over
bet-everything-now.

## Pillar B — is the machine positioned to succeed? (`scripts/system_readiness.py`)

Waiting is only coherent if the system is accruing what the persistence read needs and not leaking
money meanwhile. Self-test PASS (ETA math, stalled-detection, leak detector).

| read | finding |
|---|---|
| **accrual ETA** | favorite: 4 independent clusters, 45/day → **~6 days to the 10-cluster persistence floor**. Waiting is a DATED plan (~2026-07-08), not open-ended. |
| **the orthogonal lever** | `trust_weighted` fires **2.5× favorite** (111/day) — 1 cluster so far, ~9 days to floor. IF its orthogonal edge (D17 watch-item) is real, it accrues certification power fast: the profitability upside with a timeline. |
| **THE LIVE LEAK** | effective alerting = **`strict` only** (−EV after costs, entry-10 DODGE) while `favorite`/`elite_fresh_fav` stay **silent**. Anyone acting on alerts follows the WRONG signal. Fix = the pending D12 config (Tue's go). |

## Pillar C — the forward go/no-go (`scripts/persistence_tracker.py`)

The instrument the wall is actually waiting on: split favorite at a cutoff into IN-sample
(discovery) vs OUT-of-sample (forward), read the edge on OUT rows ONLY (leakage-free) via the
reconciled convention (cluster-robust SE + independent-cluster-COUNT floor, D17-a). The TEMPORAL
complement to entry-15's SPATIAL sport_edge_tracker. Self-test PASS (persisting → PERSISTS,
decaying → REFUTED, thin → PENDING, new-regime detection).

**Live read (cutoff = median day):** OUT-of-sample surplus **+19.2%** (higher than the +8.8%
in-sample), including a NEW-regime read **MLB +20.3%** — but only **2 independent forward
clusters** (< 10 floor) → **VERDICT: PENDING**. The early forward signal is *favorable* (the edge
is not decaying out of sample so far, and it shows up in MLB, the sharp post-WC bridge), but it is
not certifiable on 2 clusters — honest. Re-run with a rolling cutoff as the post-WC stream accrues;
it flips to PERSISTS/REFUTED at the date Pillar B computes.

## Model assumptions (stated so they are auditable)

- π (persistence probability) is YOUR belief, an INPUT, not estimated — the model prices the
  tradeoff structure, it does not predict which world we're in.
- The fade model mean-shifts the empirical outcome structure by λ (risk_engine's edge_mult class),
  not a full regeneration; FALL_BLIND ∈ {0, −0.02} brackets the efficient/overpriced fall.
- The WAIT cert test uses a normal z at ≥10 clusters (slightly optimistic vs small-cluster t; it
  makes WAIT certify a hair more often, i.e. conservative for the "cost of waiting").
- Everything inherits a 4-day record; the tradeoff numbers are illustrative of magnitudes, not
  guarantees. Every P&L is conditional on the edge being real (D7's job).

## What this run recommends (concrete, in priority order)

1. **Fix the live leak (highest realized-P&L lever, pending Tue's go):** flip the D12 alert config
   so favorite/elite alert and strict stops being the only signal. Nothing else this run found
   changes money faster.
2. **De-lever the band-5 Kelly, then PILOT** (convergent with the D18 bad-days stress test): the
   ⅛-Kelly-capped stake is too hot (both runs agree); a de-levered PILOT is the dominant posture
   across π AND survives the bad-days test, and it buys the fill-probability data paper cannot.
3. **Watch `trust_weighted`** — the one orthogonal profitability lever, accruing 2.5× fast.
4. **Re-run persistence_tracker + system_readiness at the ~6-day floor** (~2026-07-08) and after
   the WC/Wimbledon ends — that is when "wait" resolves to a verdict.

## What was NOT done / limitations
- No live behavior changed; the leak fix and any pilot are PROPOSED, pending Tue.
- The tradeoff model is stylized (see assumptions); it quantifies structure, not a point forecast.
- Persistence reads PENDING today by construction (4 days) — the instruments earn their value
  forward.

## Rollback
`git revert` the merge of `feat/reliability-effectiveness`; delete
`reports/{reliability_tradeoff,system_readiness,persistence_tracker}.json`. No migrations, no env,
no live behavior touched.
