# RUN — Capture Hardening (survivorship fix + hot lane + ledger rows)

**Paste-to-launch prompt for a long autonomous Opus 4.8 run on `~/polymarket-bot`
(Rust + Postgres, PAPER-ONLY).** Authored 2026-07-04 by the router/unified-risk chat
(D27/D28, merge 8cb9fab) — all file:line pointers below were verified live that day.

```
# AUTONOMOUS RUN — Capture Hardening. Repo: ~/polymarket-bot. Models: Opus/Sonnet ONLY
# (never Haiku; never set ANTHROPIC_API_KEY; never spawn child claude processes).
# PAPER-ONLY. Work on ONE branch `feat/capture-hardening` in a git worktree
# (`git worktree add wt/capture-hardening -b feat/capture-hardening`). Build items
# SEQUENTIALLY. Gate per item = cargo build && cargo test (+ --selftest for any script).
# DO NOT merge to main — a main HEAD advance AUTO-DEPLOYS to the running bot
# (launchd autoupdater, scripts/consensus-autoupdate.sh). Leave the branch for review.
# Reserved migration numbers for THIS run: 041 (and 042 if truly needed) — 040 is
# CLAIMED by the MM-filter calibration chat (memory: project-polymarket-mm-filter). Check
# `ls migrations/` first; if 041 is taken, STOP and report (concurrent-chat collision).
# NEVER edit an already-applied migration file (sqlx checksum crash-loops the app).

## CONTEXT (read first)
- DECISIONS.md D27/D28 + reports/entries/2026-07-04-proven-router.md and
  2026-07-04-unified-risk-benchmark.md — the router arm, its verification, the risk policy.
- The proven_router paper arm is LIVE (PROVEN_ROUTER=true): follow-set re-scored hourly
  (live.rs — "Router follow-set re-scorer" task), published from
  refresh_router_followset (common/src/storage/consensus.rs, migration 039).
- reports/PREREG_2026-07-04T094304Z_proven_router.md — frozen thresholds. Do not tune any.

## ITEM 1 — Survivorship capture fix (the de-biasing build; do this first)
Problem (measured, router_verify.py A4): fill capture STOPS when a wallet drops off the
leaderboard — followed_traders has 245 active=false wallets with 0 fills after
last_seen_on_lb. Every forward scorecard/benchmark read is conditioned on staying tracked
⇒ biased UP by an unknown amount.
Build: keep polling fills for deactivated wallets that the scorecard still cares about —
at minimum every wallet that EVER appeared in router_followset, plus wallets with ≥100
band fills in trailing 365d (the scorecard-eligible pool). Bounded: a dedicated slow loop
(hourly is fine; reuse the trust-refresh cadence pattern in live.rs), semaphore-capped like
the consensus poll (consensus_max_concurrency), flag-gated env default-OFF
(e.g. CAPTURE_DROPPED=true set in BOTH .env.consensus AND the compose environment: block —
env drift between them is a known footgun). Fills go through the SAME ingestion path as
live capture (trader_fills dedup exists). Add a test proving deactivated-wallet fills land.
Acceptance: with the flag on in a dev run, a deactivated wallet's new fills appear in
trader_fills; with it off, byte-identical behavior.

## ITEM 2 — Hot-lane fast poll for the follow-set
Problem (measured): fill→ingestion median 66s p90 124s + up to 60s cycle tick ⇒ signal
detection ~1.5–3 min. The router follows ~6 wallets; the edge is front-loaded (only 28–36%
of signals retrace to the sharp's price — reports/maker_fill_sim.json).
Build: a flag-gated (HOT_LANE=true, default OFF, both env files) tokio task that polls ONLY
the current follow-set wallets every HOT_POLL_SECS (default 12) via the existing
poll_trader_activity, appends through the SAME window-vote ingestion (dedup exists), then
runs a SCOPED scoring pass for the affected market only: build that one market's book via
books_from_window_votes and score ONLY the proven_router arm (score_market is PURE —
copy-trading-bot/src/scanner/consensus.rs:337), upsert via the existing idempotent
upsert_consensus_signal. Do NOT touch the main cycle cadence and do NOT poll the whole
universe faster (API 429 budget). Read the follow-set from the same shared slot live.rs
already publishes (Arc<RwLock<Option<Arc<HashSet<String>>>>>).
Acceptance: unit test for the scoped scorer (router arm only, other arms untouched);
in a dev run with the flag on, a follow-set wallet fill produces a proven_router signal
with first_detected_at ≲30s after the fill's ts; flag off ⇒ byte-identical.

## ITEM 3 — Readiness-ledger rows
Extend scripts/readiness_ledger.py (read-only) with three rows, each STATUS /
value-vs-threshold / what's-needed / ETA:
- router_gate: proven_router signals with first_detected_at ≥ the prereg timestamp vs the
  standing gate (promotion_verdict ≥30 events / day-deflated LB > 3% / selection_null p≤0.01
  / ≥2 disjoint regimes) — expect PENDING with counts.
- unified_book: forward day-blocks accrued vs the ≥20 floor (reports/unified_book.json).
- beats_best_trader: best arm LB vs B_LB + 3pp (reports/best_trader_benchmark.json).
Keep the board's binding-constraint line = the unmet gate with the longest horizon.
--selftest on fixture JSONs.

## ITEM 4 — DO NOT BUILD (data-gated; just report status)
maker δ/T execution policy pick: re-run scripts/maker_fill_sim.py; report resolved-signal
count vs its 30 floor. If ≥30 AND a policy dominates taker on edge/signal with a
non-negative adverse-selection gap, write the recommendation to the run report — build
nothing live.

## STANDING GUARDRAILS
- NO REAL MONEY. PILOT_ARMED stays unset; EARN_DEEP_SHARPS stays false; alerting flags
  untouched (alert path = strict only).
- Never bump thresholds/prereg constants. Never merge/rebase main. Never push to origin.
- Commit per item with a NEW/EXTEND-flagged message ending
  "Co-Authored-By: <model> <noreply@anthropic.com>".
- Final report: reports/entries/2026-07-04-capture-hardening.md — per item: built/tested/
  what-changed/how-verified + the Item-4 status line. Then STOP and hand back for review;
  the reviewing chat (or Tue) merges → autoupdater deploys.
```
