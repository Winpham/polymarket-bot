# Entry 09 — Earned trader-trust profiles ("who to actually follow")

**2026-06-29 · branch `feat/trader-profiles` (off `feat/consensus-engine`)**

Built the full trader-profile lever from `run-prompts/RUN-TRADER-PROFILES.md` (Forge-hardened;
reasoning trail in `RUN-TRADER-PROFILES.FORGE_DEBATES.md`). Five phases, each gate-green +
committed + live-verified on a throwaway Docker Postgres. Default-OFF and non-regressive for
anything touching live `strict` alerting.

## What shipped

**Phase 0 — durable, never-stop capture spine.** Migration `026_trader_fills` (every tracked
trader's fills, BOTH sides, deduped by two partial unique indexes: `tx_hash` when present,
content when null). `poll_trader_activity` now returns `PollResult{trades, raw_count}`; a 429
surfaces as `Err` (cursor not advanced ⇒ gap re-fetched) and bumps a metric. `insert_trader_fills`
is ONE UNNEST batch with a bare `ON CONFLICT DO NOTHING`. `record_capture` counts a gap iff a
full 100-row page's oldest row is newer than everything we'd seen (the API ignores `startTs` and
returns a hard 100-row newest page — the *only* mechanism is poll-often-and-accumulate). Capture
once, use twice: the SAME consensus poll feeds the window AND the archive; a Semaphore
(`CONSENSUS_MAX_CONCURRENCY=8`) bounds the fan-out. Frozen `sport` bucket at capture (single
source of truth). Flagged book-source cutover `CONSENSUS_BOOKS_FROM_FILLS` (default off,
dual-write).

**Phase 1 — leak-free, multi-outcome resolution ledger.** An INDEPENDENT unresolved source
(`trader_fill_unresolved_conditions`) UNIONed into housekeeping fixes survivorship: markets a
trader bet that never fired a consensus signal still resolve. `resolve_trader_fills(cond,
winner_index)` is multi-outcome correct; `advantage = won::int − price` for BUY (mirrors the gate),
NULL for SELL. Closed-but-no-winner (void/refund) is SKIPPED — never charges every BUY a loss.

**Phase 2 — earned trust = surplus-over-own-blind + gate reuse.** `trader_slice_scores()` is ONE
event-clustered query keyed by wallet × slice {overall, sport, price band, 7d/30d} with a
`trader_fills`-native band-blind baseline that neutralizes favorite-longshot loading. The verdict
(`scanner/trader_trust.rs`) adds ZERO new statistics — it reuses `surplus_bounds` (a sibling of
the promotion gate's machinery, `probit` stays private): ≥30 distinct-EVENT floor ⇒ INDETERMINATE,
Bonferroni across the wallet's slices, `lo > margin` ⇒ Trusted, `hi < −margin` ⇒ Avoid. One
conservatism, not two — RAW surplus at the verdict; shrink-toward-0 lives only on the P4 weight.

**Phase 3 — surfacing.** `/trader <wallet>` (honesty-first profile: verdict + decisive bound + N
events, best/worst games, recency, capture-completeness flag), `/trustedtraders` (ranked by
EARNED trust, not leaderboard rank), and a second "👥 Trader trust" table on the `:9002` board.

**Phase 4 — earned trust feeds consensus (silent, flag-gated).** `TraderVote` gains
`earned_quality` (defaults to `quality_weight(rank)`) + `trusted` (defaults true);
`WeightMode::TrustWeighted` and `trusted_only` are two NEW silent arms appended ONLY when
`CONSENSUS_TRUST_ARMS` is on, judged by the gate in the EXPERIMENTAL family. A cached trust map is
slow-refreshed (`TRUST_REFRESH_MINS=60`), not recomputed per cycle. INDETERMINATE/absent ⇒
`quality_weight(rank)` fallback (never zeroes a new trader). Tiering keys on `net_count`, so live
`strict` alerts are provably non-regressive.

**Phase 5 — cutover/scale/retention.** `CONSENSUS_BOOKS_FROM_FILLS` flip documented (dual-write
kept for instant rollback). The data-api 429 count is surfaced on the board — the scale gate: only
widen `TRACK_TOP_N`/`TRACK_PERIODS` (via periods, never N>50) once it stays ≈ 0.
`TRADER_FILLS_RETENTION_DAYS=0` (keep-all) retention knob; durability = the existing daily
`scripts/consensus-backup.sh` pg_dump.

## Verification

Per-phase gate green (`fmt --check`, `clippy --workspace --all-targets -Dwarnings`, `test
--workspace`). Live-verified on a throwaway Docker PG:
- dedup (tx + intra-batch + null-tx content), gap detection (first-poll no-gap, full-page-no-overlap
  ⇒ gap, partial-page no-gap), re-derived-quality book source, SELL exclusion (`trader_fills_it`);
- multi-outcome resolve (advantage signs, SELL=NULL), void-stays-unresolved (`resolve_multi_outcome_and_void`);
- **the load-bearing one** (`trust_scores_e2e`): skilled wallet ⇒ Trusted, negative ⇒ Avoid,
  10-event ⇒ Indeterminate, and an FLB favorite-loader's surplus neutralized to ~0 by the band-blind
  baseline even though its raw advantage is positive;
- board renders the trust table with a Trusted trader (`board_trust_render`).
Unit tests cover `surplus_bounds` monotonicity, the verdict logic, both formatters, and the P4
non-regression (strict byte-identical, `TrustWeighted` tier == `Quality` with default votes,
`trusted_only` drops untrusted / no-ops when all trusted, arms registered separately + silent).

## Honest limits

- **Forward-only, accruing.** No trader has 30 resolved distinct events yet — every profile reads
  INDETERMINATE until the archive fills (sports next-day, others over days). That is correct: trust
  is EARNED at the belief-blind gate, not hoped.
- Round-trip PnL (SELL advantage) is a documented v2; we measure directional BUY edge only.
- Finer Gamma `category` is deferred (cost-zero); `sport` is the slug-derived bucket.
- Promotion of a trust arm to alerting is a deliberate human call — never automatic.
