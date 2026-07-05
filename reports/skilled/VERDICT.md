# VERDICT — "Identify the Genuinely Skilled"

**Bottom line, unhedged:** No signal identifies copyable skilled traders ex-ante today. Every
past-performance ranking is REFUTED again on the 2.47M-fill snapshot; every ex-ante structural
attribute fails to generalize across traders; the one signal that is genuinely REAL — round-trip
**timing** skill (persists ρ=0.62) — is a market-making mechanism a taker-follower **cannot
copy**. The single lead with a positive, forward-shaped point estimate is **CLV**, and it is
**power-limited** (36 wallets, CI includes 0). **Identification of copyable skill requires
months of forward CLV accrual; no retrospective signal suffices.** Nothing is promoted; all arms
silent/paper. This is the honest, pre-registered outcome — not a certified winner, and a
"it works" here would have been a failure.

## SURVIVED / REFUTED / INDETERMINATE

| Class | Signal | Verdict |
|---|---|---|
| Past PnL | blind-surplus, ROI, success-rate | **REFUTED** (frozen wall, WS-0.2) |
| Reduced-variance | sign-consistency, EB-shrinkage, calibration-slope | **REFUTED** (WS-2) |
| Structural ex-ante | 6 attributes, out-of-cohort | **REFUTED** (WS-3) |
| Timing (round-trip PnL persistence) | — | **REAL but UNCOPYABLE** (WS-4) |
| Timing → copyable direction (selector) | — | **INDETERMINATE-BY-POWER** (ρ=0.29) |
| **CLV** (tape-derived) persistence | — | **INDETERMINATE-BY-POWER** (ρ=0.27) — the lead |
| CLV → copyable direction | — | **INDETERMINATE-BY-POWER** (ρ=0.14) |

**Survivors of the pre-registered gate: zero.** With no gate-clearer across ~13 signals, the
label-permutation / orthogonality multiplicity tests are moot (the family produced fewer
survivors than chance would). The two positive leans (CLV, timing→direction) sit *below* the
certification bar, not above it.

## The one methodological unlock (worth keeping)
**CLV need not wait for a new price-capture daemon.** The tracked-trader fill tape is itself a
price feed: `closing_line(cond,outcome) = avg fill price in the last 20% of a market's fill-life`
(≥5 late fills, from OTHER traders), and `CLV = closing_line − entry_price` on the BUY. This is
cost-zero, needs no external API, no deploy surface, and **accrues forward for free** as fills
ingest. Fleet mean CLV ≈ −0.004 (sanity: closing ≈ entries on average — no units bug). Instrument
lives at `scripts/skilled/ws1_clv.py`; re-run to read accrual.

## Forward-CLV ETA (the exact N/weeks still needed)
Pre-registered gate: `CLV_lo>0 forward, ≥50 events/window, ≥2 disjoint windows`, over a cohort
large enough for a persistence test (≥~20 wallets). Current depth (non-MM, both halves):

| CLV-events/half threshold | wallets clearing |
|---|---|
| ≥10 | 36 |
| ≥20 | 13 |
| ≥30 | 6 |
| ≥50 | **2** |

Binding constraint = per-wallet CLV-event depth in **time-separated** windows. To reach a
≥20-wallet persistence test at ≥50 events/window is ~5× current depth → **on the order of 3–6
months** of continued fleet capture (matches the mission's stated expectation). No shortcut:
the tape must simply accumulate.

## WS-0.1 — churn classifier swap (code; GATED; HELD for deploy)
`classify_trader_types` swapped from the 92%-wrong `fills/day ≥ 400` rule to the pre-registered
**churn ≥ 0.70** metric (`Σ 2·min(buy_sh,sell_sh)/Σ(buy_sh+sell_sh)` per market).
- Read-only validation on live DB: **26 wallets** flagged MM (was 115 under fpd); **108**
  formerly-mislabeled directional traders restored — matches the pre-registered ~25 / ~100.
- `cargo clippy -p polymarket-common -- -D warnings`: **GREEN**.
- Blast radius: `trader_type` is advisory; the router arm ALSO applies the position-grain
  microstructure screen, and the churn set ⊆ that screen, so router membership is ~unchanged —
  the swap corrects the advisory label, it does not move live selection.
- **HELD off `main`** on branch `feat/identify-skilled`. **`main` auto-deploys on HEAD advance**
  (`.autoupdate.log` live). Deploy consequence if merged: on the next `backfill` cycle,
  `classify_trader_types` recomputes `trader_type` (26 bots vs 115), a one-shot advisory
  reclassification; no live-alert-path change. **Tue's call to merge** — not auto-deployed by
  this run.

## Kill-criteria honored
Every claimed signal was judged belief-blind, event-clustered, leak-free, out-of-cohort where
applicable, against the aggregate/fleet baseline. Positive point estimates that failed to exclude
0 were labeled INDETERMINATE-BY-POWER, never "works." The frozen null (WS-0.2) prevents any
future run re-opening past-PnL ranking. Real money stays gated.
