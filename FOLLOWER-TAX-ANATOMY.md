# The Follower Tax: what it's made of, why we missed it, and what survives

**2026-07-14.** Branch `feat/follower-tax`. Paper/analysis only — nothing here touches the live path.

Follows the same-day retraction on `feat/niche-rosters` (74555a5), which measured a 3.4–4.6¢
follower tax and concluded **"COPY-TRADING IS DEAD."** This run decomposes that number instead of
reporting it. Two of the retraction's three load-bearing claims are **wrong**, and the verdict
changes from *dead* to **alive in one structurally-protected cell.**

Instruments (all self-testing, `scripts/niche/`): `tax_anatomy.py`, `net_surface.py`,
`copy_vs_blind.py`, `favband_forensics.py`, `tax_by_band.py`.

---

## TL;DR

| the retraction said | what the decomposition shows |
|---|---|
| tax = 3.4–4.6¢ | **understated.** On the price a taker really pays: 4.1–4.6¢ at 5s, worse at longer lags. |
| "their fill IS the move — they take the top of book and every follower pays the next level" | **REFUTED.** The tax *falls* with their size ($0–3 → 8.2¢; $37+ → 3.9¢). Impact rises with size. It falls. And these wallets bet a **median of $10** — a $10 order cannot jump a book 3.4¢. |
| net = edge − **3%** ⇒ dead at every lag | **the 3% is not a measurement.** It is `slippage(0.01)+fee(0.02)` (RESEARCH.md:24). The slippage is **double-counted**; the fee is **~3× the real one**. True cost ≈ **0.9¢**, not 3¢. |
| **copy-trading is dead** | **No.** Pooled, it is *indistinguishable from zero*. In the **80–100¢ band it CERTIFIES**: raw net **+2.99¢/share** [+0.76, +5.00], p=0.005, **830 markets**, **+2.62¢ over a matched blind baseline** (p=0.000, survives Benjamini–Hochberg). |

---

## 1. What the follower tax is actually made of

Four things it is **not**, each ruled out by a test that could have gone the other way:

1. **Not a measurement artifact.** A taker order that walks the book prints at rising prices under
   its *maker counterparties'* wallets — so wallet-level self-exclusion (what `copy_econ` does)
   would let a wallet's own book-walk back in as "other wallets' prints". Re-measured with
   **on-chain tx-level exclusion**: the tax is unchanged to 4 decimals. (It is structurally zero:
   a follower's cost is measured on *taker* prints, and an order's own counterparties are all
   *makers*.)

2. **Not microstructure.** A genuinely blind taker buy carries ~0 tax. There is no generic cost of
   crossing the spread here.

3. **Not their market impact.** The tax runs **backwards** in their size:

   | their fill size | 5-min tax |
   |---|---|
   | $0–3 | **+8.16¢** |
   | $3–6 | +5.67¢ |
   | $6–12 | +5.45¢ |
   | $12–37 | +4.49¢ |
   | $37–5000 | **+3.85¢** |

   Impact scales *with* size. This scales *against* it. Whatever moves the price, it is not their order.

4. **Not something they cause at all.** The event study (price path in event time, normalised to
   their fill, LOCF over 2.8M prints):

   | t rel. to their fill | −1h | −15m | −5m | −1m | **0 (their fill)** | +10s | +5m | +6h |
   |---|---|---|---|---|---|---|---|---|
   | P(t) − P_them | −3.25¢ | **−6.05¢** | −5.59¢ | −4.24¢ | **0** | +2.71¢ | +4.31¢ | **+5.48¢** |

   **The price is already rallying for 15 minutes before they buy.** The pre-move (+6.05¢) is as
   large as the post-move (+5.48¢), it runs monotonically *through* their fill, and it never
   reverts. They are **mid-wave, not the origin of it.** We have been copying laggards.

### What it IS: information, capped by headroom

Banding on **their entry price** (not the execution price — banding on the latter conditions on the
move and manufactures the answer):

| entry band | headroom (1−p) | **TAX** | tax / headroom |
|---|---|---|---|
| 0–20¢ (longshots) | 0.890 | **+10.33¢** | 0.116 |
| 20–40¢ | 0.708 | +7.01¢ | 0.099 |
| 40–60¢ | 0.489 | +3.75¢ | 0.077 |
| 60–80¢ | 0.315 | +1.70¢ | 0.054 |
| **80–90¢** | 0.161 | **+1.32¢** | 0.082 |
| **90–100¢** | 0.053 | **+1.88¢** | 0.353 |

**The tax runs 8× from longshots to favourites, and it tracks the room the price has left to run.**
A price at 0.10 can rally 10¢ against a follower; a price at 0.90 hits the 1.00 boundary first and
physically cannot. The pooled "4.6¢" is an average over this curve, dominated by the mid- and
low-priced trades — **it never applied to the band we actually trade.**

**The mirror test refutes the pure-geometry version, and that matters.** If headroom alone drove
the tax, a *SELL* (whose headroom runs down toward 0) would show a tax scaling with p. It does not:
sell-side taxes are ≈0 at every band. So the correct synthesis is two-factor —

> **tax ≈ (the information in their BUY) × (the room the price has to express it).**
> Their **buys** carry information and the price moves. Their **sells** are exits, carry none, and
> cost a follower nothing. Headroom **caps** the informed move; it does not create it.

**Therefore our edge survives exactly where the tax cannot reach. That is arithmetic, not luck.**

---

## 2. Why we didn't find this sooner

Five causes, in increasing order of how much they should bother us.

1. **The instrument did not exist.** The follow-on price is only computable from a *market-side*
   tape (`/trades?market=`), which we first harvested **on 2026-07-14** — the same day. Before
   that we held a wallet-side tape, in which the price a follower would have paid is simply not a
   recorded quantity. You cannot measure what you did not collect.

2. **The tape was silently half-missing.** `/trades` defaults to `takerOnly=TRUE` and serves only
   the taker side (~60% of fills invisible). Even after harvesting, the tax would have been
   measured on a biased tape until that default was found. (Same class as the `startTs` bug.)

3. **We assumed the cost instead of measuring it — twice, in opposite directions.**
   - The **1.3¢ tax** came from an old audit and was carried forward as a constant. It was ~3.5× too small, and it inflated the edge.
   - The **3% capture cost** (`slippage 1% + fee 2%`) was *also* never measured. It is ~3× too large, and it produced the DEAD verdict. The 1% slippage is **double-counted** — `copy_econ` already prices entry at a real follow-on taker print, which *is* the spread — and the real Polymarket taker fee is `feeRate·p·(1−p)` (≈0.7¢ for sports at p=0.6, and it **vanishes** at the favourite band), not a flat 2¢.

   > **The lesson, and it generalises past this repo:** we were rigorous about measuring *edges* and
   > careless about *costs*, treating them as conservative constants. **An unmeasured cost is a free
   > parameter that silently decides the verdict** — in whichever direction you happened to guess.
   > Worse, "conservative" felt like rigor, so nobody audited it. The tax-sensitivity check even
   > said *"breaks even at 4.7¢ vs ~1.3¢ measured — healthy buffer"*, which manufactured confidence
   > in a number that had never been measured at all.

4. **We pooled a cost that is not poolable.** The tax is an 8× function of price band. Reporting one
   number for it guaranteed the favourite band's result would be swamped by the longshots'.

5. **The instrument could fail silently.** The `psql()` helper (inherited from `copy_econ.py`) runs
   without `ON_ERROR_STOP`, so **psql exits 0 on a failed query and hands back an empty CSV**. A
   1,109-wallet IN-list blew the container's 64MB `/dev/shm`, and the script reported a clean
   `0 signals` null result rather than crashing. Fixed here; **`copy_econ.py` still has it.**

---

## 3. What we do about it

### The edge that survives: copy, but only in the favourite band

| property | value |
|---|---|
| raw net (5s lag, real fee) | **+2.99¢/share** [+0.76, +5.00], p=0.005 |
| vs matched blind baseline | blind = **−0.39¢**; **surplus +2.62¢** [+1.24, +4.00], p=0.000, BH-clean |
| markets | **830** (out-of-sample, window B) |
| **lag sensitivity** | **NONE.** 2s +2.87 · 15s +3.08 · 30s +3.44 · **5m +2.72** |
| is it just momentum? | **NO.** Every roster-blind momentum policy is *negative* (−0.2% to −1.6%). The wallets are load-bearing. |
| worth | 7.8 signals/day · **+$1.66/signal @ $50** · **≈ +$13/day** (LB +$3.30) |

Three consequences:

- **There is no latency race.** The edge is flat out to 5 minutes. This is the single most useful
  operational fact in the run: it means a simple poll-and-execute loop suffices, and it retires the
  "we must be fast" framing (consistent with `project-polymarket-latency`, which already retracted it).
- **We cannot route around the roster.** Momentum does not replicate it, so the signal really is
  *who traded*, not *what the price did*. Keep the roster.
- **It is robust, and robust along the predicted axis.** Across 27 (ranker × floor) rosters, every
  **magnitude** ranker is positive in the band (a_pnl +1.2% at p=0.000 on **12,734 markets**;
  a_surplus +4.3%; a_raw +3.2%; eb_shrunk +3.0%) while every **consistency** ranker is ≈0 (sharpe,
  t_stat, signcons, both_halves). That reproduces "magnitude works, consistency is the wrong filter"
  from an entirely independent measurement. A scan artifact would not sort itself along the
  theoretically-predicted axis.

### The highest-leverage action: re-run every arm that was killed by the 3% constant

This is worth more than the copy edge itself. The `margin = slippage(0.01)+fee(0.02) = 3%` gate is
wired into the **live board** (`board.rs::render`), the certification bar, and *every* negative
verdict in the graveyard — per-sport conditioning (0/7), cross-market bands (0 cells), the fade
inversion, exec-policy. **Some of those arms were killed by a phantom 2.3¢.** The favourite band is
precisely where the real fee vanishes, and it is precisely where we already trade.

### What NOT to do

- **Don't chase the pre-ramp.** It is real (+6¢ in the 15 min before their fill) but naive momentum
  on it loses money. Whatever starts the wave, a trailing-price rule does not capture it.
- **Don't reopen longshots.** 0–40¢ carries a 7–10¢ tax. It is the most structurally hostile region
  on the board for a follower.
- **Don't bank this yet.** 830 markets, one harvest, a skewed payoff (favourites win small and often,
  lose big and rarely) — the mean is established, the *drawdown* is not. This earns a
  **pre-registered forward paper test** on the `honest-pnl` ledger, not money.

---

## 4. Status

**CANDIDATE, not certified.** The mechanism is now understood and the cost model is measured rather
than assumed. The claim being carried forward is narrow and falsifiable:

> Copying magnitude-ranked wallets, **restricted to entries executable at ≥80¢**, nets ~+3¢/share at
> any lag up to 5 minutes, against a real fee of ~0.5¢ — and beats a matched blind favourite
> baseline by +2.6¢.

Next: forward paper test (pre-registered), then the 3%-gate audit across the parked arms.
