# CONSOLIDATE-AND-IMPROVE — Cycle 8 (beat-best-trader)

**UTC: 2026-07-06T21:55:41Z** · branch `run/beat-best-trader` · PAPER-ONLY · adopts/arms/promotes
NOTHING · no Rust/migration edits · DB read-only · cost-zero (Max-only).

Goal: take everything built across prior cycles and apply it to make the frozen STANDARD (the
favorite-tilted consensus champion) genuinely better — **only** adopting a challenger that BEATS the
champion out-of-sample on the realizable metric AND clears the belief-blind gate, via
`scripts/standard_guard.py` + `scripts/consolidate_challengers.py`. **Never manufacture a win.**

## Champion reference (live, this run)
- **realizable edge** (band-aware tax, event-clustered, `initial_market_price` basis): **+4.92%** over 139 events.
- **belief-blind** (`selection_null`, favorite arm): 164 ev · surplus +7.7% · **LB +4.69%** · p_emp 0.000 · 3 non-soccer regimes+ · SELECTION-REAL · `--calibrate` **PASS**.
- **resolved-P&L** (canonical ledger): +2.43% over 241 bets (decaying, World-Cup front-loaded — unchanged).
- Regression status: **HEALTHY** (LB +4.69% > 0 floor).

## Ranked challenger table (realizable-edge Δ vs champion, 90% event-bootstrap CI)

| # | challenger | belief-blind evs | realizable | Δ vs champ | Δ CI90 | belief-blind p | **verdict** |
|---|---|---:|---:|---:|---|---:|---|
| 1 | reliable-weighted (reliable-backed subset) | 13 | +9.20% | **+4.28%** | [−19.3%, +25.0%] | — (underpowered) | **INDETERMINATE-BY-POWER** |
| 3 | mid-band consensus, combined book | 323 | +1.01% | −3.91% | [−10.9%, +3.5%] | 0.001 | **CHAMPION-STANDS** |
| 2 | backer-quality (clean-directional screen) | 11 | −13.86% | −18.79% | [−54.1%, +11.4%] | — (underpowered) | **INDETERMINATE-BY-POWER** (leans REFUTED) |
| 4 | CLV-exit overlay | (overlay) | mean −1.0…−1.6% vs hold | negative | — | n/a | **REFUTED** (hold > exit for favorites) |
| 5 | conviction-weighted sizing overlay | (overlay) | log-growth +0.21 | (single path) | — | n/a | **PRE-REGISTER** (drawdown doubles) |

**No challenger ADOPTS. The champion STANDS, unchanged.** This is the honest, expected outcome on
~8 correlated days — most subset challengers are power-starved by construction.

---

## Per-challenger findings

### 1. Reliability-weighted consensus → INDETERMINATE-BY-POWER (structural obstacle)
Concentrating the favorite arm on events with ≥1 durably-reliable backer (the `reliability_score`
skill pool: cal_gap>0, per-wallet null p≤0.05, directional) leaves only **13 of 164** favorite events.
Realizable +9.2% (Δ +4.28%) looks good but the CI is **[−19.3%, +25.0%]** — indistinguishable from
noise. **Root cause (a real finding):** the durably-reliable traders our instrument can score from
`trader_fills` are **near-disjoint** from the wallets that actually back the favorite consensus
signals (shortlist overlap = 0 events; broad skill-pool overlap = 13 events). We cannot "concentrate
on reliable backers" because the reliable population and the backer population barely intersect. Not
adoptable now; pre-registered as a forward candidate that only becomes testable once enough
reliable-backed favorite events accrue (months).

### 2. Backer-quality screen → INDETERMINATE-BY-POWER, leans REFUTED
Screening favorite events to those whose backer pool is **majority-directional** (drop
MM/bot-dominated, reusing the `trader_scorecard` MM + bot flags) keeps only **11 of 164** events, and
that clean subset is realizable **−13.9%** (Δ −18.8%, CI [−54%, +11%]). Striking finding: ~93% of
favorite events have backer pools our MM/bot screen flags as majority non-directional. The favorite
consensus edge appears to **ride on** high-volume / MM-flagged wallets, not despite them; removing them
destroys both the edge and the sample. (Caveat: the MM screen was built to exclude two-sided rebate
capture, and may be mis-targeted for this population — but either way the screen does **not** clean the
signal.) Champion stands; do not apply the screen.

### 3. Mid-band consensus add-on → CHAMPION-STANDS (the classic selection≠realizable trap)
CONSENSUS (`strict`) restricted to band 0.35–0.65 is **marginally selection-real** (229 ev, surplus
+4.0%, p_emp 0.041, LB +0.20%, 4 non-soccer regimes+) **and beautifully uncorrelated** with the
favorite standard: **day-return correlation = 0.05** over 8 days — the diversification thesis is
directionally supported. **But** the mid-band stream is realizable **−2.0% after the band-aware tax** —
a positive *selection surplus* that does **not** survive as *realizable P&L* (exactly the pattern that
made the standard `favorite`-only, and that the retired arms exhibit). Adding it therefore **dilutes**
the standard: combined book realizable **+1.01%** (Δ **−3.91%**, CI [−10.9%, +3.5%]) vs champion +4.92%.
An uncorrelated diversifier with no realizable edge diversifies nothing worth having. Champion stands.
**Pre-registered forward idea:** mid-band consensus becomes an interesting diversifier **only if** its
realizable tax can be cut (see §6) into positive territory — the low correlation makes it the best
diversification candidate we have *if* the realizable problem is solved.

### 4. CLV-exit overlay → REFUTED in-sample
Exiting favorite positions when the market moves in our favor by a CLV target (0.03 / 0.05 / 0.08),
vs holding to resolution, over 284 favorite events with an observed later mid: at **every** target
early-exit **lowers** mean return (−1.6% / −1.3% / −1.0%), barely changes variance (Δsd ≈ −0.005), and
slightly **raises** max drawdown. Economically sensible: for **favorites** (high win-prob) the full
(1−entry) resolution payoff dominates a small locked CLV move — you should **hold**, not scalp. (Caveat:
`last_market_price` is a single late snapshot, not a full trajectory — a rough proxy — but the direction
is robust.) The champion's hold-to-resolution posture is correct. Discarded.

### 5. Conviction/edge-weighted sizing overlay → PRE-REGISTER (not adoptable; single path)
Sizing favorite bets 1%→3% by `net_quality` conviction (cap 3%) vs flat 1%, over the resolved sequence:
final wealth 1.448 vs 1.173, **log-growth +0.21**, Calmar 5.49 vs 4.09 — **but max drawdown doubles**
(8.2% vs 4.2%). This is on the **same selection**, so it is **leverage, not a selection edge**; it
cannot clear the belief-blind gate (guard requires it) and is measured on a **single 8-day path** with
no CI and obvious ruin exposure. Promising as a compounding overlay but must be forward-evaluated with a
block-bootstrap CI + explicit ruin analysis before any belief. **Pre-registered**; not adopted.

### 6. Entry-timing / tax reduction → the HIGHEST-LEVERAGE next improvement (DEFERRED — live change)
From the standing instruments (`real_tax.json`, `dense_capture_diag.json`, `clv_lambda_marketkey.json`):
the standard's realizable +4.92% is scored at a **conservative band-aware tax (~2.3¢ avg)**, but the
**measured real follower tax is ~1.0–1.3¢** — roughly half. Favorite CLV is realizing **positively**
(+1.3¢, CI [+0.6, +2.1], z=3.5). Dense at-open capture (fix already spec'd in `dense_capture_diag.json`)
recovers ~84% of post-dense signals and lifts trajectory coverage **12.6×**. Cutting entry tax from
~2.3¢ to ~1.0¢ adds ≈ +1.5–2% realizable to the **champion's own** edge (≈ +6.5–7% realizable at the
real tax). This is a **measurement/capture** lever on the champion, not a new strategy — and it is a
**LIVE capture change → DEFERRED to human review** (no Rust/config edits in this run). It is also the
key that could rescue the uncorrelated mid-band stream (§3) into a real diversifier.

---

## Decision & disposition
- **Champion UNCHANGED** (`reports/baseline_champion.json`, `STANDARD-BASELINE.md` not modified). No
  challenger beat it on the realizable metric while clearing the belief-blind gate.
- **Pre-registered forward challengers** (do NOT adopt; accrue then re-judge through the guard):
  (1) reliability-weighted consensus — blocked on reliable-backer accrual;
  (3) mid-band consensus as an uncorrelated diversifier — blocked on realizable tax;
  (5) conviction-weighted sizing — blocked on a multi-path CI + ruin analysis.
- **Discarded:** (2) backer-quality screen (kills the edge); (4) CLV-exit (hold beats exit for favorites).
- **Single highest-leverage next improvement:** dense at-open capture to cut the entry/follower tax
  (§6) — it lifts the champion's realizable directly and could turn the uncorrelated mid-band stream
  into a genuine diversifier. It is a live change → **DEFERRED to human review**.

## Honest bottom line
Nothing beat the champion at current power — as expected on ~8 correlated, World-Cup-front-loaded days.
The value delivered is a **ranked, CI'd, pre-registered improvement pipeline** and two clean refutations
(CLV-exit; backer-quality screen), not a forced upgrade. The champion stands, healthy (LB +4.69%),
still **not real-money eligible** (binding constraint unchanged: non-expiring regime persistence over
months). Reproduce: `python3 scripts/consolidate_challengers.py` → `reports/consolidate_challengers.json`.
