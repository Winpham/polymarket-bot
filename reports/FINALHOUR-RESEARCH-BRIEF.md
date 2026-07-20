# BRIEF — final-hour favourite arm: what is established, and what must be decided

You are researching ONE candidate approach for a CS-adjacent quantitative trading problem. Read this
whole brief before starting. Everything here is measured unless marked otherwise. **Your value is in
finding what is WRONG, not in confirming what is hoped.** A well-evidenced "this cannot work" is a
more valuable deliverable than a speculative "this might".

## The venue and the instrument

Polymarket **US** (regulated, separate book from the international venue). Binary game-winner
markets on tennis ATP/WTA, slugs like `aec-atp-<a>-<b>-YYYY-MM-DD`. 1 share pays $1.

Local data, all read-only, all verified working:
- Postgres at `127.0.0.1:5432` (`postgresql://bot:bot@127.0.0.1:5432/polymarket`), started via
  `docker compose up -d postgres` in `~/polymarket-bot` (NEVER bare `up` — the compose file also
  defines live trading containers).
- `us_mid_tape` — live full-book capture (real `best_bid`/`best_ask` + size + depth at 1c/2c/5c),
  ~2,700 rows/min, from the venue MARKET_DATA websocket. **One book per slug: the LONG side's.**
- `finalhour_feed_tape` — paired ESPN game-state x book series, 60s polls (migration 049).
- `~/polymarket-archive/us_markets.parquet` — market metadata incl. orientation. Refreshed daily.
- `us_time_sales/*.parquet` — 24.9M historical prints.
- Official settlement: `https://gateway.polymarket.us/v1/markets/{slug}/settlement` (free, no auth,
  needs a browser User-Agent or it 403s).
- Code: `~/polymarket-bot/wt/capture/scripts/niche/finalhour_*.py`; prereg in `reports/`.

## The claim under test

A thin US book underprices the LEADING favourite in the final ~30 minutes of a near-decided match.
Retrospective: **+6.29¢ at −0.5h**, ATP/WTA +7.55¢, ITF +3.94¢, esports +4.51¢; survives a 3¢
haircut (+3.4¢, p=0.025); not concentration-driven; anchor not circular.

**THE LOAD-BEARING CAVEAT.** The measurement is **maturity-anchored** — the window is located by a
timestamp knowable only AFTER the fact, and **every live-knowable PRICE anchor is negative**. λ (the
information fraction) is **0.44 [LB 0.22] at −30min but 0.10 [LB 0.00] at −45min** — modest, slow
information that is gone ~15 minutes early. λ=0.73 was RETRACTED as overstated. The effect is also
**exploratory-search derived** (multi-cell over horizons/bands/anchors), so nominal p overstates.

## Costs, measured (do not re-assume these)

- Taker fee **0.06·p(1−p)**, verified: `feeCoefficient=0.06` on all 247,847 markets.
- Tennis in-band spread: median **1.00¢** (mean 1.32¢) ⇒ half-spread ~0.5¢.
- **One-way toll ≈ 1.43¢ ≈ 1.77% of stake.** There is **no exit spread** — this is
  buy-and-hold-to-settlement, so the round-trip toll that killed the maker arms does not apply.
- Depth: median touch **9,314 shares** (a $50 ticket ≈ 61 shares) but **p10 = 10 shares**.
- **5.3% of expired tennis markets settle NON-binary** (0.35–0.68): voids/abandonments return a
  mark, not a verdict.
- Payoff shape at mean ask 0.809: win +0.191, loss −0.809 ⇒ **hazard/reward 4.24×, break-even hit
  rate 80.9%**.

## The live result that reframes everything (2026-07-19, ~7h, 18 matches — PRELIMINARY)

Funnel: 18 live → 11 near-decided → 10 mapped → 6 leader-is-long-side → 4 quoted → **0 in band.**
**16/16** near-decided observations priced **ABOVE 0.92** (min 0.940, median 0.965). Zero fires.

**Lateness.** Ask 10 min BEFORE the trigger vs at the trigger:
`0.870→0.970`, `0.870→0.990`, `0.820→0.950`, `0.940→0.950`. **The book re-rates ~+10–13¢ before our
trigger fires — a larger move than the +6.29¢ edge being chased.** Prices DO traverse the band on
the way up (0.57→0.99, 0.71→0.99), so the band is reachable; **the trigger is late.**

**The gradient (279 obs, exploratory).** Price rises monotonically with how decided the match is:

| candidate trigger | fires | in band | median ask |
|---|---|---|---|
| up 1 set | 200 | 52% | 0.880 |
| + ≥1 game | 132 | 45% | 0.940 |
| + ≥2 games | 69 | 16% | 0.950 |
| + ≥3 games (frozen trigger) | 16 | **0%** | 0.970 |

**There is no game state that is both clearly-winning and cheap.** That is the signature of a market
pricing game state CORRECTLY — i.e. the null hypothesis.

Scale is ~10 MINUTES, so 60s polling (~1%) and execution latency (~0%) are irrelevant. Rust,
colocation and faster HTTP optimise a number that is not the problem.

## Structural constraints you must respect

1. **Orientation.** The long side is `side_desc[i] where side_long[i]` — NOT `outcomes[i]`. Those
   arrays are reversed on **23.9%** of tennis markets. Verified 13/13 vs ESPN winners × settlement;
   the `outcomes` reading scored 0/13. Reading it wrong buys the LOSING side.
2. **One book per slug.** `us_mid_tape` carries only the LONG side's book. When the leader is the
   SHORT side there is no ask for the side you would buy ⇒ genuinely unfireable. This is the real
   cause of the documented "~50% coverage" ceiling. ~44–58% of near-decided observations.
3. **ESPN exposes set + game only.** No server/possession, no point-level (15-30-40), no
   plays/commentary resource for tennis. Verified across 735 competitions. It is a SNAPSHOT api —
   within-match timing cannot be reconstructed after the fact at any price.
4. **Power.** Simulated on the empirical ask distribution (per-event sd 0.3843), one-sided 95%
   bootstrap LB: N=60 → power **0.38** at +6.29¢ (MDE +10.82¢); N=250 → 0.80; at a realistic +4¢,
   N=250 → 0.41 and you need ~900. The frozen gate is **N≥250**.
5. **Reliability metrics do not discriminate.** At N=250 the longest losing streak is **4 whether
   the true edge is +6.29¢ or exactly ZERO**; "% periods green" moves only 50%→80%. Detection is
   ROI LB and λ. Nothing else.
6. **ToS.** bo3.gg (esports) is ToS-HELD — `robots.txt` disallows `/api/`. Any data source you
   propose MUST have its terms checked; a paid or scraped feed is not automatically acceptable.
7. **Everything fails CLOSED.** A dead tape or stale snapshot yields "no signals qualified", which
   is indistinguishable from "no edge". Absence of signals is not evidence of absence of edge.
8. **k=0.** No live order is authorised. Paper only. A green gate does NOT authorise an order.

## The project's base rate (respect it)

Five arms — copy-trading, consensus, weather, collapse-avoidance, favorite_v2 — all had BETTER
retrospective numbers than this one. All are dead. Four reversed sign when a control or a real
executable ask was finally added. The single most common failure was **an entry price that was not
a real, decision-time, executable ask**. The second was **a stale belief that was never overwritten**.

The governing document is `reports/PREREG_20260719_final_hour_favourite_v3.md`. The standing
certification bar: walk-forward + λ CI LB>0 + realizable price + live-knowable trigger.

## THE OPEN QUESTION that may decide everything

Does the BOOK move before or after ESPN publishes a score change?
- **Book LEADS the feed** ⇒ unfixable at ANY speed; the price already contains the information.
- **Book LAGS the feed** ⇒ the feed is usable and we are merely triggering on too late a state.

`scripts/niche/finalhour_leadlag.py` measures it (5s ESPN polling vs ~1s book path). First run was
INCONCLUSIVE (130 polls, 0 score changes — run outside live hours). Scheduled daily 13:05Z.
**Treat this as UNRESOLVED. If your approach depends on the answer, say which answer it needs.**

## What a good deliverable looks like

- Grounded in THIS data. Run queries. Cite numbers you personally computed, with the query.
- Explicit about which measured constraint above would kill your approach, and at what threshold.
- Honest about power: state the N your approach needs and the calendar time that implies.
- If your approach cannot clear the ~1.77% toll on realistic assumptions, say so plainly and stop.
- Distinguish what you VERIFIED from what you INFERRED. Never present a hoped-for number as measured.
