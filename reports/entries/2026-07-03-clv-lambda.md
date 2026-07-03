# 2026-07-03 · WS-A — the CLV / λ instrument (marquee): MEASURE the edge, don't assume it

**One line:** the proper CLV instrument (`signal_price_trajectory`) is **empty — dense capture has
never run** — so the true λ is **INDETERMINATE-BY-DATA (K1)**. The only available proxy
(`mean_price` drift) is positive and beats the selection-matched null, but explains only **~15% of
the favorite surplus** (λ̂≈0.15, wide CI) — evidence that, if anything, points to a **LOW λ, below
the λ=0.25 profitability threshold**, not a high one. CLV does **not** support "the edge is mostly
real." It shortens the epistemic wait **only once dense capture is turned on**.

## What was built
`scripts/clv_lambda.py` — stdlib-only, docker-exec psql, seeded (20260703), `--selftest`, writes
`reports/clv_lambda.json`. Reconstructs CLV = close − entry per resolved position, with:
- **entry** = `initial_mean_price` (at-fire, D6).
- **close** = the last trajectory `mid ∈ [0.02, 0.98]` at/before `resolved_at` (the **degenerate
  guard** — the post-resolution 0/1 print is hindsight, not value). Falls back to `mean_price`
  **only** when trajectory is empty, and **flags the fallback rate**.
- **Q1** selection-matched null on CLV (band×UTC-day-matched random `_blind` draws — the exact
  `selection_null.py` machinery, CLV as the statistic). **Q2** surplus decomposition (CLV-explained
  vs residual). **Q3** λ̂ = clip(mean_CLV/δ, 0, 1) with a block-bootstrap (event-clustered) CI.

**Self-test PASSES all three fixtures**, incl. the K3 guard (a synthetic trajectory spiking to 0.99
at resolution yields close=0.82 / CLV +0.02, **never** +0.19) and a positive-CLV recovery.

## What the data says (favorite, 232 positions / 113 events)

| quantity | value | read |
|---|---:|---|
| **trajectory coverage** | **0.0%** | K1 — `signal_price_trajectory` has **0 rows globally**; 100% proxy fallback |
| mean CLV (proxy) | **+0.0172** [+0.0086, +0.0265] | line drifted our way on the proxy |
| selection-matched null | μ −0.0085, z +3.51, **p=0.0000** | the proxy drift **beats** matched-blind composition |
| realized surplus δ | +0.1140 | the edge being explained |
| **CLV-explained fraction** | **15.1% of δ** | only ~1/7 of the surplus is confirmed by line movement |
| residual (won − close) | +0.0968 | ~85% realized only at resolution (bias/variance) |
| **λ̂ (proxy)** | **0.151** [0.076, 0.296] | if trustworthy, **below** the λ=0.25 profitability floor (D21) |

`elite_fresh_fav` (74 pos): λ̂=0.051, null p=0.036 (not < 0.01) — weaker still.

## Why this is INDETERMINATE, not a λ (the honest caveats)
1. **The proper instrument never ran.** `signal_price_trajectory` is written only by the dense-capture
   loop (`live.rs:227`), gated by `DENSE_CAPTURE` (default **false**, `config.rs:162`). It has never
   been enabled → 0 rows → the CLV monitor the prompt flagged as EMPTY is empty *because capture is
   off*, not because the query is wrong.
2. **The proxy is not a closing line.** `mean_price` is the **consensus mean** (mean of backer
   prices), a single ambiguous snapshot — 82/232 favorites have `last_updated_at` *after*
   `resolved_at`. It is confounded **upward** by consensus-formation (more backers piling in at higher
   prices reads as "the line moved" even if the market mid did not). So the +1.72pt is an **optimistic**
   read, and it *still* only yields λ̂≈0.15.
3. **Direction, not magnitude.** The one thing the proxy establishes (null p=0.0000) is that the drift
   is not zero and not pure composition — *some* of the edge is information the market began to
   confirm. But 15%-explained is far from the ">50% ⇒ λ near 1" regime; the weight of the surplus is
   the static favorite-longshot bias + variance that only resolves at settlement — the λ→0 world.

## The structural fix (proposed, NOT applied — benign, paper-only)
To turn λ from a proxy guess into a **measurement**, dense capture must run so real
mid-trajectories accrue:
- Set `DENSE_CAPTURE=true` and ensure `DENSE_STRATEGIES` includes `favorite,elite_fresh_fav`
  (`config.rs:180`). This is a **paper-only data-capture** env — it places no orders and changes no
  betting behavior; it only writes `signal_price_trajectory` (migration 034). It is additive and
  reversible. **Proposed for the integrator/Tue to flip** (an env change; not one of the two Tue-only
  betting decisions, but per guardrail 2 this run does not flip envs).
- Once ~2 weeks of dense capture accrue, re-run `clv_lambda.py`; coverage crosses the 50% K1 bar and
  the same instrument emits a **real** λ̂ from true closing mids. `clv_lambda.py` is written to switch
  from proxy to trajectory automatically the moment coverage exists.

## Verdict
**INDETERMINATE-BY-DATA.** No high-λ evidence exists; the available proxy is weakly *anti* a high λ
(15%-explained, λ̂≈0.15). This is a genuine negative and it is the deliverable — it is **not**
laundered into a profitability claim. Real money remains gated on out-of-sample persistence (D7); CLV
would *shorten* that wait, but only after dense capture is enabled and accrues. λ̂ on this record is
both **small and very uncertain** — and the uncertainty is the point.
