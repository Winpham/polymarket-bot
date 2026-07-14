# US-BOOK-DEPTH — can the US book fill our clips?

**Question that gates execution:** can the US book fill a $50 (and $250) market clip in the families
we trade — sports favorites (mid 0.71–0.98) and weather (`tc-temp*`) — and how does it vary by time
of day? Public `/v1/markets/{slug}/book`, unauthenticated. Fill = a market BUY of that size fully
consumed by resting asks; slippage = VWAP over the best ask, in cents.

## Two snapshots — and why they disagree (read both honestly)

**A. Research snapshot, 23:20 ET (n=126 favorites, 28 weather).** Set = markets that *traded* that day
(from the Daily Market Report), i.e. the liquid subset.

| family | n | median spread | median $ at best ask | $50 fill | $250 fill |
|---|---|---|---|---|---|
| favorite (traded subset) | 126 | **1.0¢** | **$2,457** | 100% @ 0.000¢ | 99.2% @ 0.000¢ |
| weather (traded subset) | 28 | 2.0¢ | $8 | 100% @ 1.55¢ | 100% @ 8.7¢ |

**B. Sampler snapshot, ~01–02 ET (n=397 favorites, 29 weather).** Set = *all* currently-active band
markets (LITE-stream discovery), which includes illiquid longshot-complements at 0.71–0.98.

| family | n | median spread | median $ touch | median $ full book | $50 fill | slip50 (med) | $250 fill | slip250 (med) |
|---|---|---|---|---|---|---|---|---|
| favorite (all band) | 397 | **17.0¢** | $355 | $17,634 | **84%** | 0.000¢ | 73% | 0.000¢ |
| weather (all band) | 29 | 1.0¢ | $29 | $10,488 | 100% | 0.693¢ | 100% | 7.03¢ |
| other (control) | 60 | 3.5¢ | $267 | $25,644 | 100% | 0.000¢ | 97% | 0.000¢ |

**The disagreement is mostly universe, partly time.** Snapshot B's median is worse because it averages
over *every* band market including illiquid ones (many favorite-band names are thin longshot-complements
that never trade); the median is dragged down even though the traded names (snapshot A) fill at ~0¢. Time
of day adds to it: even the traded set thins overnight (this ran near 1–2 AM ET, the quiet window).

## What this means for execution

- **The liquid/traded favorites are deep enough:** $50 and $250 fill at ~0¢ slippage, with thousands of
  dollars resting at the touch. This reverses the prior session's "immature book (2 bid / 15 ask)"
  spot-check — that was an unrepresentative single market.
- **But you cannot assume depth from the band.** The median over *all* band markets is thin and
  time-varying, so execution must be **per-market gated on live depth at fire time**, never priced off the
  band membership alone. `us_book_tape` (migration 045) exists precisely to make that gate data-driven,
  and `us_quotes` (042) captures depth at signal fire.
- **Weather is the thin arm** and consistently so across both snapshots: median touch only $8–$29, so a
  $50 market clip costs ~0.7–1.6¢ and a $250 clip ~7–9¢ — enough to eat a weather edge. Weather must trade
  **small and/or passive** (resting orders earning the maker rebate), not by crossing the spread.

## Still owed (honest gap)

A single overnight sampler pass is not the time-of-day verdict. Run `us_book_sampler.py --loop 900` across
a full US trading day — especially the hours near settlement, when depth matters most and was not yet
measured. `n` and dispersion are captured per row; the day-shape is the missing control.
