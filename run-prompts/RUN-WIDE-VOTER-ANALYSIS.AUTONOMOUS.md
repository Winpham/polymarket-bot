# Autonomous Run: Does widening the consensus voter set (top-40 → top-100/200) add REAL potential? Characterize, refine, then build ONLY if it passes.

> **Read this whole brief before touching anything.** Autonomous build worker on `~/polymarket-bot`,
> cwd = this worktree `wt/wide-voter` (branch `feat/wide-voter`, off fresh `main`). Tue's ask, verbatim
> intent: *"yes [build the wide-voter arm] BUT FIRST check how top-100/top-200 look and refine it so it
> has the same potential / has potential — before building."* So this run is **analysis-and-refine FIRST,
> build ONLY if the analysis proves potential.** Do NOT build a shadow arm for a voter set that dilutes
> the edge. A rigorous "widening dilutes, here's the evidence, don't build" is a SUCCESS. Building a
> junk-wide arm because the brief mentioned it is a FAILURE.

---

## 0. The setup (verified 2026-07-09/10)

- Prod votes with **top-40** traders (`TRACK_TOP_N` default 40) but **captures** the top-200
  (`TRACK_DEPTH=200`) and follows **1,098** traders. Ranks 41-200 are profiled, **not voting** — so
  markets that would clear `min_backers=3` on a wider voter set never fire. That is the untapped
  coverage. Turnover-multiple is ~0.76-1.14×/day (recycles ~once) — widening voters is the most direct
  lever on that trapped throughput.
- **First-look already done** (favorite-side sports fills, 07-01+, by rank band):
  top-40 win **85.7%** (5,432 mkts); r41-100 **81.3%** (2,402); r101-200 **81.7%** (8,760 mkts). So the
  wider pool is highly ACTIVE (huge added coverage) but ~4pp LOWER individual win-rate — on an
  ~0.80-priced favorite that's roughly +7% vs +2% EV. **Potential is real but thinner-margin.** Your job
  is to measure whether the CONSENSUS (3+ agree) of the wider set holds the edge, not the individual fills.

## 1. The one question that gates everything

For each candidate voter cutoff C ∈ {40 (baseline), 60, 80, 100, 150, 200}: **do the MARGINAL markets —
those that fire the favorite consensus at cutoff C but NOT at top-40 — carry a positive honest edge, or
do they dilute?** Turnover only helps if `turnover-multiple × ROI-per-turnover` grows; a wider set that
adds volume at negative marginal ROI SHRINKS daily $. Report the marginal set's honest ROI explicitly at
every cutoff — that number is the verdict.

## 2. Method — REPLAY with the real logic, not an approximation (this is where we get burned)

- **Reuse `scripts/consensus_backtest.py`** (and the real `consensus.rs` scoring semantics it encodes).
  Do NOT hand-roll a rough Python consensus that diverges from prod — the field/look-ahead artifacts that
  already inflated a "+7.9%" and a "+9.66%" all came from shortcut re-implementations. **Validation gate
  (do this FIRST):** replay at cutoff=40 and confirm it reproduces the actual top-40 favorite signal set
  in `consensus_signals` (same markets, ±small). If your cutoff=40 replay doesn't match prod, STOP —
  your replay is wrong and every wider number is garbage.
- Rank source: `followed_traders.rank` (use `min(rank)` per wallet). Voter set at cutoff C = wallets with
  rank ≤ C. Keep every other consensus param identical to the champion (`min_backers=3, max_opposers=1,
  max_price_std=0.10, price_band 0.65-0.98, max_age_mins`, two-sided exclusion, weight_mode) — the ONLY
  thing that changes across cutoffs is who is eligible to vote.
- **Honesty rails (all mandatory, learned the hard way):**
  - Corrected fee (sports taker `0.03·(1−p)` entry-only, maker 0), flat $100, event-dedup, at-fire
    fields only (`initial_*`; never live `recency_mins`/`total_usd` — look-ahead).
  - Belief-blind: run each cutoff's favorite signal set through `selection_null.py` / `standard_guard.py`
    — a wider set must stay SELECTION-REAL, not just show a nicer raw ROI.
  - **Multiple-testing correction** across the cutoff sweep (Bonferroni/BH) — say how many you tested.
  - **Time-split + non-FIFWC holdout** — a cutoff that only helps in-sample or only in the World Cup is
    rejected.
  - Report BOTH turnover (added markets/day, turnover-multiple) AND ROI/turn AND their product (daily-$
    potential) at each cutoff — never one axis alone.

## 3. Refine (the "so it has potential" part)

The likely finding (from the first-look): wider = more turnover, lower ROI/turn. So don't just pick a
cutoff — **find the version that keeps potential:**
- Sweep C and find the widest cutoff where the MARGINAL set's honest ROI (and belief-blind surplus)
  stays ≥ a pre-registered floor (e.g. ≥ the champion's own realizable, or ≥0 belief-blind LB).
- Test the wider voter set **WITH the favorite_v2/favorite_liq quality gates layered on**
  (`min_total_usd≥1000`, and the rank gate) — the added markets are likely lower-liquidity/obscure (the
  exact junk favorite_v2 filters), so "wide voters + liquidity floor" may capture the turnover while
  dropping the dilution. Report wide-raw vs wide+liquidity vs wide+liq+rank.
- The deliverable of this phase is a REFINED config (a specific cutoff, possibly + a quality gate) that
  has demonstrable potential — or a clear "no cutoff beats top-40 once you demand +EV marginal turnover."

## 4. Build — CONDITIONAL, only if §3 finds a config with potential

If (and only if) a refined config clears the pre-registered potential floor OOS + belief-blind:
- Add it as a **shadow arm** in `consensus.rs` (e.g. `favorite_wide100` / `favorite_wide100_liq`) using
  an additive voter-cutoff knob (match the existing knob pattern; default = top-40 so nothing else
  changes), `alerting=false`. Champion + `ConsensusParams::default` byte-identical. Unit test proves it.
  `cargo test` + `cargo clippy` green.
- Pre-register its forward gate (`reports/PREREG_<stamp>_favorite_wide.md`): metric it must beat, power
  floor (≥30 ev / ≥10 day-clusters), kill condition. Note it accrues automatically (`should_ledger`).
- **Do NOT merge or deploy.** Merge advances local main → autoupdater redeploys prod → interrupts the
  active g3 run. Merge/deploy is Tue's call. Leave it on `feat/wide-voter` with the report.

If §3 finds NO config with potential: **build nothing.** Write the honest negative + the evidence.

## 5. Guardrails (violating any = failed run)

- Read-only DB (bot's own accrual writes excepted; you write no analysis rows). Paper-only; deploy
  nothing, arm nothing, merge nothing, no `.env` edits. Cost-zero (no child `claude`, no ANTHROPIC_API_KEY).
- Stay in `wt/wide-voter` on `feat/wide-voter`; NEVER commit to main. Commit after each phase (reaped run
  must be salvageable). Touch `scripts/`, `reports/`, and — only in the conditional build — `consensus.rs`
  (default_portfolio + the voter-cutoff knob). Don't touch tape/fills tables or files owned by
  `feat/maker-copy-g3` / `feat/garbage-policy`; if you'd collide, yield.
- Reuse the real consensus logic (§2). No rough re-implementations presented as truth.

## 6. Completion criteria (honest done)

Green = (1) cutoff=40 replay reproduces prod's top-40 favorite set (fidelity gate passed); (2) a
`reports/WIDE-VOTER-ANALYSIS.md` with, per cutoff {40,60,80,100,150,200}: added markets/day, turnover-mult,
marginal-set honest ROI, belief-blind surplus, by-regime + non-FIFWC + time-split, WITH and WITHOUT the
liquidity/rank gates, multiple-testing corrected; (3) a REFINED recommended config (or a reasoned "top-40
is already optimal"); (4) IF it passes: the shadow arm built, tested, forward-gate pre-registered, on
`feat/wide-voter`, NOT merged; (5) a one-paragraph verdict stating the marginal ROI at the recommended
cutoff, whether it grows daily-$ potential (turnover × ROI/turn), and honestly whether the wider signals
are +EV or dilution. Do NOT claim widening "works" — claim what the marginal-ROI evidence shows and that
the forward gate is the judge. A timed-out run is "incomplete + resumable", never "done".
