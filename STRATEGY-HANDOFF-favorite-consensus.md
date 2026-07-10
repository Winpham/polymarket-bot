# Favorite‑Consensus Strategy — Engineer Handoff

**Audience:** an engineer new to this repo who will build the auto‑trader executor for this strategy.
**Author:** the Soft‑Market Edge Hunt run (2026‑07‑10). **Status: PAPER / forward‑validation. NOT real‑money‑ready.**

> ⛔ **READ THIS FIRST.** This strategy has a *promising but unproven* edge measured on **11 summer‑tournament
> days**. It is **not** cleared for real money, and the auto‑trader you build must run **paper‑only** until the
> forward gate (below) passes. Do not wire real funds. Do not set `ANTHROPIC_API_KEY` or spawn child `claude`
> processes (cost‑zero rule). When in doubt, it stays paper.

---

## 1. What this system is (30‑second orientation)

`~/polymarket-bot` is a **Polymarket consensus / copy‑trading PAPER system** (Rust + Python + SQL, Dockerized
Postgres). It tracks the top leaderboard traders ("sharps"), detects when several of them **converge one‑sided**
on the same market outcome, records those as **signals**, and forward‑tracks how they resolve. Everything is
paper; nothing places real trades today.

- **Rust bot** (`copy-trading-bot/`): polls sharps, assembles per‑market "books," scores them into signals,
  writes to Postgres. Runs on a ~2‑minute cycle.
- **Postgres** (`polymarket-bot-postgres-1` docker container, db `polymarket`, user `bot`): the record.
- **Python scripts** (`scripts/`): read‑only analysis / measurement instruments.
- **`DATA-MODEL.md`**: the authoritative schema/flow doc — read it before touching the DB.

Query the DB with:
```bash
docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket -c "SELECT ..."
```

---

## 2. The strategy in one paragraph

Bet the **favorite outcome** when the tracked sharps form a consensus on it, **only in the price band 0.71–0.98**,
sized in **flat shares**, at the **executable ask**. The edge is that casual money underprices strong favorites in
soft (often lower‑liquidity) markets; the sharps' convergence selects those. Exclude the 0.65–0.71 band (near
coin‑flips are efficient — no edge). Do **not** add a liquidity floor (it cuts the soft markets where the edge
lives). The unit of risk is the **match**, not the individual market (a best‑of‑3 with map/series markets is one
levered bet).

**Exact spec (frozen):**
| parameter | value | why |
|---|---|---|
| base signal | `strategy='favorite'` consensus arm | the only realizable‑positive arm |
| price band | **0.71 – 0.98** (on `entry_ask`, or `initial_mean_price` until capture is fixed) | 0.65–0.71 is efficient coin‑flips; drop it |
| liquidity floor | **none** | tested — a floor *cuts* the soft edge (see §5) |
| entry price | **executable ASK** (copyability cap) | a sharp's edge at their earlier price is not ours |
| fee model | `0.03·p·(1−p)` per share | corrected spread/fee |
| sizing | flat **shares** (not flat $), ⅛‑Kelly‑capped | see `project-polymarket-refined-strategy` |
| risk unit / clustering | the **match** (`scripts/superkey.super_event`) | avoid leg‑piling illusion |

---

## 3. The honest numbers (in‑sample, 11 days, 06/29–07/10)

Match‑clustered, realizable prices, corrected fee. **These are in‑sample and summer‑tournament‑heavy — see §5.**

| band | matches | win% | edge / $1 (ROI‑turn) | honest floor (95% LB) |
|---|---|---|---|---|
| 0.71–0.82 | 72 | 87% | +13.0% | +4.9% |
| 0.82–0.90 | 56 | 93% | +8.9% | +3.9% |
| 0.90–0.98 | 38 | 99% | +6.0% | +5.1% |
| **POOLED 0.71–0.98** | **118** | **93%** | **+11.3%** | **+6.7%** |

Bootstrap second opinion (resample matches 2000×): point **+8.1%**, 5th‑pct LB **+5.1%**. Holds.

### What to REALISTICALLY expect running it forward for a month
- **ROI‑on‑turnover: ~+3%** (honest range −2% to +8%), **not** the +11% in‑sample — discounted for selection
  reward, the in‑sample fade (§5), and the post‑tournament softness decline.
- **Daily ROI on capital** is mechanically ~1.1× ROI‑turn ≈ +2–4%/day, **but that number is deceptive** — it's a
  high % on a **tiny deployable base**. These are thin markets; you can get filled on only ~$20–80/pick before you
  move the price. **Capacity is the binding constraint, not the percentage.** Do not scale capital up expecting the
  % to hold — you become the liquidity and the edge collapses.
- A single month is high variance (a few big slate days carry it). Expect the month to land anywhere from −5% to
  +15% on turnover by luck alone. **One month proves little; ~6 weeks + a non‑tournament stretch is the real test.**

---

## 4. 🔧 THE ONE PREREQUISITE before any of the above is trustworthy: fix ask capture

The realizable prices in the DB are **selection‑biased**. `entry_ask` is captured on the *first housekeeping pass*
that reaches an open signal (~10–15 min after it fires). Markets that **resolve fast** (obvious chalk → winners)
resolve before capture and get **no ask**; only slow, contested (loss‑prone) markets get an ask. Result: the
picks we have realizable prices for are systematically **worse** than the full population (verified: same band,
win rate 85% for captured vs 98% for uncaptured). Every "realizable" number is biased pessimistic by ~7 points.

**Fix:** capture the executable ask **at signal detection** (the instant it fires), not at the first housekeeping
pass. Then fast‑ and slow‑resolving picks both get a representative price.
- Where: the consensus cycle, `copy-trading-bot/src/cycles/consensus_cycle.rs`, at signal upsert time; the ask
  source is the CLOB `/book` endpoint (already used) or the live `clob_price_tape` (migration 040, continuous,
  **unbiased** — it captures regardless of resolution speed).
- **This is the highest‑value change in the whole project.** Until it's done, forward numbers repeat the bias.
  Build the executor to record the ask‑at‑fire for every signal it acts on.

---

## 5. Why it is NOT real‑money‑ready (the caveats, do not skip)

1. **Selection‑biased prices** (§4) — fix first.
2. **In‑sample fade:** our own time‑split shows early half +13.0% (LB +7.3%) but **late half +7.1% (LB −1.2%)** —
   the lower bound goes negative in the second half. Classic decay signature; unresolved.
3. **All summer tournaments** (World Cup + Wimbledon). Zero regular‑season / efficient‑market data. Whether the
   edge transfers to fall NFL/NBA is **completely untested**, and the mechanism (casual‑money softness) may be
   tournament‑specific. *Note:* tennis (the only category with clean independence) is **positive** on the unbiased
   sample (+13.5%, LB +6.3%) — encouraging, but Wimbledon is itself summer softness.
4. **Day concentration:** drop the top‑2 slate days and the LB falls to +0.8%. A few days carry it.
5. **Capacity:** thin soft markets → small deployable size. High % on small dollars; does not scale.
6. **Selection reward:** the 0.71–0.98 cut was chosen from this same data; the true floor is lower than +6.7%.

---

## 6. Build order for the auto‑trader (staged — do NOT skip to live)

1. **Paper executor.** Subscribe to new `favorite` signals in `consensus_signals` (band 0.71–0.98). For each, record
   the **ask‑at‑detection** (§4), simulate a flat‑shares fill, and track resolution → realized paper P&L. Reuse the
   existing accounting convention (`scripts/audit_pnl_books.py` for reference; corrected fee `0.03·p·(1−p)`).
2. **Wire the capture fix (§4)** so the paper fills use unbiased ask‑at‑fire.
3. **Forward gate.** Run against the pre‑registered gate: `reports/PREREG_20260710T050430Z_softmarket.md`
   (objective = cluster‑robust realizable ROI‑turn LB; volume + duration + disjoint‑regime floors; beat the
   champion; ≥6 forward weeks; kill condition). Watch the **lower bound**, not the point, and watch it **through a
   non‑tournament stretch.**
4. **Only after the forward LB holds positive through non‑tournament markets** — bring a human decision to enable
   real money, small size, capacity‑capped. Never automatic.

### Sizing rules (frozen)
- **Flat shares**, never flat $ (`project-polymarket-refined-strategy`).
- **⅛‑Kelly cap**; size the **match**, not the leg (`project-polymarket-correlated-risk`).
- Cap per‑pick size to what the book fills at the good ask (~$20–80); do not chase depth.

### DO‑NOT list
- ❌ No real money until the forward gate passes. ❌ No scaling capital past fillable size.
- ❌ No finer price bands / per‑sport / per‑day cuts (overfitting — all tested and refused).
- ❌ No liquidity floor (tested: it *hurts*). ❌ No flat‑$ sizing.
- ❌ Cost‑zero: never set `ANTHROPIC_API_KEY`, never spawn child `claude`.

---

## 7. Where everything is

| what | where |
|---|---|
| Data model / schema | `DATA-MODEL.md` |
| Consensus scoring engine | `copy-trading-bot/src/scanner/consensus.rs` |
| The cycle (poll → assemble → score → upsert) | `copy-trading-bot/src/cycles/consensus_cycle.rs` |
| Signals table | `consensus_signals` (Postgres); grain = (strategy, condition_id, outcome_index) |
| Realizable entry | columns `entry_ask`, `entry_ask_mid` on `consensus_signals` |
| Match clustering key | `scripts/superkey.py` → `super_event()` |
| Cluster‑robust LB math | `scripts/effective_n.py` → `cluster_robust()`, `_t_ppf()` |
| P&L accounting reference | `scripts/audit_pnl_books.py` |
| **This run's measurement instrument** | `scripts/soft_market_edge.py` (`--selftest`) |
| **This run's diagnosis** | `scripts/esports_conversion_gap.py`, `reports/ESPORTS-CONVERSION-GAP.json` |
| **Frozen forward gate** | `reports/PREREG_20260710T050430Z_softmarket.md` |
| Shadow soft arms (esports, default‑off) | `soft_market_arms()` in `consensus.rs`; flag `CONSENSUS_SOFT_MARKET_ARM` |

### Reproduce the headline numbers
```bash
cd ~/polymarket-bot
python3 scripts/soft_market_edge.py --selftest    # instrument self-test
# band table + verification were computed ad-hoc; the queries live in this run's history.
# Core query: favorite signals, resolved, band 0.71-0.98, clustered at super_event, fee 0.03p(1-p).
```

---

## 8. One‑line status for standup

> Favorite‑consensus, band 0.71–0.98, is a *promising but unproven* paper edge (~+11% ROI‑turn in‑sample on 11
> summer days, realistically ~+3% forward, capacity‑limited). Blocking issue: ask‑capture bias — fix capture‑at‑
> detection first. Then paper‑forward against the frozen prereg for ~6 weeks incl. a non‑tournament stretch. No
> real money until the forward lower bound holds. Nothing here is bankable yet.
