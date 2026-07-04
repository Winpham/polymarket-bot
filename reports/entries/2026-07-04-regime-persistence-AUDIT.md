# AUDIT — Regime-Persistence deliverable (unbiased, independent)

**Date:** 2026-07-04 (UTC) · **Auditor:** independent (did not build this; zero stake in the verdict) ·
**Target:** branch `feat/regime-persistence` @ `e362978` (8 commits off `8cb9fab`, NOT merged) ·
**Posture:** read-only on the deliverable, paper-only, belief-blind (my numbers before their prose).
**Method:** fresh re-derivation code (`audit/rederive.py`, `attacks.py`, `stability.py`) reading the raw
DB, importing ONLY branch-unchanged primitives, never the `regime_*` scripts. Prereg: `audit/AUDIT_PREREG_20260704T195936Z.md`.
**Snapshot:** DB drifted +11 favorite signals since the committed JSON (275→286 resolved); all
re-derivation is drift-accounted.

---

## THE SINGLE MOST IMPORTANT FINDING

**The SOCCER-ARTIFACT verdict is independently reproduced and survives every attack I could mount.**
Every headline number reproduces within tolerance from scratch; the verdict is robust across 12/13
defensible researcher-DoF configurations; the classifier's debatable calls (esp. tennis→expiring) turn
out to be *evidence-based and correct*, not conservative artifacts; and the flagship suspicion — the
mid-run prereg change to leg (b) — is a **mathematically legitimate correction that is provably
immaterial to the verdict**, not a goalpost move. This is a rigorously-earned CONFIRM, not a
rubber-stamp: the attacks below are the ones that failed.

The audit is **not** a clean bill of health, though. Three real defects exist — all in *informational
sub-claims*, none load-bearing for the top verdict, and the report discloses some but not all of them:
1. **Small-cluster inference is overstated** (normal z=1.96 used where t(G−1) is required on G=2–6
   clusters). The "2 recurring regimes net-positive" collapses to **1** under correct inference; the
   "+12% recurring-OUT LB" is **+9%** under t(2). **Not disclosed** in the report's limitations.
2. **leg (b) is fully decorative on this dataset** — its permutation guard is mathematically incapable
   of firing (min achievable p_conc = 0.102 > 0.05) and the original beat-null cannot pass either
   (p=0.425), so leg (b) reduces to a raw "≥2 regimes transfer" count. The report *half*-discloses this
   (limitation 2) but still prints "leg (b) = PASS" as if a test were passed.
3. **A minor classifier bug**: `politics/elections` is hardcoded recurring, but the two political
   markets are one-off Colorado primaries (substantively expiring). Immaterial today (tiny mass,
   doesn't clear/transfer) and — notably — fixing it *raises* the expiring share (0.566→0.585),
   *reinforcing* SOCCER-ARTIFACT.

**Severity calibration (pre-committed in the audit prereg):** all three change *labels or informational
counts*, none change the *action* (SOCCER-ARTIFACT and PENDING both mean "not certifiable, real money
OFF, accrue for months"). Overall: **TRUST-WITH-MINOR-FIXES**.

---

## PHASE 1 — Independent re-derivation (agreement matrix)

Reproduced from raw DB with my own pipeline (`audit/rederive.py`). "committed" = the branch's JSON
(built at 275 favorite signals); "mine" = live snapshot (286). Both collapse to **92 events / 6
day-clusters** — the +11 signals fell into existing match keys, which is why agreement is near-exact.

| # | Claim | Committed | My re-derivation | Verdict |
|---|---|---|---|---|
| C1 | Pooled favorite surplus | +9.73% | **+9.73%** | MATCH |
| C2 | Pooled CR LB (z=1.96) | +2.45% | **+2.46%** | MATCH |
| C3 | net_taker | +5.17% | **+5.18%** | MATCH |
| C4 | Expiring edge-mass share | 56.56% | **56.58%** | MATCH (>50%) |
| C5 | Capital exposure top sport | soccer 71.33% | **soccer 71.33%** | MATCH (exact) |
| C6 | Recurring regimes clearing 10-cluster floor | 0/5 | **0/5** | MATCH |
| C7 | Breadth | 11 (5 rec / 6 exp) | **11 (5/6)** | MATCH |
| C8 | leg(a) temporal | PENDING; 3 cl, +19%, LB +12% | **PENDING; 3 cl, +19.0%, LB +12.4%** | MATCH |
| C9 | leg(b) transfer | 2/2, p_conc 0.92, PASS | **2/2, p_conc 0.92, PASS** | MATCH |
| C10 | Net-positive recurring regimes | 2 (mlb, nba/cbb) | **2 under z; 1 under t(G−1)** | MATCH (z) / see Phase 3.4 |
| C11 | VERDICT | SOCCER-ARTIFACT | **SOCCER-ARTIFACT** | MATCH |
| C13 | leg-(b) change immaterial to verdict | true | **true (SOCCER-ARTIFACT under both nulls)** | MATCH |

**Zero DIVERGE, zero CANNOT-REPRODUCE.** The spine of the deliverable is faithfully reproducible.

## PHASE 2 — Prereg-integrity / goalpost audit (flagship)

**What changed (ADDENDUM):** leg (b)'s permutation null flipped from an UPPER-tail "beat"
(`p = frac(null ≥ real) ≤ 0.05`) to a LOWER-tail "concentration guard" (`p_conc = frac(null ≤ real)`,
flag if <0.05). The transfer statistic, N_PERM=1000, and seed were unchanged — only the tail/direction.

**Mechanism is legitimate (reproduced).** I built a synthetic edge present equally in 3 recurring
regimes: real transfer count = 3, null distribution = {3: 1000}, **p_upper = 1.000**. This exactly
reproduces the addendum's claim — label-permutation *spreads* a distributed edge's mass across
pseudo-regimes, so a genuinely distributed edge sits at p≈1.0 and can *never* reach the upper tail. The
original null was mechanically incapable of certifying a distributed edge. The correction is honest.

**Materiality claim is TRUE (verified by code trace + recompute).** In `verdict_ladder`, leg(b)'s pass
is consulted only in the `a_pass AND b_pass → PERSISTS` branch. leg(a) is PENDING, so `a_pass` is False
and `b_pass` is never reached; SOCCER-ARTIFACT is decided by `rec_below_floor AND expiring_carried`.
Recomputing the full ladder under the ORIGINAL upper-tail null → **still SOCCER-ARTIFACT** (C13). So
"immaterial to the overall verdict" is confirmed. And because the verdict never depended on leg(b),
there was no cherry-picking incentive the change could have served.

**But leg (b) is decorative on this data (my addition to the builder's disclosure).** Given the real
null distribution {0:102, 1:473, 2:345, 3:77, 4:3}, the **minimum achievable p_conc across ANY real
count is 0.102** (at real=0) — so the concentration guard **can never fire**. And the original beat-null
gives p_upper=0.425 — it can never pass. Both directions of the permutation null are non-discriminating
here; leg (b) collapses to "raw count ≥ 2". The report's limitation 2 discloses the "not a beat" half
but not that the guard also cannot fail, while still headlining "leg (b) = PASS."

**Verdict: HONEST MECHANICAL CORRECTION, not a goalpost move.** The one fair criticism is presentational
— printing "leg (b) PASS" for a test that on this data is incapable of failing.

## PHASE 3 — Validity attacks

**3.1 Classifier (hand-checked against DB titles).** My most promising verdict-flip vector — and it
FAILED, vindicating the builder:
- **tennis → expiring is CORRECT, not a conservative default.** Every tennis title literally contains
  "wimbledon" (e.g. `"wimbledon atp: marin cilic vs daniil medvedev"`); Rule E's `wimbledon` keyword
  fires per-event. These *are* Wimbledon (bounded) matches. The report's "caught Wimbledon from the
  titles" is verified. Reclassifying the *category* tennis→recurring does NOT move the share (0.566),
  because the per-event keyword keeps them expiring.
- **soccer → expiring is CORRECT** — 202/202 soccer markets are World Cup (`fifwc`).
- **esports → expiring (via unknown) is substantively correct** — the LoL markets are Mid-Season
  Invitational (a bounded tournament).
- **politics → recurring is WRONG but immaterial** — the two political markets are one-off Colorado
  Democratic primaries (substantively expiring). This is a genuine instance of the exact "expiring
  mislabeled recurring" anti-pattern the prereg warns about, but the mass is tiny (2 events, doesn't
  clear the floor, doesn't transfer), and correcting it *raises* the expiring share to 0.585 —
  reinforcing the verdict. Latent bug for future political data; harmless today.

**3.2 Baseline byte-identity.** Reproduced `regime_edge._matched_baseline` vs the softness_map
convention: 51 cells, **max cell-mean difference = 0.00e+00 → BYTE-IDENTICAL**. Confirmed.

**3.3 Leakage / look-ahead.** The matched baseline in leg(a) is built from the FULL-record blind pool
(including OUT-period rows) — a real, if mild, look-ahead. I rebuilt a strictly leak-free baseline
(IN-period blind only) and recomputed the recurring-OUT surplus: full-record **+19.0%** vs leak-free
**+20.6%** (Δ +1.5pp). The full-record baseline makes the OUT edge *more conservative*, not inflated,
and leg(a) is PENDING (3 < 10 clusters) either way. **Real but non-load-bearing, and biased against the
edge.** Not disclosed in the report (LOW — since it understates rather than inflates).

**3.4 Small-cluster statistics (the real methodological defect).** Every LB uses normal z=1.96 on tiny
G. Recomputed with one-sided-95% t(G−1):

| Claim | z=1.96 | t(G−1) | survives? |
|---|---|---|---|
| Pooled edge LB (G=6, t=2.015) | +2.46% | **+2.25%** | YES — the pooled edge is real |
| Recurring-OUT LB (G=3, t=2.353) | +12.4% | **+9.2%** | positive (informational; leg-a PENDING regardless) |
| mlb\|2026-07 net-positive (G=4, t=2.353) | LB +4.9% | **+2.5%** | YES |
| nba/cbb\|2026-07 net-positive (G=2, t=6.314) | LB +12.2% | **−9.6%** | **NO — flips negative** |

So the load-bearing pooled edge (C2) **survives** proper inference, but the "**2** net-positive recurring
regimes" claim is really **1** under correct small-cluster t. This is a genuine overstatement, not
disclosed as a t-vs-z issue — though the report *does* caveat these sit "on power-starved cluster counts
(4 and 2 clusters)" and that PERSISTS-NET is not reached. Non-load-bearing (PERSISTS-NET requires leg-a
PASS, which is PENDING).

## PHASE 4 — Verdict-stability surface

13 defensible configurations (classifier re-calls, both nulls, 4 cutoffs, expiring-threshold 0.4/0.5/0.6):

| Config | expiring share | verdict |
|---|---|---|
| frozen baseline | 0.566 | SOCCER-ARTIFACT |
| tennis→recurring | 0.566 | SOCCER-ARTIFACT |
| politics→expiring | 0.585 | SOCCER-ARTIFACT |
| esports→recurring | 0.508 | SOCCER-ARTIFACT |
| tennis+esports→recurring | 0.508 | SOCCER-ARTIFACT |
| ORIGINAL (pre-addendum) null | 0.566 | SOCCER-ARTIFACT |
| cutoff 06-30 / 07-01 / 07-02 / 07-03 | 0.566 | SOCCER-ARTIFACT ×4 |
| expiring threshold 0.40 | 0.566 | SOCCER-ARTIFACT |
| **expiring threshold 0.60** | 0.566 | **PENDING** |
| tennis-rec + threshold 0.40 | 0.566 | SOCCER-ARTIFACT |

**12/13 (92%) → SOCCER-ARTIFACT; 1/13 → PENDING** (only when the carried-threshold is raised to 0.60).
The thinnest margin is esports→recurring (share 0.508, still >0.5). No single or double defensible
reclassification crosses 0.50, because the dominant expiring mass (tennis=Wimbledon, soccer=World Cup)
is genuinely bounded. **The verdict is robust.** (Note: the SOCCER-ARTIFACT *label* under-weights that
tennis carries ~3× soccer's edge mass — the substance "expiring-tournament-carried" is right, the
soccer-forward name is cosmetic.)

## PHASE 5 — Compliance & report-honesty

**Compliance — pass, with one precise nit:** `git diff 8cb9fab..HEAD` = 14 files; **0 migrations**
changed (highest 039 untouched); **no** `common/`/`src/`/`crates/` (Rust live-bot) changes; **no**
arming/alert/order lines added; **no** deliverable script writes to the DB or places orders (read-only
confirmed); `main` never merged/rebased (linear history, 0 merges, `8cb9fab` is an ancestor of HEAD); all
**6 `--selftest`s PASS** and genuinely exercise all four verdict branches (not fixture-rigged). Reuse is
faithful: `regime_edge._matched_baseline` is logically byte-identical to `softness_map`, and
`PERSIST_MIN_CLUSTERS=10 / MARGIN=0.03 / Z=1.96` are genuinely `import`ed from `persistence_tracker`, not
re-hardcoded. **The one breach:** the "additive-only (revert = delete)" invariant is *literally* violated
— `scripts/readiness_ledger.py` (+139/−10) and `reports/readiness_ledger.json` are **modifications** to
pre-existing files, not new files, so a clean revert needs `git restore`, not a delete. LOW severity:
honestly labeled "EXTEND: Item 5" in the commit log, confined to an offline reporting script, and the
persistence GO-gate bar is preserved (still `NOT_MET`/`months`).

**Report-honesty trace:** every quantitative claim in the report traces to an artifact and reproduces
(Phase 1 + net_edge n_recurring_net_positive=2, readiness verdict = not-eligible / 2-of-4 gates /
binding=persistence/months / independence median inflation ≈1.0×). **Limitations completeness:** the
report discloses the contiguous-span issue, leg(b)'s "distribution-not-beat" nature, and the empty
proven_router arm. It **omits**: (a) the small-cluster t-vs-z overstatement, (b) that leg(b)'s guard is
incapable of firing on this data, (c) the full-record-baseline look-ahead (benign-direction). These are
the fair report-honesty gaps.

## PHASE 6 — Stance-diverse synthesis & confidence-banded verdict

Five isolated read-only reviewers (statistics / leakage / prereg-integrity / compliance / alt-verdict),
none seeing the others' work, each returning its single harshest defensible finding. **All five
independently reproduced my findings and overturned nothing**; three sharpened them.

- **Statistics/small-N (CONFIRMED):** normal z=1.96 on G=2–6 clusters violates the module's own
  effective_n guidance. Backing out se from committed LBs and applying t(G−1): pooled edge survives
  (+2.25%), recurring-OUT survives (+9.2%), mlb net-positive survives (+2.5%), but **nba/cbb|2026-07
  (G=2, t(1)=6.314) flips both its net-positive LB (+12.2%→−9.6%) AND its held-gross transfer LB
  (+15.9%→−5.5%)**. So under correct inference the "2 net-positive" → **1**, and leg(b)'s transfer count
  → **1 < 2 → leg(b) FAILS**. Every correction strengthens non-certification. Does NOT overturn
  SOCCER-ARTIFACT — reinforces it.
- **Leakage (CONFIRMED, non-load-bearing):** the leg(a) baseline is built from the full blind pool;
  ~43% of those rows are post-cutoff. It **deflates** the OUT edge (+19.3% leaky vs +20.6% leak-free),
  and leg(a) is PENDING on the 3<10 cluster gate regardless. **Latent risk flagged:** once ≥10 recurring
  OUT clusters accrue (the Aug–Sep certification path), the LB *becomes* the binding PASS gate and this
  same leak would then contaminate the certification LB — fix before certification.
- **Prereg-integrity (HONEST-CORRECTION):** only the tail direction changed; the "distributed edge can't
  reach the upper tail" claim is true (synthetic → p_upper=1.000); the change is provably immaterial to
  the verdict (leg(b) never consulted while leg(a) PENDING). Sharpenings: (i) the addendum's stated
  *causal mechanism* ("null inflates above real") is contradicted by its own artifact (null_mean 1.406
  < real 2 — permutation actually *deflates* the count here), though the conclusion holds; (ii) leg(b)
  is doubly inert — the guard can't fire (min p_conc 0.102) and the old beat-null needed count 4 (real
  is 2); (iii) **latent goalpost risk**: the correction traded an *unpassable* test for an *unfailable*
  one, lowering the *future* PERSISTS bar — the report should call leg(b) a near-tautological pass.
  Not self-serving today (an easier leg(b) pushes toward PERSISTS, which the builder called a red flag).
- **Compliance (PASS + one nit):** baseline byte-identical, constants genuinely imported, read-only,
  `main` untouched, selftests exercise all four branches. The literal "additive-only (revert=delete)"
  invariant is breached by the `readiness_ledger` *modification* (+139/−10) — LOW, honestly labeled.
- **Alt-verdict (ROBUST):** ~12/12 defensible configs → SOCCER-ARTIFACT; the only label-flip
  (tennis→recurring) is refuted by the raw titles (Wimbledon). Two decisive additions: (i) **the action
  is structurally unflippable** — only 6 UTC days exist vs a 10-cluster floor, so `recurring_cleared`
  is pinned at 0 under *every* DoF and PERSISTS is unreachable by construction; SOCCER-ARTIFACT and
  PENDING are the only possible labels and both mean "real money OFF." (ii) The `|mass|` concern does
  NOT bite — there are no negative-surplus *expiring* regimes (the only negative regime is *recurring*),
  so abs() *dilutes* the expiring share; signed-positive-mass share is *higher* (0.605). And the
  **label is quantifiably misleading**: tennis/Wimbledon carries **68.3%** of expiring edge mass vs
  soccer **22.1%** — it is a Wimbledon artifact by edge mass; "soccer" only leads on capital exposure.

**Harshest surviving finding:** the small-cluster inference overstatement (z vs t) — which, corrected,
*removes* the deliverable's only two certification-favorable signals (2nd net-positive regime; leg-b
PASS) and therefore makes the non-certification verdict strictly stronger. No finding, from any lens,
moves the actionable conclusion.

### Confidence-banded verdict per claim
| Claim | Band |
|---|---|
| C1 pooled surplus +9.7% | **CONFIRMED** |
| C2 pooled LB +2.5% (survives small-cluster t) | **CONFIRMED** |
| C3 net_taker +5.2% | **CONFIRMED** |
| C4 expiring share 57% | **CONFIRMED** |
| C5 exposure 71% soccer | **CONFIRMED** |
| C6 0/5 recurring cleared | **CONFIRMED** |
| C8 leg(a) PENDING | **CONFIRMED** |
| C9 leg(b) PASS | **OVERTURNED as evidence** — decorative (null can't fire); FAILS (count 1<2) under correct small-cluster t. Immaterial to verdict. |
| C10 "2 net-positive recurring" | **OVERTURNED → 1** under correct small-cluster t (non-load-bearing) |
| C11 VERDICT = SOCCER-ARTIFACT | **CONFIRMED** — robust 12/13 by DoF, and the *action* is structurally unflippable (6 days < 10-cluster floor) |
| C12 binding = persistence, months | **CONFIRMED** |
| C13 prereg change immaterial to verdict | **CONFIRMED** |

### Overall
**SOCCER-ARTIFACT STANDS** — independently reproduced, robust across defensible researcher-DoF, and
resting on a classifier whose debatable calls are confirmed by the raw market titles. More strongly:
the *actionable* conclusion is **structurally unflippable** — with only 6 UTC days of favorite data
against a 10-cluster certification floor, no recurring regime can clear the floor under any baseline,
event key, cutoff, or reclassification, so PERSISTS is unreachable by construction and both admissible
labels (SOCCER-ARTIFACT / PENDING) mean "not certifiable, real money OFF."

The instruments are **TRUSTWORTHY-WITH-MINOR-FIXES** for the months-long accrual watch they power.
Recommended fixes, all **non-blocking** (none changes today's action):
1. **Small-cluster inference (do before certification):** replace normal z=1.96 with t(G−1) for all
   reported LBs, or explicitly label them normal-approx. This is the one fix that *must* land before the
   Aug–Sep certification path, because at ≥10 clusters the LB becomes the binding PASS gate.
2. **leg(b) honesty:** re-state as a raw "≥2 recurring regimes transfer" count; disclose that its
   permutation null cannot discriminate on current data (guard unfailable, beat-null unpassable), and
   that under correct small-cluster t the count is 1, not 2. Do not headline it as "PASS."
3. **Leakage:** build the leg(a) OUT baseline from IN-period (or rolling pre-fire) blind only — benign
   today (deflates the edge) but contaminates the certification LB once the floor is reached.
4. **Classifier:** treat one-off elections (primaries) as expiring; harmless today, latent smuggling risk.
5. **Label:** rename the verdict "expiring-carried (Wimbledon/tennis-dominant, 68% of edge mass)" — the
   "soccer" name reflects capital exposure, not where the edge mass actually sits.

**Bottom line:** a rigorously-earned CONFIRM. The builder's stated win condition (a loud, correct
"it's expiring-carried, here's exactly how many months of recurring data until we can tell") is met and
survives adversarial re-derivation. The three real defects are all in certification-favorable
sub-claims, and correcting every one of them makes the non-certification verdict *stronger*, never
weaker. Real money stays OFF; months of independent recurring-regime accrual remain the binding
constraint. **Do not merge without applying at least fix (1) if the branch is intended to power
certification; the read-only instruments are otherwise safe to merge.**
