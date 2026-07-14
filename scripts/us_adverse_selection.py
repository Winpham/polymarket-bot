#!/usr/bin/env python3
"""ADVERSE SELECTION ON POLYMARKET US — MEASURED, off the identity tape. READ-ONLY.

THE QUESTION THIS ANSWERS
------------------------
Market-making was KILLED on the international book (2026-07-09, [[project-polymarket-market-making]]):
$0-falsified at a 13x hazard/reward ratio -- a resting quote fills exactly when informed flow runs
it over. We could never SEE that on intl; we inferred it. On US we can measure it directly, because
the venue's live tape publishes `maker_username` on ~48% of prints. So we do not simulate a resting
order and assume its fate: we observe REAL makers who REALLY got filled, and price what happened to
them next.

THE MEASUREMENT
---------------
For every fill with an identified maker, the maker's realized P&L per share if they unwound at the
mid Delta seconds later:

    markout(D) = sign * (mid_{t+D} - fill_price),   sign = +1 if maker BOUGHT, -1 if maker SOLD

Verified empirically before trusting the sign: maker_side=BUY prints sit at the BID 95-96% of the
time and maker_side=SELL at the ASK, regardless of outcomeSide, and trade prices live in the same
frame as the book (~90% inside the prevailing BBO; only ~3% fit the inverted 1-p frame). So there
is no YES/NO inversion to undo here.

It is measured against the MID, never against subsequent TRADE PRICES. Prints alternate between bid
and ask, so a trade-price markout hands the maker the half-spread as fake profit and would make
every maker look good no matter how badly they are picked off. That is the error class behind the
retracted "+4.8% maker-copy". Mids cancel the bounce.

Decomposition (what makes the verdict actionable):
    markout(D) = spread_capture + drift
    spread_capture = sign * (mid_t - fill_price)      what you are PAID to provide liquidity
    drift          = sign * (mid_{t+D} - mid_t)       what informed flow TAKES BACK  <- adverse selection

THE CONTROL (the evidence rule is binding: control + significance + n & dispersion)
----------------------------------------------------------------------------------
A negative markout alone proves nothing -- the market may simply have been drifting, and any quote,
filled or not, would have looked bad. So we run a PLACEBO: at random timestamps in the same markets,
take the prevailing touch as a hypothetical fill and compute the same markout. That is the payoff of
a quote that did NOT get selected against.

    adverse selection = markout(actual fills) - markout(placebo quotes at the touch)

If filled quotes do no worse than random-time quotes, being filled carries no information and the
KILLED prior does NOT transfer to US. If filled quotes do systematically worse, it does. Two of our
four retractions reversed SIGN once a control was added; this is that control.

Significance: bootstrap CI CLUSTERED BY MARKET. Prints inside one market are heavily correlated
(one informed sweep produces dozens of prints), so an iid bootstrap would understate the error bar
by a large factor and manufacture significance. Clusters are markets.

Usage:
    python3 scripts/us_adverse_selection.py                 # full measurement + control
    python3 scripts/us_adverse_selection.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_fees  # noqa: E402

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")

HORIZONS = [1, 5, 30, 60, 300]     # seconds; must stay <= us_mid_tape MARKOUT_MAX_S
MAX_STALE_S = 120                  # a mid older than this is not a fair value; drop the observation
BOOTSTRAP = 2000
SEED = 20260714


# ---------------------------------------------------------------------------------------------
# The asof join. For each fill: the mid just BEFORE it (fair value at the moment of the fill) and
# the mid at t+D (fair value after). `MAX_STALE_S` guards against pricing a markout off a mid from
# another era of the market -- a stale mid is not a fair value, it is a fossil.
# ---------------------------------------------------------------------------------------------
_FILLS_SQL = """
WITH f AS (
    SELECT t.id, t.us_slug, t.price, t.quantity, t.maker_username, t.maker_side, t.trade_time,
           (CASE WHEN t.maker_side = 'ORDER_SIDE_BUY' THEN 1.0 ELSE -1.0 END)::double precision
               AS sign
      FROM us_trade_tape t
     WHERE t.maker_side IN ('ORDER_SIDE_BUY', 'ORDER_SIDE_SELL')
       AND t.price BETWEEN 0.01 AND 0.99
       AND t.trade_time >= %(t0)s
),
pre AS (   -- fair value at the fill
    SELECT f.*, m.mid AS mid_t, m.spread
      FROM f
      JOIN LATERAL (
           SELECT mid, spread FROM us_mid_tape m
            WHERE m.us_slug = f.us_slug AND m.mid IS NOT NULL
              AND m.transact_time <= f.trade_time
              AND m.transact_time >  f.trade_time - (%(stale)s || ' seconds')::interval
         ORDER BY m.transact_time DESC LIMIT 1) m ON TRUE
)
SELECT pre.id, pre.us_slug, pre.price, pre.quantity, pre.maker_username, pre.sign,
       pre.mid_t, pre.spread, {post_cols}
  FROM pre
 WHERE {post_where}
"""


def _post_col(d):
    """mid at t+D, as of the last book update at or before that instant (and not stale)."""
    return f"""(SELECT m.mid FROM us_mid_tape m
                 WHERE m.us_slug = pre.us_slug AND m.mid IS NOT NULL
                   AND m.transact_time <= pre.trade_time + interval '{d} seconds'
                   AND m.transact_time >  pre.trade_time + interval '{d} seconds'
                                          - ({MAX_STALE_S} || ' seconds')::interval
              ORDER BY m.transact_time DESC LIMIT 1) AS mid_{d}"""


def load_fills(con, t0):
    post_cols = ",\n       ".join(_post_col(d) for d in HORIZONS)
    # Require the LONGEST horizon to exist: otherwise the sample silently shrinks with D and each
    # horizon is measured on a different, survivorship-selected set of fills.
    dmax = max(HORIZONS)
    post_where = f"""EXISTS (SELECT 1 FROM us_mid_tape m
                              WHERE m.us_slug = pre.us_slug AND m.mid IS NOT NULL
                                AND m.transact_time >= pre.trade_time + interval '{dmax} seconds')"""
    sql = _FILLS_SQL.format(post_cols=post_cols, post_where=post_where)
    with con.cursor() as cur:
        cur.execute(sql, {"t0": t0, "stale": MAX_STALE_S})
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------------------------
# THE CONTROL. Random timestamps in the same markets; the prevailing touch is a hypothetical fill.
# This is the payoff of a quote that was NOT selected against. One placebo per side, so the control
# has the same directional mix as the treatment rather than a lucky one.
# ---------------------------------------------------------------------------------------------
_PLACEBO_SQL = """
WITH q AS (
    SELECT m.id, m.us_slug, m.best_bid, m.best_ask, m.mid, m.spread, m.transact_time
      FROM us_mid_tape m
     WHERE m.track_reason = 'traded' AND m.mid IS NOT NULL AND m.spread > 0
       AND m.best_bid IS NOT NULL AND m.best_ask IS NOT NULL
       AND m.transact_time >= %(t0)s
       AND m.us_slug IN %(slugs)s
     ORDER BY random() LIMIT %(n)s
)
SELECT q.us_slug, q.best_bid, q.best_ask, q.mid, q.spread, {post_cols}
  FROM q
"""


def _placebo_post_col(d):
    return f"""(SELECT m.mid FROM us_mid_tape m
                 WHERE m.us_slug = q.us_slug AND m.mid IS NOT NULL
                   AND m.transact_time <= q.transact_time + interval '{d} seconds'
                   AND m.transact_time >  q.transact_time + interval '{d} seconds'
                                          - ({MAX_STALE_S} || ' seconds')::interval
              ORDER BY m.transact_time DESC LIMIT 1) AS mid_{d}"""


def load_placebo(con, t0, slugs, n=20000):
    post_cols = ",\n       ".join(_placebo_post_col(d) for d in HORIZONS)
    with con.cursor() as cur:
        cur.execute(_PLACEBO_SQL.format(post_cols=post_cols),
                    {"t0": t0, "slugs": tuple(slugs), "n": n})
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------------------------
# Cluster bootstrap by MARKET. Prints within a market are not independent -- one informed sweep is
# dozens of correlated prints. Resampling prints iid would shrink the CI by ~sqrt(prints/market)
# and manufacture significance out of correlation.
# ---------------------------------------------------------------------------------------------
def cluster_bootstrap_mean(values_by_cluster, n_boot=BOOTSTRAP, seed=SEED):
    rng = random.Random(seed)
    clusters = list(values_by_cluster.keys())
    if not clusters:
        return None
    flat = [v for vs in values_by_cluster.values() for v in vs]
    if not flat:
        return None
    point = statistics.fmean(flat)
    means = []
    k = len(clusters)
    for _ in range(n_boot):
        vals = []
        for _ in range(k):
            vals.extend(values_by_cluster[clusters[rng.randrange(k)]])
        if vals:
            means.append(statistics.fmean(vals))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    # two-sided bootstrap p for H0: mean == 0
    p = 2.0 * min(sum(1 for m in means if m <= 0), sum(1 for m in means if m >= 0)) / len(means)
    return {"mean": point, "ci_lo": lo, "ci_hi": hi, "p": min(p, 1.0),
            "n": len(flat), "n_clusters": k,
            "sd": statistics.pstdev(flat) if len(flat) > 1 else 0.0}


def by_cluster(rows, keyfn, valfn):
    out = {}
    for r in rows:
        v = valfn(r)
        if v is None:
            continue
        out.setdefault(keyfn(r), []).append(v)
    return out


def analyse(con, t0, placebo_n=20000):
    all_fills = load_fills(con, t0)
    # PRIMARY SAMPLE = fills whose maker the venue names. That is the tape's crown jewel and the
    # thing intl never had. The identification-bias check below tests whether restricting to it
    # distorts the answer.
    fills = [f for f in all_fills if f["maker_username"]]
    if not fills:
        return {"error": "no fills with mid coverage yet — let the tapes accrue"}

    slugs = sorted({f["us_slug"] for f in fills})
    placebo = load_placebo(con, t0, slugs, placebo_n)

    res = {"n_fills": len(fills), "n_markets": len(slugs), "n_placebo": len(placebo),
           "horizons": {}, "t0": str(t0)}

    # price band of the sample (fees and edges are price-dependent; a markout without its price
    # band is not actionable)
    prices = [f["price"] for f in fills]
    res["price"] = {"mean": statistics.fmean(prices),
                    "median": statistics.median(prices),
                    "p10": statistics.quantiles(prices, n=10)[0] if len(prices) > 10 else None,
                    "p90": statistics.quantiles(prices, n=10)[8] if len(prices) > 10 else None}
    caps = [f["sign"] * (f["mid_t"] - f["price"]) for f in fills if f["mid_t"] is not None]
    res["spread_capture_c"] = {"mean": statistics.fmean(caps) * 100 if caps else None,
                               "median": statistics.median(caps) * 100 if caps else None}
    res["rebate_c"] = statistics.fmean(
        [us_fees.maker_rebate(f["price"]) for f in fills]) * 100

    for d in HORIZONS:
        mk = f"mid_{d}"
        # TREATMENT: realized maker markout on fills that actually happened
        t_clusters = by_cluster(
            fills, lambda r: r["us_slug"],
            lambda r: (r["sign"] * (r[mk] - r["price"]) * 100) if r[mk] is not None else None)
        t_stat = cluster_bootstrap_mean(t_clusters)

        # drift term = the adverse-selection component of the markout
        d_clusters = by_cluster(
            fills, lambda r: r["us_slug"],
            lambda r: (r["sign"] * (r[mk] - r["mid_t"]) * 100)
            if (r[mk] is not None and r["mid_t"] is not None) else None)
        d_stat = cluster_bootstrap_mean(d_clusters)

        # BENCHMARK: an unselected quote resting at the touch. Note this reduces ANALYTICALLY to
        # the half-spread -- averaging (mid_D - bid) and -(mid_D - ask) cancels mid_D entirely --
        # so it is a statement of what you earn if you are NEVER picked off, not a drift probe.
        # It is the economic bar the fills must clear, nothing more.
        def placebo_val(r):
            if r[mk] is None or r["mid"] is None:
                return None
            buy = 1.0 * (r[mk] - r["best_bid"])      # rest at the bid
            sell = -1.0 * (r[mk] - r["best_ask"])    # rest at the ask
            return (buy + sell) / 2.0 * 100          # == half-spread, by construction
        p_clusters = by_cluster(placebo, lambda r: r["us_slug"], placebo_val)
        p_stat = cluster_bootstrap_mean(p_clusters)

        # THE ARTIFACT CONTROL (this is the one that earns its keep). Same asof machinery, same
        # markets, same horizon -- but at RANDOM times with a RANDOM side. Under the null its
        # drift is ZERO by symmetry. So if it comes back non-zero, the negative drift on real
        # fills is a BUG IN THE MEASUREMENT (a biased asof join, a stale mid series, a sign slip)
        # rather than informed flow. Two of our four retractions reversed sign when a control was
        # finally added; this is the control that would catch that here.
        rng_pl = random.Random(SEED + 977 + d)

        def placebo_drift(r):
            if r[mk] is None or r["mid"] is None:
                return None
            sgn = 1.0 if rng_pl.random() < 0.5 else -1.0
            return sgn * (r[mk] - r["mid"]) * 100
        pd_clusters = by_cluster(placebo, lambda r: r["us_slug"], placebo_drift)
        pd_stat = cluster_bootstrap_mean(pd_clusters)

        # THE NUMBER: adverse selection = treatment - control, bootstrapped on the DIFFERENCE
        # (paired at the market level, so market-level drift cancels rather than leaking in).
        rng = random.Random(SEED + d)
        common = [s for s in t_clusters if s in p_clusters]
        diffs = []
        for _ in range(BOOTSTRAP):
            tv, pv = [], []
            for _ in range(len(common)):
                s = common[rng.randrange(len(common))]
                tv.extend(t_clusters[s])
                pv.extend(p_clusters[s])
            if tv and pv:
                diffs.append(statistics.fmean(tv) - statistics.fmean(pv))
        diffs.sort()
        adv = None
        if diffs and common:
            tflat = [v for s in common for v in t_clusters[s]]
            pflat = [v for s in common for v in p_clusters[s]]
            point = statistics.fmean(tflat) - statistics.fmean(pflat)
            pval = 2.0 * min(sum(1 for x in diffs if x <= 0),
                             sum(1 for x in diffs if x >= 0)) / len(diffs)
            adv = {"mean": point, "ci_lo": diffs[int(0.025 * len(diffs))],
                   "ci_hi": diffs[int(0.975 * len(diffs))], "p": min(pval, 1.0),
                   "n_clusters": len(common)}

        res["horizons"][d] = {"markout_fills_c": t_stat, "drift_c": d_stat,
                              "placebo_touch_c": p_stat, "placebo_drift_c": pd_stat,
                              "adverse_selection_c": adv}
    return res


def analyse_identification(con, t0):
    """IDENTIFICATION-BIAS CHECK — is the 48% of prints whose maker the venue NAMES a fair sample?

    The venue publishes maker_username on only ~48% of prints. Our whole maker verdict is measured
    on those. If the anonymous 52% are a different animal — a designated market maker, an internal
    liquidity program, an institution routed differently — then the named makers are a selected
    subsample and the verdict does not generalize to 'what happens to a resting order on US'.

    We can test it, because maker_SIDE is published even when maker_USERNAME is not. So we compute
    the identical markout on the anonymous half and compare. This is the difference between
    'we measured the makers we could see' and 'we measured the makers'.
    """
    fills = load_fills(con, t0)
    out = {}
    for label, sub in (("named maker (48%)", [f for f in fills if f["maker_username"]]),
                       ("anonymous maker (52%)", [f for f in fills if not f["maker_username"]])):
        if len(sub) < 30:
            out[label] = {"n": len(sub), "note": "insufficient n"}
            continue
        row = {"n": len(sub), "n_markets": len({f["us_slug"] for f in sub})}
        caps = [f["sign"] * (f["mid_t"] - f["price"]) * 100 for f in sub if f["mid_t"] is not None]
        row["spread_capture_c"] = statistics.fmean(caps) if caps else None
        row["price_mean"] = statistics.fmean([f["price"] for f in sub])
        for d in (30, 60):
            mk = f"mid_{d}"
            row[f"markout_{d}s_c"] = cluster_bootstrap_mean(by_cluster(
                sub, lambda r: r["us_slug"],
                lambda r: (r["sign"] * (r[mk] - r["price"]) * 100) if r[mk] is not None else None))
            row[f"drift_{d}s_c"] = cluster_bootstrap_mean(by_cluster(
                sub, lambda r: r["us_slug"],
                lambda r: (r["sign"] * (r[mk] - r["mid_t"]) * 100)
                if (r[mk] is not None and r["mid_t"] is not None) else None))
        out[label] = row
    return out


PRICE_BANDS = [
    ("longshot 0.03-0.30", 0.03, 0.30),
    ("midrange 0.30-0.71", 0.30, 0.71),
    ("FAVORITE 0.71-0.98", 0.71, 0.98),   # our champion arm
]


def analyse_bands(con, t0):
    """Adverse selection is not one number — it is a function of price, and our arms live in
    specific bands. A venue-wide average would blend our champion favorite band with the
    coin-flips we don't trade, and the fee schedule (Theta*p*(1-p)) is itself price-dependent, so
    a blended answer is not actionable for ANY arm."""
    fills = load_fills(con, t0)
    out = {}
    for name, lo, hi in PRICE_BANDS:
        sub = [f for f in fills if lo <= f["price"] < hi]
        if len(sub) < 30:
            out[name] = {"n": len(sub), "note": "insufficient n"}
            continue
        row = {"n": len(sub), "n_markets": len({f["us_slug"] for f in sub})}
        caps = [f["sign"] * (f["mid_t"] - f["price"]) * 100 for f in sub if f["mid_t"] is not None]
        row["spread_capture_c"] = statistics.fmean(caps) if caps else None
        row["rebate_c"] = statistics.fmean([us_fees.maker_rebate(f["price"]) for f in sub]) * 100
        row["taker_fee_c"] = statistics.fmean([us_fees.taker_fee(f["price"]) for f in sub]) * 100
        for d in (30, 60):
            mk = f"mid_{d}"
            mo = cluster_bootstrap_mean(by_cluster(
                sub, lambda r: r["us_slug"],
                lambda r: (r["sign"] * (r[mk] - r["price"]) * 100) if r[mk] is not None else None))
            dr = cluster_bootstrap_mean(by_cluster(
                sub, lambda r: r["us_slug"],
                lambda r: (r["sign"] * (r[mk] - r["mid_t"]) * 100)
                if (r[mk] is not None and r["mid_t"] is not None) else None))
            row[f"markout_{d}s_c"] = mo
            row[f"drift_{d}s_c"] = dr
        out[name] = row
    return out


def report(res):
    if "error" in res:
        print(res["error"])
        return
    print("=" * 94)
    print("ADVERSE SELECTION ON POLYMARKET US — measured on REAL identified makers")
    print("=" * 94)
    print(f"fills (maker identified, full mid coverage): n={res['n_fills']} "
          f"across {res['n_markets']} markets | placebo quotes: n={res['n_placebo']}")
    pr = res["price"]
    print(f"fill price: mean {pr['mean']:.3f}  median {pr['median']:.3f}"
          + (f"  p10-p90 {pr['p10']:.2f}-{pr['p90']:.2f}" if pr["p10"] else ""))
    sc = res["spread_capture_c"]
    print(f"spread capture at fill: mean {sc['mean']:+.3f}c  median {sc['median']:+.3f}c "
          f"| maker rebate at these prices: {res['rebate_c']:+.3f}c")
    print()
    print("all figures = CENTS PER SHARE for the MAKER (the resting side). Negative = maker loses.")
    print("  markout = what the maker ACTUALLY realized (spread capture + drift). THE number.")
    print("  drift   = fair value moving against the fill = ADVERSE SELECTION itself.")
    print("  placebo = same asof machinery, random time + random side: MUST be ~0, else the")
    print("            drift below is a measurement artifact, not informed flow.")
    print()
    print(f"{'D':>5} {'markout(fills)':>21} {'drift (ADV SEL)':>22} {'p':>6} "
          f"{'placebo drift':>17} {'unpicked-off bar':>17}")
    print("-" * 94)
    for d in HORIZONS:
        h = res["horizons"][d]
        m, dr, p_, pd = (h["markout_fills_c"], h["drift_c"],
                         h["placebo_touch_c"], h["placebo_drift_c"])
        if not (m and dr and p_ and pd):
            continue
        print(f"{d:>4}s {m['mean']:>+7.3f}c [{m['ci_lo']:+.2f},{m['ci_hi']:+.2f}] "
              f"{dr['mean']:>+8.3f}c [{dr['ci_lo']:+.2f},{dr['ci_hi']:+.2f}] "
              f"{dr['p']:>6.3f} {pd['mean']:>+7.3f}c{'':>8} {p_['mean']:>+7.3f}c")
    print("-" * 94)
    m0 = res["horizons"][HORIZONS[0]]["markout_fills_c"]
    print(f"n={m0['n']} fills, clusters(markets)={m0['n_clusters']}; "
          f"95% CIs are CLUSTER bootstrap by market ({BOOTSTRAP} reps, sd={m0['sd']:.2f}c).")

    # HAZARD / REWARD — the number that faces intl's 13x.
    print()
    print("HAZARD / REWARD  (the ratio that KILLED making on intl at 13x)")
    for d in (30, 60):
        h = res["horizons"][d]
        drift = h["drift_c"]["mean"]
        reward = res["spread_capture_c"]["mean"] + res["rebate_c"]     # what making PAYS you
        if reward > 0:
            print(f"  at {d:>3}s: hazard |drift| = {abs(drift):.3f}c  vs  reward "
                  f"(spread capture {res['spread_capture_c']['mean']:+.3f}c + rebate "
                  f"{res['rebate_c']:+.3f}c) = {reward:.3f}c   ->  ratio {abs(drift)/reward:.2f}x")
    print("  (a ratio < 1.0 means making is paid MORE than it is picked off, BEFORE any")
    print("   liquidity-pool subsidy. >= 1.0 means the rebate alone cannot carry it.)")


def report_bands(bands):
    print()
    print("=" * 94)
    print("BY PRICE BAND — adverse selection is a FUNCTION OF PRICE, and so is the fee")
    print("=" * 94)
    print(f"{'band':<22}{'n':>6}{'mkts':>6}{'capture':>9}{'drift30':>10}{'markout30':>11}"
          f"{'markout60':>11}{'rebate':>8}{'takerfee':>9}")
    print("-" * 94)
    for name, r in bands.items():
        if r.get("note"):
            print(f"{name:<22}{r['n']:>6}   -- {r['note']}")
            continue
        m30, m60, d30 = r["markout_30s_c"], r["markout_60s_c"], r["drift_30s_c"]
        print(f"{name:<22}{r['n']:>6}{r['n_markets']:>6}{r['spread_capture_c']:>+8.2f}c"
              f"{d30['mean']:>+9.2f}c{m30['mean']:>+10.2f}c{m60['mean']:>+10.2f}c"
              f"{r['rebate_c']:>+7.2f}c{r['taker_fee_c']:>+8.2f}c")
    print("-" * 94)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2000-01-01",
                    help="only fills at/after this timestamp (default: all)")
    ap.add_argument("--placebo-n", type=int, default=20000)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    con = psycopg2.connect(PG_DSN)
    try:
        res = analyse(con, a.since, a.placebo_n)
        bands = analyse_bands(con, a.since) if "error" not in res else {}
        ident = analyse_identification(con, a.since) if "error" not in res else {}
    finally:
        con.close()
    report(res)
    if bands:
        report_bands(bands)
        res["bands"] = bands
    if ident:
        print()
        print("=" * 94)
        print("IDENTIFICATION-BIAS CHECK — do the makers the venue NAMES behave like the ones it hides?")
        print("=" * 94)
        print(f"{'maker sample':<24}{'n':>6}{'mkts':>6}{'avg px':>8}{'capture':>9}"
              f"{'drift30':>10}{'markout30':>11}{'markout60':>11}")
        print("-" * 94)
        for k, r in ident.items():
            if r.get("note"):
                print(f"{k:<24}{r['n']:>6}   -- {r['note']}")
                continue
            print(f"{k:<24}{r['n']:>6}{r['n_markets']:>6}{r['price_mean']:>8.3f}"
                  f"{r['spread_capture_c']:>+8.2f}c{r['drift_30s_c']['mean']:>+9.2f}c"
                  f"{r['markout_30s_c']['mean']:>+10.2f}c{r['markout_60s_c']['mean']:>+10.2f}c")
        print("-" * 94)
        print("If these two rows disagree materially, the maker verdict is measured on a SELECTED")
        print("subsample and must be stated as such.")
        res["identification"] = ident
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1, default=str)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
