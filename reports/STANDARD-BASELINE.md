# THE STANDARD — favorite-tilted consensus (frozen 2026-07-06, Cycle 7)

**This is the current best system and our single focus.** It is defined by **CONFIG, not by a peak
number**. We iterate on it and only ever adopt a change that **beats it out-of-sample on the honest,
belief-blind metric** (enforced by `scripts/standard_guard.py`). We never silently regress from it.

**Posture (unchanged):** PAPER-ONLY. Nothing promoted, nothing armed, no Rust/migration edits, DB
read-only, cost-zero (Max-only). Real-money eligibility is **2/4 GO gates, `real_money_eligible=False`**.
This document freezes a standard to *iterate against*; it does **not** turn anything on.

Frozen snapshot of the numbers below: `reports/baseline_champion.json`.

---

## 1. The config (this IS the standard)

The champion is the **favorite-tilted consensus family**: strategies `favorite` + `elite_fresh_fav`,
defined in `copy-trading-bot/src/scanner/consensus.rs::default_portfolio`. Base params = the `strict`
baseline (`ConsensusParams::default`).

**Base (`strict`) params** — `min_backers=3`, `max_opposers=1`, `max_price_std=0.10`,
`max_age_mins=2880` (48h), `strong_net=4`, `elite_net=6`, `elite_rank=10`, `weight_mode=Quality`,
`sports_mode=Include`.

| arm | params (on top of base) | role |
|---|---|---|
| **`favorite`** | `price_band = (0.65, 0.98)` | the load-bearing arm — belief-blind **SELECTION-REAL** |
| **`elite_fresh_fav`** | `require_elite=true`, `price_band=(0.80, 0.97)`, `max_age_mins=180` | elite fresh-favorite tail; positive but power-limited |

A change to any of these params is a **CHALLENGER**, not an edit to the standard. It must clear
`standard_guard.py` before adoption (§4). Do not tune the config to chase a number.

---

## 2. Why it's real (belief-blind evidence)

Reproduce: `python3 scripts/selection_null.py` (2000 draws, seed 20260702). The selection-matched null
measures surplus vs the **band-matched `_blind` baseline**, randomizing only the *selection* — so it
cannot be gamed by the favorite-longshot composition that false-promoted `market_resid`.

- **`favorite`: 158 events, surplus +8.06% over blind, null −0.13% ± 1.91%, z = 4.28, p_emp = 0.0000
  → SELECTION-REAL.** Belief-blind lower bound (observed − 1.64σ) = **+4.93% > 0**. Bonferroni ×14
  leaves it ≪ 0.01 (p_emp < 1/2000).
- **`elite_fresh_fav`: 68 events, +3.10%, z = 1.42, p_emp = 0.069 → indeterminate** (power-limited;
  it rides in the family but is not independently significant).
- **Regime persistence** (favorite, surplus > 0 in every regime it appears):
  soccer +5.98% (70), tennis +5.95% (57), other +7.58% (16), mlb +23.67% (15) → **3 disjoint
  NON-soccer regimes positive** (clears the ≥2 rule).

---

## 3. The audited baseline metrics (two numbers, both labeled)

> **Honesty note.** There are two honest views of "how well the standard did," and they differ ~4×.
> Report both, labeled. The **resolved-P&L** is the number to treat as the baseline's TRUE realized
> performance. The **realizable-edge/CLV** view is the tracker's designed metric and is legitimate but
> more favorable (and front-loaded). The screenshot's headline **+63%** is *neither* — see §3c.

### 3a. RESOLVED-P&L (canonical — THE baseline) — `honest_paper_ledger`, flat $100
`SELECT strategy, COUNT(*), SUM(pnl), SUM(stake) FROM honest_paper_ledger WHERE strategy IN
('favorite','elite_fresh_fav') GROUP BY strategy;`

| arm | bets | P&L | turnover | ROI-on-turnover |
|---|---|---|---|---|
| `favorite` | 156 | **+$582.87** | $15,600 | +3.74% |
| `elite_fresh_fav` | 73 | −$86.32 | $7,300 | −1.18% |
| **combined** | **229** | **+$496.55** | **$22,900** | **+2.17%** |

Window 07-01..07-06. **Day-by-day: +134 / +852 / −139 / −38 / −389 / +77.** World-Cup-**front-loaded
and decaying**: 07-02 peak +$852, then 07-03..05 = −$566, 07-06 +$77.

### 3b. REALIZABLE-EDGE (CLV − haircut) — the tracker's designed metric, event-clustered
`honest_pnl_by_strategy` logic over the full `consensus_signals` record (06-29..07-06):

| arm | events | honest_roi (mid+1c) | clv_roi | hit |
|---|---|---|---|---|
| `favorite` | 134 | **+8.36%** | +8.36% | 86.5% |
| `elite_fresh_fav` | 68 | +3.29% | +4.66% | 92.3% |

Pooled flat-$100 over the full window: realizable **+$2,123 / +5.33%**; CLV-mid +$2,427 / +6.10%.
At the **measured band-aware tax** (real_tax.json), event-clustered: full-record +5.09%, trailing-3d
+2.05%, last-day +1.55%. (At event-clustering the raw honest_roi lower bound straddles 0 — the
significance is in the selection-null, not a t-test vs 0.)

### 3c. What the "+63% / +$2,008 / 349 bets" screenshot measured (C1 reconciliation)
The screenshot is the **realizable-edge view, pooled at flat stake, over the FULL 06-29..07-06 window**
— reproduced today as **+$2,123 / +5.3%** (398 resolved signals; the screenshot's 349 was an earlier
snapshot with fewer resolved). Its "**+6.9% turnover**" ≈ the event-clustered honest_roi (favorite
+8.4%, elite +3.3%). Its "**+63% on ~$3.2k working bankroll**" = total realizable P&L ÷ *peak working
capital* — a capital-**velocity** return (bets resolve in ~9h and recycle), **not** ROI-on-turnover.

**Why it's ~4× the canonical +$497:** (1) it includes the **two pre-ledger days** the ledger never
recorded — **06-29 alone = +$1,026** (the World Cup front-load) and 06-30 = −$151, = +$875; (2) it's
**pooled** over every signal fire (398) vs the ledger's deduped/appended 229; (3) it's a
**CLV/realizable-entry** basis, more favorable than resolved fills.

**Honest verdict on the +63%:** the realizable-edge *basis* is a legitimate designed metric, but the
**+63% headline is optimistic** — it leans on the un-repeatable front-loaded World-Cup window (half the
profit is one day), uses return-on-working-capital (velocity leverage) rather than edge-on-turnover, and
uses best-case CLV fills pooled. **The single reproducible baseline to trust is the resolved-P&L
+2.2%** (§3a); report the realizable +5–8% only when explicitly labeled as CLV/realizable-edge.

### 3d. The honest bottom line
The standard's value is the **DISCIPLINE** — a belief-blind-validated methodology, frozen, with a
non-regression guard — **not** the peak. On the current ~5-day record it is **+2.2% resolved and
decaying**, its belief-blind edge is real (p=0.0000) but carried by **expiring** regimes, and it is
**not real-money eligible** (binding constraint = non-expiring regime persistence over months).

---

## 4. The non-regression guard (only iterate, never regress)

`scripts/standard_guard.py` (`--selftest` green) enforces champion–challenger:

- **Champion measured forward** on the honest metric (belief-blind selection surplus + realizable edge
  at the band-aware tax), re-runnable with no code change → `reports/standard_guard.json`.
- **A CHALLENGER is ADOPTED only if** it (a) **beats the champion out-of-sample** on the honest metric
  AND (b) clears the **belief-blind gate**: `selection_null` p ≤ 0.01 with `--calibrate` PASS,
  promotion_verdict (LB > 3% margin), and **≥2 disjoint NON-soccer regimes** positive. Otherwise the
  **champion stands**.
- **REGRESSION ALARM:** if the champion's own belief-blind LB drops **≤ 0** (pre-registered floor) over
  the scored record, the guard flags it **loudly** — so a dying standard (regime change) is visible, not
  silently regressed. Today: champion LB **+4.93% > 0 → HEALTHY**.
- Folded into `readiness_ledger.py` as informational rows `standard_champion` + `standard_regression`
  (NOT GO gates).

---

## 5. RETIRED NOISE (deprecated / non-focus)

The following ~14 experimental arms are **net-negative noise** and are **NOT** our focus. They are
**not deleted** (D29 Phase-1 STOP: no live de-registration without human review — see
`HANDOFF-HUMAN-REVIEW.md`). Reporting/instruments now default to the **standard only**. Current
`honest_paper_ledger` P&L (flat $100):

| retired arm | bets | P&L | ROI | note |
|---|---|---|---|---|
| `loose` | 1594 | **−$14,791** | −9.3% | permissive capture-all; the worst |
| `whales` | 483 | −$5,874 | −12.2% | dollar-weighted; ≈ strict/count |
| `fresh2h` | 479 | −$5,956 | −12.4% | |
| `count` | 483 | −$5,863 | −12.1% | count-weighted |
| `strict` | 483 | −$5,847 | −12.1% | the incumbent alerting arm — net-negative on the full record |
| `sports_only` | 476 | −$5,320 | −11.2% | |
| `trust_weighted` | 325 | −$5,137 | −15.8% | |
| `longshot` | 144 | −$4,915 | −34.1% | price_band (0.02,0.35) — the FLB sink |
| `elite_gated` | 391 | −$4,395 | −11.2% | |
| `strict_retuned` | 104 | −$1,757 | −16.9% | |
| `trusted_only` | 47 | −$1,483 | −31.5% | |
| `tight_cluster` | 82 | −$1,466 | −17.9% | |
| `nonsports` | 7 | −$529 | −75.5% | |
| `proven_router` | 4 | −$408 | −102% | PREREG 07-04, no volume |

*(Also `_blind` — the band benchmark, never a strategy; never alerts.)*

**Note:** several retired arms show a *belief-blind* selection surplus (e.g. `strict`/`count`/`whales`
+4.7%, `sports_only` +4.6%, `trust_weighted` +6.7% in `selection_null`) yet are net-**negative** in
paper P&L — because they trade the whole band including the FLB-losing longshots. The favorite-tilted
standard is the one whose selection surplus **and** realizable P&L both survive. That is exactly why the
standard is `favorite`, and why any challenger must beat it on the **realizable** metric, not just the
selection surplus.

**Deferred (human review):** narrowing the live `LEDGER_STRATEGIES` env to the standard is proposed in
`HANDOFF-HUMAN-REVIEW.md` (a live-config change → DEFERRED, not applied here).

---

*Cycle-7 consolidation. Standard frozen by config; guard installed; noise retired to non-focus.
Nothing promoted, nothing armed, no Rust touched, DB read-only.*
