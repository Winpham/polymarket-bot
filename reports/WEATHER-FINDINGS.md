# Weather Edge Refinement — findings log

Give the daily-weather cell the same rigorous, belief-blind treatment the champion `favorite`
0.71–0.98 got (which lands ~+8% point / +5.6% honest LB). Both "confirmable edge, refine + accrue
forward" and "forecast-co-reading / power artifact, do NOT enable" are success. Paper-only.

Data reality (the binding constraint): weather has **14 calendar days** of data, all summer; the
resolved wider-universe convergence set is **7 independent day-clusters**. Weather has **zero**
captured executable ask / tape in history, so the copyable ASK spread stays the FORWARD unknown; the
shadow arm exists to capture it. The at-fire CLOB mid IS present on the full weather-favorite
population, so the realizable-PROXY basis (the champion's basis) is measurable now.

---

## Phase 1–2 — map + edge (`WEATHER-MAP.json`, `WEATHER-EDGE.json`)

**Clustering.** The honest independent unit is the resolution **DAY**, not the city-market:
same-day temperature is correlated (a heat dome resolves ~20 cities "hot favorite" together). Note
day-clustering is *conservative* — it also lumps weather-independent global cities (NYC vs Tokyo) into
one cluster, so the true independent-N is between 7 (day) and ~50 (city-day); the day-clustered LB is a
conservative floor.

**Edge (day-clustered, at-fire mid = realizable proxy):**

| cell | point | LB | boot LB | skill/blind | days | verdict |
|---|---|---|---|---|---|---|
| **WEATHER 0.71–0.98** | +7.9% | **+2.9%** | +4.6% | **+5.4%** | 7 | positive, INDETERMINATE (power) |
| — at sharp fill (directional) | +7.9% | +5.7% | +6.0% | +5.4% | 7 | copyability haircut ≈ +0.001 |
| band 0.71–0.82 | +15.4% | +2.6% | +5.1% | +4.7% | 5 | mid-fav, positive |
| band **0.82–0.90** | +12.3% | **+11.1%** | +11.1% | +6.9% | 6 | STRONGEST band |
| band 0.90–0.98 | +0.9% | **−2.1%** | −1.9% | +2.8% | 7 | deep chalk DEAD (win-rate trap) — 224/433 picks |

**Reads.**
1. **The edge is real on the copyable basis and survives the copyability test:** at-fire mid point
   +7.9% ≈ sharp fill +7.9% (haircut +0.001), so a follower buying the CLOB mid ~10–15 min after
   convergence captures essentially the sharps' edge. The executable-ask spread is the only remaining
   realizable unknown → the forward arm.
2. **It is diffuse, not a one-city/one-wallet artifact:** 49 distinct cities, top-city share **4.6%**,
   top-first-backer share ~5%. This is the opposite of tennis (one Wimbledon week) — breadth is a point
   *in weather's favor*.
3. **Same band mechanism as the champion:** the edge concentrates in mid-favorites (0.71–0.90); the
   **0.90–0.98 deep-chalk band is dead (LB −2.1%)** — the win-rate trap, and it is the *majority* of
   picks (224/433), dragging the pooled LB down. A-priori mechanism (deep chalk is efficiently priced,
   earns ~0/$) ⇒ a legitimate candidate refinement: **weather_fav → 0.71–0.90**, not 0.71–0.98.
4. **Binding constraint: 7 day-clusters, all summer.** Every cell reads INDETERMINATE on the 20-cluster
   volume floor. The day-clustered LB (+2.9%) is honestly far below the point (+7.9%) — the cluster-robust
   bound discounting the 7-day fragility. This is promising-but-power-limited, exactly weather's evergreen
   strength: it accrues day-clusters daily forward.

Phase 3 stresses this with the battery — LODO-by-week, selection_null (the forecast-co-reading + easy-day
traps), Bonferroni — to decide if the +5.4% skill is real signal or a 7-day artifact, and whether the
0.71–0.90 refinement holds.

---

## Phase 3 — anti-overfit battery (`WEATHER-VERDICT.json`)

| candidate | LB | Bonf | selection_null p | champ-corr | LODO-by-week | battery |
|---|---|---|---|---|---|---|
| WEATHER 0.71–0.98 | +2.9% | +0.8% | **0.0125** (fail) | −0.02 | IMPOSSIBLE | fails null |
| **WEATHER 0.71–0.90 (refined)** | **+9.2%** | +7.2% | **0.0065** (pass) | **−0.48** | IMPOSSIBLE | passes all *except power* |

**The decisive test — forecast-co-reading (`selection_null`).** Weather is forecastable public info, so
the real question is whether the consensus SELECTION beats a random weather favorite at the same
(band × day). The **refined 0.71–0.90 cell passes (p=0.0065)** — in the mid-favorite band the sharps'
selection is genuinely informative, NOT just several bots co-reading NOAA. The pooled 0.71–0.98 cell
**fails (p=0.0125)** because the dead 0.90–0.98 deep-chalk band (efficient, no selection skill) dilutes
it. This vindicates the a-priori 0.71–0.90 refinement: drop the band where deep chalk earns ~0/$ and
adds no selection skill.

**The refined cell also looks like a genuine COMPLEMENT to the champion:** day-level return correlation
**−0.48** (weather resolves independently of summer sports), copyability haircut ≈0, diffuse across 49
cities. On paper it is exactly what the generalize-band run went looking for and did NOT find in
sports — a positively-EV, low-correlated, copyable cell.

**THE FATAL CAVEAT (why this certifies nothing yet): it is ONE calendar week.** The 7 day-clusters are
**july 2–8 consecutive** (w26=6 days, w27=1). So:
- **LODO-by-week is IMPOSSIBLE** — there is no second disjoint week to leave out.
- **Consecutive days share weather regimes** (a stable high-pressure system spans days), so the effective
  independent-N is well below 7 — the day-clustered LB is itself optimistic here.
- This is the **tennis-one-Wimbledon-week trap by data availability**, not by choice. Every positive
  number above is one week of early-July weather; it could be a single favorable regime.

**Phase-3 verdict:** the weather 0.71–0.90 cell is the most promising complement candidate the whole
investigation has surfaced — positive on the copyable basis, passes the forecast-co-reading test,
low-correlated with the champion — **but it is confined to a single week and therefore INDETERMINATE and
uncertifiable in-sample.** The ONLY way to resolve it is forward accrual of disjoint weeks. Enable the
arm to accrue; promote nothing; require ≥2 disjoint weeks + forward selection_null + a real LODO-by-week
before any human promotion review.

---

## Phase 4 — verdict + arm decision + forward gate

**Arm decision: KEEP the capture band broad at 0.71–0.98; CERTIFY narrow at 0.71–0.90.** The arm's job
is to capture — capturing the (in-sample dead) 0.90–0.98 deep-chalk band forward is free data that
confirms whether it's really dead, so narrowing the arm now would discard information on one week of
evidence. The prereg makes **0.71–0.90 the primary certification cell** (a-priori mechanism: deep chalk
earns ~0/$ and adds no selection skill) with 0.90–0.98 tracked separately. **No arm code changed in
phase 4** — `weather_fav`/`weather_fav_liq` stay at 0.71–0.98, incumbents byte-identical.

**Forward instruments built** (`weather_scan.py`, `weather_verdict.py`, both `--selftest` green): the
gate is re-run with one command as weeks accrue — no new tooling to certify.

**Prereg updated** with the two in-sample lessons: primary cell 0.71–0.90, and a hard **≥2-disjoint-weeks
floor** (θ reads INDETERMINATE—SINGLE-WINDOW until a second qualifying week exists).

### Bottom line

Weather is the **strongest complement candidate the entire investigation has produced** — and the honest
verdict is *promising but uncertifiable in-sample, resolve it forward.* On the copyable at-fire-mid
basis (haircut ≈0), day-clustered, the mid-favorite cell **weather_fav 0.71–0.90** shows a **+9.2% LB**,
**passes the forecast-co-reading `selection_null` (p=0.0065)** — so it is real selection skill, not
several bots co-reading NOAA — is **diffuse across 49 cities** (not a one-city artifact), and is
**low-correlated with the champion (−0.48)**, exactly the positively-EV, copyable, diversifying cell the
generalize-band run went looking for and did NOT find in sports. **But every one of those numbers is a
single consecutive week (july 2–8)**, so leave-one-week-out is impossible and it could be one favorable
early-July regime — the tennis-one-Wimbledon trap by data availability. It therefore certifies nothing:
it clears everything the in-sample data CAN test and fails only the one thing it structurally cannot
(disjoint-week robustness). The right action is precisely the default-off arm already built: **enable it
to accrue disjoint weeks** (weather's evergreen daily flow means a real leave-one-week-out verdict in
2–4 weeks, not a season), certify forward against the frozen gate (≥2 disjoint weeks + selection_null +
LODO), and bring a human promotion decision only if the lower bound holds across weeks. Unlike the
summer sports, weather can actually *answer* the transfer question — that is its whole value.

---

## Phase 5 — refinement: date-gap forensics + region-clustering bracket

**Why the in-sample window is july 2–8 (two distinct causes, neither "missing data"):**
1. **Starts 07-02:** weather *consensus* (≥3 wider-universe backers on one favorite bucket) did not
   exist before july-2 — the tracked traders had not begun converging on weather. Real, not an artifact.
2. **Caps at 07-07:** **resolution-capture lag.** july 8–13 already have 600+ *converged* picks
   (111–153/day) but ~0 marked resolved in our DB (july 9–13 = 0 resolved). The sharps have bet and the
   markets have (near-)resolved on Polymarket; housekeeping just hasn't captured the outcomes yet.
   **july 8–13 is a second calendar week (w27–w28)** — the moment it resolves, weather crosses from one
   window to TWO disjoint weeks and **LODO-by-week becomes possible.** Days away, not weeks.

**Region-clustering bracket (honest independent-N).** Pure-day clustering (7) is over-conservative —
it lumps independent continents (a Tokyo heat wave ≠ an NYC one). Clustering by (synoptic-region × day)
recovers spatial independence (11 regions, 0 unmapped):

| cell | day-clustered LB (G) | region-day LB (G) |
|---|---|---|
| full 0.71–0.98 | +2.9% (7) | +4.6% (45) |
| **refined 0.71–0.90** | **+9.2% (6)** | **+8.8% (36)** |

The refined cell's LB is **robust to the clustering choice (+8.8% to +9.2%)** — so it is NOT a
spatial-correlation artifact — and at region-day granularity it **clears the 20-cluster volume floor
(36 clusters).** The temporal caveat is unchanged: all clusters are within one week, so LODO-by-week is
still impossible. Net: the refinement removes the *volume* doubt and the *spatial-artifact* doubt; only
the *single-week* doubt remains, and that resolves itself as july 8–13 (already converged) finish
resolving. This is the strongest the in-sample case can honestly get before the second week lands.
