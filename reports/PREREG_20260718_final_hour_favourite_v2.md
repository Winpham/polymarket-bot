# PRE-REGISTRATION v2 — final-hour favourite late-convergence, forward paper test

**Frozen 2026-07-18. Supersedes `PREREG_20260715_final_hour_favourite.md`. Paper/analysis only.
No live order, ever.**

**Legitimacy of this amendment:** the v1 prereg permits change only *before* signals accrue
(`changes require a new dated PREREG and reset the count`). Verified at time of writing:
`SELECT count(*) FROM finalhour_paper_signals` = **0**. No data has been observed, so no
outcome-dependent choice is possible. The count starts from zero under this document.

**Amendment principle (binding on this document):** only changes *forced by verified fact* are made
— a stale statistic, an unimplementable trigger clause, and a silent-failure hazard. Every
discretionary change that could plausibly improve the apparent result was **declined** and is listed
in §7. The gate thresholds, price band, universe, and retract conditions are **carried over
unchanged**.

---

## 1. What changed from v1, and why

### 1.1 λ corrected downward (FORCED — stale number)
v1 cited **λ=0.73 [0.51, 0.91]**. The Phase-9 adversarial audit (`CONFIDENCE-FORENSICS.md` §PHASE 9,
commit `05b0e10`) found this **overstated**: it measured the CLV "close" only 5 minutes before
resolution, where the price is near-degenerate. At a *fair tradeable close*:

| horizon | λ | LB |
|---|---|---|
| −30 min | **0.44** | **0.22** |
| −45 min | **0.10** | **0.00** |

Honest reading: **modest, slow information** — the thin book grinds the near-decided favourite up
over the final ~30 min. It is *not* a fast re-rating. v1's "strong information" framing is withdrawn.

**Operational consequence (the important part):** λ is ~0 by −45 min. The edge lives in a narrow
late window, so **trigger latency is a first-order risk, not a detail**. See §4.

### 1.2 Retrospective profit figures — carried over, with the audit's caveats attached
The ¢ figures were **not** retracted by the audit and are restated unchanged: ATP/WTA −0.5h
**+7.55¢**, ITF **+3.94¢** (n=840), esports **+4.51¢**; and **+6.29¢** at −0.5h in the Phase-7 US
measurement. Two caveats travel with them permanently:
- **Survives cost:** +3.4¢ (p=0.025) after a 3¢ haircut — profit is robust to realistic cost.
- **Exploratory search:** these came from a multi-cell search over horizons/bands/anchors, so
  **nominal p-values overstate significance**. This is precisely why the forward gate exists.
- **Maturity-anchored:** the window is located by an anchor knowable only after the fact. All
  *live-knowable price* anchors are negative. The edge's capturability is an **untested assumption**
  that a live feed locates the same window — that assumption is what this test measures.

### 1.3 Trigger re-specified to what the feed can actually express (FORCED — v1 was unimplementable)
v1's trigger read: *"a player is up 2 sets (best-of-3) OR serving for the match."* Both clauses fail:

- **"Serving for the match" is not observable.** Verified 2026-07-18: across 735 competitions the
  scoreboard payload carries **no server/possession field and no point-level (15-30-40) score** — the
  competition object exposes only `status`, `competitors`, and per-set `linescores`. On the core API
  a competition's only sub-resources are `status` and `odds`; there is **no `plays`/commentary
  resource for tennis** (`commentaryAvailable: false` on the sampled match). Set- and game-level
  state is all that exists.
- **"Up 2 sets" is incoherent for best-of-3** — being up two sets *ends* a bo3 match.

**Frozen replacement — the definition already implemented and now live-verified**
(`finalhour_forward.py::match_state`):

- **Leader** = more completed sets; ties broken by the game lead in the in-progress set.
  (A set counts as completed when `max ≥ 6` and (`margin ≥ 2` or `max == 7`).)
- **Near-decided, best-of-3:** leader has **≥1 completed set** AND leads the in-progress set by
  **≥3 games**.
- **Near-decided, best-of-5** (ATP Grand Slam, `event.major`): leader is up **≥2 completed sets**
  with a net set lead ≥1 AND is **at least level** in the in-progress set.

Both are derivable purely from `linescores`, which is what the feed provides.

### 1.4 Instrument-liveness precondition added (FORCED — silent-failure hazard)
See §4. This condition can only ever **reduce** the number of admissible signals, never inflate the
result, so it cannot function as a post-hoc favourable edit.

---

## 2. Hypothesis (unchanged in substance)
A thin US book underprices the LEADING favourite in the final ~30 minutes of a near-decided game.
It generalises across three independent regimes (ATP/WTA, ITF, esports) — clearing the ≥2-regime
durability bar that `favorite_v2` failed. The audit further confirmed the effect is **not
concentration-driven** (win 89.7% @0.825; top-5 events only 11% of P&L; survives their removal) and
that the **anchor is not circular** (maturity_time is genuinely after the last print, median +2 min).

## 3. Universe (unchanged from v1)
- US `aec-` game-WINNER markets only; standard (non-exotic per `us_native_backtest.EXOTIC`);
  liquid (≥50 prints / active book on `us_mid_tape`).
- FREE-feed subset: **tennis ATP/WTA** (ESPN hidden API). Esports CS2 is **held** — the bo3.gg ToS
  check returned RESTRICTIVE (`robots.txt` Disallow `/api/`, commit `b1e7d93`), so it is NOT part of
  the primary gate. ITF (paid feed) remains opt-in and logged separately.

## 4. Instrument-liveness precondition (NEW — binding)
Every consumer of this test **fails closed, not loud**. `finalhour_forward.py` requires a
`us_mid_tape` quote within 10 minutes and an orientation row from `us_markets.parquet`. If either is
stale, the harness reports *"no signals qualified"* — **indistinguishable from "no edge."** Both
failure modes were live on 2026-07-18:

- `us_mid_tape` had been **dead since 2026-07-16 02:39Z** (2d17h gap): main had no writer for the
  table at all; it had been run by hand from a feature worktree.
- `us_markets.parquet` was a **static 2026-07-13 snapshot** containing **0 tennis markets for
  2026-07-18** — orientation would have failed for every current match.

**Binding rule:** a signal counts toward the gate **only if**, at fire time, (a) the most recent
`us_mid_tape` write is < 10 min old, and (b) the `us_markets.parquet` snapshot contains the match's
date. A day on which either fails is **excluded from the denominator and logged as an instrument
outage** — never silently counted as "no signal." **Absence of signals is not evidence of absence of
edge unless the instruments are provably live for that window.**

## 5. Trigger / entry / costs / settlement (otherwise unchanged from v1)
Fire at most ONCE per market, at the first instant ALL hold:
1. the live feed reports **near-decided** per §1.3;
2. the US book prices that favourite in **[0.65, 0.92]** — gated on the **`best_ask` actually paid**,
   not the mid (v1 already corrected this; carried over);
3. the market is actively trading (fresh `us_mid_tape` quote within 5 min);
4. **orientation:** the YES contract's player (`outcomes[i]` where `side_long[i]`) **must equal the
   ESPN leader**, else skip. Never inferred from slug order.

Entry at the real US `best_ask`; cost = US taker fee θ=0.06·p(1−p) **plus measured** realized
slippage (not an assumed haircut); settlement = official DMR `settlement_price`; λ/CLV close = last
non-degenerate `us_mid_tape` mid in [0.02, 0.98] after entry; sizing = **PAPER**, flat $50/signal;
`warmup=TRUE` (excluded from the gate) when feed/book history at fire is <30 min.

## 6. Success gate (CARRIED OVER UNCHANGED) — clears only if ALL:
Over **≥60 clean events** (warmup=false), spanning **≥2 distinct tournament weeks with ≥1
non-Wimbledon week**:
1. event-clustered ROI **lower bound > 0**;
2. point ROI **≥ +2.0%**;
3. **λ (CLV/surplus) CI lower bound > 0**.

*(v1 also required ≥2 sports. With esports ToS-held (§3), tennis ATP/WTA is the only free feed. The
≥2-sport condition is therefore **retained as written but currently unsatisfiable**; clearing it
requires an admissible second feed. This is recorded as a **known blocker**, deliberately NOT relaxed
— relaxing a durability bar to fit available data is exactly the `favorite_v2` failure.)*

**Retract conditions (unchanged):** R1 ROI LB ≤ 0 at ≥60 clean events · R2 λ CI includes 0 at ≥60 ·
R3 edge only in Wimbledon / one tournament · R4 measured slippage+fee drives ROI LB ≤ 0.

## 7. Discretionary changes CONSIDERED AND DECLINED
Recorded so the freeze is auditable:
1. **Widening the [0.65, 0.92] band.** Declined. Retrospective near-decided states often price above
   0.92; widening would raise the event rate and is exactly the kind of post-hoc change a freeze exists
   to prevent.
2. **Relaxing ≥60 events / ≥2 weeks / ≥2 sports.** Declined (see §6).
3. **Firing when the ESPN leader is the market's NO side.** The harness currently skips these,
   halving the universe and roughly doubling calendar time to 60 events. Buying the NO side is
   outcome-neutral and symmetric, so this is *defensible* — but it materially changes the universe
   and therefore requires **explicit sign-off by Tue before any signal accrues**, not a silent
   bundling. **Left OFF under this document.**

## 8. Verification performed before freezing (evidence, not assertion)
- **Live ESPN schema — CLOSED.** The audit's open item ("needs one verification pass against a LIVE
  match; none was live at audit time") is closed. Against real in-progress payloads captured
  2026-07-18 18:58Z, the harness's **own** `match_state` parsed **3/3** live matches:
  Dzumhur `[2,7,2]` / Merida `[6,5,3]` → sets 1-1, tie broken on current-set lead → leader Merida,
  not near-decided; Krejcikova/Tauson 2-1 → not near-decided; Hodzic `[6,3]` / Webley-Smith `[2,0]`
  → **near_decided=True** (won set 1, leads set 2 by 3) — the bo3 rule firing correctly.
- **Harness self-test:** passes (fee, set-counting, leader + deciding-set tie-break, full-name matching).
- **`us_mid_tape`:** restored and persistent; ~1,450 rows/30s; crash-restart verified (~10s).
- **`us_markets.parquet`:** refreshed 2026-07-18 (247,847 markets; 145 tennis for 07-18, 392 for
  07-19); orientation resolvable **392/392 = 100%** on 07-19 tennis. Prior snapshot backed up.
- **Still OPEN:** feed *latency* is unmeasured. Given λ→0 by −45 min (§1.1), how stale ESPN's
  scoreboard is on lower-tier matches is a first-order risk. `us_quotes.capture_lag_s` is the
  existing instrument for this class of measurement and should be mirrored for the feed.

## 9. Standing bar mapping
Forward walk-forward (live is inherently OOS) + λ>0 + realizable price + live-knowable trigger.
Green here = the project's first pre-registered forward test passing on an information-bearing,
realizable-price edge. It does **NOT** authorise a live order — that remains a separate, explicit,
Tue-only decision. **k=0 remains correct.**

## 10. Superseded copies
`PREREG_20260715_final_hour_favourite.md` is marked SUPERSEDED on this branch. Identical stale copies
carrying λ=0.73 also exist on `feat/weather-cert`, `feat/weather-verify`, `feat/intl-reverify`, and
`feat/confidence-forensics`. Per `feedback-refutations-must-overwrite`, **λ=0.73 must not be quoted
from any of them.**
