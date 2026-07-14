# US GO-LIVE CHECKLIST — exactly what must be true before the first dollar

**For Tue. 2026-07-14.** Nothing on this list is optional, and nothing on it can be signed by the system.
**The system proposes; you authorize.**

> **Read this first.** The strategy is **not certified**. On the unit we actually bet — the event — the
> historical record is **one loss in 41 where the market prices 3.2**, which has a **15.8% chance of
> happening if the market is simply right.** The backtest is a **hypothesis**, not a result. **Everything
> below exists so that we find out which, without it costing you money to learn.**

---

## WHAT YOU NEED TO DO (and when)

| # | Action | Blocks | When |
|---|---|---|---|
| **1** | **Nothing.** | — | **Now → ~8 weeks.** Rungs 0–2 (decision engine, paper placer, cage) need **no key, no funding, no decision**. The US book is public. **All of the $0 evidence accrues without you.** |
| **2** | **Submit the Accelerated Tier request.** Send our trailing-30-day **intl** notional to `institutional@polymarket.us`. The venue assigns a taker-fee tier against verifiable volume on another prediction market: **$250k→10% / $1M→25% / $10M→50% off every taker fee, from day one.** | Nothing — pure discount, no strategy change, no new risk (UV-13). | **Any time. Free money; do it when convenient.** |
| **3** | **Review GATE A's verdict.** | Rungs 3–5 | **After ~115 events / ≥30 days.** A **FAIL or INDETERMINATE ⇒ we stay at $0.** That is a real, expected outcome, not a failure of the build. |
| **4** | **Issue an API key** (`polymarket.us/developer`). Key ID + Secret, **shown once**. | Rung 3 | **Only after GATE A clears.** |
| **5** | **Fund the account with the RUNG'S CAPITAL ONLY. Never the full bankroll.** | Rung 4 | Rung 4 = **$5/signal**. **Fund ~$50.** |
| **6** | **Authorize go-live, and confirm the FIRST 10 ORDERS individually.** | Rung 4 | After the preview-only rung is green. |

---

## YOUR PANIC BUTTON — and it is better than anything the intl design has

> **REVOKE THE KEY at `polymarket.us/developer`.** It takes 30 seconds from a phone, and it works **even
> if the machine is compromised, wedged, or on fire.** The bot fails closed on a revoked key.
> *(Revoking an intl EOA private key is impossible — you would have to move the funds.)*
>
> Two others: **`touch /data/US_KILL`** (works even when Postgres is down), and
> **`UPDATE us_exec_halts SET ...`** — a human-only un-halt. **There is no `unhalt()` method in the code.**

⚠️ **KNOW WHAT A HALT CAN AND CANNOT DO.** On a take-only book **nothing rests**, so `cancel-all` is a
**no-op**. **A halt stops us OPENING new positions. It does NOT cut the ones we hold** — those are held to
settlement. **Maximum exposure after you hit the switch = ONE in-flight order at the per-signal cap.**
That is bounded and quantified, and no design can do better. **A drawdown breaker here is a logger, not a
brake.** The real protection is that **positions are tiny and capped ex ante.**

---

## MUST BE TRUE BEFORE THE FIRST REAL ORDER (the system's side)

**Evidence**
- [ ] `GATE-A-PREREG.md` was **frozen before any forward data was read** (done: 2026-07-14).
- [ ] **≥115 events AND ≥30 calendar days** of forward paper.
- [ ] The pre-registered test **PASSES**, including leave-one-event-out and the injected-loss stress.
- [ ] **Zero** mapper alarms, **zero** unexplained positions, **zero** `ReconcileFailed` over the window.
- [ ] **The skip-counterfactual log says our own gate is not destroying the edge** (`ROI(skipped)` is not ≫ `ROI(traded)`).

**Blocking prerequisites (none of these exist yet)**
- [ ] **The staleness watchdog.** *(During this very run, Postgres died for ~2h, `docker ps` said "healthy", and nothing noticed. A forward window with a silent hole in it is not a forward window.)*
- [ ] **A price-matched, side-assigned placebo cohort.** The current one is matched on (league, date) only and carries no side ⇒ **no ROI is computable for it ⇒ GATE A cannot fail honestly.**
- [ ] The skip-counterfactual log.

**The cage**
- [ ] All three default-OFF locks verified: `us-live-exec` **not compiled** · `US_EXEC_ENABLED=false` · `us_exec_halts` seeded **`MasterOff` by migration**.
- [ ] **`us_exec_halts` shipped in the SAME PR as the executor.** *(A container recreate IS a kill-switch reset, and merging the executor is the very event that would erase its halt state.)*
- [ ] Halts are keyed **`(venue, arm)`** — the intl paper arm and the US executor both trade an arm named `favorite`.
- [ ] **The crash-restart drill passes**: SIGKILL mid-send → restart → reconcile correctly abandons. **Automated, not hoped.**
- [ ] **The indeterminate send is induced ON PURPOSE at $5** — `docker kill` mid-POST — and reconcile adopts the fill. *(B2 is the only dangerous boundary in the machine. Exercise it deliberately at $5 before it happens by accident at $50.)*
- [ ] The kill-watch fires `cancel-all` **exactly once and latches**, and **fails closed if it cannot read its own kill-switch.**

**Truth**
- [ ] The realized fee is **read off the venue** (`commissionNotionalTotalCollected`), cross-checked against `report/trades/search`. **Disagreement ⇒ HALT.**
- [ ] The paper VWAP matches `preview.avgPx` on **≥50 signals** *(this is what breaks the shared-mode failure — the paper track and the live executor run the same depth-walk code, so a bug in it would corrupt both in the same direction and GATE A would certify the bug).*
- [ ] The position-feed **latency has been measured**, and the 120s grace / 300s halt were **re-set from that measurement**.

---

## WHAT WE ARE STILL HONESTLY UNSURE OF

1. **Does a US IOC transit through `NEW`?** If it does, a restart landing mid-flight could **master-halt a
   perfectly healthy order.** Mitigated (we assert "no *resting* order", not "no order"), but **unproven
   until a live order.**
2. **Is our own eligibility gate selecting away the edge?** The markets we skip (wide book, thin depth) may
   be precisely the ones whose price has not yet absorbed the sharp's information. **The sign is unknown.**
   The skip log is the only thing that can settle it.
3. **Our own market impact and latency are unmeasured**, and **both bias us optimistic.** GATE A certifies
   the **pick**, not the **fill**. **The rung after GATE A is not "ramp" — it is "spend $5 to measure them."**

---

## THE FRAME

**The system's job is not to trade. It is to refuse to trade until it has earned the right.** Rungs 0–2
cost nothing, need nothing from you, and produce all the evidence. If GATE A fails, **we will tell you
plainly and stop** — and that outcome is a success of the build, not a failure of it.
