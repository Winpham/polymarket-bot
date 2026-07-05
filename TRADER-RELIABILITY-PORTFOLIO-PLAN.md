# Planning & Thinking Run — Selecting a WINNING PORTFOLIO OF TRADERS by reliability

**The reframe (Tue, 2026-07-05).** "It shouldn't be true that the most profitable and reliable traders
are negative. We just need to detect the ones that follow the trajectory we want — minimal risk and
variance, high consistency, and a clear strength and confidence in their capability." This is right, and
the data proves it: 46% of tracked traders with ≥30 resolved events are **positive at their own price**,
and a stable specialist cohort (johndegen, Sportbetting76, master-wuji, PatienceCapital, sport-intelligence…)
is durably positive over 50–350 events across 10–90 days. Our prior "everyone is negative" verdict was an
artifact of the **objective function**, not the traders.

---

## 1. What we were measuring wrong

Every ranking so far (`B_LB`, `B_point`, router argmax) optimizes **realizable point-ROI re-priced at our
entry**, then punishes it with `mean − z·sd/√effective_days`. On this data that objective is dominated by
three things that have nothing to do with "is this trader reliably skilled":

- **Thin data** — effective_n ≈ 1–3 days ⇒ the √n term nukes every lower bound negative.
- **Irreducible per-bet variance** — binary outcomes give per-event sd of 0.8–6.4 against a mean of
  0.15–1.0, so per-event Sharpe caps ~0.35 even for the best. Reliability in prediction markets lives in
  the AGGREGATE over many events, not the single bet — a variance-punishing LB destroys exactly the
  signal we want.
- **Follower tax** — re-pricing at our entry subtracts the spread+fee before we've even asked "is the
  underlying trader good?"

We collapsed **three distinct questions** into one number:
| Question | What it answers | Price to measure at |
|---|---|---|
| **SKILL** | Is this trader genuinely, repeatably good? | THEIR fill price |
| **RELIABILITY** | Is their edge low-variance, consistent, confident, persistent? | THEIR price, over time |
| **COPYABILITY** | Can WE profit tailing them after tax/lag? | OUR realizable entry |

**The fix: select the portfolio on SKILL × RELIABILITY (their price), then gate/steer by COPYABILITY
(our price) as a separate, downstream filter.** Detecting the winning book is doable NOW; whether we can
bank it is the accrual-gated question — don't let the second kill the first.

---

## 2. Operationalizing "the trajectory we want" — a multi-factor RELIABILITY score

Tue's four criteria → concrete, measurable factors (all per-wallet, event-clustered, at their price):

**(a) Minimal risk & variance** — not per-bet sd (irreducible), but the smoothness of the *aggregated*
equity curve:
- Downside deviation (Sortino denominator) — penalize only losing dispersion, not upside.
- Max drawdown of the cumulative-equity curve (flat-shares) + Ulcer index (depth×duration of drawdowns).
- Tail loss CVaR₅ — average of the worst 5% of event returns.

**(b) High consistency** — the trader keeps being right, not lumpy-lucky:
- Positive-window fraction — fraction of active days/weeks with positive clustered return (want ≥60–70%).
- Calibration — does realized hit-rate match the prices they pay? (A trader who pays 0.70 and hits 0.78
  is +EV *by skill*; one who hits 0.70 is just paying fair.) Reliability = persistent positive
  calibration gap, not raw win-rate.
- Loss-streak control — low autocorrelation / no fat clustered-loss tail.

**(c) Clear strength** — concentrated, legible skill, not diffuse noise:
- Best-cell edge — the sport×band cell where their calibration gap is largest AND real (specialist).
- Skill concentration (share of edge from their top cell) — a specialist beats a generalist for copying.
- Directional, not arb — reuse the MM-filter/profit-source screen: strength must come from prediction
  (net_maker directional edge), not two-sided rebate capture.

**(d) Confidence in capability** — we are STATISTICALLY SURE they're good (this replaces the
variance-punishing LB with a *stability* test, not a *magnitude* penalty):
- Event count & independent-day count (power).
- Cross-regime stability — positive in ≥2 disjoint regimes / ≥2 time-halves (not one hot streak).
- Survives a per-wallet permutation/selection null (their edge ≠ compositional artifact).
- Reliability persistence — early-window reliability PREDICTS late-window reliability (§5, the honesty gate).

**Composite = a GATED score, not a weighted sum.** A trader enters the book only if they clear floors on
every axis (real directional skill AND low downside deviation AND positive-window fraction ≥ τ AND
cross-regime stable). Among those who clear, rank by a risk-adjusted consistency metric (Sortino or
calibration-gap-per-drawdown). Gating (not averaging) is what stops a huge-but-lumpy PnL wallet or a
one-week wonder from ranking above a smooth, consistent +8%/event specialist.

---

## 3. Portfolio construction — the congregation done RIGHT

The repo keeps naming "a higher Sharpe than the best single member" as the prize; reliability-first
selection is how you actually get it. Steps:

1. **Screen** the tracked fleet through §2 → the reliable-specialist shortlist (at their price).
2. **Diversify by correlation, not by count.** Compute the event-level return-correlation matrix across
   the shortlist; assemble a book of specialists whose edges are LOW-correlated (different sports/styles/
   time-of-day). Portfolio variance then falls below any single member's — the one mathematically valid
   route to beating the best trader on risk-adjusted terms (the router failed precisely because top-1 had
   no diversification; a reliable, low-correlation book is the opposite).
3. **Reliability-weight, not PnL-weight.** Allocate by confidence/inverse-downside (equal-risk), so a
   high-confidence smooth specialist gets more weight than a lumpy high-mean one. Cap any single name.
4. **Copyability filter LAST.** Only now re-price at our entry (follower tax by sport) and drop/downweight
   names we can't actually fill near their price (MLB-type sharp cells). The book is chosen for reliability;
   copyability trims it — it never selects it.

Output = a low-variance, high-consistency **book of traders** with a smooth blended equity curve — the
"winning portfolio" Tue described. The signal it emits (weighted consensus of the reliable book) is what a
forward-tracked arm would tail.

---

## 4. How this plugs into what already exists (extend, don't rebuild)

- `trader_scorecard.py` already computes per-wallet `copy_return` (event-clustered), `n_events`, `n_days`,
  `persistence` (early→late corr), and the MM/bot screens — the spine of §2. EXTEND it with the
  downside/consistency/calibration/cross-regime factors and the gated composite.
- `regime_net_edge.py` gives the directional (net_maker) vs arb decomposition for §2(c).
- `best_trader_benchmark.py` becomes reliability-aware: the benchmark stops being "max realizable point-ROI
  LB" and becomes "the best single RELIABLE trader's risk-adjusted consistency," which the book must beat.
- `selection_null.py` / `persistence_tracker.py` supply the confidence/persistence gates.
- A NEW `scripts/reliability_portfolio.py` (read-only, --selftest) does the screen → correlation-diversify →
  reliability-weight → copyability-trim, emitting `reports/reliability_portfolio.json` (the book + its
  blended equity curve + per-name factor breakdown).

---

## 5. The honest trap this must not fall into (critical-partner note)

Selecting on realized consistency is **survivorship/look-ahead bait**: a trader looks smooth in-sample then
reverts. The whole method is only worth building if it passes ONE test — **does reliability PERSIST?**
i.e. reliability measured on an early window must predict reliability on a held-out late window, better than
chance, leak-free (genuine-timestamp fills, not the backfill crawl-stamp). If early-reliability doesn't
predict late-reliability, we're just curve-fitting smooth-looking noise and the book will revert the moment
we tail it. So the build order is:
1. Compute the factor set + gated composite (their price) — surfaces the cohort NOW.
2. **Reliability-persistence validation FIRST** (before any copyability claim): early-window reliability →
   late-window reliability, matched null. This is decidable on current data at their price and is the
   go/no-go for the whole idea.
3. Only if it persists: build the portfolio + copyability filter + the belief-blind copyability gate
   (still accrual-bound for real money — but now we're gating a *reliable book*, not chasing point ROI).

This also reframes the standing "everything is INDETERMINATE-BY-POWER" wall: reliability-persistence needs
far less data than realizable-ROI certification, because it tests a *stable ranking* (does the good stay
good) rather than a *profitable magnitude at our price* — so it may give a real signed answer on the data
we already have.

---

## 6. Proposed next action

A focused autonomous BUILD+VALIDATE run (after Cycle-2 returns, same worktree/branch), scoped to:
- **Thread R1** — factor library + gated reliability composite (extend `trader_scorecard.py`); surface the
  reliable cohort at their price with the full factor breakdown.
- **Thread R2 (the go/no-go)** — reliability-persistence validation (early→late, matched null, leak-free).
  If NO-GO, we stop honestly and know the cohort is smooth noise. If GO, proceed.
- **Thread R3** — `reliability_portfolio.py`: correlation-diversified, reliability-weighted book + blended
  equity curve; copyability trim; benchmark the book vs the best single reliable trader (risk-adjusted).
- Guardrails unchanged: paper-only, promote nothing, belief-blind gate for any copyability/promotion claim,
  no Rust mutation, read-only DB, flat-shares, cost-zero.

**Bottom line:** Tue is right that a reliable, low-variance, high-consistency winning cohort exists and we
were masking it with a variance-punishing, our-price, thin-data objective. The plan separates SKILL/
RELIABILITY (detectable now, at their price) from COPYABILITY (accrual-gated, at our price), builds a
reliability-first gated selection + a correlation-diversified book, and stakes the whole thing on ONE
honest test — does reliability persist out-of-sample. That test is the next thing to run.
