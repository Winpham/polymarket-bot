# 2026-06-28 · Entry 01 — Run 1: Consensus engine foundation

## Goal
Turn the cloned `polymarket-bot` into a **consensus copy-trading alert** product:
auto-track the top-N leaderboard traders, alert when they converge on a directional
position. Alert/paper only, no real money.

## What the repo actually was
A mature ~14k-LOC Rust workspace (ML `trading-bot` + per-trader `copy-trading-bot` +
`common` + Postgres + Telegram + Prometheus/Grafana). The copy bot mirrored only
**individual, manually-`/follow`ed** wallets. **No auto-tracking of top-N, no consensus
logic at all** — that gap is the product.

## Built (branch `feat/consensus-engine`, 4 commits, all CI-green)
- `scanner/consensus.rs` — pure, unit-tested scoring engine (11 tests).
- `scanner/leaderboard_tracker.rs` — auto-follow union of top-N across periods + drop-grace.
- `cycles/consensus_cycle.rs` — poll universe → per-market books → score → tiered alerts.
- `migration 021` + `common/storage/consensus.rs` — signals, alerts, forward-tracking.
- `cycles/housekeeping.rs` — resolves signals as markets close (`resolved_outcome_won`).
- Prometheus consensus metrics, `/consensus` + `/tracked` commands, config knobs, docs.

## Verified working end-to-end
Ran the real binary against Docker Postgres + live Polymarket API (dummy Telegram):
migrations applied, **auto-tracked 62 traders**, **scored 353 markets** in one cycle,
persisted signals correctly. A WATCH-tier signal stayed below the alert threshold → no
false push. CI gate green:
`RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`.

## Status
- Phase A (reality/spec): ✅  · Phase B (engine): ✅  · Phase C (validation): foundation ✅,
  forward results pending deployment.

## Next
Pivot to a **strategy portfolio** (entry 03): run many variants forward simultaneously,
since there is no backtest. Then deploy to accrue real resolved outcomes.
