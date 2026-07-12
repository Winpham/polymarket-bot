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
