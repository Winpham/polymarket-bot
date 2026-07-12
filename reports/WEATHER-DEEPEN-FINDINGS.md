# Weather Deepen — findings log

Take the merged, live-capturing weather arm (`weather_fav` / `weather_fav_liq`, default-off shadow,
enabled paper-only) and push it to a certified, copyable, per-dollar verdict at ≥ the champion
`favorite` 0.71–0.98 honest floor (+5.6% cluster-robust LB) with real power — OR the honest proof it
can't. Both outcomes are success. Paper-only; promotes nothing; incumbents byte-identical.

Inherits `reports/WEATHER-FINDINGS.md` (5-phase refinement) + `PREREG_20260712T052717Z_weather.md`
(FROZEN gate — may ADD, never loosen). Build on §0's settled facts, don't repeat them.

---

## WS1 — Capture cadence & latency (`reports/WEATHER-LATENCY.json`)

**Question:** is the ~10–15 min housekeeping capture cadence good enough, or is the realizable
weather edge decaying inside the capture window?

**Data (38 live `weather_fav` captures, first-ever executable weather asks, 2026-07-12):**

| metric | mean | median | p90 | max |
|---|---|---|---|---|
| capture lag (min) | 29.0 | 30.1 | 33.2 | 34.6 |
| spread (ask − mid) | +1.22¢ | +0.70¢ | +4.65¢ | +6.0¢ |
| adverse drift (mid − sharp) | +0.65¢ | +1.11¢ | +8.3¢ | +28.9¢ |
| **executable haircut (ask − sharp)** | **+1.87¢** | **+1.71¢** | +9.3¢ | +29.3¢ |

- **corr(lag, spread) = +0.034**, **corr(lag, drift) = −0.305** (n=38). The lag does **NOT** cause
  realizable cost — the spread is flat vs lag, and drift is if anything *lower* at longer lag (noisy,
  n=38, drift range −22.6¢…+28.9¢). So arriving ~29 min late is not where the money leaks.
- **The actual cadence is ~29 min, ~2× the assumed 10–15** (the housekeeping backlog is deeper than
  the comment estimated), yet it is not the binding constraint.
- `weather_fav_liq` (the $1k-liquidity twin) captured **0** — thin weather books are the binding **SIZE**
  constraint; a fat % on unfillable size is not a strategy.
- These 38 skew high-price (fresh july 12–14 markets, mostly deep chalk, avg ask 0.912) → the +1.71¢
  median haircut is a FIRST read, not the 0.71–0.90 cert-cell number. Re-run as cert-cell captures accrue.

**Verdict: CAPTURE-AT-DETECTION NOT WARRANTED.** Building a faster capture lane would shave ≤0.65¢ of
(uncorrelated, possibly-zero) drift and none of the 1.22¢ spread. The realizable question is the
**bid-ask SPREAD + thin-book SIZE**, not cadence. Money-saving answer: do **not** build the capture-lane
change; keep instrumenting the spread/size on the cert-cell band forward. No arm code changed.

**Realized within-window edge decay:** PENDING — needs RESOLVED captured signals (`weather_fav`
captures are days-fresh). Re-run `weather_latency.py` as they resolve to read (won − entry_ask) vs lag.

---

## WS4 — Forward certification + the real LODO-by-week (`reports/WEATHER-VERDICT.json`)

The decisive gate (LODO-by-week over ≥2 disjoint weeks) was blocked because week-2 (july 6–12) weather
convergence is **not RESOLVED in our DB**: the `trader_fills` resolver is a **42k-deep oldest-first
FIFO throttled at 200 conds/cycle** (`housekeeping.rs` → `trader_fill_unresolved_conditions ORDER BY
MIN(ts)`), so recent weather is head-of-line-blocked, and the `_blind` at-fire-mid snapshot lagged too
(only 11/557 week-2 picks had a mid). **Unblocked read-only via the public CLOB** (`weather_clob.py`,
bounded to weather conds): outcome from `/markets` winner, at-fire mid reconstructed from
`prices-history` at convergence `ts0` (no look-ahead). No pipeline change, no migration, no DB writes.

**Basis correction (a real finding, not a tooling detail).** The in-sample phase-3 `_blind`
`initial_mean_price` basis is **lag-contaminated**: validated on the w26 overlap, the CLOB-at-`ts0`
reconstruction agrees with `_blind` to **0.97¢ when `_blind` was captured promptly (≤30 min) — but
only 9/433 were**; the other **424/433 (98%) were captured >30 min late** (often *days*), landing near
resolution (0.2, 0.55…), MAE 8.9¢. So **CLOB-at-`ts0` is the correct at-fire mid; the phase-3 basis was
contaminated and *compressed* the edge toward 0.** The refined LB rises from the in-sample +9.2% to
**+15.5%** on the clean basis.

**Battery on the corrected CLOB basis (w26 6 day-clusters + w27 5 day-clusters = 2 disjoint weeks):**

| cell | base LB | LODO-by-week (drop w26) | region-day LB | Bonferroni | consensus selection_null |
|---|---|---|---|---|---|
| WEATHER 0.71–0.98 | +9.5% | **+10.8%** (5 days left) | +9.5% | +9.0% | p=0.47 **FAIL** |
| **WEATHER 0.71–0.90** | **+15.5%** | **+13.8%** (5 days left) | +14.8% | +15.0% | p=0.53 **FAIL** |

**Two results, one positive, one that reframes the whole thesis:**

1. **LODO-by-week now runs and SURVIVES.** Dropping the dominant week (w26) leaves the held-out week's
   LB at **+13.8%** (refined) — the edge is **not a single-week artifact**. This is the one thing the
   in-sample analysis structurally could not test, and on the proxy basis it passes. Region-day
   clustering (spatial-independence) holds it too.

2. **The consensus adds NO skill (`selection_null` p≈0.5).** On the corrected basis, the ≥3-backer
   CONSENSUS is indistinguishable from a single-sharp weather favorite at the same (band × day). The
   phase-3 pass (p=0.0065) does **not survive the basis correction** — it was an artifact of the
   contaminated `_blind` pool. **So the weather edge is a PRICE-BAND property of mid-favorite weather
   (0.71–0.90), NOT a consensus/copy skill.** The arm should track the band edge; the "consensus"
   framing is not where the money is.

**Caveats kept honest:**
- **Entry-timing bias unresolved.** The at-fire mid is reconstructed at `ts0` = a *sharp's* first-buy
  time; if sharps buy transient dips, this understates a late copier's entry (WS1: executable ask is
  **+1.87¢ over the sharp fill**). A neutral-reference blind pool is the next build; the FORWARD
  captured-`entry_ask` gate settles it regardless.
- **Champion correlation is uninformative here.** The reported +0.35–0.49 (and the in-sample −0.48)
  are low-variance/small-N artifacts: weather's daily return is **stably positive every day** (+0.13…
  +0.20 across 9 days) while the champion swings, so Pearson is ill-defined. Honest statement: weather
  is stably positive and does **not co-move** with the champion's swings — a diversifier in behaviour,
  but the coefficient's sign is noise.
- **Still the PROXY basis, all July.** w26/w27 predate live capture, so the frozen gate's
  `entry_ask`-only θ (≥2 disjoint FORWARD weeks) stays the arbiter — now ACCRUING (38 captures).

**WS4 verdict:** weather's mid-favorite BAND edge is real-looking and **disjoint-week-robust on the
corrected proxy basis (+13.8% LODO)** — materially *better* than the contaminated in-sample read — but
it is **not a demonstrable consensus-copy edge** (null fails on the clean basis) and its copyable
component is bounded by the executable spread + entry-timing, which only the forward captured-ask gate
resolves. Necessary disjoint-week evidence: **passed.** Sufficient frozen PASS: **still forward.**
