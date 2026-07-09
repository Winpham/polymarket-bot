# FABLE Run 2 — Supply as the First-Order Product (2026-07-09)

**One-line:** built and iterated a supply-frontier strategy to plateau: `frontier_k3e`
(wide voter pool + echo-independent counting — the only config whose persistence-honest
lower bounds stay positive under a resolution-guarded replay) as the primary arm, plus
`frontier_k2a` (2-backer anchored, ~2.3× supply, edge deliberately UNPROVEN) as the
explorer — shipped as silent shadow arms behind `CONSENSUS_WIDE_ARMS`, prereg'd
(`reports/PREREG_20260709_supply_frontier.md`), gate green, unmerged.

Branch `feat/supply-frontier` (off main 4940509, includes the run-1 `feat/wide-consensus`
merge). The judge: `scripts/supply_frontier_replay.py` (window-accurate replay engine,
7-block selftest, causal tape entries, cluster-robust LBs, 72h resolution guard).

---

## 1. Scouting shortlist (capped, one section — per the brief)

The supply chain (fills → votes → gates → signals → ledger) has these throttles. Measured
levers this run: **consensus threshold (k2 vs k3)**, **anchor requirement**, **band floor
(0.60–0.65)**, **echo-independent counting** (quality guard that makes widening safe).
Ops-only lever queued: **TRACK_DEPTH 200 → 500** (pagination already ships; rank-201–500
wallets have no retro fills → not measurable this run, pure forward accrual). Non-levers:
entry-ask budget (per-cycle, ample), window/recency/std gates (mechanism-protective),
resolution latency (capital is uncapped — supply, not recycling, binds daily $).
The top-40 voter gate itself was run 1's find; this run built on the opened pool.

## 2. The iteration trail (the deliverable the brief demanded)

Every number below: ledger formula ($100 flat, 2% fee), 10-day replay over 2.1M
tracked-wallet fills, **72h resolution guard** (signals detected within 72h of the
snapshot excluded — losers resolve ~2× slower, so unguarded recent days are
winner-enriched). "Proxy" = mean backer fill +1¢ (paired-tape test measured the real
drift at +2.4¢ median — the proxy FLATTERS; stated, not hidden). LBs = one-sided 95%
cluster-robust t(G−1), event- and day-clustered.

**The judge itself iterated under attack** (v1.0 → v1.2): selftest caught an event-order
bug; the cluster-LB call violated `effective_n`'s contract (silent None) — fixed, silent
except removed; inactive-tracked-wallet exclusion biased the pool — fixed; tape coverage
was conflated across eras — fixed; the resolution guard, frozen-window metadata, live-
champion baseline, and NULL-oidx guard were added after the adversarial audits.

| version | config | n (guarded) | proxy ROI | LB_event | LB_day | verdict |
|---|---|---:|---:|---:|---:|---|
| champ-replica | eligible pool, k3 | 59 | +1.8% | −11.3% | −12.5% | replica ≠ champion (audit #1) — context only, never a baseline |
| **live champion** | actuals, same window, guard | **353** | **+8.1%** (coalesce-ask) | — | — | the honest baseline (real ask on 126) |
| v1 | wide pool, k3 | 125 | +4.1% | −0.8% | −1.5% | starting line; weakness: burst-herd (echo) susceptibility untested |
| v2 | v1 + echo-60s | 121 | **+5.3%** | **+1.1%** | **+1.2%** | only both-LB-positive config; incremental-over-champion 79 legs @ +6.2% |
| v3 (as designed) | k2 + anchor + band 0.60 | 336 | −1.7% | −8.5% | −8.8% | **REFUTED — band 0.60–0.65 dilutes** (wr 0.63 at 0.62 price); killed |
| v3′ | k2 + anchor (band 0.65) | 278 | +2.5% | −2.8% | −3.3% | 2.3× supply, incremental ROI +0.7% — supply real, edge unproven |
| v4 grid | opp0 / anchor10 / anchor100 | 282/115/507 | +3.8/+4.4/+3.7% | all ≤0 or flat | | opp0 and anchor10 rejected; anchor 40≈100 (structural, not tuned) → **plateau** |

What each rebuild bought: v2 fixed v1's named weakness (echo) and — under honest
guarding — improved both LBs; v3 was killed by its own measurement (band60); v3′
recovered the supply half of v3 and was then demoted by the censoring fix; the v4 grid
established the plateau (every one-lever move off v2/v3′ is flat or worse).

**Retractions this run makes explicitly** (from its own earlier drafts): the unguarded
"+7.7–8.7% at tape ask" reads are RETRACTED (the 72h guard excludes the entire ~2-day
tape era — those numbers were short AND winner-enriched); "surplus-over-blind +0.24" is
demoted to context (the ≥1-buyer blind pool loses 8–16% in-band — an adverse baseline
that flatters); run 1's "wide beats champion" framing is WITHDRAWN — the live champion
(+8.1% guarded) dominates every wide config per-bet. The wide case is ADDITIVE SUPPLY
(incremental legs the champion structurally cannot fire — it needs 3 top-40 backers),
judged as NON-INFERIORITY forward.

## 3. The attack round (evidence the final version is the best, not the first)

Two isolated Opus critics (methodology; market-mechanism) produced 13 findings. Triage:

**Accepted and fixed in the judge/prereg:** resolved-only censoring (→ 72h guard — this
finding materially reordered the frontier and demoted k2a); champ-replica invalid as
baseline (→ live-champion actuals row; replica marked context-only); tape power (2
day-clusters, active-market subset → tape demoted to pilot; primary forward basis =
captured real `entry_ask` rows ONLY, no COALESCE); blind baseline adverse (→ demoted to
context; absolute ROI is primary); multiplicity (8-config sweep → config choice justified
structurally, all retro numbers tagged in-sample/pre-multiplicity; one primary hypothesis
in the prereg); floating window (→ frozen meta in JSON); NULL-oidx latent crash (→ guard).

**Accepted as named kill criteria (forward-testable, not retro-settleable):**
delayed-mirror kill (deep fills trail top-40 by median ~64 min — is the incremental leg
a late re-detection at a drifted price? → paid-drift diagnostic + incremental real-ask
LB_day in the prereg); small-cell mirage (→ leave-small-cells-out rule, size-defined);
echo at minutes-scale (the 60s guard can't catch minutes-later followers → 15-min echo
diagnostic reported forward); game-cluster risk at 40+ fires/day (→ game-cluster read
required before any promotion talk).

**Rebutted with reasons:** "wide must beat the champion" — wrong frame: there is no
capital cap, arms are additive; the correct bar is incremental-legs > 0 at our price +
non-inferiority (the critic himself proposed this — adopted). "The 60s echo screen is
cosmetic" — partially true (it binds rarely), but under the guarded replay it is the
difference between v1's negative and v2's positive LBs; it stays, PLUS the 15-min
diagnostic ships in the prereg.

## 4. What shipped

- `frontier_k3e` + `frontier_k2a` arms in `wide_arms()` (scanner/consensus.rs), both
  silent, EXPERIMENTAL family, on the wide book, behind `CONSENSUS_WIDE_ARMS` (default
  OFF — champion path byte-identical; flag-off = no extra query, no arms).
  `favorite_wide_anchored` removed BEFORE ever emitting a signal (supersession documented
  in the prereg — its mechanism lives in `frontier_k2a`).
- `ConsensusParams.echo_collapse_secs` — echo-independent min_backers counting in
  `score_market` (reporting stays raw; only the gate uses the collapsed count) + tests.
- `scripts/supply_frontier_replay.py` — the reusable frontier judge (selftest 7/7;
  resolution guard; live-champion baseline; frozen meta; --sweep/--grid2/--dump).
- `reports/PREREG_20260709_supply_frontier.md` — frozen contract: primary basis = real
  captured entry_ask only; floors (≥30 resolved incremental real-ask, ≥10 day-clusters,
  ≥2 surviving regimes); non-inferiority margin 3pp; named kills (delayed-mirror,
  small-cell, 15-min echo); INDETERMINATE stays INDETERMINATE.
- Gate: clippy 0 warnings, 292 workspace tests green (fmt drift on untouched code
  pre-exists on pristine main — not chased). No new SQL this run (the wide loader was
  throwaway-Postgres-verified in run 1).

## 5. Honest status + expected value

- **Certified: nothing.** The one defensible retro datum: v2/k3e guarded proxy +5.3%
  with LB_ev +1.1% / LB_day +1.2% (n=121, 8 day-clusters) — in-sample, proxy-priced,
  pre-multiplicity, BELOW the live champion per-bet. Everything else is supply counts
  and rejected branches.
- **The supply fact is solid:** the wide book fires on legs the champion structurally
  cannot (needs 3 top-40 backers), ~10/day incremental for k3e and ~24/day more for k2a
  in guarded replay — while champion supply is ~44/day and forecast to thin post-Wimbledon.
- **Expected daily $ if S1+S2 hold forward** (paper, $100 flat): champion ≈ $290–360/day;
  k3e incremental ≈ +$60/day at replay quality; k2a is the real prize IF the
  delayed-mirror kill doesn't fire (~$150+/day more at even 3–4%) — but that is exactly
  what the forward record must settle. No mirage: these are conditional numbers.
- **Accrual clock:** at ~10–30 incremental fires/day with ~40% real-ask capture, the
  ≥30-real-ask floor fills in ~1–2 weeks; day-cluster floor (≥10) in ~10 days.

## 6. Handoff — exact steps for Tue

```bash
cd ~/polymarket-bot
git merge --no-ff feat/supply-frontier          # brings run-1 arms + this run
# .env.consensus — add/adjust:
#   CONSENSUS_WIDE_ARMS=true
#   LEDGER_STRATEGIES=favorite,elite_fresh_fav,favorite_wide,frontier_k3e,frontier_k2a
#   DENSE_STRATEGIES=strict,favorite,elite_fresh_fav,proven_router,frontier_k3e,frontier_k2a
docker compose -f docker-compose.consensus.yml --env-file .env.consensus up -d --force-recreate copy-trading-bot
```
- **Env-drift note (diagnosed, no code change needed):** the running container predates
  the `LEDGER_STRATEGIES` line in `.env.consensus` — env only lands on recreate; the
  documented `--env-file` invocation is correct. The recreate above fixes it. (Optional
  hygiene at the same flip: `TRACK_DEPTH=500` — pagination ships; starts deep-pool
  accrual for a future widening.)
- Score forward with: `consensus_signals` rows for the two arms (real `entry_ask` only)
  vs concurrent `favorite`, per the prereg. The replay script re-runs as a retro
  cross-check (`--sweep`), never as the judge of forward claims.

## 7. Runners-up queued (why-not-now)

1. **TRACK_DEPTH 500** — ops flip; no retro data exists for ranks 201–500, so it buys
   future measurability, not current supply claims.
2. **K5/corr-risk re-read under 2–3× supply** (from run 1) — D21's "no game cap" verdict
   was fixed-supply-conditional; re-run `corr_risk_engine` once the arms accrue ~2 weeks.
3. **Live-fill fast consensus (K2)** — ~+1pt ROI-turn on unchanged supply; compounds
   with the wide arms but is gated on the latency-curve verdict; revisit when tape deepens.
4. **Beyond-leaderboard voter discovery** (counterparty mining from the tape/fills) —
   genuinely new supply source; needs a design pass + the trade-tape gap closed.
