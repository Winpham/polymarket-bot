# Entry 11 — Diversification & Risk Engine: concentration measured, sizing optimized, P(profit) made real

**Date:** 2026-07-02 · **Branch:** `feat/diversification-risk` (worktree off `main`, tag
`pre-diversification-risk-run-20260702`) · **Status:** paper-only, read-only, nothing
promoted, zero migrations. Companion: `scripts/portfolio_concentration.py`,
`scripts/risk_engine.py`, artifacts `reports/portfolio_concentration.json`,
`reports/risk_engine.json`.

The honest reframe of the ask (binding): the owner asked for "almost guaranteed profit."
**No honest system promises that, and this run never does.** The deliverable is a
**risk constitution** — how we would size the consensus edge *if* the gate (D7) ever
says real money — computed so the measured chance of losing is as small as 4 days of data
lets us honestly claim. Every P(profit) here is **conditional on the measured edge being
real and persisting**; if the edge is zero, every policy loses to costs. This engine sizes
an edge; it cannot create one, and it cannot manufacture diversification the record does
not contain.

---

## Pre-registration (frozen BEFORE any number was computed)

### Concentration battery (the "are we over-reliant" question)
Per strategy (`favorite`, `elite_fresh_fav`, `strict`), event-clustered, at-fire entry
(D6), measured costs (0.5¢ haircut + 2% fee):
1. **ICC per grain** of event-level advantage residuals (a − matched-blind edge), clustered
   by (a) **match** (slug minus the market suffix — `-exact-score`/`-more-markets` of one
   game collapse), (b) **slate** = regime × UTC-day, (c) **regime**. Also reported on raw
   advantage (the P&L-swing view).
2. **N_eff = N / design-effect**, DE = 1 + (m̄−1)·ICC, per grain, with a block-bootstrap CI.
   The headline: how many INDEPENDENT bets the record actually holds.
3. **HHI** of exposure by regime / event-day / tournament, on event-count and on P&L;
   **top-tournament P&L share** (the over-reliance number).
4. **Cross-strategy overlap** favorite ∩ elite_fresh_fav, DEDUPED (never double-count).

### The policy menu (frozen — no additions after seeing results)
Same pick stream, same costs, bankrolls B ∈ {$1k, $5k, $25k}:
- **P0 flat_dollar_100** — control, known bad (must reproduce the sign flip).
- **P1 flat_shares_100** — current house default.
- **P2 kelly_quarter, P3 kelly_eighth** — fractional Kelly on the band's own (win-rate,
  cost), shrunk toward 0 by **shrink = clamp(edge_LB/edge, 0, 1)** (per-band, never
  per-market). A band with edge_LB ≤ 0 gets f = 0.
- **P4 flat_shares_capped** — P1 + caps: ≤1 unit/event, ≤3 units/slate, ≤40% of a slate's
  units in one regime, daily stop-loss at −5 units. Caps are evaluated **within each
  resampled block** (the bootstrap unit doubles as the risk-budget window) and use only
  regime + fire order (no outcome leakage) except the stop-loss (past realized P&L only).
- **P5 kelly_eighth_capped** — P3 + P4's caps.
- **Ceilings:** RECOMMENDED policy = highest median log-growth per 100 events subject to
  **P(maxDD > 30%) ≤ 10%** at every horizon, conservative grain. maxDD is peak-relative
  (fraction of the running high-water mark; the standard, bounded definition). Ruin =
  bankroll ever ≤ 20% of B.

### The Monte Carlo (frozen)
**Block bootstrap at the slate grain** (resample regime×UTC-day blocks with replacement —
preserves within-slate & within-match correlation exactly; NEVER iid-per-pick, which fakes
diversification). Sensitivity at **event-day** and **regime-week** grains; the conservative
grain binds (K2). ≥10,000 seeded paths per (strategy × policy × B). Nested horizons
H ∈ {100, 300, 1000} snapshotted along one path. Outputs: median & 5th-pct terminal P&L,
P(P&L>0), maxDD distribution, ruin probability, growth per 100 events.

### Self-tests (ship only on PASS)
Analytic-Kelly match on an iid fixture; zero-edge fixture must lose to costs; correlated
fixture — block bootstrap must recover the inflated variance **and** iid-per-pick must
understate it (the leak the design avoids); cap policy must truncate a scripted drawdown.

### Kill criteria
- **K1:** N_eff < ~40 ⇒ H=1000 P(loss) is EXTRAPOLATION; lean on H=100/300.
- **K2:** conclusions flipping across bootstrap grains ⇒ the conservative grain binds and
  the fragility is a headline.
- **K3:** no "guaranteed" language; every P(profit) carries the conditional-on-edge caveat
  and the zero-edge line.
- **K4:** nothing changes live behavior; the recommended policy is pre-registered for the
  hypothetical real-money day (D7 + pilot floors + Tue), not applied.

---

## Results

### Phase 0 — reproduction (within accrual noise ✓)
| strategy | N_ev | matched surplus | realizable ROI |
|---|---:|---:|---:|
| favorite | 95 | **+10.55%** | +12.28% |
| elite_fresh_fav | 39 | +7.11% | +9.22% |

(Prior reads: favorite +10.5% N=94, elite +9.1% N=39 — reproduces.) Record shape: 4 days
(2026-06-29→07-02), favorite 15 slates / 4 regimes, elite 8 slates / 3 regimes.

### Phase 1 — how many INDEPENDENT bets do we actually hold?
| strategy | N_ev | ICC_match (raw) | ICC_slate | ICC_reg | **N_eff (slate)** | N_eff (regime) |
|---|---:|---:|---:|---:|---:|---:|
| favorite | 95 | 0.079 (0.06) | 0.000 | 0.036 | **95 [51, 95]** | 52 |
| elite_fresh_fav | 39 | 0.000 | 0.000 | 0.000 | 39 [39, 39] | 39 |
| strict | 228 | **0.343** (0.34) | 0.016 | 0.000 | 193 [126, 228] | 228 |

- **favorite holds ~52–95 effective independent bets** (regime-grain floor 52; block-
  bootstrap 95%-CI floor 51). Above the K1 = 40 threshold, so **H=100 ≈ the record itself;
  H=300 and H=1000 are extrapolations** and are labelled as such throughout.
- Once the matched-blind baseline is removed, favorite's per-event edges are ~independent
  within a slate (ICC_slate ≈ 0). The concentration that DOES exist is **within-match**
  (ICC_match 0.079) and **across the regime mix** — not a residual-edge slate collapse.
- **strict** shows the predicted within-match collapse (ICC_match 0.34) — it stacks
  `-exact-score`/`-more-markets` of one game; `favorite` fires fewer sub-markets, so is
  less collapsed.

**HHI / top-tournament P&L share (the over-reliance number):**
| strategy | tournament HHI | ≈ eff. tournaments | top tournament | its share of gross profit |
|---|---:|---:|---|---:|
| favorite | 0.373 | 2.7 | Wimbledon-tennis | **51%** |
| elite_fresh_fav | 0.477 | 2.1 | Wimbledon-tennis | 68% |
| strict | 0.335 | 3.0 | World Cup (fifwc) | 57% |

The winners' profit is **not** WC-dominated — it is **Wimbledon-dominated** (favorite 51%
tennis + 17% WC soccer = ~68% from the two tournaments that both end within weeks). This
is the honest concentration story: not "89% World Cup" (that is the fleet's *volume* mix),
but "~2–3 effective tournaments of P&L, both expiring."

**Cross-strategy overlap (adding a nested strategy adds how many independent bets?):**
- `elite_fresh_fav` is **100% nested inside `favorite`** — deduped union = 95 = favorite
  alone; **eff adds 0 independent bets**. The "two winners" are one bet stream; a portfolio
  of {favorite, eff} is just favorite. Never double-count them.
- `favorite` ⊂ `strict` 42% (strict adds 133 events — but they are the DODGE residue).

### Phase 2 — the risk engine (favorite, block bootstrap, 10k paths)
Full-Kelly-by-band (SE-shrunk): band 0.80–1.0 → **0.565**, band 0.60–0.80 → 0.009 (the
lower band's edge LB is near 0 → shrunk to ~0). The menu, B=$1k:

| policy | H=100 med / P(profit) / P(DD>30%) | H=300 | H=1000 | g/100 |
|---|---|---|---|---:|
| flat_dollar_100 | +1206 / 100% / 0% | +3649 / 100% / 0% | +12235 / 100% / 0% | 0.79→0.26 |
| flat_shares_100 | +936 / 100% / 0% | +2831 / 100% / 0% | +9484 / 100% / 0% | 0.66→0.24 |
| kelly_quarter | +1048 / 100% / 0% | +7676 / 100% / 0% | **+1.35M** / 100% / 0% | 0.72 |
| kelly_eighth | +435 / 100% / 0% | +1968 / 100% / 0% | +36713 / 100% / 0% | 0.36 |
| flat_shares_capped | +441 / 100% / 0% | +1281 / 100% / 0% | +4225 / 100% / 0% | 0.37→0.17 |
| **kelly_eighth_capped** | **+130 / 100% / 0%** | **+430 / 100% / 0%** | **+2272 / 100% / 0%** | **0.12** |

**The validity anchor fires exactly where predicted:** flat_dollar_100 on `strict`
(which carries longshot/DODGE mass) gives median −$349, **P(profit) 33.5%, P(ruin) 45.6%**
at B=$1k/H=100 — the known flat-$ sign flip — while flat_shares stays +$200. On `favorite`
(no longshots) flat-$ is fine. **And the SE-shrunk per-band Kelly automatically DODGES
strict's losing residue:** strict's f-by-band is `1:0, 2:0, 3:0, 4:0.06, 5:0.74` — bands
1–3 are zeroed, structurally reproducing the slice-study DODGE map from sizing discipline
alone.

### The honest P(profit) table — and why 100% is NOT a promise
P(profit) = 100% for favorite/elite at every horizon. **This is not "guaranteed profit."**
It is the block bootstrap faithfully reporting that **within this 4-day record every slate
was net-positive**, so resampling slates cannot produce a losing path. The number inherits
the record's uniform positivity; the moment a losing regime enters the record (post-WC,
post-Wimbledon) it will move. Two consequences, both binding:

1. **The frozen drawdown ceiling is SLACK.** The most aggressive menu policy
   (kelly_quarter) sails through at P(maxDD>30%) ≈ 0 — because the record has no adversity
   to price a drawdown. "Max growth under a non-binding ceiling" degenerates to "bet as
   hard as the menu allows" (the +$1.35M H=1000 median is that artifact). So the frozen
   rule's pick (quarter-Kelly) is **untrustworthy as a real recommendation**.
2. **The honest recommendation is therefore the structurally-capped policy**
   (`kelly_eighth_capped`), whose drawdown is bounded by CONSTRUCTION (caps + stop-loss),
   not by a bootstrap that cannot see adverse regimes. Quarter-Kelly earns its aggression
   only after adverse regimes accrue and the ceiling can actually bind.

**Edge-haircut stress (the teeth on "conditional on edge"):** recommended policy
(kelly_eighth_capped), H=300, B=$1k, measured edge scaled by λ:
| strategy | λ=1.0 | λ=0.5 | λ=0.25 | λ=0.0 (costs-only) |
|---|---|---|---|---|
| favorite | 100% / +$431 | 100% / +$156 | 100% / +$39 | **0% / −$67** |
| elite_fresh_fav | 100% / +$1521 | 100% / +$460 | 100% / +$110 | 0% / −$156 |
| strict | 95% / +$54 | 90% / +$20 | 69% / +$3 | 0% / −$14 |

favorite stays +EV until ~75% of the measured edge is gone; at λ=0 (no edge, costs only)
it loses — the K3 zero-edge line, quantified. `strict` is materially more fragile.

**Grain sensitivity (K2):** P(profit)/P(DD>30%)/ruin are identical across slate /
event-day / regime-week grains for all three strategies (all 100% / 0% / 0%) — no
grain-dependent conclusion flip. (The grains would diverge on a strategy with high
cross-regime correlation; the winners don't have it.)

### Phase 3 — diversification experiments (favorite, flat_shares)
- **A · eff redundancy:** elite ⊂ favorite (100%); deduped union = favorite; eff adds
  **0 independent bets → 0 risk reduction.** Adding elite_fresh_fav to a favorite book is
  not diversification, it is double-counting.
- **B · PRIORITIZE restriction:** favorite∩band[0.80,0.90) lifts per-event growth
  (g/100 0.66 → 0.73) but cuts N from 95 → 33. **Restriction concentrates the edge but the
  volume loss dominates $/day** — the winners are already near the right granularity at
  today's N (consistent with entry 10). It shrinks N more than it helps.
- **C · what an extra independent regime is worth:** spreading favorite's SAME H=100
  volume across k = 1 / 2 / 3 independent regimes changes terminal-P&L SD by
  221 → 227 → 230 (**≈ 0% variance reduction**). Because favorite's within-slate
  correlation is already ~0, de-correlating buys nothing — **the value of breadth is
  volume-linear (more independent events → √N), not a correlation bonus.** This prices the
  sibling breadth run's lever precisely: an extra independent regime is worth exactly what
  the equivalent extra *volume* is worth, no more. (The correlation bonus would appear on a
  high-ICC book like `strict`; that book is not bankable.)

---

## Verdict — the pre-registered risk constitution

**For the hypothetical day D7 + pilot floors + Tue authorize real money on the
consensus-favorite edge, the default sizing policy is `kelly_eighth_capped`:**
one-eighth Kelly on the per-band SE-shrunk (win-rate, cost), with ≤1 unit/event,
≤3 units/slate, ≤40% of a slate's units in one regime, and a −5-unit daily stop-loss.
Its numbers (favorite, conditional on the measured edge holding):

| horizon | P(profit) | median P&L @ $1k | P(maxDD>30%) | P(ruin) |
|---|---:|---:|---:|---:|
| H=100 (≈ the record) | 100%* | +$130 | 0% | 0% |
| H=300 (extrapolation) | 100%* | +$430 | 0% | 0% |
| H=1000 (extrapolation) | 100%* | +$2,272 | 0% | 0% |

\* The 100% inherits a record with no losing slate; read it as "no adverse regime has
occurred yet," not "cannot lose." The honest downside is the edge-haircut row: below ~¼ of
the measured edge, favorite turns negative.

**Why this policy and these ceilings:** (1) the drawdown ceiling is slack on today's data,
so growth-maximization is not a safe selector — a construction-bounded policy is the only
honest choice until adversity accrues; (2) ⅛-Kelly (vs ¼) leaves headroom for the true
edge being smaller than measured (the edge-stress shows real fragility only below λ≈0.25,
but N_eff ≈ 50–95 means the edge estimate itself is loose); (3) the caps bound the
tail the bootstrap cannot see (a losing regime that isn't in 4 days); (4) flat-SHARES,
never flat-$ (the anchor reproduced the sign flip and 45% ruin on the residue-carrying
stream).

**What would change it (accrual triggers — re-run this engine at each):**
- **After the World Cup final AND after Wimbledon** — the first real adverse-regime test;
  the ceiling may finally bind and quarter-Kelly may (or may not) earn its aggression.
- **+300 new fleet events** or **+50 favorite events** — tightens N_eff and the edge
  estimate; re-read the edge-haircut curve.
- **Before ANY real-money pilot** — mandatory re-run; the recommendation is
  pre-registered, not standing.

**What was deliberately NOT done:** no Markowitz/covariance optimizer (estimation noise on
4 days), no per-cell Kelly (overfit class, entry 10), no martingale, no normal-approx VaR
(every tail number is a bootstrap path), no market/venue additions (breadth is the sibling
run's lane — this run prices what it would be worth), no promotion, no alerting, no env or
live-behavior change, zero migrations.

**Rollback:** `git branch -D feat/diversification-risk` + delete the two scripts and two
JSON artifacts; nothing else is touched.
