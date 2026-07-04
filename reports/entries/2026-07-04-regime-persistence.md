# Regime Persistence & Net-Edge — is the edge stationary, or soccer-shaped?

**Date:** 2026-07-04 (UTC) · **Branch:** `feat/regime-persistence` (NOT merged — left for review) ·
**Paper-only, read-only, promotes nothing.** DB snapshot: favorite = 275 resolved signals → 92
match-events over 6 contiguous days (2026-06-29 → 07-04), spanning 2 calendar months but ONE
continuous span (World-Cup + Wimbledon window). *(Live bot; later runs drift to ~288–293 signals /
93 events — conclusions are drift-invariant.)*

> ## ⟢ AUDIT OUTCOME & CORRECTIONS APPLIED (2026-07-04)
> An **independent adversarial audit** (`2026-07-04-regime-persistence-AUDIT.md`) reproduced every
> headline number from raw DB with its own code (zero DIVERGE) and **CONFIRMED `SOCCER-ARTIFACT`** —
> robust across 12/13 defensible configs, and *structurally unflippable* (6 days < 10-cluster floor,
> so PERSISTS is unreachable by construction). It also found **three real defects, all in
> certification-favorable sub-claims — fixing each makes the non-certification verdict STRONGER.** All
> are now fixed (see `PREREG_..._ADDENDUM2.md`), belief-blind (verdict unchanged under old & new):
> 1. **Small-cluster inference** used normal z=1.96 where t(G−1) is required (G=2–6). Fixed → t(G−1)
>    via `regime_edge.lb_small_cluster`. The load-bearing pooled edge survives (t-LB ≈ +2.7%); a G=2
>    regime can no longer clear (t(1)≈6.31). The "net-positive" / "leg-b transfer" counts now DRIFT with
>    the snapshot (1 at the audit's 286-signal snapshot, 2 at 288 where nba/cbb reached 3 clusters) —
>    always non-load-bearing.
> 2. **leg (b) was decorative** — its permutation guard is mathematically incapable of firing on this
>    data. Fixed → it now reports a **RAW transfer count** with `guard_can_fire=False`, never "PASS".
> 3. **leg (a) baseline leaked** ~43% post-cutoff blind rows. Fixed → strictly-causal IN-period-only
>    baseline (`build_events_leakfree`). Benign today (leak deflated the edge) but was set to
>    contaminate the certification LB.
> Plus: classifier now treats one-off primaries as expiring, and the label is clarified —
> **by edge mass the carrier is tennis/Wimbledon (~67%), not soccer (~21%)**; "soccer" only leads on
> capital exposure (71%). The `SOCCER-ARTIFACT` enum is a frozen ladder rung; the substance is
> "expiring-tournament-carried." Audit verdict: **TRUSTWORTHY-WITH-MINOR-FIXES → now APPLIED.**

## Headline (brutally honest)

**VERDICT: `SOCCER-ARTIFACT`** — the pooled favorite edge is **57% carried by EXPIRING regimes**
(World-Cup soccer + Wimbledon tennis) at the honest event grain, and **0 of 5 recurring regimes clear
the 10-cluster independence floor**, so nothing is certifiable. The recurring edge is *promising but
power-starved*, not refuted. Real money stays OFF.

The one non-obvious nuance this run surfaced: at the honest **event grain** (super-key collapse, one
game = one bet) the edge is NOT dramatically soccer-concentrated — soccer is only ~19% of *events*
(the "68% soccer" prior lives at the **capital/bet grain**: 71% of *signals* are soccer). The edge
mass is spread (HHI 0.15, ~6.5 effective regimes), and the single largest contributor is actually a
**recurring** regime (`mlb|2026-07`, +21% surplus, 23% of mass). But every recurring regime is far
below the independence floor. So the binding wall is **accrual of independent recurring-regime
clusters**, exactly the stationarity gate — not sample size, not the point estimate.

## Numbers that matter

- Pooled favorite surplus **+9.7%** (cluster-robust LB **+2.5%**) over 92 events / 6 day-clusters;
  net-of-copyability-tax (taker) **+5.2%**.
- **Concentration:** expiring regimes carry **57%** of event-grain edge mass (the soccer-artifact
  test, marginally positive). Top single regime `mlb|2026-07` = 23%. Capital exposure = **71% soccer**
  (signal grain — where the "soccer-carried" prior actually lives).
- **Breadth:** 11 regimes (5 recurring / 6 expiring). **Recurring regimes clearing the 10-cluster
  floor: 0 / 5.** Toward the ≥2-disjoint-non-expiring bar: **0 cleared.**
- **Persistence legs (recurring only):** leg (a) temporal = **PENDING** (only 3 recurring OUT
  day-clusters < 10 floor; leak-free recurring-OUT surplus +21%, small-cluster t-LB +11% — strong but
  power-starved). leg (b) transfer = a **RAW COUNT of 2/2** recurring regimes that transfer — **NOT a
  passed statistical test**: its regime-permutation guard is non-discriminating on this data
  (`guard_can_fire=False`, min achievable p_conc ≈ 0.22 ≥ 0.05; the original beat-null is also
  unpassable). Reported honestly as a count, not "PASS." Both legs required → not PERSISTS regardless.
- **Net-positive recurring regimes after tax (taker, fee 2%, small-cluster t-LB>0):** snapshot-dependent
  — **1** at the audit's 286-signal snapshot (nba/cbb had G=2, flips negative under t(1)≈6.31), **2** at
  288+ where `nba/cbb|2026-07` reaches 3 clusters and survives t(2). Either way on power-starved counts
  (2–4 clusters, all below the 10-cluster persistence floor), so **net-positive ≠ persistent**.
  `PERSISTS-NET` requires BOTH persistence legs AND ≥2 net-positive recurring regimes; leg (a) is
  PENDING, so `PERSISTS-NET` is **not** reached under any snapshot.

## The single binding constraint + ETA

**Binding = persistence (independent recurring-regime clusters over disjoint months).** Currently 3
recurring OUT day-clusters vs a 10-cluster floor, all inside one contiguous span. To certify we need
≥10 independent recurring OUT clusters spread across ≥2 *disjoint* calendar months of **non-expiring**
sport (MLB/NBA/NHL regular season, ongoing crypto/econ), i.e. after the World Cup and Wimbledon clear.
**ETA ≈ months** — realistically accrual through ~Aug–Sep 2026 (MLB regular season runs into
September; WC ends ~mid-July). This matches the readiness ledger's standing `persistence (months)`
binding read, now made regime-legible.

## What was built (per item: built / tested / verified)

**Item 0 — Pre-registration** (`reports/PREREG_20260704T191458Z_regime_persistence.md`). Froze the
regime taxonomy (sport_category × calendar-month), the recurring/expiring/unknown type rules, the edge
metric (matched cat×band baseline, event super-key, flat-shares, cluster-robust LB), the persistence
bar (PERSIST_MIN_CLUSTERS=10, TRANSFER_MIN_REGIMES=2, MARGIN=3%, perm null 1000×), the net-after-tax
rule, and the verdict ladder. Every instrument cites it. *Verified:* every downstream constant traces
here; one correction re-registered (below), never a silent tune.

**Item 0b — Prereg ADDENDUM** (`reports/PREREG_20260704T192839Z_..._ADDENDUM.md`). Building leg (b)
revealed the frozen transfer null was mechanically wrong: a regime-label permutation on transfer-COUNT
*inflates* the null (permutation spreads a strong edge across all pseudo-regimes), so an
upper-tail "beat at p≤0.05" is **impossible for a genuinely distributed edge** (confirmed: real 3,
null 3 every draw, p=1.0). Re-registered — same mechanism, corrected DIRECTION: the null is a
**concentration guard** (`p_conc` = frac null ≤ real; a concentrated one-lucky-regime edge sits in the
LOWER tail). Re-registered BEFORE any real verdict (today's read is decided by leg (a) + concentration,
not leg (b)), so it cannot cherry-pick. *This is the honesty story of the run — a frozen constant
found wrong was re-frozen in the open, not quietly edited.*

**Item 1 — `regime_classify.py`** (NEW). Deterministic `classify_regime → (regime_id, regime_type)`,
reusing `market_taxonomy.category` (no new sport bucket). *Tested:* `--selftest` (12 cases: WC→expiring,
regular-season→recurring, playoff→expiring, tennis/esports→unknown, EPL/KBO→recurring, determinism).
*Verified live:* the archive audit correctly classifies soccer=World Cup and tennis=**Wimbledon**
(caught from the market titles, not just my conservative default) as EXPIRING; recurring pool = mlb /
nba-cbb (all thin; politics reclassified EXPIRING post-audit — one-off primaries). A human can eyeball
every edge case in the printed audit.

**Item 2 — `regime_edge.py`** (NEW). Per sport×month regime: matched-baseline surplus (byte-identical
to softness_map), cluster count + CR-LB (effective_n), regime_type, net_taker column, and TWO
concentration lenses — EDGE (event grain) vs EXPOSURE (capital/signal grain) — plus breadth. *Tested:*
`--selftest` (soccer-only edge → high concentration; 3-recurring-regime edge → low; cluster count =
day-clusters not signal count; empty arm graceful). *Verified live:* reconciles the "soccer-carried"
prior (71% capital) with the honest event-grain edge (57% expiring, spread HHI 0.15).

**Item 3 — `regime_persistence.py`** (NEW; extends persistence_tracker). Temporal recurring-OUT leg +
leave-one-recurring-regime-out transfer with the corrected concentration-guard null; verdict on
recurring regimes only. *Tested:* `--selftest` exercises all four verdicts (PERSISTS / SOCCER-ARTIFACT
/ PENDING / REFUTED) + empty arm. *Verified live:* SOCCER-ARTIFACT, with the full null distribution
reported.

**Item 4 — `regime_net_edge.py`** (NEW). gross → net_taker → net_maker (δ=0¢/5m adverse-selection gap)
per regime, in fee=2% and fee=0 columns, net_positive iff cluster-robust LB>0. *Tested:* `--selftest`
(+8% gross nets positive; +3% gross under a 5¢ spread nets negative; maker avoids the wide spread;
fee=0 ≥ fee=2%). *Verified live (post-audit, small-cluster t):* 1–2 recurring regimes net-positive
after taker tax (snapshot-dependent), all on sub-floor cluster counts.

**Item 5 — `readiness_ledger.py`** (EXTEND). Regime-aware persistence GO-gate `current`/`needs` (bar
UNCHANGED — still NOT_MET / months) + a new informational per-regime panel (status / edge-LB /
net-after-tax / net_positive + concentration + breadth). *Tested:* `--selftest` adds fixture-JSON
checks for both pure helpers (rewire keeps the frozen bar; panel excludes expiring regimes; graceful
when artifacts missing). *Verified live:* board headline still `NOT-YET`, binding = `persistence`
(months); panel renders the 5 recurring regimes.

**Item 6 — `independence_sizing.py`** (NEW, STRETCH, REPORT-ONLY). Within-day N_eff vs nominal at two
grains (EDGE residual vs P&L raw swing), and whether the 13%/day cap is sized to independence. Reuses
portfolio_concentration match_key + icc/n_eff. *Tested:* `--selftest` (sub-market-stacked day →
N_eff≈matches; distinct games → N_eff≈nominal; ordering; high-inflation → SIZE-TO-N_eff rec).
*Verified live:* the favorite arm rarely game-stacks (median inflation **1.0×**) → the 13%/day cap is
≈ well-sized to independence **on this record** (record-specific caveat; re-check as multi-game slates
grow). Consistent with — not contradicting — the broader "size the GAME" correlated-risk finding
(that is game-level exposure; this arm mostly fires one market per game). **Deploys/changes nothing.**

**Item 7 — DO NOT BUILD.** Nothing armed, sized, or flipped. Verdict is not PERSISTS-NET (as expected);
the correct next action is Tue-gated accrual, NOT an autonomous build. Stopped.

## How verified end-to-end
Every script passes `--selftest`; every live run reads the real DB read-only and writes only additive
JSON artifacts (`reports/regime_edge.json`, `regime_persistence.json`, `regime_net_edge.json`,
`independence_sizing.json`, and the extended `readiness_ledger.json`). Full chain re-run on one
consistent DB snapshot before this report. No migration added (`ls migrations/` highest = 039,
untouched). `PILOT_ARMED` unset, `EARN_DEEP_SHARPS` false, alert path untouched, `main` never
merged/rebased.

## Honest limitations (so a reviewer isn't misled — completed post-audit)
1. All recurring data sits in one **contiguous** 6-day span; the calendar-month regime split
   (mlb|2026-06 vs mlb|2026-07) yields "2 disjoint regimes" that are really adjacent days — the
   `≥2 disjoint recurring regimes` bar is technically satisfiable by contiguous months, but leg (a)'s
   10-cluster floor (unmet: 3) is the real gate and is robust to this. Noted, not hidden.
2. **Leg (b) is decorative on this data** (audit finding, now fixed): its regime-permutation null
   cannot fire (min p_conc ≈ 0.22) and the beat-null cannot pass, so leg (b) is a RAW "≥2 transfer"
   count, not a passed test — and under correct small-cluster t the count itself is snapshot-fragile
   (1–2). It is immaterial to the verdict (consulted only if leg (a) PASSes, which is PENDING).
3. **Small-cluster inference** (audit finding, now fixed): LBs use t(G−1), not normal z. The pooled
   edge survives (t-LB ≈ +2.7%); any G=2 per-regime clearance/net-positive claim flips negative under
   t(1)≈6.31, so those informational counts drift with the snapshot. Never load-bearing (all sub-floor).
4. **Leg (a) baseline leakage** (audit finding, now fixed): the temporal baseline now uses IN-period
   blind only. The old full-record baseline deflated the OUT edge (benign) but would have contaminated
   the certification LB once ≥10 clusters accrue.
5. The `SOCCER-ARTIFACT` **label** reflects capital exposure (71% soccer); by EDGE MASS the carrier is
   tennis/**Wimbledon** (~67%) vs soccer (~21%). The verdict enum is a frozen ladder rung; the
   substance is "expiring-tournament-carried."
6. `proven_router` has ~0–1 resolved events → reported as empty/PENDING, not analyzed. Favorite is the
   only arm with real evidence.

## Before certification (Aug–Sep accrual) — the audit's must-fix list, status
- **DONE** small-cluster t(G−1) inference — this was the one fix flagged as *must-land-before-cert*
  because at ≥10 clusters the LB becomes the binding PASS gate.
- **DONE** leg (a) leak-free IN-period baseline — would otherwise contaminate the certification LB.
- **DONE** leg (b) honest labeling; classifier one-off-election fix; Wimbledon-vs-soccer label.
- **OPEN (by design)** the binding constraint itself: ≥10 independent recurring OUT clusters across
  ≥2 disjoint (non-contiguous) months of non-expiring sport. ETA ~months. Nothing to build — accrue.

## Handback
Branch `feat/regime-persistence` is left for review — **do not merge** without a look (a `main` HEAD
advance auto-deploys). The reviewing chat (or Tue) merges → autoupdater deploys the read-only
instruments. No real-money action is warranted today; the win condition (a loud, correct
"it's expiring-carried, here's exactly how many months of recurring-regime data until we can tell")
is met.
