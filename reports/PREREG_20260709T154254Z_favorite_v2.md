# PRE-REGISTRATION — decoupled favorite shadow arms (frozen 2026-07-09T15:42:54Z)

**Frozen BEFORE any forward-outcome analysis** (no favorite_liq/favorite_v2 signal has accrued yet —
the arms are not deployed). Amended same-day (pre-forward-data) per Tue's critical review to
**decouple the trustworthy claim from the fraught one**. Both arms are SHADOW (`alerting=false`,
paper-only, promote nothing, arm nothing, real-money eligibility UNCHANGED).

## Two arms, decoupled ON PURPOSE
The headline lift decomposes into two very different claims; registering them separately lets the
forward gate rule on each instead of rank's story hiding behind liquidity's.

| arm | params on top of champion band (0.65–0.98) | claim | billing |
|---|---|---|---|
| **`favorite_liq`** | `min_total_usd = 1000` | cut thin/unfillable books | **TRUSTWORTHY** — small (~9% vol) cut, mechanism-clean, helps OOS |
| **`favorite_v2`** | `min_total_usd = 1000` + `require_backer_rank_lt = 5` | + only follow top-5 backers | **UNPROVEN + HISTORICALLY FRAUGHT** — see caveats |

## Honest decomposition (in-sample; corrected fee, turnover $100/bet) — NOT the gate
| | champion `favorite` | `favorite_liq` | `favorite_v2` |
|---|---|---|---|
| resolved ROI (taker) | +2.81% | **+4.17%** (~+1.4pp) | +9.66% (~+5.5pp more) |
| volume retained | 100% | **91%** | 61% (−39%) |
| OOS non-FIFWC | −2.08% | **−1.02%** | +7.63% |

**The +9.66% is rank-driven, not garbage-driven.** Liquidity alone earns +1.4pp keeping 91% of
volume; the rank gate adds the other ~+5.5pp but cuts 39% of volume — it is an "only follow top-5
leaderboard traders" strategy, not "cut illiquid junk."

### Why `favorite_v2`'s rank half is billed UNPROVEN (do not read +9.66% as validated)
1. **Re-opens a refuted axis.** Leaderboard-rank-as-skill was refuted 5 ways (identify-skilled memo);
   top traders are market-makers whose edge is uncopyable at our price. Confound checks (price/
   liquidity/sport flat across rank bins) are necessary but do NOT dissolve that history.
2. **Non-monotonic rank profile** (rank<5 +7.2%, 5–9 −8.3%, ≥10 −4%, **20–50 +27.7%**) — a small-N
   noise tell; boundary-at-5 may be a lucky cut, not a skill gradient.
3. **The non-FIFWC "flip" is tennis/Wimbledon-carried** (only tennis n=14 positive at support; mlb
   n=3, other n=7 below floor). Tennis is an EXPIRING tournament regime — the same soft-tournament
   trap as the World Cup, in a different jersey. It does NOT establish durability outside tournaments.
4. **Weighting ≠ excluding:** a full-volume rank TILT (no cut) recovers only part of the lift (+5.68%
   combined) and **does NOT reproduce the non-FIFWC flip** (stays −2.2%) — the durability appears only
   when you *remove* the few tennis-carried rank≥5 non-soccer bets, confirming it is selection, not a
   sizeable edge. (See POLICY-SEARCH-LOG "WEIGHT-NOT-CUT".)

## THE FORWARD GATE — evaluated SEPARATELY for each arm
Realizable metric (frozen): event-clustered resolved ROI-on-turnover at the corrected taker fee
(`0.03·p(1−p)`), on signals **first detected after 2026-07-09T15:42:54Z**; champion measured on the
same window. `selection_null.py --challenger <arm>` reused, not reimplemented.

For an arm to be ADOPTABLE as a challenger, ALL must hold on FORWARD data:
1. **Superiority:** arm realizable ROI ≥ champion `favorite` on the shared window (NI margin 0), and
   beats it on the point estimate.
2. **Belief-blind gate:** p_emp ≤ 0.01, `--calibrate` PASS, LB > 3% margin, and **≥ 2 disjoint
   NON-SOCCER regimes** with surplus > 0 (soccer never counts).
3. **Power floor** (below → "power-limited", not a verdict): ≥ 30 resolved events, ≥ 10 day-clusters,
   ≥ 2 non-soccer regimes at support.
4. **Non-regression** (`standard_guard.py`): champion belief-blind LB stays > 0 on the window.

### The two claim-breakers to watch explicitly (Tue)
- **(a) Durability past the tournaments.** `favorite_v2`'s edge must survive AFTER Wimbledon ends and
  the World Cup decays — i.e. in NON-tournament non-soccer regimes (regular-season MLB/NBA/NFL).
  If its non-soccer surplus collapses once tennis stops, the rank gate is a tournament artifact →
  KILL the rank half; `favorite_liq` survives on its own merits.
- **(b) Fire-rate / capacity.** Track how often `favorite_v2` fires vs `favorite_liq` vs champion
  (require top-5 backer + $1k may make it too rare/capacity-capped to matter). Report weekly.

## KILL CONDITIONS (pre-registered, per arm)
Once the power floor is met, an arm dies (de-registered proposal) if it is **inferior to champion by
> 3pp** realizable ROI OR its **belief-blind LB ≤ 0**. Additionally, `favorite_v2`'s rank half is
killed if breaker (a) fires — non-soccer edge does not survive the end of the tournament regimes —
even if the aggregate number still looks positive. In every kill case the sport-map fix survives.

## Honest expectations
- `favorite_liq` cuts ~9% volume → readable near the champion's cadence.
- `favorite_v2` cuts ~39% → accrual to floor is ~1.6× slower; gate readable in **~2–3 weeks**, and the
  ≥2-non-soccer clause may never clear if the edge is tournament-bound. A pass is NOT expected.

## Accrual verification
Both arms are registered in `default_portfolio` (unit-tested) and `LEDGER_STRATEGIES` is unset in prod
(empty ⇒ `should_ledger` accrues every non-blind strategy). On merge + autoupdater deploy both fire
into `consensus_signals` and accrue into `honest_paper_ledger` automatically — no config change.

_Reproduce: `garbage_segments.py`; `policy_search.py {--sweep,--bbgate,--residual,--weight}`._
