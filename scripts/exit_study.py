#!/usr/bin/env python3
"""
CASH-OUT STUDY (truth-audit attack A): do the Polymarket sharps we copy exit BEFORE resolution,
and if so is their exit INFORMATION that predicts our held position failing?

We copy backers' ENTRIES and hold to resolution. `trader_fills` records BOTH sides (BUY + SELL,
timestamped, priced). For each resolved `favorite`/`elite_fresh_fav` signal and each backer wallet
in its `observed_votes` atoms, we reconstruct that wallet's position on the SAME
(condition_id, outcome_index) up to resolution:

  buy_usd / buy_vwap  = Σ BUY size / vwap  (ts ≤ resolved_at)
  sell_usd / sell_vwap= Σ SELL size / vwap (ts <  resolved_at)   ← the exit
  exited(any)     ⇔ sell_usd > 0
  exited(majority)⇔ buy_usd>0 ∧ sell_usd ≥ 0.5·buy_usd

Outputs (all event-clustered on the match super-key):
  1. backer exit rate, by time-to-resolution decile and by profit-at-exit sign (sell_vwap−buy_vwap)
  2. OUR held outcome (win rate, hold surplus vs at-fire entry) conditional on {no / some / majority
     backer exit}, matched within the winner population
  3. counterfactual P&L: hold-to-resolution (ours) vs mirror-their-exit (sell at the backer sell_vwap
     when a majority exits) — priceable from trader_fills SELL price; coverage reported
  4. THE INFORMATION TEST: does "≥1 backer majority-exited" (a live-observable event) predict a
     LOWER win rate on our held position vs matched non-exit signals? Event-clustered win-rate
     difference + seeded label-permutation p (enters the experimental Bonferroni family if it fires).

Self-test:  ./exit_study.py --self-test   (informative-exit fixture MUST be detected; random-exit flat)
Live:       ./exit_study.py
"""

import csv
import io
import random
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
SEED = 20260702
N_PERM = 5000

# One row per (signal, backer): the backer's position on the signal's outcome up to resolution.
SQL = """
WITH sig AS (
  SELECT cs.id, cs.condition_id, cs.outcome_index, cs.resolved_at, cs.outcome_won,
         cs.event_slug, cs.slug, COALESCE(cs.initial_mean_price, cs.mean_price) AS entry,
         lower(a->>'wallet') AS wallet,
         (a->>'ts')::bigint AS atom_ts
  FROM consensus_signals cs, jsonb_array_elements(cs.observed_votes) a
  WHERE cs.resolved AND cs.strategy IN ('favorite','elite_fresh_fav')
),
sb AS (
  SELECT DISTINCT id, condition_id, outcome_index, resolved_at, outcome_won,
         event_slug, slug, entry, wallet, MIN(atom_ts) OVER (PARTITION BY id, wallet) AS buy_ts
  FROM sig
)
SELECT s.id, s.condition_id, s.outcome_index, s.event_slug, s.slug, s.entry,
       s.outcome_won, s.wallet,
       extract(epoch FROM s.resolved_at)::bigint AS resolved_ts,
       s.buy_ts,
       COALESCE(SUM(tf.size_usd) FILTER (WHERE tf.side='BUY'  AND tf.ts<=s.resolved_at),0) AS buy_usd,
       COALESCE(SUM(tf.size_usd*tf.price) FILTER (WHERE tf.side='BUY'  AND tf.ts<=s.resolved_at),0) AS buy_notional,
       COALESCE(SUM(tf.size_usd) FILTER (WHERE tf.side='SELL' AND tf.ts<s.resolved_at),0) AS sell_usd,
       COALESCE(SUM(tf.size_usd*tf.price) FILTER (WHERE tf.side='SELL' AND tf.ts<s.resolved_at),0) AS sell_notional,
       MIN(EXTRACT(epoch FROM tf.ts)) FILTER (WHERE tf.side='SELL' AND tf.ts<s.resolved_at) AS first_sell_ts
FROM (SELECT DISTINCT id, condition_id, outcome_index, resolved_at, outcome_won,
             event_slug, slug, entry, wallet, buy_ts FROM sb) s
LEFT JOIN trader_fills tf
  ON tf.wallet=s.wallet AND tf.condition_id=s.condition_id AND tf.outcome_index=s.outcome_index
GROUP BY s.id, s.condition_id, s.outcome_index, s.event_slug, s.slug, s.entry,
         s.outcome_won, s.wallet, s.resolved_at, s.buy_ts
"""


def fetch():
    out = subprocess.run(PG + ["-c", SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        for k in ("entry", "buy_usd", "buy_notional", "sell_usd", "sell_notional"):
            r[k] = float(r[k] or 0)
        for k in ("resolved_ts", "buy_ts"):
            r[k] = int(r[k]) if r[k] else 0
        r["first_sell_ts"] = float(r["first_sell_ts"]) if r["first_sell_ts"] else None
        r["won"] = 1 if r["outcome_won"] == "t" else 0
        rows.append(r)
    return rows


def ev_key(r):
    return super_event(r["event_slug"], r["slug"]) or r["condition_id"]


def clustered_rate(signals):
    """event-clustered win rate over signal dicts with keys ev, won."""
    ev = defaultdict(list)
    for s in signals:
        ev[s["ev"]].append(s["won"])
    if not ev:
        return float("nan"), 0
    means = [sum(v) / len(v) for v in ev.values()]
    return sum(means) / len(means), len(means)


def info_test(signals, rng, n_perm=N_PERM):
    """signals: list of dict(ev, won, exited). Returns (rate_noexit, rate_exit, diff, p, n_exit_ev).
    diff = rate_noexit − rate_exit (positive ⇒ exit predicts our failure). p via label permutation
    of the `exited` flag across signals, event-clustered, one-sided on diff."""
    ne = [s for s in signals if not s["exited"]]
    ex = [s for s in signals if s["exited"]]
    r_ne, _ = clustered_rate(ne)
    r_ex, n_ex_ev = clustered_rate(ex)
    if n_ex_ev == 0:
        return r_ne, float("nan"), float("nan"), None, 0
    diff = r_ne - r_ex
    flags = [s["exited"] for s in signals]
    k = sum(flags)
    ge = 0
    for _ in range(n_perm):
        perm = flags[:]
        rng.shuffle(perm)
        pe = [s for s, f in zip(signals, perm) if f]
        pn = [s for s, f in zip(signals, perm) if not f]
        rpe, _ = clustered_rate(pe)
        rpn, _ = clustered_rate(pn)
        if (rpn - rpe) >= diff:
            ge += 1
    return r_ne, r_ex, diff, ge / n_perm, n_ex_ev


def run_live():
    rows = fetch()
    n_backer_rows = len(rows)
    any_sell = [r for r in rows if r["sell_usd"] > 0]
    maj = [r for r in rows if r["buy_usd"] > 0 and r["sell_usd"] >= 0.5 * r["buy_usd"]]
    print(f"cash-out study · {n_backer_rows} (signal,backer) pairs on winner signals\n")
    print("1) BACKER EXIT RATE")
    print(f"   any pre-resolution SELL: {len(any_sell)} ({100*len(any_sell)/n_backer_rows:.2f}%)")
    print(f"   majority exit (≥50% of buy): {len(maj)} ({100*len(maj)/n_backer_rows:.2f}%)")
    # profit-at-exit sign + timing decile (majority exits, priced)
    prof_pos = prof_neg = 0
    deciles = defaultdict(int)
    for r in maj:
        if r["sell_usd"] > 0 and r["buy_usd"] > 0 and r["buy_notional"] > 0:
            sell_vwap = r["sell_notional"] / r["sell_usd"]
            buy_vwap = r["buy_notional"] / r["buy_usd"]
            (prof_pos := prof_pos + 1) if sell_vwap >= buy_vwap else (prof_neg := prof_neg + 1)
        if r["first_sell_ts"] and r["resolved_ts"] and r["buy_ts"]:
            win = r["resolved_ts"] - r["buy_ts"]
            frac = (r["first_sell_ts"] - r["buy_ts"]) / win if win > 0 else 0
            deciles[min(9, max(0, int(frac * 10)))] += 1
    print(f"   profit-at-exit sign (majority exits): {prof_pos} up, {prof_neg} down "
          f"(exit in profit ⇒ risk-off, not necessarily information)")
    print(f"   exit timing (fraction of buy→resolution window): "
          + ", ".join(f"d{d}:{deciles[d]}" for d in sorted(deciles)) if deciles else "   (no timed exits)")

    # signal-level aggregation
    sig = defaultdict(lambda: dict(won=0, n_back=0, n_exit_any=0, n_exit_maj=0, ev=None,
                                   entry=0.0, resolved_ts=0, exit_prices=[]))
    for r in rows:
        s = sig[r["id"]]
        s["won"] = r["won"]
        s["ev"] = ev_key(r)
        s["entry"] = r["entry"]
        s["n_back"] += 1
        if r["sell_usd"] > 0:
            s["n_exit_any"] += 1
        if r["buy_usd"] > 0 and r["sell_usd"] >= 0.5 * r["buy_usd"]:
            s["n_exit_maj"] += 1
            if r["sell_usd"] > 0:
                s["exit_prices"].append(r["sell_notional"] / r["sell_usd"])
    sigs = list(sig.values())
    n_sig = len(sigs)
    with_any = [s for s in sigs if s["n_exit_any"] >= 1]
    with_maj = [s for s in sigs if s["n_exit_maj"] >= 1]
    print(f"\n2) OUR HELD OUTCOME conditional on backer exits ({n_sig} winner signals)")
    for label, subset in (("no backer exit", [s for s in sigs if s["n_exit_any"] == 0]),
                          ("≥1 backer any-exit", with_any),
                          ("≥1 backer majority-exit", with_maj)):
        rate, nev = clustered_rate([{"ev": s["ev"], "won": s["won"]} for s in subset])
        print(f"   {label:<26} signals={len(subset):>3} events={nev:>3} held-win-rate={rate:.1%}" if nev else
              f"   {label:<26} signals={len(subset):>3} (no events)")

    # 3) counterfactual P&L: hold vs mirror-majority-exit (flat $100/signal)
    hold = mirror = 0.0
    priced = unpriceable = 0
    for s in sigs:
        entry = min(0.999, s["entry"])
        hold += 100.0 * (s["won"] - entry) / entry
        if s["n_exit_maj"] >= 1 and s["exit_prices"]:
            sell_px = sum(s["exit_prices"]) / len(s["exit_prices"])
            mirror += 100.0 * (sell_px - entry) / entry
            priced += 1
        elif s["n_exit_maj"] >= 1:
            unpriceable += 1
            mirror += 100.0 * (s["won"] - entry) / entry  # can't price → hold (labeled)
        else:
            mirror += 100.0 * (s["won"] - entry) / entry
    print(f"\n3) COUNTERFACTUAL P&L (flat $100/signal, at-fire entry)")
    print(f"   hold-to-resolution (ours):     {hold:+.0f}$")
    print(f"   mirror majority-exits:         {mirror:+.0f}$   "
          f"({priced} exits priced from SELL vwap, {unpriceable} UNPRICEABLE→held)")
    print(f"   Δ (mirror − hold):             {mirror-hold:+.0f}$")

    # 4) information test
    rng = random.Random(SEED)
    sset = [{"ev": s["ev"], "won": s["won"], "exited": s["n_exit_maj"] >= 1} for s in sigs]
    r_ne, r_ex, diff, p, n_ex_ev = info_test(sset, rng)
    print(f"\n4) INFORMATION TEST (does ≥1 backer majority-exit predict OUR failure?)")
    if p is None:
        print(f"   no exit-events → untestable (n_exit_events=0)")
    else:
        print(f"   no-exit win rate {r_ne:.1%} (evts {len([s for s in sset if not s['exited']])}) vs "
              f"exit win rate {r_ex:.1%} (exit events {n_ex_ev})")
        print(f"   diff (no-exit − exit) = {diff:+.1%}, permutation p = {p:.4f}  "
              f"({'exit predicts failure (nominate, FDR-gated)' if p <= 0.05 else 'NOT significant — holding vindicated'})")
    return 0


# --- self-test -------------------------------------------------------------------------------
def _mk(ev, won, exited):
    return {"ev": ev, "won": won, "exited": exited}


def _self_test():
    ok = True
    rng = random.Random(1)
    # Informative fixture: 40 signals; exited⇒always lost, not-exited⇒mostly won. Distinct evs.
    info = ([_mk(f"w{i}", 1, False) for i in range(30)] +
            [_mk(f"l{i}", 0, True) for i in range(10)])
    r_ne, r_ex, diff, p, n_ex = info_test(info, rng, n_perm=2000)
    c1 = p is not None and p <= 0.05 and diff > 0.5
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] informative fixture: diff={diff:+.2f} p={p:.4f} (want p≤0.05, diff>0.5)")
    # Random fixture: exited flag independent of outcome → p should be un-significant (~uniform)
    rng2 = random.Random(2)
    # won alternates within each exit-group of 2 ⇒ exited is orthogonal to won by construction
    base = [_mk(f"e{i}", i % 2, (i // 2) % 2 == 0) for i in range(60)]
    r_ne2, r_ex2, diff2, p2, _ = info_test(base, rng2, n_perm=2000)
    c2 = p2 is not None and p2 > 0.05
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] random fixture: diff={diff2:+.2f} p={p2:.4f} (want p>0.05, flat)")
    # clustered_rate collapses same-ev rows
    rate, nev = clustered_rate([_mk("a", 1, False), _mk("a", 0, False), _mk("b", 1, False)])
    c3 = nev == 2 and abs(rate - 0.75) < 1e-9   # ev a: mean .5, ev b: 1 → (0.5+1)/2=0.75
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] clustered_rate: {nev} evs rate={rate:.3f} (want 2, 0.750)")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_live())
