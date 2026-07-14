# Where is the money — FOR US? (pre-registered, 2026-07-14)

Branch `feat/niche-rosters`. Paper/analysis only.

## The objective function changes

Every previous cut ranked traders by how much money **they** make. That is the wrong sort.
What we want is expected dollars to **us**:

    copy_value(trader) = (their_taker_edge - REAL_follower_tax - fees) x deployable_size
                         summed over their signals per unit time
                         subject to: our order does not move the price against us

A trader earning +20% on $10 bets in a market that dies if you touch it is worth **nothing**.
A trader earning +5% in a market that absorbs $200 is worth real money. The prior run's roster
was ranked on *their* edge; this run ranks on *ours*.

## The number we have been ASSUMING and can now MEASURE

Every result so far has subtracted a **1.3¢ follower tax** taken from an old audit. We now hold
the complete market tape — every fill, with timestamps. So the tax is **measurable, not assumed**:

> after roster wallet W takes a fill at price p at time t, what price could we actually have
> got at t+Δ (Δ = 1m, 5m, 15m, 1h)? The subsequent fills in that market ARE the answer.

This also yields the **edge-decay curve** (how fast the edge dies with lag), which sets the
latency budget for any executor, and it is a *measurement*, not a modelling assumption.

## Questions this run must answer

1. **REAL follower tax + edge decay vs lag.** If the true tax is 3–4¢ rather than 1.3¢, the
   candidate edge dies and we stop. This is the first and most dangerous test.
2. **Market impact vs order size.** How much can we push into these markets before we eat the
   edge? Measured from the tape (price move vs trade size), not proxied by `n_trades`.
3. **Copy-value ranking.** Re-rank the population by expected $ to US, not by their ROI.
4. **Strategy archetypes.** Cluster the winners on behaviour (price band, entry timing,
   category mix, size, maker/taker, hold-to-resolution). Which archetype is most *copyable*?
   A "strategy" we can state in words is far more robust than a list of wallet addresses —
   wallets churn, strategies persist.
5. **Signal stacking / relationships.** When several roster members hit the same side of the
   same market, is the edge bigger? A consensus-of-winners signal may beat any individual, and
   it is the natural way to turn many small-bankroll traders into one tradeable position.
6. **Signal frequency ⇒ $/day.** Edge per signal is useless without a rate. How many actionable
   signals per day, and what is the expected daily P&L at our size?
7. **Walk-forward.** All of the above selected on window A, confirmed on B, then **re-confirmed
   on a held-out window C that no decision has touched.**

## Pre-registered kill criteria (fixed BEFORE results)

- **K1** REAL tax ≥ (taker edge − fees) ⇒ the edge is not realizable ⇒ **STOP, report dead.**
- **K2** Edge at our deployable size (post-impact) < 0 ⇒ capacity-dead ⇒ report the ceiling.
- **K3** Window-C confirmation fails (net edge CI includes 0) ⇒ the B result was a fluke of the
  many looks taken ⇒ **report NULL and retract the candidate.**
- **K4** Any archetype/consensus rule must beat the *individual-copy* baseline out-of-sample, or
  it is complexity for its own sake and gets dropped.

Multiple-testing discipline: window C is touched **once**, at the end. Everything else is
exploration on A/B and is labelled as such.

## Honest prior

The project's history says edges die at the realizable price ([[exec-policy]]: "selection
exhausted at the realizable price"). The candidate survived a *modelled* 1.3¢ tax. The most
likely outcome of measuring the real tax is that it is larger and the edge shrinks. The run is
designed so that outcome is reportable in one number.
