# Entry 20 — Per-sport specialist mining + copyability gate (2026-07-03)

**Branch** `feat/specialist-mining` (worktree off `main` 643886e, tag
`pre-specialist-mining-20260703`). **Instrument:** `scripts/specialist_mining.py`
(self-testing; `--self-test` runs the K1 battery on synthetic fixtures — all 8 green).
Paper/analysis only: no migration, no env flip, no real money, no arm switched on.

## The one-sentence result (ugly number first)

**We mined every wallet's deep historical resolved-fill record per sport and asked WHO to
follow at OUR price. Zero copyable specialists certify — and the reason is not subtle:
59% of the ≥30-match "specialists" are market-makers holding both sides (structurally
uncopyable), and the genuine directional edge that remains is power-limited and, in the
one sharp daily market (MLB), eaten alive by a ~3¢ follower tax.** Blind global tailing
has no certified per-sport replacement today. This is a valid honest null (K2/K3/K4),
mined on a far deeper record than the congregation run — not a re-run of it.

## What this run is (and is NOT)

The congregation run (DECISIONS D2, "per-sport specialist book DEAD") certified per-sport
specialists on the **4-day FORWARD consensus record** and found 0 — correctly, because
that record is one correlated World-Cup weekend. This run is different on two axes it
never touched: (1) it mines the far deeper **historical `trader_fills`** resolved record
on the slug-parsed **event-date** time axis (D1) — MLB alone is 41k fills / 78 wallets /
20 dates; (2) it judges **COPYABILITY at OUR realizable entry** after the measured
follower tax, and classifies the **mechanism** of each wallet's profit. A null after
*that* is a real finding about sharp-market untailability, reported as such.

## The family (pre-registered)

Unit = (wallet × sport). Certify floor = **30 distinct resolved match-events** (the
existing trust floor), clustered at the **match super-key** (`superkey.super_event` —
strips market-type sub-slugs so one match ≠ N events; event_slug inflates N ~29%,
D16-E). **56 cells** clear the floor across 6 sports:

| sport | cells ≥30 matches | distinct event-DATES (the real independent-cluster count) | note |
|---|---:|---:|---|
| tennis | 19 | 17 (Wimbledon) | correlated tournament |
| other | 14 | 19 | mixed |
| mlb | 8 | 20 | **daily, non-tournament — the honest test** |
| crypto | 8 | **0 parseable** (D1) | date-blind → baseline only |
| soccer | 6 | 38 (World Cup) | correlated tournament |
| cs2 | 1 | 24 | thin |

The distinct-DATE column is the binding number: per D17, the honest independent-cluster
count is the event-DAY, not the match. A wallet with 107 MLB matches still has them
inside ≤20 dates. Every gate verdict below is reported at **both** SE conventions —
event-N (generous) and **day-deflated** `effective_n = clamp(n_dates,1,n_matches)` (the
real bar, `promotion.rs`).

## The measured follower tax by sport (the copyability core)

`trader_fills` stores only the trader's fill price; OUR realizable entry
(`entry_ask`/`initial_market_price`) exists only on `consensus_signals` for fired
markets. So the tax = (OUR entry − the sharps' mean fill) is **measured on the forward
consensus record** and applied to the historical fills as the best available proxy.
Surplus/share = `won − entry`, so a positive tax subtracts share-for-share.

| sport | measured tax (OUR entry − sharp fill) | provenance | conservative floor used |
|---|---:|---|---:|
| **mlb** | **+2.96¢** | executable ask, n=149 | 2.96¢ |
| soccer | +0.27¢ | ask, n=1607 | 1.3¢ |
| other | +0.71¢ | mid, n=402 | 1.3¢ |
| tennis | −1.10¢ | ask, n=191 (thin, noisy) | 1.3¢ |
| crypto | −0.16¢ | mid | 1.3¢ |

**The single most important copyability finding:** MLB — the sharpest, most liquid *daily*
market, and the one non-tournament sport with real depth — has the **highest** measured
follower tax (~3¢). The sharp market prices the sharps' information into the book fastest,
so the delayed taker pays the most. That is the honest copyability test, and MLB largely
fails it (below). Soccer/tennis taxes are near-zero and noisy (thin overlap); we floor the
conservative verdict at the truth-audit chase (~1.3¢, D16 F5). *Framing caveat:* the tax
is charged as the **specialist-chase** cost (the blind-favorite baseline is a fixed fleet
reference at that band, not itself re-chased); under a symmetric-execution reading the tax
partly cancels. We use the asymmetric (conservative, real-follower) reading as primary —
but it does **not** drive the 0-count (see below).

## The gate verdict (belief-blind, at OUR price)

```
CERTIFIED copyable @ OUR price, DAY-deflated SE (the real bar):  0
CERTIFIED @ OUR price, event-N SE (generous, no accrual penalty): 0
K2 — real @ THEIR price but DEAD @ OUR price (tax killed it):    8
Mechanism-EXCLUDED (market-maker / price-improver, uncopyable): 33  (59% of the family)
```

**0 certify at either SE convention.** The exclusions and the tax are the headline, but
they are not even the binding constraint: **even at their own untaxed price, no wallet
clears the 3% lower bound at event-N** — the point estimates that survive the tax
(soccer +9–10%, below) still have LB < 3% at N=41–58 with high variance. This reproduces
the standing Item-7 verdict ("32 wallets clear +3% *point*, 0 clear the *lower bound*")
now on the copyability axis: **the binding wall is power / independent-event accrual, not
the point estimate — and the tax is a second killer stacked on top, specifically in MLB.**

## K4 — the dominant mechanism is market-making (structurally uncopyable)

33 of 56 cells (59%) are excluded as two-sided market-makers or systematic
price-improvers. This is strongest exactly where a naive leaderboard would send us:

- **crypto (btc/eth up-down):** 6 of 8 cells are two-sided on **77–100%** of markets —
  pure spread market-making on a date-blind instrument. Uncopyable by a directional taker.
- **tennis (Wimbledon):** 13 of 19 cells two-sided on **39–98%** — the "top" tennis
  wallets are booking both sides, not predicting.
- **mlb:** 6 of 8 cells two-sided on 30–84%. The two highest raw-surplus MLB wallets
  (+10.5%, +8.8% @ their price) are **both** ≥32% two-sided — their profit is largely
  liquidity provision, not a copyable read.

A leaderboard that ranks by raw PnL would tell us to follow these wallets. The mechanism
classifier says: you cannot — they make money by being on both sides, and you can only
take one. (Threshold: two-sided ≥30% of markets, or fills ≥3¢ below the fleet mean; the
raw `two_sided_frac` is reported per cell so the 30% line is auditable. In-play/late
entries are **not** separable on this archive: `ts`/`resolved_at` are backfill/crawl
stamps, D1 — reported as a known limitation, not a clean flag.)

## Where the genuine directional signal actually is (the watch-list)

Strip the market-makers and the tax, and a small, *real but uncertifiable* directional
signal remains — concentrated in **soccer**, not in the sharp markets:

| wallet | sport | matches | dates | surp@them | surp@us | LB@us evN | LB@us **day** | sel-null p |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0xe9a6ed2e4d… | soccer | 58 | 19 | +10.9% | +9.6% | −1.2% | −9.3% | 0.172 |
| 0x56f0321917… | soccer | 41 | 11 | +11.3% | +10.0% | −1.6% | −12.4% | 0.221 |
| 0xd48a81db62… | mlb | 107 | 9 | +3.6% | **+0.6%** | −8.8% | −31.9% | 0.195 |

- The two soccer wallets have **genuine, large point surplus that survives the tax**
  (soccer tax ≈ 0) and are **not** market-makers (1-of-84, ~0% two-sided — verified
  against raw SQL). But they fail every bar: LB < 3% even at event-N (N=41–58, high
  variance), only 11–19 World-Cup dates (day-deflation → −9% to −12%), and a
  selection-null p of 0.17–0.22 ≫ 0.01 — indistinguishable from random same-(band×date)
  selection. **Point estimate, not evidence.** Textbook Item-7 power limit.
- The one genuine MLB directional wallet (0xd48a81db62, 1-of-107 two-sided) has +3.6% at
  its price → **+0.6% at ours: the ~3¢ MLB tax ate 83% of the edge.** This is the
  copyability thesis made concrete — a real sharp whose edge does not survive our entry.
- **Robustness of the 0-count to the exclusion threshold:** even if we ignored two-sidedness
  and trusted MLB's single best wallet (0xd1ed12197b, +10.5%@them, +7.6%@us, 34%
  two-sided), it clears event-N (LB +3.1%) but is sunk by the **day-deflation** to −8.2%
  on only 4 MLB dates. The accrual wall, not the exclusion, is what makes the answer 0.

## Kill criteria — disposition

- **K1** (self-test) — PASS (8/8): injected copyable specialist → Trusted; coin-flip →
  not Trusted; timing-only → K2 dead@our; market-maker & price-improver fixtures →
  excluded; genuine directional predictor → not excluded; noise family → 0 FDR survivors;
  selection-null recovers an injected selection edge (p=0.0005).
- **K2** — FIRED for 8 cells: real edge at their price, ≤0 at ours (MLB the modal case).
  Reported with the tax that killed each.
- **K3** — the certified per-sport follow-set is **empty**, so there is no treatment arm
  to beat blind global tailing on forward rows. Reported loudly: specialist selection adds
  nothing certifiable here *today*; the incumbent (global leaderboard tailing, itself
  uncertified) stands unchallenged. The forward paired-lift instrument is specified and
  activates the moment ≥1 specialist certifies (Phase 5 below).
- **K4** — FIRED and dominant: the sports' top wallets are market-maker-dominated (59%);
  crypto up-down and much of tennis are structurally uncopyable. Publishable finding.

## Phase 5 — the earned follow-set proposal (silent, default-OFF) + forward test

The certified set is **∅**, so the honest proposal is: **keep `CONSENSUS_TRUST_ARMS=false`
and `trusted_only` OFF** — nothing has earned the arm. Proposed (not applied) values live
only in this doc; no env is touched, no migration written, live behavior byte-identical.

The forward paired-lift test (activates when the set is non-empty): for each forward
consensus row in a certified specialist's sport, compare the specialist-weighted vote's
realizable surplus @ `entry_ask` against the blind global-leaderboard tail on the same
row, paired, forward-only, one hypothesis slot. Re-run `specialist_mining.py` after each
accrual block; promote nothing until a cell clears `lo_day > 3%` on ≥2 disjoint cuts AND
selection-null p ≤ 0.01.

**Watch-list (with re-read triggers):**
- **soccer 0xe9a6ed2e4d…, 0x56f0321917…** — genuine directional, tax-surviving, but
  power-limited. Re-read after the next major soccer block adds independent dates (WC
  ends imminently → soccer date density collapses; realistically club-season months).
- **mlb 0xd48a81db62…** — the tax-killed sharp. Re-read if the measured MLB tax falls
  (denser at-open capture) OR the wallet's edge widens past ~3¢ with accrual. MLB dates
  accrue daily → the fastest-growing floor cell; re-read at +20 MLB dates.
- **NBA / NFL** — calendar-blocked (0 cells ≥30 matches; ~0 in-season games on the
  archive). Auto-onboard Sept/Oct when their seasons start; no shortcut.
- **politics** — thin (grows toward the Nov-2026 midterms); baseline only for now.

## Reproduce

```
scripts/specialist_mining.py --self-test    # K1 battery (no DB)
scripts/specialist_mining.py --json         # live per-sport mine + copyability gate
```
