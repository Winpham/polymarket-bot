#!/usr/bin/env python3
"""
IS THE COPY SURPLUS *SELECTION*, OR IS IT *PRICE COMPOSITION*?

copy_vs_blind.py reported +2.62c surplus for the roster in the 80-100c band (p=0.000, 830 mkts) and
concluded copy-trading is alive there. But its blind control is matched only on a **20c-wide band**.
Both legs' payoff is exactly

        net = won - p - fee

so the surplus decomposes, with NO residual, into three measurable terms:

        surplus = D(won)  -  D(p)  -  D(fee)
                  ^^^^^^     ^^^^     ^^^^^^
                  SKILL      ARTIFACT  bookkeeping

  * If the surplus is D(won) -- the roster's picks WIN MORE OFTEN at the same price -- that is
    genuine selection. It is an edge.
  * If the surplus is -D(p) -- the roster merely ENTERS CHEAPER WITHIN THE SAME 20c BAND -- there is
    ZERO skill in it. The blind leg samples every print across the market's whole life; copy enters
    at one specific point on the price path. An entry-price difference inside a 20c bucket produces
    "surplus" mechanically.

Nobody ran this decomposition. It is cheap and it is decisive, so it runs first.

Then the control that settles it: a PRICE CALIPER. Instead of "same 20c band", require the blind
print to be in the SAME MARKET, SAME OUTCOME, and within +/- eps of the copy leg's ACTUAL ENTRY
PRICE. If the surplus survives a 1c caliper it cannot be price composition -- there is no price
difference left for it to hide in.

Also re-prices at the CORRECT fee. The predecessor typed sports=0.03; the repo's own verified figure
is sports 0.05 (docs) / US taker 0.06 (confirmed on all 2,999 US markets). Same error class as the
3% constant this whole line of work exists to expose -- only this time biased IN OUR FAVOUR.

  ./surplus_decomp.py --self-test
  ./surplus_decomp.py
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
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
# ON_ERROR_STOP: without it psql EXITS 0 on a failed query and hands back an EMPTY CSV, so a broken
# query becomes a clean "0 signals" null result instead of a crash. That already happened once.
# max_parallel_workers_per_gather=0: this DB serves the LIVE bot; a parallel seq-scan over 57M
# harvest_fills rows caused a production outage on 2026-07-14.
GUARD = ("SET work_mem='64MB'; SET statement_timeout='600s'; "
         "SET max_parallel_workers_per_gather=0; ")
BATCH = 200
SEED = 20260714
LAG = 5

# Theta by niche. The predecessor's typed guess vs the repo's VERIFIED figures.
THETA_PREDECESSOR = {"tennis": .03, "soccer": .03, "mlb": .03, "nba": .03, "nhl": .03,
                     "ufc": .03, "esports": .03, "politics": .04, "crypto": .07}
THETA_VERIFIED = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05,
                  "ufc": .05, "esports": .05, "politics": .04, "crypto": .07,
                  "weather": .05, "other": .05}
THETA_US_TAKER = 0.06          # confirmed on all 2,999 US markets (project-polymarket-us-economics)
DEFAULT_THETA = 0.05

BANDL = ["0-20c", "20-40c", "40-60c", "60-80c", "80-100c"]


def theta(niche, table):
    if table == "us":
        return THETA_US_TAKER
    t = THETA_PREDECESSOR if table == "predecessor" else THETA_VERIFIED
    return t.get(niche, DEFAULT_THETA)


def fee(p, niche, table):
    """Polymarket taker fee: shares * theta * p * (1-p). Takers only; makers pay 0."""
    return theta(niche, table) * p * (1.0 - p)


def band(p):
    return min(int(p * 5), 4)


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED (ON_ERROR_STOP working as intended):\n" + o.stderr[:1200])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def boot_decomp(pairs, n_boot=4000, seed=SEED):
    """pairs = [(market, d_net, d_won, d_p, d_fee)] -- each already differenced INSIDE the market,
    so a shared resolution shock cancels. Bootstraps MARKETS."""
    if len(pairs) < 20:
        return None
    a = np.array([[p[1], p[2], p[3], p[4]] for p in pairs], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), (n_boot, len(a)))
    bs = a[idx].mean(1)                                    # (n_boot, 4)
    net = bs[:, 0]
    return {
        "surplus":  float(a[:, 0].mean()), "lo": float(np.percentile(net, 2.5)),
        "hi": float(np.percentile(net, 97.5)), "p": float((net <= 0).mean()),
        "d_won":    float(a[:, 1].mean()),
        "d_won_lo": float(np.percentile(bs[:, 1], 2.5)),
        "d_won_hi": float(np.percentile(bs[:, 1], 97.5)),
        "d_won_p":  float((bs[:, 1] <= 0).mean()),
        "d_price":  float(a[:, 2].mean()),
        "d_price_lo": float(np.percentile(bs[:, 2], 2.5)),
        "d_price_hi": float(np.percentile(bs[:, 2], 97.5)),
        "d_fee":    float(a[:, 3].mean()),
        "n_markets": len(a),
    }


def bh(pvals, q=0.05):
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    keep, m = set(), len(pvals)
    for rank, i in enumerate(idx, 1):
        if pvals[i] <= q * rank / m:
            keep = set(idx[:rank])
    return keep


# ---------------------------------------------------------------------------- self-test
def self_test():
    assert band(.05) == 0 and band(.85) == 4 and band(1.0) == 4
    assert abs(fee(.9, "mlb", "verified") - .05 * .9 * .1) < 1e-12
    assert abs(fee(.9, "mlb", "predecessor") - .03 * .9 * .1) < 1e-12
    assert abs(fee(.9, "mlb", "us") - .06 * .9 * .1) < 1e-12
    # the fee the predecessor charged is 40% light vs the verified rate
    assert fee(.88, "soccer", "verified") > fee(.88, "soccer", "predecessor") * 1.6

    # PURE SKILL: copy wins more at the SAME price -> surplus must land in d_won
    r = boot_decomp([(f"m{i}", .04, .04, .0, .0) for i in range(200)])
    assert r["surplus"] > .03 and r["d_won"] > .03 and abs(r["d_price"]) < 1e-9
    assert r["lo"] > 0

    # PURE ARTIFACT: identical win-rate, copy just enters 4c cheaper inside the band.
    # The surplus is IDENTICAL (+4c) and the naive test cannot tell it from skill --
    # only the decomposition can. THIS IS THE ENTIRE POINT OF THIS SCRIPT.
    r2 = boot_decomp([(f"m{i}", .04, .0, -.04, .0) for i in range(200)])
    assert abs(r2["surplus"] - .04) < 1e-9, "artifact produces the same headline surplus"
    assert abs(r2["d_won"]) < 1e-9, "...but ZERO win-rate edge"
    assert r2["d_price"] < -.03, "...and it is ALL entry-price composition"

    assert 0 not in bh([0.04] + [0.5] * 19), "BH must reject a scan-manufactured winner"
    print("self-test OK  (decomposition separates skill from price composition)")
    return 0


# ---------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--roster", default="reports/niche/global_profit_floor20.json")
    ap.add_argument("--ranker", default="eb_shrunk")
    ap.add_argument("--fee-table", default="verified",
                    choices=["predecessor", "verified", "us"])
    ap.add_argument("--out", default="reports/niche/surplus_decomp.json")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    R = [r for r in json.load(open(a.roster)) if r["ranker"] == a.ranker][0]["roster"]
    wallets = [w["wallet"] for w in R]
    rosterset = set(wallets)
    print(f"roster: {len(wallets)} wallets ({a.ranker})   fee table: {a.fee_table.upper()}\n")

    # window B (out-of-sample): markets whose LAST harvest ts is above the median
    wfilt = ("AND h.condition_id IN (SELECT condition_id FROM ("
             "  SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) x "
             "  WHERE x.mts > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) "
             "                 FROM (SELECT condition_id, MAX(ts) mts FROM harvest_wm "
             "                       GROUP BY 1) y))")
    sigs = []
    for i in range(0, len(wallets), 100):
        sigs += psql(f"""
          WITH res AS (SELECT condition_id, outcome_index, BOOL_OR(outcome_won) won
                       FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
          ok AS (SELECT condition_id, niche, n_trades FROM harvest_markets WHERE NOT truncated)
          SELECT h.condition_id, h.outcome_index, h.wallet,
                 EXTRACT(EPOCH FROM h.ts) t, h.price p, (r.won::int)::float8 won,
                 ok.niche, ok.n_trades
          FROM harvest_fills h
          JOIN ok ON ok.condition_id=h.condition_id
          JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
          WHERE h.side='BUY' AND h.is_maker=false
            AND h.wallet IN ({q_lit(wallets[i:i+100])}) {wfilt};""")
    mkts = sorted({s["condition_id"] for s in sigs})
    print(f"{len(sigs):,} roster signals / {len(mkts):,} markets (window B)")

    takers, wonmap, niche_of, depth_of = defaultdict(list), {}, {}, {}
    for i in range(0, len(mkts), BATCH):
        ch = mkts[i:i + BATCH]
        for r in psql(f"""
              SELECT h.condition_id, h.outcome_index, h.wallet,
                     EXTRACT(EPOCH FROM h.ts) t, h.price p, m.niche, m.n_trades
              FROM harvest_fills h JOIN harvest_markets m USING (condition_id)
              WHERE h.side='BUY' AND h.is_maker=false
                AND h.condition_id IN ({q_lit(ch)});"""):
            takers[(r["condition_id"], r["outcome_index"])].append(
                (float(r["t"]), float(r["p"]), r["wallet"]))
            niche_of[r["condition_id"]] = r["niche"]
            depth_of[r["condition_id"]] = int(r["n_trades"])
        for r in psql(f"""
              SELECT condition_id, outcome_index, BOOL_OR(outcome_won)::int won
              FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL
                AND condition_id IN ({q_lit(ch)}) GROUP BY 1,2;"""):
            wonmap[(r["condition_id"], r["outcome_index"])] = float(r["won"])
        sys.stdout.write(f"\r  tape {min(i+BATCH, len(mkts)):,}/{len(mkts):,}")
        sys.stdout.flush()
    for k in takers:
        takers[k].sort(key=lambda x: x[0])
    print(f"\n  {sum(len(v) for v in takers.values()):,} taker prints, "
          f"{len(wonmap):,} resolved outcomes\n")

    FT = a.fee_table

    # ---- POLICY A: copy at the price we can really get (first non-self taker print at t0+LAG)
    copy_rows = []
    for s in sigs:
        k = (s["condition_id"], s["outcome_index"])
        t0, w0 = float(s["t"]), s["wallet"]
        px = next((p for (t, p, w) in takers.get(k, []) if t >= t0 + LAG and w != w0), None)
        if px is None:
            continue
        cid, n = s["condition_id"], s["niche"]
        copy_rows.append({"cid": cid, "oi": s["outcome_index"], "niche": n, "band": band(px),
                          "depth": depth_of[cid], "won": float(s["won"]), "p": px,
                          "fee": fee(px, n, FT),
                          "net": float(s["won"]) - px - fee(px, n, FT)})

    # ---- POLICY B: blind -- every NON-roster taker print in the same markets
    blind_rows = []
    for (cid, oi), prints in takers.items():
        w = wonmap.get((cid, oi))
        if w is None:
            continue
        n = niche_of[cid]
        for (t, p, wal) in prints:
            if wal in rosterset:
                continue
            blind_rows.append({"cid": cid, "oi": oi, "niche": n, "band": band(p),
                               "depth": depth_of[cid], "won": w, "p": p, "fee": fee(p, n, FT),
                               "net": w - p - fee(p, n, FT)})
    print(f"policy A (copy):  {len(copy_rows):,} entries")
    print(f"policy B (blind): {len(blind_rows):,} entries\n")

    # =================================================================== TEST 1: DECOMPOSITION
    def cell_decomp(sel):
        ca, cb = defaultdict(list), defaultdict(list)
        for r in copy_rows:
            if sel(r):
                ca[r["cid"]].append(r)
        for r in blind_rows:
            if sel(r):
                cb[r["cid"]].append(r)
        pairs = []
        for m in ca:
            if m not in cb:
                continue
            A, B = ca[m], cb[m]
            mean = lambda X, k: float(np.mean([x[k] for x in X]))
            pairs.append((m,
                          mean(A, "net") - mean(B, "net"),
                          mean(A, "won") - mean(B, "won"),
                          mean(A, "p") - mean(B, "p"),
                          mean(A, "fee") - mean(B, "fee")))
        return boot_decomp(pairs)

    SPORTS = ("soccer", "mlb", "tennis", "esports", "nba", "nhl", "ufc")
    cells = [("ALL", lambda r: True)]
    cells += [(f"band {BANDL[b]}", lambda r, b=b: r["band"] == b) for b in range(5)]
    cells += [("FAV 80-100c x SPORTS", lambda r: r["band"] == 4 and r["niche"] in SPORTS)]
    cells += [("FAV 80-100c x NON-sports", lambda r: r["band"] == 4 and r["niche"] not in SPORTS)]
    cells += [(f"FAV x {n}", lambda r, n=n: r["band"] == 4 and r["niche"] == n)
              for n in ["weather", "crypto", "other", "soccer", "esports", "tennis", "mlb"]]
    cells += [("FAV x mid-depth 200-1k",
               lambda r: r["band"] == 4 and 200 <= r["depth"] < 1000)]

    live = [(nm, cell_decomp(sel)) for nm, sel in cells]
    live = [(nm, r) for nm, r in live if r]
    keep = bh([r["p"] for _, r in live])

    W = 100
    print("=" * W)
    print(f"TEST 1 -- SURPLUS DECOMPOSED     surplus = D(won) - D(price) - D(fee)   [fee={FT}]")
    print("=" * W)
    print(f"{'cell':>26s} {'SURPLUS':>9s} {'95% CI':>18s} {'p':>6s} | "
          f"{'D(won)':>8s} {'D(won) CI':>18s} | {'D(price)':>9s} {'mkts':>6s} BH")
    print("-" * W)
    out = {"meta": {"fee_table": FT, "lag": LAG, "roster": a.ranker}, "decomp": {}}
    for i, (nm, r) in enumerate(live):
        print(f"{nm:>26s} {r['surplus']:>+9.4f} [{r['lo']:+.4f},{r['hi']:+.4f}] {r['p']:>6.3f} | "
              f"{r['d_won']:>+8.4f} [{r['d_won_lo']:+.4f},{r['d_won_hi']:+.4f}] | "
              f"{r['d_price']:>+9.4f} {r['n_markets']:>6,} {'PASS' if i in keep else ''}")
        out["decomp"][nm] = r
    print("\n  D(won)   = does the roster PICK WINNERS at the same price?  <- the only thing that is SKILL")
    print("  D(price) = does the roster merely ENTER CHEAPER inside a 20c band?  <- pure ARTIFACT")
    print("  If SURPLUS is large but D(won) ~ 0, the edge is composition and there is nothing here.\n")

    # =================================================================== TEST 2: PRICE CALIPER
    # Same market, SAME OUTCOME, blind entry within +/-eps of the copy leg's ACTUAL entry price.
    # With no price difference left, any surviving surplus MUST be win-rate selection.
    bl_by_key = defaultdict(list)
    for r in blind_rows:
        bl_by_key[(r["cid"], r["oi"])].append(r)

    print("=" * W)
    print("TEST 2 -- PRICE-CALIPER CONTROL   (same market, same outcome, |p_blind - p_copy| <= eps)")
    print("=" * W)
    print(f"{'cell':>26s} {'eps':>6s} {'SURPLUS':>9s} {'95% CI':>18s} {'p':>6s} | "
          f"{'D(won)':>8s} | {'D(price)':>9s} {'mkts':>6s}")
    print("-" * W)
    out["caliper"] = {}
    for nm, sel in [("band 80-100c", lambda r: r["band"] == 4),
                    ("FAV 80-100c x SPORTS",
                     lambda r: r["band"] == 4 and r["niche"] in SPORTS),
                    ("band 60-80c", lambda r: r["band"] == 3),
                    ("ALL", lambda r: True)]:
        for eps in (0.005, 0.01, 0.02):
            per_mkt = defaultdict(lambda: [[], []])
            for r in copy_rows:
                if not sel(r):
                    continue
                cand = [b for b in bl_by_key.get((r["cid"], r["oi"]), [])
                        if abs(b["p"] - r["p"]) <= eps]
                if not cand:
                    continue
                per_mkt[r["cid"]][0].append(r)
                per_mkt[r["cid"]][1].extend(cand)
            pairs = []
            for m, (A, B) in per_mkt.items():
                if not A or not B:
                    continue
                mean = lambda X, k: float(np.mean([x[k] for x in X]))
                pairs.append((m,
                              mean(A, "net") - mean(B, "net"),
                              mean(A, "won") - mean(B, "won"),
                              mean(A, "p") - mean(B, "p"),
                              mean(A, "fee") - mean(B, "fee")))
            r = boot_decomp(pairs)
            if not r:
                print(f"{nm:>26s} {eps:>6.3f}  -- too few paired markets --")
                continue
            print(f"{nm:>26s} {eps:>6.3f} {r['surplus']:>+9.4f} "
                  f"[{r['lo']:+.4f},{r['hi']:+.4f}] {r['p']:>6.3f} | "
                  f"{r['d_won']:>+8.4f} | {r['d_price']:>+9.4f} {r['n_markets']:>6,}")
            out["caliper"][f"{nm} @{eps}"] = r
    print("\n  A surplus that survives a 1c caliper CANNOT be price composition -- there is no price")
    print("  difference left for it to hide in. A surplus that VANISHES here never was an edge.\n")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
