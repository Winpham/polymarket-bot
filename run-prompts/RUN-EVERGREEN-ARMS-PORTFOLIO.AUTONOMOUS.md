# Autonomous Run: Per‑Market‑Type Arm Portfolio — diversify, strengthen, and separately optimize each evergreen branch

> **Read this whole brief before touching anything.** You are an autonomous build worker on
> `~/polymarket-bot` (Rust + Python + SQL Polymarket consensus/copy‑trading **PAPER** system). A live
> default‑off shadow arm `weather_fav` (highest‑temperature) is enabled and accruing. A discovery run
> found that **lowest‑temperature is a distinct, copyable, higher‑skill sibling that behaves
> DIFFERENTLY and is ~uncorrelated at the tradeable band** — so the direction is to build a **portfolio
> of independently‑certified, separately‑optimized, low‑correlated evergreen arms**, one per market
> type, rather than one blended arm. Your job: **build that per‑market‑type arm framework, add the
> low‑temp arm, optimize each branch to its OWN behavior (belief‑blind, not in‑sample), and measure the
> diversification forward** — so the portfolio's risk‑adjusted, copyable, per‑dollar lower bound beats
> any single arm and approaches/passes the champion's honest floor (+5.6% LB). **Both "here is a
> diversified, each‑certified portfolio + forward proof" and "these arms don't independently certify /
> aren't actually uncorrelated / are eaten by thin‑book spread — here is the proof" are SUCCESS. A
> goal‑sought green or a pile of un‑certified arms is failure.** If you catch yourself proliferating
> arms or tuning knobs to inflate an in‑sample number, STOP — you have drifted.

---

## 0. READ FIRST — inherit the state, do not re‑derive it

- **`reports/WEATHER-FINDINGS.md`**, **`reports/PREREG_20260712T052717Z_weather.md`** — the weather arm's
  5‑phase refinement + FROZEN gate. The floors there are the template; you may ADD, never loosen.
- **Instruments (all `--selftest` green, reuse — don't fork):** `scripts/weather_scan.py`,
  `weather_verdict.py`, `weather_regions.py`, `cell_lib.py`, `cell_map.py`, `cell_scan.py`.
- **The live arm:** `weather_market_arms()` in `copy-trading-bot/src/scanner/consensus.rs`;
  `load_weather_window_votes()` in `common/src/storage/consensus.rs`; wired in `consensus_cycle.rs`
  behind `CONSENSUS_WEATHER_ARM` (LIVE, paper, alerting=false, `SOFT_MARKET_RANK_CUTOFF=250`).
- Memory: `project-polymarket-weather`, `project-polymarket-cell-scan`, `project-polymarket-identify-skilled`,
  `project-polymarket-correlated-risk`, `project-polymarket-risk-engine`, `feedback-edge-exists-prior`.
- DB: `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket -c "..."`.

**Settled — do NOT re‑litigate (build on, don't repeat):**
- **High‑temp vs low‑temp behave DIFFERENTLY (this is why they get separate arms):** on the at‑fire‑mid
  (realizable‑proxy) basis, DAY‑clustered, band **0.71–0.90**:
  - HIGH‑temp: n=167 / 6 days, **LB +10.4%**, skill/blind +10.3% (blind favorite +2.1% — casual prices highs ~right). The workhorse.
  - LOW‑temp: n=21 / 5 days, **LB +4.0%**, skill/blind **+16.3%** (blind favorite **−4.6%** — casual MIS‑prices lows; sharps exploit a bigger bias). Higher skill, POWER‑STARVED.
  - Deep chalk 0.90–0.98 stays DEAD in both (win‑rate trap) — arms CAPTURE broad, CERTIFY at 0.71–0.90.
- **Diversification is directionally there but THIN:** day‑ROI correlation at 0.71–0.90 ≈ **+0.02**
  (uncorrelated → diversifies), vs +0.76 at the full band (a deep‑chalk artifact). But this is **5 common
  days** — indicative, NOT reliable. Re‑measure forward before trusting it.
- **Copyability triage from the evergreen scan (do not re‑derive):** `lowest-temperature` COPYABLE
  (~20h life); `crypto-updown` UNCOPYABLE (21‑min life ≈ our capture lag — sharp‑timing siren, do NOT
  build); `crypto-level` (BTC‑above‑$X / price‑of, ~24h life) COPYABLE but tiny (17 picks, likely
  selection) — ACCRUE‑only candidate, don't act on it.
- DEAD as *copyable* edges: past‑PnL rank (refuted 5 ways), naive global widening (withdrawn),
  finer‑than‑0.10 bands, total‑P&L / win‑rate as objectives.

---

## 0.5. THE OBJECTIVE (optimize THIS — nothing else)

> **Maximize the DIVERSIFIED, risk‑adjusted, REALIZABLE per‑dollar lower bound of a PORTFOLIO of
> per‑market‑type arms — each an independently‑certified, copyable, belief‑blind, DAY/region‑clustered,
> ≥2‑disjoint‑weeks edge measured at OUR captured `entry_ask` — such that the portfolio LB exceeds any
> single arm and approaches/passes the champion's +5.6% honest floor. OR the honest proof that the arms
> don't independently certify / aren't uncorrelated / are eaten by spread.**

- **Each arm certifies ON ITS OWN** (its own gate, its own belief‑blind `selection_null`, its own
  ≥2‑disjoint‑weeks + LODO). An arm that doesn't certify is RETIRED, not carried.
- **Diversification only counts when BOTH hold**: each arm is independently +EV at realizable cost AND
  the cross‑arm match‑day correlation is low (< ~0.3) — re‑measured forward, not on 5 days.
- **Per‑arm optimization is BELIEF‑BLIND and MECHANISM‑ONLY.** "Optimize each branch" = find the config
  (band, eligibility/specialist set, capture cadence, min_backers) that maximizes the arm's realizable
  belief‑blind LB with an a‑priori mechanism you'd predict BEFORE looking — NEVER an in‑sample grid
  search for the highest number. Every tuning knob is forward‑gated.
- **Win rate, total P&L, and the NUMBER OF ARMS are DIAGNOSTICS, not the objective.** A pile of
  un‑certified arms is worse than one certified arm.

---

## 1. Mission — five workstreams, each HARD‑STOP + commit + write findings so a reaped run is salvageable

### WS1 — Build `weather_low_fav` as its own arm (the second branch)
Mirror the weather arm EXACTLY, scoped to lowest‑temperature, as a SEPARATE strategy (not a merged
`temperature` filter — high/low behave differently and must optimize/certify independently):
- `load_low_temp_window_votes()` (or generalize `load_weather_window_votes` to take a family — see WS2)
  filtered `slug ~ 'lowest-temperature'`, same wider eligibility.
- `weather_low_fav` / `weather_low_fav_liq` arms (0.71–0.98 capture, 0.71–0.90 certify), `alerting=false`,
  behind a flag (`CONSENSUS_WEATHER_LOW_ARM`, or a shared `CONSENSUS_EVERGREEN_ARMS` — WS2's call).
- Unit tests (shape/isolation/fires‑on‑nonsport/skips‑sub‑0.71) + `cargo test --bin copy-trading-bot` +
  clippy green; champion + `weather_fav` + `ConsensusParams::default` + every incumbent BYTE‑IDENTICAL.
- A frozen `reports/PREREG_<stamp>_weather_low.md` (its OWN gate: day/region‑clustered LB at `entry_ask`,
  ≥2 disjoint weeks, LODO‑by‑week, `selection_null` p≤0.01, skill‑over‑blind>0, low corr vs `weather_fav`).
- Stage the compose wiring (do NOT flip the live flag — human's call). **Commit.**

### WS2 — The per‑market‑type arm FRAMEWORK (make adding a branch cheap + uniform)
Refactor the weather arm's loader + arm‑def + cycle wiring into a small, parameterized pattern so each
new evergreen market type is a `{family_regex, arm_names, band, eligibility, flag}` entry — each still
DEFAULT‑OFF and independently certified. The refactor must leave `weather_fav` BYTE‑IDENTICAL (prove it
with a test asserting the generated arm equals today's). This is the factory that lets high‑temp,
low‑temp, and future types (crypto‑level candidate, other weather props) each be their own optimized
branch without copy‑paste drift. **Commit.**

### WS3 — Optimize EACH branch to its OWN behavior (belief‑blind, mechanism‑only)
Different market behavior ⇒ different optimal config. For EACH arm, search — belief‑blind, forward‑gated,
a‑priori‑mechanism‑only — the config that maximizes its realizable LB:
- **Band**: confirm 0.71–0.90 per arm; a‑priori (deep chalk dead). Do NOT slice finer than 0.10.
- **Eligibility / specialist set**: low‑temp is thinner — does a weather‑SPECIALIST discovery (per
  RUN‑WEATHER‑DEEPEN WS2: rank wallets by their weather track record, not global rank) raise its
  realizable LB + skill, or just add volume? Certify forward, Bonferroni over the # screened.
- **Convergence bar (`min_backers`)**: does a thinner market want a different bar? Mechanism‑justified only.
- **Capture cadence**: reuse the WEATHER‑LATENCY read; if the edge decays in the capture window, stage
  capture‑at‑detection for that arm.
- Report each arm's tuned config as a FORWARD hypothesis in its prereg, never as an in‑sample win.
  **Commit.**

### WS4 — Strengthen reliability: per‑arm certification engine + forward accrual
- Re‑run each arm's battery (`weather_verdict.py` generalized per family) as weeks resolve; the moment a
  **second disjoint week** exists per arm, run the real **LODO‑by‑week** — the decisive gate.
- Every measurement: `entry_ask` coverage %, day‑cluster + region‑day bracket, bootstrap 2nd opinion,
  Bonferroni over all arms/cells tested, `selection_null` (forecast‑co‑reading). More signals count ONLY
  if the LB + skill hold. Emit `reports/EVERGREEN-PORTFOLIO-VERDICT.json` (per‑arm + portfolio). **Commit.**

### WS5 — Portfolio & diversification (the point of diversifying)
- Re‑measure cross‑arm match‑day correlation FORWARD (the +0.02 is 5 days — firm it up). Diversification
  is real only if each arm is +EV AND low‑correlated.
- Define how the arms COMBINE: independent flat‑SHARES per arm now; a correlation‑aware allocation
  (reuse `corr_risk_engine.py` / `project-polymarket-risk-engine`: N_eff/HHI, ⅛‑Kelly‑capped, size the
  cluster) only once each arm is certified. Compute the PORTFOLIO LB (diversified) vs the best single arm
  and vs the champion's +5.6% floor.
- Deliverable: the portfolio verdict + (only if arms certify over ≥2 disjoint weeks) a staged, default‑off
  paper‑executor path per arm, promoting nothing. **Commit.**

---

## 2. Rigor & anti‑overfit defense (LOAD‑BEARING)

- **Copyability first.** `weather_fav_liq` fired 0 on enable — weather books are THIN. Measure every arm
  at the captured `entry_ask`, report the spread tax; a fat % on unfillable size is NOT a strategy.
- **Day‑cluster, region‑day bracket; ≥2 disjoint weeks + LODO‑by‑week is the decisive gate** (one window,
  however fat, certifies nothing — the tennis‑one‑Wimbledon trap by data availability).
- **Belief‑blind + `selection_null` per arm** (forecast‑co‑reading + easy‑day traps). Optimization or
  widening must raise skill‑over‑blind + realizable LB, not volume.
- **Per‑arm optimization overfits easily.** Every knob = an a‑priori mechanism + a forward gate;
  Bonferroni over every config/arm/cell tried; report the count. "Best in‑sample config" is FORBIDDEN.
- **Diversification honesty.** The +0.02 correlation is 5 days — treat as INDETERMINATE until forward
  data firms it; a portfolio LB that assumes independence on thin correlation is a false tightening.
- **Correlated‑unit discipline.** Cluster at the DAY (region‑day bracket); NEVER city‑market. Cross‑arm
  correlation at the MATCH‑DAY. The forward gate is the final arbiter.

---

## 3. Build order (checkpoint + commit after EACH; a timed‑out run is "incomplete + resumable")

1. WS2 framework refactor (weather_fav byte‑identical, proven by test) → **Commit.**
2. WS1 `weather_low_fav` arm + tests + frozen gate + staged compose → **Commit.**
3. WS3 per‑arm belief‑blind optimization (config as forward hypotheses) → **Commit.**
4. WS4 per‑arm certification refresh + `EVERGREEN-PORTFOLIO-VERDICT.json` → **Commit.**
5. WS5 portfolio LB + forward correlation + (gated) executor staging → **Commit.**

Work in an ISOLATED git worktree off `main`. `cargo test --bin copy-trading-bot` + clippy green for any
Rust; every Python instrument `--selftest` green. NEVER edit another active worktree's branch.

---

## 4. Guardrails (violating any = failed run)

- **Paper‑only; promotes nothing; arms nothing real.** Every new arm `alerting=false`, default‑off flag;
  champion `favorite` + `weather_fav`/`weather_fav_liq` + `ConsensusParams::default` + all incumbents
  BYTE‑IDENTICAL (prove the WS2 refactor keeps `weather_fav` identical with a test).
- **No `.env` ARMING edits without a human.** Stage compose + prereg; enabling a live flag is Tue's call.
- **Cost‑zero / Max‑only:** never set `ANTHROPIC_API_KEY`, never spawn child `claude`. Python =
  numpy/pandas/psql/stdlib. DB read‑only except normal accrual writes; `clob_price_tape`/`trader_fills`
  SELECT‑only. Any new ingestion BOUNDED to the target markets + flag‑gated; respect poller/subscribe ceilings.
- **No new migration** unless a genuine schema defect — then STOP and report. Coordinate with other
  worktrees (maker‑copy‑g3 owns tape/fills); non‑overlapping slices.
- **No arm proliferation without certification.** An arm that doesn't clear its own gate over ≥2 disjoint
  weeks is RETIRED, not kept on hope. No re‑litigating settled findings (§0); never loosen a frozen gate.

---

## 5. Completion criteria (honest definition of done)

Green = ALL of: (1) WS2 factory lands with `weather_fav` proven byte‑identical; (2) `weather_low_fav`
built, tests+clippy green, its own frozen gate, compose staged (not flipped); (3) each arm's config is a
belief‑blind, mechanism‑justified FORWARD hypothesis (no in‑sample grid winner); (4) each arm's battery
re‑runs on accrued weeks with LODO‑by‑week the moment a 2nd week exists; (5) the portfolio verdict reports
each arm's realizable LB, the FORWARD‑re‑measured cross‑arm correlation, and the diversified portfolio LB
vs the best single arm vs the champion's +5.6% floor.

**Do NOT claim any arm or the portfolio is "real"/"bankable"/"beats the champion."** Claim: which arms
independently certify (belief‑blind, realizable, ≥2 disjoint weeks) at OUR executable entry; whether they
are genuinely low‑correlated on FORWARD data; what the diversified portfolio lower bound is; and where it
lands vs +5.6%. A diversified, each‑certified portfolio that clears the floor → stage its executors for a
human decision. Arms that don't certify, or a diversification that evaporates forward → retire them; a
smaller, honest, certified set beats a big un‑certified one. The value is a trustworthy diversified
per‑dollar verdict, not a count of arms or a bigger in‑sample number.
