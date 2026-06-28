# 2026-06-28 · Entry 06 — Strategy catalog (workflow) + quick-wins shipped

Ran the **strategy-foundry** multi-agent workflow (54 agents: 4 research → 7 family generators →
42 adversarial vetters → synthesis). **42 strategies generated, 37 survived, 5 rejected.** Full
catalog: `../strategies/CATALOG.md` + `catalog-2026-06-28.json`.

## The headline insight (reshapes priorities)
**The highest near-term ROI is measurement/honesty INFRASTRUCTURE, not new market signals.** The
top-4 ranked items are all infra — they are the *denominator* almost every "edge" is judged against:
1. `blind-band-benchmark` (86) — surplus-over-blind per price-band × category × venue + a permanent
   blind-shadow null arm. Build this FIRST; it unblocks every edge claim.
2. `cluster-robust-dedup` (80) — cluster by `event_slug` → **fixes the within-match leak** (Tue's
   known issue) so correlated legs don't inflate N.
3. `belief-blind-promotion-gate` (74) — always-valid confidence sequence + FDR across all live +
   replayed variants + a **distinct-EVENT** N floor (controls multiple-comparisons / optional-stopping).
4. `correlation-effective-N` (72) — p-value calibration.

Best NEW market edge = **cross-venue** (free, mirrored World Cup): `depth-confirmed-dutch-divergence-alert`
(70) gated by `cross-venue-resolution-truth` (68 — the make-or-break: resolution *concordance*, not
divergence magnitude). **Kalshi-native + scraped families ranked LAST** (positions private,
microstructure unharvestable under paper-only) — matches the entry-05 live probe.

## Universal confounds the catalog hammered (Foresight-aligned)
- **Favorite-longshot bias** games any AVG(won − entry) metric → need surplus-over-blind-by-band.
- **Multiple comparisons / optional stopping** across 13 live + replayed variants → need FDR +
  always-valid sequences + distinct-EVENT floor; never promote on in-sample edge.
- **Mid-price scoring is a phantom-edge generator** (esp. thin Kalshi books) → score at executable
  bid/ask net of fees. **Action taken below: start capturing executable quote into atoms (can't backfill).**
- Many surviving edges are **INDETERMINATE-BY-POWER** → pre-registered floors + silent forward-tracking.

## Shipped this entry (param-only quick-wins → portfolio 10→13)
Added to `default_portfolio` (silent, forward-tracked, pre-registered, no post-hoc relaxation):
- `tight_cluster` (min_backers=4, max_opposers=0, max_price_std=0.04, max_age_mins=720)
- `elite_fresh_fav` (require_elite, price_band=0.80–0.97, max_age_mins=180)
- `favorite_tail` (price_band=0.85–0.96, non-sports) — FLB measurement probe, NOT promotable
CI green.

## Next builds (catalog-ordered, the infra-first roadmap)
1. `blind-band-benchmark` + blind-shadow null arm (the denominator).
2. `cluster-robust-dedup` (event-level) into the scoreboard.
3. `belief-blind-promotion-gate` (the only thing allowed to flip a strategy to `alerting`).
4. `atom-replay-cli` (realize the no-backtest superpower over stored atoms) + capture executable bid/ask.
5. cross-venue `resolution-truth` whitelist → `depth-confirmed-dutch-divergence-alert`.
