# WIDE-VOTER ANALYSIS — does widening the consensus voter set (top-40 → 60/80/100/150/200) add REAL edge?

**Run:** `feat/wide-voter`, paper-only, DB read-only, cost-zero. 2026-07-10.
**Replay:** `scripts/wide_voter_replay.py` (faithful trailing-48h reconstruction of the real
`consensus.rs::favorite` arm from the durable `trader_fills` archive).
**JSON:** `reports/wide_voter_replay.json`.

---

## TL;DR — VERDICT: widening is DILUTION, not edge. Build nothing.

Prod votes with **top-40** (rank≤40 ⇒ 191 eligible wallets), captures top-200, follows 1,098.
The trapped coverage (ranks 41–200 profiled-but-not-voting) is enormous, but the **marginal
markets it would unlock carry no honest edge**:

| voter cutoff C | marginal picks/day | marginal honest ROI/turn (ev-clustered) | belief-blind surplus | belief-blind **LB** | p_emp |
|---|---|---|---|---|---|
| **40 (champion, REAL prod set)** | — (37.8 total) | **+7.05%** (splitB +3.57%) | (baseline) | — | — |
| 60 | 2.9 | **−25.85%** | −19.44% | −30.03% | 0.998 |
| 80 | 44.9 | **+0.71%** | +0.83% | −3.09% | 0.402 |
| 100 | 163.4 | **−0.30%** | −0.10% | −2.38% | 0.368 |
| 150 | 190.4 | **−0.00%** | +0.06% | −1.96% | 0.280 |
| 200 | 228.9 | **+0.82%** | +1.66% | **−0.20%** | 0.001 |

The **marginal-set honest ROI is the verdict**, and at every cutoff it is **~0%** — collapsing
onto the blind favorite-band baseline (belief-blind surplus ≈ 0, lower bound **negative at every
cutoff**). Against the champion's real **+7.05%** (or even the decayed forward-regime **+3.57%**),
the added markets are pure **dilution**. Widening multiplies turnover ~6–7× (from ~38 to ~267
picks/day at C=200) at an honest marginal ROI indistinguishable from zero — which *shrinks* the
portfolio's ROI-on-turnover (7% → ~1.7%) and balloons correlated exposure, for **no reliable added
daily-$**. **No refined config — with or without the liquidity/rank quality gates — clears the
pre-registered potential floor. Top-40 is already the right cutoff. No shadow arm was built.**

---

## 1. Method & the honest fidelity result (read this before trusting any number)

**Replay.** For each cutoff C∈{40,60,80,100,150,200} the voter set = `followed_traders.rank ≤ C`
(rank = the stored per-wallet min rank; rank≤40 == `consensus_eligible` == prod's live voter set —
191 wallets; ≤100 = 404; ≤200 = 1,105). The *only* thing that changes across cutoffs is who may
vote; every other champion gate is identical (`min_backers=3, max_opposers=1, max_price_std=0.10`,
favorite band 0.65–0.98, two-sided MM exclusion, 48h trailing window). Fills come from the durable
`trader_fills` archive (the live `consensus_vote_window` is pruned to ~4 days). A sweep-line
reconstructs prod's per-cycle behaviour: at each candidate fire time *t*, the book = fills in
(t−48h, t] from eligible voters; the signal fires the **first** *t* the gates pass, and at-fire
`initial_mean_price`/std/total are taken from that window only (no look-ahead). Same-price laddering
is collapsed exactly (fill-count-weighted mean/std).

**Fidelity gate — PARTIAL, and honestly disclosed.** Replaying the champion at C=40 and comparing to
prod's real `consensus_signals(strategy='favorite')` set (458 signals):

- **Scoring is faithful.** On the 209 markets both fire, at-fire entry prices match to a **median
  0.18¢ (90% within 2¢)**. Running my exact honest metric on prod's *stored* favorite set reproduces
  **+7.05% ev-clustered** (matches the documented champion +8.36% realizable / +2.2% resolved).
- **Set membership only partially reproduces** (recall 46%, precision 53%). The gap is **not a gate
  bug** — of the missed markets, **zero fail on the band/std/opposer gates**; every miss is "not
  enough eligible one-sided backers." The causes are **data-availability limits, all conservative**:
  1. **Point-in-time rank drift** — `followed_traders.rank` is a single *current* snapshot; prod
     voted on ranks *as-of each cycle*. A wallet ranked 30 then / 150 now (or vice-versa) shifts set
     membership. (~80 missed markets.)
  2. **Capture bootstrap** — tracking/vote-window capture started ~06-30; **06-29 = 0/73 recall**.
     (~24 markets absent from the archive.)
  3. **Cycle-timing / two-sided evolution** across the 48h window (~145 markets).
- My replay is **conservative** (fires *fewer*, never a phantom in-band cluster), and fidelity is
  best on recent days (56–58% by 07-08/09) where ranks are closest to the snapshot.

**Consequence for validity (and why the negative is robust).** Because the replayed top-40 set is
depressed (it misses the high-edge early World-Cup markets), it is **not** used as the baseline.
Instead the baseline is anchored on prod's **real** favorite set (+7.05%), and every marginal set is
defined as `replay_fav(C) − replay_fav(40) − prod_fav_set` — subtracting BOTH the replayed-40 set
AND prod's real set, so top-40 contamination is purged and what remains genuinely needs rank 41–C
voters. Any residual rank-drift contamination can only pull marginal ROI *up* toward the champion's
+7% — yet it sits at ~0%, so the genuinely-wider markets are **≤0%**. The negative is robust to the
fidelity limitation *by direction*.

**Honesty rails applied.** At-fire `initial_*` only (never live recency/total_usd); corrected fee =
`catrate·(1−p)` per stake, entry-only (sports 0.03; canonical `fee_schedule_sensitivity.py`); flat
$100; event-clustered on the match-level `super_event` key; belief-blind surplus vs a **same-cutoff**
`_blind` band baseline rebuilt at each C; permutation null (`selection_null.null_pvalue`, 2000 draws)
**calibrated PASS** on the replayed blind universe (p<0.05 in 12%, mid-band 72%); multiple-testing
noted below.

---

## 2. Marginal edge by cutoff (the gating question)

See the TL;DR table. Every marginal set's honest ROI is ~0% and its **belief-blind lower bound is
negative** at every cutoff. C=60 is actively terrible (−26%, tiny n). The one arithmetically-positive
raw cell, **C=200 (+0.82%, surplus +1.66%, p=0.001)**, is *selection-real* (the wider selection beats
a random draw from the blind favorite band) but the effect is **tiny and its LB is below zero** — it
does not beat the blind baseline with any margin, let alone approach the champion.

## 3. Layering the favorite_v2 quality gates (the "refine so it has potential" step)

Tested each marginal set **raw**, **+liquidity** (at-fire `total_usd ≥ $1k`), and
**+liquidity+rank** (require ≥1 top-40 backer). ROI-ev / n_ev / belief-blind LB:

| C | raw | +liq $1k | +liq+top40 |
|---|---|---|---|
| 60 | −25.85 / 35 / −30.03 | −25.94 / 30 / −30.14 | −25.94 / 30 / −30.21 |
| 80 | +0.71 / 142 / −3.09 | −9.19 / 69 / −11.54 | −12.02 / 60 / −14.32 |
| 100 | −0.30 / 367 / −2.38 | +0.57 / 102 / −3.61 | −1.34 / 86 / −5.02 |
| 150 | −0.00 / 458 / −1.96 | −0.02 / 127 / −4.24 | −1.95 / 106 / −5.90 |
| 200 | +0.82 / 673 / −0.20 | **+4.25 / 195 / +0.56** | −0.04 / 140 / −3.30 |

The gates **do not rescue** the edge — they mostly make it worse while discarding most of the
turnover we were trying to capture. The lone positive-LB cell, **C=200+liq (+4.25%, p_emp=0.01,
LB +0.56%)**, is **1 of 18** gate×cutoff cells: it **fails Bonferroni** (needs p ≤ 0.05/18 = 0.0028)
and its LB **+0.56% is far below the standard's +3% promotion margin**. It is a post-hoc-selected,
liquidity-thinned subset (~30 picks/day) — a forward-only curiosity, not a buildable config.

## 4. Robustness — regime, non-FIFWC holdout, time-split (marginal sets)

| C | non-FIFWC | split A (≤07-01, World Cup) | split B (≥07-02) |
|---|---|---|---|
| 80 | +2.49 / 117 | **−33.69 / 15** | +4.51 / 128 |
| 100 | +0.04 / 340 | −9.25 / 25 | +0.27 / 343 |
| 150 | +0.23 / 432 | +1.50 / 23 | −0.14 / 436 |
| 200 | +0.59 / 646 | +1.77 / 41 | +0.76 / 632 |

The wider markets are **~0% everywhere** and **strongly negative in the high-value World-Cup regime**
(split A −9% to −34%) — the exact regime where the champion earns +12.3%. There is no regime, no
holdout, and no split where the marginal turnover carries the champion's edge.

## 5. Turnover × ROI/turn × daily-$ (never one axis)

Widening does deliver the turnover — and nothing else:

| | picks/day | ROI/turn | daily-$ (nominal) | daily-$ (belief-blind LB) |
|---|---|---|---|---|
| champion top-40 (real) | 37.8 | +7.05% | ≈ +$266 | positive (LB +4.9% documented) |
| champion top-40, forward regime (splitB) | 37.8 | +3.57% | ≈ +$135 | positive |
| + marginal @ C=200 | +228.9 | +0.82% | +$188 nominal | **≈ $0 / negative (LB −0.20%)** |

Adding ~$23k/day of turnover at a marginal ROI whose honest lower bound is **below zero** does not
reliably grow daily-$ (the +$188 nominal is inside the noise), while it **collapses portfolio
ROI-on-turnover from ~7% to ~1.7%** and multiplies correlated same-day exposure and capacity strain.
That is the textbook definition of dilution.

## 6. Recommendation & decision

- **Top-40 is already the right voter cutoff.** No cutoff in {60,80,100,150,200}, and no cutoff +
  liquidity/rank gate, produces marginal turnover whose honest ROI clears (a) the champion's
  realizable edge, (b) the decayed forward-regime edge, or (c) even a 0% belief-blind lower bound.
- **No shadow arm was built** (brief §4: build only if the analysis proves potential; it disproves
  it). No Rust touched; `ConsensusParams::default` and the champion remain byte-identical.
- **Single forward-only note (not actionable now):** the *only* direction with a positive
  belief-blind LB is **C=200 + $1k-liquidity**, and it dies under multiple-testing (p=0.01 vs 0.0028
  bar) and misses the +3% margin. If widening is ever revisited, it is the one cell to pre-register
  and let the forward gate judge — but it captures only ~30 marginal picks/day, so the turnover prize
  is largely gone anyway. Not worth a shadow arm today.

## 7. Honest one-paragraph verdict

Widening the consensus voter set beyond top-40 unlocks large trapped **turnover** (up to ~+229
picks/day at C=200) but the **marginal markets carry ~0% honest ROI-on-turnover at every cutoff**
(−25.85%, +0.71%, −0.30%, −0.00%, +0.82% at C=60/80/100/150/200), with a **negative belief-blind
lower bound at every cutoff** and a calibrated null — i.e. the added signals collapse onto the blind
favorite-band baseline and are **dilution, not edge**, versus the champion's real +7.05% (forward
+3.57%). Layering the favorite_v2 liquidity/rank gates does not rescue it; the lone positive cell
(C=200+liq, +4.25%/LB+0.56%) fails Bonferroni across the 18-cell sweep and misses the +3% promotion
margin. Because the marginal ROI product does **not** grow daily-$ (nominal +$188/day is inside the
noise, honest LB ≤ $0) while it craters portfolio ROI/turn 7%→1.7%, **the honest finding is that
top-40 is already optimal and no wider config was built.** Caveat and judge: exact reproduction of
prod's historical top-40 set is limited to ~46% by point-in-time rank drift and the 06-29 capture
bootstrap (scoring is faithful to 0.2¢; the negative is robust because contamination can only inflate
the marginal ROI, which is still ~0). If any wider config is ever pursued, the forward accrual gate —
not this backtest — is the arbiter.
