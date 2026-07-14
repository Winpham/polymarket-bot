#!/usr/bin/env python3
"""
THE ONLY QUESTION THAT MATTERS: does COPYING beat just BUYING THE SAME KIND OF THING BLINDLY?

net_surface.py found the follower's net clears zero in the 80-100c band (+2.99%, LB +0.79%, over
830 markets). That is almost certainly NOT a copy edge. 80-100c is the FAVOURITE band, and the
favourite-longshot bias means buying favourites BLINDLY already pays (~+3% -- it is our champion
arm, and it is where we already trade). A copy strategy that lands +3% in the band where a coin-flip
strategy lands +3% has an edge of ZERO. It has merely rediscovered the bias, wearing a disguise.

So this is the control that decides it. Two policies, same capital, same markets, same band:

    POLICY A (copy):  buy what a roster wallet buys, at the price WE can actually get (t0 + lag)
    POLICY B (blind): buy a random NON-ROSTER taker print in the SAME market and SAME band

    surplus = A - B,   paired PER MARKET, bootstrapped over markets

Pairing per market is what makes it honest: wallets share markets, and a shared resolution moves
copy and blind TOGETHER. Differencing inside the market cancels that common shock, so the CI
measures selection, not luck about which markets resolved YES.

Both legs pay the REAL fee (feeRate(niche)*p*(1-p)); neither pays the phantom 1c slippage, because
both are priced at REAL TAKER PRINTS that really cleared.

Cells are scanned across niche x band x depth, and the p-values are BENJAMINI-HOCHBERG corrected --
scanning ~20 cells at 95% manufactures ~1 winner from noise, and this codebase has been fooled by
exactly that before (see cell-scan: "the champion is singular").

  ./copy_vs_blind.py --self-test
  ./copy_vs_blind.py
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
LAG = 5

REAL_FEE_RATE = {"tennis": 0.03, "soccer": 0.03, "mlb": 0.03, "nba": 0.03, "nhl": 0.03,
                 "ufc": 0.03, "esports": 0.03, "politics": 0.04, "crypto": 0.07}
DEFAULT_FEE_RATE = 0.05


def real_fee(p, niche):
    return REAL_FEE_RATE.get(niche, DEFAULT_FEE_RATE) * p * (1.0 - p)


def band(p):
    return min(int(p * 5), 4)          # 0=0-20c .. 4=80-100c


BANDL = ["0-20c", "20-40c", "40-60c", "60-80c", "80-100c"]


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql failed:\n" + o.stderr[:800])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def paired_boot(pairs, n_boot=4000, seed=SEED):
    """pairs = [(market, copy_net, blind_net)]. Bootstraps MARKETS; the difference is taken
    INSIDE the market first, so a shared resolution cancels."""
    if len(pairs) < 20:
        return None
    m = np.array([p[1] - p[2] for p in pairs], float)
    a = np.array([p[1] for p in pairs], float)
    b = np.array([p[2] for p in pairs], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(m), (n_boot, len(m)))
    d = m[idx].mean(1)
    # one-sided p: how often does the resampled surplus fail to beat 0
    p_val = float((d <= 0).mean())
    return {"copy": float(a.mean()), "blind": float(b.mean()), "surplus": float(m.mean()),
            "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
            "p": p_val, "n_markets": len(m)}


def bh(pvals, q=0.05):
    """Benjamini-Hochberg. Returns the set of indices that survive."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    keep, m = set(), len(pvals)
    for rank, i in enumerate(idx, 1):
        if pvals[i] <= q * rank / m:
            keep = set(idx[:rank])
    return keep


# ------------------------------------------------------------------------------ self-test
def self_test():
    assert band(0.05) == 0 and band(0.85) == 4 and band(1.0) == 4 and band(0.60) == 3
    assert abs(real_fee(0.9, "mlb") - 0.03 * 0.9 * 0.1) < 1e-12

    # a REAL surplus is detected
    r = paired_boot([(f"m{i}", 0.05, 0.01) for i in range(200)])
    assert r["surplus"] > 0.03 and r["lo"] > 0 and r["p"] < 0.01

    # THE CASE THIS SCRIPT EXISTS FOR: copy is +3% but blind is ALSO +3% -> surplus must be ~0
    rng = np.random.default_rng(1)
    pk = [(f"m{i}", 0.03 + rng.normal(0, .2), 0.03 + rng.normal(0, .2)) for i in range(500)]
    r2 = paired_boot(pk)
    assert abs(r2["surplus"]) < 0.02 and r2["lo"] < 0 < r2["hi"], "must NOT certify a fake edge"
    assert r2["p"] > 0.05

    # BH kills a lone 0.04 among 20 nulls (which a naive 95% cut would have crowned)
    ps = [0.04] + [0.5] * 19
    assert 0 not in bh(ps), "BH must reject the scan-manufactured winner"
    assert 0 in bh([0.0001] + [0.5] * 19), "BH must keep a genuinely strong one"
    print("self-test OK")
    return 0


# ------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--roster", default="reports/niche/global_profit_floor20.json")
    ap.add_argument("--ranker", default="eb_shrunk")
    ap.add_argument("--out", default="reports/niche/copy_vs_blind.json")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    R = [r for r in json.load(open(a.roster)) if r["ranker"] == a.ranker][0]["roster"]
    wallets = [w["wallet"] for w in R]
    rosterset = set(wallets)

    wfilt = ("AND h.condition_id IN (SELECT condition_id FROM ("
             "  SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) x "
             "  WHERE x.mts > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) "
             "                 FROM (SELECT condition_id, MAX(ts) mts FROM harvest_wm "
             "                       GROUP BY 1) y))")
    sigs = psql(f"""
      WITH res AS (SELECT condition_id, outcome_index, BOOL_OR(outcome_won) won
                   FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
      ok AS (SELECT condition_id, niche, n_trades FROM harvest_markets WHERE NOT truncated)
      SELECT h.condition_id, h.outcome_index, h.wallet,
             EXTRACT(EPOCH FROM h.ts) t, h.price p, (r.won::int)::float8 won,
             ok.niche, ok.n_trades
      FROM harvest_fills h
      JOIN ok ON ok.condition_id=h.condition_id
      JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
      WHERE h.side='BUY' AND h.is_maker=false AND h.wallet IN ({q_lit(wallets)}) {wfilt};
    """)
    mkts = sorted({s["condition_id"] for s in sigs})
    print(f"{len(sigs):,} roster signals / {len(mkts):,} markets  (window B)\n")

    # the FULL taker tape + the resolution of EVERY outcome in those markets (the blind leg needs
    # the outcomes the roster did NOT buy -- a blind favourite buyer has no idea which side wins)
    takers, wonmap, niche_of, depth_of = defaultdict(list), {}, {}, {}
    for i in range(0, len(mkts), BATCH):
        ch = mkts[i:i + BATCH]
        for r in psql(f"""
              SELECT h.condition_id, h.outcome_index, h.wallet,
                     EXTRACT(EPOCH FROM h.ts) t, h.price p, m.niche, m.n_trades
              FROM harvest_fills h JOIN harvest_markets m USING (condition_id)
              WHERE h.side='BUY' AND h.is_maker=false AND h.condition_id IN ({q_lit(ch)});"""):
            k = (r["condition_id"], r["outcome_index"])
            takers[k].append((float(r["t"]), float(r["p"]), r["wallet"]))
            niche_of[r["condition_id"]] = r["niche"]
            depth_of[r["condition_id"]] = int(r["n_trades"])
        for r in psql(f"""
              SELECT condition_id, outcome_index, BOOL_OR(outcome_won)::int won
              FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL
                AND condition_id IN ({q_lit(ch)}) GROUP BY 1,2;"""):
            wonmap[(r["condition_id"], r["outcome_index"])] = float(r["won"])
        sys.stdout.write(f"\r  {min(i+BATCH, len(mkts)):,}/{len(mkts):,}")
        sys.stdout.flush()
    for k in takers:
        takers[k].sort(key=lambda x: x[0])
    print(f"\n  taker tape {sum(len(v) for v in takers.values()):,} prints, "
          f"{len(wonmap):,} resolved outcomes\n")

    # ---- POLICY A: copy, at the price we can really get (first taker print at/after t0+LAG)
    copy_rows = []
    for s in sigs:
        k = (s["condition_id"], s["outcome_index"])
        t0, w0 = float(s["t"]), s["wallet"]
        px = next((p for (t, p, w) in takers.get(k, []) if t >= t0 + LAG and w != w0), None)
        if px is None:
            continue
        n = s["niche"]
        copy_rows.append({"cid": s["condition_id"], "niche": n, "band": band(px),
                          "depth": depth_of[s["condition_id"]],
                          "net": float(s["won"]) - px - real_fee(px, n)})

    # ---- POLICY B: blind -- EVERY non-roster taker print, same markets. A blind buyer picks a
    #      band, not a side, so we keep every outcome and let the band decide.
    blind_rows = []
    for (cid, oi), prints in takers.items():
        w = wonmap.get((cid, oi))
        if w is None:
            continue
        n = niche_of[cid]
        for (t, p, wal) in prints:
            if wal in rosterset:
                continue
            blind_rows.append({"cid": cid, "niche": n, "band": band(p),
                               "depth": depth_of[cid], "net": w - p - real_fee(p, n)})
    print(f"policy A (copy): {len(copy_rows):,} entries")
    print(f"policy B (blind): {len(blind_rows):,} entries\n")

    # ---- the paired, per-market comparison, cell by cell
    def cell_test(name, sel):
        ca, cb = defaultdict(list), defaultdict(list)
        for r in copy_rows:
            if sel(r):
                ca[r["cid"]].append(r["net"])
        for r in blind_rows:
            if sel(r):
                cb[r["cid"]].append(r["net"])
        pairs = [(m, float(np.mean(ca[m])), float(np.mean(cb[m])))
                 for m in ca if m in cb]
        r = paired_boot(pairs)
        return name, r

    tests = []
    tests.append(cell_test("ALL", lambda r: True))
    for b in range(5):
        tests.append(cell_test(f"band {BANDL[b]}", lambda r, b=b: r["band"] == b))
    for n in ["weather", "crypto", "other", "soccer", "esports", "tennis", "mlb"]:
        tests.append(cell_test(f"niche {n}", lambda r, n=n: r["niche"] == n))
    for lab, lo, hi in [("thin <200", 0, 200), ("mid 200-1k", 200, 1000),
                        ("deep >1k", 1000, 10 ** 9)]:
        tests.append(cell_test(f"depth {lab}", lambda r, lo=lo, hi=hi: lo <= r["depth"] < hi))
    # the one cell that "survived" -- favourites, isolated
    tests.append(cell_test("FAVOURITES 80-100c x sports",
                           lambda r: r["band"] == 4 and r["niche"] in
                           ("soccer", "mlb", "tennis", "esports", "nba", "nhl", "ufc")))

    live = [(n, r) for n, r in tests if r]
    keep = bh([r["p"] for _, r in live])

    print("=" * 96)
    print(f"COPY  vs  BLIND-IN-THE-SAME-BAND     (paired per market, {LAG}s executor lag, real fees)")
    print("=" * 96)
    print(f"{'cell':>30s} {'COPY':>8s} {'BLIND':>8s} {'SURPLUS':>9s} {'95% CI':>20s} "
          f"{'p':>7s} {'mkts':>6s}  BH")
    print("-" * 96)
    out = {}
    for i, (nm, r) in enumerate(live):
        sig = "PASS" if i in keep else ""
        print(f"{nm:>30s} {r['copy']:>+8.4f} {r['blind']:>+8.4f} {r['surplus']:>+9.4f} "
              f"[{r['lo']:+.4f},{r['hi']:+.4f}] {r['p']:>7.3f} {r['n_markets']:>6,}  {sig}")
        out[nm] = r

    print("\n  COPY    = what a follower nets copying the roster (real fee, real follow-on price)")
    print("  BLIND   = what the SAME capital nets buying non-roster prints in the SAME band+market")
    print("  SURPLUS = what the ROSTER SELECTION is actually worth. This is the whole ballgame.")
    print("  BH      = survives Benjamini-Hochberg across every cell scanned.\n")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
