# FORGE PLAN — Specialist Selection (slice-aware tailing)

**What changes.** Today a trader votes with ONE wallet-level weight regardless of the market's
category, even though `trader_slice_scores` already computes their per-cell edge and throws it away
at selection time (`0x032eb…` soccer **+0.156** / MLB **−0.083**, both real, both surfaced only in
`best/worst_slices`, neither read at `consensus.rs:481`). This plan wires the per-(trader × cell)
edge into the vote weight via a **continuously-pooled** per-cell multiplier, measures every cell
against a **favorite-residual cell-blind baseline**, and gates the whole thing behind an
orthogonality-vs-favorite BAR and a forward label-permutation test. Everything is silent,
default-OFF, `strict` byte-identical, and promotes **nothing** until a forward gate clears AND Tue
approves. Real money stays gated on the unchanged pilot bar (N≥50 events, ≥5 regimes).

## Why this isn't congregation-2 (binding frame — DECISIONS.md D2 / charter §0.5)

The named adversary: a per-SPORT specialist book was found **DEAD** on 2026-06-30 — 0 wallets cleared
`lo>3%` at N≥30 on a per-sport slice at every cut, because of (a) the sample floor (edge-showing
wallets were sub-30-event), (b) thin capture margin, and (c) slate collapse (~2 adjacent WC-soccer
days, ≈89% of resolved buys). A second adversary: `elite_fresh_fav ⊂ favorite` (adds ~0
diversification) and the reliability program's **0/12 strategies diversify favorite**. Any per-cell
book that (i) certifies on a thin cell, (ii) measures surplus against a cross-sport baseline so a
favorite-heavy sport looks skilled, or (iii) fires only on favorite-band events is congregation
wearing a new name.

Four structural changes make per-(trader×cell) a *different bet*, not a rerun:

1. **The profiling floor has materially lifted.** 78 wallets now clear ≥30 distinct resolved events
   over a real **2022-12-15 → 2026-07-03** archive (1.04M fills, 5,922 distinct resolved events) —
   not one WC weekend. Item 1 (25 floor) lifts more, for *profiling reach only*.
2. **The baseline becomes a favorite-residual (Item 2).** The incumbent blind is keyed on `band`
   ONLY (`consensus.rs:1470`), so `0x032eb`'s soccer +0.156 is "soccer beats the fleet's per-*band*
   average" — a favorite-heavy sport rides the cross-sport band mean (favorite-in-disguise). We
   generalize the blind to `(sport, band)` with a **cascade fallback** so surplus is always measured
   vs blind play in the SAME cell, and because `favorite` IS the band region 0.65–0.98, blinding
   within band subtracts favorite-loading *at the verdict*.
3. **Thin cells borrow strength instead of being discarded (Item 3).** The congregation death was
   *sub-30 cells thrown away*. Instead of a hard cell-verdict switch (which either discards a thin
   soccer cell or lets it swing a vote to its full multiplier on a 2-day slate), we **partial-pool**
   the continuous multiplier toward the wallet's overall multiplier by `N_cell/(N_cell + K)`, K a
   FIXED const. A thin cell moves the weight only a fraction of the way; at N=0 the weight IS the
   wallet-level behavior we already ship. This removes cell *selection* from the live layer — the
   live arm is one hypothesis, not a ~thousands-way search.
4. **The binding control is forward cross-window persistence + orthogonality-vs-favorite (Items
   4–5), not in-sample FDR.** The per-sport book never ran a forward label-permutation test or an
   orthogonality gate against `favorite`. We require both: a survivor must post `≥ MIN_INDEP`
   independent (non-favorite) events (G1), a favorite-orthogonal residual edge (G2), residual
   independence (G3), survive `portfolio_constructor.py`'s marginal-LB drop, AND clear a forward
   `(cell×day)` label-permutation at `p ≤ 0.01` on ≥2 disjoint windows. On today's backfill this
   correctly returns **PENDING/null** — the honest D2 reality, automated.

So the burden of proof is discharged *by construction at the verdict* (favorite-residual baseline),
*by construction at the live layer* (pooling, no selection), and *by a forward gate that beats both
favorite-only and global `trust_weighted`* (the WS-5 BAR). Nothing here can false-promote; the value
today is a mechanism that can finally REACH a specialist and a gate that can HONESTLY judge one.

---

## Items

Dependency-ordered. GAP-4 (multiplicity) is the discipline threaded through Items 3–5; its resolution
is recorded in each.

### Item 1 — `TrustParams{min_events:25}` floor split (GAP-3) — SHIP FIRST, isolates the pilot bar

**Tag: NEW-DELTA** (dossier decision (a); RUN-TRADER-PROFILING kept the 30 floor via
`PromotionParams::default`). Both Direct and Rethink converge on the identical design — adopt it.

**Before** (verified). `trust_verdict` (`trader_trust.rs:118`) calls
`trust_verdict_with(slices, &PromotionParams::default())`, and `PromotionParams::default().min_events
= 30` (`promotion.rs:110`) — the **same struct** `honest.rs::pilot_verdict` builds for its
`min_events:50` pilot floor (`honest.rs:100-104`). The trust floor and the real-money floor are
entangled through one default: naively lowering 30→25 risks moving any caller that reads that default.

**After.** `trust_verdict` reads a named `TrustParams{min_events:25, margin:0.03, alpha:0.05}`;
`honest.rs:100` still constructs `PromotionParams{min_events: th.min_events(=50), …}` untouched. A
25-event hairline slice still reads **Indeterminate** (widened CI is the point).

*Concrete verdict.* A `sport=cs2` cell of exactly **25** distinct events, surplus `+0.04`, sd `0.10`,
`n_days=12`, `n_comparisons≈6`: floor-25 admits it to evaluation; then
`eff_n=12`, `se=0.10/√12=0.0289`, `α/6=0.0083`, `z≈2.64`, `lo=0.04 − 2.64·0.0289 = −0.036` ⇒ **still
Indeterminate**. 25 widens *eligibility*, not *false-positives*.

**Implementation.**
```rust
// promotion.rs — adjacent to PromotionParams. A DISTINCT type, not a PromotionParams alias.
#[derive(Debug, Clone)]
pub struct TrustParams { pub min_events: i64, pub margin: f64, pub alpha: f64 }
impl Default for TrustParams {
    fn default() -> Self { Self { min_events: 25, margin: DEFAULT_PROMOTION_MARGIN, alpha: 0.05 } }
}
impl TrustParams {
    /// Adapter so trust_verdict_with reuses the EXACT surplus_bounds machinery —
    /// no new estimator, probit stays private (promotion.rs:33).
    pub fn into_promotion(&self) -> PromotionParams {
        PromotionParams { min_events: self.min_events, margin: self.margin, alpha: self.alpha }
    }
}
```
`trader_trust.rs:119`: `trust_verdict_with(slices, &TrustParams::default().into_promotion())`.

**Integration points.** `promotion.rs:~120` (new type) · `trader_trust.rs:118-119` (one call-site
swap) · `honest.rs:100` **explicitly NOT touched**.

**Power / Multiplicity / Forward-weeks.** 25 lifts more wallets past the *profiling* floor (78 clear
≥30; more at 25) — a power gain for profiling only; the widened CI means fewer certify, so no free
promotions. Zero pilot impact (the entire point). Forward-weeks unchanged.

**Non-regression proof.** NEW `trust_floor_is_25_pilot_floor_still_50` (asserts
`TrustParams::default().min_events==25 && PilotThresholds::default().min_events==50` — floors
independent). NEW `hairline_25_event_slice_reads_indeterminate` (the numbers above ⇒
`TrustVerdict::Indeterminate`). Mirror `margin_zero_regression_hairline_surplus_rejected`
(`promotion.rs:473`) and `below_event_floor_never_promotes` (`promotion.rs:340`) for shape.

**Source: DIRECT (= Rethink; both identical).** 6-line adapter + one call-site swap; the pilot gate
is physically a different struct. ADOPT the shared design as-is.

---

### Item 2 — bet_type axis (mig 037) + favorite-residual cell-blind baseline (GAP-2) — makes cells honest

**Tag: SPLIT.** bettype axis = **ADOPT-AS-IS** (RUN-TRADER-PROFILING FORGE_PLAN **Item 2**:
`bet_type_bucket`, migration 037, UNION branch). The per-cell blind = **NEW-DELTA** (dossier decision
(d)). Source seam: Rethink's *favorite-residual* framing (why the baseline neutralizes favorite) +
Direct's *cascade fallback* (how it stays non-regressive). **REFINED.**

**Before** (verified, `consensus.rs:1470` and `_asof:1527`). `blind AS (SELECT band, AVG(a) FROM adv
GROUP BY band)` — 1-D on band. `0x032eb`'s soccer +0.156 is measured vs the cross-sport per-band
average ⇒ a favorite-heavy sport can look skilled purely by band-loading (the leak the congregation
book certified and then lost forward). `trader_fills` has no `bet_type` column (migration 026,
confirmed absent).

**After.** `blind_cell AS (SELECT sport, band, AVG(a) GROUP BY sport, band)` with a **cascade
fallback** to the incumbent band-blind then 0. `surplus_soccer = a − blind[(soccer, b4)]`. Because
`favorite` is the band region 0.65–0.98 (b4/b5), the b5 blind IS "the average bettor on that sport's
favorites" — a specialist who merely rides soccer favorites has `a ≈ blind[(soccer,b5)]` ⇒ surplus ≈
0 ⇒ Indeterminate. **The verdict itself refuses favorite-in-disguise.** A `bettype=spread` cell now
exists so a `+15%-ml / −10%-spread` wallet stops blending.

**Implementation.**

*Schema — migration `037_trader_fills_bettype.sql`* (037 = next free; `ls migrations/` confirms 036
`_initial_atfire_shape.sql` is latest. **Verify 036 is still latest in the ACTIVE trunk before
writing — `wt/*` worktrees carry their own `migrations/` and can collide.**):
```sql
-- 037_trader_fills_bettype.sql — mirror the nullable + COALESCE pattern of `sport`
ALTER TABLE trader_fills ADD COLUMN IF NOT EXISTS bet_type TEXT;  -- NULL ⇒ 'other' at read; no backfill
```

*Capture.* NEW `bet_type_bucket(title, slug) -> String` in `consensus_cycle.rs`, sibling of
`sport_bucket` (`:133`), buckets `moneyline | spread | totals | prop | other` (first-hit-wins,
lower-cased): `spread:`/`-spread`/` +N`/` -N` → spread; `o/u `/`over/under`/`total` → totals;
`to score`/`player`/`assists`/`rebounds`/`props` → prop; `vs`/`moneyline`/`ml`/`to win` → moneyline
(LAST, broadest); else other. Set on the fill in `trade_to_fill` (`consensus_cycle.rs:199`); add
`pub bet_type: Option<String>` to `NewTraderFill` (append after `sport`, don't reorder) + one column
+ one bind to the insert. Unit test mirrors `sport_bucket`'s classifier test.

*Extended CTE — BOTH `trader_slice_scores` (`consensus.rs:1461`) and `_asof` (`:1526`)* (the `_asof`
twin gets the identical `adv`/`blind`/`surp` change; it keeps its `resolved_at < $1` predicate and
still emits only `overall|sport|band` unless a composite is added — see below):
```sql
adv AS (
  SELECT wallet, COALESCE(event_slug, condition_id) AS ev,
         width_bucket(price, 0.0, 1.0, 5) AS band,
         (outcome_won::int)::double precision - price AS a,
         (outcome_won::int)::double precision AS won,
         COALESCE(sport, 'other')    AS sport,
         COALESCE(bet_type, 'other') AS bettype,        -- NEW
         ts
  FROM trader_fills WHERE resolved AND side = 'BUY' AND outcome_won IS NOT NULL
    /* _asof only: */ -- AND resolved_at IS NOT NULL AND resolved_at < $1
),
blind_cell AS ( SELECT sport, band, AVG(a) AS blind_edge FROM adv GROUP BY sport, band ),  -- NEW
blind_band AS ( SELECT band, AVG(a) AS blind_edge FROM adv GROUP BY band ),                -- incumbent, now fallback
surp AS (
  SELECT v.wallet, v.ev, v.band, v.a, v.won, v.sport, v.bettype, v.ts,
         v.a - COALESCE(bc.blind_edge, bb.blind_edge, 0) AS s   -- cascade: cell → band → 0 (NEVER open)
  FROM adv v
  LEFT JOIN blind_cell bc USING (sport, band)
  LEFT JOIN blind_band bb USING (band)
),
tagged AS (
  … existing overall | sport | band [| recency7d | recency30d live-only] branches, now over cell-blind `s` …
  UNION ALL
  SELECT wallet, 'bettype', bettype, ev, a, s, won, ts FROM surp     -- NEW axis
)
```
`TraderSliceStat` (`common consensus.rs:1855`) FromRow order is **unchanged** — bettype is a new
`slice_kind`/`slice_key` VALUE, never a new column (the load-bearing invariant). `n_comparisons`
(`trader_trust.rs:129`) rises by the wallet's populated bettype cells — CONSERVATIVE (only ever
toward Indeterminate).

**Cascade, not COALESCE-to-0 (the load-bearing correction).** The fallback is
`COALESCE(blind_cell, blind_band, 0)`, NOT `COALESCE(blind_cell, 0)`. A thin/empty `(sport,band)`
blind cell degrades to the incumbent per-band blind — never to a raw-advantage baseline. A
COALESCE-to-0 would fail **open** exactly where the baseline is thinnest and re-import the
favorite-in-disguise leak; the cascade preserves the per-band FLB neutralizer as the floor
(§ preservation requirement).

**Granularity is staged.** Ship the blind keyed at `(sport, band)`. Add `bettype` to the *blind* key
(`(sport, bettype, band)`) and a composite `cell` slice_kind ONLY after a bettype specialist survives
Item 5 — band-loading is the dominant leak; thinner blind cells buy noise for marginal specificity.

**Integration points.** `migrations/037_*` (new) · `consensus_cycle.rs:~160` (`bet_type_bucket`) ·
`:199` (`trade_to_fill` sets it) · `common consensus.rs:108` (`NewTraderFill` +field) ·
`consensus.rs:1461` and `:1526` (`adv`+blind rewrite + bettype UNION, both queries).

**Power / Multiplicity / Forward-weeks.** The `(sport,band)` blind splits N — thin cells fall back to
`blind_band` (documented). Multiplicity: +1 comparison per wallet per populated bettype cell
(bounded, conservative). Forward-weeks: **none** — a re-measurement of existing history, not a new
accrual clock.

**Non-regression proof.** NEW `cell_blind_falls_back_to_band_blind_when_thin` (a `(sport,band)` cell
absent from `blind_cell` yields the SAME surplus as today's band-blind — proves the generalization
never NULLs and never weakens the FLB neutralizer). NEW `single_sport_wallet_cell_blind_equals_band`
(a wallet whose fills are all one sport ⇒ `(sport,band)` blind == `band` blind ⇒ surplus unchanged).
`strict` never reads slice surplus ⇒ unaffected.

**Source: REFINED (Rethink residual framing + Direct cascade fallback).**

---

### Item 3 — Pooled per-cell vote weight (GAP-1) — the named task — SILENT, env-gated, inert

**Tag: NEW-DELTA** reframing **ADOPT-AS-IS** RUN-TRADER-PROFILING FORGE_PLAN **Item 4** (`SliceCtx` +
per-vote cell weight + silent arm). We adopt Item 4's plumbing verbatim but replace its **hard
cell-verdict switch** with **continuous partial pooling**. **Source: RETHINK (pooled multiplier),
REFINED for minimalism + the forward BAR.** Depends on Items 1–2.

**Before** (verified). `WeightMode::TrustWeighted` sums `v.earned_quality` (`consensus.rs:481`) — ONE
overall scalar/wallet from `earned_quality(trust, wallet, rank)` (`consensus_cycle.rs:69`), never sees
the market's sport. `0x032eb` MLB BUY and soccer BUY get the SAME overall multiplier (or the
`quality_weight(rank)` fallback when overall is Indeterminate); the −0.083 MLB and +0.156 soccer
cells are discarded at `:481`.

**After** (env `SLICE_POOLED` ON). A soccer market consults `sport=soccer`; an MLB market consults
`sport=mlb`. The vote weight is the wallet's overall multiplier **shrunk toward the cell multiplier by
`N_cell/(N_cell + K_POOL)`**, K_POOL a fixed const:
| vote | cell (verdict) | today | Direct hard-switch | **Pooled (this plan)** |
|---|---|---|---|---|
| `0x032eb` soccer | +0.156, 276 ev, `lo≈+0.09` Trusted ⇒ `m_cell≈1.084` | 1.0 | 1.084 (full swing even if overall Indet.) | `1.0 + (1.084−1.0)·276/(276+40) = ` **1.073** |
| `0x032eb` MLB | −0.083, 89 ev, `hi≈−0.04` Avoid ⇒ `m_cell≈0.967` | 1.0 | 0.55–0.967 | `1.0 + (0.967−1.0)·89/(89+40) = ` **0.977** |

Pooling tempers a possibly-correlated thin cell toward the parent while still reaching it; at N=0 the
weight IS the overall (today's) behavior. `SLICE_POOLED` OFF (default) ⇒ **byte-identical to today.**

**Implementation.**

*Schema/SQL.* None — rides Item 2's cells.

*Rust types* (`consensus.rs` near `TraderVote:30`, `WeightMode:121`):
```rust
// Built once at book assembly from the market row. `sport` is the ONE live axis for v1
// (band is width_bucket(price); bettype is bet_type_bucket(title,slug) — both live-derivable
// and extendable here later. Archetype is NOT live-derivable: it needs the event-wide fill
// distribution, unavailable at single-vote scoring — display/accrual only, per old Item 3.)
#[derive(Debug, Clone)]
pub struct SliceCtx { pub sport: String }

// CellVerdict caches the SAME fields trust_verdict already computes, per cell.
pub struct CellVerdict { pub verdict: TrustVerdict, pub lower_bound: f64,
                         pub upper_bound: f64, pub n_events: i64 }
pub type CellMap = std::collections::HashMap<(String,String), CellVerdict>; // (slice_kind, slice_key)

// TraderVote gains ONE fail-closed field (mirrors earned_quality's contract):
//   pub cell_earned_quality: f64,   // defaults to earned_quality when ctx/flag absent
// WeightMode gains ONE variant:
//   CellPooled,   // rank by summed POOLED per-cell earned quality of the backers
```
`score_market` base match adds ONE arm (`consensus.rs:481`), symmetric to `TrustWeighted`:
```rust
WeightMode::CellPooled => backers.values().map(|v| v.cell_earned_quality).sum(),
```
`probit` stays PRIVATE — pooling is pure arithmetic on `lower_bound`/`upper_bound` already returned by
`trust_verdict`; no z is computed here.

*The pooling fn* (`consensus_cycle.rs`, sibling of `earned_quality:69`):
```rust
/// Per-CELL earned quality, partial-pooled toward the wallet's overall multiplier.
/// K_POOL is a FIXED config const (NOT fitted — a fitted K would leak). Mirrors the
/// already-blessed damp = n/(n+20) seam (consensus_cycle.rs:67-68). Fail-closed ladder:
///   most-specific cell, if verdict ≠ Indeterminate ⇒ pool m_cell toward m_over by N/(N+K)
///   Indeterminate / absent cell / untracked wallet ⇒ m_over (overall path; never zero)
fn slice_pooled_quality(cells: &CellMap, ctx: &SliceCtx, m_over: f64, k_pool: f64) -> f64 {
    if let Some(c) = cells.get(&("sport".into(), ctx.sport.clone())) {
        if !matches!(c.verdict, TrustVerdict::Indeterminate) {
            let m_cell = match c.verdict {                     // EXISTING earned_quality arms
                TrustVerdict::Trusted => (1.0 + c.lower_bound * damp(c.n_events)).clamp(0.5, 2.0),
                TrustVerdict::Avoid   => (1.0 + c.upper_bound * damp(c.n_events)).clamp(0.5, 1.0),
                TrustVerdict::Indeterminate => unreachable!(),
            };
            let w = c.n_events as f64 / (c.n_events as f64 + k_pool);   // partial-pool weight
            return m_over + (m_cell - m_over) * w;             // shrink toward parent
        }
    }
    m_over                                                     // fail-closed
}
// damp(n) = n/(n+20) — factor out the existing earned_quality shrink; NO probit, NO new estimator.
```
`CellMap` is built once per trust refresh by running the **existing** `trust_verdict_with` over each
wallet's `slice_kind=="sport"` rows with the wallet's own `n_comparisons` + `TrustParams` (Item 1).
Add it to the cached `TraderTrust` value (new `cells: CellMap` field, empty ⇒ today's behavior) in
`compute_trust_map`'s sibling — ONE extra pass over the `Vec<TraderSliceStat>` already fetched
(`consensus_cycle.rs:95`); **zero new queries**.

**Integration points.**
- `consensus.rs:481` (CellPooled base arm) · `consensus.rs:~30/:121` (one vote field + one WeightMode
  variant + `SliceCtx`/`CellVerdict`/`CellMap`).
- `consensus_cycle.rs:537` — at the existing `earned_quality` call, when `cfg.slice_pooled`, build
  `let ctx = SliceCtx{ sport: sport_bucket(&v.title,&v.slug) };` (sport_bucket already called at
  capture `:133`) and set `cell_earned_quality = slice_pooled_quality(&trust.get(w).cells, &ctx, eq,
  cfg.k_pool)`; else `cell_earned_quality = eq` ⇒ byte-identical.
- `consensus_cycle.rs:95` `compute_trust_map` — populate `TraderTrust.cells`.
- `consensus_cycle.rs:859` `active_portfolio` — append the silent arm behind `cfg.slice_pooled`:
  `if cfg.slice_pooled { all.push(slice_sport_tail(&base)); }` where `slice_sport_tail =
  StrategyDef{ name:"slice_sport_tail", params:ConsensusParams{ weight_mode:WeightMode::CellPooled,
  ..base.clone() }, alerting:false }`.
- **CRITICAL:** add `"slice_sport_tail"` to the `EXPERIMENTAL` const in `family()`
  (`copy-trading-bot/src/scanner/enrich/mod.rs:339`). `family()` defaults unknown names to `"core"`
  (`:356`) — omitting this silently puts the arm in `strict`'s core Bonferroni family.

**Power / Multiplicity / Forward-weeks.** Power: pooling spends LESS power per cell than a hard switch
(a 25-event cell moves the weight ~38%). Multiplicity: **no per-cell SELECTION at the live layer** —
the weight is a continuous function of the wallet's cells, never an argmax; the arm is **one**
EXPERIMENTAL hypothesis (does pooled weighting beat wallet-level forward), strictly less than Direct's
"consult the winning cell." Forward-weeks: accrues in the EXPERIMENTAL family like any arm; binding
flip = Item 4's forward permutation. No acceleration — honest.

**Non-regression proof.** `SLICE_POOLED` off ⇒ `cell_earned_quality == earned_quality` and
`CellPooled` not registered ⇒ mirror `default_strict_is_non_regressive` (`consensus.rs:1172`) holds
byte-for-byte. NEW `slice_arm_registered_separately_and_silent` (mirror
`trust_arms_registered_separately_and_silent` `:1200`: `slice_sport_tail` absent when off, present +
`alerting:false` when on, `family("slice_sport_tail")=="experimental"`). NEW
`pooled_weight_equals_overall_when_only_overall_data` (wallet with no `sport` cell ⇒
`slice_pooled_quality` returns `m_over` exactly). NEW `pooled_weight_tempers_thin_cell` (the 89-ev MLB
row above ⇒ 0.977, not the full 0.967 swing).

**Source: RETHINK (pooled multiplier), REFINED.** One vote field, one WeightMode variant, K fixed,
fail-closed to overall. It answers "how much do I trust this cell *given its N*?" instead of "which
cell?" — the thin-cell-borrows-strength property is the direct structural answer to the congregation
sub-30-discard death, and it is free (no estimator; K fixed; `probit` private).

---

### Item 4 — Multiplicity-at-scale: three layers, live family dissolved, forward permutation binds (GAP-4)

**Tag: ADOPT-AS-IS** (FORGE_PLAN Item 4 three-layer separation + Item 5 forward permutation) **+
NEW-DELTA refinement** (explicit ×-wallet Bonferroni in the screen; `(cell×day)` strata). **Source:
HYBRID** (Rethink: pooling dissolves the live cell-family; Direct/old-plan: forward-permutation is the
binding control). Depends on Item 3.

**Before.** Bonferroni today is per-wallet-over-its-slices (`n_comparisons` `trader_trust.rs:129`) and
per-arm-over-the-family (`n_strategies` `promotion.rs:208`). Nothing controls 78 wallets ×
(sport×bettype×band×recency) cells × levers (~thousands). Naively certifying every `(wallet×cell)`
with `lo>0.03` at 78×~8=624 comparisons yields ~6 chance clears at α=0.05 — the market_resid
false-promote at scale (that arm's +30% "surplus" was a baseline artifact caught only by a
label-permutation null, 2026-07-01).

**After — three layers, the live one dissolved.**
- **L1 (live) — family size 1.** Because Item 3 pools *continuously*, **no cell is ever selected** at
  scoring. There is *no cell-family to correct at the live layer* — strictly stronger than "one cell
  per vote," which still selects one cell. The arm is one pre-registered hypothesis.
- **L2 (fleet SCREEN, non-binding).** Over the frozen family `{(wallet,cell): n_events≥25 ∧
  surplus≠null}` (say M=624), `bh_fdr(pvals, q=0.10)` (`slice_study.py:197`) returns survivors, AND
  the screen prints each survivor's explicit ×-wallet Bonferroni LB `surplus_bounds(eff_n, surplus,
  sd, n_comparisons=M, params)` — at M=624, `α/624` ⇒ `z≈4.0`, so a cell needs `surplus > 4.0·se` to
  even watchlist. **Non-binding** — within-slate correlation defeats FDR (two co-active weekend
  "specialists" both light up). Promotes nothing.
- **L3 (BINDING) — forward label-permutation, family size 1.** Fit as-of cut `C` via
  `trader_slice_scores_asof(C)` (`consensus.rs:1526`, leak-free); score the pooled arm's picks on the
  strictly-future window `(C, now]`; permute wallet→cell labels within `(cell_kind × cell_key ×
  UTC-day)` strata (`selection_null.py::null_pvalue:106` / `clustered_surplus:95`, `N_PERM=2000`);
  require empirical `p ≤ SELECTION_NULL_P_BAR=0.01`; flip only on the **2nd disjoint window**.
  Forward-only ⇒ D1 bulk-stamp-immune.

**Is the dissolution real? (the skeptical check.)** Two ways a "dissolved" family secretly re-incurs
error: a *fitted K* (K discovered from data = a hidden search) and a *fitted pick-membership rule*.
Both are closed here: **K_POOL is a fixed const** (Item 3), and the permutation "picks" are defined by
a deterministic pre-registered rule — votes whose pooled weight differs from the overall weight by
`> ε` (ε fixed). No argmax, no cell discovery ⇒ the binding test is genuinely family-size-1. The
*cell-blind residual baseline* is a fitted quantity (fleet `AVG(a)` per cell) and IS leak-prone — it
is leak-free ONLY because L3 computes it inside `trader_slice_scores_asof` (bounded by the cut). Any
forward claim that reads the *live* (non-asof) blind is a leak; L3 must use `_asof`.

**Implementation.**
- L2: NEW `scripts/slice_screen.py` wraps `bh_fdr` — read `trader_slice_scores` rows, filter
  `n_events≥25 ∧ surplus≠null`, one-sided p per cell from `(surplus, sd, eff_n)`, `S=bh_fdr(pvals,
  0.10)`, print each survivor's Bonferroni-M LB. Watchlist artifact only.
- L3: generalize `selection_null.py`'s `(band × UTC-day)` strata to `(cell_kind × cell_key × UTC-day)`
  — `null_pvalue`'s `picks_meta` already carries an opaque cell tuple (`:106`), so the caller passes
  `cell=(sport,band,utc_day)` and `blind_cells` keyed the same; `clustered_surplus:95` unchanged. NEW
  `scripts/procedure_forward_null.py` fits as-of, scores forward, permutes, appends
  `reports/accrual/vNNN.json` + manifest, ntfy on the 2nd disjoint p≤0.01 window (idempotent).

**Integration points.** `promotion_verdict:168` already fail-closes on `selection_null_ok` (env
`SELECTION_NULL_P`); the arm is judged there in the EXPERIMENTAL family (`n_strategies` = experimental
size, does NOT tighten `strict`). NEW `scripts/slice_screen.py`, `scripts/procedure_forward_null.py`
(wrap `selection_null.py`); `trader_slice_scores_asof` is the fit; `reports/accrual/` append-only;
ntfy `consensus_cycle.rs:417-430`.

**Power / Multiplicity / Forward-weeks.** L2's ×-wallet Bonferroni (M=624) is deliberately brutal —
most cells never watchlist (thin cells lie). L3 is family size 1 ⇒ no Bonferroni inflation of the
promotion bar. Forward-weeks is the binding cost: enough forward `(cell×day)` strata for a valid
2000-draw permutation over ≥2 disjoint windows — the honest wall-clock to certification. On today's
backfill this correctly returns PENDING (`persistence_tracker.py`: `<PERSIST_MIN_CLUSTERS ⇒ PENDING`).

**Non-regression proof.** L2/L3 are out-of-band Python (read-only, append-only artifact + ntfy). NEW
`selection_null.py --selftest` extension: `(cell×day)` strata reproduce the `(band×day)` result when
sport is constant. Assert the live arm adds exactly one name to EXPERIMENTAL (mirror
`family_splits_experimental_from_core` `enrich/mod.rs:365`) so `strict`'s core `n_strategies` is
unchanged.

**Source: HYBRID.** Every layer is an existing instrument pointed at the new surface; the real cost is
L3's forward-weeks, which cannot be shortcut — the honest defense against manufacturing 6 false
specialists out of 624 cells.

---

### Item 5 — WS-5 orthogonality/integration vs `favorite` (GAP-5) — the burden of proof

**Tag: NEW-DELTA** (dossier WS-5 / decision (c); FORGE_PLAN predates `edge_orthogonality.py` /
`portfolio_constructor.py`). **Source: REFINED — Direct's full G1∧G2∧G3 + portfolio_constructor BAR
is BINDING; Rethink's cell-blind (Item 2) is a first-line PRE-FILTER, NOT a replacement.** Depends on
Items 3–4.

**Why not collapse the gate (the load-bearing synthesis decision).** Rethink argues the cell-blind
(Item 2) makes `edge_orthogonality.py`'s **G2 (orthogonal-component edge)** "largely pre-satisfied,"
collapsing G1∧G2∧G3 to a thin confirmatory check. This is **half right and dangerous**: the cell-blind
removes the **MEAN** favorite artifact within `(sport,band)`, so a pure favorite-rider's cell surplus
→ 0 (genuine, keep it). But `eff⊂favorite` / **0-of-12 diversify favorite** is a *portfolio
independent-VOLUME / event-overlap* finding — it is about whether the arm fires on events `favorite`
does NOT, i.e. **covariance**, which the mean-blind does not touch (Rethink concedes this in its own
Trade-offs). Collapsing the gate under-armors exactly the dimension every prior arm died on. So the
cell-blind is adopted as a pre-filter that lets G2 pass *honestly*, and the **full forward gate stays
the BAR.**

**Before.** No test that a specialist arm's edge is independent of `favorite`. A `slice_sport_tail`
that only up-weights favorite-band events is favorite wearing a new name.

**After — the BAR (a survivor must clear ALL):**
- **G1 (independent volume):** the arm's `S_only` picks (events it up-weights that `favorite` does
  NOT fire) must have `≥ MIN_INDEP` distinct events. A soccer specialist firing only in band .80–.97
  has `S_only≈∅` ⇒ **FAIL G1** ⇒ it IS favorite. Item 2's cell-blind is what lets a *non*-favorite-band
  soccer cell earn weight, generating genuine `S_only` volume — the structural reason per-(trader×cell)
  can diversify where `elite_fresh_fav` (a favorite-band arm by construction) could not.
- **G2 (orthogonal-component edge):** regress the arm's per-event surplus on `favorite`'s indicator;
  the favorite-orthogonal residual must itself have `lo>0` (event-clustered). Item 2 makes this
  *reachable*, does not waive it.
- **G3 (residual independence):** the arm's `S_only` surplus clears its own `selection_null.py`
  `(cell×day)` permutation (Item 4 L3).
- **Integration BAR:** feed both arms to `portfolio_constructor.py` (DEDUP→SIZE→SCORE→PRICE); the
  specialist is trusted ONLY if it survives the greedy drop (adds `≥ MIN_INDEP` independent events)
  AND its **MARGINAL** reliability LB (the design-effect-priced SE reduction of adding a 2nd edge over
  favorite-only) is `> bar`. **And, per the pooled-arm caveat: the marginal test must show the arm
  adds edge over BOTH `favorite`-only AND global `trust_weighted`** — a pooled weighting that merely
  reproduces `trust_weighted` on favorite events is not a specialist. If it collapses into either,
  `portfolio_constructor` drops it — the same verdict that killed `elite_fresh_fav`, applied honestly.

**Implementation.** No new Rust. A WS-5 harness runs on the arm's forward picks (already persisted —
the scoreboard shadow-scores the identical `active_portfolio`): `edge_orthogonality.py --arm
slice_sport_tail --vs favorite` (G1∧G2∧G3, reuses `selection_null`), then `edge_orthogonality.py --vs
trust_weighted` (the second adversary), then `portfolio_constructor.py` for the marginal-LB. The BAR
is documented alongside the arm.

**Integration points.** `scripts/edge_orthogonality.py` (`--selftest` present) ·
`scripts/portfolio_constructor.py` · the per-strategy picks table the scoreboard already writes ·
`scripts/persistence_tracker.py` for forward OUT clusters.

**Power / Multiplicity / Forward-weeks.** G1 needs enough forward `S_only` distinct events — a
specialist that only ever agrees with favorite never accrues `S_only` and honestly never certifies.
The marginal-LB is a strict, small number priced on the design-effect SE reduction. Forward-weeks: the
binding cost is accumulating independent (non-favorite) clusters.

**Non-regression proof.** `edge_orthogonality.py --selftest` and `portfolio_constructor` are existing,
tested. NEW harness test: a synthetic arm that is a pure re-label of `favorite` must FAIL G1
(`S_only=∅`) and be dropped by `portfolio_constructor` — proves the gate reproduces the
`elite_fresh_fav ⊂ favorite` verdict. Out-of-band; no live path touched.

**Source: REFINED.** The full gate is the burden of proof the reliability program imposes (0/12
diversify favorite); Item 2 makes passing it *reachable* without waiving the covariance dimension.

---

### Item 6 — Unify the SE convention before any GO (GAP-6) — day-deflated everywhere

**Tag: NEW-DELTA** (dossier known-bug D16-a; not in FORGE_PLAN). **Source: DIRECT (= Rethink; both
identical).** Independent of Items 1–5 for *building*; binding before any GO.

**Before** (verified). `trust_verdict` uses day-deflated `eff_n = n_days.clamp(1,n_events)`
(`trader_trust.rs:179`); `promotion_verdict` uses day-deflated `effective_n` (`promotion.rs:180`); but
`pilot_verdict` passes **EVENT-N** `inp.distinct_events` to `surplus_bounds` (`honest.rs:105-109`).
`favorite` reads +3.33% under one convention and ≈−23% on 4 correlated event-days under the other
(D16-a). A specialist could be "promoted" on the flattering convention.

**After.** `pilot_verdict` passes the SAME day-deflated N (the D17-a reconciliation toward
cluster-robust `n_eff`). Trust, promotion, and pilot read ONE SE.
```rust
// honest.rs:105  BEFORE:  surplus_bounds(inp.distinct_events,                       honest_roi, …)
// honest.rs:105  AFTER:   surplus_bounds(inp.distinct_days.clamp(1, inp.distinct_events), honest_roi, …)
```

**Verified prerequisite (do not skip).** `PilotInputs` (`honest.rs:21`) has fields `honest_roi`,
`honest_roi_sd`, `distinct_events`, `n_family` — **there is NO `distinct_days` field today.** GAP-6
therefore REQUIRES: (a) add `pub distinct_days: i64` to `PilotInputs`; (b) populate it at the
construction site from the same day-count already computed for the slice scores (degrade-to-1
fail-closed). This is a real (small) struct + populate-site change, not a one-liner.

**Direction is monotone-safe (verified).** `surplus_bounds` sets `se = sd/√N`; day-deflation LOWERS N
(events cluster into fewer days) ⇒ WIDER CI ⇒ the pilot gets HARDER, never easier. The unification can
only make GO more conservative — safe for a real-money bar. `strict` never calls `pilot_verdict`, so
the live alert path is untouched.

**Integration points.** `honest.rs:21` (`PilotInputs` +`distinct_days`) · its construction site
(populate) · `honest.rs:105` (the one read-time change). `surplus_bounds` unchanged (takes the
caller's N). `probit` untouched.

**Power / Multiplicity / Forward-weeks.** Stricter pilot; no multiplicity change; forward-weeks
unchanged.

**Non-regression proof.** SENSITIVE (touches the pilot gate). NEW `pilot_uses_day_deflated_n`: a
50-event/1-day input now yields `eff_n=1` ⇒ wide CI ⇒ no GO (was event-N=50 ⇒ falsely tight); assert
`pilot_verdict` LB equals `promotion_verdict` LB for the same record (agree by construction). Confirm
on a fixture that `favorite`'s board number == its pilot number.

**Source: DIRECT.** One read-time change + one struct field; unifies the two pre-registered
conventions. Ship before any GO — not a prerequisite for building Items 1–5.

---

### Item 7 — Diagnose "0 earned_eligible" + forward-gated cell-scoped earn (GAP-7)

**Tag: NEW-DELTA** (dossier live-gap; FORGE_PLAN doesn't address `earned_eligible`). **Source:
HYBRID** (diagnose-first, both; forward-gated cell-scoped earn). Rides Items 1–4.

**Before** (verified). `promotable_deep_sharps` (`earned.rs:75`) keeps only
`TrustVerdict::Trusted` (`:77`), grading the **overall** (band-blind) slice. A specialist's overall
surplus is diluted by its weak sports (`0x032eb`: soccer +0.156 washed out by MLB −0.083 → overall
≈+0.02 → Indeterminate). `457 tracked / 167 consensus_eligible / 0 earned_eligible` — structurally
nobody in the deep pool clears overall-Trusted at ≥30 events.

**After.** DIAGNOSE first (read-only), then a forward-gated cell-scoped earn.
- *Diagnosis (a query, trivial):* classify each deep-pool (`!consensus_eligible`) wallet as
  (sub-25 / 25–29 / ≥30 & Indeterminate / ≥30 & Avoid / Trusted), under BOTH the current band-blind
  and Item 2's cell-blind, at floors 30 and 25. If most are "≥30 & Indeterminate (diluted)," the
  cell-blind + cell-scoped earn unblocks them; if genuinely Avoid/nobody, that is itself the honest
  finding — the design must NOT force a promotion to make the number nonzero.
- *Fix (rides GAP-1/2/3):* NEW `promotable_deep_sharps_cell` keeps a wallet if ANY `sport` cell is
  Trusted (from the Item 3 `CellMap`) **AND that cell has cleared the Item 4 L3 forward permutation on
  ≥2 disjoint windows** — never on an in-sample cell (the congregation defense). The wallet earns in
  for that sport; its votes elsewhere are down-weighted by Item 3 pooling, so earning it does not
  import the −0.083 leak.

**The coupling caveat (must gate).** `earned_eligible` is a boolean that admits a wallet to the voter
set broadly. Earning a wallet "for soccer" but letting it vote everywhere is safe ONLY if the arm
consuming it uses the Item 3 pooled per-cell weight. Therefore the cell-scoped earn is gated on
`cfg.slice_pooled` being on AND the forward-flip — if pooling were off, a cell-earned wallet's
weak-sport votes would leak at full weight. Enforce both in the predicate.

**Implementation.** `earned.rs:75` — add `promotable_deep_sharps_cell` behind the same
`EARN_DEEP_SHARPS` guard + the forward-flip + `slice_pooled`; reuses the Item 3 `CellMap`; no new
query. Diagnosis is a standalone read-only query.

**Integration points.** `earned.rs:46-77` (`deep_sharp_pass`/`promotable_deep_sharps` sibling) ·
Item 3 `CellMap` · Item 4 L3 forward-flip artifact.

**Power / Multiplicity / Forward-weeks.** A cell-scoped earn adds voters only in the cell they earned
— narrower, more honest than an overall earn; reuses the per-cell gate (no new comparisons); earned
voters still forward-accrue. On today's data ⇒ still 0 until a cell clears ≥2 disjoint forward windows
(honest).

**Non-regression proof.** Diagnosis is read-only. NEW `deep_sharp_cell_earn_requires_trusted_cell_and_forward_flip`
(a wallet Indeterminate overall but Trusted+forward-flipped on `sport=cs2` becomes eligible ONLY for
cs2, and ONLY when `slice_pooled` on). Assert `promotable_deep_sharps` (overall path) byte-identical
when the cell-earn flag is off ⇒ today's set (empty).

**Source: HYBRID.** The 0-earned puzzle is *caused by* demanding an undiluted overall edge from
wallets who are specialists by nature; the upstream fixes make the fix here a one-predicate change —
the gap dissolves once GAP-1/2/3 land. "Genuinely nobody" remains a valid honest outcome.

---

## Execution Order

1. **Item 1 — TrustParams{25} (GAP-3).** *Verify:* `cargo test -p copy-trading-bot`;
   `trust_floor_is_25_pilot_floor_still_50` + `hairline_25_event_slice_reads_indeterminate` green;
   `PilotThresholds::default().min_events==50` asserted unchanged.
2. **Item 2 — bet_type axis + cell-blind cascade (GAP-2).** Depends on 1. *Verify:* migration 037
   applies (confirm 036 latest in the active trunk FIRST); `bet_type_bucket` classifier test;
   `cell_blind_falls_back_to_band_blind_when_thin` + `single_sport_wallet_cell_blind_equals_band`
   green; a bettype cell appears in `/profile`; `_asof` and live queries both carry the cascade.
3. **Item 3 — pooled per-cell weight (GAP-1).** Depends on 1–2. *Verify:* `SLICE_POOLED` OFF ⇒
   `default_strict_is_non_regressive` byte-identical; `slice_arm_registered_separately_and_silent`
   green; `family("slice_sport_tail")=="experimental"`; `pooled_weight_tempers_thin_cell` reproduces
   the 0.977 MLB / 1.073 soccer numbers with the flag on.
4. **Item 4 — multiplicity three-layer (GAP-4).** Depends on 3. *Verify:* `slice_screen.py` prints
   the Bonferroni-M watchlist; `procedure_forward_null.py` produces a p-value + append-only artifact
   on synthetic forward data and returns PENDING on the current backfill; `selection_null.py
   --selftest` `(cell×day)`↔`(band×day)` equivalence when sport constant; ntfy idempotent on the 2nd
   disjoint window.
5. **Item 5 — WS-5 orthogonality BAR (GAP-5).** Depends on 3–4. *Verify:* synthetic favorite-relabel
   arm FAILS G1 and is dropped by `portfolio_constructor`; the marginal-LB harness runs `--vs
   favorite` AND `--vs trust_weighted`; the BAR is documented with the arm.
6. **Item 6 — SE unification (GAP-6).** Independent; ship before any GO. *Verify:* `PilotInputs`
   carries `distinct_days` populated at its site; `pilot_uses_day_deflated_n` green; `favorite`
   board==pilot number on a fixture; `strict` untouched.
7. **Item 7 — earned_eligible diagnose + cell-scoped earn (GAP-7).** Rides 1–4. *Verify:* the
   read-only diagnosis query classifies deep-pool wallets under both blinds/floors;
   `deep_sharp_cell_earn_requires_trusted_cell_and_forward_flip` green; overall
   `promotable_deep_sharps` byte-identical with the flag off.

---

## Power / Multiplicity / Forward-weeks Summary (the "cost" analog)

| Item | Power (distinct-event N / cell) | Multiplicity (Bonferroni denominator) | Forward-weeks to certify | Touches `strict`? |
|---|---|---|---|---|
| 1 — TrustParams{25} | +profiling reach (78→more at 25); widened CI ⇒ fewer certify | none (isolates trust from pilot floor) | none | No |
| 2 — bettype + cell-blind | `(sport,band)` blind splits N; cascade fallback to band-blind | +1/wallet per populated bettype cell (→ Indeterminate only) | none (re-measures history) | No |
| 3 — pooled weight | pooling spends LESS/cell (N/(N+K)); thin cells tempered | **live family size 1** (no cell selection); +1 EXPERIMENTAL arm | accrues like any arm | No (env-gated, EXPERIMENTAL) |
| 4 — multiplicity | L2 screen brutal (M-Bonferroni); L3 needs forward strata | L2 non-binding; **L3 family size 1** | **binding: ≥2 disjoint forward windows** | No (out-of-band) |
| 5 — WS-5 BAR | G1 needs forward `S_only` distinct events | none new (reuses selection_null family size 1) | binding: independent non-favorite clusters | No (out-of-band) |
| 6 — SE unify | day-deflation LOWERS pilot N (stricter) | none | none | No (pilot only) |
| 7 — cell earn | narrower voter add (cell-scoped) | none new (reuses per-cell gate) | earned voters forward-accrue | No (env-gated) |

**Unchanged real-money gate (this run certifies NOTHING live):** the pilot bar stays `PilotThresholds
{min_pilot_roi:0.02, min_events:50, min_regimes:5, regime_frac:0.7, min_liquidity_usd:2000}`. Promotion
to live `strict` alerting remains Tue's manual call after Item 4 L3 clears ≥2 disjoint forward windows
AND Item 5's orthogonality BAR passes.

---

## Existing Infrastructure Leveraged

- `surplus_bounds` (`promotion.rs:281`), `promotion_verdict` (`:168`), `SELECTION_NULL_P_BAR` (`:97`)
  — reused verbatim, zero new gate stats; `probit` stays private (`:33`).
- `trust_verdict_with` / `n_comparisons` / `eff_n` (`trader_trust.rs:123/129/179`) — the per-cell
  bound loop and the `CellMap` verdicts drop straight in.
- `earned_quality` + `damp = n/(n+20)` (`consensus_cycle.rs:69-74`) — the pooled multiplier factors
  out and generalizes the already-blessed shrink seam (comment `:67`).
- `trader_slice_scores` / `_asof` (`consensus.rs:1459/1526`) — CTE extension points; `_asof` is the
  leak-free fit for Items 4–5.
- `sport_bucket` (`consensus_cycle.rs:133`) — exact template for `bet_type_bucket`.
- `family()` EXPERIMENTAL const (`scanner/enrich/mod.rs:338`) — keeps the new arm out of the core bar.
- `trust_arms` + `certified_only` + `active_portfolio` `CONSENSUS_TRUST_ARMS` guard
  (`consensus.rs:735`, `consensus_cycle.rs:854-860`) — template for the `SLICE_POOLED` guard.
- `bh_fdr` (`slice_study.py:197`), `selection_null.py` (`null_pvalue:106`/`clustered_surplus:95`,
  `N_PERM=2000`), `edge_orthogonality.py`, `portfolio_constructor.py`, `persistence_tracker.py` — the
  screen, the binding forward test, and the orthogonality BAR.
- Mirror tests: `default_strict_is_non_regressive` (`consensus.rs:1172`),
  `trust_arms_registered_separately_and_silent` (`:1200`), `margin_zero_regression_hairline_surplus_rejected`
  (`promotion.rs:473`), `below_event_floor_never_promotes` (`:340`), `family_splits_experimental_from_core`
  (`enrich/mod.rs:365`).

---

## Open Questions (resolve during implementation)

- **K_POOL value.** Start K=40 (mirrors the spirit of the `+20` damp; makes a 40-event cell pool
  halfway). FROZEN once chosen — a *fitted* K would leak (Item 4). Resolve by picking a round const
  before the first forward window opens, never by tuning to in-sample surplus.
- **bettype keyword tuning.** Run `bet_type_bucket` over a sample of live `trader_fills.title/slug`;
  aim `other` rate <15% before merge.
- **ε for the permutation pick-membership rule** (pooled weight vs overall). Pick a small fixed
  threshold (e.g. |Δweight| > 0.01) before the forward window; deterministic, pre-registered.
- **Blind granularity `(sport,band)` vs `(sport,bettype,band)`.** Ship `(sport,band)`; add bettype to
  the blind only if a bettype specialist survives Item 5.
- **Scheduler for Item 4 L3** — cron beside `consensus-backup.sh` (preferred) vs a Rust `accrual_tick`.
  Resolve by which fits the deploy container.
- **Δ (as-of window width) + disjoint-window definition** — resolve against how fast real forward
  `resolved_at` accrues; start with per-tournament-block windows.

---

## Rejected Approaches (with the verification finding that killed each)

- **Live per-slice specialist book overriding the overall gate (the naive vision).** REJECTED —
  DECISIONS.md D2: already built, DEAD (0 capturable persistent specialists at every cut). Shipping it
  manufactures the false specialists the charter forbids. We build the inert, forward-gated mechanism.
- **Direct's hard cell-verdict SWITCH for GAP-1.** REJECTED in favor of the pooled multiplier. The
  hard switch either discards a thin soccer cell (congregation's sub-30-discard death) or swings a
  vote to the cell's FULL multiplier on a 2-day slate. Pooling with fixed K tempers thin cells toward
  the parent, reaches specialists even when overall is Indeterminate, AND removes cell selection from
  the live layer (family size 1) — a strictly-better congregation answer at equal statistical cost
  (both reuse `surplus_bounds`, `probit` private).
- **Rethink's GAP-5 collapse ("G2 pre-satisfied by the cell-blind → thin confirmatory check").**
  REJECTED as the binding gate. Verification finding: the cell-blind removes the MEAN favorite
  artifact but NOT event-level covariance/overlap with `favorite` — and `eff⊂favorite` / 0-of-12 is a
  covariance/independent-volume finding. Collapsing G1∧G2∧G3 under-armors the exact dimension prior
  arms died on. The cell-blind is kept as a *pre-filter* that lets G2 pass honestly; the full forward
  G1∧G2∧G3 + `portfolio_constructor` marginal-LB (vs favorite AND trust_weighted) stays the BAR.
- **Rethink's `COALESCE(blind_edge, 0)` for the cell-blind fallback.** REJECTED. Verification finding:
  it fails **open** on thin `(sport×subtype×band)` blind cells — an empty blind cell → surplus = raw
  advantage (no neutralization) → favorite-in-disguise leaks back exactly where the baseline is
  thinnest. Replaced by Direct's cascade `COALESCE(blind_cell, blind_band, 0)`, which degrades to the
  incumbent per-band FLB neutralizer and never to 0.
- **Rethink's 3-D `(sport×subtype×band)` blind from day one.** DEFERRED (not rejected). Thinner blind
  cells buy noise for marginal specificity; band-loading is the dominant leak. Ship `(sport,band)`;
  add bettype to the blind only after a bettype specialist survives Item 5.
- **A *fitted* pooling K or a *fitted* pick-membership rule.** REJECTED as leaks. A K discovered from
  data is a hidden search that re-inflates the family Item 4 claims to dissolve; both K_POOL and ε are
  fixed pre-registered consts.
- **BH-FDR over the frozen cell family as the BINDING accrual control.** REJECTED as binding (kept as
  the L2 screen only): on a co-active slate FDR controls expected FDP but not within-slate
  correlation. Forward cross-window label-permutation (L3) is the real control.
- **Archetype as a live per-vote selection axis.** REJECTED (per old plan Item 3): `entry_pct` needs
  the event's full fleet-fill distribution, unavailable at single-vote scoring. Archetype stays
  display/accrual only; the live arm keys `sport`.
