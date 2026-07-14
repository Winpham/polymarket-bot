# Copy-Edge Hardening — the follower tax was a symptom; the disease is collapse

**2026-07-14. Branch `feat/copy-edge-hardening`. Paper/analysis only — no order placed, ever.**
Audits and extends `feat/follower-tax` (`FOLLOWER-TAX-ANATOMY.md`), which concluded copy-trading is
alive in the favourite band (+2.99¢/share, +2.62¢ over blind, p=0.005, 830 markets).

That conclusion **survives its audit but is superseded by a bigger one.** The copy edge is real, its
mechanism is not what was written down, and the mechanism turns out to be capturable **without the
roster at all** — on an 18× larger universe, on the venue we actually execute on.

---

## TL;DR

| claim carried in | what this run found |
|---|---|
| copy surplus in 80–100¢ is selection skill | **CONFIRMED, but re-mechanised.** It is not "picks winners" in general and not price composition — it is **collapse-avoidance**, the only channel a binary market leaves open. |
| the roster is load-bearing | **FALSE.** A roster-free market-feature model captures the **same magnitude** (+3.15¢ vs +3.68¢). The roster was a proxy. |
| sports-favourite cell was dead (+0.39¢, p=0.372) | **artifact of print-volume weighting.** Opportunity-weighted it is +3.68¢ (p=0.009); the roster-free model makes it +3.15¢ (p=0.001) on 686 markets. |
| edge lives on the intl venue only | the roster-free model needs **no wallet identity**, so it ports to the US regulatory price tape (`us_mid_tape`, 2.3M rows) — signal and execution on the **same book**. |

---

## 1. The audit: three instruments, each able to kill the claim

### 1.1 The surplus is not price composition (`surplus_decomp.py`)
Both legs pay `net = won − p − fee`, so the surplus decomposes with **no residual**:

> surplus = **Δ(won)** − Δ(price) − Δ(fee)

| cell | surplus | **Δ(won)** | Δ(price) |
|---|---|---|---|
| band 80–100¢ | +2.62¢ | **+2.73¢** | +0.11¢ |

The edge is Δ(won) — the roster's favourites **win more** at the **same price**. It is not entering
cheaper inside a 20¢ bucket. (My leading hypothesis going in — that the 20¢-wide "band" hid a
price-composition artifact — was **wrong**, and the decomposition is what proved it.)

### 1.2 It is not a "buy late" timing artifact (`timing_forensics.py`)
Copy and blind buy at the **same point in market life** (median life-fraction 0.95 for both).
Time-matching the blind leg *sharpens* the edge rather than killing it. So the edge is not "the
roster waits until the favourite is safe and blind doesn't."

### 1.3 The mechanism, exactly (`blind_weighting.py`)
**51,003 of 51,006 markets are binary with complementary prices** (verified: the two outcomes' mean
prices sum to ~1.0). So at any instant only one side can be ≥80¢, and under a tight time-match both
legs must be on the **same outcome**:

| time-matched blind, band 80–100¢ | Δ(won) |
|---|---|
| **same-outcome** prints (95%) | **+0.0000** — identically zero, as structure demands |
| **different-outcome** prints (5%, lead changes) | **+0.3126** — carries 100% of the effect |

> **The roster has exactly one edge channel: it does not buy the favourite that collapses.** Buying
> a ≥80¢ favourite is only expensive when you buy the side that is ahead and then loses. Everything
> the predecessor described — the follower tax, the headroom geometry, the pre-drift event study — is
> downstream of this single fact.

**A cost error the predecessor made, reported honestly:** it typed `sports θ = 0.03` into the fee
model while the repo's own verified figure is **0.05** (US taker 0.06) — the exact "untyped cost
constant" sin the run's own lesson (`feedback-measure-costs-not-just-edges`) names, this time biased
*in our favour*. Every number in this run is re-priced at the verified rate. It moves the level, not
the sign.

**A weighting fragility, also reported honestly:** per-*print*, the sports-favourite cell reads
+0.39¢ (p=0.372, dead); per-*opportunity* (≤1 blind entry per market-outcome, so a noisy lead-change
can't outvote a quiet favourite) it reads +3.68¢ (p=0.009). The verdict depends on the convention.
Per-opportunity is the correct one — a strategy places one order, not one per print — and §2 confirms
it on an independent universe.

---

## 2. The prize: capture it **without the roster** (`collapse_risk.py`, `collapse_robust.py`)

If the edge is collapse-avoidance, and collapse risk is predictable from **market features alone**,
the roster is decoration. It is.

**Model.** HistGradientBoosting win-probability on ≥80¢ sports decision points. Features are
**strictly backward-looking** (price, persistence above band, drawdown from running max, dip/flip
counts, drift, volatility) — leak-tested: **rewriting the tape's *future* changes no feature**, and
banned lookahead (`n_trades`, life-fraction, market-end) is excluded by construction. Train window A,
test window B (disjoint markets, verified 0 overlap), CIs **bootstrap-clustered on market**.

**Result (window B, out-of-sample, sports = the US-tradeable set, one entry per market):**

| policy | net ¢/share | 95% CI | p | markets |
|---|---|---|---|---|
| **Blind** — take every favourite | **+0.14¢** | [−0.47,+0.78] | 0.336 | 4,830 |
| **Model** — EV > +0.01 | **+3.15¢** | [+1.18,+5.02] | 0.001 | 686 |
| **Model** — EV > +0.03 | **+4.51¢** | [+1.92,+6.97] | 0.000 | 386 |

AUC(B) = **0.78**. Model **Brier 0.0854 beats the market price's 0.0879** at these decision points —
consistent with the follower-tax event study: a taker buy transiently inflates the print, and the
model discounts it.

**It survives every adversarial check** that has killed a prior strategy in this repo:

- **R1 price caliper** — at a *fixed price* (±1–2¢, same market+outcome), the model still beats blind
  by +0.21¢ (p=0.001). Win-probability skill, not a price sort.
- **R2 one decision point per market** — kills DP-count weighting; the result **strengthens**.
- **R3 temporal** — A/B disjoint; win-rates 0.898 vs 0.895 (no regime break).
- **R4 ablation** — drop every clock-ish feature (`elapsed`, `staleness`, `n_prints`); AUC 0.77, edge
  holds +1.61¢ (p=0.002). Not a clock leak.

**The magnitudes reconcile.** Roster (opportunity-weighted sports) **+3.68¢** ≈ roster-free model
**+3.15¢**. The roster was a proxy for collapse-avoidance; the model is the thing itself, and it comes
with three structural advantages the roster can never have:

1. **18× the universe** — 43,731 untruncated markets vs the roster's 2,360.
2. **No capacity ceiling from signal count** — every market is a candidate, not 7.8/day.
3. **Native US execution.** The US venue publishes no wallet history, so a roster **cannot** be built
   there retrospectively — but a price-path model needs no identity. `us_mid_tape` already holds
   **2.3M** per-instrument US price rows. Signal and execution collapse onto the **same book**.

---

## 3. Status and the pre-registered next steps

**CANDIDATE, not certified.** The mechanism is understood, the cost model is measured not assumed,
and the edge is roster-free and leak-checked. What is *not* yet done, in priority order:

1. **Port the model to US prices.** Every number here is on the **international** tape. Rebuild the
   backward-looking features from `us_mid_tape` / the statutory Time & Sales tape (no identity
   needed — this is why the roster-free framing matters), settle on the Daily Market Report, price at
   the US taker fee (θ=0.06) **plus the measured 0.5¢ ask haircut** `us_backtest.py` already applies.
   The intl favourite arm survived that treatment at +16.7% net; confirm this model does too.
2. **Measure the slippage we set to zero.** "Priced at a real print" is honest for a backtest but we
   *add* an order live. Replay $50/$100/$250 clips against measured `us_book_tape`/`us_quotes` depth.
   Expected small in deep sports-favourite books — but *measured* small, not asserted.
3. **Characterise the drawdown.** Favourites win small/often, lose big/rarely. Block-bootstrap the
   equity curve **clustered by EVENT** (the unit of risk is the game); report max DD, risk-of-ruin,
   ⅛-Kelly fraction.
4. **Forward paper test, pre-registered**, on the `honest-pnl` ledger. Retrospective slices are
   exhausted; power is the binding constraint and only forward time buys it.

**Independent of all the above — the cost-model prize (`feedback-measure-costs-not-just-edges`).**
The `margin = 0.03` constant is wired into `board.rs::render` and every parked negative verdict
(per-sport conditioning, cross-market bands, the fade inversion, exec-policy). True favourite-band
cost ≈ 0.9¢. Re-net every parked arm against the measured cost module, **BH-corrected across the whole
graveyard.** Some arms died to a phantom ~2.3¢. This is worth more than the copy edge and it is owed
its own run.

---

## Instruments (all self-testing, `scripts/niche/`)
- `surplus_decomp.py` — decomposes surplus into Δ(won)/Δ(price)/Δ(fee); price-caliper control.
- `timing_forensics.py` — time-matched blind; where-in-life descriptive.
- `blind_weighting.py` — same-vs-different-outcome decomposition; per-print vs per-opportunity.
- `collapse_risk.py` — the roster-free win-prob model; leak-tested feature builder.
- `collapse_robust.py` — R1–R4 adversarial battery.

All `psql` pinned with `-v ON_ERROR_STOP=1` and `max_parallel_workers_per_gather=0` (the DB serves
the live bot). `copy_econ.py` still carries the silent-failure defect; not touched here.
