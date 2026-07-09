# 2026-07-08 — Execution-policy shadow ledger (Fable wild-generator run, Tier-1 champion refinement)

**Branch:** `feat/exec-policy` · **Prereg:** `reports/PREREG_20260709T020500Z_exec_policy.md`
(frozen before any outcome-joined read) · **Flag:** `EXEC_POLICY_SHADOW` (default OFF) ·
Paper-only; promotes nothing; arms nothing.

## Mission

ONE strategy proposal + ONE implementation pass, priority ladder Tier 1 (refine the
champion) → Tier 2 (additive stack) → Tier 3 (new edge). Champion = favorite-tilted
consensus copy, honest ROI-on-turnover verified live this session: **+3.27% after fees,
324 resolved / 168 events / 10 days**. Its limiters: A capacity, B leverageability,
C persistence.

## Candidates considered (ranked; effort spent top-down per the ladder)

1. **K1 · TIER 1 · PICKED — execution-policy shadow** (B primary, opens A). Outcome-blind
   structural read off the live tape (recency-constrained lookups, n≈20–22/horizon):
   on `favorite` the executable ask ≈ mid₀+3.4¢ at fire → +2.2¢ at +5m → +0.6¢ at +15m →
   ~mid₀ at +30m, while the mid itself shows no material decay <30 min (D8). So the
   ledger's +3.27% is implicitly a PATIENT-taker number (housekeeping captures the ask
   ~10–20 min post-fire); a fire-time copier pays ~3¢ more (≈ −3.5% ROI at 0.85 entries);
   a maker resting at fire-time mid gets filled BY the relaxing spread, fee-free.
   ~3.5–4.5¢ of entry spread between the worst and best policy ≈ larger than the whole
   champion edge. Measure it forward, per signal, judged by the existing ledger machinery.
2. **K2 · TIER 1 · DEFERRED** — maker at the sharp's fill price ("set the price"): an
   independent autonomous run froze `PREREG_20260709T011424Z_maker_copy_g3.md` hours
   before this session and is mid-flight on `feat/maker-copy-g3`. Duplicating it would
   collide; its adverse-selection verdict + this run's P-MREST arm triangulate the same
   trap from two universes (sharp-fill-anchored vs consensus-signal-anchored).
3. **K3 · TIER 1 · KILLED by historical replay** — widen recurring-regime supply by
   lowering the consensus floor to 2 backers (attack on C). The `loose` arm already logs
   2-backer signals: in the favorite band they are NEGATIVE everywhere — MLB −3.4% (27
   events), tennis −3.6% (168), other −4.1%, esports −2.2%, soccer −0.6%. The ≥3-backer
   floor is load-bearing; C stays supply/calendar-gated (consistent with D17-b: 0/12
   orthogonal, supply-limited).
4. **K4 · TIER 2 · runner-up** — wire the dormant `pilot.rs` sized-shadow into the daemon.
   Zero information today: it self-vetoes on λ̂≈0.15 < 0.25 and books nothing until dense
   CLV accrues. Revisit once the tape has ~2 weeks of CLV.
5. **TIER 3 — none.** Tiers 1–2 move the axes; no new-mechanism edge is needed or claimed.

## What was built (all additive, flag-gated, default-inert)

- **Migration 041** `exec_policy_entries`: one set-once row per flagged-strategy signal —
  fire-time top-of-book (bid/ask/mid + tape timestamp), patient ask (+15 m), maker fill
  verdict (REALISTIC print vs OPTIMISTIC touch, fill time), booking state. Durability:
  the tape prunes at 72 h; this freezes the fire-time book forever (same rationale as
  `entry_ask`, migration 032).
- **`common/src/storage/exec_policy.rs`**: tape lookups (`recv_at` ordering only — D1-E
  clock lesson; no look-ahead; 900 s staleness refusal), one-shot evaluator, explicit-entry
  paper-ledger append (`append_paper_bet_at`, same idempotency contract as
  `append_paper_bet`), booking under `exec_fire:/exec_p15:/exec_mrest:<strategy>` labels.
  Maker arm books ONLY on a realistic print, at fee 0 (makers pay zero; no rebate modeled);
  unfilled ⇒ abstain, visible in the table, never a ledger row.
- **Housekeeping sub-step** (`exec_policy_shadow_pass`): budgeted evaluate + book per
  cycle, best-effort per signal, pure DB (no HTTP). Runs only when `EXEC_POLICY_SHADOW=true`.
- **Config**: `EXEC_POLICY_SHADOW` (false), `EXEC_POLICY_STRATEGIES`
  (`favorite,elite_fresh_fav`), `EXEC_POLICY_MAX_PER_CYCLE` (40). Policy constants
  (35 m eval age, 60 h tape-safety ceiling, 900 s staleness, +15 m patient, 30 m cancel)
  are FROZEN in code, deliberately not env-tunable.

## Verification

- Full gate GREEN: `cargo fmt --check --all` + `clippy --workspace --all-targets`
  (`-Dwarnings`, tokio_unstable) + `cargo test --workspace` (288 pass).
- Throwaway Postgres 17 (port 55433): migration 041 applies via `run_migrations`;
  **22/22 ignored DB integration tests pass** — the 4 new ones (no-look-ahead +
  staleness refusal; print-vs-touch incl. size-less quote echo and post-cancel
  exclusion; e2e evaluate→resolve→book incl. maker abstain on the runaway winner,
  set-once, idempotent re-book; ledger entry guard + pnl arithmetic) AND all 18
  pre-existing storage tests (non-regression).
- Note: pre-existing repo-wide rustfmt drift (stable toolchain moved to rustfmt 1.9.0)
  fixed in a separate mechanical commit — `--check --all` was already red on untouched
  main files before this run.

## Verdict path (frozen in the prereg)

INDETERMINATE-BY-POWER until ≥30 booked resolved signals/policy and ≥5 day-clusters
(~1–2 weeks of accrual at favorite's ~30 signals/day, tape-coverage-limited). Then the
bands: REFINEMENT CONFIRMED / TRAP CONFIRMED (maker) / MIRAGE CONFIRMED (fire-taker).
Everything judged from `honest_paper_ledger` + `exec_policy_entries` by the standing
honest-P&L and gate machinery; any promotion goes through the belief-blind gate.

## To activate (Tue's call, after merge deploys)

Append to `.env.consensus`: `EXEC_POLICY_SHADOW=true` (LIVE_TAPE is already on), then the
sanctioned `bash scripts/consensus-autoupdate.sh`. Until then the daemon is byte-identical.
