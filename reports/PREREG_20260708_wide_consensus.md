# PRE-REGISTRATION — Wide-Pool Consensus Arms (frozen 2026-07-08, before any forward outcome)

Run: FABLE wild-generator (FABLE-WIDE-CONSENSUS-RUN.md). Branch `feat/wide-consensus`.
This freezes arm definitions and judgment criteria BEFORE the arms emit a single forward
signal. The 9-day retrospective in the run doc is MOTIVATION ONLY (stated biases: sharp-fill
entry proxy +1¢, resolved-only, day-bucketed windows, no event-day clustering) and can never
certify anything.

## Hypothesis

H1: The consensus mechanism's edge (favorite band 0.65–0.98) is carried by the MECHANISM
(≥3 distinct one-sided backers, ≤1 opposer, price coherence, two-sided-MM drop), not by the
top-40 leaderboard rank of the voters. Therefore widening the voter pool to all tracked
active non-bot wallets (~296 vs ~60) multiplies eligible supply ~3-8× at approximately the
champion's per-bet edge.

H0 (what would refute): wide-only signals' surplus-over-`_blind_wide` ≤ 0 at our realizable
entry, or the anchored variant strictly dominates the plain variant (edge lives in the
top-cohort anchor, not the wide mechanism), or the fires are bot-echo (backer sets
collapse to mirrored fills of a single top-40 wallet).

## Frozen arm definitions (as shipped in code)

- `favorite_wide` — champion `favorite` params exactly (min_backers 3, max_opposers 1,
  price_std ≤ 0.10, max_age 48h, band 0.65–0.98), scored on the WIDE book
  (`load_wide_window_votes` = eligible ∪ tracked deep with `trader_type <> 'bot'`).
- `favorite_wide_anchored` — same + `max_best_backer_rank = TRACK_CONSENSUS_RANK_CUTOFF`
  (≥1 top-cohort backer must co-sign; fail-closed on unranked).
- `_blind_wide` — capture-all (min_backers 1) on the SAME wide book; the band-matched
  baseline population for surplus and selection-null; never ledgered (prefix exclusion),
  never alerted.
- All silent (`alerting: false`); EXPERIMENTAL Bonferroni family; $100 flat stake;
  entry = decision-time `entry_ask` capture, fallback initial+1¢ haircut; fee 2%.

## Frozen judgment criteria (the standing gate, no new bars invented)

A wide arm becomes PROMOTION-DISCUSSABLE (never auto-promoted) only when ALL hold on
forward data (`first_detected_at ≥` the flip timestamp):
1. Standing gate: Bonferroni-corrected one-sided LB on surplus-over-blind > +3% at ≥30
   distinct events, SE deflated to distinct event-days (`promotion.rs` defaults), where
   the blind baseline is `_blind_wide` band-matched picks.
2. `selection_null.py` vs the `_blind_wide` population: p_emp ≤ 0.01 (≥1000 draws).
3. Regime persistence: surplus > 0 in ≥2 disjoint sport-regimes; any cell-level claim uses
   the WITHIN-CATEGORY blind baseline (verify A6 standing rule).
4. Echo audit passes: share of fires whose backer set is ≥2/3 wallets that co-fill within
   60s of the same top-40 wallet's fill < 25% (measured from `trader_fills` timestamps);
   plain-vs-anchored comparison reported alongside.
5. ≥5 distinct day-clusters.

Pre-committed comparisons to report regardless of outcome: favorite_wide vs favorite (same
forward days, same scoreboard basis), favorite_wide vs favorite_wide_anchored, per-sport
splits with within-category baselines, realized entry_ask coverage + tax vs the 1¢ model.

## What this run does NOT do

No real money (paper-only, permanent posture per D26 legal gate). No alerting. No champion
path change (flag default OFF; wide pass is additive after eligible scoring; atoms merge is
fill-only). No promotion — the gate + Tue decide.
