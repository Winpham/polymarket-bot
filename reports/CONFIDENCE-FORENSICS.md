# Confidence Forensics — were we ever *confidently* profitable, and does the collapse edge escape the pattern?

**Branch `feat/confidence-forensics` (~/polymarket-bot). Paper/analysis only. No order placed. Ever.**
Run 2026-07-15. Predecessor context: `reports/GO-LIVE-READINESS.md`,
`project-polymarket-collapse-avoidance`, `REPORT-COPY-EDGE-HARDENING.md`, `reports/clv_lambda*.json`.

## Verdict (up front)
**We were never confidently profitable, and the collapse model — the one arm that looked
categorically different — is not the exception. It is verdict C: a variance / favourite‑longshot
premium, not information.** Under a proper walk‑forward its celebrated +4.14% intl edge is ~+1.3%; its
λ (information fraction) is **0.000, CI [0.00, 0.14]** at 94% coverage; and out of time **the market's
own price forecasts better than the model** (Brier 0.0784 < 0.0811). On the venue we actually trade,
settled on the **official** regulatory report, it is **negative** (model −4.15%; blind −7.45%; US
favourites overpriced 6.4pp). The single‑split +4.14% and "beats‑the‑market‑Brier" were the same
optimism artifacts that have killed every prior arm.

This is a NO. Per the run's own terms, a well‑evidenced NO is the deliverable; the only failure would
be a fabricated YES.

---

## PHASE 1 — the confidence ledger: what was ever real?

| claim | rested on | what it actually is now |
|---|---|---|
| champion `favorite` +2.85% belief‑blind LB | one A/B split, 4 benign WC days | **VARIANCE / INDETERMINATE.** λ̂≈0.14–0.20 but CI [0.07, 0.62] and **only 16% CLV coverage** ⇒ not even measurable. Sizing engine parks it at **k=0** on purpose. "Profitable" was always the wrong word. |
| `favorite_v2` +7.63% | tournament window | **ARTIFACT.** ruled not‑bankable (tennis/tournament); fails the durability bar. |
| copy‑trading edge | leaderboard PnL | **RETRACTED** → INDETERMINATE, net ~+1.5¢ CI spans 0. |
| market‑making | subsidy math | **KILLED** ($0‑falsified + US‑ToS‑blocked). |
| per‑sport / cross‑market / latency / discovery | various | **RETRACTED** (0/7, 0 cells, p=0.36, my error). |
| **collapse model +4.14%** (the felt‑confident one) | **one A/B split + one model fit** | **this run: VARIANCE (λ=0), ⅓ magnitude on walk‑forward, negative on US.** See Phases 2–4. |

**Answer to "were we ever confidently profitable?": No.** Every positive number rests on a single
split or a benign window, and the one arm with a well‑measured information test (this run, the collapse
model) reads λ=0. The frame is therefore *establish for the first time*, not *recover*.

---

## PHASE 2 — the crux: the US absolute is MEASURABLE, and it is negative

### "Unmeasurable" was a data gap, not a law
The predecessor settled US markets by **rounding the T&S last price** (validated on 2 local DMR days)
and called the absolute "unmeasurable, could be ~0." But the **full official regulatory Daily Market
Report** was backfilled into `us_daily_market_report` on **2026‑07‑14 05:19 UTC**
(`source=regulatory_dmr`): 100% settlement coverage, **2025‑10‑30 .. 2026‑07‑13**, 321,743 rows.
Terminal settlement = `business_date = maturity_date` (57,011 symbols; 96% of the `aec-` game‑winner
universe is a clean {0,1}). The T&S price‑path symbols join to it exactly. Tool:
`scripts/niche/us_dmr_backtest.py` (forks `us_native_backtest.py`; byte‑identical features/paths, label
swapped to the official DMR number).

### Result — frozen model on real US paths, OFFICIAL settlement (06‑24..07‑13, curated, event‑clustered)
| policy | ROI/turn | 95% CI | events |
|---|---|---|---|
| BLIND every US favourite | **−7.45%** | [−10.80, −4.35] | 884 |
| MODEL EV>+0.01 | **−4.15%** | [−10.64, +1.72] | 265 |
| MODEL EV>+0.03 | −4.40% | [−10.64, +1.65] | 251 |

### The settlement‑bias excuse, refuted on the SAME symbols
| label | model EV>0.01 ROI | agreement vs DMR |
|---|---|---|
| **OFFICIAL DMR** | **−4.15%** | — |
| T&S maturity‑round (predecessor default) | −4.01% | **99.0%** |
| T&S strict 0.95/0.05 | −4.81% | 99.6% |

The distrusted inferred label agreed with the official truth **99%** of the time and moved the answer
**0.14pp** — not the gap between negative and positive. **The negative was real; "unmeasurable" was the
comfortable framing of "measurably bad."** (Textbook `feedback-measure-costs-not-just-edges`: a soft
word silently decided the verdict.)

### Why: US favourites are genuinely overpriced (clean calibration, official labels)
932 first‑cross favourite entries: mean price **0.829**, win rate **0.765** → **overpriced 6.4pp**,
worsening with price ([0.80,0.85) +2.7pp on 726 entries; ≥0.95 a noisy transient‑spike tail). The
model's selection recovers ~3.3pp of the blind −7.45% but cannot cross zero — the overpricing exceeds
the edge.

**Caveat (not buried):** the US price tape is only 2026‑06‑24..07‑13 — a World‑Cup‑dominated 3‑week
window. DMR settlement reaches to Oct 2025 but we hold no US price paths before 06‑24, so the US
measurement can't yet be checked out‑of‑window. The negative is clean *for this window*.

---

## PHASE 3 — matched transfer: intl vs US, same window, same frozen model

True event‑matching needs the full `us_mapper` offline (ISO↔FIFA codes, tennis name‑matching); the 58
live `cross_venue_basis` pairs join to **zero** settled sports markets in‑window, so event‑matching was
out of scope here. Instead: the **frozen model on both venues over the same calendar window** (the
cleanest test available without the mapper build). The result is the whole run in one line:

| evaluation | ROI (EV>0.01) | note |
|---|---|---|
| intl, **in‑sample** (frozen model trained on these markets) | **+7.44%** | optimism ceiling |
| intl, **out‑of‑sample** (walk‑forward, Phase 4) | **+1.34%** | the honest intl number |
| **US, out‑of‑sample** (frozen, official DMR) | **−4.15%** | the realizable venue |

**Confidence evaporates at every step: in‑sample +7.4% → OOS +1.3% → realizable venue −4.2%.** The
attenuation the predecessor saw (3¢→1¢) is real and then some: on the venue we trade, the sign flips.
(The +7.44% is *in‑sample* and must not be read as an intl edge — it is the artifact, shown on purpose.)

---

## PHASE 4 — the decisive test: is the intl collapse edge information or variance?

`scripts/niche/collapse_lambda_wf.py` — same intl data as the certified result (76,551 pts / 10,857
markets, `harvest_fills` paths, `trader_fills` settlement), three tests, market‑clustered.

### A) Walk‑forward (4 expanding folds, each test block strictly later than its training)
| fold | train mk | blind ROI | model ROI | 95% CI | p | AUC |
|---|---|---|---|---|---|---|
| 1 | 2,171 | −1.28% | +1.24% | [−0.50,+2.86] | 0.076 | 0.772 |
| 2 | 4,343 | −1.09% | +1.69% | [−0.18,+3.48] | 0.037 | 0.782 |
| 3 | 6,514 | −1.08% | +2.00% | [+0.06,+3.85] | 0.022 | 0.770 |
| 4 | 8,686 | −1.47% | **+0.46%** | [−1.58,+2.47] | **0.326** | 0.797 |
| **pooled** | | −1.23% | **+1.34%** | **[+0.40,+2.25]** | **0.003** | |

Survives — all folds positive, pooled p=0.003 — but at **~⅓ the certified +4.14%**, and the most‑recent,
most‑trained fold 4 is **insignificant** (+0.46%, p=0.33). The +4.14% single‑split overstated ~3×.

### B) λ — information vs variance (94.4% forward‑close coverage — well measured, unlike the champion's 16%)
```
mean surplus (won−entry)   = +0.0160
mean CLV     (close−entry) = −0.0029   95% CI [−0.0091,+0.0033]   p(CLV≤0)=0.81
residual     (won−close)   = +0.0189   (variance / static premium)
λ̂ = CLV/surplus            =  0.000    95% CI [0.000, 0.141]
```
**The market never moves toward the model's picks** (CLV ≈ 0, slightly negative — consistent with
entering at a self‑inflated taker print, the follower‑tax mechanism). The **entire** surplus is
residual. **λ CI lower bound = 0 ⇒ by the run's own kill condition, this is variance, not an edge —
size nothing.** Same disease as the champion (λ≈0.14), but now *confidently* diagnosed rather than
indeterminate.

### C) Brier‑beat, out of time — FAILS
Pooled OOS model‑selected: **model Brier 0.0811 vs market‑price Brier 0.0784 → the market wins.**
Reference control (same code, single A/B split): model **0.0854 < 0.0879 → model beats market.** The
only change is single‑split → walk‑forward. **The "beats the market Brier" signature was an overfit
artifact** — exactly the leak signature the run was told to distrust. (The single split also reproduces
the certified net +1.57¢/share, so this is not a pipeline bug: the split reproduces the claim; the
walk‑forward breaks it.)

---

## PHASE 5 — the systematic pattern, named

Every arm dies the same way. **Confidence is manufactured by three evaluation shortcuts and evaporates
when each is removed:**

1. **Single split / benign window → walk‑forward.** favorite (4 WC days), favorite_v2 (tournament),
   ITER‑5 (+1.58% split → −2.75% WF), and now collapse (+4.14% → +1.34%). A single split is an
   in‑sample‑flavoured number.
2. **Mean ROI → information (λ).** A positive mean is not an edge if the market never confirms it.
   champion λ indeterminate; collapse λ=0. Both are variance / favourite‑longshot premium harvesters.
3. **Backtest price → realizable venue price.** exec‑policy ("selection exhausted at the realizable
   price"), the measured‑cost graveyard, and now US (−4.15% at the official settlement, favourites
   overpriced 6.4pp).

### The standing certification bar (nothing gets sized until it clears ALL four)
1. **Walk‑forward‑stable:** ≥3 expanding folds, pooled ROI LB > 0, no fold materially negative — NOT a single split.
2. **Information, not variance:** λ (CLV/surplus) **CI lower bound > 0** at ≥50% trajectory coverage.
3. **Beats the market out of time:** model Brier < market‑price Brier on pooled OOS.
4. **Positive at the realizable venue ask:** ROI LB > 0 on the venue we trade, settled on official data.

The collapse model clears **only #1**. The champion clears **none** (fails #2 by measurement, #4 by k=0).

---

## PHASE 6 — resolution: verdict C

**C) The collapse edge is variance, not information — same disease as the champion.** Its single‑split
+4.14% and Brier‑beat were optimism artifacts; walk‑forward leaves a small (+1.34%) variance premium
with λ=0; and on the realizable US venue it is negative because US favourites are overpriced beyond
what the selection recovers. **We have never had a confident, information‑bearing edge.**

### The pivot (what to actually do)
1. **Do not size the collapse model.** λ LB=0 and US<0 both trip the bar. Keep k=0.
2. **Reframe the forward test, don't kill it.** `collapse_forward.py` is cheap and already running,
   but its success bar (ROI>0 over ≥60 events) can be met by *variance* and would then revert. **Add
   the λ/CLV‑positive and Brier‑beat conditions to its gate** so it can only pass on information, not a
   lucky forward stretch. It is a monitor, not a go‑live path, until λ>0 appears.
3. **The honest search is for a λ>0 signal.** Nothing in the graveyard has one. Either find a
   genuinely anticipatory signal (the market moves to confirm it) — the collapse mechanism, being
   structural not predictive, is unlikely to be it — or accept that at our realizable price this market
   is efficient and stop sizing. The intl book carries a small variance premium; the US book does not
   even carry that.
4. **US‑native is not a rescue.** The US absolute is negative on official data; a US‑trained price‑path
   model would be learning the same variance premium on a book where it is negative.

### Kill‑conditions honoured
- λ CI lower bound ≤ 0 ⇒ not an edge → **honoured** (collapse λ=[0,0.14]; nothing sized).
- Walk‑forward mean ≤ 0 ⇒ retract → intl WF is +1.34% (not ≤0), so the intl *premium* is not retracted,
  but it is reclassified variance, not information.
- No fabricated YES → **honoured**; the answer is C, delivered with its evidence.

---

### Artifacts
- `scripts/niche/us_dmr_backtest.py` — clean US absolute on official DMR settlement (+ bias A/B).
- `scripts/niche/collapse_lambda_wf.py` — walk‑forward + λ + Brier‑beat on the intl collapse model.
- `reports/niche/.collapse_wf_cache.pkl` — per‑decision‑point cache (adds decision ts + forward close).
All `psql` via the pinned docker‑exec helper (`ON_ERROR_STOP`, parallel workers off — the DB serves the
live bot). No order path touched.
