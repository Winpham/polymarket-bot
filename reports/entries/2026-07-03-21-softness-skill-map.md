# Softness × Skill map — steer the edge to the soft pockets, sports and beyond (2026-07-03, entry 21)

Branch `feat/softness-skill-map` (worktree off `main` 643886e, tag `pre-softness-skill-map-20260703`).
Follow-up to the per-sport tracker (entry 15): the favorite edge is real but lives in the **soft
pockets** of the book and **bleeds in the sharp ones**. This run builds the `category × market-type ×
band` map that separates three numbers per cell — **softness** (opportunity size), **skill** (the
edge), **realizable ROI** (the bankable number) — and never conflates them. It steers the *same*
generic edge; it invents no new signal. Paper-only, gate-judged, nothing changed live.

## The ugly cells first (kill criteria honored)

- **0 PRIORITIZE cells. 0 FDR survivors** across the 5-cell testable skill family (min p = 0.052,
  soccer/deriv/0.80–0.90). Skill is **INDETERMINATE-by-power**, not refuted — exactly the D16
  accrual wall: ~5 correlated summer days (World Cup + Wimbledon) cannot certify at any clustering.
  The map orders nothing to bet today. That is the honest headline.
- **The one DODGE that certifies is on softness, not skill:** `mlb / deriv / 0.60–0.80` softness
  **−10.5%** (95% CI upper bound **−0.5%** < 0, on 121 blind favorites). Low-band MLB derivatives
  (near-tossup totals) are sharp enough that the base rate bleeds past the ~3% capture cost — DODGE,
  and it needed *only the blind pool* to say so (the softness-needs-less-data thesis, working).
- **K2 downgrades fire as designed** — soft is not bankable:
  - `soccer / deriv / 0.80–0.90`: softness **+9.3%** (reliably soft) but the consensus skill there is
    realizable-ROI LB **−7.0%** → **NEUTRAL**, not PRIORITIZE. A soft market we cannot yet harvest.
  - `tennis / main / 0.60–0.80`: softness +0.8% but roi_lb −11.4% → **NEUTRAL**.
- **The retrospective overlay lift is NEGATIVE (−0.8%)** and this is a *feature*: the DODGE cell's 4
  actual consensus fires happened to *win* (+42.7% realized on N=4), so dropping them looked costly
  in-sample. The map is pre-registered on the **reliable large-sample softness**, not on 4 favorable
  fires — which is precisely why the overlay is judged **forward-only** (K3). Forward lift today =
  **INDETERMINATE** (0 events after the map's effective time); the overlay orders nothing yet.

## The instruments (all self-testing)

- **`scripts/market_taxonomy.py`** — `category(slug,title)` extends `sport()` to **politics/elections,
  esports, econ/other** via two documented layers (structured slug-prefix; unstructured → title
  keywords), with explicit traps: `co-`=Call of Duty (not Colorado), `world-`=WC props (soccer),
  `spx`/`highest`=econ (not crypto), `hype`=crypto. `market_type` = main|deriv (crypto/index
  up-or-down = headline **main**; handicap/total/score = **deriv**). Self-test PASS: 27/27 category,
  16/16 mtype, null discipline (ambiguous → `(other, None)`), all 5 traps, slice_study parity.
- **`scripts/softness_map.py`** — the map. Everything event-clustered at the match super-key, at-fire
  entry, matched **(category × 5-band)** blind baseline (composition-trap-safe), BH-FDR q=0.10.
  Self-test PASS (K1): injected soft+skilled cell → PRIORITIZE, sharp cell → DODGE, pure noise → 0
  FDR survivors.
- **`scripts/seed_softness_map.py`** — expresses the combined map as a **new dimension `catmix`** in
  the existing `map_state.py` versioned store (**v002**, effective 2026-07-03T18:00Z), via a
  verdict-preserving crosswalk through the frozen `step()`; v001 (entry-10 slice map) carried
  unchanged. NOT a parallel store.
- **`scripts/overlay_lift.py`** — the silent virtual overlay (base favorite − DODGE cells), forward-
  only paired lift (K3), + a per-cell watch-list with re-read triggers.

## Coverage: where the consensus can even be measured (the non-sports verdict)

`market_taxonomy.py` over the whole book (resolved), with `favorite` fire counts:

| category | resolved | blind favs | **FIRES** | verdict |
|---|---:|---:|---:|---|
| soccer | 6724 | 1397 | **174** | measurable |
| tennis | 2750 | 568 | **52** | measurable |
| mlb | 1961 | 202 | 13 | data-starved (< 20) |
| esports | 724 | 196 | 9 | data-starved |
| nba/cbb | 176 | 33 | 3 | data-starved |
| **politics/elections** | 107 | 92 | 2 | data-starved (3 days only) |
| crypto | 3736 | 808 | **0** | **NEVER FIRES (K4 — observation)** |
| other | 552 | 885 | **0** | **NEVER FIRES (K4)** |
| econ/other | 546 | 266 | **0** | **NEVER FIRES (K4)** |
| nhl / nfl-cfb | 15 / 5 | 7 / 0 | 0 | never fires (off-season / thin) |

- **Only soccer and tennis fire the consensus enough to measure skill.** Everything else is
  data-starved or never-fires. This is the binding reality for the whole "steer beyond sports" thesis:
  the *softness* is measurable widely; the *skill* is not, yet.
- **Crypto (808 blind favorites, softness ≈ +0.9%) NEVER fires the consensus** — sharps never agree
  one-sided on up/down, so it is a softness *observation*, not a steerable arm (K4). Same for the
  unclassified "other" (885 blind favs) and econ/culture. No Bonferroni slot spent on them.
- **Politics/elections** has 92 blind favorites but only **3 days** of data and fires the consensus
  **twice** — a *year-round soft frontier* that is data-starved now and ramps toward the Nov-2026
  midterms. It is the most interesting non-sports watch cell, not a today-arm.

## The softness map (blind favorites, pooled bands; reconciles with entry 15 within noise)

| category × market-type | softness | 95% CI | read |
|---|---:|---|---|
| nhl / main | +19.2% | [+11.0,+27.8] | ★soft but N=5 (thin, off-season) |
| esports / deriv | **+9.0%** | [−2.3,+19.1] | **softest well-populated non-summer cell** |
| soccer / main | +7.6% | [−3.1,+17.9] | soft (band 0.60–0.80 carries it: +21.3%) |
| soccer / deriv | +5.2% | [−2.2,+12.5] | soft (WC casual-money props) ≈ entry-15 +3.3% |
| mlb / main | +4.5% | [−11.9,+19.9] | ~fair |
| esports / main | +3.5% | [−5.5,+11.3] | mildly soft |
| tennis / main | +3.2% | [−0.6,+7.2] | ≈ entry-15 +2.7% ✓ |
| crypto / main | +0.9% | [−1.6,+3.5] | ~fair — **and never fires** |
| tennis / deriv (handicaps) | **−5.3%** | [−17.3,+6.0] | sharp (≈ entry-15 −9.0%) |
| mlb / deriv (props) | **−7.7%** | [−15.4,+0.4] | sharp (≈ entry-15 −5.1%) |
| nba/cbb / main | −8.7% | [−27.0,+7.6] | sharp-leaning (thin) |
| politics / main | −9.4% | (n<5) | thin/longshot-heavy |

Reconciliation with the per-sport tracker (entry 15) is within sampling noise on same-sign,
same-magnitude cells (tennis moneyline, tennis handicaps, mlb props, soccer props) — the map is the
tracker, refined to `category × market-type × band` and extended past sports.

**Two genuinely new findings:** (1) **esports is a soft venue** (deriv +9.0%, main +3.5%) and it
*does* fire the consensus a little (9 fires) — the top non-summer harvest frontier to watch.
(2) **MLB-derivative sharpness is concentrated in the low band** (0.60–0.80 = −10.5%, DODGE), while
*heavy-favorite* MLB totals (0.90–1.00) are mildly **soft** (+4.6%) — the sport-level −5.1% hid both.

## What binds (and what does not)

- **DODGE `mlb / deriv / 0.60–0.80`** — sharp on the base rate; do not concentrate favorite-following
  there. (The broader "MLB/tennis derivatives are sharp" intuition holds directionally but only this
  low-band cell certifies as reliably sharp today.)
- **Nothing is PRIORITIZED.** Soccer and tennis are the only skilled candidates and neither clears
  the cost margin with FDR control on this data (INDETERMINATE-by-power, not refuted).
- **The steering is a forward hypothesis, not a certified bet.** Cells test vs the matched blind
  baseline, not vs a parent; the map is an *ordering* of where to look, governed by `map_state`'s
  ENTER-on-record / EXIT-on-recent state machine (v002).

## Watch-list (re-read triggers)

`tennis/main/0.80–0.90` (soft +9.5%, N=18/20 — **re-read at +2 fires**), `soccer/main/0.60–0.80`
(soft +21.3%, N=8/20), `esports/deriv/0.60–0.80` (soft +11.5%, N=5/20), `esports/main/0.60–0.80`
(soft +4.9%, silent — watch to harvest when it fires), `mlb/deriv/0.90–1.00` (soft +4.6%, silent),
plus the fall sports (NFL Sept / NBA Oct) and **politics → Nov-2026** as they come into season.
Trigger per cell: skill N crossing 20 fires / +7 days / the category coming into season.

## Live behavior

Unchanged. No migration, no Rust, no env flip, no alert change. New files are analysis scripts +
two JSON artifacts (`reports/softness_map.json`, `reports/map/v002.json` + manifest). Rollback =
git-revert the merge.
