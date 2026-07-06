# Long Autonomous Run — PER-SPORT SPECIALIST MINING + COPYABILITY GATE: follow the right people, only where we can actually tail them

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace; deploy branch `main`, auto-deploys ~5 min after merges).
Ground truth on `main`: `DECISIONS.md`, `REFINED-STRATEGY.md`, `DATA-MODEL.md`, `scripts/` kit.

---

## 0. The one-sentence mission

We currently tail the **global** PnL leaderboard blind — which is a lazy copycat that lags behind and
loses edge to the follower tax. **Stop.** Zero-sum logic is airtight: whoever tops a leaderboard
extracts from worse money, so per-sport SPECIALISTS with real edge exist in every liquid market. This
run **mines those specialists per sport from the resolved-fill history we already store, and certifies
them on COPYABILITY — surplus over the blind favorite at the price WE can actually get after the
follower tax — not on their raw profitability.** MLB-first (the one non-tournament sport with minable
depth today, and a *sharp* market → the honest copyability test). The product is a per-sport,
copyability-gated follow-set that replaces blind global tailing. Paper-only, gate-judged, cost-zero.

## Why this is NOT the dead "congregation" premise (do not relitigate — extend it)

A prior run (feat/congregation-engine, DECISIONS "per-sport specialist book DEAD") certified per-sport
specialists on the FORWARD consensus record and found **0** — correctly, because that record was one
correlated World-Cup weekend (≪ 30 independent event-days per wallet). That verdict stands **for that
data**. This run is different on two axes: (1) it mines the far deeper **historical `trader_fills`**
record (resolved BUY fills keyed by event date × sport — MLB alone has ~41k fills / 50 wallets with
≥20 / 21 dates), not the 4-day consensus record; (2) it judges **COPYABILITY at our price**, a
question the congregation run never asked. If it STILL finds nothing copyable in MLB, that is a real,
publishable null about sharp-market untailability — not a re-run of the same dead premise.

## The three things this run must get right (fix BEFORE computing)

1. **Per-sport, not global.** Rank each wallet by its surplus **in that sport**, over the sport×band
   blind-favorite baseline, event-clustered at the match super-key — never by global PnL (blind to
   *what* they're good at) and never against a global-blind baseline (the composition trap, D16-b).
2. **Copyability, not their profitability (the anti-lazy-copycat core).** A wallet's raw edge comes
   partly from the PRICE they got; we enter AFTER their fill at the worse price (the measured follower
   tax +0.7–2.1¢; the truth audit's F5 showed winners had already moved ~1.3¢ by our first observable
   mid). So every certification is computed at **OUR realizable entry** (`initial_market_price` /
   `entry_ask`, after tax), and the per-wallet **copyability tax** (their fill price − our entry) is
   reported. An edge that vanishes at our price is NOT a follow (expected in sharp markets — a valid
   honest null, K2).
3. **Directional prediction vs uncopyable mechanism.** Leaderboard profit can come from market-making
   the spread, in-play/live entries, cross-venue arb — none copyable by a delayed taker. FLAG and
   exclude: two-sided/market-maker wallets (reuse the existing directionality score — they sit on both
   sides), systematic price-improvement (they consistently beat the post-fill mid ⇒ liquidity
   provision, not prediction), and late/in-play entries. Certify only plausibly-directional edge.

## Ground truth you must NOT relitigate

- Follower tax is real and measured (+0.7–2.1¢; sharp markets can eat 100% of a thin edge). The edge is
  accrual- AND copyability-gated (DECISIONS D16). `favorite` is the real, attack-hardened base edge.
- Per-sport RESOLVED trader_fill depth we already store (event-date × sport): **soccer 544k/276 wallets
  ≥20 but 21 dates = all WC; tennis 68k/50/18 dates = Wimbledon; MLB 41k/50/21 dates = MINABLE + year-
  round + sharp; other 42k/123/49 dates; politics 432/7 = thin (grows to Nov-2026 midterms); NBA
  139/1, NFL 7/0 = CALENDAR-BLOCKED, ~0 games — auto-onboard Sept/Oct, no shortcut.** Crypto has no
  parseable date (D1) and never fires consensus — baseline only.
- **The archive time-axis is the slug-parsed EVENT DATE, not `resolved_at`** (a bulk-backfill stamp) or
  `ts` (mostly a crawl stamp) — DECISIONS D1. Any per-wallet history must key on the event_slug date.
- The per-sport trust machinery already EXISTS and is dormant: `trader_slice_scores` (per-wallet ×
  slice {overall,sport,band,7d,30d}, trader_fills-native band-blind surplus), `surplus_bounds` +
  `trust_verdict` (≥30 distinct-EVENT floor ⇒ INDETERMINATE, Bonferroni across the wallet's slices,
  `lo>margin`⇒Trusted), and the `trusted_only` / `trust_weighted` consensus arms (enabled only under
  `CONSENSUS_TRUST_ARMS=true`, experimental family). REUSE all of it; do not reinvent ([[extend-dont-rebuild]]).

## What already exists (reuse)

Self-testing Python on `main` (`--self-test`): `superkey.py` (match cluster key), `sport_edge_tracker.py`
+ `softness_map` machinery (softness/skill decomposition), `selection_null.py` (selection null, D7),
`grading_verify.py` (Gamma second-source), `slice_study.py` (FDR/LODO/self-test patterns). Rust: the
whole trader-trust stack above (`common/src/storage/consensus.rs::trader_slice_scores`,
`copy-trading-bot/src/scanner/{promotion.rs::surplus_bounds, trader_trust.rs::trust_verdict}`,
board trust table, `WeightMode::{TrustWeighted}` + `trusted_only`). DB:
`docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket --csv -q`. At-fire entry =
`COALESCE(initial_mean_price, mean_price)`; realizable entry = `COALESCE(entry_ask, initial_market_price
+ haircut)`. Gamma: `gamma-api.polymarket.com/markets?closed=true&condition_ids=<cid>` (non-default UA).

## Non-negotiable guardrails

1. **Isolated worktree off fresh `main`, new branch, tag first.** `main` MOVES UNDER YOU — `git worktree
   list`, non-overlapping slice, smallest additive change to shared files (append/renumber on collision).
   **Applied migrations IMMUTABLE.** Prefer analysis + docs; if you enable the existing `trusted_only`
   per-sport arm it must stay **silent, default-OFF, experimental family** (no migration, no alerting
   change) — the arm is EARNED at the gate, not switched on by hope.
2. **Gate EVERY commit.** Python: `py_compile` + a PASSING self-test (recovers an injected specialist
   AND reads flat on a null/random-wallet fixture). Rust (if touched): `cargo fmt --check --all &&
   RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo clippy --workspace --all-targets --locked &&
   RUSTFLAGS="--cfg tokio_unstable" cargo test --workspace --locked`. **`--cfg tokio_unstable` is
   REQUIRED** (a bare `-Dwarnings` overrides `.cargo/config.toml` → false-red on a gated tokio_metrics
   field). **Re-gate post-merge `main`** before the ~5-min deployer ships it.
3. **Paper-only.** No env flips on the live bot (propose `CONSENSUS_TRUST_ARMS`/follow-set values,
   don't apply); deploy only via `scripts/consensus-autoupdate.sh` (rebuilds only on code paths;
   `--ff-only`; docs/scripts = "no code change"). Cost-zero: no API keys, no child claudes.
4. **Report ugly numbers first.** A sport whose specialists' edge dies at our price, a "top" wallet that
   turns out to be a market-maker, a category that's all uncopyable timing — those LEAD the report.

## Pre-registration (fix BEFORE computing)

- **Unit:** (wallet × sport). Family = all (wallet × sport) cells with ≥ the event floor.
- **Floors:** certify nothing below **30 distinct resolved match-events** for that wallet in that sport
  (the existing trust floor); below = INDETERMINATE (watch-list). Report N honestly per cell.
- **Baseline:** sport×band blind-favorite (never global-blind). **Statistic:** surplus at OUR realizable
  entry, event-clustered at the match super-key, Bonferroni across the wallet's slices (existing
  trust math) + a **selection null** (reuse `selection_null.py` — is this wallet's per-sport selection
  distinguishable from random same-profile picks?) + BH-FDR q=0.10 across the wallet×sport family.
- **Kill criteria:** K1 self-test fails (injected copyable specialist → Trusted, market-maker fixture →
  excluded, random wallet → not Trusted, noise → 0 FDR survivors) ⇒ STOP. K2 a wallet's edge is real at
  THEIR price but ≤0 at OUR price ⇒ NOT copyable, exclude (report the tax that killed it). K3 the
  per-sport specialist follow-set does not beat blind global-leaderboard tailing on forward-only rows ⇒
  specialist selection adds nothing here, report the null loudly. K4 the sport's "top" wallets are
  dominated by market-makers / price-improvers ⇒ the sport's profit is structurally uncopyable — a
  publishable finding, not a failure.

## Phases (each gate-green + committed; report incrementally)

### Phase 0 — setup + reproduce
Worktree, branch, tag. Reproduce the per-sport resolved-fill depth census (confirm MLB ≈ 50 wallets ≥20
across 21 dates; NBA/NFL ≈ 0). Print, per sport, how many (wallet × sport) cells clear the 30-event
floor — the honest map of what is certifiable TODAY vs calendar-blocked.

### Phase 1 — per-sport raw performance mining (`scripts/specialist_mining.py`, self-testing)
Reconstruct each wallet's resolved BUY fills by **event_slug date × sport** (D1 time axis). Per (wallet
× sport): distinct match-events, hit rate, and RAW surplus over sport×band blind at THEIR fill price.
The "who's been winning at what" map. Self-test: injected skilled wallet ranks top, coin-flip wallet ~0.

### Phase 2 — the copyability transform (the core; extend the script, self-testing)
Re-price every (wallet × sport) record at OUR realizable entry (the follower tax): surplus over blind
at `COALESCE(entry_ask, initial_market_price+haircut)` when available, else the measured mean tax by
sport. Report per-wallet **copyability tax** = (their fill − our entry) and how much of their raw edge
survives it. K2 lives here. Self-test: a wallet with edge-only-from-timing collapses to ~0 at our price;
a genuine predictor keeps most of it.

### Phase 3 — mechanism classification (extend, self-testing)
Flag and exclude uncopyable profit sources: (a) two-sided/market-maker wallets (reuse the directionality
score — appears on both sides of the same market), (b) systematic price-improvement (consistently beats
the post-fill mid ⇒ liquidity provision), (c) late/in-play entries (fill timestamp near resolution).
Certify only plausibly-directional wallets. Self-test each flag on a synthetic fixture.

### Phase 4 — the belief-blind per-sport trust gate (reuse the Rust machinery via a harness)
For each surviving (wallet × sport): the existing `surplus_bounds`/`trust_verdict` at OUR-price surplus,
≥30-event floor, Bonferroni across slices, + the selection null (Phase-2 CLI), + BH-FDR across the
family. Emit the certified per-sport specialist set. Reconcile against the dormant `trader_slice_scores`
(does the OUR-price gate agree with the native band-blind trust?). INDETERMINATE below floor.

### Phase 5 — the per-sport follow-set + forward validation (silent, earned)
Turn the certified specialists into a per-sport `trusted_only` follow-set (the dormant machinery),
SILENT / default-OFF / experimental family — propose the `CONSENSUS_TRUST_ARMS` + follow-set env values,
do not apply. Forward-measure the copyable lift of specialist-tailing vs blind global-leaderboard
tailing (paired, forward-only rows, 1 hypothesis slot). Watch-list: NBA/NFL cells to auto-onboard when
their seasons start; MLB cells approaching the floor; politics toward the midterms — each with its
re-read trigger.

### Phase 6 — synthesis + merge
`reports/entries/NN-specialist-mining.md` (per-sport certified specialists, the copyability-tax table,
the market-maker exclusions, the honest nulls first) + a DECISIONS entry + `REFINED-STRATEGY.md` only
where it binds (e.g. "follow per-sport specialists at OUR price, not the global leaderboard"; "MLB
specialist edge SURVIVES/DIES the tax"; "NBA/NFL onboard Sept/Oct"). Merge `--no-ff`, **re-gate
post-merge `main`** with the correct RUSTFLAGS, confirm the deployer + container behavior are unchanged.

## Rejected approaches (do not do)

- **Certifying on raw profitability instead of copyability** — the whole point is to stop being a lazy
  lagging copycat; every verdict is at OUR price after the tax (K2).
- **Global-PnL ranking or global-blind baseline** — per-sport surplus over sport×band blind only.
- **Re-running the dead congregation premise** — mine the historical fill depth + copyability, not the
  4-day consensus record; a null in MLB after THAT is a real finding, reported as such.
- **Switching on `trusted_only`/alerting/env for real** — the arm is earned at the gate, stays
  silent/default-OFF; propose values, Tue applies. No real money. No migration. No child claude/API key.

## Acceptance

Per-sport (wallet × sport) family pre-registered; specialists mined from the historical resolved-fill
record on the event-date time axis; every certification computed at OUR realizable entry with the
copyability tax reported; market-maker/price-improver/in-play wallets flagged and excluded; a
belief-blind per-sport trust gate (reusing `surplus_bounds`/`trust_verdict` + selection null + FDR)
emitting a certified per-sport follow-set; a SILENT, earned per-sport `trusted_only` proposal (values
proposed, not applied) with a forward paired-lift test vs blind global tailing and an NBA/NFL/politics
watch-list; kill criteria honored (an edge that dies at our price, or a market-maker-dominated sport, is
a valid honest null); self-testing instruments committed; docs updated; merged `--no-ff` + post-merge
re-gated green; live behavior unchanged. The deliverable is WHO to follow, per sport, only where their
edge survives OUR price — the end of blind lagging copycat tailing.
