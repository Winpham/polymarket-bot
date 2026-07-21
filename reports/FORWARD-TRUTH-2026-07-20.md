# FORWARD TRUTH — 2026-07-20

What the forward instrument actually says, after finding that it could not say anything.

Context: the operating doctrine is now **trust the inherited archive only for what the market
COSTS, never for whether there is an EDGE.** Collection was never under our control; the `startTs`
bug once dropped 96.8% of history, `entry_ask` was captured wrong until D4, and `us_mid_tape` had
silent zero-row days on 07-17/18. Under that doctrine the forward paper test is not one instrument
among several — it is **the only one that can certify anything.**

So the first question is whether it works. It did not.

---

## 1. THE FORWARD TEST COULD NEVER HAVE PASSED — no settlement leg existed

78 signals accrued from 07-19. **Zero were settled.** Not "settled and losing" — never written.
`favband_forward.py` declares `settled / won / settled_at` and reads them back in `--report`, and
**nothing in the repository ever wrote them.** The pre-registered box `>= 60 settled events` was
unreachable by construction; the harness would have logged busily and reported `0/60` forever.

77 of the 78 were **already terminally resolved** in the venue's own market record at the moment I
looked. The data was sitting there the whole time.

This is the project's signature failure in a new costume — the same shape as the 2d17h tape outage,
where a dead input reported "nothing qualified", indistinguishable from "no edge".

**Fixed:** `scripts/favband_settle.py`, with four fail-loud guards (live-file provenance stamp,
settlement-parse sanity, an **orientation check** that refuses to write when the win rate sits far
below the mean entry price, and idempotence). Settlement requires *terminal* resolution — `closed=
True` is not enough, and a closed-but-unpriced market stays pending rather than being guessed.

**Also fixed, same class:** skips were computed, passed to `write()`, and never inserted. Worse,
`write()` was only called when signals existed — so the **300 of 331 sweeps that qualified nothing
recorded nothing at all.** The funnel for those sweeps existed only in a rotating log file. That is
precisely the "dead feed vs. no edge" ambiguity that must never be allowed to recur.

## 2. TWO GATE BOXES WERE LYING, both in the flattering direction

- **"≥60 settled events" counted SIGNALS.** The 77 signals span **15 baseball games**. Sibling
  props of one game share a pitcher, a park and an umpire; they are ~15 independent draws, not 77.
  True state: **15/60**, not 77/60.
- **"≥2 distinct competitions" counted market TYPES.** Five `baseball_player_*` types are one
  competition (MLB) wearing five names. True state: **2** (mlb, cs2).

All CIs are now event-clustered.

## 3. THE FORWARD TEST IS NOT TESTING WHAT WAS CERTIFIED

**99% of settled forward signals are PLAYER PROPS.** `favband_forward.py` has **no market-type
filter at all** — it trades whatever sits in the 0.80–0.98 band with a tight book.

Player props did not exist on this venue before **2026-05-13** (home runs), and the bulk — hits,
total bases, hits+runs+RBIs — launched **2026-06-10**. The retrospective +1.52% was measured on a
**TEAM/MATCH-dominated** universe (fwc soccer, 27 leagues).

This forward ledger is **not a replication** of the retrospective result. It is a measurement of a
different market that happens to share a price band. The report now prints a population warning.

## 4. THE INTERIM READOUT (not a gate tick)

```
settled 77 / 15 events / 1 day
ROI at the EXECUTED vwap : +4.53%   [-4.08%, +10.68%]   (event-clustered)
win rate 0.922   mean entry 0.8779

gate: [ ] 15/60 events   [ ] LB -4.08%   [x] 2 competitions   [ ] 1 week   => k=0
```

One day. CI spans zero. **This is not evidence of an edge.** It is evidence that the instrument
now works.

## 5. RETRACTED — my own alarm, killed by conditioning

I opened by measuring the live tight-spread share at **25.6%** against the retrospective's **69.9%**
and called it a refutation of the only rule that makes FAVBAND implementable ("trade only the 1¢
book"). Conditioning on lead time dissolves it: `us_book_depth` sweeps markets at **any** distance
from tip-off, and only **1.68%** of its observations fall inside the <30-min decision window. Books
days out are naturally wide. `us_quotes` fires near game time, which is why it reads tight.

The two instruments were measuring different moments, not disagreeing about the same one.
**The 69.9% stands. My refutation does not.**

The real finding underneath is worse for a different reason: **the capacity instrument spends 98.3%
of its effort outside the window it exists to measure.**

## 6. KILLED ON ARRIVAL — the "+14.32% deep-book edge"

Slicing the ledger by touch depth produced:

```
touch >= $250   n=34  events=13   roi= +14.32%  [+12.72%, +16.03%]
```

A 3.3pp CI on 13 events would have been the most significant result in this project's history.

**It is an artifact.** That subset contains **34 wins and zero losses**. A bootstrap cannot resample
a loss it has never seen, so the interval collapses to the dispersion of *winning payouts* and stops
measuring uncertainty about the edge entirely. Same defect as the retracted "0% chance of a losing
year".

Honest arithmetic: rule of three puts the true loss rate as high as **23.1%** on 13 events, while
breakeven at a 0.873 entry needs it below **12.7%**. Wilson on events propagates to ROI
**[-12.0%, +14.0%]**. The data cannot exclude a losing strategy.

`zero_loss_check()` now runs on every subset the report prints, and is self-tested both ways.

## 7. λ (CLV) — measured forward for the first time on this population

Does the market move *toward* our picks after we buy? That is the difference between an information
edge (which can clear a toll) and a risk premium (which cannot).

```
lambda = +0.104c  [-0.441c, +0.777c]   n=55, 15 events
median -0.500c    only 30.9% of signals move toward us
5%-trimmed mean   -0.090c
close measured a median of 10.0 min before tip-off (min 0.1)
```

**Essentially zero, and indeterminate.** The mean is carried by a few large positive moves; the
typical signal drifts slightly *against* us.

Two things matter here:
- It is **not** the strong negative the retrospective showed (λ = −6.7¢, significantly negative —
  "~100% of return is settlement variance"). Different population, different answer.
- **The window is too short to be decisive.** Entry lands ~26 min out, the last quote we hold is
  ~10 min out. We are measuring 16 minutes of drift and have **no observation at t−0**. This is a
  low-power test, not a negative result.

## 8. CAPACITY — the first real numbers, and they are not small

Measured at the decision moment, walking the actual offer side:

```
touch >= $250    44.2% of signals        touch >= $5,000   32.5%
median touch $70     p90 $30,362     max $49,024
median slippage to fill $50: 0.000%
```

Bimodal: roughly half the signals are dust (<$100), and a third carry **thousands of dollars at the
touch**. For comparison, team/match books near start sat at $139–420.

This matters because capacity has been the project-wide ceiling — `$50/signal`, `~$41/day`,
`~$10k/yr`. The prop book is a different order of magnitude. **But depth is not edge.** A tight,
deep book on a brand-new market is also exactly what a professional market maker looks like, and
being consistently filled by one is a well-known way to lose money slowly.

## 9. TIME TO AN ANSWER

```
per-event sd 18.1pp, 15.0 events/day observed

a true edge of  1.5%  needs ~560 events  = ~37 days
a true edge of  3.0%  needs ~140 events  = ~ 9 days
a true edge of  4.5%  needs ~ 62 events  = ~ 4 days
```

**Plan against the small edge.** If the truth is the retrospective +1.5%, this is a months-long
measurement — and stopping early on a good week is exactly how it goes wrong.

---

## WHAT TO DO NEXT, in order

1. **Keep settlement running.** The plist is prepared but deliberately not loaded — starting it is
   an operational act. Without it the ledger silently re-accumulates unsettled signals.

2. **Build the signal-shadow capture — the highest-leverage instrument available.**
   Once a signal fires, poll *that* market's book every 30–60s until tip-off. This is cheap (only
   signal slugs) and it converts λ from a 16-minute low-power estimate into a real closing-line
   measurement. **λ resolves far faster than ROI** — every price tick is an observation, where ROI
   gets one binary per game. It is the difference between an answer in days and an answer in months.

3. **Pre-register the player-prop program BEFORE looking again.** The population is new, so the
   retrospective pre-registration does not cover it. Write the gate first, while nothing is at
   stake. Note explicitly that props were found by *not filtering* — they were never hypothesised,
   which is a multiple-comparisons exposure, not a discovery.

4. **Decide the population question deliberately.** Either filter the forward harness to
   TEAM/MATCH (replicating what was certified) or declare props the new target and gate them on
   their own evidence. Right now it is doing neither on purpose.

5. **Fix or retire the book capture's targeting.** 1.68% of observations inside the decision window
   makes it structurally unable to state capacity.

## THE STANDING RULE

> No claim ships without (a) a control/placebo arm, (b) a significance test, (c) explicit n and
> dispersion. A number without those is a HYPOTHESIS, not a result — and must never be the basis
> for risking money.

Two claims died to that rule today, one of them mine.
