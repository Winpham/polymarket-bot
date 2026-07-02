# Deep-pool → reliability + edge (run report, 2026-07-02)

Follow-on to the top-200 widening (`REPORT-DEEP-OBSERVATORY.md`): convert the
5×-wider captured universe into measurable profit **reliability** and
**margin** — additive, flag-gated, paper-only, non-regressive. Motto held
throughout: *capture wide, promote narrow; rank is not trust; an honest NULL is
a real result.*

## Substrate re-verification (2026-07-02 04:00 prod snapshot, read-only)
| check | result |
|---|---|
| hot/deep split | 56 hot (rank ≤ 40) / 221 deep — capture healthy |
| deep leak into `strict` | 2,180 backer slots over 7d, ranks **1–40 only** — 0 leaks |
| deep gate-ready (≥30 resolved BUY events) | **13** (the brief's ~21 was a looser/any-side count) |
| deep certified by the belief-blind gate | **0** — every deep verdict ⏸ INDETERMINATE |

All snapshot analysis ran against a **restored backup** (`pg-report`), never prod.

## What shipped (all default-off / silent; `strict` byte-for-byte unchanged)

**Phase 0 — durable earned eligibility + shadow-first promotion pipeline.**
`followed_traders.earned_eligible` (migration 035): the durable half of
eligibility — the leaderboard refresh never touches it (proven live: rank churn
cannot clobber a promotion). Both book sources now count a trader iff
`consensus_eligible OR earned_eligible` (all-FALSE ⇒ provably a no-op).
`scanner::earned` runs the promotion pass over the EXISTING `trust_verdict`
(no new gate) and a read-only **shadow study** (what the live portfolio WOULD
emit if certified sharps voted — identical books/scorer, A/B diff). Board:
"⤴ Earned deep sharps (shadow-first)" panel + ✅⤴/✅🗳 cohort markers.
`EARN_DEEP_SHARPS` (default OFF) is the only path that flips eligibility, in
the hourly trust-refresh task, logged as the promotion record.
**Result today: 150 deep traders profiled, 13 gate-ready, 0 certified ⇒ 0
promotable; shadow impact zero by construction.** The bounds are dominated by
day-deflation — deep traders' events cluster on few distinct days, so effective
N stays small even at N=96 events.

**Phase 1 — the edge thesis (deep sharps vs whales, realizable margin).**
Pre-registered instrument `scripts/deep_edge_thesis.py`: labels each resolved
`strict` signal deep-backed iff a deep trader bought the same (market, outcome)
before detection (decision-time discipline, post-deep-capture era only),
measures the exact honest-P&L realizable-ROI formula per group, event-clustered,
with a (band × day)-stratified label-permutation null + liquidity split.
- **Tier A (primary, certified sharps): STRUCTURAL NULL** — no certified deep
  sharp exists yet, so the certifiable comparison cannot run. Honest answer.
- **Tier B (exploratory, gate-ready deep): direction POSITIVE, power-limited** —
  honest-ROI gap **+15.8pp** favoring deep-backed (68 vs 131 events), CLV +6.3%
  vs +2.4%, no inversion in the high-liquidity half — but permutation
  **p = 0.29** ⇒ INDETERMINATE BY POWER. Nothing promoted; the instrument
  re-runs on any future snapshot (`--certified` feeds from the Rust harness).

**Phase 2 — deeper/trust-weighted consensus (reliability).**
New silent arms behind `CONSENSUS_TRUST_ARMS` (experimental Bonferroni family,
never alert): `cross_cohort` (fires only when a whale AND a certified deep
sharp agree — inert until a sharp is earned in), plus the existing
`trust_weighted` / `trusted_only` (= sharp-only). Threshold re-tune as a
config-gated SILENT variant `strict_retuned` (`CONSENSUS_RETUNED`, fail-closed
parse) — evidence: strict's alert-class fires all sit at net ≥ 4 (34/686 over
7d); each earned sharp adds +1 net, so **4,5,8** preserves selectivity for the
first 1–2 earned sharps. `strict` itself never moves.

**Phase 3 — tail-the-sharp.**
`TraderVote.certified` (STRICT gate-Trusted flag; unprofiled = false,
fail-closed — unlike the deliberately-lenient `trusted`) + two `min_backers=1
certified_only` arms: `sharp_tail_fresh` (≤3h, actionable) vs `sharp_tail`
(lagged control) — their CLV difference measures the freshness premium. The
existing signal machinery gives decision-time capture, honest ROI/CLV/capture
lag, and the paper ledger for free; the backers field records WHICH sharp.
`scripts/tail_records.py` renders per-wallet executable track records
(day-deflated Bonferroni LB vs the 3% capture margin). **Accrual starts when
the arms are enabled and ≥1 trader is certified; honest zero today.**

**Phase 4 (stretch) — relational/bloc probes: honest NULLs.**
`scripts/relational_probes.py` (pre-registered): co-movement pair surplus
(67 pairs, 436 shared events, +3.3% but selection-null p=0.16 → **NULL**);
deep-leader timing premium (+0.5%, 27/68 positive, sign-test p=0.96, does not
beat the whale-lead control → **NULL**); dumb-bloc feasibility (6 raw-advantage
fade candidates — a lead only; nothing built). The relational frontier stays
power-limited at 280 traders, as anticipated.

## Production config record (this deploy)
| flag | value | why |
|---|---|---|
| `CONSENSUS_TRUST_ARMS` | **true** (was default false) | start SILENT forward accrual of the trust/cross-cohort/tail arms + hourly trust map; no alerting change; volume bounded (≤ `_blind`) |
| `CONSENSUS_RETUNED` | **4,5,8** | silent selectivity baseline, from the net-count evidence above |
| `EARN_DEEP_SHARPS` | **false** (default) | promotion stays report-only — nothing certifies today anyway; flipping it is Tue's deliberate call |
| `TRUST_REFRESH_MINS` | 60 (default) | trust inputs move ~daily |
| everything else | unchanged | `strict` alerting, voter set, thresholds untouched |

## What to watch (the standing loop)
- Board "Earned deep sharps" panel: the moment a deep trader shows **⤴
  promotable**, the shadow table quantifies what earning them in would change —
  then `EARN_DEEP_SHARPS=true` (+ recreate stack) is the deliberate flip.
- `sharp_tail_fresh` vs `sharp_tail` CLV on the scoreboard: the freshness
  premium, once any trader (hot or deep) certifies.
- Re-run `deep_edge_thesis.py` / `tail_records.py` / `relational_probes.py`
  against a fresh snapshot as history accrues (all read-only, restored-backup
  targeted).

**Nothing was promoted that didn't clear the gate — and today nothing cleared
it. The pipeline that lets tomorrow's clearers in is now live, shadow-first,
and reversible.** Paper only; NO real money.
