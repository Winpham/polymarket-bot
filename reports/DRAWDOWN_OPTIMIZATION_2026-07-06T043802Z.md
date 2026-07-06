# DRAWDOWN-TO-PROFIT OPTIMIZATION — Cycle-4 report

**Branch:** run/beat-best-trader · **UTC:** 2026-07-06T04:38Z · **Posture:** PAPER-ONLY, nothing
promoted, no Rust threshold mutated (D29 Phase-1 STOP holds), DB read-only, cost-zero.
Instrument: `scripts/drawdown_optimization.py` (`--selftest` green; `reports/drawdown_optimization.json`).
Objective switched to **realizable (OUR-price) CALMAR = return ÷ max-drawdown** everywhere, with MAR
(total/maxDD) and return/CVaR₅ as robustness siblings. Event-clustered, flat-SHARES, event-level
aggregation is **numerically identical** to the validated per-fill pipeline (134 wallets, max field
diff 4.7e-14 vs `reliability_score.score_wallet`).

---

## 0. One-paragraph bottom line
**The drawdown edge is real at the trader's price and evaporates at ours — and optimizing the book does
NOT recover it out-of-sample.** (O0) The Cycle-3 reframe reproduces exactly: at their price the
reliability book beats the best single trader on Calmar (0.167 vs 0.122), and the follower tax collapses
that to 0.044 at our entry. (O1) Across five weighting methods the winner by *realizable* OOS Calmar is
**plain EQUAL weight** (0.0265); risk-parity is byte-identical to equal (near-disjoint trading days ⇒
covariance methods add nothing); HRP is between; and the direct **max-Calmar optimizer wins in-sample
(0.0798, the only method that cuts drawdown below the best single at our price) but overfits hard
out-of-sample (0.0028)**. Decisively, **at our price every diversified book has a NEGATIVE
drawdown-reduction-per-return ratio** (−5.7 for equal): the book carries *more* drawdown than the best
single trader once the tax is paid — the halved-drawdown property that holds at their price does not
survive repricing. (O2) Widening the band admits a genuinely new low-band specialist (**Villson**, our-price
in-sample maxDD 0.46, the lowest of any name) and the realizable-Calmar-vs-#names curve *peaks* at OOS
0.2306 (n=3) — **but that peak is a thin-window artifact**: the same book's in-sample Calmar is 0.0076
with maxDD 1.93 (IS and OOS disagree by 30×). (O3) The name-drop tax filter (Calmar≤0) recovers nothing
(0 names killed); only tax-aware *weighting* (max-Calmar) recovers ~29% of the collapse in-sample, and it
overfits. (O4) Rolling rebalancing is **untestable** — re-scoring on a trailing half leaves 0 wallets
above the 30-event floor. **WORTH-IT GATE: NO / INDETERMINATE-BY-POWER.** The refined book's realizable
OOS Calmar (0.1044) does **not** beat the single best reliable trader (master-wuji, 0.2113), and the
belief-blind null cannot distinguish the reliability selection from a random equal-size book on realizable
Calmar (p=0.120). **The value is diversification and — more starkly — the single best trader, not
selection. Nothing promoted; the binding wall (months of independent-regime persistence) is unchanged.**

---

## O0 — Objective switch: CALMAR everywhere, reframe reproduced
| quantity (Cycle-3 frozen anchor) | their price | our price |
|---|---|---|
| **book Calmar** (mean_day / maxDD) | **0.1668** | **0.0443** |
| best single (acorp) Calmar | 0.1216 | — |
| book Calmar OOS | 0.0795 | — |
Reframe **confirmed**: book beats best-single at their price (+37%), and the tax collapses realizable
Calmar to 0.044 (the 0.167→0.044 gap = **0.123**, the optimization target). Live re-derivation on the
current (drifted) data agrees: their-price book Calmar 0.1767, best single 0.1216.

## O1 — Weighting head-to-head (SAME shortlist master-wuji/djokowin/zhuz632/acorp, n=4)
Realizable = OUR price. IS = full→full; OOS = weights fit on EARLY, evaluated on the held-out LATE half
(leak-free, cut 2026-05-26). ddRed/retGiveup = (best-single maxDD − book maxDD) ÷ (best-single return − book return).

| method | their Calmar IS | **our Calmar IS** | our maxDD IS | **our Calmar OOS** | ddRed per ret sacrificed (our) |
|---|---|---|---|---|---|
| equal (**winner OOS**) | 0.177 | 0.047 | 1.194 | **0.0265** | **−5.75** |
| inverse-drawdown (baseline) | 0.177 | 0.050 | 1.138 | 0.0105 | −4.35 |
| risk-parity (ERC) | 0.177 | 0.047 | 1.194 | 0.0265 | −5.75 |
| HRP | 0.177 | 0.047 | 1.194 | 0.0215 | −5.75 |
| **max-Calmar optimizer** | 0.171 | **0.0798** | **0.775** | 0.0028 | **+6.29** |

**Reads.** (1) **Risk-parity ≡ equal (identical to 4 dp)** and HRP≈equal: the shortlist trades on
near-disjoint days, so the 0-fill covariance is ~diagonal-equal and every covariance-aware method
collapses to equal — the noisy small-sample correlation matrix HRP was meant to tame simply carries no
usable structure here. (2) **The generic diversified book has a NEGATIVE ddRed/retGiveup at our price**
(−5.75): its maxDD (1.19) is *worse* than the best single trader's, so it gives up return AND adds
drawdown — the Cycle-3 "halved drawdown" is a their-price property that repricing destroys. (3) **Only
the max-Calmar optimizer cuts drawdown at our price** (0.775 vs 1.14, ratio +6.29) and lifts our-price
Calmar to 0.0798 in-sample — but its OOS Calmar is **0.0028**, the classic in-sample drawdown-optimizer
overfit. **Winner by realizable OOS Calmar: EQUAL** — the simplest possible weighting; the sophistication
adds nothing that survives the holdout. (Bonferroni: 5 methods tested; no single OOS figure is
significant on its own.)

## O2 — Widen the shortlist (pre-registered relaxations, never tuned to pass)
**Pre-registered before results:** (P1) widen the price band 0.45–0.90 → **0.10–0.97** (admit longshot +
other bands), all other gate floors frozen, MM/bot screen ON; (P2) relax the ≥2-positive-sports floor to
≥1 on the frozen band. Bonferroni: 2 relaxations × 5 weightings this cycle.

**P1 widened universe:** pool 166, shortlist n=4 = **[Villson, zhuz632, master-wuji, djokowin]** —
`acorp` drops out and **Villson (a longshot/other-band specialist invisible to the 0.45–0.90 gate)
enters**: exactly the mechanism the charter predicted. Realizable-Calmar-vs-#names curve (winner = equal):

| n | name added | our Calmar **IS** | our maxDD IS | our Calmar **OOS** |
|---|---|---|---|---|
| 1 | Villson | 0.0997 | **0.461** | — (no OOS overlap) |
| 2 | zhuz632 | 0.0332 | 0.969 | — |
| 3 | master-wuji | 0.0076 | **1.933** | **0.2306 (peak)** |
| 4 | djokowin | 0.0183 | 1.497 | 0.1044 |

**Verdict: widening helps ONLY as a thin-window artifact — NOT a stable efficient-frontier gain.** The
OOS "peak" (0.2306 at n=3) sits on a book whose *in-sample* Calmar is 0.0076 with maxDD 1.93 — IS and OOS
disagree by 30×, the signature of power starvation (each name has ~1–3 weeks of overlap). The one durable
signal is that **Villson alone has the lowest our-price in-sample drawdown of any name (0.46)** but zero
OOS coverage — a lead to accrue, not a result. **P2** (cross-sport ≥1) widens the shortlist to n=7
[cnyek, RISK-IS-NEVER-OK, master-wuji, djokowin, zhuz632, Oneger, acorp] but is reported as sensitivity
only (single-sport names are exactly the lumpy-specialist risk the gate exists to screen).

## O3 — Tax-aware selection (recover the 0.167→0.044 collapse?)
Two distinct levers on the widened universe:
- **Name-DROP filter (per-name our-price Calmar ≤ 0):** **0 names dropped** — every widened-shortlist name
  is our-price-positive (Villson 0.100, zhuz632 0.035, master-wuji 0.031, djokowin 0.003). The filter is
  too weak to recover anything (book Calmar 0.0183 → 0.0183). djokowin is the marginal tax casualty
  (their 0.034 → our 0.003, tax 0.039/day) but survives Calmar>0.
- **Tax-aware WEIGHTING (max-Calmar, apples-to-apples on the narrow shortlist):** our-price Calmar
  **0.044 → 0.0798 in-sample = recovers ~29% of the 0.123 collapse gap** by concentrating on the
  tax-robust, low-drawdown names (maxDD 0.775 vs 1.14). **But OOS = 0.0028 — the recovery does not
  survive the holdout.** This is the honest ceiling of tax-aware optimization on the current record: the
  lever exists and points the right way in-sample; there is not enough forward data to bank it.

## O4 — Rebalancing (adapt to reliability drift, or overfit?)
**UNTESTABLE — INSUFFICIENT-DATA.** Re-scoring reliability on a trailing half-window leaves **0 wallets**
above the 30-event / 5-day floor (`roll_n=0`), so a rolling-window book cannot even be formed on ~5 weeks
of sparse per-name coverage. Rebalancing is a months-of-data question; the honest verdict now is that the
data does not exist to answer it.

## WORTH-IT GATE (belief-blind, realizable OOS Calmar)
Refined book = widened universe, tax-pruned, EQUAL weighting (the strongest realizable book found):
[Villson, zhuz632, master-wuji, djokowin].

| gate check | result |
|---|---|
| (1) beat a RANDOM equal-size book on realizable OOS Calmar (weighting held equal ⇒ isolates SELECTION; 1455 valid draws) | book 0.1044 vs random mean −0.0225, **p = 0.120** — **NOT** ≤0.05 |
| (2) beat the best single reliable trader on realizable OOS Calmar | book 0.1044 vs **master-wuji 0.2113** — **NO** |
| (3) selection_null `--calibrate` PASS | PASS (unchanged) — the null is trustworthy |

**VERDICT: NOT worth-it / INDETERMINATE-BY-POWER.** The refined book is directionally above a random
book (random mean is *negative*), but 12% of random equal-size books match or beat it — the reliability
**selection cannot be distinguished from generic diversification** on realizable Calmar. Worse for the
thesis, **the single best reliable trader (master-wuji) beats every diversified book at our price OOS**
(0.2113 > 0.1044, and > the fragile n=3 peak's IS-unstable 0.2306). The headline
**drawdown-reduction-per-return-sacrificed at our price is −7.79** (the book adds drawdown per unit
return) — the opposite of the goal. **If the drawdown book were worth it, it would beat a random book AND
the best single on realizable Calmar; it does neither. The value is diversification/best-single, not
selection.**

## READINESS-LEDGER DELTA
No GO gate moves. Informational: `drawdown_calmar_objective` = **BUILT** (realizable Calmar everywhere,
reframe reproduced); `weighting_optimization` = **EQUAL-WINS / max-Calmar-overfits** (covariance methods
collapse to equal on disjoint days); `shortlist_widening` = **ADMITS-NEW-NAME-BUT-POWER-STARVED** (Villson
enters; peak is a thin-window artifact); `tax_aware_recovery` = **29%-IS-ONLY** (weighting lever exists,
overfits OOS); `rebalancing` = **UNTESTABLE**; `drawdown_worth_it` = **NO / INDETERMINATE** (loses to best
single AND to random on realizable Calmar, p=0.120). **GO gates unchanged 2/4; real-money-eligible = False;
binding constraint = out-of-sample persistence across independent non-expiring regimes (months) + fill/lag
copyability.**

## HONEST BOTTOM LINE + single strongest refined approach
**The optimization is honest and decisive, and the answer is "not worth it on the current record."** The
right objective (realizable Calmar) makes the failure mode legible: **the drawdown edge lives entirely at
the trader's price and the follower tax eats it** — at our entry the diversified book carries more
drawdown than simply following the single best reliable trader, so its realizable
drawdown-reduction-per-return is negative (−7.79). No weighting method escapes this out-of-sample: the
sophisticated ones (risk-parity, HRP) collapse to equal on near-disjoint trading days, and the only method
that cuts our-price drawdown (max-Calmar, +6.29 in-sample, 29% of the collapse recovered) overfits to 0.003
OOS. Widening the band does surface a real new low-drawdown specialist (Villson) but the Calmar gains are
power-starved artifacts. **The single strongest *realizable* approach is therefore NOT a book at all — it
is following the single best reliability-persistent trader (master-wuji: our-price OOS Calmar 0.2113, maxDD
0.57), which dominates every optimized book at our price.** The single highest-leverage next refinement:
**accrue forward days for Villson and forward-test the tax-aware max-Calmar weighting** — Villson is the
only name with a genuinely low our-price in-sample drawdown (0.46) and has zero OOS coverage, and
max-Calmar is the only weighting that cuts drawdown at our price; both need weeks of forward data to move
from "in-sample lead" to "bankable," and both are gated behind the same months-long independent-regime
persistence wall as everything else in this run.

---
*New this cycle: `drawdown_optimization.py` (NEW; O0–O4 + belief-blind Calmar gate; `--selftest` green;
event-level SQL aggregation proven identical to the per-fill pipeline). `reliability_score.py` refactored
(EXTEND: `score_evs` split out of `score_wallet`, selftest green). All read-only, paper-only, nothing
promoted, no Rust mutated.*
