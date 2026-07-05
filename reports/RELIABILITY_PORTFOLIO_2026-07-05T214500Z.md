# RELIABILITY PORTFOLIO — Cycle-3 report ("select a winning portfolio of traders by reliability")

**Branch:** run/beat-best-trader · **UTC:** 2026-07-05T21:45Z · **Posture:** PAPER-ONLY, nothing
promoted, no Rust threshold mutated (D29 Phase-1 STOP holds), DB read-only.
`selection_null.py --calibrate` **PASSED** (p<0.05 at 2% ≤ 20%; mid-range 78% ≥ 60%) → every null
verdict below is trustworthy.

---

## 0. One-paragraph bottom line
The reframe is **validated at its core and honestly bounded at its edge.** (R1) At the trader's own
fill price, reliability is real and measurable: **66% of 121 scored wallets are +EV by skill** on the
favorite band, and a strict gate (skill-beyond-luck null ∧ cross-sport ∧ both-time-halves ∧
consistency, MM/bot-excluded) yields a **4-name shortlist ranked by Sortino**. (R2 — the go/no-go)
**Reliability PERSISTS out-of-sample: GO.** Early-window reliability rank predicts late-window rank
with signed Spearman **ρ = +0.220, 95% CI [+0.03, +0.40], permutation p = 0.007** — and, decisively,
the **confound-controlled n-stratified null agrees (p = 0.0055)**, so this is not a power artifact; it
survives ×4 Bonferroni. (R3) The correlation-diversified reliability-weighted **book HALVES drawdown**
vs the best single reliable trader (maxDD 0.58 vs 1.14, **in-sample and out-of-sample**) and stays
**positive after the modeled copyability tax** — but it does **NOT** beat the best single trader on
**Sortino** (risk-adjusted return), and the selection does not clearly beat a random book on Sortino
(p = 0.093). **Net: we have a defensible RISK-REDUCTION portfolio (smoother than any single specialist,
the exact "minimal risk/variance" axis Tue prioritized), not a certified risk-adjusted-RETURN edge over
simply following the single best reliable trader. Nothing promoted; the binding wall is unchanged —
persistence across independent, non-expiring regimes over months, plus fill/lag copyability.**

---

## R1 — Factor library + GATED reliability composite (at THEIR price)
Instrument: `scripts/reliability_score.py` (`--selftest` green; `reports/reliability_score.json`).
Per wallet, event-clustered at the trader's **own fill price**, flat-shares (per-event return
`r_e = mean_fills(won − price)` = the per-event **calibration gap**). Factors: **RISK** (downside
deviation, max-drawdown + Ulcer of the equity curve, CVaR₅); **CONSISTENCY** (positive-window fraction
over days, calibration gap, loss-streak); **STRENGTH** (best sport×band cell gap + skill concentration,
MM/bot-excluded directional); **CONFIDENCE** (n_events/n_days, cross-sport + both-time-halves stability,
and a per-wallet **belief-blind skill null** — H0: each fill ~ Bernoulli(its fill price), so the
calibration gap has null **mean = 0 exactly**; σ analytic; the exact "do they beat the prices they pay
by more than luck" test, no threshold tuned).

**Composite = GATED** (clear a floor on every axis: n_events≥30 ∧ n_days≥5 ∧ directional ∧ cal_gap>0 ∧
null_p≤0.05 ∧ pos-window≥50% ∧ ≥2 positive sports ∧ both halves positive), then **rank qualifiers by
Sortino** — NOT a variance-punishing weighted sum.

| result | value |
|---|---|
| wallets scored (≥30 events, band 0.45–0.90, trailing 365d) | **121** |
| **positive cal_gap at their price** | **80/121 = 66%** (corroborates the reframe's "46% positive", higher on the favorite band) |
| **shortlist (gate-clearing, by Sortino)** | **djokowin (+0.44), master-wuji (+0.39), acorp (+0.30), zhuz632 (+0.28)** |

**Sanity check — PARTIAL (1/5 named specialists surface), and the reasons are defensible:**
- **master-wuji** → SHORTLIST ✓ (cal_gap +0.113, null_p 0.003).
- **johndegen** → genuinely skilled (cal_gap +0.145, null_p 0.003) but **MM-flagged** — this is the
  same `0x4f1af091` idiosyncratic-high-variance wallet Cycle-1 traced as the router's swing source;
  excluding it is the "no lumpy high-variance names" sanity **working**, not a false negative.
- **PatienceCapital** → MM-flagged **and** negative on the favorite band.
- **Sportbetting76** (cal_gap +0.041, null_p 0.11) and **sport-intelligence** (+0.081, null_p 0.062)
  → miss the belief-blind **skill-beyond-luck** floor.
- The gate surfaced **belief-blind winners not on the reputation list** (djokowin, acorp, zhuz632) —
  it is not rubber-stamping names. Honest read: the "named durable specialists" were leaderboard/PnL
  reputation; under a directional, skill-null, favorite-band gate most do not clear. **Caveat:** the
  band scoping (0.45–0.90) does not see a specialist's longshot/other-band skill — a known limitation.

## R2 — RELIABILITY-PERSISTENCE VALIDATION — **VERDICT = GO**
Instrument: `scripts/reliability_persistence.py` (`--selftest` green; `reports/reliability_persistence.json`).
Leak-free **per-wallet median-event-time split** (genuine fill ts; crawl-stamp confirmed real, Cycle-2
backfill 1.7%), each half R1-scored. Reliability scalar = regularized Sortino = cal_gap/(downside_dev+0.10).

| rank test (early→late) | Spearman ρ | bootstrap 95% CI | perm p (global) | perm p (n-strata) |
|---|---|---|---|---|
| **reg_sortino** (primary) | **+0.220** | **[+0.03, +0.40]** | **0.0070** | **0.0055** |
| cal_gap (skill) | +0.207 | [+0.02, +0.38] | 0.0085 | 0.0055 |
| pos_window_frac (consistency) | +0.264 | [+0.08, +0.45] | 0.0020 | 0.0005 |

**Transition matrix** (reg_sortino quartiles, 0=low..3=top): early-top-Q → **top-half 60%** (chance 50%),
→ top-Q 40% (chance 25%); bottom-Q stays bottom 39%. **Practical arm:** select on EARLY only (12 of 44
early-eligible, top-Q by early reg_sortino) → **LATE cal_gap +0.052 vs matched-random-subset +0.019,
beats-random p = 0.0445.**

**Verdict = GO.** Reliability **rank** persistence is robust: signed, CI excludes 0, and the
**n-stratified permutation null agrees (p = 0.0055)** — so it is *not* the "big-n wallets are less
noisy in both windows" confound; it survives ×4 Bonferroni. This is the strongest signal any cycle of
this run has produced. **Critical-partner caveats (do not inflate):** (1) the effect is **modest**
(ρ≈0.22, ~5% of rank variance). (2) The **practical profit-arm is marginal** (p=0.044, would *not*
survive ×4 Bonferroni) — reliability *ranks* persist more cleanly than reliability *profit-selection*.
(3) The split is **within-wallet temporal**, not a single-calendar-forward holdout; it proves a trader's
early behavior predicts its own later behavior across the fleet, **not** that the ranking survives a
regime shift at one future date — that remains the months-bound accrual question.

## R3 — Correlation-diversified, reliability-weighted BOOK (R2=GO gated)
Instrument: `scripts/reliability_portfolio.py` (`--selftest` green; `reports/reliability_portfolio.json`).
Shortlist n=4; **correlation matrix is genuinely low** (djokowin·acorp −0.01, master-wuji·zhuz632 +0.06,
djokowin·master-wuji +0.10, master-wuji·acorp +0.18, acorp·zhuz632 +0.26; one noisy +0.85 on 6 common
days). Inverse-downside (equal-risk) weights, 40% cap → ~0.24–0.27 each.

| metric | reliable BOOK | best single (acorp) | book wins? |
|---|---|---|---|
| Sortino (their price, in-sample) | +0.678 | **+0.853** | **NO** |
| max-drawdown (in-sample) | **0.58** | 1.14 | **YES (halved)** |
| positive-window fraction | 67% | 81% | no |
| Sortino (OUT-of-sample: wts from early, eval late) | +0.267 | +0.337 | **NO** |
| max-drawdown (OUT-of-sample) | — | — | **YES (book lower)** |

**Copyability (applied LAST, re-priced at OUR entry = price + follower_tax + band_spread + fee):** book
stays **positive** — totalPnL **+2.89**, Sortino **+0.321**, **0 names dropped** (all 4 survive our-entry
repricing with positive total P&L). **But** this is the *modeled* tax only, **not** fill/lag-validated —
the standing dense-capture/accrual wall means *copyable-positive at our modeled entry ≠ bankable.*
**Belief-blind gate:** matched-random-subset null (conservative inf-clamp) → reliable-book Sortino 0.678
vs random-book finite-mean 1.25, **selection-beats-random p = 0.093** — NOT gate-clearing (need ≤0.01).
**Nothing clears the promotion gate; nothing promoted.**

**R3 read:** diversification buys **smoothness** (drawdown halved, in and out of sample — the risk axis
Tue explicitly prioritized) but **not** risk-adjusted *return* over the single best reliable trader:
diluting acorp (Sortino 0.85, posWin 81%) with lower-Sortino names lowers the ratio. The "book beats the
best single trader on Sortino" prize is **NOT** won; the "minimal risk/variance" objective **IS** met.

## READINESS-LEDGER DELTA
`scripts/readiness_ledger.py` +3 **informational** rows (`--selftest` PASS; not GO gates):
`reliability_shortlist` = **BUILT** (4/121, sanity 1/5); `reliability_persistence` = **GO** (ρ +0.22,
p_global .007 / n-strata .0055); `reliability_book` = **RISK-REDUCTION-ONLY** (maxDD halved, loses on
Sortino, selection-vs-random p=.093). **GO gates unchanged 2/4; real-money-eligible = False; binding
constraint = persistence (months).**

## HONEST BOTTOM LINE — do we now have a defensible winning portfolio of traders?
**Yes as a risk-reduction instrument; no as a certified return edge over the single best trader — and
still accrual-bound for money.** The reframe was right on its central claim (reliability at their price
is real, prevalent — 66% positive — and **persists out of sample**, the R2 GO, which is genuinely new and
survives the confound-controlled null). The correlation-diversified book delivers exactly the trajectory
Tue described — **minimal risk/variance, smoother than any single specialist** (drawdown halved in and
out of sample) — and survives the modeled follower tax. What it does **not** do is beat the single best
reliable trader on Sortino, and the belief-blind judge does not distinguish the selection from a random
book on risk-adjusted return (p=0.093). So the defensible product is *"a low-drawdown book of
reliability-persistent specialists,"* not *"a book that out-returns the best trader per unit risk."*
**Binding constraint (unchanged): out-of-sample persistence across independent, non-expiring regimes
over months, and fill/lag copyability (dense-capture wall).** **Single highest-leverage next action:**
grow the shortlist past n=4 — the whole R3 diversification test is power-starved at 4 names (one +0.85
corr on 6 days can swing it); accrue non-soccer regimes + relax the band scoping so specialists' full
skill (longshot/other bands) enters the gate, then re-run R2/R3 as the shortlist widens. That is what
turns "reliability persists (proven)" into "the diversified book beats the best trader (currently NO)."

---
*New this cycle: `reliability_score.py` (R1, NEW), `reliability_persistence.py` (R2, NEW),
`reliability_portfolio.py` (R3, NEW), `readiness_ledger.py` +3 rows (EXTEND). All `--selftest` green;
reports in `reports/`. Read-only, paper-only, nothing promoted, no Rust mutated.*
