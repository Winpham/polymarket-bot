# Entry 18 — Correlated Risk: size the GAME, not the position — and keep the profit

**Date:** 2026-07-02 · **Branch:** `feat/correlated-risk` (worktree off `main` 7bdf4a2, tag
`pre-correlated-risk-20260702`) · **Status:** paper-only, read-only on live behaviour, **zero
migrations**, nothing promoted, no env/alert change. Builds on the diversification & risk run
(entry 12 / D15), the reliability portfolio (entry 14 / D17) and the bad-days stress test
(entry 16 / D18). Two new self-testing instruments, each reusing the gate's machinery:

- `scripts/game_correlation.py` — the honest concentration measurement at the GAME grain
  (`superkey.super_event`). Reuses `portfolio_concentration` (ICC/N_eff), `effective_n`
  (cluster-robust), `selection_null` (band/regime).
- `scripts/corr_risk_engine.py` — the correction to `risk_engine.py`: game-block bootstrap +
  nested Gaussian copula, the P0–P4 policy family with per-GAME caps, the frozen objective +
  risk-adjusted ratio + K5 profit-preservation. Reuses `risk_engine.kelly_by_band` byte-compatibly.

Artifacts: `reports/game_correlation.json`, `reports/corr_risk_engine.json`.

---

## The mission, honestly stated

`portfolio_concentration.py` (D15) measured within-slate ICC ≈ 0.008 and reported the book as
"independent." That number is an artifact: it was computed on advantage *residuals* (which
subtract the shared favorite factor by construction), on a 93%-win record with no losing day,
after the event-clustering step had already collapsed the worst same-`event_slug` stacks. The
book's TRUE unit of correlation is the **GAME** (match-key): every position on one game —
moneyline, spread, "team to advance", halftime, O/U, six "Exact Score X — No" — resolves on the
SAME underlying outcome. This run measures and sizes the real correlation unit, and finds the
sizing that **keeps as much profit as possible per unit of honestly-measured, edge-robust
correlated tail risk.** It does NOT change the promotion gate (D7), the null, or anything live.

---

## Pre-registration (frozen BEFORE any number was computed)

**Objective.** RECOMMENDED = max median log-growth per 100 positions **subject to
P(maxDD > 25%) ≤ 10%** under the GAME-BLOCK copula at **λ = 0.5** (half the measured edge),
robust across the `w_game` sweep. Report the frontier, recommend the knee. **risk-adjusted
ratio** = median growth ÷ p95-maxDD (game-block copula, λ=0.5) — the single "profit per unit of
tail risk" number.

**Correlation model.** Resample **GAME blocks** with replacement (never positions, never
`event_slug`). **A · block-bootstrap** (each sampled game keeps its REAL joint outcome — the
benign floor). **B · nested Gaussian copula**: true `P(win_i)=clip(entry_i+λδ, .02, .995)`, δ
calibrated so λ=1 reproduces realized WR; latent `z_i = √w_day·U_day + √(w_game−w_day)·V_game +
√(1−w_game)·ε_i`, win iff `z_i ≤ Φ⁻¹(p_i)`. Sweep **λ ∈ {1, .5, .25, 0}**, **w_game ∈ {lb,
.4, .55, .8}** (lb = the measured lower bound), w_day small. `w_game` is NOT fit (you cannot
estimate it from a no-upset sample) — the tail's sensitivity to it is the binding uncertainty.

**Policy family (frozen).** P0 flat_shares; **P1 kelly_eighth_capped with EVENT-keyed caps**
(the current constitution — its ≤1/event cap is the gap); **P2** = P1 + hard **≤K_game units
per GAME** (sweep {1,2,3,5,∞}, keep highest a-priori-edge positions); **P3** = P2 + drop the
"Exact Score — No"/entry≥0.95 redundancy; **P4** per-game Kelly (size the game as ONE bet).

**K5 profit-preservation (teeth).** The recommended policy's median growth at λ=1 must be
**≥ 90% of P0/P1's**. If no policy both cuts the tail AND keeps ≥90% of the edge's growth,
THAT is the finding.

**Kill criteria.** K1 n_eff(game) < ~40 ⇒ long horizon is EXTRAPOLATION. K2 conclusions
flipping across `w_game`/grain ⇒ the fattest-tail setting binds and the fragility is a headline.
K3 no "guaranteed" language; every P(profit) carries the conditional-on-edge caveat and the λ=0
line. K4 nothing changes live behaviour. K5 as above.

---

## Phase 0 — reproduction (within accrual noise ✓)

`favorite` resolved record (grew to 5 UTC-days, 2026-06-29→07-03): **220 positions on 78 GAMES**
(prompt: 219/79), **112 `event_slug` clusters** in between, **top-10 games hold 64%** of
positions (prompt: 62%), **66% World Cup** across **12 WC games**, realized **WR 93.2%**, δ ≈
**+0.14**. Worst-game FULL-upset block loss (flat-shares, all positions lose) **−$870…−$1,444**
(the copula's partial-block loss lands in the prompt's −$600…−$1,200 range). All reproduce.

The mission's premise is not just confirmed, it is **understated**: `fifwc-eng-cdr-2026-07-01`
spans **7 distinct `event_slug`s**, so the constitution's ≤1/event cap lets ONE game take **7
units = 35% of a $10k bankroll** under ⅛-Kelly. A single upset there is a −35% drawdown from one
game.

## Phase 1 — the honest correlation measurement (`game_correlation.py`)

| grain | favorite | what it means |
|---|---:|---|
| positions | 220 | staked market bets (the bankroll-swing unit) |
| `event_slug` clusters | 112 | the gate's / constitution's unit (≤1/event keys here) |
| **GAMES** (`super_event`) | **78** | the true correlation unit — up to 17 positions each |

**Why ICC_slate ≈ 0.008 is a benign-sample artifact, reproduced numerically.** Measure the
correlation of the RAW win outcome at the GAME grain and you get ICC_win = **0.12** — but even
that is between-game *skill* variance, not within-game clumping: the within-game **pair
concordance is 0.874, exactly the 0.873 independence baseline**, and the 6 mixed-outcome games
have ICC = 0.000. The measured within-game correlation is ≈ 0 **because no favorite team was
upset on this record** — the shared block shock (moneyline+spread+advance+halftime resolving
against together) was never sampled; the only within-game losses are idiosyncratic single-market
losses, which ARE independent. The structural correlation is invisible until an upset occurs, and
the mechanism guarantees it is large.

**How many independent bets at the game grain?** The honest answer is a RANGE, not a point:
**n_eff(game) ∈ [78, 220]**. The measured cluster-robust n_eff is ~200 (near the 220 position
count) — the same benign-sample artifact one level down. Under a full block shock (w_game→1) the
design effect is the mean positions-per-game (2.8) and n_eff → 78. Which end binds depends
entirely on the unmeasurable `w_game`. That is the whole game.

## Phase 2–3 — the risk-adjusted sizing (`corr_risk_engine.py`)

The engine resamples GAME blocks at the POSITION grain (correcting `risk_engine`'s
event-clustering, which is right for the EDGE but wrong for the SWING). **Self-test proves the
leak this fixes:** on a fully-correlated-game fixture the game-block bootstrap recovers terminal
SD 3309 while a POSITION bootstrap reports 1082 (understates the tail 3×), and the per-game cap
provably truncates it. Copula calibration lands where the pre-run sim predicted: **P1 at λ=0.5
gives P(loss) ≈ 9%, p95 maxDD 24.7%; λ=0.25 P(loss) ≈ 30%; λ=0 (efficient market) P(loss) ≈
64%, all policies losing to costs.**

**The frozen objective picks P1** — but only because the DD ceiling is SLACK (even the levered
P1 hits P(maxDD>25%) = 4.7% < 10% on average paths). The average-path ceiling **cannot see the
worst-case single-GAME block** (35% of bankroll), because the record has no upset to sample it.
So, exactly as D15 chose `kelly_eighth_capped` over `kelly_quarter`, the honest recommendation is
the **construction-bounded** policy. The K5 sweep decides which:

| config | bets | worst-game loss (% bankroll) | g/100 @ λ=1 | **K5** | ratio @ λ=0.5 |
|---|---:|---:|---:|---:|---:|
| P0 flat_shares | 220 | 14% | +0.085 | 32% | 0.45 |
| **P1 constitution (≤1/event)** | 112 | **35%** | +0.265 | 100% | 0.50 |
| P2 ≤1/game | 78 | 7% | +0.191 | 72% | 0.36 |
| P2 ≤2/game | 89 | 14% | +0.217 | 82% | 0.40 |
| **P2 ≤3/game  ← recommended** | 99 | **21%** | +0.241 | **91% ✓** | 0.44 |
| P2 ≤5/game | 109 | 23% | +0.260 | 98% | 0.49 |
| P3 drop redundancy | 87 | 14% | +0.214 | 81% | 0.39 |
| P4 per-game Kelly | 112 | 7% | +0.187 | 70% | 0.37 |

**P2 ≤3/game is the unique knee**: it bounds the worst single-game loss **35% → 21% of
bankroll** while preserving **91% of the edge's λ=1 growth (K5 PASSES)**. Tighter caps (≤1,≤2)
and P4 bound harder (7–14%) but gut growth to 70–82% (K5 fail). ≤5/game preserves 98% but barely
bounds (23%). The per-game cap is **not a free lunch** — it lowers the average-path risk-adjusted
ratio (0.50 → 0.44), because the tail it insures against is one the benign record cannot price.
It is **insurance**, bought at ~9% of median growth, against the levered-block tail that appears
only when a stacked favorite is upset.

**Does dropping the "Exact Score — No" redundancy help? NO — it is EV-negative (P3).** Those 50
near-certain markets (WR 0.98) carry **+$2.5/position of independent EV** and, crucially, are
**near-independent of a directional upset** — a different final score still makes "Exact Score X
— No" win. They are the LOW-correlation, +EV positions; dropping them removes profit without
cutting the directional tail. (This exposes a conservatism in the single-`w_game` copula: it
applies one correlation to all of a game's markets, over-stating the correlation of the
totals/exact-score markets. The true within-game structure is heterogeneous — the tail lives in
the ~few DIRECTIONAL markets, which the count cap bounds as a robust proxy.)

**Robustness (K2).** The tail is **insensitive to the cross-game day shock `w_day`** (P1 p95
maxDD 24.2% → 23.7% as w_day 0.05 → 0.40) and to `w_game` over [0.12, 0.8] (p95 maxDD 23.6% →
24.1%). The conclusion does not flip on a grain. **WC-exclusion cross-check:** off the World Cup,
favorite is **74 positions on 66 games ≈ 1 per game** (tennis/MLB fire one market; only soccer
stacks) — so P1 ≡ P2≤3/game **off-WC (the cap is inert)**. The levered-block risk is a
**World-Cup-soccer-specific phenomenon**; the per-game cap is free insurance that only activates
while the book is soccer-heavy, and rotates itself off as the calendar moves to tennis/MLB.

---

## Verdict — the corrected go/no-go, and it turns on λ

**The instrument's recommended PRE-REGISTERED sizing (for the hypothetical GO day, NOT applied):**
`kelly_eighth` per band (SE-shrunk), with the exposure cap **re-keyed from `event_slug` to the
GAME**: **≤3 units per match-key** (super_event), plus the constitution's ≤3/slate, ≤40%/regime,
−5-unit daily stop. This bounds the worst single-game block at ~21% of bankroll (vs 35% today),
costs ~9% of median growth, and is inert off soccer. Its numbers (favorite, conditional on the
edge, game-block copula, B=$10k):

| | λ=1 | λ=0.5 (the honest number) | λ=0.25 | λ=0 |
|---|---:|---:|---:|---:|
| P(profit) | 100%* | 89% | 66% | 34% |
| median P&L | +$7,188 | +$2,608 | +$852 | −$702 |
| **risk-adjusted ratio** | — | **0.44** | — | — |

\* The 100% inherits a record with no losing slate (D15 artifact), not a promise.

**GO / NO-GO / NOT-YET: NOT-YET on real money — and the reason is λ, which the record cannot
establish.** The whole go/no-go pivots on how much of the measured edge is real (λ). At λ=1 the
book compounds beautifully; at λ=0.5 it still profits with a bounded tail; at λ≤0.25 it bleeds;
at λ=0 it loses to costs. **4 benign days cannot distinguish λ=1 from λ=0.25**, because the
separating event — an adverse correlated day where stacked favorites are upset together — is
exactly what the record does not contain (the same wall as D18/D19). What would move it:
**survive ≥K adverse correlated days across ≥5 non-expiring regimes** (calendar-gated, months),
per D18/D19 — NOT more benign WC weekends. This run does not shorten that clock; it makes the
sizing HONEST about the correlation unit so that when the clock runs out, the book is not
carrying 35%-of-bankroll single-game blocks.

**K5 outcome, stated plainly:** a policy that both cuts the correlated tail AND preserves ≥90% of
the profit **exists** (P2 ≤3/game, 91%). The trade-off is real but small — bounding the worst
block to 21% costs ~9% of median growth. Going tighter (≤1–2/game, worst block ≤14%) would gut
15–28% of the edge and fails K5; that is the honest price of harder de-levering, and the record
does not justify paying it.

## Kill criteria honored

- **K1** n_eff(game) ∈ [78, 220]; H=5× (≈1yr) labelled EXTRAPOLATION in the artifact, leaned on
  H=1× (220 positions ≈ the record).
- **K2** the `w_game` and `w_day` sweeps are IN the output; the tail is robust to both and the
  WC-exclusion check is reported — no grain-dependent flip. The fattest-tail w_game=0.8 governs
  the recommendation (both frontier cells checked).
- **K3** no "guaranteed" language; every P(profit) is conditional-on-edge; the λ=0 costs-only
  line stands; the risk-adjusted ratio at λ=0.5 is the honest headline number.
- **K4** nothing changes live behaviour — instruments + a *proposed* (not applied) cap re-key +
  this memo only.
- **K5** PASS (P2 ≤3/game preserves 91%); the trade-off is quantified, not hidden.

## What was deliberately NOT done

- **Not applied to the live Rust bot.** The cap re-key (`event_slug` → game) is pre-registered
  for the hypothetical GO day; flipping any live behaviour is Tue's explicit call (three gates:
  this proposal, D7, a pilot).
- **No second strategy** (reliability is supply-limited, D15/D17 — this run sizes the ONE edge).
- **No `w_game` / Kelly-fraction fit on the record** (no-upset sample; bounded and swept instead).
- **No per-market-type tuning** (the market_resid/entry-10 lesson) — the count cap is the robust
  proxy for "bound the directional stack"; a market-type-aware cap is the theoretically-right
  refinement but requires classification I will not fit here.
- **No promotion, no alerting, no env, no migration.**

## Rollback

`git revert` the merge of `feat/correlated-risk`; delete `scripts/{game_correlation,
corr_risk_engine}.py` and `reports/{game_correlation,corr_risk_engine}.json`. No migrations, no
env, no live behaviour touched.
