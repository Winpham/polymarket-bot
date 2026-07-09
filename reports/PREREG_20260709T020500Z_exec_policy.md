# PRE-REGISTRATION — Execution-policy shadow ledger (Tier-1 champion refinement)

**UTC stamp:** 2026-07-09T02:05:00Z · **Instrument:** `exec_policy_entries` (migration 041)
+ housekeeping evaluator, flag `EXEC_POLICY_SHADOW` (default OFF).
**Author:** Fable wild-generator run (ONE proposal + ONE code pass). Paper-only, promotes
nothing, arms nothing, no live order under any outcome.

Frozen BEFORE any outcome-joined analysis. The structural motivation (below) was measured
outcome-BLIND: ask trajectories only, never joined to `outcome_won`.

---

## 0. Thesis

The champion (`favorite`, honest ROI-on-turnover ≈ +3.2–3.3% after 1¢-haircut fallback + 2%
fee buffer, verified live 2026-07-09: 324 resolved / 168 events / 10 days) underconverts on
**leverageability**: its measured edge is an average over entry prices captured by the
housekeeping pass ~10–20 min after fire — NOT what a fire-time copier pays.

**Outcome-blind structural read (live tape, 2026-07-09, recency-constrained ≤240s lookups):**
on `favorite` the executable ask sits at ~mid₀+3.4¢ at fire, +2.2¢ at +5 min, +0.6¢ at
+15 min, ~mid₀ at +30 min (n≈20–22 per horizon). The spread shock after sharp buys decays
over ~30 min while the mid does not (decay study D8: no material decay <30 min). So:

- a **fire-time taker** pays ~3¢ over mid — most of the champion edge;
- the ledger's number is implicitly a **patient-taker** number (accident of housekeeping cadence);
- a **resting maker bid near fire-time mid** should be filled BY the relaxing ask — the
  fee-free, capacity-opening entry (maker fee 0; we quote, not chase depth).

This instrument measures all three policies forward, per signal, from the live CLOB tape
(`clob_price_tape`), and books them side-by-side into the existing paper ledger where the
existing honest-P&L machinery judges them. It changes NOTHING about selection, alerting,
sizing, or the champion's own rows.

## 1. Policy menu (FROZEN — constants in code, not env-tunable)

For each newly-fired signal of `EXEC_POLICY_STRATEGIES` (default `favorite,elite_fresh_fav`),
evaluated once, ≥35 min after fire (window complete), within tape retention (≤60 h):

- **P-FIRE `exec_fire:<strat>`** — taker at fire: entry = best_ask at `first_detected_at`
  (last tape inflection ≤ fire, staleness ≤ 900 s). Fee = `FEE_PCT` (2% buffer).
- **P-P15 `exec_p15:<strat>`** — patient taker: entry = best_ask at fire+15 min (same
  staleness rule). Fee = `FEE_PCT`.
- **P-MREST `exec_mrest:<strat>`** — resting maker BUY at `mid_fire = (bid_fire+ask_fire)/2`,
  cancel after 30 min. Filled (REALISTIC) only if a `price_change` PRINT at
  `last_price ≤ mid_fire` with `last_size > 0` occurs in `[fire, fire+30m]` (quote-flicker
  touch is recorded separately as the OPTIMISTIC bound, never booked). Unfilled ⇒ ABSTAIN
  (no ledger row; the abstention is recorded in `exec_policy_entries.maker_print=false`).
  Entry = `mid_fire`. Fee = 0 (makers pay zero; NO rebate modeled — conservative).

Clock discipline: all tape lookups order by `recv_at` (never `exch_ts` — D1-E lesson).
No look-ahead: P-FIRE may not read any tape row with `recv_at > first_detected_at`.

## 2. Metrics (frozen; judged by EXISTING machinery)

Primary, per policy label, from `honest_paper_ledger` / `equity_curve` / `ledger_stats`:
1. ROI-on-turnover vs the champion's own ledger rows on the SAME signals; event-clustered
   LB via the standing scoreboard/gate machinery when read.
2. **Adverse-selection gap for P-MREST**: win_rate(filled) − win_rate(abstained) from
   `exec_policy_entries` joined to outcomes. Materially negative ⇒ the maker trap fires on
   consensus signals too; SAY SO (extends D26/G3, does not contradict it).

Secondary: fill rate (maker_print), touch-vs-print gap (queue optimism bound),
miss-the-winners fraction, tape coverage (share of eligible signals with a fire quote).

## 3. Verdict bands (frozen)

- **INDETERMINATE-BY-POWER** until ≥30 booked resolved signals per policy AND ≥5 distinct
  day-clusters. Expected state for ~1–2 weeks. Do NOT promote.
- **REFINEMENT CONFIRMED** if, at power, P-MREST or P-P15 ROI ≥ champion-ledger ROI on the
  same signals with event-clustered LB > 0 AND (for P-MREST) adverse-selection gap ≥ −2 pp.
- **TRAP CONFIRMED (kill maker arm)** if P-MREST adverse-selection gap < −5 pp at power.
- **MIRAGE CONFIRMED (ledger overstates)** if P-FIRE ROI < champion-ledger ROI − 2 pp at
  power — then the honest board must caveat that +3.2% requires patience, and fire-time
  alert-followers are warned.

## 4. Guardrails

Paper-only; flag default OFF; behavior with flag off byte-identical (no tape reads, no new
writes). Never touches `entry_ask`, alerting, selection, or existing ledger labels. Anything
learned goes through the standing belief-blind gate before promotion. If tape coverage is
poor, report coverage honestly — never backfill from a different clock.
