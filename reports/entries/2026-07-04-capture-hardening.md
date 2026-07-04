# 2026-07-04 — Capture hardening: de-bias the forward reads + shrink the router latency

**Autonomous run, paper-only. Branch `feat/capture-hardening` (off `main` 8cb9fab), NOT
merged — left for review; the reviewing chat / Tue merges → autoupdater deploys.** No new
migration (Items 1–2 need none; the reserved 041/042 were not used). Nothing bets, nothing
promotes, no thresholds moved. `cargo build && cargo test` green after every item; the two
scripts self-test green.

The problem this run attacks (measured in `router_verify.py`): every forward number that
judges the router arm is **conditioned on the wallet staying tracked** (capture stops at
deactivation — 245 inactive wallets, 0 fills after `last_seen_on_lb`), and the router edge is
**front-loaded** while fill→signal latency is ~1.5–3 min. Two default-OFF, byte-identical-when-
off levers close both gaps; a third surfaces the router gate on the readiness board; the fourth
is a data-gated status read that just cleared its floor.

---

## Item 1 — Survivorship capture fix (`CAPTURE_DROPPED`, default OFF)

**Built.** A bounded slow loop that keeps polling the fills of DEACTIVATED wallets the scorecard
still cares about, so the forward scorecard/benchmark stops being survivorship-biased upward.

- `storage::scorecard_eligible_dropped_wallets()` — the wallets that are `active = FALSE` AND
  scorecard-eligible: EVER in `router_followset`, OR ≥100 BUY fills in band 0.45–0.90 over the
  trailing 365d (the `n_fills ≥ 100` floor the scorecard itself applies). Returns a poll-since
  cursor per wallet.
- `cycles/capture_dropped.rs::capture_dropped_tick` — polls those wallets, `consensus_max_
  concurrency`-semaphore-capped (same bound as the consensus fan-out, so it can't widen the 429
  pressure), archives NEW fills through the **same `insert_trader_fills` dedup path** as live
  capture, advances the shared cursor. A failed/429 poll leaves the cursor untouched (self-
  healing).
- `live.rs` — flag-gated task on the trust-refresh cadence; off ⇒ never spawned.

**What changed / why it's safe.** It writes **ONLY the durable `trader_fills` archive — never
consensus window votes** — so a deactivated wallet can never re-enter the live consensus book.
The consensus book is byte-identical whether the flag is on or off; the only thing that grows is
the archive the scorecard reads. `CAPTURE_DROPPED` is declared in the compose `environment:`
block (`${CAPTURE_DROPPED:-false}`) AND must be set in `.env.consensus` to reach the container
(the known env-drift footgun); default OFF.

**How verified.** `cargo build && cargo test` green. Ignored live-DB test
`capture_dropped_selects_deactivated_scorecard_eligible` (repo convention for DB tests): a
deactivated + ≥100-fill wallet IS selected; an ACTIVE wallet (owned by the main loop) and a
deactivated-but-thin wallet are NOT; and a new deactivated-wallet fill lands in `trader_fills`
(the acceptance). Run: `DATABASE_URL=… cargo test -p polymarket-common
capture_dropped_selects -- --ignored`.

## Item 2 — Hot-lane fast poll for the follow-set (`HOT_LANE`, default OFF; `HOT_POLL_SECS`=12)

**Built.** A task that polls ONLY the current follow-set wallets (~6) fast, then scores just the
one arm that cares — collapsing fill→router-signal latency from ~1.5–3 min to ≲30s.

- `cycles/hot_lane.rs::hot_lane_tick` — reads the follow-set from the shared slot the re-scorer
  publishes (`Arc<RwLock<Option<Arc<HashSet>>>>`), polls each wallet (same
  `consensus_max_concurrency` bound) every `HOT_POLL_SECS` (default 12, floored 5s), ingests
  through the SAME window-vote + fills dedup path, then runs a **scoped scoring pass over the
  affected markets only**: rebuild each book with `books_from_window_votes`, score ONLY the
  `proven_router` arm via the new pure `score_router_only`, upsert via the idempotent
  `upsert_consensus_signal`. It never touches the main cadence and never polls the whole universe
  faster (the 429 budget). Bonus: it also captures **inactive** follow-set wallets the slow loop
  (active-only) can't see — a router-proven wallet is routed to regardless of leaderboard status.
- `scanner::consensus::score_router_only` — pure; emits EXACTLY the `proven_router` signals the
  slow portfolio pass would over the same books, so fast and slow lanes converge (the signal just
  arrives sooner). No other arm is ever scored, so `strict` is untouchable by this path.
- `storage::traders_by_wallets` (any active status) attaches real rank/pnl to the fresh votes.

**What changed / why it's safe.** Gated on `HOT_LANE && PROVEN_ROUTER`; off ⇒ never spawned ⇒
byte-identical. When on, it only adds `proven_router` (EXPERIMENTAL, silent, non-alerting) rows
sooner and shares the one window store with the slow cycle (dedup, no divergence).

**How verified.** `cargo build && cargo test` green. Unit test
`score_router_only_scores_router_arm_and_nothing_else`: tags ONLY `proven_router`, counts ONLY
routed wallets (net_count excludes a non-router backer), and is fail-closed on an empty/absent
follow-set. The ≲30s acceptance is a dev-run observation (flag on): a follow-set wallet's fill
produces a `proven_router` row with `first_detected_at` ≈ poll time; flag off ⇒ byte-identical.

## Item 3 — Readiness-ledger rows

**Built.** `scripts/readiness_ledger.py` gains three INFORMATIONAL rows (STATUS / value-vs-
threshold / what's-needed / ETA); pure, fixture-tested builders. Today's live read:

| row | status | current | threshold |
|---|---|---|---|
| `router_gate` | **PENDING** | 0 sigs / 0 events / 0 regimes since prereg | ≥30 events / LB>3% / selection_null p≤0.01 / ≥2 regimes |
| `unified_book` | **NOT_MET** | 1/20 forward day-blocks | ≥20 |
| `beats_best_trader` | **NOT_MET** | best arm favorite LB −7.1% vs B_LB+3pp +6.4% | B_LB +3.4% + 3pp |

`router_gate` reads `proven_router` resolved signals with `first_detected_at ≥` the frozen
prereg stamp (`2026-07-04T09:43:04Z`); disjoint regimes = distinct calendar months (the table has
no sport column). The three are informational — NOT GO gates — so the board's binding-constraint
line is unchanged: **persistence (months)**, GO gates 2/4, real-money-eligible FALSE.

**How verified.** `--selftest` green (existing verdict logic + three new fixture-JSON cases:
thin→PENDING / cleared+artifact→MET, 1/20→NOT_MET / 20/20→MET, favorite-LB<bar→NOT_MET /
above→MET, plus the "not-a-GO-gate" invariant). Full live run renders all three rows and still
prints `BINDING CONSTRAINT: persistence`.

## Item 4 — Maker δ/T execution policy pick (DATA-GATED — status read, nothing built)

**Status: the floor is now CLEARED, and a policy meets the recommendation condition.**
`scripts/maker_fill_sim.py` (self-test green) over the dense-capture trajectories now has
**34 resolved tracked signals ≥ the 30 floor** (70 tracked). On `edge_per_signal`, the incumbent
TAKER is −0.128 (2% buffer) / −0.108 (fee-zero); **`maker_+0c_5m` (limit at the sharp's price,
cancel after 5 min) dominates it: −0.016 / −0.010**, i.e. limit-at-their-price claws back most of
the copyability tax — **with a FAVORABLE (non-negative) adverse-selection gap of +0.012** (the
fills it takes are not preferentially the losers). `maker_+2c_5m/15m` also dominate taker with
non-negative gaps (+0.012 / +0.025); the `+1c` and `+0c_15m` variants have NEGATIVE gaps (real
adverse selection) and are rejected on that basis.

**Recommendation (report-only — BUILD NOTHING; PILOT_ARMED stays unset).** When execution is
eventually wired for the router edge, the pick is **MAKER limit at the sharp's price (δ=0¢),
cancel after 5 min** — it dominates taker on edge/signal on both fee bases with a favorable
adverse-selection gap. Honest caveats that bound this, do NOT overclaim: (1) absolute edges are
NEGATIVE because the tracked stream is `strict`-dominated — this is POLICY-RELATIVE evidence, not
a live +EV claim; (2) n=34 barely clears 30 and is not day-clustered here → INDETERMINATE-BY-
POWER on absolute EV; re-confirm as it accrues; (3) δ=0¢/5m only fills 29% (71% abstain) — the
edge/signal win is largely "avoid the bad taker fills," though its edge/FILL (−0.054) still beats
taker and its adverse-selection gap is favorable; (4) 45s sampling ⇒ TRUE fill rates ≥ reported;
(5) the 2% fee is OUR modeled buffer, not the exchange charge — the fee-zero table (where the
dominance also holds) is the realistic basis; verify the live fee schedule before any real order.

---

## Guardrails honored
No real money; `PILOT_ARMED` unset, `EARN_DEEP_SHARPS` false, alert path untouched (strict-only).
No thresholds/prereg constants moved. No new migration. No merge/rebase of `main`, no push to
origin. Every item committed with a NEW/EXTEND-flagged message. Both new flags default OFF and
byte-identical when off.

## Rollback
All additive. Revert the branch (or leave it unmerged). At runtime: `CAPTURE_DROPPED=false` /
`HOT_LANE=false` + container recreate ⇒ both tasks vanish, portfolio byte-identical. Item 3/4 are
read-only scripts.

## Files
- Rust: `common/src/storage/consensus.rs` (+`scorecard_eligible_dropped_wallets`, +ignored test),
  `common/src/storage/copy_trade.rs` (+`traders_by_wallets`),
  `copy-trading-bot/src/cycles/{capture_dropped,hot_lane}.rs` (new),
  `copy-trading-bot/src/cycles/{mod,consensus_cycle}.rs`,
  `copy-trading-bot/src/scanner/consensus.rs` (+`score_router_only`, +unit test),
  `copy-trading-bot/src/config.rs`, `copy-trading-bot/src/live.rs`,
  `docker-compose.consensus.yml`.
- Python: `scripts/readiness_ledger.py` (3 rows + fixture selftest).
