# Confidence Forensics — were we ever *confidently* profitable, and does the collapse edge escape the pattern?

**Branch `feat/confidence-forensics` (~/polymarket-bot). Paper/analysis only. No order placed. Ever.**
Run opened 2026-07-15. Predecessor context: `reports/GO-LIVE-READINESS.md`,
`project-polymarket-collapse-avoidance`, `REPORT-COPY-EDGE-HARDENING.md`.

> The spawning question was *"why aren't we confidently profitable like we were, and fix it."* The
> premise "like we were" is tested, not assumed. **Bottom line so far: we were never confidently
> profitable, and the one place the story looked strongest — the US book we actually trade — is now
> cleanly measured and is NEGATIVE.**

---

## PHASE 2 (done first — it's the crux): the US absolute is MEASURABLE, and it's negative

### The reframe: "unmeasurable" was a data gap, not a law
The predecessor concluded the US absolute edge is "unmeasurable retrospectively" because it settled
markets by rounding the **T&S last price** (validated on only 2 local DMR days). But the **full
official regulatory Daily Market Report** was backfilled into `us_daily_market_report` on
**2026-07-14 05:19 UTC** (`source=regulatory_dmr`), 100% settlement coverage for
**2025-10-30 .. 2026-07-13** (321,743 rows). Terminal settlement = the row where
`business_date = maturity_date`: 57,011 symbols, 96% of the game-winner (`aec-`) universe settles a
clean binary {0,1}. The T&S price-path symbols join to it exactly (`aec-mlb-stl-chc-2026-07-03`).

So we can settle the US backtest on the **official number**. Tool: `scripts/niche/us_dmr_backtest.py`
(forks `us_native_backtest.py`, byte-identical features/paths, label swapped to official DMR).

### The result — frozen model on real US price paths, OFFICIAL DMR settlement
Window 2026-06-24 .. 07-13 (the full US T&S tape we hold), curated to standard liquid game markets,
one decision point per market, US fee θ=0.06·p(1−p) + 0.5¢ ask haircut, **event-clustered**:

| policy | ROI/turn | 95% CI | p | events |
|---|---|---|---|---|
| BLIND every US favourite | **−7.45%** | [−10.80, −4.35] | 1.000 | 884 |
| MODEL EV>+0.00 | −3.46% | [−9.32, +2.22] | 0.879 | 282 |
| MODEL EV>+0.01 | **−4.15%** | [−10.64, +1.72] | 0.911 | 265 |
| MODEL EV>+0.03 | −4.40% | [−10.64, +1.65] | 0.922 | 251 |

Per-sport (model EV>0.01): soccer +2.09% (15 ev, p=0.39 — noise), tennis −4.22%, esports −5.54%.

### The settlement-bias excuse is refuted directly (A/B on the SAME symbols)
| settlement label | model EV>0.01 ROI | agreement vs DMR |
|---|---|---|
| **OFFICIAL DMR** | **−4.15%** | — |
| T&S maturity-round (predecessor default) | −4.01% | **99.0%** |
| T&S strict 0.95/0.05 | −4.81% | 99.6% |

The inferred label the predecessor distrusted agreed with the official truth **99%** of the time and
moved the answer by **0.14pp** — not the gap between negative and positive. **The negative was real.
"Unmeasurable" was the comfortable framing of "measurably bad."** (This is exactly the
`feedback-measure-costs-not-just-edges` failure mode: a soft word — "unmeasurable" — silently decided
the verdict.)

### Why: US favourites are genuinely overpriced (clean calibration, official labels)
932 first-cross favourite entries: mean price **0.829**, mean win rate **0.765** → **overpriced 6.4pp.**
Worsens with price:

| entry band | n | mean price | win rate | overpricing |
|---|---|---|---|---|
| [0.80,0.85) | 726 | 0.807 | 0.780 | **+2.7pp** |
| [0.85,0.90) | 97 | 0.866 | 0.763 | +10.3pp |
| [0.90,0.95) | 52 | 0.916 | 0.789 | +12.8pp |
| [0.95,1.00) | 57 | 0.974 | 0.561 | +41pp (noisy tail — transient-spike entries) |

The heavy tail above 0.95 is a noisy blind-entry artifact (first-cross catches transient spikes), but
the **dominant [0.80,0.85) band is already +2.7pp overpriced on 726 entries** — robust. The model's
selection recovers ~3.3pp of the blind −7.45% (selection transfers, as the predecessor found) but
cannot cross zero: the overpricing is larger than the edge.

### Phase 2 verdict
**The US book, cleanly measured on official settlement, does NOT pay.** US favourites are overpriced
by more than the collapse selection edge can recover. This is verdict **B** territory (edge is
intl-side; US is not tradeable-profitable today) — pending Phase 3 (matched intl-vs-US) and Phase 4
(is the *intl* edge even information?).

**Caveat (stated, not buried):** the US price tape we hold is only 2026-06-24..07-13 — a
World-Cup-dominated 3-week window. The DMR settlement reaches back to Oct 2025 but we have no US price
paths before 06-24, so the US measurement cannot yet be checked out-of-window. The negative is clean
*for this window*; generalisation needs more forward US tape.

---

## PHASE 1 — confidence ledger (in progress)
## PHASE 3 — matched-event intl-vs-US (pending)
## PHASE 4 — λ + walk-forward on the collapse model itself (pending — the most important test)
## PHASE 5 — the systematic pattern (pending)
## PHASE 6 — verdict + standing certification bar (pending)
