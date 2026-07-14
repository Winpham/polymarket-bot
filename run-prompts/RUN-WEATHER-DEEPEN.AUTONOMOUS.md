# Autonomous Run: Deepen the Weather‑Market Strategy — get `weather_fav` to (or past) champion level

> **Read this whole brief before touching anything.** You are an autonomous build worker on
> `~/polymarket-bot` (Rust + Python + SQL Polymarket consensus/copy‑trading **PAPER** system). A prior
> run discovered, refined, built, MERGED, and ENABLED a live default‑off shadow arm `weather_fav` /
> `weather_fav_liq` on daily‑temperature markets — the strongest **complement** candidate the whole
> investigation produced. Your job: **make weather a certified, copyable, per‑dollar edge at ≥ the
> champion `favorite` 0.71–0.98's honest floor (+5.6% cluster‑robust LB), with real statistical
> power** — or prove honestly that it can't and say exactly why. **Both "weather now clears the
> champion‑level gate + here is the forward proof" and "weather plateaus below champion / is eaten by
> its thin‑book spread / is forecast‑co‑reading — here is the proof" are SUCCESS. A goal‑sought green
> is failure.** If you catch yourself widening the universe or slicing cities to inflate an in‑sample
> number that dies under the belief‑blind + anti‑overfit battery, STOP — you have drifted.

---

## 0. READ FIRST — inherit the state, do not re‑derive it

- **`reports/WEATHER-FINDINGS.md`** — the 5‑phase refinement run (map → edge → battery → verdict →
  region/forensics). The load‑bearing facts below come from it; build on them, don't repeat them.
- **`reports/PREREG_20260712T052717Z_weather.md`** — the FROZEN forward gate. It is the arbiter; you
  may add cells/workstreams but you may NOT loosen its floors.
- **`scripts/weather_scan.py` · `weather_verdict.py` · `weather_regions.py` · `cell_lib.py`** — the
  instruments (all `--selftest` green). Reuse and extend them; do not fork parallel copies.
- **`STRATEGY-HANDOFF-favorite-consensus.md`**, **`DATA-MODEL.md`**, and memory topics
  `project-polymarket-weather`, `project-polymarket-cell-scan`, `project-polymarket-identify-skilled`,
  `feedback-edge-exists-prior`, `feedback-polymarket-live-betting-posture`.
- The arm: `weather_market_arms()` in `copy-trading-bot/src/scanner/consensus.rs`;
  `load_weather_window_votes()` in `common/src/storage/consensus.rs`; wired in `consensus_cycle.rs`
  behind `CONSENSUS_WEATHER_ARM` (LIVE, paper). DB: `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket -c "..."`.

**Settled — do NOT re‑litigate (build on, don't repeat):**
- Weather `weather_fav` **0.71–0.90** is the primary certification cell (drop the 0.90–0.98 deep‑chalk
  band: +0.9% ROI / −2.1% LB — the **win‑rate trap**; the arm still CAPTURES 0.71–0.98 broad, certifies
  narrow). On the at‑fire‑mid (realizable‑proxy) basis it is copyable (haircut ≈0), passes the
  forecast‑co‑reading `selection_null` (p=0.0065), is low‑correlated with the champion (−0.48), diffuse
  across 49 cities, LB robust +8.8% (region‑day, 36 clusters) → +9.2% (day).
- **THE binding limit is POWER/DURATION, not the point estimate.** All in‑sample data is one consecutive
  week (july 2–8); a second week (july 8–13) is already converged and pending resolution. **LODO‑by‑week
  and the ≥2‑disjoint‑weeks floor are the gate weather has not yet cleared.**
- DEAD ends, do not revisit as *copyable* edges: past‑PnL trader ranking (refuted 5 ways), naive
  global‑voter widening (`wide-consensus` run‑1 WITHDRAWN), finer‑than‑0.10 price bands, total‑P&L /
  win‑rate as objectives. Deep chalk 0.90–0.98 is non‑productive turnover, not profit.

---

## 0.5. THE OBJECTIVE (optimize THIS — nothing else)

> **Maximize the DAY‑clustered (and region‑day‑bracketed) cluster‑robust one‑sided 95% LOWER BOUND of
> REALIZABLE, COPYABLE ROI‑on‑turnover for the weather cell, measured at OUR captured executable
> `entry_ask` (fee `0.03·p·(1−p)`), subject to the volume + ≥2‑disjoint‑weeks + belief‑blind floors,
> that SURVIVES the anti‑overfit battery and reaches ≥ the champion's honest floor (+5.6% LB) — OR the
> honest proof it cannot.**

- **Realizable & copyable is non‑negotiable.** The sharps' own fill is the DIRECTIONAL ceiling, never
  the objective. Now that the arm is live, prefer the **captured `entry_ask`** over the at‑fire‑mid
  proxy as coverage accrues; report `entry_ask` coverage % every measurement.
- **Belief‑blind SKILL is mandatory**: surplus over the `_blind` weather favorite at the same
  band × day, PLUS `selection_null` p≤0.01 (≥1000 draws) — the guard against forecast‑co‑reading and
  easy‑day selection. Volume/turnover that adds no skill over blind is NOT progress.
- **Win rate and total P&L are DIAGNOSTICS ONLY.** More traders / more signals / more turnover are
  means, not the objective; a wider universe that adds volume but not per‑dollar LB is a FAILURE to
  report as such.

---

## 1. Mission — five workstreams, each HARD‑STOP + commit + write findings so a reaped run is salvageable

### WS1 — Capture cadence & latency (answer: "is every ~10–15 min good enough?")
The consensus cycle detects at ~2 min; `entry_ask` is captured on the first housekeeping pass
(~10–15 min post‑fire). Weather is a fast, forecast‑driven market — the executable ask may drift as
forecasts update. **Measure the realizability cost of the capture lag**, then reduce it if it's real:
- Quantify: for captured weather signals, `entry_ask_at − first_detected_at` (the lag) and the
  `entry_ask − at‑fire‑mid` haircut vs the lag — does a longer lag mean a worse realizable ask? Is the
  edge decaying inside the capture window?
- If material: implement **capture‑at‑detection for weather** (record the executable ask the instant the
  signal fires, from the CLOB `/book` already used, or the live `clob_price_tape`), and/or add weather
  to `DENSE_CAPTURE` / a faster housekeeping lane. Default‑off, paper‑only, incumbents byte‑identical.
- Deliverable: `reports/WEATHER-LATENCY.json` + the answer, and (if warranted) a default‑off capture
  improvement behind a flag. **Commit.**

### WS2 — Widen ingestion the RIGHT way: weather‑specialist DISCOVERY beyond top‑250
Your insight is correct and important: weather is a **niche** — only ~16 tracked wallets (7 carry the
volume) touch it in the top‑250, because specialists have *mediocre GLOBAL rank* (they specialize).
Global‑leaderboard rank is the WRONG filter for a niche. Do NOT just raise the global cutoff (naive
widening was withdrawn, and it floods the poller). Instead:
- **Discover weather specialists by their WEATHER track record**, not global rank: enumerate ALL wallets
  active in weather markets (from the weather markets' trade/fill feed, bounded to weather
  `condition_id`s — cheap, targeted, not a global poll), and rank them by a **sustained‑consistency /
  belief‑blind weather metric** (Sharpe‑like `mean(won−realizable_price)/sd`, shrunk for low N) — a
  HYPOTHESIS GENERATOR only. Past weather PnL alone is survivorship‑biased; candidates certify ONLY
  forward / belief‑blind at OUR realizable entry, Bonferroni over the # screened.
- Build a **weather‑specialist voter set** (a domain eligibility, not a global‑rank one) and score a new
  shadow arm (e.g. `weather_fav_wide` / `weather_fav_specialist`) on it — default‑off, alerting=false.
  Test belief‑blind whether the wider/specialist set **improves the realizable LB + skill‑over‑blind
  (not just signal count)** vs the current rank‑250 book. Respect poller/API + subscribe ceilings
  (`reference-polymarket-leaderboard-pagination`, `project-polymarket-live-ingestion`); if discovery
  needs new ingestion, keep it bounded to weather markets and flag‑gated.
- Deliverable: `reports/WEATHER-SPECIALISTS.json` (discovered set + belief‑blind ranking + the
  guard) + a default‑off wider/specialist arm if it earns one. **Commit.**

### WS3 — More evergreen niches like weather
Weather is one evergreen daily market; there may be others the rank‑40 gate hides. Extend the cell scan
(`cell_map.py`/`cell_scan.py` from the generalize‑band run) to enumerate other **daily / recurring,
tournament‑independent** venues (other weather types — rain/wind/high‑low; daily crypto up/down; any
recurring daily prop) and measure each on the LOCKED objective, belief‑blind, day‑clustered, at
realizable entry. Flag under‑powered ones INDETERMINATE. Report which (if any) clear the belief‑blind +
copyable bar — a second evergreen complement would be as valuable as improving weather.
- Deliverable: `reports/EVERGREEN-SCAN.json` + a one‑paragraph verdict per niche. **Commit.**

### WS4 — Signal quality, confidence & power (the certification engine)
- **Accrue + certify forward**: the arm is live. Re‑run `weather_verdict.py` as july 8–13 + subsequent
  weeks resolve; the moment a **second disjoint week** exists, run the real **LODO‑by‑week** and the
  ≥2‑disjoint‑weeks floor. This is the single highest‑value confidence gain and it's already in motion.
- **Sub‑cell refinement (mechanism‑only, a‑priori)**: is the edge broad or is it carried by specific
  regions/bands? Use the region map; require every cut to have an a‑priori mechanism you'd predict
  BEFORE looking (never "drop whatever lost"). Keep the honest independent‑N **bracket** (day ↔
  region‑day); never report one inflated number.
- **Confidence math**: report the LB with `entry_ask` coverage %, bootstrap 2nd opinion, Bonferroni over
  every cell/arm tested, and `selection_null` every time. More signals only count if the LB and skill
  hold.
- Deliverable: an updated `reports/WEATHER-VERDICT.json` (with the forward weeks) + the confidence read.
  **Commit.**

### WS5 — Harden `weather_fav` as its OWN standalone strategy
Keep weather a distinct strategy (the user's call), not folded into the champion. Ensure it has its own
certification cell (0.71–0.90), its own frozen gate, its own forward record, and — only IF WS4 clears
the gate over ≥2 disjoint weeks — a **default‑off paper executor** path mirroring the champion's build
order (capture‑at‑fire → paper fills → forward gate), promoting nothing. Update
`PREREG_..._weather.md` only by ADDING (never loosening) and freeze any new cell before its forward
data. **Commit.**

---

## 2. Rigor & anti‑overfit defense (LOAD‑BEARING — this is where prior mistakes live)

- **Copyability first.** `weather_fav_liq` (the $1k‑liquidity twin) fired 0 on enablement — weather books
  are THIN. The executable‑ask spread is the binding realizable question: measure the edge at the
  captured `entry_ask`, report the spread tax, and treat a fat % on unfillable size as NOT a strategy.
- **Day‑cluster, region‑day bracket.** Cross‑city same‑day temperature is correlated (heat domes);
  consecutive days share regimes. Pure‑day is the conservative floor, region‑day the upper — report the
  bracket, never a single inflated number. NEVER cluster by city‑market (over‑counts ~25×).
- **≥2 disjoint weeks + LODO‑by‑week is the decisive gate** (the tennis‑one‑Wimbledon trap by data
  availability). One week — however fat — certifies nothing.
- **Belief‑blind + `selection_null`** on EVERY cell/arm/universe (forecast‑co‑reading + easy‑day traps).
  Widening the universe or adding specialists must raise **skill‑over‑blind + realizable LB**, not just
  volume — else it's efficient forecast‑following re‑labeled.
- **Widening guard.** Past‑PnL rank was refuted 5 ways; naive global widening was withdrawn. A
  discovered specialist certifies ONLY forward/belief‑blind at OUR realizable entry, Bonferroni over the
  # screened. A wallet whose edge is timing/price we can't copy certifies to ~0.
- **Multiple testing is real.** Bonferroni/BH over the cities × bands × universes × niches you test;
  report how many. The more you scan, the higher the LB bar.
- **The forward gate is the final arbiter.** In‑sample/OOS earns a shadow slot + a frozen gate; forward
  weeks decide. No slicing shortcuts the accrual wall.

---

## 3. Build order (checkpoint + commit after EACH; a timed‑out run is "incomplete + resumable")

1. WS1 latency read (+ optional capture‑at‑detection) → `WEATHER-LATENCY.json`. **Commit.**
2. WS2 specialist discovery + belief‑blind ranking (+ optional wider/specialist arm) → `WEATHER-SPECIALISTS.json`. **Commit.**
3. WS3 evergreen niche scan → `EVERGREEN-SCAN.json`. **Commit.**
4. WS4 forward certification refresh + confidence → updated `WEATHER-VERDICT.json`. **Commit.**
5. WS5 standalone hardening + prereg addenda (+ executor ONLY if the gate clears). **Commit.**

Work in an ISOLATED git worktree off `main` (which now carries the live weather arm + instruments).
`cargo test --bin copy-trading-bot` + clippy green for any Rust; every new Python instrument
`--selftest` green. NEVER edit another active worktree's branch.

---

## 4. Guardrails (violating any = failed run)

- **Paper‑only; promotes nothing; arms nothing real.** Every new arm `alerting=false`, default‑off flag,
  incumbents (champion `favorite` + `weather_fav`/`weather_fav_liq` + `ConsensusParams::default` + all
  others) BYTE‑IDENTICAL. No new arm changes an existing one.
- **No `.env` ARMING edits without a human.** You may PROPOSE flags (compose + prereg); enabling a live
  capture/ingestion flag on the running daemon is Tue's call — stage it, don't flip it.
- **Cost‑zero / Max‑only:** never set `ANTHROPIC_API_KEY`, never spawn child `claude`. Python =
  numpy/pandas/psql/stdlib only. DB read‑only except the bot's normal accrual writes;
  `clob_price_tape`/`trader_fills` SELECT‑only. Any new ingestion must be BOUNDED (weather markets only)
  and respect poller/subscribe ceilings — no unbounded global polling.
- **No new migration** unless a genuine schema/pipeline defect — then STOP and report (likely a separate
  run). Coordinate with other worktrees (maker‑copy‑g3 owns tape/fills); non‑overlapping slices.
- **No re‑litigating settled findings** (§0): total‑P&L/win‑rate are wrong objectives; deep chalk is
  non‑productive turnover; naive global widening + past‑PnL ranking are refuted; never loosen the frozen
  gate's floors.

---

## 5. Completion criteria (honest definition of done)

Green = ALL of: (1) WS1 answers the capture‑latency question with data (+ a staged improvement if
warranted); (2) WS2 delivers a belief‑blind weather‑specialist discovery + a tested verdict on whether a
wider/specialist universe raises the REALIZABLE LB + skill (not just volume); (3) WS3 reports whether any
other evergreen niche clears the copyable belief‑blind bar; (4) WS4 refreshes the forward certification
with the accrued weeks and runs LODO‑by‑week the moment a 2nd disjoint week exists; (5) WS5 keeps weather
a hardened standalone strategy with its frozen gate, and stages an executor ONLY if the gate clears.

**Do NOT claim weather is "real"/"bankable"/"beats the champion."** Claim: the realizable, belief‑blind,
anti‑overfit LB weather reaches over ≥2 disjoint weeks at OUR executable entry; whether widening to
discovered specialists raised it; whether another evergreen niche exists; and where each lands vs the
champion's +5.6% floor. If weather clears the gate — stage its executor for a human decision. If it
plateaus below champion or is eaten by the thin‑book spread — that is a fully valid, money‑saving result
that tells Tue the ceiling, and saves wasted build. The value is a trustworthy per‑dollar‑edge verdict,
not a bigger in‑sample number.
