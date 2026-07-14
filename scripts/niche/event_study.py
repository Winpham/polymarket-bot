#!/usr/bin/env python3
"""
EVENT STUDY: does the informed trader MOVE the price, or RIDE a move already underway?

Tue's objection, and it is the right one: these wallets bet ~$10. A $10 order CANNOT move a
market 4c. So the 4c "follower tax" I measured is almost certainly NOT their market impact --
it is far more likely that they trade INTO an already-moving market (news breaking, odds
shifting), and the post-trade drift is the continuation of a move that started before them.

That distinction changes everything:
  * IF THEY CAUSE THE MOVE -> copying is hopeless; their own signal destroys its value.
  * IF THEY RIDE THE MOVE  -> the move is EXOGENOUS. It was already happening. Then a copier
    is simply LATE to a public repricing -- and the real question becomes whether the move
    over- or under-shoots (does it revert?), and whether the SOURCE of the move is detectable
    earlier than any of these wallets.

The test is an event study aligned on the roster wallet's taker fill at t=0, tracking the
price path from -60m to +6h relative to their entry:

  PRE-DRIFT  (t<0)  If the price is ALREADY rising before they trade, they are chasing.
                    A $10 order cannot cause a move that started before it existed.
  POST-DRIFT (t>0)  Does it keep going (information) or revert (transient impact)?
                    A REVERSION would mean a patient follower gets a better price by waiting.
  SIZE TEST         If a $10 trade shows the SAME move as a $1000 trade, the move CANNOT be
                    impact -- impact scales with size. This is the cleanest causal test.
  QUIET TEST        Trades into a QUIET book (no other prints for 5+ min before). If the move
                    vanishes there, the "tax" only exists when they trade during active
                    repricing -- i.e. it was never theirs.
  CONTROL           Random uninformed wallets, same treatment.

Price proxy: the tape gives executed prices, not quotes. We use the VWAP of all fills in each
time bucket around the event, which is the best available proxy for "where the market was".
"""
import argparse
import csv
import io
import json
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
GUARD = "SET work_mem='128MB'; SET statement_timeout='600s'; "

# buckets in seconds relative to the event (negative = BEFORE their trade)
BUCKETS = [(-3600, -900, "-60..-15m"), (-900, -300, "-15..-5m"), (-300, -60, "-5..-1m"),
           (-60, 0, "-1m..0"), (0, 60, "0..+1m"), (60, 300, "+1..5m"),
           (300, 900, "+5..15m"), (900, 3600, "+15..60m"), (3600, 21600, "+1..6h")]
SEED = 20260714


def psql(sql):
    out = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr[:400])
    return list(csv.DictReader(io.StringIO(out.stdout)))


def boot_mean(vals_by_mkt, n_boot=2000, seed=SEED):
    """Market-clustered mean + CI."""
    k = list(vals_by_mkt)
    if len(k) < 20:
        return None
    s = np.array([sum(vals_by_mkt[x]) for x in k], float)
    n = np.array([len(vals_by_mkt[x]) for x in k], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(k), (n_boot, len(k)))
    mu = s[idx].sum(1) / np.maximum(n[idx].sum(1), 1)
    return (float(s.sum() / n.sum()), float(np.percentile(mu, 2.5)),
            float(np.percentile(mu, 97.5)))


def load(wallet_sql, niche=None):
    nf = f"AND h.niche='{niche}'" if niche else ""
    okf = f"AND niche='{niche}'" if niche else ""
    sigs = psql(f"""
      WITH ok AS (SELECT condition_id FROM harvest_markets WHERE NOT truncated {okf}),
      res AS (SELECT condition_id,outcome_index,BOOL_OR(outcome_won) won FROM trader_fills
              WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
      {wallet_sql}
      SELECT h.condition_id,h.outcome_index,h.wallet,EXTRACT(EPOCH FROM h.ts) t,
             h.price p, h.size_usd sz, (r.won::int)::float8 won
      FROM harvest_fills h JOIN ok USING (condition_id) JOIN w ON w.wallet=h.wallet
      JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
      WHERE h.side='BUY' AND h.is_maker=false {nf};""")
    mkts = sorted({s["condition_id"] for s in sigs})
    tape = defaultdict(list)
    for i in range(0, len(mkts), 500):
        ch = ",".join("'" + c + "'" for c in mkts[i:i + 500])
        for r in psql(f"""SELECT condition_id,outcome_index,wallet,
                                 EXTRACT(EPOCH FROM ts) t, price p, size_usd sz
                          FROM harvest_fills WHERE side='BUY'
                            AND condition_id IN ({ch});"""):
            tape[(r["condition_id"], r["outcome_index"])].append(
                (float(r["t"]), float(r["p"]), r["wallet"], float(r["sz"])))
    # index each (market,outcome) as sorted numpy arrays so bucket lookups are O(log n)
    # binary searches instead of a full scan per signal per bucket (the naive version was
    # O(signals x tape x buckets) and did not finish).
    idx = {}
    for k, v in tape.items():
        v.sort()
        idx[k] = (np.array([x[0] for x in v]),          # t
                  np.array([x[1] for x in v]),          # price
                  np.array([x[2] for x in v], dtype=object))  # wallet
    return sigs, idx


def path(sigs, tape, label, sig_filter=None):
    """Mean price in each bucket MINUS their entry price. Positive after 0 = price rose."""
    rows = [s for s in sigs if (sig_filter is None or sig_filter(s))]
    if len(rows) < 50:
        print(f"  {label:28s} (only {len(rows)} signals)")
        return
    print(f"\n  {label}   ({len(rows):,} signals)")
    print(f"    {'bucket':>12s} {'price - their entry':>20s} {'95% CI':>20s}")
    for lo, hi, name in BUCKETS:
        by = defaultdict(list)
        for s in rows:
            key = (s["condition_id"], s["outcome_index"])
            if key not in tape:
                continue
            T, P, W = tape[key]
            t0, p0, w0 = float(s["t"]), float(s["p"]), s["wallet"]
            i, j = np.searchsorted(T, t0 + lo), np.searchsorted(T, t0 + hi)
            if j <= i:
                continue
            m = W[i:j] != w0                                  # self-excluded
            if m.any():
                by[s["condition_id"]].append(float(P[i:j][m].mean()) - p0)
        r = boot_mean(by)
        if not r:
            continue
        m, l, h = r
        star = "  <-- BEFORE they trade" if hi <= 0 else ""
        print(f"    {name:>12s} {m*100:+19.2f}c [{l*100:+.2f},{h*100:+.2f}]{star}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", default="reports/niche/global_profit_floor20.json")
    ap.add_argument("--ranker", default="eb_shrunk")
    a = ap.parse_args()

    R = [r for r in json.load(open(a.roster)) if r["ranker"] == a.ranker][0]["roster"]
    wl = ",".join("'" + w["wallet"] + "'" for w in R)
    roster_sql = f"w AS (SELECT unnest(ARRAY[{wl}]) AS wallet)"
    ctrl_sql = ("w AS (SELECT h.wallet FROM harvest_fills h "
                "JOIN ok USING (condition_id) WHERE h.side='BUY' AND h.is_maker=false "
                f"AND h.wallet NOT IN ({wl}) "
                "GROUP BY h.wallet HAVING COUNT(*)>=30 ORDER BY md5(h.wallet) LIMIT 150)")

    print("=" * 78)
    print("EVENT STUDY -- is the 4c move THEIRS, or was it already happening?")
    print("=" * 78)

    sigs, tape = load(roster_sql)
    path(sigs, tape, "ROSTER (informed) -- full price path")

    # SIZE TEST: impact scales with size. Information does not.
    print("\n  --- SIZE TEST: if a $10 order shows the same move as a $500 order,")
    print("      the move CANNOT be their impact (impact scales with size) ---")
    path(sigs, tape, "ROSTER, trades UNDER $25", lambda s: float(s["sz"]) < 25)
    path(sigs, tape, "ROSTER, trades OVER $250", lambda s: float(s["sz"]) > 250)

    # QUIET TEST: no other prints in the 5 min before => the market was NOT already moving
    quiet_cache = {}
    def quiet(s):
        kk = (s["condition_id"], s["outcome_index"], s["t"], s["wallet"])
        if kk in quiet_cache:
            return quiet_cache[kk]
        key = (s["condition_id"], s["outcome_index"])
        r = True
        if key in tape:
            T, P, W = tape[key]
            t0, w0 = float(s["t"]), s["wallet"]
            i, j = np.searchsorted(T, t0 - 300), np.searchsorted(T, t0)
            r = not (j > i and (W[i:j] != w0).any())
        quiet_cache[kk] = r
        return r
    print("\n  --- QUIET TEST: they trade into a SILENT book (no other prints for 5 min).")
    print("      If the move vanishes here, it was never theirs ---")
    path(sigs, tape, "ROSTER, quiet book before", quiet)
    path(sigs, tape, "ROSTER, ACTIVE book before", lambda s: not quiet(s))

    csigs, ctape = load(ctrl_sql)
    print("\n  --- CONTROL: random uninformed wallets ---")
    path(csigs, ctape, "CONTROL -- full price path")


if __name__ == "__main__":
    main()
