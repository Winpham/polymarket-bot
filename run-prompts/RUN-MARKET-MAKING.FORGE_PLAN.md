# Implementation Blueprint: Market-Making — Stage-0 Precondition Measurement (and the verdict to NOT pivot)

**What this changes:** it does NOT build a market-maker. It answers, for ~$0 and no Rust, whether we
have any seat at market-making at all — by measuring a single falsifiable precondition on data we
already hold plus two public HTTP endpoints — and it names the one move that actually dominates the
whole decision (flip `DENSE_CAPTURE` on to measure λ). The headline is a **strategic verdict backed by
a cheap, staged, kill-first measurement ladder**, not an MM build.

> Forge provenance: Diagnostician + Designer A (Direct/Rust build) + Designer B (Rethink/Python ladder),
> reality-checked by the orchestrator against the **live API** (both load-bearing facts verified, §Facts).
> Full debate record: `RUN-MARKET-MAKING.FORGE_DEBATES.md`.

---

## 0. The strategic verdict (decided first — this is the actual answer to "is this the best approach?")

**No. Do not pivot to market-making.** MM is a from-scratch, pro-dominated, reward-compressed,
legally-gated microstructure business whose one differentiated angle ("informed MM", quoting around a
better fair-value) is **downstream of a directional edge we have certified at exactly zero** (λ̂≈0.15,
below the profit floor). It would *replace* the copy-trading stack, not compound it.

**The move that dominates the whole decision** is not an MM build and not even the MM measurement — it is
the **already-built config flip `DENSE_CAPTURE=true`** (`config.rs:162-180`; spawn already coded
`live.rs:227-249`; `signal_price_trajectory` is globally **0 rows** today). That flip measures λ — the
shared load-bearing unknown under BOTH the real favorite-consensus edge AND the MM signal-skew thesis —
for one config line, fully reversible, ~2 weeks to a real λ̂. Do that first.

**MM earns at most a $0-at-risk Stage-0 MEASUREMENT** of one precondition, and even that is gated on one
question only Tue can answer (§7). Build nothing that signs, places, or holds capital.

### The single falsifiable precondition for having a seat
> There exists a **reachable** niche — latency-tolerant (slow / long-dated; NOT crypto-updown or live
> sports) and high-enough-volume — where the realized bid-ask **half-spread a passive two-sided quoter
> earns EXCEEDS the adverse-selection cost** (the mean adverse mid-move against a resting quote over its
> time-to-fill/cancel), with **shark density** low enough that our 10–100 ms latency isn't systematically
> picked off.

Needs **no directional edge** — only spread > adverse-selection in *some* reachable pocket. The whole
Stage-0 ladder exists to falsify this fast and cheap.

### First numbers already in hand (Rung 0, run by Designer B over existing data)
- **Reward** (`entry_ask − entry_ask_mid`, 2,417 paired signals): mean **+0.48¢**, best niche ~**0.75¢**.
- **Hazard** (`|Δ market_price|` over 63,200 `consensus_snapshots` steps): median **1.9¢**, mean **6.5¢**.
- ⇒ **hazard is 4–13× the reward on every niche we can currently see.** The lone positive datapoint
  (round-tripper +7.1¢) is survivorship bias: only **47%** of its tokens were ever sold; the held 53%
  won just **37%** — the adverse selection hides in the unsold half. **Expected Stage-0 outcome: a fast,
  honest NULL.**

---

## Items

### 1. Rung 0 — the existing-data read (~1 hour, $0, Python/SQL only) — DO FIRST

**Before:** we assert "spreads are ~1¢" from 2,416 taker-side favorite-market half-spreads; no
comparison to the hazard; no verdict.
**After:** a niche-stratified table of `median(half_spread) − E[adverse_drift(τ)]` with a pre-registered
KILL verdict — likely negative everywhere visible, killing the general case for ~$0.

**Implementation** (extend the existing `scripts/mm_premise_probe.sql`; all columns confirmed to exist):
```sql
-- Reward per niche (taker-quoted half-spread; favorite-tilted, one-sided — a biased FLOOR on maker spread)
SELECT (is_sports::int) AS sports, width_bucket(entry_ask_mid,0,1,5) AS band,
       count(*) n, round(avg(entry_ask-entry_ask_mid)::numeric,4) half_spread_mean,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY entry_ask-entry_ask_mid))::numeric,4) half_spread_med
FROM consensus_signals WHERE entry_ask IS NOT NULL AND entry_ask_mid IS NOT NULL
GROUP BY 1,2 ORDER BY half_spread_mean DESC;
-- Hazard per niche (adverse mid drift over the maker's hold horizon; change-only ⇒ conservative UPPER bound)
SELECT round(avg(abs(dp))::numeric,4) drift_mean,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(dp)))::numeric,4) drift_med
FROM (SELECT market_price - lag(market_price) OVER (PARTITION BY signal_id ORDER BY ts) dp
      FROM consensus_snapshots) s WHERE dp IS NOT NULL;
```
Estimators (Python): `net_cell = median(half_spread|niche) − E[|adverse_drift| over τ∈{5,10,30,60}min|niche]`.
De-bias the round-trip signal explicitly: `roundtrip_spread` sold-only is biased UP; report
`disposition_bias = 1 − frac_roundtripped` and the held-subset win-rate alongside it.

**KILL rule (pre-registered):** if `net_cell < 0` for **every** stratum AND Tue's live-deploy answer is
No → **STOP, branch falsified for ~$0**. A NULL here is a successful run (D23 posture).

**What Rung 0 CANNOT answer (why Rung 1 exists):** every row we hold was logged *because a favorite
consensus fired* — it is blind to the exact "slow pocket the pros ignore" the precondition needs. Rung 0
kills what it can see; it cannot greenlight.

**Source:** Rethink (Designer B). **Cost:** $0. **Integration:** extend `scripts/mm_premise_probe.sql` +
new `scripts/mm_rung0.py` (imports `superkey.super_event`; belief-blind side-shuffle via `selection_null`).

---

### 2. Rung 1 — retrospective hazard over the *reachable* niches (~hours, $0, Python only, NO wait)

**Before:** zero data on slow/non-favorite markets — the one place MM could live.
**After:** for each candidate slow niche, `adverse_τ`, an adverse-selection signature `picked_off_τ`, and
`shark_density` — measured historically at 1-min granularity, closing Rung 0's blind spot with no capture.

**Verified API facts that make this free (probed live, §Facts):** `GET clob.polymarket.com/prices-history
?market={token}&interval=max&fidelity=1` returns a **dense ~1-min mid series** (4,306 pts / ~30 days on
the probe). Niche frame from `gamma-api.polymarket.com/markets?active=true&closed=false` filtered to
long-dated (`end_date > now+7d`) + liquid (`liquidity_num ≥ floor`), excluding crypto-updown/live-sports
by the `selection_null.py` regime-prefix map, bucketed into ≥2 disjoint niches.

**Estimator (`scripts/mm_hazard.py`, mid-only — a KILL-grade hazard proxy, honestly NOT greenlight-grade):**
```
for each market m, 1-min mid p[t], for τ in {5,10,30,60,240}min:
   adverse_τ    = E[|p[t+τ] − p[t]|]                              # symmetric hazard a two-sided quoter eats
   jumps        = { t : |p[t+1]−p[t]| ≥ κ }                        # large 1-min move ≈ informed print proxy
   picked_off_τ = E[ sign(p[t+1]−p[t])·(p[t+τ]−p[t]) | t∈jumps ]   # does mid KEEP going the print's way? >0 = adverse
shark_density_m = |jumps| / minutes
```
`picked_off_τ > 0` reconstructs the adverse-selection signature from public prints — the diagnostic's
GAP-3 WS shark-counter, with **no WS, no Rust, no capture.** Compare `adverse_τ` to the ~0.75¢ reward ceiling.

**Honest limit (Designer A's correction, accepted):** mids alone cannot detect *when you'd be filled*, so
`adverse_τ` is drift/volatility hazard, an **upper-bound proxy** for true fill-conditioned adverse
selection — sufficient to KILL (if drift ≫ spread everywhere, no fill model rescues it), insufficient to
GREENLIGHT. Greenlight needs the trade tape (Rung 2).

**KILL rule:** if `E[adverse_τ] ≥ reward_ceiling(≈0.75¢)` in **every** candidate slow niche, or
`picked_off_τ > 0` pervasively → STOP before Rung 2.

**Source:** Rethink (Designer B), with Direct's hazard-vs-adverse honesty grafted. **Cost:** $0.
**Self-test:** injected post-jump continuation δ → `picked_off_τ` recovers δ, monotone in τ; i.i.d. null →
`picked_off_τ≈0`, `E[drift_τ]≈σ√τ` (guards a volatility-artifact false-positive).

---

### 3. Rung 2 — forward spread+tape capture (ONLY if Rung 1 survives; ~1–3 days, Python, $0 capital)

**Before:** no per-niche spread *time-series* and no fill-conditioned adverse-selection — the only terms
not available retroactively.
**After:** for the Rung-1 survivor niches, `net_at_τ = half_spread_live − adverse_at_fill(τ) − fees` with a
Bonferroni lower bound and a belief-blind p-value → the pre-registered SEAT-PLAUSIBLE / FALSIFIED verdict.

**This stays Python** (no Rust struct, no migration, no WS): a `while True: requests.get` loop writing a
flat parquet. `/book` returns full depth over HTTP (verified). The one thing `/book` lacks is the trade
**tape** (it carries only `last_trade_price`), so Rung 2 ALSO polls the trade endpoint — **FLAG: confirm
`clob.polymarket.com/trades?market=` shape at build time; proven fallback is the WS `last_trade_price`
stream `trading-bot/src/scanner/ws.rs:256-279`.** Because the niche is latency-tolerant (prints minutes
apart), a 2–5 s poll brackets each fill fine; a niche whose tape truncates is by definition too fast for
our latency and is excluded.

**Conservative back-of-queue fill model (Designer A — a PASS here is trustworthy):**
```
Resting BID at b=best_bid(t), size q; queue_ahead = resting size at b in snapshot t. Dwell W=60s.
 aggressor_sell_vol_≤b over (t,t+W] ; FILL iff that vol ≥ queue_ahead + q ; fill_time = crossing print.
 (side-unknown prints counted → conservative). Symmetric for the ASK. No fill in W → CANCEL, excluded.
 Report the optimistic queue_ahead:=0 variant as a sensitivity UPPER bound only; go/no-go uses conservative.
half_spread_earned: BID→ mid(fill_time)−b ;  ASK→ a−mid(fill_time)
adverse_at_fill(H): BID(long)→ mid(fill_time)−mid(fill_time+H) ;  ASK(short)→ mid(fill_time+H)−mid(fill_time)   (H∈{30,60,300}s)
net_per_fill(H)   = half_spread_earned − adverse_at_fill(H) − fee − margin_cushion(≈0.2¢)
```
**Belief-blind null (reuse `selection_null.py`):** observed = event-clustered mean of `net_per_fill`
(cluster = `superkey.super_event`). Null = keep `half_spread_earned`, replace `adverse_at_fill` with drift
over the same H from a **random anchor in the same token** (destroys the causal fill→drift link), ≥2000
draws, `p_emp≤0.01`. Secondary: shuffle each fill's side label — a net that survives only from in-sample
side-picking collapses. **Lower bound:** port `promotion.rs::surplus_bounds` (Bonferroni over #niches,
day-deflated `effective_n`, ≥30-cluster floor) verbatim to Python.

**GO/NO-GO (pre-registered, D23-style) — SEAT-PLAUSIBLE iff ALL:** (a) event-clustered net **LB > 0** in
**≥2 disjoint niches** at ≥1 realistic H; (b) ≥30 distinct-event clusters/niche; (c) belief-blind
`p_emp≤0.01` per surviving niche; (d) LB>0 robust across the H grid; (e) `depth_at_touch` ≥ a tradeable
minimum and shark_density not top-decile. **FALSIFIED (STOP) iff** net LB≤0 everywhere OR <2 niches clear
OR p_emp>0.01 everywhere. **KILL the measurement iff** the tape truncates, or fees alone drive LB<0, or
<30 clusters accrue in budget (power-starved = INDETERMINATE, never a PASS).

**Source:** hybrid — Rethink's Python-first transport + Direct's fill model / null / gate. **Cost:** $0
capital, ~13 req/s peak (under the existing `CONSENSUS_MAX_CONCURRENCY=8` budget). **Self-test:** injected
niche (spread 3¢ vs adverse 1¢) → SEAT-PLAUSIBLE; null (2¢ vs 2¢) → FALSIFIED; `--calibrate` 50 pseudo-
niches (drift drawn = spread) → `p_emp` ~uniform, ≤20% below 0.05.

---

## Execution Order

1. **Ask Tue the one gating question** (§7) — *before any code.* If "no", stop at Rung 0's read.
2. **Flip `DENSE_CAPTURE` on** (independent of MM; the dominant move) — 1 config line, measures λ in ~2wk.
   - Verify: `signal_price_trajectory` starts accruing rows; `scripts/clv_lambda.py` switches proxy→trajectory.
3. **Rung 0** (`scripts/mm_rung0.py` + extend `mm_premise_probe.sql`) — ~1 hr. Verify: self-test green;
   verdict printed. **If KILL → stop, write the null finding.**
4. **Rung 1** (`scripts/mm_hazard.py`) — ~hours, only if Rung 0 leaves the untracked-niche escape hatch
   open. Verify: self-test green; per-niche `adverse_τ` vs reward ceiling. **If KILL → stop.**
5. **Rung 2** (`scripts/mm_spread.py`, forward /book+tape poll) — ~1–3 days, only if Rung 1 survives.
   Verify: self-test + `--calibrate` green; SEAT-PLAUSIBLE/FALSIFIED verdict. **Only a SEAT-PLAUSIBLE
   here would justify considering Stage-1 — and only after the Tue question is "yes".**

Each rung is additive, gate-green-committed, self-testing, and revertable. Report ugly-first at every rung.

## Cost Summary

| Item | Tooling | Wait | $ capital | Claude/API |
|---|---|---|---|---|
| DENSE_CAPTURE flip | 1 config line | ~2 wk to λ̂ | $0 | $0 |
| Rung 0 | Python/SQL over existing data | ~1 hr | $0 | $0 |
| Rung 1 | Python over `/prices-history` | ~hours | $0 | $0 |
| Rung 2 | Python `/book`+tape poll → parquet | ~1–3 days | $0 | $0 |
| **Total Stage-0** | **all Python, no Rust, no migration** | **days** | **$0** | **$0** |

## Existing Infrastructure Leveraged

`selection_null.py` (belief-blind shuffle + `--calibrate`), `superkey.super_event` (event clustering),
`promotion.rs::surplus_bounds` (ported to Python), `scripts/mm_premise_probe.sql` (extend), the
`consensus_signals.entry_ask/entry_ask_mid` + `consensus_snapshots` columns (Rung 0), and the public
`clob`/`gamma` HTTP endpoints (Rungs 1–2). The `pilot.rs` kill-switch harness and the Rust WS scaffold are
**Stage-1+ only** — untouched here.

## Rejected Approaches

- **Designer A's Rust L2-depth capturer + migration 039 + `ClobBook` extension** — REJECTED for Stage-0:
  the reality-check confirmed `/book` returns full depth over plain HTTP and `/prices-history` gives
  retroactive dense mids, so the entire Rust build (new structs, `mm_capture.rs`, an immutable migration,
  a WS move) is unnecessary to *measure* the precondition. Retained ONLY as the Stage-1+ upgrade path *if*
  a fast niche ever qualified — which a latency-tolerant precondition guarantees it won't. (Designer A's
  *statistics* — fill model, null, gate — are kept and power Rung 2.)
- **Stage-1 paper sim as the next step** (the MM-thesis §7 recommendation) — REJECTED as premature: it
  spends real engineering on a lane whose downstream gate (US-person ToS, Tue US-located) is a legal wall
  no measurement moves. A green sim that dead-ends at a legal bar is validated-but-unfieldable.
- **Full MM pivot** — REJECTED (§0): negative EV after adverse selection, four stacked near-disqualifiers,
  and its one differentiated angle is downstream of a directional edge certified at zero.

## The iceberg beyond Stage-0 (so the true size is visible, not hidden)

- **Stage 1 (paper sim):** the fill model *is* the experiment — assuming fills at the touch overstates
  P&L because the same informed flow that is your adverse selection also biases your fills. Significant.
- **Stage 2 (live):** the ENTIRE signing/placement stack is net-new — **zero signing crates exist** (grep
  `ethers|alloy|k256|secp256k1` empty): EIP-712 order construction, L2 auth, CLOB `POST /order`,
  cancel/replace, private-key/gas custody, inventory, a low-latency loop. Plus ~$50k practitioner capital
  floor and a UMA oracle-dispute tail that can zero a held position — the *same* directional risk we
  cannot forecast. This is a new company, not a feature.

## Open Questions (resolved during implementation)

1. Trade-tape transport: exact `clob /trades` shape / truncation / taker-side flag — confirm at Rung-2
   build; WS `last_trade_price` (`ws.rs:256-279`) is the proven fallback.
2. Maker/taker **fee schedule** + liquidity-reward formula params — pull from primary source at Rung 2;
   score net at fee=0 AND worst-case; pre-register the go/no-go fee.
3. Gamma niche floors (`liquidity_num`/`volume_num`) + the exact disjoint-niche buckets — pre-register in
   `mm_rung1.py` before capturing.

## §7. The one question only Tue can answer (ask BEFORE writing any capture loop)

**Is live market-making deployment on Polymarket.com (or Polymarket US) EVER realistically on the table
for you, given the US-person ToS?** If **no**, the binding constraint is legal and sits downstream of —
and unmovable by — any measurement: run Rung 0 (it's ~free and clarifies the landscape), then stop; do
not spend Rungs 1–2. If **yes**, the ladder above is the cheapest honest path to a go/no-go, still $0 and
still likely a fast NULL.
