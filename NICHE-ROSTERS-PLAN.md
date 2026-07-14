# Per-Niche Trader Rosters — find the top 50–100 of EACH space, not the top-1000 of ALL

**Run date:** 2026-07-14 · branch `feat/niche-rosters` · paper/analysis-only, no live path touched.

## The problem, stated precisely

Every wallet we have ever known (3,085 of them) came from the Polymarket leaderboard, which
sorts by **absolute PnL** — a bankroll-and-volume sort, not a skill sort. Measured on our own
pool: `corr(rank, ROI) = −0.05`. So our "trader universe" is really a *whale* universe, and the
niches it covers are just the niches whales happen to have volume in.

The scale of what that hides, measured live this run:

| | |
|---|---|
| distinct wallets in our entire DB | **3,085** |
| distinct wallets in ONE median esports market | **447** |
| distinct wallets in ONE median weather market | **170** |

A single market contains a meaningful fraction of our whole universe. We are not sampling
niches; we are sampling whales.

## The inversion (mechanism, verified live this run)

`/trades?market=<condition_id>` enumerates **every participant** in a market. Cost is
**O(markets), not O(wallets)**. Verified against the live API today:

- `limit=1000` is honored (the *leaderboard's* 50-cap does NOT apply here) → 10× cheaper.
- **`offset` hard-caps at 3000** ⇒ max ~4000 trades/market, newest-first.
- **Every time-window param is silently IGNORED** — `before`, `after`, `startTs`, `endTs`, and
  even an invented `bogusParamXYZ` all return the byte-identical page. There is **no time-slicing
  escape** from the 4000 cap. (This reproduces the `startTs` burn that once cost 96.8% of history:
  this API returns 200 OK for params it ignores. Never trust an unverified filter param here.)
- **The cap does not bite in our niches:** 1 of 42 sampled markets hit it (a politics market).
  Median trades/market 12–996. So enumeration is 1–4 requests per market.

Resolutions do **not** need extra API calls: harvested fills join to our existing
`trader_fills` on `(condition_id, outcome_index) → outcome_won`.

## The trap this run must not fall into

Ranking traders by past surplus and taking the top-50 is **exactly the procedure this project has
already refuted five separate ways** (past-PnL ranking: ρ≈−0.04 to −0.06; per-cell specialization:
1000-perm null manufactured *more* "specialists" than we observed, p=0.79).

**Widening the pool from 3k to ~200k wallets makes a naive top-50 MORE contaminated, not less** —
with more candidates, the extreme order statistics under pure noise get more extreme. The prior
run's naive scan crowned a "+0.69 surplus/fill specialist" that had traded **2 markets**.

So the expansion is a **power lever, not a signal**. What it genuinely buys:
1. **Per-trader N within a niche** — a weather specialist with 43 weather markets was previously
   invisible; N is the binding constraint on any per-trader verdict.
2. **A measurable null** — with the full population we can compute how many "skilled-looking"
   traders pure noise manufactures in this exact niche.

## Pre-registered kill criteria (written BEFORE any result is seen)

- **K1 — Harvest fidelity.** Harvested market-side fills must reconcile with our own
  `trader_fills` for the same `(wallet, condition_id)`. If the two tapes disagree → **STOP**;
  the harvest is not measuring what we think.
- **K2 — PERSISTENCE (the make-or-break).** Rank wallets within a niche on window **A**, then
  measure those same wallets in disjoint later window **B**. If the A-top-50's B-surplus lower
  bound (market-clustered) is not > 0 **and** not > the niche's blind baseline → the roster is
  **not predictive** → report **NULL for that niche**. A roster that fails K2 is noise, and I
  will say so.
- **K3 — Permutation null.** Shuffle wallet labels within `(niche × price-band × market)` to
  preserve market and price structure. If the observed certified count ≤ p95 of the null's
  certified count → **NULL** (max-of-noise).
- **K4 — Copyability.** Edge must survive at **OUR** price net of the follower tax
  (`max(measured_tax, 1.3¢)`). Uncopyable profit (market-making / spread capture) is excluded via
  the churn classifier (churn ≥ 0.70 = MM). A niche whose top wallets are all MMs is a
  *publishable finding*, not a roster.
- **K5 — N-floor on independent clusters.** Minimum distinct **resolved markets** per wallet per
  niche. Small-N artifacts (the "+0.69 on 2 markets") must be *structurally impossible*, not
  filtered after the fact. Cluster at the MARKET, never the fill.

Multiple testing across the wallet × niche family: **BH-FDR q = 0.10**.

## Safety (discovery must never become trust)

Harvested wallets are written to a **separate `harvest_fills` table**, not `trader_fills`.
This is deliberate: memory records that `consensus_eligible` **DEFAULTS TRUE** (a naive insert
would hand thousands of strangers a vote in the live consensus engine), and `active=TRUE` would
drag them into the per-cycle wallet poll (~167 req/s — 4× the API ceiling). Writing to a table
the live path does not read makes that entire class of landmine *structurally impossible* rather
than merely avoided.

No migration on live tables. No env flip. No real money.

## Honest expected outcome

The most likely result, given five prior refutations, is that **most niches certify ZERO** real
specialists. That is a legitimate and valuable outcome: it would mean the niche rosters are
rank-orderings of noise, and it would close off "specialize by space" the same way past-PnL
ranking was closed off. The run is designed so that outcome is *reportable*, not hidden.

The result that would be genuinely new: a niche where the hidden (harvest-only) population
contains persistent, copyable edge that the leaderboard structurally could not see. Memory's
weather probe hints at this (hidden pop: 36% positive vs 15% tracked; p90 +4.2%) — but that was
an ungated scan, and the gate is exactly what killed every previous hint.
