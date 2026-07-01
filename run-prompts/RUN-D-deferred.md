# RUN-D — Deferred arms (Bayesian anchor + import-model collapse-probe)

> ⚠️ **Do NOT build yet.** Run this only after RUN-A/B have accrued real forward data and there's a concrete
> reason (e.g. `ml_top` shows promise and you want an anchored variant, or you want to confirm the market-model
> null on this data). Both designers ranked these LOW expected ROI. Land them one at a time, behind the RUN-B
> enricher seam (each is one new file + one `registry()` line). Read `FORGE_PLAN_LEVERS.md` (Deferred section).

## D1 — Bayesian-anchor arm (`bayes_top`)
**Idea:** prior = the live CLOB mid of the fired outcome (already captured as `initial_market_price`, or fetch
once per fired market with `fetch_clob_market`); evidence = consensus conviction mapped to a likelihood ratio
(monotone in `net_quality`, confidence from price coherence) [+ the ML LR from RUN-B if present]; combine via
`bayesian_update` → posterior; emit `bayes_top` only when the posterior still beats the mid by a margin.
**Prereq:** move `trading-bot/src/bayesian.rs` → `common/src/model/bayesian.rs` (pure fns; re-export so
trading-bot is unbroken — see FORGE_PLAN_LEVERS PREP-A). Then `scanner/enrich/bayes.rs` + one `registry()` line.
**Owned files:** `common/src/model/bayesian.rs` (+ mod re-export), `trading-bot/src/main.rs`+`model/mod.rs`
(re-export), `scanner/enrich/bayes.rs`, the one `registry()` line.
**Honest expectation:** a selection filter on `strict` picks; the gate judges its surplus. Likely marginal.

## D2 — Import-model exploitation — PROMOTED to its own first-class run
**Superseded — see [`RUN-TRADING-BOT-EXPLOIT.md`](RUN-TRADING-BOT-EXPLOIT.md).** The import-model is no
longer a "confirm the null" cheap probe; it is now a **first-class exploitation target** with a full
phase-structured run prompt + blueprint (`FORGE_PLAN_TRADING_BOT.md`). The old "≈0 surplus, documented
null" expectation was a **price-conditioning artifact, not a refutation**: scoring `p_model − clob_mid`
cancels against the gate's own `blind_edge[band]` subtraction, so a price-anchored model scores ~0 BY
CONSTRUCTION. The new run gives the model a genuine, leak-free shot — a price-FREE residual model
compared to baked per-band base rates (`band_rate`, not `clob_mid`), YES-oriented, GroupKFold-by-event,
forward-calibrated on a new `market_feature_log`, judged solely by the belief-blind gate. Run that
instead of building anything here for the market model.

## Both
- Each arm is SILENT (`alerting=false`), judged only on surplus-over-blind by the gate.
- Each new arm raises the gate's Bonferroni denominator for ALL strategies. If the arm count grows past ~4–5,
  first implement the **family split** (FORGE_PLAN_LEVERS.md §"Bonferroni family split") so experimental arms
  don't tighten `strict`'s own promotion bar.
- Follow `run-prompts/README.md` workflow (worktree, gate, safe merge, default-off).
