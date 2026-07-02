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
3. **Size flat-SHARES (or ¼-Kelly), NEVER flat-dollar.** Flat-$ turned `strict` from +$571
   (flat-shares) into −$4,584 by over-exposing to longshots. This single choice flips the P&L sign.
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
   the as-of run: **0 wallets certify on one weekend** → this is data-starved, not disproven.)*
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

## Honest status & posture
- **Certified/bankable today: nothing.** One tournament, ~89% World Cup soccer.
- **Best paper result (one weekend, $100 flat):** favorites-only ≈ +$900-1,300; naive full-feed
  flat-$ LOSES (−$4,447 strict). Sane sizing is mandatory.
- **Posture:** keep accruing across the World Cup ending + other sports; re-run the as-of pre-flight
  each block; promote nothing until ≥2 cross-sport cells clear `lo > 3%` on disjoint cuts. The
  relational layer waits for data. No real money until the gate says yes.
