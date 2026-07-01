# DECISIONS — Optimal Congregation Engine run (2026-06-30)

Non-obvious choices and their "why", so a future run resumes with full context.
Branch `feat/congregation-engine` (worktree off `feat/consensus-engine`).

---

## D1 — The as-of time axis is the slug-parsed EVENT DATE, not `resolved_at` or `ts`

**Context.** Charter H2 requires leak-free identification via `trader_slice_scores_asof(cut)`
with `resolved_at < cut`. The blueprint (Item 6) names `trader_fills.resolved_at` as the
cut key.

**Reality found (read-only SQL, this DB).**
- `resolved_at` for **all** 134,099 resolved fills falls in a 2-day window
  (130,280 in 2026-06 + 3,856 in 2026-07). It is a **bulk-backfill / ingest** stamp,
  not true market-resolution time. A `resolved_at < cut` split for any cut before the
  backfill puts *every* row in the test set → the harness is vacuous.
- `ts` (fill time) is *also* mostly a crawl stamp: **119,579 of ~134k resolved buys
  share `ts::date = 2026-06-30`**; the "4-year archive" is a few hundred stray old rows.
- `event_slug` **does** carry the true event date (`fifwc-fra-swe-2026-06-30`,
  `nba-por-phi-2026-03-15`): 125,134 / 129,242 rows parse a `YYYY-MM-DD`. This is the
  only honest economic time axis on the archive.

**Decision.** For the **retrospective pre-flight/research** on this archive, cut on the
slug-parsed event date (`scripts/asof_slice_scores.sql`). For the **in-engine forward
instrument** (`trader_slice_scores_asof`, Phase 0.5) keep `resolved_at < cut` as the
blueprint specifies — that is correct once `resolved_at` is populated in real time on
forward data; it is only degenerate on the backfilled historical archive. Both facts
are documented at the call sites. This is a reversible, evidence-backed reality
correction (charter H9 posture), not a mission change.

**Why it matters.** Using `resolved_at < cut` literally on this archive would have
manufactured a "clean" but meaningless harness. The finding below depends on getting the
time axis right.

---

## D2 — §0.5 pre-flight verdict: the diversification premise is DEAD ON THIS DATA → stop before the arms

**The binding experiment (reproducible: `scripts/asof_preflight.py`).**
As-of certification faithfully replicating `trader_slice_scores` + `surplus_bounds`
(per-wallet Bonferroni denominator = slices-with-data; `z = probit(1−0.05/nComp)`;
`lo = surplus − z·se`; Trusted@capture ⇔ `N≥30 ∧ lo > 3%`).

| test | result |
|---|---|
| per-sport specialists Trusted@capture, cut 2026-06-29 (train side) | **0** |
| per-sport specialists Trusted@capture, cut 2026-06-30 (train side) | **0** |
| **full-window, in-sample** (no walk-forward, most generous) Trusted@capture per-sport cells | **0** |
| wallet-sport cells with ≥30 events on **both** sides of any cut | **0** (only cut 06-30 even has 3 cells with ≥30 both sides; disjoint cut 06-29 has 0) |

**Why zero — legible, not a bug (exactly the Forge's predicted binding constraints):**
1. **Sample floor.** The wallets with a visible point-estimate edge are *below* 30 events
   (soccer +0.274 @ N=28, +0.197 @ N=20) — small N, not evidence. World Cup is a short
   tournament; a wallet bets ~20–28 distinct matches.
2. **Capture margin + variance.** The wallets that *do* clear N≥30 have either tiny
   surplus (tennis ~+0.04 @ N≈108, below the 3% margin once bounded) or high variance
   (soccer +0.108 @ N=58 → lo −0.034). None clears `lo > 3%`.
3. **Slate collapse (H4).** The whole record is essentially **two adjacent days of one
   tournament** (World Cup soccer, 2026-06-29/30) plus Grand Slam tennis bursts (166
   tennis events over just 9 event-days). Even the ≥30-event cells are correlated
   within-tournament markets → effective independent-N ≪ 30, and any two "specialists"
   are co-active on the same slate. Diversification across independent certified edges —
   the entire north star — is impossible when the data is one tournament weekend.

**Decision (binding, charter §0.5).** `<2` capturable, persistent per-sport specialists
(in fact **0**, even in-sample) **and** maximal slate collapse ⇒ premise DEAD ON THIS
DATA. Per the decision rule: **do NOT build Phases 2/5** (the specialist/contrarian/
edge-pool/coalition arms). Deliver the as-of harness, the honest-null finding, and the
accrual curve. This is *also* the leak-free answer to the §7 escalation trigger
("does per-context certification predict forward edge out-of-sample" — unanswerable
here because no wallet certifies in-sample and there is no second disjoint cut). Per the
charter, **a dead premise correctly established in one hour is a successful run.**

---

## D3 — What DID ship, and why (not nothing, not the arms)

The DEAD branch says deliver "the as-of harness". Shipped, each non-regressive and
gate-green:
- **Phase 0 — capture margin at the strategy gate.** `board.rs` render gates arms at
  `slippage_pct + fee_pct = 3%` instead of `margin 0`. Pure rigor; raises the bar for
  every existing arm; touches neither `strict` alerting nor `trader_trust`. This is the
  exact bar the pre-flight certifies against, so the live board and the report now agree.
- **Phase 0.5 — `trader_slice_scores_asof(cut)`** — the leak-free forward instrument
  (blueprint Item 6), `resolved_at < cut` in both the slice surplus and the band-blind,
  recency slices dropped. Plus the reproducible pre-flight harness
  (`scripts/asof_slice_scores.sql` + `scripts/asof_preflight.py`) that produced D2.

**Not shipped (deliberately):** Phase 1 `SliceTrustMap` (exists only to feed arms),
Phases 2–5 arms. No arm can be honestly certified when 0 specialists exist. Building them
silent+OFF would add hypotheses to the family Bonferroni for zero information. The clean
extension point remains: when accrual (D4) yields ≥2 persistent cross-sport specialists,
Phase 1 + Arm A/D are the next run's first move, and this harness is their gate.

---

## D4 — Accrual: when could ≥2 persistent specialists emerge?

Dated independent **event-days** per sport on the whole archive: soccer 21, tennis 9,
mlb 12, everything else ≤4; crypto has 237 events but **zero** parseable date (no time
axis — cannot be walk-forward split at all). A wallet cannot reach 30 *independent*
soccer event-days when the fleet has only 21 in total. Event accrual is bursty and
tournament-gated (World Cup, Grand Slams), and tournaments are seasonal with gaps.

**Honest ETA.** Two conditions must *both* hold, and the second is the real wall:
1. *Coverage:* ~30 independent event-days in a single sport per wallet — realistically
   **months** of continuous major-tournament slates (and the World Cup ends imminently,
   after which soccer density collapses).
2. *Edge:* a surplus that clears `lo > 3%`. The full-window in-sample test shows this is
   **absent for every wallet today**, consistent with the standing "consensus count is
   noise / the market is ~efficient" prior. More data mainly tightens bounds around
   point estimates that mostly sit below the capture margin — it does not create an edge
   that is not there. So the defensible ETA to a bettable per-sport specialist is
   **not estimable as a near-term date**; the correct posture is to keep accruing the
   forward record and re-run this one-hour pre-flight after each major tournament block,
   promoting nothing until ≥2 cross-sport cells clear `lo>3%` on ≥2 disjoint cuts.
