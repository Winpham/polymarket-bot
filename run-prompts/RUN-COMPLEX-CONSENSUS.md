# Implementation Blueprint: Conditional / Coalition Consensus Engine

After this build, the consensus engine can tell **"1 certified soccer specialist + 3 noise" from "4 noise"**: a single new per-`(wallet,slice)` trust map (reusing the existing belief-blind bound — zero new statistics) feeds two silent, flag-gated `Enricher` arms that fire on a **lone, fresh, gate-certified specialist footprint** (leading the crowd) and on a **certified specialist fading the crowd**, each judged forward by the existing event-clustered gate over `(event_slug)` units, stress-tested at a slippage+fee capture margin, and reported with a lower-variance CLV/line-movement lens. The likely honest result on current data is an **INDETERMINATE board** (too few per-sport certified specialists yet) — and that correctly-judged null is the success criterion, not a green number.

All citations verified by read/grep on `~/polymarket-bot` branch `feat/consensus-engine`, 2026-06-30.

---

## Items (dependency-ordered)

### 1. Capture margin at the strategy gate: `margin = 0.0` → `slippage_pct + fee_pct`

**Before (a board verdict).** An arm with surplus +2.5%, Bonferroni lower bound +0.3% over N=40 renders `✅ PROMOTABLE` (`board.rs:180`), even though a copier entering later/worse, minus ~3% fees+slippage, captures nothing. The gate is built with `PromotionParams::default()` → `margin: 0.0` (`board.rs:153`, default at `promotion.rs:84`).

**After.** `margin = cfg.slippage_pct + cfg.fee_pct = 0.01 + 0.02 = 0.03` (`config.rs:199,203`). The same arm's lower bound `+0.3% < 3%` → `⏳ hold`. Only edges surviving a realistic copier entry certify.

**Implementation.** The margin hook already exists and is honored at `promotion.rs:134` (`promotable = lower_bound > p.margin`). Thread the value into the one board render path:

```rust
// board.rs — render() currently has no cfg (board.rs:146). Give it the capture margin.
async fn render(portfolio: &PgPortfolio, capture_margin: f64) -> String {
    // ...
    let pp = PromotionParams { margin: capture_margin, ..PromotionParams::default() }; // was ::default() @ :153
    // promotion_verdict(... &pp) at :179 now gates at the capturable bar
}
```

The board's HTTP handler holds `cfg`; pass `cfg.slippage_pct + cfg.fee_pct`. **Do NOT** change `trust_verdict` (`trader_trust.rs:106`) — "is this trader better than blind" (margin 0) is a deliberately different question than "is this arm capturable after fees". Only the **strategy/arm** gate gets the capture margin.

**Integration points.** `board.rs:146` (render signature), `board.rs:153` (PromotionParams build), `board.rs:179` (gate call), `config.rs:199/203` (slippage_pct/fee_pct).

**Multiple-testing.** Zero new hypotheses; raises the bar for all existing arms.

**Source.** direct (P0b) — verified the margin hook is the designed seam and is currently fed 0.0.

---

### 2. Per-`(wallet, slice)` trust map — the keystone infra (no arm yet)

This is the single thing that unlocks both arms. It reuses the exact gate bound (`surplus_bounds`, `promotion.rs:165`) and the exact per-slice SQL that already runs (`trader_slice_scores`, `storage/consensus.rs:857-904`). **Zero new statistics.**

**Before.** `compute_trust_map` (`consensus_cycle.rs:87-96`) calls `trust_verdict` (`trader_trust.rs:106`), which reads **only** the `overall` slice (`trader_trust.rs:119,136-160`). The per-`sport`/`band` slices `trader_slice_scores` computes survive only as display strings `best_slices`/`worst_slices` (`trader_trust.rs:98-100,122-132`) and are never used for weighting. A soccer sharp's +33% soccer edge becomes one overall scalar.

**After.** A `SliceTrustMap` carries every wallet's per-slice certified verdict + bounds, built from the **same** `trader_slice_scores()` snapshot the trust refresh already pulls — no extra DB round-trip.

**Implementation.**

```rust
// scanner/trader_trust.rs — NEW, beside trust_verdict_with (:111). Reuses surplus_bounds.
#[derive(Debug, Clone, Copy)]
pub struct SliceTrust {
    pub verdict: TrustVerdict,   // reused enum (trader_trust.rs:54-62)
    pub lower_bound: f64,        // one-sided Bonferroni lower bound on slice surplus
    pub upper_bound: f64,        // symmetric upper bound (the Avoid side)
    pub surplus: f64,            // raw event-clustered point estimate (display only)
    pub n_events: i64,           // distinct-event N behind this slice
}

/// wallet (as stored, lower-cased by ingest — same key convention as TrustMap,
/// see consensus_cycle.rs:79-81 "lower-cased wallet") → (slice_kind, slice_key) -> SliceTrust.
pub type SliceTrustMap =
    std::collections::HashMap<String, std::collections::HashMap<(String, String), SliceTrust>>;

/// One wallet's slice table. Bonferroni denominator = that wallet's slices-with-data,
/// IDENTICAL to trust_verdict_with (:117) — so "best of N slices" cannot fake Trusted.
pub fn slice_trust_for_wallet(
    slices: &[TraderSliceStat],
    p: &PromotionParams,
) -> std::collections::HashMap<(String, String), SliceTrust> {
    let n_comparisons = slices.iter().filter(|s| s.surplus.is_some()).count().max(1);
    let mut out = std::collections::HashMap::new();
    for s in slices {
        let Some(surplus) = s.surplus else { continue };
        let key = (s.slice_kind.clone(), s.slice_key.clone());
        // Below the distinct-event floor ⇒ INDETERMINATE regardless of point estimate
        // — identical rule to trust_verdict_with (:149). Small N is not evidence.
        if s.n_events < p.min_events {
            out.insert(key, SliceTrust { verdict: TrustVerdict::Indeterminate,
                lower_bound: 0.0, upper_bound: 0.0, surplus, n_events: s.n_events });
            continue;
        }
        let (lo, hi) = surplus_bounds(s.n_events, surplus, s.surplus_sd, n_comparisons, p); // promotion.rs:165
        let verdict = if lo > p.margin { TrustVerdict::Trusted }
                      else if hi < -p.margin { TrustVerdict::Avoid }
                      else { TrustVerdict::Indeterminate };
        out.insert(key, SliceTrust { verdict, lower_bound: lo, upper_bound: hi, surplus, n_events: s.n_events });
    }
    out
}
```

```rust
// cycles/consensus_cycle.rs — compute BOTH maps from ONE snapshot (no extra round-trip).
// Refactor compute_trust_map (:87-96) to fetch once and fan out:
pub async fn compute_trust_maps(portfolio: &PgPortfolio) -> (TrustMap, SliceTrustMap) {
    let scores = portfolio.trader_slice_scores().await.unwrap_or_default(); // empty on DB err ⇒ arms no-op
    let mut by: HashMap<String, Vec<_>> = HashMap::new();
    for s in scores { by.entry(s.wallet.clone()).or_default().push(s); }
    let p = PromotionParams::default(); // margin 0 here; the arm gate applies the capture margin (Item 1)
    let mut trust = TrustMap::new();
    let mut slice = SliceTrustMap::new();
    for (w, slices) in by {
        trust.insert(w.clone(), crate::scanner::trader_trust::trust_verdict(&slices));
        slice.insert(w, crate::scanner::trader_trust::slice_trust_for_wallet(&slices, &p));
    }
    (trust, slice)
}
```

```rust
// scanner/enrich/mod.rs:159-169 — EnrichCtx gains EXACTLY ONE borrowed field.
pub struct EnrichCtx<'a> {
    pub now: DateTime<Utc>,
    pub models: &'a EnrichModels,
    pub margins: EnrichMargins,
    pub markets: &'a HashMap<String, MarketCtx>,
    pub slice_trust: &'a SliceTrustMap,   // NEW — the only seam change (unlocks both arms)
}
```

**As-of safety (forward-live, NO harness).** Verified posture: `trader_slice_scores` has `WHERE resolved AND side='BUY' AND outcome_won IS NOT NULL` (`storage/consensus.rs:866`) — a snapshot over **resolved ⇒ past** fills. A live signal predicts an **unresolved** market, excluded by that clause, so weighting a forward-live arm with this snapshot cannot leak the predicted outcome. This is structural, not a date check, and is exactly why the arms need no walk-forward harness (Item 6 is only for fitted/mined variants).

**Integration points.** New type+fn `trader_trust.rs:~111`; refactor `consensus_cycle.rs:87-96`; `EnrichCtx` `enrich/mod.rs:159-169`; thread `slice_trust: &SliceTrustMap` through `consensus_cycle(...)` signature (`consensus_cycle.rs:221-230`, beside `trust: &TrustMap` at :229) and the `EnrichCtx{ … }` build site (`consensus_cycle.rs:270-281`); the slow refresh task in `live.rs` calls `compute_trust_maps` (replacing `compute_trust_map`).

**Multiple-testing.** Zero hypotheses (no arm yet). The cross-wallet selection of "who is a certified specialist" is corrected only within-wallet; across ~90 wallets a few will be Trusted-in-sport by chance — but that is **conservative for the forward arm gate** (a spuriously-certified wallet dilutes the arm's forward record, it cannot manufacture forward edge), so no extra correction is required here.

**Non-regression.** With no arm flag on, `registry()` is unchanged, `enrich_all` stays a passthrough (`enrich/mod.rs:258` test), the new ctx field is simply unread; `cargo build` + the passthrough test stay green.

**Source.** hybrid (DIRECT P1 + RETHINK §3.1 "one snapshot, no extra round-trip" + "one field"). Refined: ONE EnrichCtx field, not three — sport is read off the signal (Item 3), and the capture margin lives at the gate (Item 1), not the arm.

---

### 3. Arm A — `arm_spec_footprint`: lone, fresh, certified-specialist footprint

**Before (DIAGNOSTIC §1.3).** Soccer outcome 0 backed by `0x65018f9f` (certified soccer sharp) + 3 noise → `ConsensusSignal{ net_count:4, net_quality:Σ rank-weights }` (`consensus.rs:391-393`); swap the sharp for a 4th rank-matched noise wallet and the row is byte-identical. Worse, by the time `strict` fires (min_backers 3) the crowd has already moved the price — the lone-specialist t0 moment is invisible (only a `_blind` row, never distinguished).

**After.** The arm rides `_blind` rows (which capture every observed outcome, `min_backers:1` at `consensus.rs:639`), selecting the **lone/near-lone, fresh** book where ≥1 backer is gate-Trusted in **this market's sport** — i.e. it leads the crowd. A 4-noise book has no certified specialist → no row. The two configurations are separable at the source.

```rust
// scanner/enrich/specialist.rs — NEW.
use super::{ConsensusSignal, EnrichCtx, re_emit};
use crate::scanner::trader_trust::TrustVerdict;
use crate::cycles::consensus_cycle::sport_bucket; // make pub (currently private @ consensus_cycle.rs:125)

const MAX_BACKERS_EARLY: usize = 2; // 1–2 backers = lone/near-lone specialist (n_backers is usize @ consensus.rs:262)
const MAX_FRESH_MINS:    i64   = 30; // entered within the last 30 min (recency_mins is i64 @ consensus.rs:271)

pub fn arm_spec_footprint(sigs: &[ConsensusSignal], ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    if !ctx.models.spec_footprint_enabled { return Vec::new(); } // per-arm flag, mirrors bayes (bayes.rs:18)
    let mut out = Vec::new();
    for s in sigs {
        if s.strategy != "_blind" { continue; }                  // ride the universe of observed books
        if s.n_backers > MAX_BACKERS_EARLY || s.recency_mins > MAX_FRESH_MINS { continue; }
        let sport = sport_bucket(&s.title, &s.slug);              // sport off the SIGNAL (consensus.rs:256-257) — no books needed
        if sport == "other" { continue; }                        // specialist routing is sport-keyed
        let key = ("sport".to_string(), sport);
        let certified = s.backers.iter().any(|b| {               // BackerInfo.wallet @ consensus.rs:242
            ctx.slice_trust.get(&b.wallet)
                .and_then(|m| m.get(&key))
                .map(|st| st.verdict == TrustVerdict::Trusted)
                .unwrap_or(false)
        });
        if certified { out.push(re_emit(s, "spec_footprint")); } // silent WATCH row (enrich/mod.rs:199)
    }
    out
}
```

**Certification target — PRIMARY = outcome surplus (robust), SECONDARY = CLV (Item 5).** The arm's `spec_footprint` rows are non-`_blind`, so housekeeping resolves AND price-snapshots them (`housekeeping.rs:127-163`; the `_blind`-skip at :148 does NOT apply to them). They flow through the **existing** `consensus_scoreboard_by_strategy()` (`storage/consensus.rs:466-540`), whose `_blind` band-baseline is computed from `outcome_won - mean_price` (`:488-495`) — which **works for `_blind`** because `_blind` rows are resolved (just not snapshotted). So the primary gate is the proven, leak-free, FLB-neutralized outcome surplus. CLV is reported as a lens, not the sole judge (see Rejected: RETHINK's CLV-as-sole-certifier).

**Integration points.** New file `scanner/enrich/specialist.rs`; `registry()` `enrich/mod.rs:177` += `specialist::arm_spec_footprint`; `EXPERIMENTAL` `enrich/mod.rs:229-237` += `"spec_footprint"`; `sport_bucket` visibility `consensus_cycle.rs:125`; `EnrichModels` `enrich/mod.rs:33-48` += `pub spec_footprint_enabled: bool`, set in `load_models` (`enrich/mod.rs:67`, mirror `bayes_enabled` at :125) from `cfg.consensus_arm_spec_footprint`; flag `config.rs:150-168` pattern `#[config(env="CONSENSUS_ARM_SPEC_FOOTPRINT", default=false)]`.

**Multiple-testing.** +1 hypothesis in the experimental family (7→8). Per-arm corrected one-sided z rises only `probit(1−0.05/7)=2.45 → probit(1−0.05/8)=2.49`.

**Source.** refined (RETHINK MOVE 1 early-footprint selection + DIRECT outcome certification + Item 2 plumbing). Beats both: leads the crowd (vs DIRECT riding post-crowd `strict`) **and** certifies on the robust outcome scoreboard whose blind baseline actually exists (vs RETHINK's CLV-only, whose blind baseline does not — see Item 5 / Rejected).

---

### 4. Arm D — `arm_spec_contrarian`: certified specialist fading the crowd

**Before.** A book with a certified specialist on the **minority** side is exactly what `strict` discards (`n_opposers > max_opposers 1` → rejected at `consensus.rs:408-409`) — the single most informative configuration is thrown away.

**After.** The arm fires on a `_blind` row that is the **minority** outcome (`net_count < 0`) yet carries a certified-in-sport specialist — a proven specialist fading the crowd in a domain it has earned edge in.

```rust
// scanner/enrich/specialist.rs — same file as Arm A.
pub fn arm_spec_contrarian(sigs: &[ConsensusSignal], ctx: &EnrichCtx) -> Vec<ConsensusSignal> {
    if !ctx.models.spec_contrarian_enabled { return Vec::new(); }
    let mut out = Vec::new();
    for s in sigs {
        if s.strategy != "_blind" { continue; }
        if s.net_count >= 0 { continue; }                        // this outcome is the MINORITY side (i64 @ consensus.rs:265)
        let sport = sport_bucket(&s.title, &s.slug);
        if sport == "other" { continue; }
        let key = ("sport".to_string(), sport);
        let has_specialist = s.backers.iter().any(|b| ctx.slice_trust.get(&b.wallet)
            .and_then(|m| m.get(&key))
            .map(|st| st.verdict == TrustVerdict::Trusted).unwrap_or(false));
        if has_specialist { out.push(re_emit(s, "spec_contrarian")); }
    }
    out
}
```

**Why this and not DIRECT's smart-vs-dumb.** DIRECT's `arm_smart_vs_dumb` needs the **opposers'** identities (which `ConsensusSignal`/`BackerInfo` drop) → it required a new `books: &[MarketBook]` EnrichCtx field, AND it keys on certified-**Avoid** ("dumb") money on the other side — but at current N almost no wallet is certified Avoid in a sport, so `dumb_against ≈ 0` and that arm rarely fires anyway. The contrarian reframe needs neither the books field nor an Avoid classification; it works off the same `slice_trust` + `_blind` minority signal. Cleaner, cheaper, fires more honestly.

**Integration points.** `registry()` += `specialist::arm_spec_contrarian`; `EXPERIMENTAL` += `"spec_contrarian"`; `EnrichModels` += `pub spec_contrarian_enabled: bool`; flag `CONSENSUS_ARM_SPEC_CONTRARIAN` (`config.rs` pattern). No `books` field needed (the refinement that lets EnrichCtx stay at one new field).

**Multiple-testing.** +1 hypothesis (experimental 8→9).

**Source.** refined toward rethink (RETHINK §3.4 contrarian-in-competence; rejected DIRECT's opposer-trust smart-vs-dumb on the verified grounds above).

---

### 5. CLV / line-movement lens + outcome guard (reported, not sole certifier)

**The real insight (RETHINK MOVE 2), tempered by verification.** Certifying on a **price delta** (`last_market_price − initial_market_price`) instead of a 0/1 outcome cuts per-unit sd from ~0.45 (coin flip) to ~0.05–0.10 (price move) — a large variance reduction that powers the Bonferroni gate at equal N, needs no win-label, and *is* the quantity a copier captures. This is a genuine improvement worth surfacing.

**But the clean blind baseline is NOT free (verified).** RETHINK's design certifies CLV with a band-blind computed from `_blind` rows' move. `_blind` rows are **never price-snapshotted** — housekeeping explicitly skips them: `None if sig.strategy != "_blind"` (`housekeeping.rs:148`, comment: "Skip the `_blind` benchmark population … to bound snapshot volume"). So `initial_market_price`/`last_market_price` are NULL on every `_blind` row; the CLV band-blind CTE filters them all out and degenerates to `COALESCE(blind_move,0)=0` → **no FLB/drift neutralization**, contradicting RETHINK §5(1). The existing `our_clv` (`storage/consensus.rs:511-516`) likewise has **no** band-blind. So CLV cannot be the *sole* certifier without new snapshot volume.

**Decision: ship CLV as a SECONDARY lens + an outcome guard, primary certification stays on outcome surplus (Item 3).**

**Before.** Board shows `our_clv = AVG_event(outcome_won − initial_market_price)` (`board.rs` column, `storage/consensus.rs:529`) with no blind and no bound — a number, not a verdict.

**After.** A reported CLV bound per arm via the **existing** `surplus_bounds` over the arm's captured moves, plus a one-sided **outcome guard**: promotion (a human PROPOSE, never auto-flip) requires the primary outcome lower bound > capture margin **AND** the CLV is favorable **AND** the outcome upper bound ≥ −margin (the resolved subset is not systematically resolving against us). All three numbers come from `surplus_bounds`/`promotion_verdict` — zero new statistics.

**Implementation (minimal, honest).** Add a reporting-only `consensus_clv_move_by_strategy()` mirroring `consensus_scoreboard_by_strategy` but targeting `(last_market_price − initial_market_price)` over the arm's own rows (which ARE snapshotted), clustered by event, **without** a `_blind` band-blind (documented: no clean blind population exists for price-move; the capture margin + outcome guard are the substitutes). Report its lower bound beside the outcome verdict; do not promote on it alone.

```rust
// storage/consensus.rs — NEW, reporting lens. NO _blind subtraction (none exists for price-move).
pub struct StrategyClvMove { pub strategy: String, pub distinct_events: i64,
    pub clv_move: Option<f64>, pub clv_move_sd: Option<f64> }
// SELECT strategy, COUNT(DISTINCT ev), AVG(u_move), STDDEV_SAMP(u_move) over
//   ev := COALESCE(event_slug, condition_id), u_move := AVG(last_market_price - initial_market_price)
//   FROM consensus_signals WHERE resolved AND initial_market_price IS NOT NULL
//     AND last_market_price IS NOT NULL AND strategy <> '_blind' GROUP BY strategy, ev
```

**Reflexivity guard (the real risk).** The line may move toward the specialist *because the tracked fleet keeps buying* — own-impact, not transferable alpha. Guards: (a) the outcome guard catches "favorable move, adverse settlement"; (b) `last_market_price` is the latest pre-resolution snapshot (hours later), so transient own-book pressure has decayed; (c) the capture margin debits a worse copier fill. These reduce but cannot eliminate reflexivity on paper data — so CLV stays a lens, and `spec_footprint` certifying on CLV yet failing the outcome guard is itself a correct, informative verdict ("moves the line, not the result").

**Caveat (verified, weak).** For fast-resolving sports, a `spec_footprint` row may receive only 1–2 housekeeping snapshots before resolution (`housekeeping.rs:120` sleeps 120ms/cond over many conds), so `initial ≈ last` and the captured move understates the early drift the selection targets. Report the snapshot count; treat thin-snapshot rows as low-confidence.

**Integration points.** New query `storage/consensus.rs` (mirror :466); board column `board.rs:170-200`; outcome guard reuses `consensus_scoreboard_by_strategy` row's `surplus`/`surplus_sd` + `surplus_bounds`.

**Multiple-testing.** Zero NEW promotion hypotheses — CLV is a guard/lens on the SAME arms, not a separate promotable strategy (spend alpha once, on the outcome gate).

**Source.** rethink (the variance insight) tempered by verification (blind-baseline gap → lens not certifier).

---

### 6. AS-OF / walk-forward harness + null + holdout (offline; gate for any fitted/mined arm)

The live arms (3,4) are forward-by-construction and need nothing here. This phase exists for honest backtest/holdout reporting and as the **hard prerequisite** for any arm that *fits* to history (Item 7 fitted weights, Item 8 coalition mining).

**Why it is required for fitting.** `trader_slice_scores` is a **global snapshot** with no as-of cut (`storage/consensus.rs:857`, `WHERE resolved`). Applying today's resolved fills to a 2026-03 signal weights it with future-resolved outcomes; even the band-blind leaks. Fix = a `resolved_at < cut` parameter (`trader_fills.resolved_at` exists, `026_trader_fills.sql:36`).

```rust
// storage/consensus.rs — NEW, parameterized clone of trader_slice_scores (:857-904).
pub async fn trader_slice_scores_asof(&self, cut: DateTime<Utc>) -> Result<Vec<TraderSliceStat>> {
    // identical CTEs, plus  AND resolved_at IS NOT NULL AND resolved_at < $1  in the adv CTE,
    // so BOTH the slice surplus AND the band-blind are computed within the cut (leak-free).
    // Drop recency7d/30d (ambiguous "7d before cut"); keep overall/sport/band — what arms consume.
}
```

```rust
// scanner/asof_harness.rs — NEW offline (#[ignore] test or binary subcommand).
// For each (event,day-ish) cut t chronologically:
//   1. weights/coalitions := f(trader_slice_scores_asof(t))         // ONLY past-resolved
//   2. emit forward picks for signals whose freshest backer ts >= t // reuse forward_ok(sig,Some(t),now) @ enrich/mod.rs:211
//   3. let the EXISTING resolve→scoreboard→gate judge them          // no special judging
// TRAIN cuts (fit/mine) vs HOLDOUT cuts (report). Two NULLs:
//   identity-shuffle (permute wallet labels within cut) → certified edge → 0
//   outcome-shuffle  (permute outcome_won within event) → surplus → 0
```

**Integration points.** New query `storage/consensus.rs`; new harness `scanner/asof_harness.rs`; reuses `forward_ok` (`enrich/mod.rs:211-223`) as the per-cut forwardness guard and `surplus_bounds` as the judge.

**Multiple-testing.** Zero live hypotheses; it is the instrument that lets Items 7/8 spend their budget honestly.

**Source.** direct (P4).

---

### 7. Arm B — `arm_edge_pool` (fixed gate-derived weights). OPTIONAL / deferred.

A log-odds nudge of the live mid by each backer's certified, shrunk slice bound. Forward-live with **fixed** weights (no fitting ⇒ same as-of posture as Items 3/4). **Deferred and may be cut**, because at current N only ~0–1 backers per book are certified-in-sport, so the pool degenerates to ≈ Arm A while spending another hypothesis.

```rust
// scanner/enrich/edge_pool.rs — NEW (build only after A/D prove the plumbing).
// z = logit(mid);  for each backer with a sport SliceTrust:
//   w = match verdict { Trusted => st.lower_bound, Avoid => st.upper_bound, _ => 0.0 };
//   z += POOL_TEMP * w * (st.n_events/(st.n_events+20.0));   // reused n/(n+20) shrink (consensus_cycle.rs:67)
// emit if sigmoid(z) - mid > capture_margin.   POOL_TEMP = 1.0 FIXED (fitting needs Item 6).
```

**Honesty note (verified weak point).** The summed term adds a probability-scale surplus (~0.08) into log-odds space — a heuristic **monotone nudge**, NOT a calibrated probability. Call it that. Reads `clob_mid` from `ctx.markets` (`enrich/mod.rs:150-156`), which `prefetch_markets` populates **only for strict-fired markets** (`consensus_cycle.rs:641`) — so this arm must ride `strict` rows (where the mid exists), unlike Arms A/D which ride pre-strict `_blind` books. That coupling is another reason it is secondary.

**Multiple-testing.** +1 (experimental 9→10) if built.

**Source.** direct (P3), downgraded to optional on verified degeneracy.

---

### 8. Arm C — coalition mining. OPTIONAL / last / EXPECTED NULL.

Built only on Item 6, never live-first. Restrict the search to pairs/triples of the **per-sport Trusted specialists Arm A already certifies** (turns `2^103` into a handful per sport). At each as-of cut, mine candidates co-occurring on the same event-outcome ≥K times, pre-register survivors as named `StrategyDef`s (appended like `trust_arms`, `consensus.rs:697-718`), emit forward, judge with Bonferroni over the **entire** candidate set ever scored.

**Honest accounting.** With per-coalition N far below the per-wallet N (a specific trio co-occurs rarely) and a search-wide Bonferroni denominator in the hundreds, the corrected lower bound will essentially never clear the capture margin. **The designed, acceptable output is an honest NULL** ("no coalition certifies at this N"); a green C would be the surprise. May be deferred indefinitely.

**Source.** direct (P5), downgraded to optional honest-null instrument per the brief's prior.

---

## Execution Order

1. **Phase 0 — Item 1 (capture margin).** Unlocks: every downstream verdict is judged at the capturable bar. Green: `cargo build` + `promotion.rs` unit tests (`:183-240`, pass explicit margins, unaffected); board renders with `margin=0.03`.
2. **Phase 1 — Item 2 (per-slice trust map + one EnrichCtx field).** Unlocks: arms can condition on backer×sport. Green: `cargo build`; `enrich_all` passthrough test (`enrich/mod.rs:258`) still green (new field unread when no arm enabled); add a unit test for `slice_trust_for_wallet` mirroring `trader_trust.rs:209-258` (Trusted/Avoid/Indeterminate/floor).
3. **Phase 2 — Items 3 & 4 (Arm A + Arm D), forward-live.** Unlocks: the conditional engine emits silent rows judged by the existing gate. Green: per-arm unit tests (seed a `_blind` fixture + a seeded `SliceTrustMap`): emits a `Tier::Watch` row on the certified case; no-op when map empty / backer Indeterminate-in-sport / flag off. Default-OFF ⇒ portfolio byte-identical.
4. **Phase 3 — Item 5 (CLV lens + outcome guard).** Unlocks: lower-variance reporting + reflexivity/settlement guard. Green: new reporting query compiles; board shows CLV bound + outcome guard beside the verdict.
5. **Phase 4 — Item 6 (as-of harness + null + holdout)** lands **before** any fitted/mined arm. Green: `trader_slice_scores_asof` compiles; null shuffles drive surplus→0 in the `#[ignore]` harness.
6. **Phase 5 (optional) — Item 7 (edge_pool), then Item 8 (coalition).** Only if Phases 2–3 show ≥1 certified specialist actually firing; otherwise document the null and stop.

The as-of SQL + null/holdout (Phase 4) precede the only arms that fit (7,8). A/D (Phase 2) are forward-by-construction and need nothing but the one EnrichCtx field.

## Certification & Report Spec

Per arm (`spec_footprint`, `spec_contrarian`, and optional `edge_pool`/coalitions), the board renders — all over **event-clustered** units, the existing gate's N:

| column | source | meaning |
|---|---|---|
| events (N) | `distinct_events` (`storage/consensus.rs:524`) | de-correlated sample |
| surplus | `surplus` (`:527`) | edge over band-`_blind` (FLB-neutralized) |
| lower bound | `promotion_verdict(N, surplus, sd, n_family, {margin=slip+fee})` (Item 1) | capturable, Bonferroni one-sided |
| our CLV move | Item 5 query lower bound | line-movement edge (lower variance; lens only) |
| outcome guard | `surplus_bounds(...).1 ≥ −margin` | resolved subset not adverse |
| verdict | derived | **TRUSTED** (`lo>margin` AND guard OK) / **INDETERMINATE** / **AVOID** (`hi<−margin`) — the `trader_trust.rs:164-170` convention at the arm level |
| null check | Item 6 harness | identity- + outcome-shuffle surplus must be ≈0 |

Each arm is reported **vs naive count** (`strict`/`count` rows already on the board) and **vs market** (CLV). For forward-live arms (A/D) the on-board forward record **is** the holdout (every unit emitted live, resolved later); fitted/mined arms (7,8) report the Item 6 walk-forward holdout split. **An all-INDETERMINATE board is a correct result** — the win is a correctly-judged instrument.

## Existing Infrastructure Leveraged

- Belief-blind gate `promotion_verdict`/`surplus_bounds` + `PromotionParams.margin` (`promotion.rs:102-177`) — reused unchanged; zero new statistics.
- Per-slice surplus SQL `trader_slice_scores` (`storage/consensus.rs:857-904`) + `TraderSliceStat` (`:1003`) — the per-sport edge already exists.
- Event-clustered, FLB-neutralized outcome scoreboard `consensus_scoreboard_by_strategy` (`storage/consensus.rs:466-540`) — the arms' primary judge.
- The silent arm seam: `Enricher` (`enrich/mod.rs:173`), `registry()` (:176), `re_emit→Tier::Watch` (:199), `family()` experimental split (:228), `forward_ok` (:211); per-arm flag pattern `EnrichModels.bayes_enabled`/`load_models` (`enrich/mod.rs:47,125`, gated at `bayes.rs:18`).
- `sport_bucket` single-source-of-truth classifier shared with `trader_fills.sport` (`consensus_cycle.rs:125`) — no classification drift.
- The slow trust-refresh cadence `trust_refresh_mins` (`config.rs:173`) — both maps from one snapshot.

## Open Questions (resolved during implementation)

1. **event_slug granularity / clustering unit** — WHEN: Phase 1, before any clustering change. HOW: one read-only query for the fills-per-`event_slug` distribution and the fraction of multi-day (non-date-stamped) `event_slug`s. Verified so far: activity `eventSlug` is a **date-stamped per-game slug** (e.g. `"nba-por-phi-2026-03-15"`, `copy_trader.rs:89,626`), so existing event-clustering already collapses a game's many markets and already encodes the day. **This is why the `(event,day)` change is rejected** (see below); the probe is to confirm the multi-day-futures fraction is negligible.
2. **Wallet case normalization** — WHEN: Phase 1. HOW: confirm `trader_fills.wallet` and `BackerInfo.wallet` share the lower-cased convention the existing `TrustMap` already relies on (`consensus_cycle.rs:79-81`, `earned_quality` lookup at :64 does not re-case). Build and query `SliceTrustMap` with the identical convention; add a lookup-hit assertion to the arm unit test.
3. **`spec_footprint` snapshot density for fast sports** — WHEN: Phase 3. HOW: report per-row snapshot count; gate the CLV lens on ≥2 snapshots.

## Rejected Approaches

- **`(event_slug, day)` re-clustering (DIRECT P0a; RETHINK §4 CLV query).** REJECTED. Verified `eventSlug` is a date-stamped per-game slug (`copy_trader.rs:89,626`), so `(event,day)` is a **no-op** for sports and **anti-conservative** for any non-dated multi-day futures (`date_trunc('day')` splits one correlated event into many day-units, monotonically **increasing** N and making the gate *easier*, the wrong direction for rigor). Existing event-clustering already collapses the within-match multi-market leak via the shared slug. Both designs misread this as a rigor fix. Keep the existing key; revisit only if the Open-Question-1 probe finds a material multi-day-futures fraction.
- **RETHINK's CLV-movement as the SOLE certifier.** REJECTED as primary. Its band-blind requires `_blind` rows to carry `initial/last_market_price`; housekeeping **explicitly never snapshots `_blind`** (`housekeeping.rs:148`), so the blind CTE degenerates to 0 — no FLB/drift neutralization, contradicting RETHINK §5(1). The variance insight is kept as a reported lens + outcome guard (Item 5); primary certification stays on the outcome scoreboard, whose `_blind` baseline does work (it needs only `outcome_won`+`mean_price`, both present on resolved `_blind` rows).
- **DIRECT's `arm_smart_vs_dumb` + the `books: &[MarketBook]` EnrichCtx field.** REJECTED in favor of `arm_spec_contrarian` (Item 4). It required opposer identities (a new ctx field) and keyed on certified-**Avoid** money, which is near-empty at current N (`dumb_against≈0`). The contrarian reframe needs neither, keeping EnrichCtx at a single new field and firing more honestly.
- **DIRECT's three-field EnrichCtx (`slice_trust`, `books`, `capture_margin`).** REDUCED to one (`slice_trust`). Sport is read off the signal's own `title`/`slug` (`consensus.rs:256-257`); the capture margin belongs at the gate/board (Item 1), not the arm; `books` is unnecessary once D is the contrarian.
- **DIRECT's `is_empty()`-only arm gating / RETHINK's `ctx.cfg_first_footprint()`.** Both wrong. `slice_trust` is shared, so `is_empty()` can't toggle arms independently; `ctx.cfg_*()` accessors do not exist. Use the verified per-arm `EnrichModels` bool pattern (`bayes_enabled`, set in `load_models`, checked at `bayes.rs:18`).
- **Coalition mining as a headline.** Demoted to optional/last/expected-NULL (Item 8): the `(event,day-ish)` sample (only ~10/90 wallets clear even the overall floor) and a search-wide Bonferroni make a clearing coalition essentially impossible; its value is a documented honest null behind the Item 6 harness.
