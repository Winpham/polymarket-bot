#!/usr/bin/env python3
"""
ANATOMY OF THE FOLLOWER TAX -- what is the 4.6c actually MADE OF?

copy_econ.py MEASURED the tax and killed copy-trading. It did not decompose it. The headline
number hides a contradiction that decides whether the verdict is right:

  * ~75% of the tax lands within 5 SECONDS, and it is FLAT from 60s to 6h (4.07 -> 4.60c).
    That is a JUMP, permanent, with no reversion.
  * but these wallets bet a MEDIAN OF $10. A $10 taker order cannot jump a book 3.4c.

"Their fill IS the move" (the story in the retraction) cannot explain both. So either the
measurement has an artifact, or the price jumps for a reason that merely COINCIDES with their
trade. Those have opposite prescriptions, so we test them apart.

THE FOUR TESTS
--------------
T1  SAME-TX CONTAMINATION (an artifact that would FAKE the tax).
    A taker order that walks the book produces MANY prints at RISING prices -- and the maker
    counterparties of those prints are DIFFERENT WALLETS. copy_econ self-excludes on `wallet`,
    so a roster wallet's own book-walk re-enters its own follow-on window as "other wallets'
    prints at higher prices". The clean exclusion is the ON-CHAIN TX: one order = one tx_hash.
    => recompute the tax excluding same-tx prints. If it collapses, the tax was partly our own
       measurement eating its own tail.

T2  THE EVENT STUDY -- the decisive one. Price path in event time, t0-1h .. t0+6h.
      pre-drift  = P(t0) - P(t0-300)     was the price ALREADY running before they bought?
      jump       = P(t0+10) - P(t0)      did it move AT their trade?
      post-drift = P(t0+6h) - P(t0+10)   did it keep going (information) or revert (impact)?
    - no pre-drift + jump + no reversion   => private information. Uncopyable, verdict stands.
    - pre-drift already present            => they are RIDING a public wave, not causing it.
                                              Then the signal is the WAVE, and we can be early.
    - jump then reversion                  => liquidity/impact. Wait it out and the tax is a myth.

T3  THE CONTROL THAT DECIDES WHO OWNS THE TAX.  Two controls, and the CONTRAST is the finding:
      (a) BLIND control  -- a random non-roster taker BUY anywhere in the market.
      (b) MOMENT control -- a random NON-ROSTER taker BUY in the SAME market+outcome, within
          +/-30 min and +/-3c of the roster trade. Same market, same regime, same price level;
          the ONLY thing that differs is WHO traded.
    If the MOMENT control shows the SAME ~4c tax, the tax belongs to the MOMENT, not the wallet:
    the roster is not informed, it is merely CO-LOCATED IN TIME with whatever repriced the market.
    That kills "skill" as the object of study and replaces it with "the event".
    If the MOMENT control shows ~0, the wallet genuinely carries information the market lacks.

T4  SIZE.  Tax vs their fill size, by decile. Impact scales with size; information does not.
    A flat curve is proof the tax is NOT their own impact.

Everything is measured OUT-OF-SAMPLE (window B), on the roster fit in window A, with CIs
bootstrapped CLUSTERED ON THE MARKET (wallets share markets; a shared resolution moves them
together, so treating fills as independent fakes significance).

*** OPERATIONAL NOTE -- READ BEFORE EDITING THE SQL ***
This Postgres serves the LIVE bot. An earlier version of copy_econ went cartesian and took the
production database down. Rules, inherited and non-negotiable:
  - the tape is streamed MARKET-BY-MARKET in bounded batches; nothing is joined fill-to-fill
  - every session sets work_mem and statement_timeout, so a bad query dies instead of the server
  - all window logic is numpy, never SQL

Usage:
  ./tax_anatomy.py --self-test      # synthetic fixtures, no DB; exits non-zero on failure
  ./tax_anatomy.py                  # measure; writes reports/niche/tax_anatomy.json
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
GUARD = "SET work_mem='64MB'; SET statement_timeout='240s'; "

BATCH = 250
SEED = 20260714

# event-time buckets, seconds relative to the roster fill
BUCKETS = [-3600, -1800, -900, -300, -60, -10, 0, 10, 60, 300, 900, 3600, 21600]

MOMENT_DT = 1800      # +/-30 min   (moment control)
MOMENT_DP = 0.03      # +/-3c       (moment control)


def psql(sql):
    out = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr[:800])
    return list(csv.DictReader(io.StringIO(out.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def cluster_boot(recs, n_boot=2000, seed=SEED):
    """recs = [(market, value)]. Bootstrap resamples MARKETS, not fills."""
    if not recs:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0, "n_markets": 0}
    by = defaultdict(list)
    for m, v in recs:
        by[m].append(v)
    k = list(by)
    s = np.array([sum(by[x]) for x in k], float)
    n = np.array([len(by[x]) for x in k], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(k), (n_boot, len(k)))
    mu = s[idx].sum(1) / np.maximum(n[idx].sum(1), 1)
    return {"mean": float(s.sum() / n.sum()),
            "lo": float(np.percentile(mu, 2.5)),
            "hi": float(np.percentile(mu, 97.5)),
            "n": len(recs), "n_markets": len(k)}


def locf(prints, t):
    """Last print at or before t. prints = sorted [(t, price)]. None if none exists."""
    lo, hi = 0, len(prints)
    while lo < hi:
        mid = (lo + hi) // 2
        if prints[mid][0] <= t:
            lo = mid + 1
        else:
            hi = mid
    return prints[lo - 1][1] if lo else None


def next_taker_price(takers, t0, horizon, excl_tx=None, excl_wallet=None):
    """Mean price of taker-BUY prints in (t0, t0+horizon] -- what a follower actually pays.
    excl_tx removes the signal's OWN on-chain order (its book-walk + its maker counterparties)."""
    out = [px for (t, px, w, tx) in takers
           if t0 < t <= t0 + horizon
           and (excl_wallet is None or w != excl_wallet)
           and (excl_tx is None or tx != excl_tx)]
    return float(np.mean(out)) if out else None


# ----------------------------------------------------------------------------- self-test
def self_test():
    # locf
    p = [(0.0, 0.10), (5.0, 0.20), (9.0, 0.30)]
    assert locf(p, -1) is None
    assert locf(p, 0) == 0.10
    assert locf(p, 6) == 0.20
    assert locf(p, 100) == 0.30

    # next_taker_price honours BOTH exclusions
    tk = [(1.0, 0.50, "A", "tx1"), (2.0, 0.55, "B", "tx1"), (3.0, 0.60, "C", "tx2")]
    # B is a *different wallet* but the SAME on-chain order as A: wallet-exclusion alone lets it in
    assert abs(next_taker_price(tk, 0.0, 10, excl_wallet="A") - (0.55 + 0.60) / 2) < 1e-9
    # tx-exclusion removes the whole book-walk -- this is the contamination T1 is about
    assert abs(next_taker_price(tk, 0.0, 10, excl_tx="tx1") - 0.60) < 1e-9
    assert next_taker_price(tk, 5.0, 10) is None

    # cluster_boot: 2 markets, one dominant -- clustering must not treat fills as independent
    r = cluster_boot([("m1", 1.0)] * 100 + [("m2", 0.0)], n_boot=500)
    assert r["n_markets"] == 2 and r["n"] == 101
    assert 0.0 <= r["lo"] <= r["mean"] <= r["hi"] <= 1.0
    # a constant series has a degenerate CI
    r2 = cluster_boot([("m%d" % i, 0.04) for i in range(50)], n_boot=500)
    assert abs(r2["mean"] - 0.04) < 1e-9 and abs(r2["hi"] - r2["lo"]) < 1e-9
    print("self-test OK")
    return 0


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--roster", default="reports/niche/global_profit_floor20.json")
    ap.add_argument("--ranker", default="eb_shrunk")
    ap.add_argument("--out", default="reports/niche/tax_anatomy.json")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    R = [r for r in json.load(open(a.roster)) if r["ranker"] == a.ranker][0]["roster"]
    wallets = [w["wallet"] for w in R]
    wl = q_lit(wallets)
    print(f"roster: top-{len(wallets)} by {a.ranker}  (window-B / OUT-OF-SAMPLE signals only)\n")

    wfilt = ("AND h.condition_id IN (SELECT condition_id FROM ("
             "  SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) x "
             "  WHERE x.mts > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) "
             "                 FROM (SELECT condition_id, MAX(ts) mts FROM harvest_wm "
             "                       GROUP BY 1) y))")

    sigs = psql(f"""
      WITH res AS (SELECT condition_id, outcome_index, BOOL_OR(outcome_won) won
                   FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
      ok AS (SELECT condition_id, niche, n_trades FROM harvest_markets WHERE NOT truncated)
      SELECT h.condition_id, h.outcome_index, h.wallet, h.tx_hash,
             EXTRACT(EPOCH FROM h.ts) t, h.price p, h.size_usd sz,
             (r.won::int)::float8 won, ok.niche, ok.n_trades
      FROM harvest_fills h
      JOIN ok ON ok.condition_id = h.condition_id
      JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
      WHERE h.side='BUY' AND h.is_maker=false AND h.wallet IN ({wl})
        {wfilt};
    """)
    print(f"{len(sigs):,} roster taker-BUY signals")

    by_mkt = defaultdict(list)
    for s in sigs:
        by_mkt[s["condition_id"]].append(s)
    mkts = list(by_mkt)
    print(f"across {len(mkts):,} markets -- streaming the tape in batches of {BATCH}")

    # full tape for those markets (BOTH the level series and the taker series)
    allp = defaultdict(list)     # (cid,oidx) -> [(t, price)]                 every BUY print
    takers = defaultdict(list)   # (cid,oidx) -> [(t, price, wallet, tx)]     taker BUYs only
    rosterset = set(wallets)
    for i in range(0, len(mkts), BATCH):
        chunk = mkts[i:i + BATCH]
        for r in psql(f"""
              SELECT condition_id, outcome_index, wallet, tx_hash, is_maker,
                     EXTRACT(EPOCH FROM ts) t, price p
              FROM harvest_fills
              WHERE side='BUY' AND condition_id IN ({q_lit(chunk)});"""):
            key = (r["condition_id"], r["outcome_index"])
            t, p = float(r["t"]), float(r["p"])
            allp[key].append((t, p))
            if r["is_maker"] == "f":
                takers[key].append((t, p, r["wallet"], r["tx_hash"]))
        sys.stdout.write(f"\r  {min(i+BATCH, len(mkts)):,}/{len(mkts):,} markets")
        sys.stdout.flush()
    for d in (allp, takers):
        for k in d:
            d[k].sort(key=lambda x: x[0])
    print(f"\n  tape: {sum(len(v) for v in allp.values()):,} BUY prints "
          f"({sum(len(v) for v in takers.values()):,} taker)\n")

    out = {}

    # ---------------------------------------------------------------- T1  same-tx contamination
    print("=" * 78)
    print("T1  SAME-TX CONTAMINATION -- is the tax partly the signal's OWN book-walk?")
    print("=" * 78)
    HORIZ = [5, 60, 300, 3600, 21600]
    print(f"{'horizon':>10s} {'tax (wallet-excl)':>19s} {'tax (TX-excl)':>15s} "
          f"{'artifact':>10s} {'n':>7s}")
    print("-" * 78)
    out["T1"] = {}
    for H in HORIZ:
        w_tax, x_tax = [], []
        for s in sigs:
            key = (s["condition_id"], s["outcome_index"])
            t0, p0, w0, tx0 = float(s["t"]), float(s["p"]), s["wallet"], s["tx_hash"]
            tk = takers.get(key, [])
            pw = next_taker_price(tk, t0, H, excl_wallet=w0)
            px = next_taker_price(tk, t0, H, excl_wallet=w0, excl_tx=tx0)
            if pw is not None:
                w_tax.append((s["condition_id"], pw - p0))
            if px is not None:
                x_tax.append((s["condition_id"], px - p0))
        bw, bx = cluster_boot(w_tax), cluster_boot(x_tax)
        lab = f"{H}s" if H < 60 else (f"{H//60}m" if H < 3600 else f"{H//3600}h")
        print(f"{lab:>10s} {bw['mean']:>+19.4f} {bx['mean']:>+15.4f} "
              f"{bw['mean']-bx['mean']:>+10.4f} {bx['n']:>7,}")
        out["T1"][H] = {"wallet_excl": bw, "tx_excl": bx}
    print("\n  artifact = how much of the 'tax' was the signal's own order, double-counted")
    print("  through the DIFFERENT wallets on the maker side of its own book-walk.\n")

    # ---------------------------------------------------------------- T2  event study
    print("=" * 78)
    print("T2  EVENT STUDY -- the price path around their trade (level, LOCF, all BUY prints)")
    print("=" * 78)
    paths = defaultdict(list)
    for s in sigs:
        key = (s["condition_id"], s["outcome_index"])
        t0, p0 = float(s["t"]), float(s["p"])
        pr = allp.get(key, [])
        for b in BUCKETS:
            v = locf(pr, t0 + b)
            if v is not None:
                paths[b].append((s["condition_id"], v - p0))   # normalised to THEIR price
    print(f"{'t rel':>8s} {'P(t) - P_them':>15s} {'95% CI':>22s} {'n':>7s}")
    print("-" * 78)
    out["T2"] = {}
    for b in BUCKETS:
        r = cluster_boot(paths[b])
        lab = (f"{b}s" if abs(b) < 60 else
               (f"{b//60}m" if abs(b) < 3600 else f"{b/3600:+.0f}h"))
        star = "  <- their fill" if b == 0 else ""
        print(f"{lab:>8s} {r['mean']:>+15.4f} [{r['lo']:+.4f},{r['hi']:+.4f}] "
              f"{r['n']:>7,}{star}")
        out["T2"][b] = r
    pre = out["T2"][-300]["mean"] - out["T2"][-3600]["mean"]
    print(f"\n  pre-drift  P(t0-300) - P(t0-3600) = {pre:+.4f}")
    print(f"  the level AT their fill vs 1h before  = {-out['T2'][-3600]['mean']:+.4f}")
    print("  (a large positive pre-move means they are RIDING a wave, not making it)\n")

    # ---------------------------------------------------------------- T3  the two controls
    print("=" * 78)
    print("T3  WHO OWNS THE TAX?  blind control vs MOMENT-MATCHED control")
    print("=" * 78)
    rng = np.random.default_rng(SEED)
    blind, moment = [], []
    for s in sigs:
        key = (s["condition_id"], s["outcome_index"])
        t0, p0, w0 = float(s["t"]), float(s["p"]), s["wallet"]
        tk = takers.get(key, [])
        nonr = [x for x in tk if x[2] not in rosterset]
        if not nonr:
            continue
        # (a) blind: any non-roster taker BUY in this market
        c = nonr[rng.integers(0, len(nonr))]
        v = next_taker_price(tk, c[0], 300, excl_wallet=c[2], excl_tx=c[3])
        if v is not None:
            blind.append((s["condition_id"], v - c[1]))
        # (b) moment: non-roster taker BUY near them in TIME and PRICE
        near = [x for x in nonr
                if abs(x[0] - t0) <= MOMENT_DT and abs(x[1] - p0) <= MOMENT_DP and x[2] != w0]
        if near:
            c = near[rng.integers(0, len(near))]
            v = next_taker_price(tk, c[0], 300, excl_wallet=c[2], excl_tx=c[3])
            if v is not None:
                moment.append((s["condition_id"], v - c[1]))
    rost = [(s["condition_id"],
             next_taker_price(takers.get((s["condition_id"], s["outcome_index"]), []),
                              float(s["t"]), 300, excl_wallet=s["wallet"],
                              excl_tx=s["tx_hash"]) - float(s["p"]))
            for s in sigs
            if next_taker_price(takers.get((s["condition_id"], s["outcome_index"]), []),
                                float(s["t"]), 300, excl_wallet=s["wallet"],
                                excl_tx=s["tx_hash"]) is not None]
    print(f"{'group':>28s} {'5-min tax':>11s} {'95% CI':>22s} {'n':>7s}")
    print("-" * 78)
    out["T3"] = {}
    for name, recs in (("ROSTER (the signal)", rost),
                       ("blind control", blind),
                       ("MOMENT-matched control", moment)):
        r = cluster_boot(recs)
        out["T3"][name] = r
        print(f"{name:>28s} {r['mean']:>+11.4f} [{r['lo']:+.4f},{r['hi']:+.4f}] {r['n']:>7,}")
    print("\n  If MOMENT ~= ROSTER: the tax belongs to the MOMENT, not the wallet. The roster is")
    print("  not informed -- it is CO-LOCATED IN TIME with whatever repriced the market.")
    print("  If MOMENT ~= 0: the wallet really does carry information the market lacks.\n")

    # ---------------------------------------------------------------- T4  size
    print("=" * 78)
    print("T4  DOES THE TAX SCALE WITH THEIR SIZE?  (impact does; information does not)")
    print("=" * 78)
    sized = []
    for s in sigs:
        v = next_taker_price(takers.get((s["condition_id"], s["outcome_index"]), []),
                             float(s["t"]), 300, excl_wallet=s["wallet"], excl_tx=s["tx_hash"])
        if v is not None:
            sized.append((float(s["sz"]), s["condition_id"], v - float(s["p"])))
    sized.sort()
    qs = np.quantile([x[0] for x in sized], [0, .2, .4, .6, .8, 1.0])
    print(f"{'their size':>22s} {'5-min tax':>11s} {'95% CI':>22s} {'n':>7s}")
    print("-" * 78)
    out["T4"] = []
    for i in range(5):
        lo, hi = qs[i], qs[i + 1]
        grp = [(c, v) for (z, c, v) in sized if (lo <= z <= hi if i == 4 else lo <= z < hi)]
        r = cluster_boot(grp)
        r["lo_usd"], r["hi_usd"] = float(lo), float(hi)
        out["T4"].append(r)
        print(f"{'$%.0f - $%.0f' % (lo, hi):>22s} {r['mean']:>+11.4f} "
              f"[{r['lo']:+.4f},{r['hi']:+.4f}] {r['n']:>7,}")
    print()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
