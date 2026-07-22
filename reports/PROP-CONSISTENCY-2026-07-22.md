# PROP LOGICAL ARBITRAGE — the deepest confirmation of THE TOLL

2026-07-22. Digging into the self-collected tape for an edge that does NOT depend on the discarded
external archive. Found a genuinely new class of signal — and the most decisive negative in the
project's history.

## The data we actually have (answering "is this a month?")

**No — the trustworthy record is 9 days.** Provenance split, verified this session:

| source | window | rows | who collected it |
|---|---|---|---|
| `us_time_sales` (the +1.52% basis) | 06-24 → 07-13 | 20 files | **external portal** |
| `us_daily_market_report` | 2025-10-30 → 07-13 | 321k | **external portal** |
| **`us_mid_tape`** | **07-13 → 07-22** | **16.7M** | **us (dense WS)** |
| `us_book_depth` | 07-19 → 07-22 | 403k | us |
| `favband_paper_signals` | 07-19 → 07-22 | 118 | us |

Everything from 07-13 is ours, provenance-controlled. The 16.7M-row mid tape is far richer than the
118-signal FAVBAND ledger I had been reasoning from, so I mined it directly.

## The new idea: arithmetic, not statistics

The venue lists logically NESTED markets on one player-game:
`astatc-mlb-{away}-{home}-{date}-{stat}-{player}-gte{N}`. **7,348 such markets**, 9 stats, multiple
thresholds each. They are bound by arithmetic the pricing engine can violate:

- **within a stat:** P(TB≥4) ≤ P(TB≥2) — monotonicity.
- **across stats:** a home run IS 4 total bases, so P(HR≥1) ≤ P(TB≥4) — implication.

A violation is not a forecast — it is a bet that arithmetic holds. Risk-free if both legs fill and
settle consistently. This is the strongest form of edge there is, and it owes **nothing** to the
contaminated data.

## The violations are real — and decay perfectly with depth

Across 8,085 within-stat threshold comparisons: **5.79% violate mid-monotonicity.** The engine is
frequently inconsistent. But the violation rate is a clean monotone function of how much money rests
in the book:

| tradeable size | comparisons | mid-violation rate |
|---|---|---|
| <$1 (dust) | 2,805 | **9.16%** |
| $1–10 | 2,290 | 6.07% |
| $10–50 | 1,084 | 4.61% |
| $50–200 | 545 | 3.49% |
| **≥$200** | 1,378 | **0.22%** |

**The mispricing lives exactly where the money is not.** A deep book is a policed book.

## The decisive table: net of the taker fee

Locked arb: buy the underpriced implied leg YES, buy the overpriced leg NO. Worst-case payoff is
exactly 1, so `net = (bid_sub − ask_sup) − fee_sup − fee_sub`, fee = `0.05·p·(1−p)` per leg.
`prop_consistency.py --historical`:

| book depth | arbs | avg gross | avg net | net>0 |
|---|---|---|---|---|
| <$10 | 19 | +3.74¢ | +1.93¢ | 13 |
| $10–50 | 1 | +20.00¢ | +17.61¢ | 1 |
| $50–200 | 1 | +1.00¢ | −0.74¢ | 0 |
| **≥$200 (tradeable)** | **4** | **+2.00¢** | **−0.10¢** | **0** |

**Every locked arb at tradeable size nets ≤ 0.** The single +17.6¢ case is one near-abandoned $10–50
book. Net-positive arbs exist only in dust.

And the ≥$200 population is essentially **one player-game**: Kyle Schwarber, 2026-07-20, HR≥1 bid
0.31 vs TB≥4 ask 0.29 — a real 2¢ inversion in a $2,825 book with 9k+ shares a side. The fee is
2.1¢. It nets **−0.1¢**. The venue's fee sits exactly at the boundary of its own pricing error.

**This is THE TOLL, proven on risk-free arbitrage.** If a free arb cannot clear the fee at size, no
statistical premium ever will. It is the same wall FAVBAND hit, the same wall every prior arm hit —
now demonstrated on the strongest edge that can exist. The consistency of that result across five
years of arms is itself the finding.

## The one live angle — and its catch

Violations mean-revert: the underpriced leg rises toward the overpriced one. Measured against the
universal pre-game sharpening as a control, violations correct **~13.6¢ more** than baseline drift
(t≫3, p<1e-4 on the within-stat set). Real exploitable structure exists.

But:
1. **As a TAKER you cannot profit** — the fee eats it, as proven above.
2. **At size it is n=2–3** — the correction is measured almost entirely in thin books.
3. **As a MAKER (fee = 0) you theoretically could** — but you cannot *take* an existing
   inconsistency as a maker. You post into it and hope both legs fill, which reintroduces legging
   risk and adverse selection.

## The strategic reframe this produces

Every taker edge on this venue dies to the ~2–4¢ round-trip fee. That is now proven all the way down
to free arbitrage. Two structural escapes remain, and only two:

1. **Be a maker.** Props have wide spreads (median ~4¢, far wider than the 1¢ favourite books) and
   zero maker fee. A maker who posts inside the spread with even a slightly-better-than-market fair
   value collects the spread the takers cannot. The logical structure here (mean-reverting
   violations) is exactly the kind of signal a maker fair-value model would exploit.
2. **Have genuine information** — know the outcome better than the market before it converges.

**Both point at the same missing piece: a prop fair-value model.** And one already exists in this
account — **Foresight**, the CS2/baseball player-prop ML. The synthesis worth testing is
*Foresight's fair value driving a maker strategy on Polymarket US prop markets* — the one
construction where the model's edge is collected at zero fee instead of being taxed away. That is a
cross-project bet, not a favband tweak, and it is the first direction in this project that isn't
fighting the toll head-on.

## What shipped

- `scripts/prop_consistency.py` — self-building, self-testing (9 implications × 7 worked box scores,
  fee model, the fee-eaten Schwarber case). `--historical` rebuilds `prop_map`/`prop_q2` from the
  tape and prints the net-of-fee-by-depth table. Fails LOUD on an empty/absent tape.
- This report.

## What did NOT ship, deliberately

A live taker scanner. The historical result says a taker cannot win here, so shipping one would be
building an instrument to lose money slowly. The next instrument, if this direction is pursued, is a
MAKER fair-value + posting harness — and that is a design decision, not a mechanical build.
