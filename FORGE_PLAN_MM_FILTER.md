# Implementation Blueprint: Market-Maker Detection & Filtering (signal-cleaning)

After this is built, the engine stops treating liquidity-provision churn as prediction. Every
tracked wallet gets a **cross-referenced, calibrated, auditable MM verdict** — `MM | Unknown |
Human` — computed hourly from the SELL leg the current system throws away, cross-checked against
its resolution edge, and validated by whether excluding the churners actually makes the survivor
pool *more persistent out-of-sample* (not by a hand label). The 115 existing `bot` flags and the
29–72 human survivors get reconciled against the new verdict **before** the winner's-curse
persistence test consumes them. Nothing touches the live alert path until it is forward-proven.

> Provenance: 4-agent Forge (diagnose → dual-design Direct/Rethink → reality-check+synthesis),
> 2026-07-04. Every file:line verified against source. Companion: `FORGE_DEBATES_MM_FILTER.md`.
> This is a PLAN — no code written yet. Gate for implementation = `cargo build && cargo test`.

---

## The reframe that shapes everything

The user's ask arrived mid-stream with critical context: the blunt classifier (`classify_trader_types`,
`fpd ≥ 400`) has **already run**, flagged **115 wallets `bot`**, and after filtering them **only
29–72 humans** survive with enough monthly history for the persistence test. So this is **not** a
greenfield detector — it is **"cross-reference and make it reliable"**, at a stakes where every
**false positive silently deletes 1 of ~29 usable humans** (starves the test) and every **false
negative re-pollutes the pool with break-even churn PnL** (revives the hot-run confound).

Three verified facts set the design:
1. The only live MM defense is the **in-window, per-market, BUY-only two-sided drop** in `score_market`
   (`consensus.rs:365-382`). The "59% of top wallets are MMs" figure (DECISIONS.md D23) was measured
   *after* it runs — proof it is insufficient.
2. **No Rust reads `trader_type`.** The live book filter is `COALESCE(consensus_eligible OR
   earned_eligible, TRUE)` (`storage/consensus.rs:1403`). The 115 flags feed **only** the offline
   Python persistence analysis today — so hardening is free of live-path risk *now*.
3. **The SELL leg is captured but featurized nowhere.** `advantage` is `CASE WHEN side='BUY'` (NULL
   for every SELL, `storage/consensus.rs:1450-1451`); `trader_slice_scores` filters `side='BUY'`
   (`:1507`). Half of every MM's activity — the leg that *defines* market-making (round-tripping) —
   is invisible. **This is the untapped signal.**

Reliability here = **cross-reference (agreement of independent signals) + calibration (measured FP/FN)
+ validation-by-downstream-effect (non-circular) + fail-open-for-humans + shadow-first**. Not a
cleverer threshold.

---

## Items

### 1. Position-lifecycle microstructure: featurize the SELL leg — `fpd`-blind MM signals
**(closes GAP-2 + GAP-3 in one query)**

**Before**: MM-ness is inferred from BUY-side fill *counts* (`fpd`, in-window both-outcomes). A
scalper that churns BUY→SELL→BUY on **one** outcome never shows 2 outcomes and is counted as **one
clean backer** (`consensus.rs:433`; test `laddering_one_wallet_counts_once` `consensus.rs:1028`). A
patient MM at 195 fills/day reads `human`; a World-Cup-burst human at 473 fills/day reads `bot`.

**After**: per-wallet microstructure at the **position grain** `(wallet, condition_id, outcome_index)`,
so MM-ness is read from *how positions end*:

| wallet | round_trip_rate | sell/buy $ | two_sided_rate | fpd | today | new read |
|---|---|---|---|---|---|---|
| $36.6M churner (D26) | 0.78 | 0.92 | 0.64 | ~600 | bot (by luck) | churn screams MM |
| patient MM (40k/205d) | 0.71 | 0.88 | 0.61 | **195 → human (FN)** | pollutes pool | caught — *fpd-independent* |
| WC-burst human (5.2k/11d) | 0.04 | 0.05 | 0.02 | **473 → bot (FP)** | deletes a human | spared (holds to resolution) |
| soccer 0xe9a6ed2e4d (+10–11%) | ~0.03 | ~0.04 | ~0.00 | — | genuine | spared |

**Implementation** — NEW `wallet_microstructure()` in `common/src/storage/consensus.rs`, sibling to
`trader_slice_scores` (`:1497`). One aggregation over `trader_fills` (BUY+SELL — *no* side filter,
that is the point), hitting `idx_tf_cond_outcome` (`026:47`) and `idx_tf_wallet` (`026:46`):

```sql
WITH pos AS (                                 -- one row per held (wallet, condition, outcome)
  SELECT wallet, condition_id, outcome_index,
         SUM(size_usd) FILTER (WHERE side='BUY')  AS buy_usd,
         SUM(size_usd) FILTER (WHERE side='SELL') AS sell_usd,
         COUNT(*)      FILTER (WHERE side='BUY')  AS n_buy,
         COUNT(*)      FILTER (WHERE side='SELL') AS n_sell,
         MIN(ts) FILTER (WHERE side='BUY')        AS first_buy,
         MAX(ts) FILTER (WHERE side='SELL')       AS last_sell,
         MIN((ts AT TIME ZONE 'UTC')::date)       AS pos_day
  FROM trader_fills
  GROUP BY wallet, condition_id, outcome_index
),
sided AS (                                    -- lifetime both-sides (GAP-3); reuses specialist_mining MECH_SQL idea
  SELECT wallet, condition_id, COUNT(*) FILTER (WHERE n_buy > 0) AS n_out_held
  FROM pos GROUP BY wallet, condition_id
),
two AS ( SELECT wallet, AVG((n_out_held >= 2)::int)::float8 AS two_sided_rate
         FROM sided GROUP BY wallet )
SELECT p.wallet,
       COUNT(*)                                              AS n_positions,
       COUNT(DISTINCT p.condition_id)                        AS n_conditions,   -- market breadth
       COUNT(DISTINCT p.pos_day)                             AS n_days,         -- DAY-DEFLATION N
       AVG( (p.n_sell>0 AND p.n_buy>0)::int )::float8        AS round_trip_rate,-- the SELL-leg tell
       (SUM(LEAST(p.sell_usd,p.buy_usd)) / NULLIF(SUM(p.buy_usd),0))::float8 AS sell_buy_ratio,
       percentile_cont(0.5) WITHIN GROUP (
         ORDER BY EXTRACT(EPOCH FROM (p.last_sell - p.first_buy)))
         FILTER (WHERE p.n_sell>0 AND p.n_buy>0)::float8     AS median_hold_s,  -- ADVISORY only (see note)
       t.two_sided_rate
FROM pos p JOIN two t USING (wallet)
GROUP BY p.wallet, t.two_sided_rate;
```
```rust
// common/src/storage/consensus.rs — sibling to TraderSliceStat (:1907). NEW.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct WalletMicro {
    pub wallet: String,
    pub n_positions: i64,      // total (w,cond,outcome) positions — the "despite volume" input for the edge axis
    pub n_conditions: i64,     // distinct markets — structural-MM breadth (thousands ⇒ LP, not picker)
    pub n_days: i64,           // distinct fill-days — DAY-DEFLATION floor (mirrors TraderSliceStat.n_days)
    pub round_trip_rate: f64,  // fraction of positions bought AND sold back — churn axis, fpd-independent
    pub sell_buy_ratio: f64,   // $ churned back / $ bought (≈0.9 MM, ≈0.05 human) — corroborant
    pub median_hold_s: Option<f64>, // scalp vs conviction; ADVISORY (ts as-of noise on backfilled rows)
    pub two_sided_rate: f64,   // fraction of conditions ever held on ≥2 outcomes (lifetime GAP-3)
}
```
**Note (as-of discipline)**: `median_hold_s` uses `ts`, a real fill timestamp on live+backfill rows,
but `resolved_at` is a bulk-ingest stamp — so hold-time is trustworthy for ordering but kept
**advisory (audit-only, Item 6)**, never a gating feature. `round_trip_rate` and `sell_buy_ratio`
are timestamp-*order*-only and carry the churn signal.

**Integration**: `storage/consensus.rs:~1497` new method; consumed only by Item 2's `compute_mm_map`.
No schema change; read-only.

**Cost**: +1 hourly aggregation, ~2× the row-scan of the BUY-only `trader_slice_scores` (still one
pass on ~1.8M rows with the two indices; sub-second). **Zero** live-cycle (~2 min) delta.

**Source**: rethink (position-grain unit of observation) — cleaner than summing BUY/SELL features
wallet-first; both designs produced the same columns, this framing is crisper.

---

### 2. Cross-referenced verdict: two orthogonal axes must agree, humans fail open
**(refines/closes GAP-4)**

**Before**: `CASE WHEN fpd>=400 THEN 'bot'` (`storage/consensus.rs:1336`) — one uncalibrated
threshold, inverts both error directions.

**After**: a wallet is `MM` only when **two genuinely-independent axes agree AND it has no proven
edge**:
- **Structural axis** (how it trades) = churn `S1` OR both-sides `S2`
  (`round_trip_rate ≥ τ_rt AND sell_buy_ratio ≥ τ_sb`)  OR  (`two_sided_rate ≥ τ_2s`)
- **Edge axis** (does it predict) = `S3` = resolution-edge ≈ 0 *despite* volume
  (`TrustVerdict::Indeterminate AND n_positions ≥ V`) — the **invert-the-trust-gate** signal, computed
  from the *already-cached* `trader_slice_scores`, **zero new features**.
- **Fail-open guard** = a wallet whose existing `trust_verdict` is `Trusted` is **never** `MM`,
  regardless of churn (it demonstrably predicts).

```rust
// copy-trading-bot/src/scanner/trader_trust.rs — next to TrustVerdict (:67). NEW.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MmVerdict { Mm, Unknown, Human }   // Unknown FAILS OPEN for pool membership (never deletes)

#[derive(Debug, Clone)]
pub struct MmSignals {                       // per-wallet signal vector + decision; feeds the audit table
    pub wallet: String,
    pub structural: bool,   // S1 (churn) OR S2 (both-sides) — the "how they trade" axis
    pub edge_zero_vol: bool,// S3 — Indeterminate edge despite n_positions ≥ V — the "do they predict" axis
    pub s1_churn: bool, pub s2_two_sided: bool,   // kept split for the audit trail / driver
    pub verdict: MmVerdict,
    pub round_trip_rate: f64, pub sell_buy_ratio: f64, pub two_sided_rate: f64,
    pub n_positions: i64, pub n_days: i64, pub surplus: f64, pub driver: &'static str,
}
pub type MmMap = std::collections::HashMap<String, MmSignals>;  // sibling to TrustMap; NOT overloaded onto it

// promotion.rs — next to TrustParams (:130). Thresholds frozen at domain/precedent values,
// operating point chosen by Item 3's calibration, NEVER hand-tuned for signal.
pub struct MmParams {
    pub tau_rt: f64,   // round-trip cutoff  (calibrated; ~0.30)
    pub tau_sb: f64,   // sell/buy cutoff    (calibrated; ~0.30)
    pub tau_2s: f64,   // two-sided cutoff — FROZEN at 0.30 (specialist_mining.py precedent)
    pub min_volume: i64,        // V for S3 — a low-N human must not read edge≈0 as "MM"
    pub min_days_for_human: i64,// day-floor before a wallet may be called Human (mirrors trust min_events)
}
```
```rust
// trader_trust.rs — sibling to trust_verdict (:178). REFINED (2-orthogonal-axes, not raw K≥2).
fn mm_verdict(m: &WalletMicro, trust: Option<&TraderTrust>, p: &MmParams) -> MmSignals {
    let s1 = m.round_trip_rate >= p.tau_rt && m.sell_buy_ratio >= p.tau_sb;   // churn
    let s2 = m.two_sided_rate  >= p.tau_2s;                                   // both-sides
    let structural = s1 || s2;                                               // ONE axis (S1,S2 correlated)
    let edge_zero_vol = matches!(trust.map(|t| t.verdict), Some(TrustVerdict::Indeterminate))
                        && m.n_positions >= p.min_volume;                     // orthogonal edge axis
    let proven = matches!(trust.map(|t| t.verdict), Some(TrustVerdict::Trusted));
    let verdict = if structural && edge_zero_vol && !proven {
        MmVerdict::Mm                                    // 2 orthogonal axes agree + no proven edge
    } else if !structural && m.n_days >= p.min_days_for_human
              && !matches!(trust.map(|t| t.verdict), Some(TrustVerdict::Indeterminate)) {
        MmVerdict::Human
    } else {
        MmVerdict::Unknown                               // fail-OPEN: stays in pool, weight-capped (Item 4)
    };
    let driver = if s1 {"round_trip"} else if s2 {"two_sided"} else if edge_zero_vol {"edge_zero_vol"} else {"none"};
    MmSignals { /* … raw features + verdict + driver … */ }
}
```
**Why 2 axes, not B's raw K≥2 (reality-check refinement)**: S1(churn) and S2(both-sides) are both
"how they trade" and are correlated — counting them as 2 of 3 votes overstates independence and
inflates the "multiplicative-FP" claim. The genuinely orthogonal split is **structural (S1∨S2) AND
edge (S3)**: a churner and a predictor can look identical on structure but *never* on resolution
edge. Requiring both axes + `!proven` is what actually bounds the false-positive that would delete a
human. (Both agents independently added the `!proven` guard — it is load-bearing, kept.)

**Integration**: NEW `compute_mm_map(pf, p)` in `cycles/consensus_cycle.rs`, a structural twin of
`compute_trust_map` (`:131`), built in the **same** `live.rs` slow refresh; `S3` reuses the cached
`trader_slice_scores` (served from `cached_slice_scores`, `trader_trust.rs:39`) → **0 extra queries**
beyond Item 1.

**Cost**: +0 queries over Item 1. O(1)/wallet in memory. **Source**: hybrid — rethink's orthogonal-
agreement spine + direct's explicit `!proven` guard, refined on the axis-independence finding.

---

### 3. Two-tier validation: labeled calibration + the label-free downstream-effect test
**(closes GAP-1 — the reliability spine)**

**Before**: zero measured error rate on `fpd≥400`. Unknown FP → could be silently deleting several
of the ~29 humans.

**After**: the verdict ships with a *measured* FP/FN, a passed permutation-null, **and** proof that
excluding its MMs *improves* the survivor pool's out-of-sample persistence.

- **Tier 1 (labeled)** — NEW `scripts/mm_calibrate.py`, cloning `scripts/selection_null.py`'s
  permutation machinery. Labeled set (~40): MMs = the $36.6M churner + the D23 crypto up-down 6/8
  two-sided wallets + D23 tennis wallets; Humans = `0xe9a6ed2e4d…`, `0x56f0321917…` (~0% two-sided,
  DECISIONS.md:734) + hand-verified cleanest of the 29. Compute per-axis and ensemble FP/FN over a
  τ-grid; run the **label-permutation null** (shuffle labels ≥1000×, require real separation in the
  right tail, `p ≤ 0.01` — the D23 standard, `promotion.rs:97`). Emit the chosen `MmParams` operating
  point + report to `reports/entries/`.
- **Tier 2 (label-free — the non-circular ground truth)** — NEW `scripts/mm_persistence_effect.py`,
  reusing `scripts/persistence_tracker.py`'s cutoff + event-clustering. Split the human pool
  early/late by fill-day; compute top-pick early→late surplus correlation **with vs without** the
  Item-2 MMs. Verdict metric = **Δcorr** (dossier baseline: early→late corr **−0.10**). Positive Δ =
  exclusion removes noise → validated; ≤0 = exclusion isn't consuming MMs → **revert**, no label needed.

**Why Tier 2 is decisive (reality-check)**: the labeled set is drawn from the *same* two-sided
heuristic being tested (`specialist_mining` `two_sided_frac≥0.30`), so Tier-1 AUC is **partly
circular** — a two-sided-based classifier will "predict" two-sided-defined labels. Tier 2 needs **no
labels**: if removing suspected churners doesn't make the pool more persistent out-of-sample, the
classifier is worthless regardless of any label; if it does, it is validated on the exact metric the
persistence work depends on. This is the reliability the user asked for.

**Discipline (from direct path)**: freeze `tau_2s` at the precedent 0.30 and keep the calibrated
knobs minimal (`tau_rt`, `tau_sb`, `min_volume`); with ~40 labels, calibrating many thresholds
overfits — the K-of-axes conjunction + Tier-2 effect, not a finely-fit boundary, carry reliability.

**Integration**: offline Python only (matches every gate here — calibrate out-of-band, paste the
operating point into `MmParams::default()`, exactly like `SELECTION_NULL_P`, `promotion.rs:197`).
Tier-1 gates the *shadow* deploy; Tier-2 gates any *live* consideration. **Cost**: two manual scripts,
zero live/DB cost beyond ad-hoc reads. **Source**: rethink (two-tier, label-free Tier-2) + direct
(one-knob-not-five discipline).

---

### 4. Fail-closed weighting seam: cap suspected-MM weight, never zero, never full
**(closes GAP-5)**

**Before**: `TrustVerdict::Indeterminate ⇒ quality_weight(rank)` — a break-even MM at rank 20 keeps
full weight **1.6** (`consensus_cycle.rs:77`; `quality_weight(20)=1.6`, `consensus.rs:317-322`); it
can only lose weight via `Avoid` (`hi<0`), which break-even never triggers.

**After**: at the per-vote stamp (`consensus_cycle.rs:646-659`), after `earned_quality`, cap by the
`MmMap` — reusing the exact `.clamp(0.5,1.0)` idiom already on the `Avoid` branch (`:76`):
```rust
let (mut eq, trusted, certified) = earned_quality(trust, &v.trader_wallet, v.rank);
let is_mm = matches!(mm.get(&v.trader_wallet).map(|s| s.verdict), Some(MmVerdict::Mm));
if let Some(sig) = mm.get(&v.trader_wallet) {
    let cap = match sig.verdict { MmVerdict::Mm => 0.5, _ if sig.structural => 1.0, _ => f64::INFINITY };
    eq = eq.min(cap);          // INFINITY ⇒ no-op ⇒ byte-identical when MmMap empty / wallet absent
}
// cell_earned_quality capped identically; is_mm rides onto the TraderVote (Item 5).
```
`score_market` stays **pure** — `is_mm`/the cap arrive on the vote from the impure layer, never
computed in the scorer. **Cost**: O(1) hashmap lookup/vote, zero DB. **Note**: weighted arms
(`CONSENSUS_TRUST_ARMS`) are OFF today (DECISIONS.md:747), so this seam is dormant-but-correct — any
future MM-aware weighting inherits the right asymmetry. **Per-cell extension** (crypto-MM keeps NBA
weight): the `CellMap`/`slice_pooled_quality` machinery (`trader_trust.rs:108-121`) supports a
per-`(wallet×sport)` cap later — deferred to v2. **Source**: both (identical); merged direct's 0.5
confirmed-MM floor with rethink's 1.0 suspected-band cap.

---

### 5. Live wiring, shadow-first: an `exclude_mm` arm that stays silent until forward-proven
**(the "does it gate alerts" question, isolated as a separate step)**

- **`TraderVote`** (`consensus.rs:30-69`): add `pub is_mm: bool`, default `false`. ⚠️ touches **9
  constructor sites** (`consensus_cycle.rs:663` + 8 test helpers in `consensus.rs`) — mechanical;
  update all, keep `ConsensusParams::default()` behavior byte-identical (test `consensus.rs:1206`).
- **`ConsensusParams`** (`:149-189`): add `pub exclude_mm: bool`, default `false` — mirrors
  `trusted_only`/`certified_only` (`:177,188`).
- **`score_market` keep closure** (`:361-363`): `... && (!params.exclude_mm || !v.is_mm)`.
- **`books_from_window_votes`** (`consensus_cycle.rs:631,646`): add `mm: &MmMap` param; stamp `is_mm`.
- **`mm_arms(base)`** (NEW, mirrors `trust_arms` `consensus.rs:750`): one silent arm
  `exclude_mm:true, alerting:false`, registered in `active_portfolio` (`consensus_cycle.rs:977`) only
  under NEW env `CONSENSUS_MM_ARMS` (default false; mirror `CONSENSUS_TRUST_ARMS`, `config.rs:243`).
  A **separate** `EXCLUDE_MM` flag (default false) gates ever touching the live `strict` filter.
- **Shadow test** (NEW, mirror `deep_pool_excluded…shadow_differs` `consensus_cycle.rs:1398`): a
  seeded MM vote makes the MM-excluding book differ from incumbent — proves the gate is load-bearing.

**Live `strict` alert path (Component A) stays byte-identical** until Item-3 Tier-2 is positive AND
the shadow arm has forward-proven. **Cost**: no live-cycle cost (arm scores already-built books).
**Source**: both (identical; mirrors the trust-arms ladder verbatim).

---

### 6. Audit trail + reconciliation of the 115 flags — never overwrite `trader_type`
**(closes GAP-6 + the literal "cross reference" ask)**

**Before**: bare `trader_type TEXT` (`mig 038`), no features/confidence/reason; `classify_trader_types`
is a **blind in-place UPDATE** (`storage/consensus.rs:1335-1338`) that destroys the prior label.

**After**: a NEW append-only table carrying the full signal vector per wallet, written *alongside*
(never over) `trader_type`, plus a reconciliation report of old-vs-new.
```sql
-- migrations/039_mm_verdicts.sql — append-only, idempotent, additive. NEVER edit once applied.
CREATE TABLE IF NOT EXISTS mm_verdicts (
    wallet            TEXT NOT NULL,
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verdict           TEXT NOT NULL,          -- 'MM' | 'UNKNOWN' | 'HUMAN'
    structural        BOOLEAN NOT NULL, edge_zero_vol BOOLEAN NOT NULL,
    s1_churn          BOOLEAN NOT NULL, s2_two_sided  BOOLEAN NOT NULL,
    round_trip_rate   DOUBLE PRECISION, sell_buy_ratio DOUBLE PRECISION,
    two_sided_rate    DOUBLE PRECISION, n_positions BIGINT, surplus DOUBLE PRECISION,
    driver            TEXT,
    PRIMARY KEY (wallet, computed_at)         -- append-only history; latest = MAX(computed_at)
);
CREATE INDEX IF NOT EXISTS idx_mmv_wallet ON mm_verdicts (wallet, computed_at DESC);
```
Written by `upsert_mm_verdicts(&[MmSignals])` in `compute_mm_map`'s refresh. **Reconciliation** (NEW
read-only query or `scripts/mm_reconcile.py`) — the disagreement set the user wants surfaced *before*
the persistence test runs:
```sql
SELECT ft.proxy_wallet, ft.trader_type AS old_label, v.verdict AS new_verdict,
       v.driver, v.round_trip_rate, v.two_sided_rate, v.surplus, v.n_positions
FROM followed_traders ft
JOIN LATERAL (SELECT * FROM mm_verdicts m WHERE m.wallet = LOWER(ft.proxy_wallet)
              ORDER BY computed_at DESC LIMIT 1) v ON TRUE
WHERE (ft.trader_type = 'bot') != (v.verdict = 'MM');
```
Surfaces (a) old-`bot`/new-`Human` = **burst-human FPs the `fpd` rule wrongly deleted → restore to
the 29–72 pool**; (b) old-`human`/new-`MM` = **patient-MM FNs polluting the pool → exclude**. Both
feed Item-3 Tier-2 and a **human review** before any wallet is removed (deleting 1 of ~29 > leaking 1
MM). **Cost**: +1 small upsert/hour. **Source**: rethink (append-only PK `(wallet, computed_at)`
keeps verdict-drift history) over direct's single-row table.

---

## Execution Order

1. **Item 1** (`wallet_microstructure` + `WalletMicro`) — foundation; unlocks 2, 3, 6.
   - *Verify*: run the query against the live DB; confirm the $36.6M churner reads `round_trip_rate`
     high and `two_sided_rate ≥ 0.6`, and a known soccer human reads both ≈ 0.
2. **Item 6 migration + audit write** (mig 039 + `upsert_mm_verdicts`) — needed so 2 can persist.
   - *Verify*: `cargo test` migration applies idempotently; `trader_type` untouched.
3. **Item 2** (`mm_verdict` + `compute_mm_map` + `MmMap`) — depends on 1, 6; unlocks 3, 4, 5.
   - *Verify*: `MmMap` populates in the slow refresh; spot-check 5 known wallets' verdicts + drivers.
4. **Item 3 Tier-1** (`mm_calibrate.py`) — depends on 2's audit rows; sets `MmParams::default()`.
   - *Verify*: permutation-null `p ≤ 0.01`; report FP/FN; freeze the operating point.
5. **Item 6 reconciliation** (`mm_reconcile.py`) — depends on 2; the cross-reference deliverable.
   - *Verify*: the old-vs-new disagreement list is produced and human-reviewed **before** the
     persistence test consumes the pool.
6. **Item 3 Tier-2** (`mm_persistence_effect.py`) — depends on 2 + reconciliation.
   - *Verify*: Δcorr on early→late persistence with-vs-without MMs is **positive**; else revert.
7. **Item 4** (weight-cap seam) — depends on 2; dormant until weighted arms on.
   - *Verify*: with `MmMap` empty, `earned_quality` output byte-identical (existing tests green).
8. **Item 5** (shadow `exclude_mm` arm) — depends on 2 + 4; **only after** Tier-2 positive.
   - *Verify*: `ConsensusParams::default()` byte-identical (test `consensus.rs:1206`); shadow test
     shows the MM-excluding book differs on a seeded MM vote; live `strict` alerts unchanged.

**Gate before touching the live `strict` filter (`EXCLUDE_MM=true`)**: Tier-1 null passed + Tier-2
Δcorr positive + shadow arm forward-proven + Tue's explicit sign-off. This is a **separate, later**
decision — not part of this build.

## Cost Summary

| Item | Where | Added load | Delta vs current |
|------|-------|-----------|------------------|
| 1 | hourly refresh | +1 aggregation over `trader_fills` (BU+SELL, sub-sec) | +1 query/hr |
| 2 | hourly refresh | O(1)/wallet in memory; S3 reuses cached slice scores | +0 queries |
| 3 | offline manual | 2 Python scripts, ad-hoc reads | 0 live |
| 4 | live cycle | O(1) hashmap lookup/vote | 0 DB |
| 5 | live cycle | extra silent scoring pass (env-gated) | 0 when off |
| 6 | hourly refresh | +1 small upsert; 1 reconciliation query | negligible |

**Net: +1 hourly aggregation. Zero live-cycle (~2 min) delta. Zero change to
`ConsensusParams::default()` behavior. No paid API, no LLM — pure Rust + SQL.**

## Existing Infrastructure Leveraged
- `trader_fills` (BUY+SELL, `idx_tf_cond_outcome`/`idx_tf_wallet`) — the only data source; SELL leg
  already captured byte-identical (`trade_to_fill` keeps both sides), never featurized until now.
- `compute_trust_map` hourly refresh (`consensus_cycle.rs:131`) + `cached_slice_scores` 30s TTL
  (`trader_trust.rs:39`) — the exact cadence/caching pattern `compute_mm_map` clones; S3 rides its
  cached output for free.
- `earned_quality` per-vote seam (`consensus_cycle.rs:69,646`) + `.clamp(0.5,1.0)` Avoid idiom (`:76`)
  — the weight-cap host, untouched signature.
- `trusted_only`/`certified_only` drop-by-flag + `keep` closure (`consensus.rs:177,361`) — the exact
  `exclude_mm` precedent; `trust_arms`/`active_portfolio`/shadow-test ladder (`:750`, `cycle:977,1398`)
  — the shadow-first deployment shape.
- `TrustVerdict` three-way + day-deflation `eff_n` (`trader_trust.rs:66,244`) — the fail-safe verdict
  + one-weekend-can't-decide template.
- `selection_null.py` / `specialist_mining.py` (two-sided MECH_SQL, `two_sided_frac≥0.30`) /
  `persistence_tracker.py` — verified present; Item 3's calibration + Tier-2 clone them.

## Open Questions (resolved during implementation)
- **`τ_rt`, `τ_sb`, `V` (min_volume) operating point** — resolved by Item 3 Tier-1 on real data; do
  NOT hand-set. `τ_2s` frozen at 0.30 (precedent).
- **Does exclusion actually improve persistence (Δcorr sign)?** — resolved by Item 3 Tier-2; if ≤0,
  the whole live-wiring path (Item 5) is not pursued and the system stays an offline audit only.
- **How many of the 115 are FPs / how many of the 29–72 are FNs?** — resolved by Item 6
  reconciliation; human-reviewed before the persistence test consumes the pool.
- **Per-`(wallet×sport)` MM-ness** (crypto-MM who bets NBA) — deferred to v2; the CellMap seam exists.

## Rejected Approaches
- **Better single threshold on `fpd`** — rejected: `fpd` counts BUY+SELL so it tracks *round-trip
  style*, not *being an MM*; it inverts on the patient-MM (FN) and burst-human (FP) cases that matter
  most, and no single threshold has a measured FP at the 29-human stakes.
- **Summed calibrated scorecard (direct path's first form)** — rejected as the *decision* rule (kept
  as intuition): a weighted sum lets one loud, confounded feature (e.g. `two_sided`) cross the cutoff
  alone; the orthogonal-axis conjunction bounds FP better and is the literal "cross-reference." Direct
  path's own design already backstopped its sum with `AND two_sided≥hard AND !proven`, converging here.
- **Labeled-AUC calibration alone** — rejected as sufficient: the labeled set is drawn from the same
  two-sided heuristic under test → partly circular. Kept as Tier 1, but **Tier 2 (label-free
  downstream persistence effect) is the binding validation.**
- **Overwriting `trader_type` with the new verdict / auto-deleting flagged wallets** — rejected:
  destroys the 115-flag artifact and risks deleting 1 of ~29 humans automatically. Replaced by a new
  append-only table + human-reviewed reconciliation.
- **Raw K≥2-of-3 orthogonal signals (rethink path's first form)** — refined: S1(churn) and S2(both-
  sides) are correlated (both "how they trade"), so treating them as 2 independent votes overstates
  independence. Collapsed to `structural(S1∨S2) AND edge(S3) AND !proven` = 2 genuinely-orthogonal
  axes.
