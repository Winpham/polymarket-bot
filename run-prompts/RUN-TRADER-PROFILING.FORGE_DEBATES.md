# FORGE DEBATES — Per-Trader Strength-Profiling & Slice-Aware Tailing

Compressed record of the two designs, the reality-check findings, and the forced-choice synthesis
per gap. The governing frame is DECISIONS.md **D2 / charter §0.5**: the naive live specialist book
is **DEAD on current data** (0 capturable persistent specialists at every cut — sample floor + thin
capture margin + slate collapse). Every choice below is shaped by that: build measurement + an
inert, forward-gated mechanism; promote nothing until forward accrual clears.

## Reality-check findings (all symbols grep-verified against `~/polymarket-bot`)

Everything both designs cite EXISTS with the claimed shape:
- `earned_quality` @ `consensus_cycle.rs:69` — empty-map contract `(qw,true,false)` confirmed.
- `trust_verdict_with` @ `trader_trust.rs:123`; `n_comparisons = slices.filter(surplus.is_some())`
  @ `:129`; `eff_n = n_days.clamp(1, n_events)` @ `:179`; overall-only verdict @ `:148-193`.
- `surplus_bounds` @ `promotion.rs:281`: `alpha_corr = alpha/n_comparisons` → `z = probit(1−alpha_corr)`
  → `se = sd/√events`. **Direct's z-shift math verified:** n 6→8 ⇒ z probit(0.99167)→probit(0.99375)
  = 2.394→2.498 (+4.3 %). Sound and conservative (only → Indeterminate).
- `TraderVote` @ `consensus.rs:30` (dossier said :44 — struct opens :30, immaterial); adding two
  fail-closed fields is clean.
- `WindowVote` @ `common consensus.rs:85` — carries `title/slug/price/is_sports`, **NO `sport`, NO
  `bet_type`** (confirms Direct's "derive at call site" claim; field is `trader_wallet`).
- `NewTraderFill` @ `:108` already has `sport: Option<String>` — `bet_type` is a clean append.
- `trader_slice_scores` @ `:1459` / `_asof` @ `:1526`: `tagged` CTE hard-codes overall/sport/band/
  recency; `_asof` drops recency + adds `resolved_at IS NOT NULL AND resolved_at < $1`. UNION
  extension is exactly as both designs describe.
- `score_market` filter @ `:349-351`; `family()` EXPERIMENTAL const @ `enrich/mod.rs:339-352`
  (defaults unknown → `"core"`); `active_portfolio` `CONSENSUS_TRUST_ARMS` guard @ `:854-860`.
- Scripts all exist: `bh_fdr` @ `slice_study.py:197`; `selection_null.py` (`N_PERM=2000`,
  `null_pvalue`/`clustered_surplus`); `asof_slice_scores.sql` slug-date regexp @ `:21`;
  `asof_preflight.py`, `map_checkpoint.py`, `tail_records.py`.
- `format_trader_profile` @ `commands.rs:289` calls `trust_verdict` internally (:290) then renders
  `best/worst_slices` (:315-332); `slice_tag` @ `:411`; `render_trust` @ `board.rs:615/672`.

**Findings that shaped the synthesis:**
1. `promotion::probit` is **PRIVATE** (`fn probit`, `promotion.rs:33`). Rethink's shrinkage needs it
   `pub(crate)` — a NEW change. (Moot once shrinkage is rejected; noted.)
2. Rethink's `archetype` axis **cannot drive live per-vote selection** — `entry_pct` needs the
   event's full fleet-fill distribution (percent_rank over the event), unavailable at single-vote
   scoring. Rethink concedes "display/forward-shadow only." → archetype is inherently display/accrual.
3. Rethink's "τ̂²=0 ⇒ byte-identical to today" is a **self-disable property, not the non-regression
   mechanism.** strict safety in BOTH designs comes from the env gate + EXPERIMENTAL family +
   empty-map contract; the τ² collapse only makes the *trust_weighted arm* match today, and only
   when τ̂² is exactly 0. So Rethink's non-regression is structurally identical to Direct's — the τ²
   claim overstates its own novelty.
4. `family()` defaults unknown strategy names to `"core"`. Any NEW arm name (`slice_sport_tail`)
   **must** be added to EXPERIMENTAL or it silently tightens `strict`. Direct gets this right.
5. `percent_rank` for archetype is **leak-free in `_asof`**: the window ranks only over fills already
   inside the `resolved_at < cut` set; no future outcome weights any signal. (Minor caveat: a fill
   placed early but resolved after the cut is excluded from the as-of window — consistent with the
   surplus filter, belief-blind, not a leak.)

## Per-gap: both designs, verdict, synthesis

### GAP-4 — profiling display
- **Direct:** per-cell raw surplus + `surplus_bounds` lower bound + N/days + ✅/⏸/⛔ marker; reuses
  the gate verbatim, zero new stats, ships first standalone.
- **Rethink:** shrunk posterior mean + a credibility meter (B_c bar), `raw → shrunk` so `+40%@N6`
  reads as `+3% (cred 5 %)`; refuses to assert a certification.
- **Verdict — DIRECT (refined).** Rethink's meter is more elegant but the credibility % requires the
  DL/τ² estimator (a new statistic). N + event-days + bound width convey the same "how much to trust
  this" honestly with zero new stats. Steal Rethink's framing (soft markers, never "certified"; a
  big-N-thin number must read as noise; wallet-local footer). Highest value-per-risk; ships first.

### GAP-2 — the bet-TYPE axis
- **Direct:** frozen `bet_type` column + `bet_type_bucket` (moneyline/spread/totals/prop) — the axis
  the user literally named; per-vote derivable; costs a migration + capture + ≤4 comparisons/wallet.
- **Rethink:** reframe to a slate-independent **behavioral archetype** (entry-timing × conviction),
  SQL-only, no migration, attacks D2 reason 3 (slate collapse) + reason 1 (sample floor) — the only
  axis whose N accrues *across* disjoint tournaments.
- **Verdict — HYBRID / BOTH.** They solve different problems. Direct's `bettype` answers the user
  literally and can later drive live selection; keep it (counted conservatively in `n_comparisons`).
  Rethink's `archetype` is the single idea that attacks the actual D2 bottleneck (independent-N
  accrual across slates) and is statistically free at the display/accrual layer — but it is
  display/accrual ONLY (finding 2), so it is excluded from the live `n_comparisons` denominator and
  never drives the hot path. bettype = named display + live axis; archetype = the axis that makes the
  premise reachable over a disjoint calendar.

### GAP-1 — overall-vs-slice selection blindness
- **Direct:** wire a hard per-cell Trusted/Avoid flag into `earned_quality`; one pre-registered axis
  (sport), one cell per vote = one hypothesis; fail-closed to overall.
- **Rethink:** wire a continuous shrunk multiplier; no selection event, so GAP-3 never fires; thin
  cells pinned to overall by B_c→0.
- **Verdict — DIRECT.** Both self-disable on the dead archive and both stay silent/experimental. The
  decisive tie-breaker is the charter's hard line "reuse the gate's stats, add ZERO new statistics":
  Direct reuses `surplus_bounds` with zero new estimators; Rethink adds DL τ² + normal-normal EB to
  the generator and needs `probit` exposed. Direct reaches the same conservative outcome (a thin cell
  can't swing a vote) via fail-closed Indeterminate → overall. Rethink's continuity is a marginal win
  given everything is env-gated + forward-judged. The shrinkage idea survives only as display framing.

### GAP-3 — multiple-comparisons inflation (the #1 trap)
- **Direct:** three-layer separation — per-wallet Bonferroni at the vote (one cell = one hypothesis),
  `promotion_verdict` at the arm, fleet Bonferroni + BH-FDR + disjoint cuts at accrual.
- **Rethink:** dissolve it — remove selection (shrinkage) ⇒ no family to correct; the only hypothesis
  is GAP-5's single procedure test.
- **Verdict — HYBRID.** Adopt Direct's three-layer separation (it keeps the live arm to ONE
  experimental hypothesis without needing shrinkage), but adopt **Rethink's insight that in-sample
  BH-FDR over a frozen ~3000-cell family is NOT a sufficient binding control** — on a co-active 2-day
  slate FDR controls expected FDP but not within-slate correlation, so it still lights spurious
  co-active cells. So the fleet Bonferroni/BH-FDR becomes a **screen/watchlist**, and the **binding**
  control is Rethink's forward permutation test (GAP-5). This is the cleanest reading: no live family
  + in-sample screen + forward cross-window persistence as the gate.

### GAP-5 — accrual auto-trigger
- **Direct:** schedule `asof_preflight.py` per block on the slug-date axis (D1 workaround), enumerate
  the frozen family, Bonferroni + BH-FDR, per-cell certifications, ntfy on <2→≥2 transition.
- **Rethink:** ONE forward procedure-level permutation test — fit as-of cut C, score picks on the
  strictly-future window (C, now], permute wallet→cell labels; forward-only ⇒ D1-immune; family
  size 1; ntfy on the 2nd disjoint window with p≤0.01.
- **Verdict — RETHINK (wrapping Direct's selection procedure).** Rethink's trigger is strictly
  better: forward-only sidesteps the D1 bulk-stamp landmine (no slug-date harness), family size 1,
  and it tests the quantity that matters (does per-context tailing make money forward) instead of
  certifying ~3000 cells hoping ≥2 survive on 2 correlated days. We wrap Direct's per-cell as-of
  selection procedure (consistency with Item 4), keep both designs' shared append-only artifact +
  ntfy-on-transition. On today's backfill it correctly returns a waiting/null state — the honest D2
  reality, now automated.

## Key insights that emerged

- **The DEAD premise shaped every choice.** Because D2 forbids a live specialist book, the whole
  build splits into (a) measurement that promotes nothing (Items 1–3, buildable now) and (b) an
  inert, env-gated, forward-judged mechanism (Items 4–5) that flips only when a forward permutation
  test clears ≥2 disjoint windows AND Tue approves. Nothing in the plan can false-promote.
- **Shrinkage vs per-cell-gate — the central tension.** Rethink is right that "select best of ~3000
  cells" is a lethal 3000-way search on a 2-day slate, and that shrinkage dissolves it structurally.
  But Direct never opens that search at the *live* layer either (one pre-registered axis, one cell
  per vote, per-wallet correction, judged later by forward P&L). The 3000-way problem only appears at
  the *accrual* layer — and there the honest answer is neither Bonferroni nor BH-FDR (both fail on
  within-slate correlation) but Rethink's **forward** permutation test. So the resolution is a split:
  Direct's zero-new-stat wiring for the live mechanism, Rethink's forward test for the flip trigger.
  Shrinkage loses not because it is wrong but because it buys continuity at the price of a new
  generator estimator, when fail-closed Indeterminate already delivers the conservative behavior.
- **Different sources for different gaps.** GAP-4 display = Direct; GAP-1 wiring = Direct; GAP-2 =
  Direct's bettype + Rethink's archetype (BOTH, different roles); GAP-3 = Direct's layering +
  Rethink's "in-sample FDR is only a screen" insight; GAP-5 = Rethink's forward test. The best
  blueprint is not one design but the seam between them.
- **The binding budget is false-promotion risk, not dollars.** Every added slice is a comparison;
  the plan pays that cost consciously (bettype tightens overall conservatively; archetype is scoped
  out of the live denominator; the live arm is one experimental hypothesis; accrual is family size 1).
