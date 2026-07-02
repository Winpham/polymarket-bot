# Long Autonomous Run — Turn the deep-pool data into reliability + edge

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace + Python), in a dedicated git worktree off `main`.
Gate-green + commit after EVERY phase; at the end `merge --no-ff` into `main` (the branch the
launchd auto-updater deploys) so it ships. Companion reading (same house style, read for
conventions + the earned-trust spine this run stands on): `run-prompts/RUN-TRADER-PROFILES.md`,
`run-prompts/RUN-HONEST-PNL-TRACKER.md`, `REPORT-DEEP-OBSERVATORY.md`,
`VERIFY-DEEP-LEADERBOARD.md`, `DATA-MODEL.md`, `model/README.md`.

---

## 0. The one-sentence mission
We just widened the tracked universe from the top-40 to the **top-200** (5× more traders, all
captured/resolved/profiled) — now **convert that data into measurable gains in profit
*reliability* and profit *margin/edge*** by (a) letting certified sub-whale sharps EARN their
way into a deeper consensus, (b) testing the thesis that small efficient traders give a
follower **more realizable edge than whales** (they don't move the price), and (c) generating +
belief-blind-certifying new strategies over the richer data — all **additive, flag-gated,
paper-only, and non-regressive** to the trusted top-50 signal until each new thing is *earned*.

The motto: **capture wide, promote narrow. Rank is not trust; volume is not edge. Every new
voter and every new strategy earns its place ONLY at the belief-blind, event-clustered,
sample-floored, shrunk gate against a matched blind baseline. The trusted top-50 signal does not
change until a deep trader is earned in. Wild generator, rigorous gate. An honest NULL is a real
result. NO real money.**

---

## Philosophy — read first, it overrides everything
- **More data is candidate signal, not automatic edge.** 224 new deep traders and ~+33%
  picks/day are *raw material*. What makes any of it improve profit is surviving the
  belief-blind gate (`trader_trust::trust_verdict` / `promotion::promotion_verdict`): a positive
  Bonferroni-corrected surplus **lower bound** over a **band-matched blind baseline**, over
  **≥ min_events distinct resolved events**, **event-clustered** (never pooled), **shrunk**
  toward the pool mean. A green number that isn't gate-certified is noise.
- **The core thesis to test (profit MARGIN):** deep sharps are *capital-efficient* (high ROI on
  small size), not *whales* (high absolute PnL who move the book). A **follower captures more of
  a small trader's edge** — less market impact, better CLV, a real executable ask closer to
  their entry. So deep-sharp-backed signals may have **higher realizable edge after the capture
  haircut** than whale-backed ones, even at the same raw surplus. This is measurable on the
  honest-P&L ledger (`HonestPnl`, `ledger_stats`, CLV, capture-margin). If it holds, it directly
  lifts margin; if it's NULL, say so.
- **Deeper consensus, earned not assumed.** Consensus today counts *backers* (a whale-biased
  headline). With a profiled 280-trader universe you can weight/gate consensus by **earned
  trust** across cohorts, so a signal certified sharps agree on beats a signal random whales
  agree on. Extend the existing `earned_quality`/`TrustMap`/`trusted_only` machinery — do NOT
  invent a parallel one.
- **Non-regression is sacred.** The trusted `strict` alerting and the top-40 voter set stay
  **byte-for-byte** until a deep trader clears the gate AND is deliberately earned in
  (flag-gated, shadow-first). Prove it every phase.
- **Cost-zero, paper-only, Max-subscription only. NO real money, ever.** Same standing rules as
  every run here.

---

## The data we now have (verified live 2026-07-02 — the substrate for this run)
- **280 tracked leaderboard traders**: 56 hot (rank ≤ 40, the trusted voters — unchanged) + 224
  deep (41–200), all polled, archived, resolved, profiled.
- **Ongoing yield**: deep adds **+67.7k picks/day** on top of hot's 205.9k (**+33%**), **185**
  distinct active deep wallets/day (vs 64 hot — ~3× more *distinct* signalers), covering ~2,830
  markets/day. Archive holds **~624k picks**; deep bet **2,704 markets no top-40 trader touched**
  (**+48% unique market breadth**, 5,647 → 8,351).
- **The sharps to mine**: **21 deep traders are already gate-ready** (≥30 distinct resolved
  events — enough for a real `trust_verdict`), **~20 more approaching** (15–29), 46 early. **0
  deep traders are certified yet** — their verdicts are accruing; most are ⏸ indeterminate.
  That 0-vs-21 is exactly the frontier this run works.
- **The instruments are already built**: cohort observatory (`scanner::cohort`,
  `board::render_cohort`, sliceable `?cohort=trusted|top250|band2|all&sort=profit|rank`); the
  belief-blind trust gate; honest realizable-P&L + CLV + capture-margin; forward-seal + paper
  ledger. This run *uses* them; it does not rebuild them.
- **Re-verify at the start of Phase 0** with the read-only queries in `REPORT-DEEP-OBSERVATORY.md`
  (hot/deep split, gate-ready count, no deep leak into signals). If reality has drifted, note it
  and adapt; if the widening has regressed (deep leaking into `strict`), STOP and report.

---

## Gate (run before EVERY commit)
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
Python (if touched): `python3 -m py_compile <f>` + a smoke run on a tiny synthetic fixture.
**Live-verify each phase on a THROWAWAY Docker Postgres** (never the prod `polymarket-bot-postgres-1`):
`docker run -d --name pg-edge -e POSTGRES_DB=polymarket -e POSTGRES_USER=bot -e POSTGRES_PASSWORD=bot -p 55499:5432 postgres:17-alpine`,
then run the ignored integration tests with `DATABASE_URL=postgres://bot:bot@localhost:55499/polymarket … -- --ignored`.

### Deploy + coordination gotchas (learned the hard way — heed them)
- The autoupdater deploys **local `main`** on HEAD advance (`origin/main` is intentionally
  stale); merge `--no-ff` into local main, let the autoupdater rebuild. **Multiple chats work
  this repo at once** — re-check the next free **migration number** right before you add one
  (grep `migrations/`), and **never edit an already-applied migration, even a comment** (sqlx
  checksums the whole file → crash-loop). Container env vars must be in BOTH `.env.consensus`
  AND the `environment:` block of `docker-compose.consensus.yml`. `wt/` is in `.dockerignore`
  (keep it there — dev worktrees blow up the build context otherwise). If a deploy hangs on
  "transferring context" or crash-loops on a migration checksum, see
  `[[reference-polymarket-deploy-mechanism]]` behavior: force `compose build --no-cache`.

---

## Context (extend, don't rebuild — grep to pin exact lines)
- **Belief-blind gate**: `copy-trading-bot/src/scanner/trader_trust.rs` (`trust_verdict`,
  `TraderTrust`, `TrustVerdict`, `cached_slice_scores`, `TraderSliceStat`) +
  `scanner/promotion.rs` (`promotion_verdict`, `PromotionParams`, `surplus_bounds`). This is THE
  gate — every promotion and every new arm passes through it. Do not add a second gate.
- **Consensus scoring + earned-trust weighting (already partly built)**:
  `scanner/consensus.rs` (`score_market`, `score_all_strategies`, `quality_weight`,
  `ConsensusParams` — `min_backers`/`strong_net`/`elite_net`/`elite_rank`/`require_elite`/
  `trusted_only`/`weight_mode`, `StrategyDef`, `default_portfolio`, `Tier`). `cycles/consensus_cycle.rs`
  (`earned_quality` — trust-map vote weighting; `TrustMap`; `compute_trust_map`;
  `books_from_window_votes`; `trade_to_window_vote`; the trust-arm registration behind
  `CONSENSUS_TRUST_ARMS`). Extend THIS for trust-weighted / deeper consensus.
- **Eligibility seam (the non-regression contract)**: `common/src/storage/consensus.rs`
  `load_window_votes` + `load_buy_fills_since` filter on `COALESCE(consensus_eligible, TRUE)`;
  the `followed_traders.consensus_eligible` column (migration 033) is set from rank ≤ cutoff at
  upsert. **A deep trader that EARNS eligibility needs a durable flag that leaderboard refresh
  won't clobber** — build `earned_eligible` (see Phase 0). Consensus counts a trader iff
  `consensus_eligible OR earned_eligible`.
- **Cohort model**: `scanner/cohort.rs` (`Band`, `parse_bands`, `CohortFilter`, `band_of`;
  config `TRACK_COHORT_BANDS`). Every per-cohort analysis reuses this.
- **Honest realizable P&L / CLV / capture-margin**: `scanner/honest.rs`,
  `common/src/storage/consensus.rs` (`HonestPnl`, `ledger_stats`, `consensus_scoreboard_by_strategy`,
  the paper ledger `honest_paper_ledger`, entry-ask / decision-time capture). This is where the
  "profit margin" thesis is measured — realizable ROI after the follower's haircut, not raw surplus.
- **Board**: `board.rs` (`render_cohort`, `render_trust`, `render_honest`) — surface new
  findings here, clearly labeled, non-alerting until earned.
- **Config**: `config.rs` — new flags use `#[config(env=…, default=…)]` and **default to today's
  behavior**. Alerting knobs: `consensus_alert_strategies`, `consensus_alert_watch_for`,
  `consensus_alert_cross_dedup_mins`.
- **Archive**: `trader_fills` (all picks, both sides, `resolved`/`outcome_won`/`advantage`,
  `sport`), `consensus_vote_window`, `consensus_signals`, `capture_gaps`. Everything you need is
  already captured — this run is analysis + gating, not new capture.

---

## Rejected approaches (do not build these)
- ❌ Auto-promoting deep traders into consensus by rank, PnL, or a raw green number. Eligibility
  is EARNED at the belief-blind gate, then flipped by a deliberate (flag-gated) act — never by
  leaderboard presence.
- ❌ A new/parallel gate, baseline, or trust metric. Reuse `trust_verdict` / `promotion_verdict`
  and the band-matched blind baseline. Inventing a gate is how you fool yourself (see the
  `market_resid` 0-baseline false-promotion class in memory).
- ❌ Pooled or small-sample green numbers. Event-clustered, sample-floored (≥ min_events),
  shrunk. A per-trader or per-arm ROI without its N and its Bonferroni lower bound is not a
  result.
- ❌ Changing `strict` alerting, the top-40 voter set, or any live-emitted signal before a deep
  trader is earned in. Shadow-first: compute what WOULD change, ship nothing, measure.
- ❌ Real money, live betting, or any non-paper action. Measurement only.
- ❌ Raising `TRACK_DEPTH` toward 500 as part of THIS run (the cold-cycle latency was ~96s at
  200; re-measure before pushing depth — that's a separate change). This run mines the data we
  ALREADY capture at 200.
- ❌ Editing an applied migration; bumping the winmon→brainstem-style pointer; running concurrent
  write/git subagents alongside your own git work.

---

## Phase 0 — Earn deep sharps into a deeper consensus (durable, shadow-first)
The direct unlock. **(a) Durable earned eligibility:** add `followed_traders.earned_eligible
BOOLEAN NOT NULL DEFAULT FALSE` (new migration — grep for the next free number). The leaderboard
upsert must NOT touch it; consensus counts a trader iff `consensus_eligible OR earned_eligible`
(update `load_window_votes` + `load_buy_fills_since` filters + `get_active_traders`). **(b) The
promotion pass:** a read-only job that runs `trust_verdict` over each deep (rank > cutoff)
trader's resolved slices and lists those that **clear the gate** (Trusted: surplus lower bound >
capture margin over ≥ min_events). **(c) Shadow measurement:** a parallel, **non-alerting**
computation of what `strict` (and the portfolio) WOULD emit if the certified deep sharps voted —
alert rate, tier distribution, net_count deltas — WITHOUT shipping it. Surface on the board
(cohort observatory: mark gate-clearing deep traders "⤴ promotable"). **Nothing flips
automatically**; promotion is a deliberate flag (`EARN_DEEP_SHARPS`, default off) that sets
`earned_eligible` for gate-clearers. Prove: with the flag OFF, live signals are byte-for-byte
unchanged. Report which of the ~21 gate-ready clear, and the shadow impact. Gate, commit.

## Phase 1 — The edge thesis: do deep sharps give better *realizable* edge than whales?
The profit-margin question. Using the honest-P&L machinery (realizable ROI = CLV − execution
haircut − fees; capture-margin gate), **compare, on the paper ledger, event-clustered:** signals
backed by ≥1 **certified deep sharp** vs signals backed **only by whales (top-40)** — realized
ROI, CLV, capture lag, and the real measured haircut (`entry_ask − entry_ask_mid`). Pre-register
the hypothesis (deep-sharp-backed ≥ whale-backed after haircut) and the metric BEFORE looking.
Control for the confound that deep sharps trade smaller/less-liquid markets (segment by
liquidity band; a thin-market edge you can't fill is not edge). Shuffle/label-permutation NULL to
prove the gap isn't a baseline artifact. Output: a certified answer — deep sharps DO / DO NOT
improve realizable margin, with N, lower bound, and the liquidity caveat. An honest NULL here is
a real, valuable finding. Gate, commit.

## Phase 2 — Trust-weighted / deeper consensus (reliability) + threshold re-tune
Consensus today is an absolute *backer count* — whale-biased and it fires *more* as the eligible
set grows. Build, as **silent forward-tracked strategy arms** (registered like the existing trust
arms, `alerting = false`), variants that use the **earned-trust weight** (`earned_quality`) and
the **cohort** as first-class inputs: e.g. `trust_weighted` (net *trust* not net *count*),
`cross_cohort` (fires only when a whale AND a certified deep sharp agree — a conviction signal),
`sharp_only` (certified traders across all cohorts). Because more eligible voters inflate
`net_count`, **re-tune the absolute thresholds** (`min_backers`/`strong_net`/`elite_net`) — as a
config-gated variant, default = today — so selectivity/precision holds; measure precision +
realizable ROI of each arm vs `strict` over the forward window. Prove `strict` itself is
untouched. Certify only what clears the gate on ≥ N days. Gate, commit.

## Phase 3 — Tail-the-sharp + learn-from-the-best (new strategies)
For each **certified** trader (any cohort), a direct single-trader **paper-follow** strategy,
measured with the honest ledger (realizable ROI, capacity, capture lag) — "who is actually
worth tailing" as an executable track record, not a leaderboard rank. Add a "fresh certified-sharp
entry" arm (a certified trader's NEW position in a market, captured decision-time) and measure its
CLV vs a lagged follow. Generate broadly across the 280-trader pool; **certify narrowly** — only
traders/arms whose shrunk lower bound clears the capture margin survive. Surface the survivors on
the board (non-alerting) with their N and bound. Gate, commit.

## Phase 4 (stretch, power-permitting) — Relational / bloc structure
The data-starved frontier is less starved at 280 traders + more history. Belief-blind probes:
co-movement clusters (traders who repeatedly take the same side of the same market within a
window), leader→follower lag (who moves first — a *timing* edge if a slow follower reliably
trails a fast sharp), and smart-vs-dumb segmentation by forward surplus. Treat every cluster/lead
as a hypothesis that must clear the gate; expect most to be **INDETERMINATE BY POWER** and say so
honestly (do not upgrade a power-limited null to a finding). Only ship a relational signal if it
independently certifies. If the whole phase is NULL, that IS the result — report and move on.

## Phase 5 — Consolidate, certify, cutover, report
Collect every arm/promotion from Phases 0–4; keep only those that **clear the belief-blind gate**
(positive shrunk lower bound over the capture margin, ≥ N distinct resolved days, event-clustered,
not power-limited). Promote the certified deep sharps (`EARN_DEEP_SHARPS` decision recorded) and/or
enable a certified consensus arm's alerting — **each behind its own default-off flag**, with the
`strict` incumbent proven non-regressive. Choose production flag values from evidence. Final
`merge --no-ff` into `main`; deploy via the autoupdater; verify live (container healthy, no deep
leak into `strict` unless earned, board surfaces the new arms). Write a short report: which deep
sharps certified, whether the edge-thesis held (margin lift + liquidity caveat), which new arm (if
any) beats `strict` on realizable ROI, the honest NULLs, and exactly which flags are on/off in prod.

---

## Acceptance
Every phase gate-green + committed; final `merge --no-ff` + deploy. Deliverables:
1. Durable `earned_eligible` + a shadow-first, flag-gated promotion pipeline; a report of which
   gate-ready deep sharps certify and the shadow consensus impact.
2. A certified answer to the edge thesis — do deep sharps improve **realizable** margin vs whales,
   with N / lower bound / liquidity caveat (a clean NULL is acceptable).
3. Trust-weighted / cross-cohort consensus arms forward-tracked vs `strict`, with re-tuned
   thresholds, and a byte-for-byte proof `strict` is unchanged.
4. Tail-the-sharp survivors (certified single-trader follows) with executable track records.
5. An honest verdict on relational/bloc structure (likely power-limited — say so).
6. A production config record + short report; nothing promoted that didn't clear the gate.

## Standing disciplines
Extend, don't rebuild. Additive + reversible; every new flag defaults to today's behavior.
Belief-blind at the gate; rank isn't trust, volume isn't edge, capture wide / promote narrow.
Event-clustered, sample-floored, shrunk — no pooled or small-sample green numbers; pre-register
hypotheses; shuffle/permutation NULLs; adversarially verify surviving findings. Shadow-first —
change no live-emitted signal until a deep trader/arm is *earned* in. Cost-zero, paper-only, **NO
real money**. `merge --no-ff` at the end; deploy via the autoupdater. An honest NULL beats a
flattering number.
