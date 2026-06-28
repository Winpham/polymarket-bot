# Weekly strategy regeneration — runbook

The **strategy-foundry** workflow (54 agents: research → 7 family generators → adversarial vetting →
synthesis) is the quality instrument that keeps "continuously coming up with strategies." It must run
in a **local Claude Code session** (it calls the Workflow tool, writes to `reports/`, and implements
quick-wins). Cadence: **weekly** (chosen 2026-06-28).

## How to re-run (one command in a local session)
Ask Claude: **"Re-run the strategy-foundry to generate a strategy DELTA — new ideas only, diffing
against the existing catalog."** Claude will:
1. Re-invoke the saved workflow (script persisted under the session's `workflows/scripts/`, or re-author
   from `FORGE_PLAN.md` + this runbook), passing the **avoid-list** below so it ADDS rather than repeats.
2. Re-ground first (markets/venues shift): re-probe Polymarket + Kalshi liquidity (entries 02, 05 method),
   note what changed (new liquid Kalshi series, new event categories, leaderboard turnover).
3. Adversarially vet the new candidates, append survivors to `reports/strategies/CATALOG.md` (date-stamped
   section), refresh `catalog-<date>.json`, and implement any new param-only quick-wins into the portfolio.
4. Write a new dated entry summarizing the delta.

## Avoid-list (already cataloged — generate NEW angles beyond these)
Portfolio strategies live: `strict, loose, fresh2h, longshot, favorite, sports_only, nonsports,
elite_gated, whales, count, tight_cluster, elite_fresh_fav, favorite_tail, _blind`.
Catalog families already mined: polymarket-consensus-refinements, polymarket-new-mechanisms,
cross-venue-arb-divergence, kalshi-orderflow-microstructure, kalshi-smartmoney-scraped,
bot-infra-improvements, risk-portfolio-meta. Infra backlog (build, don't re-propose): blind-band-benchmark
(DONE), cluster-robust-dedup (partial: distinct-events done), belief-blind-promotion-gate, correlation-
effective-N, atom-replay-cli, clv-capture-overlay, cross-venue resolution-truth + depth-confirmed-dutch.

## Standing disciplines the regeneration must keep (from the catalog)
- Favorite-longshot bias is the universal confound → every edge judged on **surplus-over-blind**, not raw edge.
- Multiple-comparisons / optional-stopping across many variants → FDR + always-valid sequences + **distinct-EVENT N floor**.
- Score at **executable bid/ask** net of fees, never mid (phantom-edge generator on thin books).
- Many edges are **indeterminate-by-power** → pre-register, forward-track silently, **never auto-promote** to alerting.

## Lighter cloud cadence (optional)
A weekly cloud routine can do self-contained idea SCOUTING (web research on venue/market changes + new
edge literature) and deliver a short brief, since cloud routines can't see the local repo. The heavy
foundry re-run + implementation stays local. See the scheduled routine if configured.
