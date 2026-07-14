# US VENUE — market map, book depth, and the mapper's verified coverage

**2026-07-13.** Phases A and B of the US-venue-port run. Read-only throughout; no order was
placed on either venue. Reading a public API is not trading.

---

## The one-line verdict

**The sports arms transfer. The weather arm does not.** The US book is real, deep enough in
our band, and *pays makers* — but our best arm has almost no tradeable surface there.

| | Kill Gate | result | |
|---|---|---|---|
| **A** — can the US book support $50 clips in our arms' families? | yes/no | **$50 fills AT THE TOUCH, 0.00¢ slippage** | ✅ PASS |
| **B** — do ≥50% of our fired signals map to a US instrument? | ≥50% | **sports 51.8% · weather 3.5%** | ⚠️ SPLIT |

---

## PHASE A — the US book is real

`gateway.polymarket.us` is public, unauthenticated, and holds **224,614 markets**.

**Depth, measured live in our certification band (ask 0.71–0.90):**

| | sports (n=15) | climate (n=3) |
|---|---|---|
| $ resting at the touch (p50) | **$3,955** | $41 |
| $50 clip fillable | **100%** | 100% |
| slippage vs touch, $50 (p50/p90) | **0.00¢ / 0.00¢** | 0.96¢ |
| $250 clip slippage (p90) | 0.62¢ | 5.20¢ |
| ask levels (p50) | 10 | 7 |

**$50 clips fill at the touch with zero slippage in sports.** Capacity is not the wall. The
climate book is genuinely thin (~$41 at the touch) but still fills $50.

**Fees — confirmed twice, independently.** From `docs.polymarket.us/fees` *and* from
`feeCoefficient: 0.06` present on **every one of 224,614 markets**:

- **taker** `Fee = 0.06 × C × p × (1−p)` → **1.20¢/share at p=0.80**
- **maker** coefficient **−0.0125** → **the maker is PAID ~0.25¢/share**

That is a **~1.45¢/share swing** on a total measured edge of only 3–7¢. Given our single most
robust finding — *the edge is in the FILL, not the pick* — **a venue that pays you to make
may matter more than the pick itself.** This is the most valuable open hypothesis in the run.

**No copy signal exists on the US venue.** `/v1/trades`, `/v1/leaderboard`, `/v1/activity`,
`/v1/positions` all **404**. Confirmed. The signal can only come from the international book;
that asymmetry is the entire premise of the design and it holds.

### Two gateway traps (both silent, both cost me time)

1. **Every query param except `limit`/`offset` is IGNORED.** `?category=climate`, `?sport=`,
   `?q=`, even `?orderBy=` return the *same unfiltered page*. A filtered fetch looks like it
   worked and quietly returns the wrong rows. **Filter client-side.** (Same class as the
   data-api ignoring `startTs`, which once cost us most of a history.)
2. **There are 224k markets, not the ~20k a truncated scan suggests.** My first scan stopped
   at a bound and concluded *"climate is dead, newest market is 2026-05-06."* **Both were
   false** — artifacts of truncation. Page to genuine exhaustion (an empty page), never to a
   bound.

---

## PHASE B — the mapper, and why its coverage number is trustworthy

No shared key exists: no `condition_id`, no `token_id`. We match on
**(league × entity set × event date × market subtype)** and resolve the **proposition**
explicitly. Fail-closed: anything under 0.90 confidence is **skipped, never guessed**.

### It is verified against the one thing that cannot lie

> **Resolution agreement: 406 / 406 settled mapped pairs AGREE. 0 disagreements.**

If the intl book says our side won and the US book says it lost, the map is broken. There is
no third explanation. **It took four rounds of adversarial testing to reach 100%, and every
single round found a real inversion bug.**

### The four bugs — each would have lost money silently

1. **Two false negatives that nearly killed the thesis on my own regex.** A too-strict slug
   pattern rejected the US venue's *exact-score* markets (200 signals written off as "the US
   has no such market type" — **false**), and the venues use **different entity codes**: intl
   ISO-3166 (`hrv`, `prt`, `nld`, `che`, `ury`, `cvi`, `cdr`) vs US FIFA (`cro`, `por`, `ned`,
   `sui`, `uru`, `cpv`, `cod`); tennis is surname (`shapova`) vs first3+last3 (`kammaj`).
   Fixing both moved coverage **20.6% → 54.9%**. *A mapper that under-reports will kill a live
   thesis by accident.*

2. **Orientation.** `outcomePrices[i]` corresponds to **`side_desc[i]`**. The `outcomes` array
   is **not reliably ordered and must be ignored** — it even disagrees with `side_desc` on the
   same market (`aec-atp-lorson-joesch`: `outcomes ["Joel Schwaerzler","Lorenzo Sonego"]` vs
   `side_desc ["Lorenzo Sonego","Joel Schwaerzler"]`). Decided by an **invariant**, not by
   taste — a 3-way soccer result must have exactly one winning leg:

   | decoding | consistent | violations |
   |---|---|---|
   | zip `outcomes`→`prices`, find "Yes" by name | 322/783 | **461** |
   | **align to `side_desc`** | **783/783** | **0** |

   *I asserted the opposite first.* The invariant test is what caught it.

3. **One fixture is many markets.** A soccer tie is `{-bra, -mar, -draw}`. Returning
   `cands[0]` is an **inverted-map generator** — we would price "Brazil win" and buy "Morocco
   win". The proposition is now read from our own title and must match the US suffix, with
   exact-score re-emitted in the **US slug's own team order**.

4. **Sub-markets masquerading as the main line.** One intl `event_slug` covers the match winner
   *and* "Set Handicap", "Set 1 Winner", "halftime-result". Mapping those onto the full-time
   moneyline is a **wrong** map, not a missing one. Skipped, fail-closed.

### Coverage (verified)

| arm | signals | mapped | coverage | gate (≥50%) |
|---|---|---|---|---|
| `elite_fresh_fav` | 177 | 115 | **65.0%** | ✅ |
| `favorite_v2` | 47 | 25 | **53.2%** | ✅ |
| `favorite` | 562 | 267 | **47.5%** | ~ |
| **sports arms combined** | **786** | **407** | **51.8%** | **✅ PASS** |
| `weather_fav` | 452 | 16 | **3.5%** | ❌ **FAIL** |
| blended | 1,238 | 423 | 34.2% | ❌ |

---

## The finding that matters most: the weather arm has no venue

**Our best arm — the LODO survivor, `selection_null` p=0.0005 — is effectively untradeable in
the US.**

- We fire weather signals on **49 distinct cities**: london, qingdao, paris, shenzhen,
  toronto, amsterdam, istanbul, madrid, seoul, kuala-lumpur, milan, cape-town, tokyo, wuhan,
  hong-kong, shanghai, taipei, buenos-aires, wellington, tel-aviv, ankara, moscow, karachi…
- **The US venue lists five**: `nyc`, `mia`, `mdw`, `lax`, `sfo`. All American.
- **404 of 452 weather signals have no US instrument at all.** That is not a mapper gap; it is
  the venue.

And even the 16 that do map carry a **resolution hazard**: the US contracts settle off the
**NWS Climatological Report at a specific station** — `mdw` is Chicago *Midway*, not "Chicago".
Same city name ≠ same contract. Any live use must confirm resolution agreement per station,
not merely match a city.

**This reshapes the run.** The thesis now rests on the **sports/favorite arm**, not on weather.
Phase D must be run on the sports arms, and any weather result there is powered by ~16 signals
— nowhere near the frozen gate's ≥20 resolution-day clusters. *We should say plainly that the
weather arm does not port, rather than torture 16 signals into a verdict.*

---

## What is still unknown (and what Phase C/D must answer)

- **The basis.** At the instant our signal fires internationally, has the US ask already moved?
  If yes, the edge is gone before we act. If no, it may be *larger* there. **Requires a matched
  placebo pool** — this is the exact trap that produced the RETRACTED "15 min = 8¢" latency
  claim (which collapsed to +2.05¢ ± 4.0¢, p=0.36 once a placebo was added).
- **Does the edge certify at the US ask, after the US fee?** The frozen gate, unchanged, on the
  sports arms. Taker leg **and** maker leg.
- **Maker fill rate.** The rebate is only real if a resting order actually fills. **Never ship a
  fill rate we did not observe.**
