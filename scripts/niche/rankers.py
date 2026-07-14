#!/usr/bin/env python3
"""
DOES *ANYTHING* RANK TRADERS WITHIN A NICHE? -- an out-of-sample ranker panel.

roster.py answered one question: ranking a niche's population by PAST COPYABLE SURPLUS
does not transfer out of sample (rank rho ~ +0.02..+0.10). That refutes one ranker. It
does not prove that no ranker works. This script tests a PANEL, honestly:

    fit every ranker in window A  ->  evaluate realized copyable surplus in window B

Rankers tested (all computable from the harvested tape alone):
  past_surplus     the H1 ranker (control -- must reproduce its failure)
  raw_advantage    absolute edge, no baseline subtraction
  CLV              *** the headline candidate ***
  win_rate         hit rate on resolved BUYs
  avg_size         conviction / bankroll proxy
  entry_earliness  how early in a market's life they enter
  n_markets        activity (a pure-volume control -- the leaderboard's own sort)
  concentration    how much of the wallet's TOTAL activity lives in THIS niche
                   (the literal "is this trader a SPECIALIST of this space" hypothesis --
                    a whale with 20 weather markets out of 500 is not a weather specialist)

WHY CLV IS THE ONE THAT MATTERS. This project has already found that past-PnL ranking is
refuted five ways, while CLV is "the only forward-shaped lead" (persistence rho=+0.27, but
INDETERMINATE-BY-POWER: only ~2 wallets cleared 50 events, ETA to a verdict ~3-6 months of
forward accrual). That ETA assumed we could only accrue CLV going forward, on the ~3k
wallets we could poll. The market-side harvest changes the arithmetic: the closing line is
computable FROM THE TAPE ITSELF, retrospectively, for EVERY trader in the population. The
3-6 month wait may simply collapse.

CLV = closing_line(market, outcome) - entry_price,  on BUYs.
    closing_line = mean price of fills in the LAST 20% of a market's fill-life, taken from
    OTHER traders only (self-exclusion -- otherwise a wallet that trades late defines its
    own benchmark and scores itself). Outcome-independent, so it is far lower-variance than
    realized PnL, which is exactly why it can persist where PnL cannot.

Pre-registered success criterion for a ranker (fixed before results):
  (1) top-50 by ranker-in-A has window-B copyable surplus with a MARKET-CLUSTERED 95% CI
      strictly above 0, AND
  (2) spearman rho(ranker_A, realized_surplus_B) > 0 with a bootstrap CI excluding 0.
  BH-FDR q=0.10 across the whole (ranker x niche) family -- this is a panel, and a panel
  that is not corrected will always crown someone.
"""
import argparse
import csv
import io
import math
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

TAX = 0.013
N_FLOOR_SPLIT = 8      # min markets in EACH window
TOP_N = 50
FDR_Q = 0.10
SEED = 20260714
CONC_MIN = 0.60        # "specialist of this space" threshold for the concentration arm


def psql(sql):
    out = subprocess.run(PG, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


# Per (wallet, market): entry stats + the self-excluded closing line.
# Everything is computed on COMPLETE-tape markets only (truncation drops the earliest
# entrants, which would poison both CLV and entry-earliness).
SQL = r"""
WITH res AS (
  SELECT condition_id, outcome_index, BOOL_OR(outcome_won) AS won
  FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2
),
ok AS (SELECT condition_id, niche FROM harvest_markets WHERE NOT truncated),
f AS (
  SELECT h.wallet, h.niche, h.condition_id, h.outcome_index, h.price, h.size_usd,
         h.is_maker, EXTRACT(EPOCH FROM h.ts) AS ts, (r.won::int)::float8 AS won,
         width_bucket(h.price, 0.0, 1.0, 20) AS band
  FROM harvest_fills h
  JOIN ok USING (condition_id)
  JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
  WHERE h.side='BUY'
),
life AS (   -- each market's fill-life, precomputed once into harvest_life:
            -- recomputing it inline rescanned all ~45M fills on every query
  SELECT condition_id, t0, t1 FROM harvest_life
),
late AS (   -- the CLOSING LINE: mean price over the last 20% of the market's life,
            -- per (market, outcome). Self-exclusion is applied later, in Python.
  SELECT f.condition_id, f.outcome_index,
         SUM(f.price) close_sum, COUNT(*) close_n
  FROM f JOIN life l USING (condition_id)
  WHERE l.t1 > l.t0 AND f.ts >= l.t0 + 0.8*(l.t1-l.t0)
  GROUP BY 1,2
),
selflate AS ( -- each wallet's OWN contribution to that window, so we can subtract it
  SELECT f.wallet, f.condition_id, f.outcome_index,
         SUM(f.price) s_sum, COUNT(*) s_n
  FROM f JOIN life l USING (condition_id)
  WHERE l.t1 > l.t0 AND f.ts >= l.t0 + 0.8*(l.t1-l.t0)
  GROUP BY 1,2,3
),
blind AS (SELECT niche, band, AVG(won - price) be FROM f GROUP BY 1,2)
SELECT f.wallet, f.niche, f.condition_id,
       AVG(f.won - f.price - b.be)                       AS surplus,
       AVG(f.won - f.price)                              AS raw_adv,
       AVG(f.won)                                        AS win_rate,
       AVG(f.price)                                      AS price,
       SUM(f.size_usd)                                   AS usd,
       AVG((f.is_maker)::int::float8)                    AS maker_frac,
       COUNT(DISTINCT f.outcome_index)                   AS n_sides,
       MAX(f.ts)                                         AS ts,
       -- how early in the market's life did they enter? 1 = at the very open
       AVG(CASE WHEN l.t1 > l.t0 THEN 1.0 - (f.ts - l.t0)/(l.t1 - l.t0) ELSE 0.5 END)
                                                         AS earliness,
       MAX(COALESCE(lt.close_sum,0))                     AS close_sum,
       MAX(COALESCE(lt.close_n,0))                       AS close_n,
       MAX(COALESCE(sl.s_sum,0))                         AS self_sum,
       MAX(COALESCE(sl.s_n,0))                           AS self_n
FROM f
JOIN blind b USING (niche, band)
JOIN life l USING (condition_id)
LEFT JOIN late lt ON lt.condition_id=f.condition_id AND lt.outcome_index=f.outcome_index
LEFT JOIN selflate sl ON sl.wallet=f.wallet AND sl.condition_id=f.condition_id
                     AND sl.outcome_index=f.outcome_index
GROUP BY f.wallet, f.niche, f.condition_id;
"""


def load(niche=None):
    sql = SQL if not niche else SQL.replace(
        "WHERE h.side='BUY'", f"WHERE h.side='BUY' AND h.niche = '{niche}'")
    rows = psql(sql)
    recs = defaultdict(list)
    for r in rows:
        try:
            cs, cn = float(r["close_sum"]), float(r["close_n"])
            ss, sn = float(r["self_sum"]), float(r["self_n"])
            # SELF-EXCLUDED closing line: remove the wallet's own late fills, else a
            # late-trading wallet benchmarks itself against itself and scores ~0 by
            # construction (and a whale that IS the late market looks clairvoyant).
            n_oth = cn - sn
            close = (cs - ss) / n_oth if n_oth > 0 else None
            price = float(r["price"])
            recs[(r["wallet"], r["niche"])].append({
                "mkt": r["condition_id"],
                "surplus": float(r["surplus"]),
                "raw_adv": float(r["raw_adv"]),
                "win_rate": float(r["win_rate"]),
                "price": price,
                "usd": float(r["usd"]),
                "maker_frac": float(r["maker_frac"] or 0),
                "n_sides": int(r["n_sides"]),
                "ts": float(r["ts"]),
                "earliness": float(r["earliness"]),
                "clv": (close - price) if close is not None else None,
            })
        except (ValueError, TypeError):
            continue
    return recs


def is_mm(mk):
    maker = statistics.fmean([m["maker_frac"] for m in mk])
    two = sum(1 for m in mk if m["n_sides"] >= 2) / len(mk)
    return maker >= 0.80 or (two >= 0.50 and maker >= 0.5)


def spearman_ci(x, y, n_boot=2000, seed=SEED):
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = x.size
    if n < 10:
        return float("nan"), float("nan"), float("nan")
    def rho(a, b):
        ra = np.argsort(np.argsort(a)).astype(float)
        rb = np.argsort(np.argsort(b)).astype(float)
        ra -= ra.mean(); rb -= rb.mean()
        d = math.sqrt((ra**2).sum() * (rb**2).sum())
        return float((ra*rb).sum()/d) if d else float("nan")
    r0 = rho(x, y)
    idx = rng.integers(0, n, (n_boot, n))
    bs = np.array([rho(x[i], y[i]) for i in idx])
    return r0, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def cluster_boot(recs, n_boot=2000, seed=SEED):
    """CI clustered on the MARKET -- wallets share markets, so records are NOT independent."""
    if not recs:
        return 0.0, 0.0, 0.0, 0
    by = defaultdict(list)
    for m, v in recs:
        by[m].append(v)
    keys = list(by)
    sums = np.array([sum(by[k]) for k in keys], float)
    lens = np.array([len(by[k]) for k in keys], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), (n_boot, len(keys)))
    means = sums[idx].sum(1) / np.maximum(lens[idx].sum(1), 1)
    obs = sums.sum() / lens.sum()
    return (float(obs), float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)), len(keys))


RANKERS = {
    "past_surplus":    lambda A, c: statistics.fmean([m["surplus"] for m in A]),
    "raw_advantage":   lambda A, c: statistics.fmean([m["raw_adv"] for m in A]),
    "CLV":             lambda A, c: (statistics.fmean([m["clv"] for m in A if m["clv"] is not None])
                                     if any(m["clv"] is not None for m in A) else None),
    "win_rate":        lambda A, c: statistics.fmean([m["win_rate"] for m in A]),
    "avg_size":        lambda A, c: statistics.fmean([m["usd"] for m in A]),
    "entry_earliness": lambda A, c: statistics.fmean([m["earliness"] for m in A]),
    "n_markets":       lambda A, c: float(len(A)),
    "concentration":   lambda A, c: c,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/niche")
    ap.add_argument("--niche", default=None)
    ap.add_argument("--conc-arm", action="store_true",
                    help="restrict to niche SPECIALISTS (concentration >= 0.60) and re-test")
    a = ap.parse_args()

    recs = load(a.niche)
    # concentration = share of the wallet's TOTAL harvested activity that lives in a niche.
    # The denominator MUST come from the whole tape, not from the loaded slice -- with
    # per-niche loading, deriving it from `recs` would make concentration identically 1.0
    # for every wallet and silently turn the ranker into a constant.
    tot = defaultdict(int)
    for r in psql("""SELECT wallet, COUNT(DISTINCT condition_id) n
                     FROM harvest_fills GROUP BY wallet;"""):
        tot[r["wallet"]] = int(r["n"])

    niches = sorted({nz for (_, nz) in recs})
    results = []
    for nz in niches:
        mkt_ts = {}
        for (w, x), mk in recs.items():
            if x != nz:
                continue
            for m in mk:
                mkt_ts[m["mkt"]] = max(mkt_ts.get(m["mkt"], 0.0), m["ts"])
        if not mkt_ts:
            continue
        cut = sorted(mkt_ts.values())[len(mkt_ts) // 2]
        win_A = {k for k, v in mkt_ts.items() if v <= cut}   # disjoint market sets

        pool = {}
        for (w, x), mk in recs.items():
            if x != nz or is_mm(mk):
                continue
            conc = len(mk) / max(tot[w], 1)
            if a.conc_arm and conc < CONC_MIN:
                continue
            A = [m for m in mk if m["mkt"] in win_A]
            B = [m for m in mk if m["mkt"] not in win_A]
            if len(A) >= N_FLOOR_SPLIT and len(B) >= N_FLOOR_SPLIT:
                pool[w] = (A, B, conc)
        if len(pool) < 30:
            print(f"\n{nz}: only {len(pool)} testable wallets -- UNDERPOWERED, skipped")
            continue

        arm = "SPECIALISTS (conc>=0.60)" if a.conc_arm else "ALL gate-eligible"
        print(f"\n{'='*78}\nNICHE: {nz}   [{arm}]   testable wallets = {len(pool)}")
        print(f"{'ranker':17s} {'rho(A,B)':>18s} {'top50 B-surplus':>17s} "
              f"{'95% CI (mkt-clustered)':>26s}  verdict")
        print("-" * 78)

        for name, fn in RANKERS.items():
            scored = []
            for w, (A, B, conc) in pool.items():
                v = fn(A, conc)
                if v is None:
                    continue
                scored.append((w, v))
            if len(scored) < 30:
                continue
            b_surp = {w: statistics.fmean([m["surplus"] - TAX for m in pool[w][1]])
                      for w, _ in scored}
            rho, rlo, rhi = spearman_ci([v for _, v in scored],
                                        [b_surp[w] for w, _ in scored])
            top = [w for w, _ in sorted(scored, key=lambda t: t[1], reverse=True)[:TOP_N]]
            brecs = [(m["mkt"], m["surplus"] - TAX) for w in top for m in pool[w][1]]
            obs, lo, hi, nclu = cluster_boot(brecs)
            works = lo > 0 and rlo > 0
            results.append({"niche": nz, "ranker": name, "arm": arm, "rho": rho,
                            "rho_lo": rlo, "rho_hi": rhi, "b_surplus": obs,
                            "b_lo": lo, "b_hi": hi, "n_markets": nclu,
                            "n_wallets": len(scored), "works": works})
            print(f"{name:17s} {rho:+.3f} [{rlo:+.2f},{rhi:+.2f}] {obs:+16.4f} "
                  f"  [{lo:+.4f},{hi:+.4f}]  {'*** WORKS ***' if works else 'no'}")

    os.makedirs(a.out, exist_ok=True)
    tag = "specialists" if a.conc_arm else "all"
    with open(os.path.join(a.out, f"rankers_{tag}.json"), "w") as f:
        json.dump(results, f, indent=2)

    winners = [r for r in results if r["works"]]
    print(f"\n{'='*78}")
    print(f"PANEL RESULT: {len(winners)} of {len(results)} (ranker x niche) cells clear "
          f"BOTH pre-registered bars")
    if winners:
        print("  (a panel this wide WILL crown someone by chance -- BH-FDR applied next)")
        for w in winners:
            print(f"   {w['niche']:10s} {w['ranker']:17s} rho={w['rho']:+.3f} "
                  f"B={w['b_surplus']:+.4f} [{w['b_lo']:+.4f},{w['b_hi']:+.4f}]")
    else:
        print("  NOTHING ranks traders within a niche out-of-sample.")
    print(f"wrote {a.out}/rankers_{tag}.json")


if __name__ == "__main__":
    main()
