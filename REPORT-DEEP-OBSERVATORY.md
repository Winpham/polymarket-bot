# Deep-pool observatory — verification + cohort-filterable tracking (run report)

Follow-on to the top-200 widening. Two halves: **(A)** verify the deployed widening works
exactly as intended, and **(B)** extend the per-trader verification stack to the whole tracked
universe as a first-class, filterable **rank-cohort** dimension — clearly labeled so trusted
top-50 is never confused with experimental candidates. Additive, read-only, no schema,
cost-zero, paper-only.

## A. Verification of the live deployment (all green)
Read-only checks against the **production** DB ~1h post-deploy:

| Check | Result |
|---|---|
| Eligibility = rank ≤ 40 | 56 eligible (1–40) / 218 deep (41–200) · **0 violations** |
| Deep capture accruing | 187 deep wallets · **32,348 fills / 24h** |
| Deep leak into signals | 7,800 backer slots, rank **1–40 only** · **0 leaks** |
| Consensus still healthy | 4,131 signals · 63 alerts / 24h |
| Deep resolution live | 24,610 resolved fills · 150 wallets · **50 already ≥10 events** |
| Cadence | steady-state poll ~34s (of 120s) · **0 429s** |

**Conclusion:** the deep pool is fully captured, resolved, and profiled — everything the top-50
gets — while the voter set stays top-40 and **not one deep trader has entered a signal or
alert** (byte-for-byte non-regression, proven live). The efficiency verdict is still maturing
(the trust gate wants ≥30 resolved events; 50 wallets already ≥10). Full report:
`VERIFY-DEEP-LEADERBOARD.md`.

## B. The cohort-filterable observatory
The user's steer: *"label it well and structure it so it can be called/filtered easily — top-50
only, all top-500, top-250 only, or the most profitable within each group of 50 — whatever is
most future-proof and practical."* So rank-cohort is now a **first-class, filterable
dimension**, not a rigid hot/deep binary — and it needs **no schema** (bands derive from the
`rank` already stored).

- **`scanner::cohort`** (pure, unit-tested): `Band` model + `parse_bands` (config
  `TRACK_COHORT_BANDS`, default `40,100,250,500` → bands `1-40` *trusted* / `41-100` /
  `101-250` / `251-500` / `501+`) + `CohortFilter` (`trusted` / `top-N` / `band-i` / `all`) +
  `band_of`. The first band is trusted (= the consensus cutoff, 40); everything deeper is a
  candidate cohort.
- **Board "Deep-pool observatory"** (`render_cohort`): the **same belief-blind `trust_verdict`
  analytics** as the trusted top-50 table (no new gate) assembled across every band, **grouped
  by band**, **"most-profitable-within-band" ranked**, with per-trader N / surplus / bound /
  verdict / capture-health. Sliceable **by URL**:
  `/?cohort=trusted|top250|band2|all&sort=profit|rank` — filter chips + a sort toggle render
  inline; the auto-refresh preserves the query.
- **Segregation (the anti-noise guardrail):** a standing **EXPERIMENTAL** banner + per-band
  `⚠ candidate` tags for everything past the trusted top-40; the section **never alerts**; a
  ✅ candidate is a *lead* to promote by a deliberate human flip, never automatic. The trusted
  top-50 "Trader trust" table above is **untouched** (no regression) — the observatory is a
  strictly additive second surface.

## How to use it
- `http://localhost:9002/` — trusted table (top-50) as before, then the observatory below it.
- `…/?cohort=trusted` → top-40 only · `?cohort=top250` → rank ≤ 250 · `?cohort=band3` → one
  50-group · `?cohort=all` (default) → every band · `&sort=profit` (default) ranks most
  profitable first within each band; `&sort=rank` orders by leaderboard rank.
- Change the bands without a rebuild-of-meaning: set `TRACK_COHORT_BANDS` in `.env.consensus`
  (e.g. `50,100,150,...` for pure 50-groups). Keep the first bound = the consensus cutoff.

## Verification of the extension
Pure unit tests (`parse_bands`, robustness, `band_of`, `CohortFilter`, `parse_cohort_query`) +
a live board-render test on a throwaway PG: a rank-120 Trusted trader surfaces in the `101-250`
band, labeled experimental, under the same gate. Gate green through a clean merge with the
concurrently-landed winners/dense-capture work (80/88/73 tests pass).

## Production config (all default = today's behavior)
| flag | default | effect |
|---|---|---|
| `TRACK_DEPTH` | 40 (prod: **200**) | capture depth |
| `TRACK_CONSENSUS_RANK_CUTOFF` | 40 | who votes (unchanged) |
| `TRACK_COHORT_BANDS` | `40,100,250,500` | observatory bands (display/filter only) |

The observatory is pure read-only display — deploying it cannot regress the live signal.
