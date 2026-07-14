#!/usr/bin/env python3
"""
MOST PROFITABLE + CONSISTENTLY PROFITABLE -- globally, across the whole harvested population.

Different cut from the niche run, and better powered. Within a niche only 214-1,019 wallets
had >=50 markets; GLOBALLY 17,734 do. Since the attenuation check showed rank correlation
RISES with per-wallet N (rho +0.19 at N>=50), the global pool is where a real signal has the
best chance of showing itself. This is the fairest test the data can support.

"Most profitable" and "consistently profitable" are DIFFERENT rankers, and the difference is
the point -- a raw-profit sort is dominated by wallets with a few huge lucky wins, which is
precisely how a leaderboard manufactures phantom skill. So we test both, plus the estimators
that combine them:

    total_pnl_usd     the leaderboard's own metric (control -- should fail)
    mean_raw_adv      average absolute edge per market
    mean_surplus      edge over the blind price-band baseline (band-confound removed)
    t_stat            mean / standard error   <- "profitable AND consistent", the headline
    sharpe            mean / sd
    sign_consistency  fraction of markets with positive surplus
    eb_shrunk         James-Stein shrinkage toward the pool mean (the principled way to
                      stop small-N wallets from topping the table)
    both_halves       profitable in BOTH halves of window A (a pure consistency screen)

*** THE LEAKAGE TRAP, AVOIDED. *** "Consistently profitable" must be measured in window A
ONLY. Selecting wallets that were profitable in BOTH window A and window B, and then
reporting their window-B returns, is circular -- it will look spectacular and mean nothing.
Every ranker here is fit on A and paid on B, which are DISJOINT MARKET SETS.

Bankability: if we copy them, our P&L per $1 is their raw advantage MINUS the follower tax
(>=1.3c, since the price has already moved by the time we can act) MINUS the ~3% capture cost
(fees+slippage). So the bar is  mean_raw_adv_B > 0.043.  Beating zero is not enough.

CIs are bootstrapped CLUSTERED ON THE MARKET: many wallets share a market, and one
resolution moves them all together, so treating (wallet,market) rows as independent
understates the error bar and fakes significance.
"""
import argparse
import csv
import io
import json
import math
import os
import statistics
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

TAX = 0.013           # follower tax -- the price has already moved when we can act
CAPTURE = 0.03        # fees + slippage
BAR = TAX + CAPTURE   # 4.3%: what a COPYABLE edge must clear to be worth money
N_FLOOR = 20
TOP_K = 100
SEED = 20260714


def psql(sql):
    out = subprocess.run(PG, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


# harvest_wm is the per-(wallet, market) table, materialised ONCE (5.3M rows). Recomputing
# it inline rescanned all 57M fills on every query -- that is what stalled the per-niche
# crypto run. The MARKET is the unit of inference throughout, never the fill.
#
# Window A/B are DISJOINT MARKET SETS, split at the global median market time. A1/A2 are the
# two halves of window A, used for the consistency screen -- consistency must be measured
# inside A, never against B, or the test is circular.
BASE = r"""
WITH mk AS (SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1),
q AS (SELECT PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY mts) c50,
             PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY mts) c25 FROM mk),
tagged AS (
  SELECT w.*, (mk.mts <= (SELECT c50 FROM q)) AS in_a,
              (mk.mts <= (SELECT c25 FROM q)) AS in_a1
  FROM harvest_wm w JOIN mk USING (condition_id)
)
"""

STATS_SQL = BASE + r"""
SELECT wallet,
  COUNT(*) FILTER (WHERE in_a)                                  AS n_a,
  COUNT(*) FILTER (WHERE NOT in_a)                              AS n_b,
  AVG(surplus)  FILTER (WHERE in_a)                             AS a_surplus,
  STDDEV(surplus) FILTER (WHERE in_a)                           AS a_sd,
  AVG(raw_adv)  FILTER (WHERE in_a)                             AS a_raw,
  SUM(pnl_usd)  FILTER (WHERE in_a)                             AS a_pnl,
  SUM(usd)      FILTER (WHERE in_a)                             AS a_usd,
  AVG((surplus > 0)::int::float8) FILTER (WHERE in_a)           AS a_signcons,
  AVG(surplus)  FILTER (WHERE in_a AND in_a1)                   AS a_h1,
  AVG(surplus)  FILTER (WHERE in_a AND NOT in_a1)               AS a_h2,
  AVG(maker_frac)                                               AS maker_frac,
  AVG((n_sides >= 2)::int::float8)                              AS two_sided
FROM tagged
GROUP BY wallet
HAVING COUNT(*) FILTER (WHERE in_a) >= {floor}
   AND COUNT(*) FILTER (WHERE NOT in_a) >= {bfloor};
"""

# Pass 2: per-market window-B rows, but ONLY for the shortlisted wallets (for the
# market-clustered bootstrap). Tiny.
B_ROWS_SQL = BASE + r"""
SELECT wallet, condition_id, surplus, raw_adv, usd
FROM tagged WHERE NOT in_a AND wallet IN ({wallets});
"""


def cluster_boot(recs, n_boot=4000, seed=SEED):
    """recs = [(market, value)]. Resample whole MARKETS, not rows."""
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
    return (float(sums.sum() / lens.sum()),
            float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)), len(keys))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=int, default=N_FLOOR,
                    help="min markets in window A (attenuation says quality is only "
                         "reliably rankable at high N -- try 20, then 50, then 100)")
    ap.add_argument("--top", type=int, default=TOP_K)
    ap.add_argument("--b-floor", type=int, default=8,
                    help="min markets in window B. SURVIVORSHIP: requiring many B markets "
                         "silently DROPS wallets that blew up early in B and quit, which "
                         "inflates the measured out-of-sample edge. Set to 1 to keep them.")
    ap.add_argument("--out", default="reports/niche")
    a = ap.parse_args()

    rows = psql(STATS_SQL.format(floor=a.floor, bfloor=a.b_floor))
    W = []
    for r in rows:
        try:
            n_a, n_b = int(r["n_a"]), int(r["n_b"])
            sd = float(r["a_sd"] or 0) or 1e-9
            mean = float(r["a_surplus"])
            maker = float(r["maker_frac"] or 0)
            two = float(r["two_sided"] or 0)
            # uncopyable profit: a maker earns the spread WE would have to pay
            if maker >= 0.80 or (two >= 0.50 and maker >= 0.5):
                continue
            se = sd / math.sqrt(n_a)
            W.append({
                "wallet": r["wallet"], "n_a": n_a, "n_b": n_b,
                "a_surplus": mean, "a_raw": float(r["a_raw"]),
                "a_pnl": float(r["a_pnl"] or 0), "a_usd": float(r["a_usd"] or 0),
                "a_signcons": float(r["a_signcons"] or 0),
                "h1": float(r["a_h1"] or 0), "h2": float(r["a_h2"] or 0),
                "t_stat": mean / se, "sharpe": mean / sd, "maker": maker,
            })
        except (ValueError, TypeError):
            continue
    if len(W) < 100:
        sys.exit(f"only {len(W)} eligible wallets at floor={a.floor} -- underpowered")

    # James-Stein: shrink each wallet toward the pool mean by its own noise. This is the
    # principled fix for "small-N wallets top the table"; it is what a naive sort lacks.
    pool_mu = statistics.fmean([w["a_surplus"] for w in W])
    pool_var = statistics.pvariance([w["a_surplus"] for w in W])
    for w in W:
        se2 = (w["a_surplus"] / w["t_stat"]) ** 2 if w["t_stat"] else pool_var
        shrink = pool_var / (pool_var + se2) if (pool_var + se2) > 0 else 0.0
        w["eb_shrunk"] = pool_mu + shrink * (w["a_surplus"] - pool_mu)
        w["both_halves"] = 1.0 if (w["h1"] > 0 and w["h2"] > 0) else 0.0
        w["roi"] = w["a_pnl"] / w["a_usd"] if w["a_usd"] > 0 else 0.0

    RANKERS = ["a_pnl", "roi", "a_raw", "a_surplus", "t_stat", "sharpe",
               "a_signcons", "eb_shrunk", "both_halves"]
    LABEL = {"a_pnl": "total_pnl_usd (leaderboard's own sort)",
             "roi": "ROI (profit / staked)",
             "a_raw": "mean raw advantage",
             "a_surplus": "mean surplus over blind",
             "t_stat": "t-stat (profitable AND consistent)",
             "sharpe": "sharpe (mean/sd)",
             "a_signcons": "sign-consistency (% markets won)",
             "eb_shrunk": "EB-shrunk mean (James-Stein)",
             "both_halves": "profitable in BOTH halves of A"}

    # shortlist every ranker's top-K, then pull their window-B markets in ONE query
    short = set()
    tops = {}
    for rk in RANKERS:
        t = sorted(W, key=lambda w: w[rk], reverse=True)[:a.top]
        tops[rk] = t
        short.update(w["wallet"] for w in t)
    wl = ",".join("'" + w.replace("'", "''") + "'" for w in short)
    brows = psql(B_ROWS_SQL.format(wallets=wl))
    B = defaultdict(list)
    for r in brows:
        try:
            B[r["wallet"]].append((r["condition_id"], float(r["surplus"]),
                                   float(r["raw_adv"])))
        except (ValueError, TypeError):
            continue

    print(f"\nGLOBAL POOL  |  floor = {a.floor} markets in window A  |  "
          f"{len(W):,} eligible non-MM wallets  |  top-{a.top} each")
    print(f"BAR: a copyable edge must clear tax({TAX:.3f}) + capture({CAPTURE:.3f}) "
          f"= {BAR:+.3f} in window B\n")
    print(f"{'ranker (fit on window A)':38s} {'B raw adv':>10s} "
          f"{'95% CI (mkt-clustered)':>24s} {'B surplus':>10s}  verdict")
    print("-" * 100)

    results = []
    for rk in RANKERS:
        raw = [(m, ra) for w in tops[rk] for (m, s, ra) in B.get(w["wallet"], [])]
        sur = [(m, s) for w in tops[rk] for (m, s, ra) in B.get(w["wallet"], [])]
        r_obs, r_lo, r_hi, nclu = cluster_boot(raw)
        s_obs, s_lo, s_hi, _ = cluster_boot(sur)
        bankable = r_lo > BAR
        beats0 = r_lo > 0
        verdict = ("*** BANKABLE ***" if bankable
                   else "positive but < cost" if beats0 else "no")
        print(f"{LABEL[rk]:38s} {r_obs:+10.4f} [{r_lo:+.4f},{r_hi:+.4f}] "
              f"{s_obs:+10.4f}  {verdict}")
        results.append({"ranker": rk, "label": LABEL[rk], "b_raw": r_obs,
                        "b_raw_ci": [r_lo, r_hi], "b_surplus": s_obs,
                        "n_markets": nclu, "bankable": bankable,
                        "beats_zero": beats0,
                        "roster": [{"wallet": w["wallet"], "n_markets_A": w["n_a"],
                                    "A_pnl_usd": w["a_pnl"], "A_roi": w["roi"],
                                    "A_surplus": w["a_surplus"], "A_tstat": w["t_stat"],
                                    "A_sign_consistency": w["a_signcons"]}
                                   for w in tops[rk][:a.top]]})

    # field baseline: what the WHOLE eligible pool earned in B (is the top-K special at all?)
    allw = [(m, ra) for w in W for (m, s, ra) in B.get(w["wallet"], [])]
    if allw:
        f_obs, f_lo, f_hi, _ = cluster_boot(allw)
        print("-" * 100)
        print(f"{'FIELD (all shortlisted, for reference)':38s} {f_obs:+10.4f} "
              f"[{f_lo:+.4f},{f_hi:+.4f}]")

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, f"global_profit_floor{a.floor}.json"), "w") as f:
        json.dump(results, f, indent=2)
    n_bank = sum(1 for r in results if r["bankable"])
    print(f"\n{n_bank} of {len(results)} rankers produce a roster whose out-of-sample edge "
          f"clears the {BAR:+.3f} cost bar")
    print(f"wrote {a.out}/global_profit_floor{a.floor}.json (full rosters inside)")


if __name__ == "__main__":
    main()
