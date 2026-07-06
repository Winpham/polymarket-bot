# FORGE PLAN — Per-Trader Strength-Profiling & Slice-Aware Tailing

**What changes for the user.** Today `/profile` shows a trader's best/worst slices as raw
surpluses — you cannot tell `+40% @ N=6` (noise) from `+12% @ N=34` (a real edge), and the live
tailing gate flags a wallet Trusted/Avoid from its **overall** verdict only, so a whale's edge
leaks into the one sport it's bad at and a single-sport specialist is dropped entirely. This plan
builds two things: (1) the **profiling instrument** — per-(sport × price-band × bet-type ×
behavioral-archetype) cells each carrying N, event-days, the gate's own corrected lower bound, and
a soft strength marker, so you understand a trader better than they understand themselves; and (2)
the **ready-to-flip selection mechanism** — a silent, env-gated, forward-tracked slice-aware trust
arm plus an automated accrual trigger that pings you the instant the data can actually support
going live.

**Honest framing (binding — DECISIONS.md D2, charter §0.5).** The naive version of this idea — a
live per-sport specialist book that overrides the overall trust gate — was already built and found
**DEAD on current data**: 0 capturable persistent specialists at every cut, because of the sample
floor, thin capture margin, and slate collapse (the archive is ~two co-active tournament days).
So this plan ships **measurement now** (promotes nothing) and the **mechanism wired but inert**,
gated behind an env flag, judged by the existing promotion machinery, promoting nothing until the
accrual trigger clears ≥2 disjoint forward windows AND Tue approves. We build the flip switch, not
the flip.

---

## Items

Dependency-ordered. GAP-3 (multiple-comparisons discipline) is **not a standalone item** — it is
the stats rule threaded through Items 4 and 5, and its resolution is recorded in each.

### Item 1 — Per-cell profiling display (GAP-4) — SHIP FIRST, zero stat cost, promotes nothing

**Before** (`format_trader_profile`, `commands.rs:289`):
```
👤 Trader 0xNBA…
✅ Trusted
📈 Surplus +3.1% (lower bound +0.4%) over 58 events
✅ Best: nba +12.1%, price b5 +7.0%
🔻 Worst: soccer −9.0%
```
Cannot distinguish `nba +12.1% @ N=34` (real) from `b5 +7.0% @ N=12` (thin).

**After:**
```
👤 Trader 0xNBA…
✅ Trusted · Surplus +3.1% (lower bound +0.4%) over 58 events
Per-cell strengths (wallet-local, NOT a fleet specialist verdict — promotes nothing):
  ✅ sport nba      +12.1%  [lo +4.2%]  N=34 / 14d   promising
  ⏸ band  b5       +7.0%   [—]         N=12 / 7d    thin (<30 events)
  ⛔ sport soccer   −9.0%   [hi −1.0%]  N=20 / 6d    avoid
  ⏸ bettype spread +3.0%   [—]         N=8  / 4d    thin (<30 events)
```

**Implementation.**
- New type in `trader_trust.rs` (next to `TraderTrust`):
```rust
pub struct SliceVerdict {
    pub slice_kind: String,   // "sport" | "band" | "bettype" | "archetype"
    pub slice_key:  String,   // "nba" | "b5" | "spread" | "late_small"
    pub n_events:   i64,
    pub n_days:     i64,
    pub surplus:    f64,      // raw event-clustered surplus (display context)
    pub lower_bound: f64,     // surplus_bounds lo, wallet-local n_comparisons
    pub upper_bound: f64,
    pub verdict:    TrustVerdict, // Trusted=promising / Avoid / Indeterminate(=thin or inconclusive)
}
```
- Extend `TraderTrust` with ONE field `pub slice_verdicts: Vec<SliceVerdict>`. **Keep**
  `best_slices`/`worst_slices` intact so the existing test `best_and_worst_slices_ranked` stays
  green (safe-swap, no behavior deleted).
- In `trust_verdict_with` (`trader_trust.rs:123`), after `n_comparisons` is computed (`:129`),
  loop every non-overall slice **that has surplus**:
  `eff_n = n_days.clamp(1, n_events.max(1))`;
  `(lo, hi) = surplus_bounds(eff_n, surplus, surplus_sd, n_comparisons, p)` — **verbatim reuse of
  the gate**, same `n_comparisons` the overall verdict already uses;
  `verdict = Indeterminate if n_events < p.min_events, else Trusted if lo > p.margin, else Avoid if
  hi < 0.0, else Indeterminate`. Push a `SliceVerdict`. Return the vec in BOTH early-return
  branches (`:148`, `:161`) and the final struct (`:195`). Sort
  Trusted → Indeterminate(surplus desc) → Avoid.
- Render: replace the `best`/`worst` block in `format_trader_profile` (`commands.rs:315-332`) with
  a loop over `t.slice_verdicts` using `slice_tag` (`:411`) + `verdict.marker()` (`:84`) + a
  `thin`/`promising`/`avoid` label. Add the wallet-local footer line. In `render_trust`
  (`board.rs:672`) switch the best column to `slice_verdicts.iter().filter(Trusted).take(2)`.
- The marker language is deliberately **soft** (`promising`/`thin`/`avoid`), never "certified" —
  a green cell must not read as tradeable while accrual is unmet.

**Integration points.** `trader_trust.rs:96` (TraderTrust +field) · `:123` trust_verdict_with
(compute per-cell bounds) · `commands.rs:289/315-332` format_trader_profile (render) ·
`board.rs:672` render_trust (best column).

**Cost.** Compute: one `surplus_bounds` call per non-overall slice per wallet, all under
`cached_slice_scores` 30 s TTL — negligible. **Statistical: ZERO.** Uses the wallet's EXISTING
`n_comparisons`; asserts no fleet verdict, gates nothing, promotes nothing, never touches `strict`.

**Source: DIRECT (refined).** Rethink's credibility-meter display is more elegant but requires the
DL/τ² empirical-Bayes estimator (a NEW statistic) to compute B_c. N + event-days + the corrected
bound width already convey "how much to trust this cell" honestly with **zero new statistics** —
the charter's hard constraint. We steal Rethink's framing insight: the marker must not read as a
certification, and the honesty signal is making a big number visibly thin (`+40% @ N=6 → ⏸ thin`).

---

### Item 2 — Bet-TYPE slice axis (GAP-2a) — the axis the user literally named

**Before.** A `+15%-moneyline / −10%-spread` wallet shows ONE blended `sport nba` cell. `tagged`
CTE has no bettype UNION; `trader_fills` has no `bet_type` column.

**After.** `slice_kind='bettype'` keys `moneyline | spread | totals | prop | other`, frozen at
capture like `sport`, surfaced as its own `SliceVerdict` in Item 1's display and available as a
future live-selection axis.

**Implementation.**
- New classifier `bet_type_bucket(title, slug) -> String` in `consensus_cycle.rs`, sibling to
  `sport_bucket` (`:133`). Substrate already exists in `sport_bucket`'s title patterns and
  `is_sports`. Match order (first hit wins), all lower-cased:
  `spread:` / `-spread` / ` +N` / ` -N` → `spread`;
  `o/u ` / `over/under` / `total` → `totals`;
  `to score` / `player` / `assists` / `rebounds` / `props` → `prop`;
  `vs.` / ` vs ` / `moneyline` / `ml` / `to win` → `moneyline` (kept LAST — broadest);
  else `other`. Add a unit test asserting the mappings (mirror `sport_bucket_classifies_known_domains`).
- **New migration `migrations/037_trader_fills_bettype.sql`** (latest is 036; NEVER edit an applied
  migration): `ALTER TABLE trader_fills ADD COLUMN IF NOT EXISTS bet_type TEXT;` No backfill →
  historical rows NULL → `COALESCE(bet_type,'other')` in the query.
- Capture: `trade_to_fill` (`consensus_cycle.rs:199`) computes
  `bet_type_bucket(&title, &tr.slug)` and sets it on `NewTraderFill`. Add
  `pub bet_type: Option<String>` to `NewTraderFill` (`common consensus.rs:108`, after `sport` —
  append, don't reorder). Add one column + one bind to the insert SQL.
- SQL: in BOTH `trader_slice_scores` (`consensus.rs:1461`) and `_asof` (`:1531`): add
  `COALESCE(bet_type,'other') AS bet_type` to the `adv` SELECT, thread it through `surp`, and add
  one UNION-ALL branch to `tagged`:
  `SELECT wallet,'bettype',bet_type,ev,a,s,won,ts FROM surp`.
  **`TraderSliceStat` needs NO field change** — new slice_kind/key VALUES only, preserving the
  sqlx `FromRow` column order.

**Integration points.** `consensus_cycle.rs:133` (new bucket) · `:199/:210` trade_to_fill (freeze)
· `common consensus.rs:108` NewTraderFill (+field) · `consensus.rs:1461` and `:1531` slice SQL
(UNION branch, both live and as-of) · `migrations/037_*` (new).

**Cost.** SQL: +1 UNION branch → slice vector +~20 % rows (cached, TTL unchanged). **Statistical
(binding): bettype adds up to +4 comparisons to each wallet's `n_comparisons`** (`trader_trust.rs:129`),
tightening every wallet's one-sided overall bound. Worked example (verified against `surplus_bounds`,
`promotion.rs:281-291`): 6→8 comparisons ⇒ `alpha_corr` 0.05/6→0.05/8 ⇒ `z` = probit(0.99167)→
probit(0.99375) = **2.394 → 2.498 (+4.3 %)** ⇒ overall LB drops ~0.19 pp — can flip a hairline
Trusted→Indeterminate. This is **conservative** (only ever toward Indeterminate, never a false
Trusted) and moves only the trust map + experimental arms, **never `strict`**. Decision: INCLUDE
bettype in `n_comparisons` — it is a real comparison; excluding it would understate the family.

**Source: HYBRID (Direct half).** This is the axis the user explicitly named ("what TYPE of
bets"), it is per-vote derivable from `title`/`slug` (so it can later drive live selection), and
every pattern it needs (bucket, freeze-at-capture, add-column migration, UNION) already exists.

---

### Item 3 — Behavioral-ARCHETYPE slice axis (GAP-2b) — the only axis that beats slate collapse

**Before.** A wallet "good at fading late longshots" is smeared across `sport/soccer` + `band/b1`,
invisible as a unit; soccer alone has only ~21 fleet event-days (D4) so it never reaches the floor.
Every existing axis (sport, bettype) is **calendar-bound** — a spread specialist only accrues N
while spread markets are live (the same WC weekend), which is exactly D2 reason 3 (slate collapse).

**After.** `slice_kind='archetype'` keys `{early,mid,late}_{big,small}` from **entry-timing ×
conviction**, both slate-independent behaviors that RECUR on every tournament and sport ⇒ events
decorrelate across slates ⇒ independent-N accrues on the whole fill stream. A "fade-late" edge
expresses on WC soccer, the next Grand Slam, and NBA alike, so `late_small` aggregates across
every slate.

**Implementation (SQL-only — no migration, no capture, no hot-path change).** In BOTH
`trader_slice_scores` (`:1461`) and `_asof` (`:1531`):
- `adv` gains `size_usd`, `percent_rank() OVER (PARTITION BY ev ORDER BY ts) AS entry_pct`
  (fleet-relative earliness within the event — needs no new column; leak-free for `_asof` because
  the window ranks only over fills already inside the `resolved_at < cut` set).
- New CTE `wmed`: `percentile_cont(0.5) WITHIN GROUP (ORDER BY size_usd)` per wallet (conviction
  anchor = wallet's own median stake).
- `surp` carries `size_usd`, `entry_pct`, `med`; one UNION branch to `tagged`:
```sql
SELECT wallet,'archetype',
  (CASE WHEN entry_pct <= 0.33 THEN 'early' WHEN entry_pct >= 0.67 THEN 'late' ELSE 'mid' END)
  ||'_'||(CASE WHEN size_usd >= med THEN 'big' ELSE 'small' END),
  ev, a, s, won, ts FROM surp
```
- `TraderSliceStat` unchanged (VALUES-only; FromRow order immutable).
- Archetype cells flow through the SAME `Vec<TraderSliceStat>` into Item 1's display and Item 5's
  accrual — **no hot-path integration.**

**Statistical scoping decision (important).** Archetype cells are **display + accrual ONLY**; they
are **excluded from the live `n_comparisons` denominator** in `trust_verdict_with`. Reason:
archetype is not live-selectable (see trade-off) so it never drives a live vote, and its multiple-
comparisons cost is borne at the accrual layer (Item 5's fleet-wide forward test), not the
per-wallet overall verdict. Implementation: `n_comparisons` counts only live-eligible slices
(`overall`/`sport`/`band`/`bettype`); archetype rows are skipped in that filter but still rendered
and still fed to the accrual harness. This keeps the live family tight and archetype statistically
free where it belongs.

**Integration points.** `consensus.rs:1461` and `:1531` (UNION + window + wmed CTE, both queries)
· `trader_trust.rs:129` (scope `n_comparisons` to live-eligible kinds) · flows into Item 1 display
and Item 5 accrual with no further wiring.

**Cost.** SQL: one `percent_rank` window (O(N log N) inside the existing sort) + one
`percentile_cont` CTE over the same single scan; rows +~20 %; cached. Sub-second. **Statistical: at
the display/accrual layer, ZERO added live comparisons** (excluded from live `n_comparisons`; the
accrual layer has its own family-size-1 forward test).

**Source: RETHINK (Design B's reframe).** This is the single idea in either design that directly
attacks the D2 slate-collapse wall: an axis whose N accrues *across* slates is the only way the
premise can ever come alive on a calendar of disjoint tournaments. It is statistically free here
and needs no schema change. **Trade-off / why it is not a live-selection axis:** `entry_pct` needs
the event's full fill distribution (percent_rank over all fleet fills on that event), which is not
available at single-vote scoring time — so archetype informs display and the accrual watch, and
could only ever drive live selection via a forward-shadow replay, not the hot path. This is why
Item 4's live arm keys `sport`, not archetype.

---

### Item 4 — Slice-aware selection wiring (GAP-1 + GAP-3 live discipline) — SILENT, env-gated, inert

**Before** (`earned_quality`, `consensus_cycle.rs:69` — branches on the **overall** verdict only):
- **A · leak into a weak cell:** `0xWHALE` overall Trusted (lo ≈ +5 %); its `sport/nba = −0.14`.
  An NBA BUY → `earned_quality` sees overall Trusted → `(1.05, true, true)`: the bad-cell vote is
  flagged trusted+certified and up-weighted. `worst_slices` caught it but selection never consulted it.
- **B · specialist dropped:** `0xNBASPEC` `sport/nba +12.1% @ N=34` but overall `+3.1%` (dragged by
  −9 % soccer) → Indeterminate → `(qw,false,false)`. `trusted_only` DROPS its NBA votes.

**After** (env `SLICE_TRUST` ON, pre-registered axis = `sport`):
- **A:** NBA cell verdict = Avoid → `slice_certified=false` → down-weighted / dropped by the arm.
- **B:** NBA cell verdict = Trusted → `slice_certified=true`, counted/up-weighted **only for NBA
  votes** (soccer votes stay uncertified). The specialist's edge becomes reachable.
- `SLICE_TRUST` OFF (default) ⇒ **byte-identical to today.**

**Implementation.**
- `struct SliceCtx { sport: String }` derived at book assembly (extendable to band/bettype later;
  ONE axis per arm on purpose — see GAP-3).
- Extend `TraderVote` (`consensus.rs:30`) with TWO fail-closed fields, appended after `certified`:
  `pub slice_certified: bool` (default **false**), `pub slice_earned: f64` (default = overall
  `earned_quality`). Extend `ConsensusParams` (`:137`) with
  `pub slice_certified_only: bool` (default **false**, mirrors `certified_only`).
- New `slice_earned_quality(trust, wallet, ctx: &SliceCtx, overall_earned) -> (f64, bool)`: find
  the `SliceVerdict` where `slice_kind=="sport" && slice_key==ctx.sport`; if none →
  `(overall_earned, false)` (fail-closed). Else earn from `sv.verdict` exactly as `earned_quality`
  does today (Trusted → `(1+lo*damp).clamp(0.5,2.0)`; Avoid → `(1+hi*damp).clamp(0.5,1.0)`;
  Indeterminate → `overall_earned`); `certified = matches!(sv.verdict, Trusted)`. **ONE cell per
  vote ⇒ ONE hypothesis** — no cross-cell max/min, so no GAP-3 fleet inflation at the live layer.
- Call site `books_from_window_votes` (`:522/:537`): `v.title`/`v.slug` in scope → build
  `SliceCtx { sport: sport_bucket(&v.title, &v.slug) }` **only when `slice_trust` is on**, set
  `slice_certified`/`slice_earned` on the `TraderVote`; else `(default false, overall_earned)`.
- `score_market` filter (`:349-351`): add the conjunct
  `&& (!params.slice_certified_only || v.slice_certified)`.
- New `slice_arms(base, cutoff)` sibling to `trust_arms` (`:735`), one StrategyDef
  `"slice_sport_tail" { min_backers:1, max_opposers:MAX, max_price_std:1.0, max_age_mins:180,
  slice_certified_only:true }`, `alerting:false`. Register in `active_portfolio` (`:854`) behind a
  new `SLICE_TRUST`/`cfg.slice_trust` guard, exactly like the `CONSENSUS_TRUST_ARMS` block (`:857-860`).
- **CRITICAL:** add `"slice_sport_tail"` to the `EXPERIMENTAL` const in `family()`
  (`enrich/mod.rs:339-352`). `family()` defaults unknown strategies to `"core"` — omitting this
  would silently put the arm in the core Bonferroni family and tighten `strict`.

**GAP-3 resolution (three-layer separation — the multiple-comparisons discipline).**
- **Layer 1 (live vote selection):** per-wallet Bonferroni — correct for "does *this wallet's own*
  nba cell clear *its own* bar." One pre-registered axis, one cell per vote ⇒ this is a selection
  SIGNAL, not a promotion, and never opens the ~3000-way (200 wallets × ~15 cells) search that D2
  proved lethal.
- **Layer 2 (promotion to alerting):** the arm's forward P&L judged by `promotion_verdict`
  (`promotion.rs:168`) with the EXPERIMENTAL `n_strategies` + selection-null — already correct,
  untouched.
- **Layer 3 (accrual / flip-live):** the fleet-wide "≥2 persistent specialists" question lives in
  Item 5, where the family denominator and the binding forward control live.

**Non-regression proof.** `strict` = `Quality` weight mode with all `*_only=false`, so
`slice_certified` is read only under `slice_certified_only` (false for strict) and `slice_earned`
only under a future `SliceWeighted` mode (strict is `Quality`). Empty map ⇒ `slice_ctx` never
built (guard off) ⇒ `earned_quality` returns `(qw,true,false)` unchanged. Add sibling test
`slice_arms_registered_separately_and_silent` (mirror `trust_arms_registered_separately_and_silent`,
`consensus.rs:1200`).

**Cost.** Compute: per vote, one `sport_bucket` + one linear find over `slice_verdicts`, ONLY when
`SLICE_TRUST` on. **Statistical:** `slice_sport_tail` = ONE new experimental-family hypothesis;
consults only the pre-registered `sport` cell (one cell/vote → no inflation). `strict` core gains ZERO.

**Source: DIRECT.** Reuses the trust gate verbatim (per-cell `surplus_bounds` from Item 1) with
**zero new estimators** — the best honoring of "reuse the gate's stats, add ZERO new." It fails
CLOSED on thin cells (Indeterminate → overall path), self-disables on the dead archive (nearly all
cells Indeterminate → today's behavior), and confines the whole mechanism to ONE experimental
hypothesis. Rethink's continuous shrinkage is elegant but adds a DerSimonian-Laird τ² + normal-normal
EB estimator to the generator for a marginal continuity benefit that Direct achieves via fail-closed
Indeterminate — see Rejected Approaches.

---

### Item 5 — Accrual auto-trigger (GAP-5 + GAP-3 binding control) — forward permutation, D1-immune

**Before.** `asof_preflight.py` runs only on a human invoke; the D4 "≥2 persistent specialists"
condition is eyeballed; no schedule, no persistence, no alert. Worse, on the backfilled archive
`resolved_at` is a bulk stamp, so any retrospective per-cell certification degenerates (D1) and
needs the slug-date harness as a workaround.

**After.** A nightly checkpoint asks ONE forward question — "does the as-of slice-selection
procedure predict positive surplus on the picks it makes in the future window?" — with a single
permutation p-value, forward-only (so **immune to the D1 bulk-stamp trap**), family size 1. It
persists an append-only artifact and pushes ntfy ONLY on the **2nd disjoint window** clearing
`p ≤ 0.01` (D4's ≥2 disjoint cuts, now a procedure test), with copy: "📈 ACCRUAL FLIP — slice-tail
predicts forward surplus on 2 disjoint windows → SliceTrustMap Arm A/D is next (D3). Awaiting Tue."

**Implementation (NEW `scripts/procedure_forward_null.py` + a checkpoint task).**
1. Pick cut `C = now − Δ`. Fit the Item-4 selection procedure on fills with **real forward**
   `resolved_at < C` via `trader_slice_scores_asof(C)` (`consensus.rs:1526`).
2. Form the "would-tail" pick set: each wallet's cells whose as-of verdict = Trusted (the same
   per-cell `surplus_bounds` rule Item 1/4 use).
3. Score the realized event-clustered surplus of those picks on fills with
   `resolved_at ∈ (C, now]` — strictly future, real stamps.
4. Permutation p: shuffle the wallet→cell label assignment `N_PERM≥1000` times (reuse
   `selection_null.py`'s engine — `null_pvalue`/`clustered_surplus`, `scripts/selection_null.py`,
   `N_PERM=2000`; the (band × UTC-day) null generalizes to (kind × key)); recompute forward
   surplus each draw; `p_emp = (#{null ≥ observed} + 1)/(N_PERM + 1)`.
5. Append a versioned artifact `reports/accrual/vNNN.json` + `manifest.json`
   (version, effective_from, sha256, observed, p_emp, window) — D14 `map_checkpoint.py` append-only
   pattern.
6. Fire ntfy (`consensus_cycle.rs:417-430` topic/env) ONLY on the 2nd disjoint window with
   `p ≤ 0.01` (`SELECTION_NULL_P_BAR`, no new threshold); idempotent via the prior manifest.

**Schedule.** A cron line beside `consensus-backup.sh` (preferred, matches the offline-harness
convention) OR a Rust housekeeping `accrual_tick` shelling out daily. Resolve during
implementation (Open Questions).

**GAP-3 resolution (binding control).** The in-sample fleet Bonferroni (`α/n_testable`) and BH-FDR
(`bh_fdr`, `slice_study.py:197`) over the frozen `{n_events≥30 & surplus non-null}` family are
computed and reported as a **SCREEN / watchlist** only. The **binding** control is this forward
permutation test, because on a co-active 2-day slate in-sample FDR controls expected FDP but **not**
within-slate correlation (two "specialists" co-active on the same weekend both light up). Only
forward, cross-window persistence rules that out — which is exactly why nothing promotes until this
fires on ≥2 disjoint windows.

**On today's data.** The backfill has no genuine forward window, so this returns a **waiting/null
state** — the honest D2 reality. The trigger automates the watch so the flip signal arrives the
moment real forward data accrues.

**Integration points.** `scripts/procedure_forward_null.py` (new, wraps `selection_null.py`) ·
`trader_slice_scores_asof` (`consensus.rs:1526`, the fit) · `reports/accrual/` (new, append-only)
· ntfy (`consensus_cycle.rs:417-430`) · cron beside `consensus-backup.sh` or a Rust `accrual_tick`.

**Cost.** 2 slice queries + ~2000 reshuffles nightly — seconds, off the hot path. **Statistical: 1
hypothesis per window** (vs ~3000 × cuts for the naive per-cell approach). Adds no comparisons to
any live family. Frozen thresholds (`p≤0.01`, ≥2 disjoint windows) = re-reading, not re-tuning.

**Source: RETHINK (wrapping Direct's selection procedure).** Rethink's forward-permutation framing
is the better trigger: forward-only ⇒ D1-immune (no slug-date harness), family size 1 (reuses
`selection_null.py` verbatim), and it tests the thing you actually care about (does per-context
tailing make money forward) instead of certifying ~3000 cells hoping ≥2 survive on 2 correlated
days. We wrap **Direct's** as-of selection procedure (per-cell verdict), not Rethink's shrink
procedure, for consistency with Item 4. We keep the append-only artifact + ntfy-on-transition
plumbing both designs share.

---

## Execution Order

1. **Item 1 — display (GAP-4).** Verify: `bun run verify` (or `cargo test -p copy-trading-bot`);
   `/profile` on a seeded wallet shows per-cell N/days/[lo]/marker; existing
   `best_and_worst_slices_ranked` still green.
2. **Item 2 — bettype axis (GAP-2a).** Depends on Item 1's `SliceVerdict` (bettype renders as a
   cell). Verify: migration 037 applies; `bet_type_bucket` unit test passes; a bettype cell appears
   in `/profile`; slice-vector row count up ~20 %.
3. **Item 3 — archetype axis (GAP-2b).** Depends on Item 1. Verify: `_asof` and live queries both
   emit `archetype` cells; `entry_pct` leak-free check (as-of window ranks only within-cut fills);
   `n_comparisons` unchanged by archetype (scoped to live-eligible kinds).
4. **Item 4 — selection wiring (GAP-1/GAP-3 live).** Depends on Items 1–2. Verify:
   `SLICE_TRUST` OFF ⇒ `default_strict_is_non_regressive` byte-identical; new
   `slice_arms_registered_separately_and_silent` green; `family("slice_sport_tail")=="experimental"`;
   worked examples A/B produce the After outcomes with the flag on.
5. **Item 5 — accrual trigger (GAP-5/GAP-3 binding).** Depends on Item 4's selection procedure.
   Verify: `procedure_forward_null.py` runs, produces a p-value + append-only artifact on synthetic
   forward data; returns waiting-state on the current backfill; ntfy fires only on 2nd disjoint
   window (idempotent via manifest).

---

## Cost Summary

| Item | Compute delta | Statistical / family-comparisons delta | Touches `strict`? |
|------|---------------|------------------------------------------|-------------------|
| 1 — display | +1 `surplus_bounds`/cell/wallet, cached | **ZERO** (wallet-local `n_comparisons`, asserts no verdict) | No |
| 2 — bettype | +1 UNION, rows +~20 %, +1 migration/capture | +≤4 to each wallet's `n_comparisons`; conservative (only → Indeterminate); worked z 2.394→2.498 | No (trust map + experimental only) |
| 3 — archetype | +1 window +1 CTE, same scan, rows +~20 % | **ZERO live** (excluded from live `n_comparisons`; accrual family = 1) | No |
| 4 — selection | per-vote 1 bucket + 1 find, only if `SLICE_TRUST` | +1 experimental hypothesis (`slice_sport_tail`); one cell/vote → no inflation | **No** (env-gated, EXPERIMENTAL family) |
| 5 — accrual | 2 queries + ~2000 perms nightly, offline | **1 hypothesis/window** (vs ~3000×cuts naive); no live-family adds | No |

---

## Existing Infrastructure Leveraged

- `surplus_bounds` (`promotion.rs:281`), `promotion_verdict` (`:168`), `SELECTION_NULL_P_BAR`
  (`:97`) — reused verbatim, zero new gate stats.
- `bh_fdr` (`slice_study.py:197`) + `selection_null.py` permutation engine (`N_PERM=2000`) — the
  fleet screen and the forward binding test.
- `trust_verdict_with` / `n_comparisons` / `eff_n` (`trader_trust.rs:123/129/179`) — the per-cell
  bound loop drops straight in.
- `sport_bucket` (`consensus_cycle.rs:133`) — exact template for `bet_type_bucket`.
- `trader_slice_scores` / `_asof` (`consensus.rs:1459/1526`) — UNION-branch extension points;
  `_asof` is the leak-free fit for Item 5.
- `family()` EXPERIMENTAL const (`enrich/mod.rs:339`) — keeps the new arm out of the core bar.
- `trust_arms` + `certified_only` + `active_portfolio` `CONSENSUS_TRUST_ARMS` guard
  (`consensus.rs:735`, `consensus_cycle.rs:854-860`) — template for `slice_arms`/`SLICE_TRUST`.
- `cached_slice_scores` 30 s TTL (`trader_trust.rs:37`) — amortizes the extra UNIONs.
- `map_checkpoint.py` append-only + ntfy (`consensus_cycle.rs:417-430`) — Item 5 persistence + push.
- `asof_slice_scores.sql` slug-date axis (`:21`) — available for retrospective screening if wanted
  (not on the forward critical path).

## Open Questions (resolve during implementation)

- **Bettype keyword tuning** — the pattern list will mis-bucket exotic markets to `other`;
  resolve by running `bet_type_bucket` over a sample of live `trader_fills.title/slug` and checking
  the `other` rate before merge (aim <15 %).
- **Archetype `entry_pct` thresholds (0.33/0.67)** — the early/mid/late cut points are a guess;
  resolve by inspecting the per-event fill-time distribution once archetype cells populate (keep
  frozen thereafter — re-reading not re-tuning).
- **Scheduler: cron vs Rust housekeeping tick** — resolve by which fits the existing deploy
  container (cron beside `consensus-backup.sh` is preferred; a Rust `accrual_tick` avoids a second
  scheduling surface). Decide when wiring Item 5.
- **`Δ` (as-of window width) and disjoint-window definition for Item 5** — resolve against how fast
  real forward `resolved_at` accrues once live (start with per-tournament-block windows).

## Rejected Approaches

- **Live per-slice tailing book that overrides the overall gate (the naive user vision).** REJECTED
  by DECISIONS.md D2 / charter §0.5: already built, found DEAD (0 capturable persistent specialists
  at every cut) because of sample floor + thin capture margin + slate collapse. Shipping it live
  manufactures the false specialists the charter forbids. This plan builds the measurement + the
  inert, forward-gated mechanism instead.
- **Rethink's continuous EB shrinkage for GAP-1/GAP-3 (DerSimonian-Laird τ² + normal-normal).**
  REJECTED for the live wiring. It is genuinely elegant (dissolves the multiple-comparisons family
  structurally: correlated-noise → high sampling variance → credibility→0 → collapse to overall)
  and self-disables on the dead archive (τ̂²=0 ⇒ every cell = overall). But it **adds a new
  estimator to the generator**, violating "reuse the gate's stats, add ZERO new statistics" more
  than Direct does; it requires exposing `promotion::probit` (currently private, `promotion.rs:33`);
  and its "τ̂²=0 ⇒ byte-identical" is a *self-disable* property, not the non-regression *mechanism*
  (strict safety in BOTH designs comes from the env gate + EXPERIMENTAL family, which Direct also
  has). Direct reaches the same conservative behavior — thin cells can't swing a vote — via
  fail-closed Indeterminate → overall, with zero new statistics. The shrinkage credibility meter
  survives as an *inspiration* for Item 1's honesty framing, not as code.
- **Direct's per-cell slug-date accrual (GAP-5).** REJECTED in favor of Rethink's forward
  permutation test: the per-cell/slug-date approach re-enters the D1 `resolved_at` bulk-stamp
  landmine, certifies ~3000 cells hoping ≥2 survive on 2 correlated days, and needs the slug-date
  harness as scaffolding. The forward permutation test is D1-immune, family size 1, and tests the
  quantity that actually matters.
- **BH-FDR over the frozen ~3000-cell family as the BINDING accrual control.** REJECTED as binding
  (kept only as a screen): on a co-active 2-day slate, FDR controls expected FDP but not
  within-slate correlation, so it still lights spurious co-active cells. Forward cross-window
  persistence is the real control (Item 5).
- **Archetype as a live per-vote selection axis.** REJECTED: `entry_pct` needs the event's full
  fleet-fill distribution, unavailable at single-vote scoring time. Archetype is display + accrual
  only; the live arm (Item 4) keys `sport`.
