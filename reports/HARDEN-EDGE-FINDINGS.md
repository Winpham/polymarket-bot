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
| resolved ROI (honest_paper_ledger basis)* | +2.17% | **+1.27%** | ↓ |
| non-soccer positive regimes | 3 | **2** | ↓ (`other` flipped −3.12%) |

*\*The ledger-basis ROI shows DECAY consistently, but is NOT the authoritative baseline — the
cash-basis `audit_pnl_books.py` reads ≈5.6–7% ROI-on-turnover (4.38% ex-soccer). See §7.*

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

**Two DIFFERENT compounding axes — size is capped, throughput is the live lever (CORRECTED 2026-07-09
after reconciling with `audit_pnl_books.py`, the authoritative cash-basis source):**

- **Per-event SIZE — capped (this finding stands): ~$500–1,000 per signal**, well below on the thin
  tail. Scaling stake past that makes us the flow and the historical edge (measured small) no longer
  applies. ⅛-Kelly ≈ flat (§5). So you cannot grow via bigger bets.
- **THROUGHPUT (turnover-multiple) — the REAL growth axis, with headroom.** Realized daily $ =
  **turnover-multiple × ROI-on-turnover**. The authoritative audit measures the multiple at **1.14×/day**
  (bankroll recycles ~once/day; median resolved hold 2.7h ⇒ a ~**8.8×/day** resolution-speed ceiling).
  Holding the ex-soccer edge (~4.4% ROI-turn) constant and lifting the multiple 1.14×→3× would ~triple
  daily dollars with **no bigger edge** — the honest ambition target.

**But the throughput lever is gated by the SAME resource as persistence — out-of-soccer event supply.**
You can only recycle freed capital into *concurrent soft-favorite events that exist*; out-of-soccer
that supply is thin (~0.9 MLB clusters/day; ~2.6 recurring ev/day historically). So the 8.8× ceiling is
theoretical — the *achievable* multiple out-of-soccer is supply-limited well below it, and the recent
cash days are **negative** (07-05 −$281, 07-07 −$105, 07-08 −$159 — the P1 decay, on a cash basis). So
my earlier "compounding mirage is dead" was **half-right and half-wrong**: mirage-via-SIZE is dead;
growth-via-THROUGHPUT is real but bottlenecked by exactly the out-of-soccer event supply that also
gates persistence. **This unifies P1 and P2: the single binding resource is non-soccer event supply —
it caps both the persistence gate AND the turnover-multiple.**

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

## 4. Execution realism — fee model reconciled, measured entry is dear

**The "staged fee-model" the brief expected does not exist:** branch `fee-model-accuracy` (wt/fee-model)
is at main HEAD with a clean tree — the accurate taker fee was never committed. In the tree today the
fee is **inconsistent**: `backtest.py` uses flat `0.03·stake` (over-charges favorites 6×), copyability
/ selection_null use a 2% buffer. The correct Polymarket sports taker fee is **0.03·(1−p)** per $ of
stake (entry-only; makers pay 0) — ~0.5% at favorite prices, far below the flat fees.

**Realizable-edge ROI (at-fire entry basis; = the §3b honest_roi view, matches the prior +8.36%). The
authoritative CASH-basis resolved number is `audit_pnl_books.py`: +$1,922 / 419 bets, ROI-on-turnover
≈5.6% (11-day) / 6.95% (8-day), 4.38% ex-soccer — NOT the +1.27% honest_paper_ledger figure (a
truncated/decayed sub-window; see §3b/§7). All labeled:**

| entry basis | correct 0.03(1−p) | flat 2% buffer | flat 3%·stake | maker (fee 0) |
|---|---|---|---|---|
| at-fire mid | **+8.02%** | +6.55% | +5.55% | +8.55% |
| mid + 1¢ measured tax | +6.71% | +5.22% | +4.22% | +7.22% |
| measured ask* | +1.41% | −0.02% | −1.02% | +1.98% |

`*measured ask = entry_ask` (172/418 rows), captured ~20min post-detection (G3 audit): a **future
price**, flatters ~1.8pp — shown, never the headline.

**Reads:** (1) using the correct fee vs the flat 2%/3% fees adds **+1.5 to +2.5pp** to the honest edge —
it's the right number and it's favorable to favorites. (2) But **measured realized entry is dear**:
even the (optimistically-contaminated) captured ask drops the realizable edge to **+1.4%**; a true
causal decision-time ask (per G3, the sharp lifts the ask ~3min pre-detection) would likely land it
near or below break-even on a taker basis. The gap between the +8% at-fire-mid basis and the ~+1.4%
measured-ask basis **is the execution tax, and it is the difference between "looks great" and
"marginal."** For real-money reasoning, trust the **authoritative cash-basis (`audit_pnl_books.py`):
ROI-on-turnover ≈5.6–7% (4.38% ex-soccer), front-loaded, with the last 3 of 4 days negative** — the
edge is real and better than the stale +1.27% suggested, but decaying and execution-sensitive. (The
+1.27% honest_paper_ledger figure I initially anchored on is a truncated/decayed sub-window and is
**not** the baseline — corrected per the cross-chat reconciliation in §7.)

## 5. Sizing / risk — cannot be safely levered (confirmed)

Sizing bake-off (correct fee, at-fire mid, realizable basis), favorite arm:

| scheme | P&L | turnover | ROI |
|---|---|---|---|
| flat-$ | +$3,350 | $41,800 | +8.02% |
| flat-shares | +$2,636 | $34,292 | +7.69% |
| capped-favoritedness | +$3,195 | $36,900 | +8.66% |
| ⅛-Kelly-on-surplus | +$2,640 | $41,800 | +6.32% |

ROI spread across schemes is only **2.34pp**, all positive — the edge does **not** depend on exotic
sizing, and **⅛-Kelly ≈ flat** (slightly lower). Combined with the P2 capacity ceiling (~$500–1k per
signal), this **confirms the frozen finding: a thin, capacity-capped edge cannot be safely levered** —
prudent compounding buys no material uplift, and full-stake compounding is not achievable. Sizing is a
second-order lever; the first-order levers remain persistence (unavailable for months) and execution
cost (dear).

## 6. Bottom line for Tue

**Not yet — and this run makes exactly-why sharper, not softer.** The favorite edge is still the one
real thing (belief-blind SELECTION-REAL, p≈0.0000), and the single most hopeful fact I can show you is
that its **recurring, non-expiring regimes are net-positive after the copy tax** (mlb +7.4%, nba/cbb
+32.8%). But every lever I could reach now hit the same wall: the edge is **decaying as data accrues**
(belief-blind LB +4.93%→+3.44%, non-soccer regimes 3→2 since the 07-06 freeze), it is **power-limited
not point-estimate-limited** (0/4 recurring regimes clear the 10-cluster floor; the transfer null is
structurally inert below ~5–6 regimes; OOS pooled surplus is ~0), its **per-bet SIZE cannot be scaled**
(caps at ~$500–1k/signal — though THROUGHPUT/turnover-multiple is a real growth axis with headroom,
gated by the same non-soccer supply; see §2/§7), and its **measured execution entry is dear** (the
realizable +8% at at-fire-mid drops to ~+1.4% at the captured ask). The authoritative cash baseline is
**≈5.6–7% ROI-on-turnover (4.38% ex-soccer)** — real and better than the stale +1.27% I first cited,
but front-loaded with the **last 3 of 4 days negative**. I searched hard for a better sub-region and the one tempting
candidate — tightening to the strong-favorite band 0.75–0.98 — was **adversarially REFUTED** as an
expiring-tournament / multiple-comparisons artifact. **The single thing standing in the way is
unchanged and unmanufacturable: months of independent NON-SOCCER regime persistence.** The concrete
timeline: a second non-soccer sport in-season (NFL ~Oct, NBA/CBB ~Nov 2026) is the earliest the gate
*could* reach power — and even then PERSISTS is conditional on the edge actually holding, which today's
flat OOS says it might not. **Nothing promoted, nothing armed, no real money, `real_money_eligible`
stays False (2/4 GO gates), champion frozen. The instruments did their job: they kept us from betting
real money on a decaying, capacity-capped, expiring-carried mirage.** That protection is the asset.

**One concrete, low-risk thing you could choose to do** (I did NOT do it — it's a live-config/registry
decision for you): **pre-register the 0.75 price floor as a single forward hypothesis** and let
`forward_track` / `standard_guard` score it on forward non-soccer months alongside the champion. If
strong-favorite concentration is real it will separate from the champion out-of-sample over months; if
it was fishing it won't. Either way it costs nothing and adds a real test — the disciplined way to
chase the one lead this run surfaced.

---

### Run log / provenance
- Branch `harden-edge` off `main` (4940509). Commits: baseline → P1 → P2 → P3(search) → P3(skeptic) →
  P4+P5 → deliverables. Not merged (no green gate; per brief, left for Tue on the branch).
- New read-only research instruments (all ran clean): `capacity_curve_harden.py`,
  `edge_refine_search.py`, `edge_refine_oos.py`, `exec_and_sizing.py`.
- **Incidental bug fixed:** `readiness_ledger._pf` crashed (`ValueError`) on a forward play with
  infinite Calmar (serialized as the string `'inf'`) — a real latent crash; hardened to pass strings
  through (display-only, no gate logic touched). Ledger now re-runs clean.
- Diff scope: pure Python + reports. **No Rust, no migration, no `.env`, no `consensus.rs`, no live
  `strict`/alert path touched. DB read-only. Cost-zero (no API key, no child claude).**
- Verdict re-run: `real_money_eligible=False`, **2/4 GO gates**, binding=persistence — **unchanged; no
  gate flipped; no ESCALATE banner** (correct — nothing was adopted).

---

## 7. Cross-chat reconciliation (2026-07-09) — baseline corrected, throughput reframed

A parallel chat ran `scripts/audit_pnl_books.py` (the authoritative cash-basis audit). I reproduced it
here (`reports/audit_pnl_books.json`): **419 resolved bets, +$1,922 net, win-rate 88.8%,
ROI-on-turnover ≈5.6% (11-day) / 6.95% (8-day window), 4.38% ex-soccer** (07-02 alone ≈46% of profit,
but stripping it stays clearly positive — soccer-**heavy**, not soccer-**only**). Two corrections to my
run:

1. **Baseline number (I was wrong):** I anchored §4/§6 on `honest_paper_ledger`'s **+1.27%** as "the
   resolved number to trust." That is a *truncated/decayed* sub-window (306 flat-$100 bets; excludes the
   pre-ledger 06-29/06-30 World-Cup front-load the cash audit includes). **The authoritative baseline is
   ≈5.6–7% ROI-turn (4.38% ex-soccer)** — my +8% realizable-at-mid was directionally right, not the
   +1.27%. Corrected throughout. (Note: the audit is front-loaded and the **last 3 of 4 cash days are
   negative** — the same decay my P1 found, now on a cash basis. So "5.6–7%" is a decaying, front-loaded
   number, not a forward run-rate.)

2. **Compounding reframe (I was half-wrong):** I said "compounding mirage is dead." Precisely: mirage
   **via SIZE** is dead (per-event ~$500–1k cap stands, ⅛-Kelly≈flat). But growth **via THROUGHPUT** is
   real: `daily $ = turnover-multiple × ROI-turn`, and the multiple is only **1.14×/day** against a
   ~**8.8×/day** resolution-speed ceiling (median hold 2.7h). Lifting 1.14×→3× ~triples daily $ with no
   bigger edge — the honest ambition. **Critical caveat (mine, standing):** that headroom is gated by
   the *same* out-of-soccer event supply that gates persistence — you can only recycle capital into
   concurrent soft-favorite events that exist, and out-of-soccer that supply is thin (~0.9 MLB
   clusters/day). And the 2.7h hold is `resolved_at` = our grading pass (backlog-sweep inflated), so the
   8.8× is itself soft. **Net: the binding resource is non-soccer event SUPPLY — it caps both the
   persistence gate and the turnover-multiple.** The reframe correctly names the growth axis; it does
   not move the wall.

**Verdict unchanged:** real, better-than-I-said, still NOT-YET, still gated by months of non-soccer
supply/persistence — which now also explains why throughput can't be lifted yet.
