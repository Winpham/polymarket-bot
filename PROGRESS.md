# PROGRESS — Optimal Congregation Engine run

Branch `feat/congregation-engine` (worktree off `feat/consensus-engine`), 2026-06-30.
Gate: `cargo build && cargo test` (clippy advisory — baseline has 2 pre-existing
`market_resid.rs` doc warnings, H10). Data: live `polymarket` DB via docker exec.

## Phase 0.5 pre-flight (§0.5) — DECISIVE, done first

Ran the minimum decisive pre-flight (read-only as-of SQL). **Outcome: diversification
premise DEAD ON THIS DATA** → Phases 2/5 (arms) NOT built, per the binding decision rule.

What it proved (full detail in RESEARCH.md / DECISIONS.md D2):
- **0** wallets certified as per-sport specialists at the capture bar (`lo>3%`, N≥30) —
  as-of at cut 2026-06-29, as-of at cut 2026-06-30, AND full-window in-sample (the most
  generous possible test). The edge is absent before fees, not just after.
- **0** wallet-sport cells with ≥30 events on both sides of any cut → persistence not even
  measurable; only one cut has two-sided coverage.
- Structural cause: the entire forward record is ~two adjacent days of one tournament
  (World Cup soccer ≈89% of resolved buys) + Grand-Slam tennis bursts → maximal slate
  collapse (H4); no uncorrelated edges to diversify.
- Reality correction (DECISIONS.md D1): `resolved_at` and `ts` are both bulk-backfill
  stamps on this archive; the honest as-of axis is the slug-parsed event date.

Deliverable: reproducible harness `scripts/asof_preflight.py` + `scripts/asof_slice_scores.sql`.

## Phase 0 — capture margin at the strategy gate (SHIPPED, non-regressive)

`board.rs::render` now gates arms at `slippage_pct + fee_pct = 3%` (threaded from
`live.rs`) instead of `PromotionParams::default()` margin 0. The live board and the
report now certify against the same bar a follower actually captures. Untouched: `strict`
alerting, `trader_trust` (deliberately margin-0). Green: `cargo build`; promotion unit
tests 6/6; enrich passthrough unchanged (16 passed).

## Phase 0.5 — `trader_slice_scores_asof(cut)` (SHIPPED, the leak-free instrument)

`Storage::trader_slice_scores_asof(cut)` in `common/src/storage/consensus.rs`:
`resolved_at < $1` in the `adv` CTE so both the slice surplus and the fleet band-blind are
bounded by the cut (H2); recency slices dropped (ambiguous under a cut). Correct for
forward data; the archive-caveat (D1) is documented at the call site. Compile-verified;
the *executable* as-of experiment lives in the Python harness (chosen over a DB-bound
`#[ignore]` Rust test because `resolved_at` is degenerate on the current archive — the
Python harness uses the honest slug-date axis).

## NOT built (deliberate, per §0.5 DEAD branch)

Phase 1 `SliceTrustMap` (feeds arms only), Phase 2 Arm A/D (`spec_footprint`/
`spec_contrarian`), Phase 3 CLV lens, Phase 5 edge-pool/coalition. No arm can be honestly
certified when 0 specialists exist; building them silent+OFF adds hypotheses for zero
information. Clean extension point recorded in DECISIONS.md D3/D4: when the pre-flight
first shows ≥2 persistent cross-sport specialists, Phase 1 + Arm A/D is the next run's
first move and this harness is their gate.

## Deliverables index

- `RESEARCH.md` — §3 findings (identification / independence / combination / capture), evidence-backed.
- `REPORT.md` — §5 certification + one-screen executive summary.
- `DECISIONS.md` — D1 (time axis), D2 (DEAD verdict), D3 (what shipped), D4 (accrual).
- `scripts/asof_preflight.py`, `scripts/asof_slice_scores.sql` — the reproducible harness.
- Code: `board.rs` + `live.rs` (Phase 0), `consensus.rs` (Phase 0.5). Gate green.
