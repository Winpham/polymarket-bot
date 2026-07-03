# Refined Strategy — our own consensus edge (findings-driven, belief-blind)

**Status: living document.** Everything below is measured on **~2.4 days = one FIFA World Cup
weekend (2026-06-29 → 07-01)** unless noted. Nothing is certified. The point is to encode what
we've learned so the observations compound, define the exact metrics we track, and set the bar a
component must clear before it earns real money. Paper/alert-only; NO real money until certified.

## The thesis (what the data supports right now)
Blindly tailing everyone loses (`_blind` ≈ −0.3% edge, negative after costs). The value is in
**selection**, and it concentrates precisely where theory predicted: **the sharp consensus on
FAVORITES.** The consensus is genuinely skillful there — it beats *blindly betting favorites at
the same price*, which is the real test that it's information and not just favorite-longshot bias:

| Entry band | Blind-favorite edge/share | **Consensus-favorite edge/share** | Consensus adds |
|---|---:|---:|---:|
| 0.6–0.8 | +3.4% | **+14.3%** | **+10.8 pts** |
| 0.8–1.0 | +1.1% | **+7.0%** | **+5.9 pts** |

Longshots are structurally overpriced (blind edge −1.9% @ 0-0.2, −3.3% @ 0.2-0.4) and the
consensus on them *lost* badly (band 1: 76 bets, 3.9% hit, −$5,821 at $100 flat). **Skip them.**

## The rules the data supports (the core strategy)
1. **Bet consensus favorites only** (entry price ≳ 0.6). Skip longshots and coin-flips.
   *Quantified by the slice study (entry 10, FDR-surviving mirror test):* the fleet's
   non-favorite residue is RELIABLY losing after real costs — strict-tennis realizable
   −23.7% [−37.3, −8.7] over 110 events (band 1: 0% hit on 26 events) and
   strict-moneyline-all-bands −13.7% [−25.8, −2.5] over 179 events. These are the
   record's two DODGE cells; the favorite side of the same streams is positive.
2. **Follow the consensus — that's the +6-11 pt edge** over betting favorites blindly. It is
   information, not just the favorite-longshot bias.
3. **Size flat-SHARES (or fractional Kelly), NEVER flat-dollar.** Flat-$ turned `strict` from
   +$571 (flat-shares) into −$4,584 by over-exposing to longshots. This single choice flips the
   P&L sign. *Sharpened by the risk engine (entry 12, `scripts/risk_engine.py`):* the
   pre-registered default is **⅛-Kelly per band (SE-shrunk) with exposure caps**
   (`kelly_eighth_capped`), NOT ¼-Kelly — because on a 4-day record with no losing slate the
   drawdown ceiling is SLACK (it cannot price a drawdown that hasn't occurred), so a
   construction-bounded policy is the only honest choice until an adverse regime accrues; ¼-Kelly
   earns its aggression only then. The per-band SE-shrunk Kelly also auto-zeroes losing bands
   (strict bands 1–3 → f=0), reproducing the DODGE map from sizing alone. Flat-$ reproduced the
   sign flip (strict P(ruin) 45.6% vs flat-shares +EV) — the anchor still holds.
   *Correlated-risk run + VERIFICATION (entries 18–19, `scripts/corr_risk_engine.py`,
   `corr_risk_verify.py`):* the game-stacking is real — one game spans up to 7 `event_slug`s
   (`fifwc-eng-cdr`), so ≤1/event lets ONE game take 35% of bankroll under ⅛-Kelly. **But the
   verification (D21) CORRECTED D20's "≤3/game fixes it":** no per-game cap improves portfolio
   downside (CVaR₅/p99 maxDD) — caps bound the *rare single-game* block but WORSEN CVaR by shedding
   +EV diversifying volume. **The first-order risk lever is the KELLY FRACTION, not the game cap**
   (P0 flat-shares is 4× safer on CVaR than any ⅛-Kelly policy — converges with D18/D19 de-lever).
   Ordered levers: **(1) de-lever the Kelly fraction (⅒–⅟₁₆); (2) OPTIONAL market-type-aware cap**
   — keep the near-independent totals/exact-score (+EV ballast), bound only the DIRECTIONAL units/
   game (this Pareto-beats a blunt count cap). All PROPOSED, not applied. The whole trade-off is
   **conditional on the edge δ** (shuffle-invariant ⇒ its reality is the selection-null's job, D16).
   *De-lever fraction PINNED (2026-07-03, entry `2026-07-03-delever-fraction.md`,
   `scripts/corr_risk_delever.py`, D22):* the k-sweep under the adverse t-copula+heterogeneous
   model gives a **flat growth-per-CVaR plateau across ⅛–⅟₁₆**; the binding constraint is the
   **P(maxDD>25%) ≤ 10%** cap, which rules out ¼ (41%) and ⅙ (14%). **Proposed default: ⅟₁₂-Kelly**
   (the OBJ-max feasible knee, p95 DD 18%), with **⅟₁₆** as the conservative default given WS-A's
   low λ̂≈0.15, and **flat-shares as the floor** if λ≈0. ¼-Kelly stays off the table until λ is
   MEASURED ≥ ~0.75. Still PROPOSED, still conditional on δ.
4. **Act in real-time, within a few minutes of fire.** The consensus is fully formed at fire
   (~3 backers, stable — it does NOT grow), and the edge is front-loaded (a ~1-1.5pt follower tax
   from the sharps' fill to our first observable mid; further drift beyond that is what speed
   protects). Promptness matters; microsecond speed does not.
5. **Do NOT scale by consensus strength or backer rank.** On this data neither adds edge:
   net_count 2-3 (+8.4%) ≈ 4-5 (+8.1%); best-backer top-10 (+8.35%) ≈ top-50 (+8.17%). Revisit
   only if a certified signal emerges. *Re-confirmed by the slice study:* within
   `favorite`, elite-present AND no-elite cells BOTH clear the FDR bar with overlapping
   CIs — the elite split does not separate the edge (drift-defined pre-migration-036;
   at-fire-readable going forward).

Note: `favorite` / `elite_fresh_fav` already implement most of this — the refinement is **sizing
discipline + skip-longshots + real-time execution**, not a new model.

## The consensus-signal ladder (what we have; what we're researching)
The engine is NOT a raw count. Levels, simplest→richest, each gated by the belief-blind gate:
1. **count** — `net_count = n_backers − n_opposers`. (baseline)
2. **rank-weighted** — `net_quality = Σ w_q(rank)`; sharper leaderboard rank counts more. *(default,
   `WeightMode::Quality`)*
3. **earned-trust-weighted** — per-wallet earned edge from the trust map. *(`WeightMode::TrustWeighted`)*
4. **trusted-only** — count only gate-Certified wallets, per-slice / per-sport. *(`trusted_only`;
   the as-of run: **0 wallets certify on one weekend** → data-starved, not disproven. The DEEP
   historical mine (entry 20, `scripts/specialist_mining.py`, D23) confirms it on the far larger
   `trader_fills` record + at OUR price: **0 copyable specialists certify** over 56 (wallet×sport)
   cells. Follow-set stays ∅; `CONSENSUS_TRUST_ARMS` stays OFF. Two hard rules this bought:
   **(a) judge any follow-set at OUR realizable entry after the follower tax, per sport, over
   sport×band blind — NEVER by global PnL; (b) exclude market-makers FIRST — 59% of the ≥30-match
   "top" wallets are two-sided book-makers you cannot tail.** The sharpest daily market (MLB) has
   the HIGHEST tax (~3¢), which alone ate 83% of its one genuine directional wallet's edge — the
   sharp-market copyability wall. The real (uncertifiable, power-limited) directional signal sits
   in SOCCER, not the sharp markets; NBA/NFL are calendar-blocked → auto-onboard Sept/Oct.)*
5. **RELATIONAL (research track — NOT built):** pairwise affinity ("A agrees with B"), **conditional
   accuracy** ("A is X% right *when B also backs*"), top-N co-agreement, disagreement penalties.
   This is the sophisticated frontier and likely the real prize — but it's ~N² parameters and
   needs dense multi-tournament co-occurrence data. On the current ~3-backer, one-weekend record it
   would overfit catastrophically (we can't even certify single wallets yet). **Build it as a gated
   measurement instrument, promote only if it beats level 2/3 at the bar — never fit-and-bet now.**

## Metrics we track as data accrues (the instruments)
- **Consensus-vs-blind-favorite premium** (per band, per sport) — the table above. This IS the edge;
  it must persist across regimes.
- **Flat-shares vs flat-$ vs favorites-only P&L** (per strategy, per band) — the sizing split that
  is the difference between winning and losing.
- **Level-ladder lift** — does each richer consensus level (rank → trust → trusted-only → relational)
  beat the simpler one *at the certification bar*? Promote only on a certified lift.
- **Execution-latency decay** — edge vs minutes-after-fire (the speed budget), once dense capture accrues.
- **Certification (the gate):** an as-of, leak-free, event-clustered surplus with a Bonferroni lower
  bound **> 3% capture margin**, over a **≥30 independent-event floor**, **persistent across ≥2
  disjoint regimes** (tournaments/sports). Re-run `scripts/asof_preflight.py` after each tournament block.
- **The slice map (`scripts/slice_study.py`, entry 10):** pre-registered PRIORITIZE/
  NEUTRAL/DODGE verdicts per slice, BH-FDR q=0.10, matched (regime×band) baseline,
  cost-realistic, frequency-weighted. Re-run at +7 days / +300 fleet events / after each
  tournament block. Today's overlap of reliability × volume: favorite's favorite-band
  slices at 10–20 ev/day; the reliably-negative mass is the fleet's non-favorite residue.
- **The adaptive overlay (`scripts/map_state.py` + `map_checkpoint.py`, entry 11, D14):**
  the slice map as a LIVING versioned state machine — cells enter DODGE/PRIORITIZE on the
  WHOLE record (power) and exit/rehabilitate on the RECENT window (adaptivity), with STALE
  (silence holds) and THRASH (two flips freeze) guards. A cut applies itself only while the
  evidence binds and reverses at the bar when the world changes (owner directive: no
  permanent cuts). `fleet_mapped` is judged on paired lift over `strict` + the excluded-pick
  counterfactual on FORWARD rows only; the Rust arm is earned, not built. Adaptive means
  re-reading the frozen procedure on new data, never re-tuning it.
- **Breadth is emergent, not code-blocked (entry 11 audit):** the only alerting strategy
  runs SportsMode::Include; the leaderboard is global category-blind PnL (6h drop-grace) so
  volume follows the calendar automatically. Post-WC forecast: strict survives ~15/day (MLB
  is the daily bridge → Oct), favorite thins to ~4/day, elite_fresh_fav (97% WC+Wimbledon)
  goes near-silent. Breadth is bought by more MARKETS via rotation, never by loosening gates.

## Truth-audit hardening (2026-07-02, entry 13 / DECISIONS D16)
Six pre-registered attacks on `favorite`/`elite_fresh_fav`, each run once. **The favorite
selection edge SURVIVED** — at honest MATCH-level clustering (event_slug had inflated N by ~29%)
surplus RISES to **+12.5%** over 70 matches, selection-null **p=0.0000 (z 4.35)**; grading is
0/305-mismatch vs Gamma UMA; the mirror is symmetric, the placebo flat, both time-halves positive,
the fills real; it is not latency-fragile and capture is 97.6%. Two things it did NOT survive:
- **The "+3.33% eligible" LB is STALE.** The current scoreboard SE deflates to distinct event-DAYS
  (commit 5b83d33, post-D6); on 4 correlated event-days favorite's LB is ≈ −23%. **Nothing certifies
  on 4 days — the wall is ACCRUAL of independent event-days, not the point estimate.** (The old
  event-N LB +4.5% is what `honest.rs` still uses; reconcile before any GO.)
- **elite_fresh_fav is materially weaker:** N=27 < the 30-event floor at match level, and +2.6% of
  its surplus is (band×day×regime) composition, not selection. Treat `favorite` as the primary edge;
  gate elite on the regime×band baseline if ever promoted.

## Reliability-portfolio hardening (2026-07-02, entry 14 / DECISIONS D17)
Three paper-only instruments off D15/D16 (`scripts/{effective_n,edge_orthogonality,portfolio_constructor}.py`),
each self-tested, nothing promoted:
- **Effective-N reconciliation (resolves D16-a).** The board's day-N LB (**−20%**) assumes within-day
  ICC=1; the MEASURED within-day ICC is **0.007≈0**, so that reads a strong, near-independent edge as
  statistically dead. Split the conflated SE: **within-sample** the surplus is well pinned down (event-N
  ≈ cluster-robust LB ≈ **+4.6%**); **out-of-sample persistence** is the real wall and is NOT a
  within-sample SE (encoding it as one is grain-arbitrary: day-grain t LB −8% vs tournament +4.5%). The
  honest binding constraint is the **COUNT of independent clusters** (~4 days / ~2 tournament cycles) —
  i.e. accrual, stated rigorously. favorite is individually **+ in 4/4 disjoint regimes**. Proposed (not
  applied) convention: cluster-robust SE at the measured ICC + an explicit independent-cluster-count floor.
- **Orthogonality gate — reliability is supply-limited, PROVEN not asserted.** 0 of 12 captured strategies
  add a second edge that diversifies favorite (G1 independent volume ∧ G2 orthogonal-component
  selection-real Bonferroni ∧ G3 residual+shock independent). The broad-consensus strategies add volume
  that is the reliably-losing non-favorite residue and co-moves with favorite. **Watch-item:
  `trust_weighted`** (ladder L3) passes independence (orth +4.7%, residual r −0.05, a −0.76 regime hedge)
  but fails G2 (power-starved, N=46) — the leading orthogonal-edge candidate, uncertified.
- **The book (constructor).** Re-derives `kelly_eighth_capped` on **[favorite] only** (elite nested →
  dropped) — no sizing change to rule 3. A second edge's worth here is **volume + continuity (post-WC
  supply droughts) + insurance**, NOT per-bet variance reduction (decorrelating fixed volume ≈ 0 at
  favorite's ~0 within-slate correlation). Re-run at each accrual block; MANDATORY before any pilot.

## Correlated-risk hardening (2026-07-02, entry 18 / DECISIONS D20)
Two paper-only instruments (`scripts/{game_correlation,corr_risk_engine}.py`), self-tested,
nothing promoted. Corrects the correlation UNIT D15 got wrong.
- **The unit is the GAME, not the position or `event_slug`.** favorite = **220 positions on 78
  GAMES** (`super_event`); 64% on the top-10 games, 66% World Cup. D15's ICC_slate≈0.008
  ("independent") is a **benign-sample artifact**: the within-game pair concordance (0.874) equals
  the independence baseline (0.873) ONLY because **no favorite team was upset** on this record — the
  shared block shock was never sampled. n_eff(game) ∈ **[78, 220]**; which end binds depends on the
  unmeasurable `w_game`.
- **The game-stacking is real but the cap is NOT a free win (D21 corrects D20).** ≤1/`event_slug`
  lets `fifwc-eng-cdr` (7 event_slugs) take 35% of bankroll on one game. D20 proposed ≤3/GAME; the
  verification found **no per-game cap improves portfolio downside (CVaR₅/p99 maxDD)** — caps bound
  the *rare* single-game block but WORSEN CVaR by shedding +EV diversifying volume. **The KELLY
  FRACTION is the first-order lever** (P0 flat 4× safer on CVaR than any ⅛-Kelly cap — converges with
  D18/D19 de-lever). Ordered: (1) de-lever ⅒–⅟₁₆; (2) OPTIONAL market-type-aware directional cap.
- **Keep the "Exact Score — No" / totals markets** — dropping them is EV-negative (+$2.5/pos) and
  they are near-INDEPENDENT of a directional upset (a different score still wins). They are +EV
  diversifying ballast; a blunt count cap that keeps directional and drops THESE is backwards — cap
  the DIRECTIONAL units instead (market-type-aware, Pareto-beats the blunt cap).
- **Go/no-go turns on λ.** At λ=0.5 the book still profits with a bounded tail; at λ≤0.25 it bleeds;
  at λ=0 it loses to costs. 4 benign days cannot distinguish λ=1 from λ=0.25 — the separating event
  (an adverse correlated day) is what the record lacks. Real money waits on ≥K adverse correlated
  days across ≥5 non-expiring regimes (months), per D18/D19 — not more WC weekends.

## Softness × Skill steering (2026-07-03, entry 21 / DECISIONS D24)
The favorite edge lives in the SOFT pockets and bleeds in the sharp ones. The `category ×
market-type × band` map separates **softness** (opportunity size, blind-pool-knowable),
**skill** (the edge, over the matched blind baseline), and **realizable ROI** (bankable, at
0.5¢+2%). Binding cell verdicts today:
- **DODGE `mlb / deriv / 0.60–0.80`** — softness −10.5% (CI ub −0.5%): sharp, base rate bleeds.
  Do not concentrate favorite-following on low-band MLB totals. (MLB/tennis derivatives are
  directionally sharp; only this low-band cell certifies today.)
- **Soft ≠ bankable (K2):** `soccer/deriv/0.80–0.90` is reliably soft (+9.3%) but its consensus
  skill is realizable-ROI-LB negative → **NEUTRAL**, not a bet. Same for `tennis/main/0.60–0.80`.
- **Nothing is PRIORITIZED** — soccer/tennis are the only skilled candidates and neither clears the
  cost margin under FDR on ~5 correlated days (INDETERMINATE-by-power, not refuted). The map is a
  forward ORDERING (governed by `map_state` v002), not a certified bet.
- **Where to watch:** esports is the softest non-summer venue (deriv +9.0%) and fires a little —
  the top harvest frontier; **politics/elections** is a year-round soft frontier ramping to the
  Nov-2026 midterms; fall sports (NFL Sept, NBA Oct) as they season. Re-read per cell at skill
  N→20 fires / +7 days / in-season.
- **Never-fire (K4):** crypto/other/econ have soft blind favorites but the consensus never fires
  there (sharps don't agree one-sided) — softness observations, not steerable arms.

## Honest status & posture
- **Certified/bankable today: nothing.** One tournament, ~89% World Cup soccer. The favorite edge is
  real and attack-hardened, but 4 correlated event-days cannot clear the day-deflated SE — accrual-gated.
- **λ is now MEASURED (weakly), not just assumed (2026-07-03, entry `clv-lambda`, D22).** The proper
  CLV instrument (`signal_price_trajectory`) is **empty — dense capture never ran** — so true λ is
  INDETERMINATE-BY-DATA. The best available proxy (`mean_price` drift) is positive and beats the
  selection-matched null (p=0.0000) but explains only **~15% of the surplus** (λ̂≈**0.15**, wide CI) —
  weakly ANTI a high λ. **Next dollar of work = turn on `DENSE_CAPTURE` (paper-only) so real CLV
  accrues and λ̂ becomes trustworthy**, before more modeling. `scripts/clv_lambda.py` switches from
  proxy to trajectory automatically once coverage exists.
- **The winners fire SILENTLY (2026-07-03, entry `alert-leak`, D22).** favorite/elite = 334 signals /
  0 alerts; only `strict` (the DODGE-containing stream) is surfaced. ≈ **+$2,122 realizable leaked**;
  the fix is a default-OFF env flip (D12, already implemented) — **Tue's live-flip decision.**
- **Best paper result (one weekend, $100 flat):** favorites-only ≈ +$900-1,300; naive full-feed
  flat-$ LOSES (−$4,447 strict). Sane sizing is mandatory.
- **Posture:** keep accruing across the World Cup ending + other sports; re-run the as-of pre-flight
  each block; promote nothing until ≥2 cross-sport cells clear `lo > 3%` on disjoint cuts. The
  relational layer waits for data. No real money until the gate says yes.
