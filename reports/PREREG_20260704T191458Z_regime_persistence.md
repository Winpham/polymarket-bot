# PRE-REGISTRATION — Regime Persistence & Net-Edge

**Frozen:** 2026-07-04T19:14:58Z (UTC). **Branch:** `feat/regime-persistence`. **Paper-only, read-only.**

This file is the honesty anchor for the run. Every downstream instrument
(`regime_classify.py`, `regime_edge.py`, `regime_persistence.py`, `regime_net_edge.py`, and the
`readiness_ledger.py` extension) **cites this file** and reads its constants from the frozen values
below (or hard-codes the identical value with a comment pointing back here). **No later item may
introduce a threshold not in this file.** If a later item needs a different constant, it FAILS —
re-register in a NEW stamped `PREREG_<ts>_*.md` and state why.

The one-paragraph purpose: time-diversification (flat-shares + 13%/day deploy cap) already solves
statistical *power*. It does **not** solve *stationarity*. Today's ~+5% favorite edge is
soccer-carried and World-Cup-heavy — an **expiring** regime. A precise estimate of a disappearing
edge is worthless. This run decomposes the edge PER REGIME, tests whether it REPEATS out-of-sample
in DISJOINT **recurring** regimes (beating a matched null), nets it against the copyability tax per
regime, and makes it legible on the readiness board. It promotes nothing and touches no real money.

---

## 1. Regime taxonomy

A **regime** is `regime_i = (sport_category, time_block)`.

- **`sport_category`** — taken from the EXISTING derivation `market_taxonomy.category(slug, title)`
  (do NOT invent a new sport bucket). Labels it can emit: `tennis`, `soccer`, `mlb`, `nfl/cfb`,
  `nba/cbb`, `nhl`, `esports`, `crypto`, `politics/elections`, `econ/other`, `other`.
- **`time_block`** — the **calendar month** (`YYYY-MM`) of the signal's `first_detected_at` at UTC.
  The month is the **disjoint-cluster unit** for the cross-regime bar: two reads of the same sport in
  the same contiguous span are NOT independent regimes; two reads a month apart begin to be.
- **Full regime id** string: `f"{sport_category}|{YYYY-MM}"` (composed in `regime_edge` /
  `regime_persistence`; `regime_classify` returns the `sport_category`-level id + its type).

## 2. Regime-TYPE classifier (the crux) — deterministic, frozen

`classify_regime(sport, market_type, slug, title) -> (regime_id, regime_type)`,
`regime_type ∈ {recurring, expiring, unknown}`. `unknown` is treated as **expiring** for the
conservative verdict. Rules are applied **in order**; first match wins. All matching is on the
lower-cased `slug + " " + title` unless stated. Err toward `expiring` when ambiguous.

**Rule E (EXPIRING keywords — highest priority).** If the text matches any bounded-event marker →
`expiring`:
`world-cup`, `worldcup`, `world cup`, `fifwc`, `-wc-`, `wimbledon`, `roland`, `us open`, `usopen`,
`australian open`, `ausopen`, `french open`, `grand slam`, `-slam`, `olympic`, `playoff`,
`play-off`, `postseason`, `knockout`, `elimination`, `round-of`, `round of`, `-final`, `semifinal`,
`semi-final`, `quarterfinal`, `quarter-final`, `-cup`, `championship`, `worlds`, `-msi-`, `major`,
`super bowl`, `superbowl`, `world series`, `grand final`, `finals`.
(`fifwc` = FIFA World Cup; the whole soccer book on this record is the World Cup → expiring.)

**Rule R (RECURRING categories / league prefixes).** Else, if NOT flagged by Rule E AND the
`sport_category` is an ongoing/regular-season venue → `recurring`:
- category ∈ {`mlb`, `nba/cbb`, `nfl/cfb`, `nhl`, `crypto`, `econ/other`, `politics/elections`}
  (regular-season league play that recurs indefinitely, or ongoing markets), **and**
- regular-league soccer slug prefixes (when they occur without a Rule-E marker):
  `epl`, `mls`, `laliga`, `seriea`, `bund`, `ligue`, `erediv`, `mar1`, `bra2`, `kbo`, `npb`.

**Rule U (UNKNOWN → treated expiring).** Else → `unknown`. This deliberately captures:
- **`tennis`** (`atp`/`wta`/`itf`): the tour recurs year-round, but grand slams are bounded and the
  machine slugs (`atp-<player>-<player>-<date>`) carry **no tournament name**, so we CANNOT confirm
  this is non-slam regular play from the slug. This record is the **Wimbledon** fortnight (bounded).
  Conservative + correct-for-this-record → `unknown` (treated expiring). Overridable by a human if a
  future slug carries a tour-level marker.
- **`esports`** (`lol`/`cs2`/`co-`/…): leagues recur but majors/worlds are bounded; slug carries no
  league/tournament marker → `unknown`.
- **`other`** and anything unclassifiable → `unknown`.

**Anti-deception note.** A `recurring` label is a claim that the regime REPEATS. It is the *only*
label that can count toward certification. Mislabeling an expiring regime as recurring would smuggle
a soccer artifact into a "persists" verdict — the exact failure this run exists to prevent. When in
doubt, `unknown`.

## 3. Edge metric per regime (frozen)

For each arm × regime:
- **event unit** — the match super-key `superkey.super_event(event_slug, slug)` (falls back to
  `condition_id`), so sub-markets of one game collapse to one event (matches
  `softness_map`/`persistence_tracker` convention).
- **baseline** — the MATCHED `(sport_category × 5-price-band)` blind-favorite baseline, built
  byte-identically to `softness_map.py` (blind pool, `won − entry` averaged per `(category, band)`
  cell). NEVER a 0-baseline and NEVER a global-blind baseline (composition trap → the `market_resid`
  false-promote class).
- **surplus** — event-clustered mean of `(won − entry) − baseline` over the arm's resolved picks.
- **entry / cost** — surplus is measured at the AT-FIRE entry (`COALESCE(initial_mean_price,
  mean_price)`); the copyability tax is applied in Item 4 (`regime_net_edge`), not here (Item 2 is
  gross surplus over the matched baseline; net is Item 4).
- **sizing** — flat-SHARES only, never flat-$ (flat-$ flips the favorite-edge sign; D-record).
- **cluster-robust LB** — one-sided 95% lower bound from `effective_n.cluster_robust` (CR1 SE),
  clustered by **UTC day**, `LB = surplus − 1.96 · se_CR`. The **independent-cluster COUNT** (`G`)
  is the honest N — raw signal count is NEVER the N.

**Arms in scope:** `favorite` (primary, 275 resolved) and `proven_router` (the second live paper
arm; currently 0 resolved → its regimes read as empty/PENDING, reported honestly, not hidden).

## 4. The persistence bar (frozen) — BOTH legs required, verdict on RECURRING regimes only

**Leg (a) TEMPORAL.** Reuse `persistence_tracker.py`'s leak-free cutoff split and its FROZEN
constants (do NOT re-pick them): `PERSIST_MIN_CLUSTERS = 10`, `MARGIN = 0.03`, `Z = 1.96`. Read the
OUT-of-sample edge PER `regime_type`; the verdict uses **recurring-regime OUT clusters only**.
Persists (a) iff `LB(recurring OUT surplus) > MARGIN` on `≥ PERSIST_MIN_CLUSTERS` independent OUT
day-clusters.

**Leg (b) CROSS-REGIME TRANSFER.** Leave-one-regime-out over **recurring** regimes: fit "edge
exists" (matched-baseline surplus > 0) on all-but-one recurring regime; test `LB > MARGIN` on the
held-out recurring regime. Require `TRANSFER_MIN_REGIMES = 2` disjoint recurring regimes to hold
out successfully. Beat a **matched regime-permutation null**: permute the regime labels
`N_PERM_REGIME = 1000` times (seed `20260704`), recompute the transfer statistic (number of
held-out recurring regimes clearing the margin), and require the real transfer count to sit at
`p ≤ 0.05` in the null (one-sided: fraction of null draws ≥ real). Report the full null distribution.

## 5. Net-after-tax rule (frozen)

A regime is **`net_positive`** iff its tax-netted cluster-robust LB `> 0`.

- **Tax source (taker path)** — `reports/copyability.json`: per-band decision-time ask spread +
  `FOLLOWER_TAX = 0.013` + `FEE`. `net_taker(regime) = gross_surplus − band_spread(price) −
  FOLLOWER_TAX − FEE·price`, per row then event-clustered, byte-consistent with `copyability.py`'s
  `modeled_row` (which already folds spread + fee; we add the follower tax explicitly on top as the
  copy path's lag cost).
- **Maker path** — `reports/maker_fill_sim.json`, policy `maker_+0c_5m` (limit at δ=0¢ / 5-min): use
  its measured `adverse_selection_gap` as the maker execution adjustment vs the taker mid; report
  `net_maker` as a SECOND column. Maker also carries a fill-rate caveat (≈28% fill) surfaced, not
  hidden.
- **Fee basis** — `FEE = 0.02` is the buffer basis (`fee_2pct_buffer`); report a companion
  `fee = 0.00` column (`fee_zero`) for both taker and maker.

## 6. The overall verdict ladder (frozen)

Applied to the **recurring**-regime evidence (expiring regimes are reported but EXCLUDED from the
verdict):

1. **`SOCCER-ARTIFACT`** — the edge is concentrated in **expiring** regimes (top-1 expiring share
   high) AND the recurring-regime edge is INDETERMINATE or negative. (The honest expected read
   today.)
2. **`PENDING`** — recurring regimes exist but are below the cluster floor (`< PERSIST_MIN_CLUSTERS`
   independent OUT clusters, and/or `< TRANSFER_MIN_REGIMES` disjoint recurring regimes). This is the
   accrual wall; the instruments report how many more days/regimes are needed. (Also honest today.)
2b. `PENDING` and `SOCCER-ARTIFACT` can co-hold; when the recurring pool is thin AND the pooled edge
    is expiring-concentrated, report `SOCCER-ARTIFACT` as the headline with the PENDING accrual-ETA
    as the binding-constraint detail (this is the expected 2026-07-04 state).
3. **`PERSISTS-NET`** — BOTH persistence legs (a AND b) pass on recurring regimes AND
   `≥ TRANSFER_MIN_REGIMES` recurring regimes are `net_positive` after tax. (Will NOT read today.)
4. **`REFUTED`** — the recurring-regime OUT upper bound `< 0` (the edge decayed out of sample on
   recurring regimes).

**Win condition of this run:** a loud, correct `SOCCER-ARTIFACT` / `PENDING` with the exact
concentration number and the exact count of recurring regimes cleared vs the `≥2` bar and the ETA —
NOT a hedge. `PERSISTS-NET` today would be a red flag that something leaked.

## 7. Frozen constants (single source of truth)

| constant | value | source / meaning |
|---|---|---|
| `TIME_BLOCK` | calendar month `YYYY-MM` (UTC) | disjoint-cluster unit |
| `SPORT_CATEGORY` | `market_taxonomy.category(slug,title)` | existing derivation, not reinvented |
| `EVENT_KEY` | `superkey.super_event(event_slug, slug)` | match super-key |
| `BASELINE` | matched `(category × 5-band)` blind-favorite | `softness_map` convention |
| `BAND` | `selection_null.band` (width_bucket p,0,1,5) | 5 price bands |
| `Z` | `1.96` | one-sided 95% (mirrors `persistence_tracker.Z`) |
| `MARGIN` | `0.03` | capture margin (mirrors `persistence_tracker.MARGIN`) |
| `PERSIST_MIN_CLUSTERS` | `10` | temporal OUT floor (mirrors `persistence_tracker`) |
| `TRANSFER_MIN_REGIMES` | `2` | disjoint recurring regimes for leg (b) |
| `N_PERM_REGIME` | `1000` | regime-permutation null draws |
| `SEED` | `20260704` | all randomness this run |
| `FOLLOWER_TAX` | `0.013` | `copyability.py` (cited, not re-measured) |
| `FEE` | `0.02` (buffer); `0.00` (companion) | fee basis |
| `MAKER_POLICY` | `maker_+0c_5m` | `maker_fill_sim.json` (limit δ=0¢/5m) |
| `ARMS` | `favorite`, `proven_router` | the two live paper arms |
| `SIZING` | flat-SHARES | never flat-$ (D-record) |

**Standing guardrails:** `PILOT_ARMED` unset, `EARN_DEEP_SHARPS` false, alert path untouched, no
migration, never merge/rebase `main`. Every new file is additive (revert = delete).
