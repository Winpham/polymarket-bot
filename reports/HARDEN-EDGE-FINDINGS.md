# HARDEN THE FAVORITE EDGE — Findings

> Autonomous run on `~/polymarket-bot`, branch `harden-edge` off `main` (4940509).
> North star: *turn the favorite edge into a real, profitable edge we can be confident in — or
> prove, rigorously, that it can't be yet.* Belief-blind discipline (§3 of the run brief). No real
> money, DB read-only, cost-zero, nothing armed/promoted, `strict` path untouched.
> Both are success; a goal-sought green is failure.

---

## 0. Baseline reproduction (starting verdict — before any lever)

Reproduced the frozen champion (`reports/STANDARD-BASELINE.md`, frozen 2026-07-06) on the **current**
(more-accrued) data. Instruments re-run unchanged from `main`:

- `standard_guard.py --selftest` → **PASS** (12/12 invariants).
- `selection_null.py --calibrate` → **PASS** (p<0.05: 12% ≤20% bar; p∈[0.1,0.9]: 72% ≥60% bar) —
  the belief-blind gate is trustworthy (not anti-conservative).
- `standard_guard.py` (champion measured forward):
  - `favorite`: **197 ev · surplus +6.29% · z 3.58 · p_emp 0.0000 · LB +3.44% · 2 non-soccer
    regimes+ · SELECTION-REAL**
  - realizable edge (band-aware tax, event-clustered): family **+2.88%** over 169 ev
  - resolved-P&L (canonical ledger): **306 bets · +$388.5 · ROI +1.27%**
  - REGRESSION STATUS: **HEALTHY** (LB +3.44% > 0).

### The honest decay since the 2026-07-06 freeze (more data → weaker edge)

| metric | freeze (07-06) | now (more accrued) | direction |
|---|---|---|---|
| favorite events | 158 | 197 | +39 |
| selection surplus | +8.06% | **+6.29%** | ↓ |
| belief-blind LB | +4.93% | **+3.44%** | ↓ (toward the +3% floor) |
| resolved ROI | +2.17% | **+1.27%** | ↓ |
| non-soccer positive regimes | 3 | **2** | ↓ (`other` flipped −3.12%) |

**favorite per-regime (current):** soccer 82 ev **+7.11%**, tennis 76 ev **+5.27%**,
mlb 18 ev **+13.54%**, other 21 ev **−3.12%**.

The two surviving non-soccer positives are **tennis** (Wimbledon/ATP — seasonally expiring) and
**mlb** (only 18 ev). This is exactly the SOCCER-ARTIFACT / expiring-regime concern the freeze warned
about, now sharper: as fresh data lands the edge is **decaying and its regime support is thinning**,
not broadening. The champion is still SELECTION-REAL and HEALTHY, but the LB has moved from +4.93% to
+3.44% — closer to the +3% adoption floor / 0 regression floor.

**Starting verdict (unchanged, re-confirmed):** `real_money_eligible = false`, **2/4 GO gates**,
binding constraint = **persistence** (non-soccer, months), `edge_reality` also unmet (capture
coverage ~2%). Nothing here flips a gate.

---

## 1. Persistence (the binding gate) — full ledger in `reports/PERSISTENCE-LEDGER.md`

Re-generated all four persistence instruments live (`regime_edge`, `regime_net_edge`,
`regime_persistence`, `persistence_tracker` — all `--selftest` green) on the current record.

**Verdict: `SOCCER-ARTIFACT` / INDETERMINATE-BY-POWER — re-confirmed and quantified.**

- The **recurring (non-expiring) regimes are directionally positive AND net-positive after the copy
  tax** — mlb\|2026-07 +11.2% gross / **+7.4% net**, nba/cbb\|2026-07 +36.4% / **+32.8% net**. This
  is the most hopeful fact in the system.
- But the gate is **power**, not the point estimate:
  - **0/4** recurring regimes clear the 10-cluster floor (best: mlb\|07 at 7 clusters).
  - Only **1** recurring regime is net-positive with **LB>0** (nba/cbb, N=4) — need ≥2.
  - Cross-regime permutation null is **structurally inert** (min achievable p_conc 0.353 — can't fire
    below ~5–6 regimes).
  - Temporal OOS pooled surplus is **−0.87% (flat)** — so count-power could resolve **REFUTED**.
  - Expiring regimes carry **67% of edge mass** (tennis 43%, other 27%, soccer 17%).
- **`forward_track.py` verified**: correctly accrues + gates forward non-soccer regimes (0 since the
  07-06 seal — only ~2 days elapsed — all INDETERMINATE-BY-POWER, binding = months). Working; needs time.

**Months-to-power (concrete):** Only **MLB** is a non-expiring sport firing at volume now (~0.9
clusters/day). MLB alone hits its 10-cluster floor in ~1 week, but that is one sport. The binding wall
is a **second non-soccer sport in-season**: World Cup ends ~07-19, Wimbledon ~07-12, NBA offseason to
~10-21, NFL starts ~09-10. ⇒ earliest 2nd independent non-soccer recurring regime at power = **NFL,
~early Oct 2026 (≈3 months)**; robust ≥5-regime non-expiring panel = **~Nov 2026–Feb 2027 (4–6
months)**. Even then, PERSISTS is conditional — current OOS edge ≈ 0. **No run can manufacture this.**

## 2. Capacity & fills — the compounding mirage, killed

**Coordination:** consumed the maker-copy G3 run's committed outputs (`reports/maker_copy_g3.json`,
its entry, `maker_capacity_fulltape.json`, `copyability.json`) — did NOT re-run its fill models or
touch its files/tables. Added the one thing no prior artifact isolated: the **native per-signal size**
(`scripts/capacity_curve_harden.py`, read-only).

**Load-bearing data reality (from G3, respected):** `clob_price_tape` is a top-of-book
best_bid/best_ask inflection series with **NO trade tape** — `last_size` is quote-book churn, not
executed volume. So a *depth-based* capacity curve from `clob_price_tape` is **not honestly
measurable** (the G2 quote-flicker trap). The measurable anchors are the sharks' native size and the
full-market flow ceiling.

**Native size:** favorite signals are backed by material aggregate position — median consensus
notional **$16,968**, p25 $3,835, p90 $198,467 (~3 backers, per-backer median $5,580). But individual
sharp *fills* are tiny (trader_fills median **$11**, p90 $277) — they accumulate via many small fills.

**Capacity curve (our stake as a share of native size; OPTIMISTIC — see caveat):**

| stake | median our-share | p90 our-share | % signals still small-copy (≤10%) | % we ARE the flow (≥50%) |
|---|---|---|---|---|
| **$100** (current) | 0.6% | 10.5% | **89.9%** | 2.4% |
| $500 | 3.0% | 52.4% | 69.7% | 10.1% |
| $1,000 | 6.1% | 104.7% | 59.6% | 18.8% |
| $2,500 | 15.1% | 261.9% | 46.2% | 30.3% |
| $10,000 | 60.6% | 1047% | 21.2% | 51.4% |

**Caveat (the true ceiling is BELOW this):** the curve uses the sharks' full *accumulated* position
(much entered earlier/cheaper), not the *marginal ask liquidity at our entry in the 5-min window* —
which the full-tape flow ceiling shows is far thinner ($4–45/signal on reachable markets, and
coverage-biased low because data-api /trades caps offset so the busiest markets are unreachable
historically). Precise taker impact-at-size needs order-book depth we don't have historically (the
same wall G3 hit); the honest read is qualitative.

**Realistic compounding ceiling: ~$500–1,000 per signal**, and well below that on the thin tail. At
~45 favorite signals/week × +2.8% resolved edge, even the optimistic $1k cap implies **only ~$1k/week
gross edge** — and that assumes the edge (measured at flat $100) survives at 10× size, which is
unproven and probably optimistic. **The compounding mirage is dead:** you cannot turn a small +2.8%
edge on $100 into meaningful absolute profit by scaling stake, because per-signal capacity caps at
low-thousands and marginal liquidity is thinner still. This is consistent with the frozen finding that
a thin, capacity-capped edge cannot be safely levered.

**Maker path (from G3, not re-derived):** real +2–4% entry edge (rest at the sharp's price, cheaper
than taking at detection) but adverse selection dominates at realistic rest windows (adverse-WR gap
−35% to −38%; miss 21–29% of winners); INDETERMINATE-BY-POWER (N=20, 2 day-clusters < 5). Volume /
queue-capture still OPEN (needs a real trade tape).

## 3. Edge refinement (challengers under the guard) — CHAMPION STANDS

Built a refinement-search harness (`scripts/edge_refine_search.py`) that reuses `selection_null.py`'s
exact belief-blind machinery on **subsets** of the favorite arm across 5 axes (price sub-band,
freshness, book-depth, backer-quality, price-std) + 2-way combos — 14 challengers. Each scored on the
full belief-blind gate (p≤1% ∧ LB>3% ∧ ≥2 non-soccer regimes).

**Most candidates correctly FAILED** (the screen working): freshness cuts go *negative*
(fresh≤180m −0.83%, fresh≤5m −1.53% — fresher isn't better here), depth/pstd/rank cuts don't clear.
**Two nested price-band tightenings cleared the full-record gate:** band 0.70-0.95 (LB +4.39%) and
**band 0.75-0.98 (obs +8.47%, LB +5.57%, p 0.0000, 3 non-soccer regimes)** — dropping the 0.65-0.75
mild-favorite slice.

I treated this as the exact "tuning to chase a number" trap the brief warns about and stress-tested it:

1. **OOS temporal split** (`scripts/edge_refine_oos.py`, cutoff 2026-07-04): band 0.75-0.98 *appeared*
   to beat champion out-of-sample too (OUT obs +5.93% vs +3.28%, OUT LB +1.71% vs −1.11%).
2. **Independent adversarial skeptic (Opus, read-only, refute-stance)** → **REFUTED.** The decisive
   findings:
   - The dropped mild band 0.65-0.75 is **+8.37% in-sample but −1.60% OOS** — the tight band's "OOS
     win" is manufactured by a 36-event mild-favorite blip dipping negative in one 4-day window; a
     band whose sign flips between adjacent windows is noise.
   - **84% of the OOS tight-band events are expiring World Cup + Wimbledon**; non-expiring support is
     ~zero (1 MLB event). It generalizes beyond those two tournaments not at all.
   - **Bonferroni ×14 → OOS p 0.0095 × 14 ≈ 0.13**, fails the p≤0.01 gate. Belief-blind surplus is
     near-monotonic in price, so "raise the floor" mechanically raises the mean — the definition of
     garden-of-forking-paths, not a discovered edge.
   - OUT LB +1.71% is also **< the +3% adoption margin**, and the champion is itself under-powered OOS.

**Verdict: CHAMPION STANDS. Nothing adopted.** band 0.75-0.98 is a *suggestive-but-refuted* candidate.
The honest, disciplined action (not taken here — it's a live-config change for Tue) is to
**pre-register the 0.75 floor as a single forward hypothesis** and re-test it on forward **non-soccer**
months, exactly as the persistence gate requires. This is a first-class success: a tempting positive,
surfaced, adversarially refuted, correctly declined.

## 4. Execution realism

_(pending)_

## 5. Sizing / risk

_(pending)_

## 6. Bottom line for Tue

_(pending)_
