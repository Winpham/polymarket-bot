# Autonomous program — "Specialist Selection": tail the right sharp in the right market

> **How to run.** This is a **multi-workstream, long-horizon program**, not a single task.
> Two ways to run it:
> - **One long self-directed session** — paste this whole file as the task for a fresh Claude
>   Code session opened in `~/polymarket-bot`, or dispatch it:
>   `claude -p "$(cat ~/polymarket-bot/run-prompts/RUN-SPECIALIST-SELECTION.AUTONOMOUS.md)"`.
>   Work WS-0 → WS-6 in order, compounding as you go.
> - **Fanned out** — dispatch WS-0 first (everything depends on it), then run WS-1…WS-4 as
>   their own long sessions in separate worktrees, then WS-5/WS-6 to integrate. §6 says what
>   is safe to parallelize.
>
> It is self-directed. Work autonomously to finished, gate-green, forward-accruing artifacts.
> Only stop for a decision that is genuinely Tue's (e.g. "flip an arm to live alerting — yes/no").

---

## 0. Mission (read this twice)

Today the engine tails leaderboard traders with a **single wallet-level weight**. A wallet that
is genuinely sharp at NBA and genuinely bad at soccer votes with the **same weight on a soccer
market**. We already *compute* each trader's per-category edge (`trader_slice_scores()` produces
per-`sport` and per-price-`band` surplus, band-blind and event-clustered) — and then we **throw
it away at the moment of selection**. `best_slices`/`worst_slices` are shown to humans and never
weight a live vote.

Your mission is to close that gap and everything it opens onto:

1. **Tail the most profitable bettors — in the markets they are actually profitable in.** Build
   a per-(trader × market-category) "specialist map," and make the consensus scorer weight (or
   gate) each trader's vote by their **earned edge in *this* market's category**, not their
   global standing.
2. **Rank by earned per-cell surplus, not leaderboard PnL.** The leaderboard ranks by raw
   dollars (whales, lucky runs, favorite-loading). Replace/augment that with who is *certified*
   in the cell the current market lives in.
3. **Innovate broadly** — pursue the many other selection levers this data unlocks (§4, WS-4):
   conviction sizing, herding/fade, edge-momentum, dispersion, cohort regression, round-trip
   PnL, microstructure conditioning. Each is a hypothesis, not a promise.
4. **Compound and integrate, honestly.** Every lever is judged by the existing **belief-blind
   gate**. Survivors are combined into **one book** only if each **adds independent edge** over
   the union of the others (no double-counting favorite). You are **expected** to conclude that
   several levers are REFUTED or INDETERMINATE-BY-POWER. A sycophantic "it all works" is a
   failure of this run.

### The generator / gate contract (the whole method)
Be a **wild generator** and a **ruthless gate**. Believe an exploitable per-specialist edge
*exists* and chase it hard when proposing levers — do not pre-censor ideas for looking naive.
Then put **all** the rigor at the **belief-blind gate**: the gate does not know what you hoped,
it only sees surplus-over-blind, event-clustered, Bonferroni-corrected, selection-null-tested,
and forward-only. Belief in the generator; rigor at the gate. Never soften the gate to let a
favorite child through.

### Why this isn't "congregation-2" (the gate you must pass before you build)
This thesis has a **dead sibling**: the **congregation engine** (2026-06-30, `DECISIONS.md` D2 /
charter §0.5) built a per-**sport** specialist *book* and found it **DEAD on current data — 0
wallets cleared `lo>3%` at N≥30 on any per-sport slice, at every cut** — killed by the sample
floor, thin capture margin, and slate collapse (~2 co-active tournament days). Its slice-aware
mechanism was even designed in `RUN-TRADER-PROFILING.FORGE_PLAN.md` and shipped **inert** for this
reason. And the reliability program separately proved **`elite_fresh_fav ⊂ favorite` — 0/12
strategies diversify favorite** (no free orthogonal edge). **You are reviving a falsified premise.
Before writing code, you must state — in `00-baseline.md` — why *this* attempt is not congregation
redux, and you must be willing to conclude it still is.** The three things that changed, and the
one thing that didn't:
- **Unit** — congregation built a standalone per-*sport* book; this **re-weights individual
  traders' votes inside an already-+EV consensus signal**. Different object, different failure
  surface.
- **Power** — congregation had ~one tournament weekend; the archive is now **deep (2022→2026,
  ~5,900 resolved events)** and **78 wallets clear ≥30 events** (72+ at the new 25 floor). The
  sample floor that forced "inert" has materially lifted **for profiling**.
- **Baseline** — the **cell-blind** baseline (blind play in the *same* sport×subtype×band cell) is
  designed to strip out the favorite-loading that usually explains away "specialist" edge.
- **Unchanged: the death mode.** Multiplicity (78 wallets × cells × levers → best-cell-is-max-of-
  noise) and favorite-in-disguise are the *identical* risks that killed congregation and refuted
  `market_resid`. If the in/out temporal split, the family-wise-error control, and the
  orthogonality-vs-favorite test don't hold, **this is congregation-2 and you say so.**

### The one distinction that governs honesty here
`trader_fills` holds **deep history (back to 2022, ~1.04M fills, ~5,900 distinct resolved
events)** — so you can **mine and profile** per-specialist edge on real history using the
**leak-free as-of** query (`trader_slice_scores_asof(cut)`). **But** the forward-tracked
**consensus-signal** record is still **thin (~days)**. Therefore: *specialist profiling* may use
the deep archive (with a strict in/out temporal split); any *consensus arm* you build on it is
**silent and forward-accruing** and is **not certified** until it clears the pilot gate on
**forward** data. Do not confuse "the specialist map fits history" with "the arm is live-ready."

---

## 1. Hard ground rules (do not violate)

- **Cost-zero.** Max subscription only. Never set or use `ANTHROPIC_API_KEY`; never spawn child
  `claude` processes. Use your own Opus-level reasoning.
- **Paper-only, read-only against reality.** Read the live Postgres
  (`docker exec polymarket-bot-postgres-1 psql -U bot -d polymarket --csv -c "…"`) and frozen
  `reports/*.json`. **Never** write to the live DB, **never** mutate `honest_paper_ledger`,
  **never** place a real order. All new code is offline analysis or **silent, default-OFF** arms.
- **Isolate — the live bot auto-deploys from `feat/consensus-engine` HEAD on commit.** Do every
  edit in a dedicated worktree: `git worktree add ../pmkt-<ws> -b lever/<ws> feat/consensus-engine`
  and work in `../pmkt-<ws>/`. Do not commit half-work to `feat/consensus-engine`.
- **Never edit an applied migration** (even a comment) — it re-checksums and crash-loops the app.
  New schema = a **new** migration file with the next number (watch for number collisions if
  running WS in parallel — coordinate the number).
- **Default OFF, strict byte-identical.** Every new arm is a silent `StrategyDef { alerting:false }`
  appended to `default_portfolio()`/`trust_arms()`; every new `ConsensusParams` knob defaults to a
  no-op. Prove the live `strict` alert path is byte-identical (there are existing non-regression
  tests to mirror — `trust_arms_registered_separately_and_silent`). **Promotion to live alerting
  is a deliberate human call — never automatic.**
- **Reuse, don't rebuild.** The gate, the stats, and most of the profiling already exist — extend
  them (§ inventory below). Every new Python script gets a `--selftest` that exits non-zero on
  failure (house style). Every new Rust arm gets `#[test]`s proving silence + non-regression.
- **Forward-only.** Skip any signal whose `first_detected_at` precedes a model's `trained_through`.
  Judge arms on **surplus-over-`_blind`** at the **distinct-EVENT** level, event-clustered on
  `COALESCE(event_slug, condition_id)` — never raw edge, never raw N.
- **Honesty over completeness.** Untestable on current data ⇒ mark **INDETERMINATE-BY-POWER**; do
  not manufacture a number. Distinguish "refuted," "survived," "unknown." Wide CIs are a finding.
- **Coordinate.** If another session is live on `consensus.rs`/`consensus_cycle.rs`, serialize the
  scorer edits (§6). Don't disturb the running daemon.

---

## 2. Ground truth you're standing on (Phase 0 — refresh it first)

A snapshot measured at authoring time (**verify and refresh these numbers before trusting them**):

- `trader_fills`: **~1,036,974 fills · 397 wallets · 766,444 resolved · 5,922 distinct resolved
  events**, spanning **2022-12-15 → 2026-07-03**.
- **78 wallets** clear a **≥30** distinct-resolved-event floor (will be more at the new **25** floor,
  §3). Per-sport volume: soccer ≫ crypto > tennis > other > mlb > cs2 > politics/nba/lol/dota/ufc/nfl.
- `followed_traders`: **457 tracked · 309 active · 167 `consensus_eligible` · 0 `earned_eligible`**
  (no wallet has earned into consensus yet — a live gap to explain, not to route around).
- **Heterogeneity is real** (the thesis, on live data): e.g. `0x032eb…` = **+0.156 soccer (276 ev)
  / −0.083 MLB (89)**; `0x84cff…` = **+0.141 soccer / −0.071 MLB**; `0x204f72…` = **+0.017 tennis /
  +0.001 MLB / −0.077 soccer (476)**. Global-tailing these wallets mixes a winning specialty with a
  losing one. That spread is the edge — *if* it survives the gate and a forward split.

**WS-0's first job is to make this current**, per Tue's two asks:
1. **Up to date on all tracked events.** Recount `trader_fills` (rows/wallets/resolved/distinct
   events), the calendar span, and per-sport resolved-event counts. Quantify **capture
   completeness** per wallet (`capture_gap_count`, `scripts/capture_completeness.py`) — remember
   the `/activity` API returns a hard **100-row newest page and ignores `startTs`**, so deep
   history exists only where polling caught it. Flag low-completeness wallets; they cannot be
   trusted as specialists no matter how good the surplus looks.
2. **The new top-250 cohort.** Confirm capture reaches the deep pool: `track_cohort_bands`
   ("40,100,250,500") and paginated `fetch_leaderboard_paged` (offset paging past the 50-row
   server cap). Ensure the **top-250** are tracked/captured (voting stays rank-cutoff-gated;
   capture is wider than voting by design). Report how many of the top-250 have a profileable
   fill history and how many clear the floor. Watch the data-api **429 count** — only widen
   `TRACK_PERIODS` (never `TRACK_TOP_N` > 50) if it stays ≈ 0.

Deliverable: `reports/selection/00-baseline.md` — the exact archive state, cohort coverage,
completeness caveats, and the honest thin-vs-deep distinction (§0).

---

## 3. Lower the trust floor to 25 (deliberate, documented)

Per Tue: **lower the per-slice event floor from 30 → 25.** Implement it as a **named, documented
knob**, not a silent global weakening:

- The trader-trust path (`trader_trust.rs` `trust_verdict`, which today borrows
  `PromotionParams::default { min_events: 30 }`) gets its **own** `TrustParams { min_events: 25 }`,
  so lowering the *trust/specialist* floor does **not** touch the **real-money pilot gate**
  (`honest.rs PilotThresholds { min_events: 50, min_regimes: 5 }` stays exactly as-is).
- Honesty tax of N=25: CIs are wider and the Bonferroni denominator (this wallet's slices) still
  applies — at 25 events a one-sided lower bound clearing a 3% margin is a **strong** claim. State
  the widened CI explicitly wherever a 25-event verdict is surfaced. Add a `#[test]` showing a
  25-event slice with hairline surplus still reads INDETERMINATE (no false trust).
- 25 is a floor for **being eligible for a verdict**, not a promise of trust. Nothing about the
  gate's margin, selection-null, or forward-only discipline relaxes.

---

## 4. The workstreams (the multi-workflow core)

Each workstream is a long run. For each lever inside it: (a) **pre-register** the hypothesis and a
**kill-criterion** in `reports/entries/` + `reports/strategies/` + `reports/CATALOG.md` *before*
running; (b) build it reusing the inventory below; (c) judge it at the belief-blind gate,
event-clustered, forward-only; (d) record SURVIVED / REFUTED / INDETERMINATE-BY-POWER in the
compounding ledger (§5). **No lever is assumed to add edge — the gate decides.**

> **WS-0 / WS-1 / WS-2 / WS-5 have a Forge-hardened implementation blueprint — follow it.**
> `RUN-SPECIALIST-SELECTION.FORGE_PLAN.md` (7 dependency-ordered Items with migration DDL,
> the extended `trader_slice_scores` CTE + favorite-residual cell-blind baseline, the pooled
> per-cell vote multiplier, the `TrustParams{25}` split, the multiplicity protocol, and the
> orthogonality BAR) + `.FORGE_DEBATES.md` (why pooling beats a hard cell-switch, and how it
> answers congregation + eff⊂favorite). Build WS-1/WS-2 to that blueprint; the prose below is the
> intent, the FORGE_PLAN is the spec. WS-3/WS-4/WS-6 remain research-loop work under the gate.

### Reuse inventory (extend these; do not rebuild)
- **Per-category profiling:** `trader_slice_scores()` + leak-free `trader_slice_scores_asof(cut)`
  and `TraderSliceStat { wallet, slice_kind, slice_key, n_events, n_days, surplus, surplus_sd,
  hit_rate }` in `common/src/storage/consensus.rs`. Slices today: `overall|sport|band|recency7d|
  recency30d`, band-blind baseline, event-clustered.
- **Verdict:** `trader_trust.rs` `trust_verdict` → `Trusted|Indeterminate|Avoid` with
  `best_slices`/`worst_slices`, using `surplus_bounds(events, surplus, sd, n_comparisons, params)`
  → `(lo, hi)` (Trusted = `lo > margin`; Avoid = `hi < 0`).
- **The gate:** `promotion.rs` `promotion_verdict(...)` (Bonferroni `alpha/n_strategies`, Moulton
  `effective_n = days.clamp(1,events)`, `lower_bound = surplus − z·se`, `promotable = lo > margin
  AND selection_null_ok`); `DEFAULT_PROMOTION_MARGIN = 0.03`, `SELECTION_NULL_P_BAR = 0.01`.
  Selection-null p is produced **out-of-band** by `scripts/selection_null.py` and read via env
  `SELECTION_NULL_P` (fail-closed).
- **The scorer:** `consensus.rs` `score_market(book, now, params)`; `WeightMode { Quality, Dollars,
  Count, TrustWeighted }`; per-vote `quality_weight(rank)`; `earned_quality()` in
  `consensus_cycle.rs` is the existing hook that threads an earned multiplier through
  `WeightMode::TrustWeighted` — **today keyed on wallet only; this is your extension point.**
- **Arms:** `StrategyDef { name, params, alerting }`; `default_portfolio()`, `trust_arms(base,
  cutoff)` (gated `CONSENSUS_TRUST_ARMS`), `_blind` baseline, existing `trust_weighted` /
  `trusted_only` / `sharp_tail` arms.
- **Orthogonality / portfolio:** `scripts/edge_orthogonality.py` (→ `reports/edge_orthogonality.json`),
  `scripts/portfolio_constructor.py`, `scripts/effective_n.py`, `scripts/persistence_tracker.py`.
- **Ingestion / cohort:** `leaderboard_tracker.rs` `refresh_universe`, `copy_trader.rs`
  `fetch_leaderboard_paged`, `sport_bucket()` in `consensus_cycle.rs`, `cohort.rs` bands.

### WS-0 — Foundation: data currency + slice-spine enrichment  *(do first; all WS depend on it)*
1. Refresh archive + cohort coverage (§2); write `00-baseline.md`.
2. Lower the trust floor to 25 (§3).
3. **Enrich the slice taxonomy.** Today the only market-category axes are coarse `sport` and 5
   price `band`s. Add the dimensions the user's thesis needs, captured/derived leak-free:
   - **market sub-type** — `moneyline | spread | over_under | binary_event | other`, detectable
     from `title`/`slug` (the `is_sports()` heuristic already recognizes `"o/u "`, `"spread:"`,
     `"moneyline"`). Freeze it at capture (new column via a **new** migration; mirror how `sport`
     is frozen) so it is leak-free and stable.
   - **favorite/longshot** beyond the 5 bands if useful; **time-to-resolution** bucket;
     **liquidity** bucket (from `size_usd`/market depth). Add each as a `slice_kind` in
     `trader_slice_scores()` and its `_asof` twin.
   Keep the band-blind baseline generalized to a **cell-blind** baseline (the fleet's average
   advantage *in that cell*), so a specialist's surplus is always measured against blind play in
   the **same** cell — this is what neutralizes favorite-loading per category.

Owned files (roughly): `consensus_cycle.rs` (bucketing), `common/src/storage/consensus.rs` (slice
SQL), a new migration, `config.rs` knobs, `scripts/capture_completeness.py`.

### WS-1 — The specialist map (per-(trader × cell) earned edge)
Build `scripts/specialist_map.py` (`--selftest`) and/or a Rust view that, for every wallet past
the 25-event floor, emits its **cell verdicts**: for each cell (sport × sub-type × band, plus
recency), the leak-free as-of surplus, `surplus_bounds` → Trusted / Avoid / Indeterminate,
Bonferroni **across that wallet's cells** (this is a large multiplicity surface — 78+ wallets ×
many cells; account for it honestly). Output `reports/selection/specialist_map.json` +
`specialist_map.md`: "who is a certified specialist in what," worst-first Avoid cells too. This is
the object every downstream arm consumes. **In/out temporal split**: fit the map on in-sample,
read edge on out-sample only — the map must *persist*, not just fit.

### WS-2 — Specialist-weighted consensus arms  *(touches the scorer — serialize with WS-3/WS-4b)*
Thread the specialist map into selection. New **silent** arms in `trust_arms()`:
- `specialist_weighted` — a new `WeightMode` (or extend `earned_quality()`) where a vote's weight
  is the trader's **cell-specific** earned quality for **this market's** (sport, sub-type, band),
  falling back to `quality_weight(rank)` when the trader is Indeterminate/absent in that cell
  (never zero a newcomer).
- `specialist_only` — count a vote only from wallets **Trusted in this market's cell**.
- `fade_avoid` — exclude (or, as a separate probe, contrarian-weight) wallets that are **Avoid in
  this cell**, even if globally ranked.
Judge each vs `favorite`, `trust_weighted`, and `_blind` on surplus-over-blind, forward-only.
Prove strict is byte-identical and the arms are silent + separately registered (mirror existing
tests). Every new arm **raises the Bonferroni denominator for all arms** — keep the set lean; if
it grows, split the gate into families (the repo's Bonferroni-family-split convention).

### WS-3 — Tail-the-most-profitable, re-ranked by earned edge
- Re-rank "who to follow" by **earned per-cell surplus**, not leaderboard PnL — extend
  `/trustedtraders` and the board to rank by certified specialist edge in each cell.
- `sharp_specialist_tail` — follow a **single certified specialist's** entry in **their best
  cell** (builds on the existing `sharp_tail`/`certified_only` arms), fresh-entry gated.
- Investigate the **0 `earned_eligible`** fact: is it the floor, the SE convention (D16-a), or a
  real "nobody's certified yet"? If the specialist framing certifies traders the global framing
  cannot, that itself is a finding.

### WS-4 — Novel levers (the "countless other things"; pre-register + gate each)
A menu — pursue the strongest first; each is silent, gate-judged, orthogonality-checked. Do **not**
promote any on backtest alone.
- **Conviction sizing** — weight a specialist's vote by their `size_usd` relative to their own
  norm (big-for-them bets), not absolute whale size.
- **Herding / fade** — detect when many *correlated* wallets pile the same side (crowded ⇒ edge
  gone) vs independent specialists agreeing; test fading the crowd.
- **Edge momentum vs mean-reversion** — is a trader's *recent* per-cell edge predictive of their
  next, or does it regress? (recency slices already exist.) Drives whether trust should decay.
- **Dispersion / disagreement** — does within-cell price dispersion among backers predict the
  outcome (confident consensus vs noisy)?
- **Cohort turnover / regression** — model leaderboard-cohort churn; discount edge attributable to
  a cohort that won't persist (adversarial split-half).
- **Round-trip PnL** — `advantage` is BUY-only (SELL = NULL today). Build leak-free round-trip
  (entry→exit) PnL per specialist as a **second** skill axis; a trader sharp on *timing* differs
  from one sharp on *direction*.
- **Microstructure conditioning** — condition specialist trust on liquidity/time-to-close cells.
- **Cross-cohort specialists** — a deep (rank > cutoff) trader certified in one cell is exactly
  what `earned_eligible` is for; feed WS-1's map into the `EARN_DEEP_SHARPS` promotion path
  (still human-gated to alert).

### WS-5 — Integration & compounding (the one book)
Isolated levers flatter themselves; a real book must **not double-count favorite** (recall
`elite_fresh_fav ⊂ favorite` added ~0 diversification, and there is currently **0/N orthogonal**
certified). For every SURVIVED lever:
1. Run it through `edge_orthogonality.py` against the **union of already-surviving** levers — keep
   it only if it adds **independent** edge (partial-out the others; report the marginal LB).
2. Feed survivors to `portfolio_constructor.py` to build the growth-per-unit-independent-exposure
   book.
3. **The integration bar:** the combined specialist book must beat **both** `favorite`-only **and**
   global `trust_weighted`, out-of-cohort and forward — otherwise the specialization is one
   favorite bet wearing new names. Report the marginal contribution of *each* lever to the book.

### WS-6 — Anti-regression & honest evaluation (throughout + finale)
- **Reconcile the SE convention (D16-a) before reading any GO** — the board uses day-deflated
  Moulton SE while `honest.rs pilot_verdict` passes event-N SE; they disagree by construction.
  Pick one, apply it everywhere a verdict is read, and say which.
- **Multiplicity across the whole search** — you will test many wallets × cells × levers. Re-run
  `selection_null.py` and estimate the family-wise error over the *entire* specialist search;
  simulate the certification pipeline on **label-permuted / synthetic-null** data and measure how
  often *some* specialist/arm emerges "certified" by chance. Recall `market_resid`: a +30%
  "surplus" was a baseline artifact a 0-baseline gate false-promoted. If a null world manufactures
  specialists at your observed rate, the real ones are unremarkable — say so.
- **Forward-only + persistence** — anything that fits the deep archive must clear
  `persistence_tracker.py` (leak-free in/out split, independent-cluster-COUNT floor) on **forward**
  rows before it counts as real.
- **Non-regression proof** — strict alert path byte-identical; all arms silent; gate green.

---

## 5. The compounding mechanism (make findings accumulate, not scatter)

Maintain **`reports/selection/FINDINGS.md`** as the single running ledger. One row per lever:
`hypothesis · exact config · verdict {SURVIVED | REFUTED | INDETERMINATE-BY-POWER} · LB/CI ·
forward-N so far · orthogonality vs surviving set · what would flip it`. Rules:
- A lever enters the **surviving set** only after the gate passes **and** it adds independent edge
  in §WS-5's orthogonality test. Being +EV alone is not enough if it's redundant with favorite.
- Each **new** lever is tested against the **current** surviving set — so findings *compound*
  (the book gets provably better) instead of piling up correlated copies of the same bet.
- REFUTED and INDETERMINATE entries are **kept**, with the number that refuted them — they stop the
  next session (or a parallel WS) from re-running a dead idea. This is how the program avoids
  regressing on things already learned.
- Cross-link the existing D-log: this program's findings become a new `DECISIONS.md` D-entry.

---

## 6. Sequencing & parallelism

- **WS-0 lands first** (foundation: currency, floor=25, enriched slice spine). Everything reads its
  output. Merge it before fanning out.
- Then **WS-1** (the specialist map) — WS-2/3/4 all consume it.
- **Parallel-safe:** WS-3's ranking/board work and WS-4 levers that **don't touch the scorer**
  (analysis scripts, round-trip PnL, cohort turnover) can run concurrently in separate worktrees.
- **Serialize the scorer:** WS-2 and any WS-4 lever that edits `consensus.rs` `score_market` /
  `earned_quality` touch a shared hot file — do them one worktree at a time, rebasing onto fresh
  `feat/consensus-engine` between merges. Coordinate the **migration number** if two WS add schema.
- **WS-5 integration** runs after the candidate levers have landed silent; **WS-6** runs throughout
  and as the finale.
- **Gate before every merge (the repo CI):**
  `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
  (Python: `python3 -m py_compile <script>` + `--selftest`). Rebase → gate → `git merge --no-ff` →
  the auto-updater redeploys → `git worktree remove`. Never merge broken/half work.

---

## 7. Adversarial self-review (Phase before the verdict — don't skip)

Red-team **your own program** with a fresh skeptical pass (stance = "the specialist edge is
overfitting and this went easy on it"). Make it hunt for, at minimum:
- **Overfitting the heterogeneity** — 78 wallets × (sport × sub-type × band × recency) cells is a
  huge multiplicity surface; a wallet's "best cell" is partly the max of noise. Did the in/out
  split and family-wise correction actually survive, or did the map just fit?
- **Completeness masquerading as skill** — a low-`capture_gap` wallet's "edge" could be a
  reconstruction artifact of which fills the 100-row page happened to catch.
- **Favorite in disguise** — is the specialist book just favorite-loading re-derived per sport? The
  cell-blind baseline is supposed to neutralize this; verify it does.
- **A kill-criterion set too lenient**, or a leak where deep-archive fitting bled into a "forward"
  read. Fix what it finds and re-run. A sycophantic self-review is worse than none.

---

## 8. Verdict & deliverables

Write `reports/selection/VERDICT.md`, a dated `reports/entries/YYYY-MM-DD-NN-specialist-selection.md`,
`reports/strategies/` files for each surviving arm, `CATALOG.md` pre-registrations, and a
`DECISIONS.md` D-entry. Include:
1. **Bottom line, first line, unhedged:** does per-specialist selection beat global tailing —
   forward and out-of-cohort — enough to matter? For each lever: SURVIVED / REFUTED /
   INDETERMINATE-BY-POWER, with its LB/CI and forward-N.
2. **The specialist map** — who is certified in what (and who to *avoid* in what).
3. **The integrated book** — marginal contribution of each lever; does it beat favorite-only and
   global trust_weighted; is it *diverse* or one bet renamed.
4. **Multiplicity verdict** — do the survivors beat the family-wise null across the whole search.
5. **Forward plan** — the exact N / regimes / calendar-weeks of forward paper data still needed to
   certify each silent arm at the pilot gate (N≥50, ≥5 regimes) for a **real-money** decision.
6. **The honest paragraph** — is this a real, diverse, persistent improvement, or a
   backtest-flattering re-slice of favorite? Be willing to say the juice isn't worth the squeeze.

**Standing truths to respect (don't re-derive or regress):** everything stays **paper/silent**;
the biggest *realized*-P&L lever remains the live alert-config leak (strict-only alerting while
winners stay silent) — that is **Tue's** pending call, out of scope here, don't conflate it with
these arms. Real money is separately gated (de-lever + ≥5 non-expiring regimes + months, per the
bad-days verdict) — nothing in this run flips that.

### Pre-registered honesty triggers (decide BEFORE running §WS-5)
Conclude a lever is **not** a real improvement if **any** hold:
- the specialist book does **not** beat `favorite`-only out-of-cohort/forward (it's favorite in
  disguise); or
- the per-cell heterogeneity does **not** persist across the in/out temporal split (it was fit,
  not skill); or
- a **label-permuted null** manufactures "certified specialists" at your observed rate (multiplicity
  ate the signal); or
- survivors add **no independent edge** over favorite in the orthogonality test (redundant, not
  diversifying).

---

## 9. When done
- Print a tight terminal summary: the one-line verdict, the SURVIVED/REFUTED table, and the three
  numbers that most drove it.
- Leave all artifacts under `reports/selection/`; all arms silent; nothing merged to live alerting;
  live ledger untouched.
- Note for memory (Tue decides whether to save): update the polymarket-consensus memory with which
  specialist levers SURVIVED vs REFUTED, the integrated-book verdict, the new 25-event trust floor,
  and any INDETERMINATE-BY-POWER results — honestly.

Remember the point: **tail the right sharp in the right market, prove it compounds, and be honest
when it doesn't.**
