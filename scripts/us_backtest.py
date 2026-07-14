#!/usr/bin/env python3
"""US BACKTEST — replay our favorite arm ON THE US VENUE, at US prices, US settlement, US fees.

WHAT MAKES THIS A REAL US BACKTEST (and not an intl backtest wearing a US hat)
-----------------------------------------------------------------------------
The live identity tape only accrues FORWARD (no history endpoint), so it cannot reach back to
06/29. But Polymarket US is a CFTC-regulated DCM, and a DCM must PUBLISH its tape. So the history
exists on the regulatory rung:

  ENTRY   = the first REAL US PRINT at/after our signal fired, from the statutory Time & Sales tape
            (~1.3-1.9M prints/day, back to 2025-10-29). Not an intl price. Not a model. A price a
            human actually transacted at, on the venue we would have traded.
  EXIT    = the US Daily Market Report's SETTLEMENT price (0.0/1.0) for that instrument.
            102,374 rows / 100% settled across the window.
  FEE     = the US taker fee, Theta*q*(1-q), Theta=0.06 (confirmed on all 2,999 live markets).

SIDE CORRECTNESS (an inverted map is a silent, catastrophic, money-losing bug)
-----------------------------------------------------------------------------
A US symbol is ONE binary contract; its T&S price is the contract's (YES) price and its DMR
settlement is 0/1 on that same side. The mapper returns the contract; `side_index` picks which side
we buy from the venue's `side_desc` and REFUSES on ambiguity (never guesses). So:
    our cost q      = px            if side==0 else 1 - px
    our payoff      = settlement    if side==0 else 1 - settlement
Fee is symmetric in q(1-q), so it is identical either way.

WHAT THIS ANSWERS
-----------------
1. Does the favorite arm SURVIVE US taker fees? (gross ROI vs net ROI, per band)
2. THE OPEN QUESTION FROM UV-11: is ROI FLAT across the favorite band? The "tilt deep" rule only
   pays if ROI does NOT fall as p rises. The fee is a tax on UNCERTAINTY --
       fee as a fraction of edge = Theta*(1-p)/ROI
   -- so deep favorites are cheap to take ONLY IF their ROI holds up. This measures ROI(p) directly
   instead of assuming it, which is exactly what the report flagged as a prerequisite.

Clustered by EVENT, because the unit of risk is the GAME ([[project-polymarket-correlated-risk]]):
signals on the same game are one bet, and an iid bootstrap over signals would fabricate confidence.

READ-ONLY. No order placed.

Usage:
    python3 scripts/us_backtest.py --from 2026-06-29 --to 2026-07-14
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys

import duckdb
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_fees  # noqa: E402
import us_mapper as M  # noqa: E402
import us_quote_capture as Q  # noqa: E402

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
ARCHIVE = os.path.expanduser(os.environ.get("US_ARCHIVE_DIR", "~/polymarket-archive"))
TS_GLOB = os.path.join(ARCHIVE, "us_time_sales", "*.parquet")

# How long after the signal fires we will still accept a US print as "our entry". A signal we
# cannot fill promptly is a signal we did not trade; stretching this would quietly import
# look-ahead (a print hours later, after the market moved our way).
MAX_ENTRY_LAG_MIN = 60

BANDS = [(0.71, 0.80), (0.80, 0.90), (0.90, 0.95), (0.95, 0.98)]

# We are the TAKER: we buy at the ASK, but the T&S tape only publishes PRINTS (which happen at the
# bid as often as the ask). Entering at the print therefore understates our cost by ~half a spread
# and flatters the arm. Median US spread = 1.0c (measured, us_mid_tape) -> 0.5c is the realistic
# haircut. The headline runs WITH it; --haircut sweeps 0/0.5/1.0 so the sensitivity is visible.
HAIRCUT_C = 0.5
BOOTSTRAP = 2000
SEED = 20260714


def load_signals(con, d_from, d_to):
    """The arm's own selection, unchanged. Gates are the certified favorite_v2 policy:
    band 0.71-0.98, liquidity >= $1k, best_backer_rank < 5 ([[project-polymarket-garbage-policy]])."""
    with con.cursor() as cur:
        cur.execute("""
            SELECT id, condition_id, outcome_index, event_slug, slug, title, outcome_label,
                   mean_price, total_usd, best_backer_rank, first_detected_at, is_sports,
                   outcome_won, entry_ask
              FROM consensus_signals
             WHERE first_detected_at >= %s AND first_detected_at < %s
               AND resolved AND outcome_won IS NOT NULL
               AND mean_price BETWEEN 0.71 AND 0.98
          ORDER BY first_detected_at
        """, (d_from, d_to))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def settlements(con, d_from, d_to):
    """symbol -> settlement (0/1). Take the LAST business_date per symbol: a contract settles once,
    and earlier rows carry the pre-settlement 0.0 default."""
    with con.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (symbol) symbol, settlement_price
              FROM us_daily_market_report
             WHERE settlement_price IS NOT NULL
          ORDER BY symbol, business_date DESC
        """)
        return {r[0]: float(r[1]) for r in cur.fetchall()}


def map_all(con, sigs):
    """intl signal -> (us_slug, side). Fail-closed: below the mapper threshold we SKIP."""
    d = duckdb.connect()                     # build_index reads the US market parquet, not Postgres
    idx = M.build_index(d)
    meta = {r[0]: {"closed": r[1], "side_desc": r[2]} for r in d.execute(
        f"SELECT slug, closed, side_desc FROM read_parquet('{M.US_PARQUET}')").fetchall()}
    d.close()

    out, skipped = [], {"unmapped": 0, "no_meta": 0, "ambiguous_side": 0}
    for s in sigs:
        m = M.map_signal(idx, s["event_slug"], s["slug"], s["title"])
        if m.confidence < M.THRESHOLD or not m.us_slug:
            skipped["unmapped"] += 1
            continue
        mt = meta.get(m.us_slug)
        if not mt:
            skipped["no_meta"] += 1
            continue
        _, si = Q.side_index(mt["side_desc"], s["outcome_label"])
        if si is None:
            skipped["ambiguous_side"] += 1
            continue
        s = dict(s)
        s["us_slug"], s["side"], s["conf"] = m.us_slug, si, m.confidence
        out.append(s)
    return out, skipped


def attach_us_entry(mapped):
    """The FIRST real US print at/after the signal fired = our realizable US entry."""
    if not mapped:
        return []
    d = duckdb.connect()
    d.execute("CREATE TABLE sig (sid BIGINT, sym VARCHAR, fire TIMESTAMPTZ)")
    d.executemany("INSERT INTO sig VALUES (?, ?, ?)",
                  [(s["id"], s["us_slug"], s["first_detected_at"]) for s in mapped])
    rows = d.execute(f"""
        WITH p AS (
            SELECT "Symbol" AS sym, "Transaction Time" AS ts, "Last Price" AS px
              FROM read_parquet('{TS_GLOB}')
             WHERE "Symbol" IN (SELECT DISTINCT sym FROM sig)
        ), j AS (
            SELECT s.sid, p.ts, p.px,
                   ROW_NUMBER() OVER (PARTITION BY s.sid ORDER BY p.ts) AS rn
              FROM sig s
              JOIN p ON p.sym = s.sym
                    AND p.ts >= s.fire
                    AND p.ts <= s.fire + INTERVAL {MAX_ENTRY_LAG_MIN} MINUTE
        )
        SELECT sid, ts, px FROM j WHERE rn = 1
    """).fetchall()
    d.close()
    entry = {r[0]: (r[1], float(r[2])) for r in rows}
    for s in mapped:
        e = entry.get(s["id"])
        s["us_entry_ts"], s["us_px"] = (e if e else (None, None))
    return mapped


def price_it(mapped, setl, haircut_c=0.0):
    """Apply side, settlement, the US fee — and the SPREAD HAIRCUT.

    THE HAIRCUT IS NOT OPTIONAL. The T&S tape gives PRINTS, not quotes. A print happens at whoever
    crossed — sometimes the bid, sometimes the ask. But WE are the taker: we BUY AT THE ASK. So
    entering at the printed price systematically understates our cost by roughly half a spread and
    flatters the arm. On this venue the median spread is 1.0c (measured, us_mid_tape), so the
    realistic haircut is ~0.5c, and 1.0c is the conservative bound.

    This is the exact failure this project has been burned by before: an edge that certifies on a
    mid/print price and then dies at the ask ([[project-polymarket-exec-policy]]). Pricing the entry
    at a print without a haircut would repeat it.
    """
    out = []
    for s in mapped:
        if s["us_px"] is None:
            continue
        st = setl.get(s["us_slug"])
        if st is None:
            continue
        px = s["us_px"]
        q = px if s["side"] == 0 else 1.0 - px            # what WE pay per share
        payoff = st if s["side"] == 0 else 1.0 - st       # what WE collect
        q = q + haircut_c / 100.0                          # ...and we pay the ASK, not the print
        if not (0.01 <= q <= 0.99):
            continue
        gross = payoff - q                                 # $/share
        fee = us_fees.taker_fee(q)                         # Theta*q*(1-q)
        r = dict(s)
        r.update({"q": q, "payoff": payoff, "gross_c": gross * 100, "fee_c": fee * 100,
                  "net_c": (gross - fee) * 100,
                  "roi_gross": gross / q, "roi_net": (gross - fee) / q,
                  "roi_net_t25": (gross - us_fees.taker_fee(q, 1.0, 0.25)) / q,
                  "won": payoff > 0.5})
        out.append(r)
    return out


def cluster_boot(rows, key, val, n_boot=BOOTSTRAP, seed=SEED):
    """Bootstrap clustered by EVENT — the unit of risk is the GAME, not the signal."""
    groups = {}
    for r in rows:
        groups.setdefault(key(r), []).append(val(r))
    ks = list(groups)
    if not ks:
        return None
    flat = [v for vs in groups.values() for v in vs]
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        vals = []
        for _ in range(len(ks)):
            vals.extend(groups[ks[rng.randrange(len(ks))]])
        if vals:
            means.append(statistics.fmean(vals))
    means.sort()
    p = 2.0 * min(sum(1 for m in means if m <= 0), sum(1 for m in means if m >= 0)) / len(means)
    return {"mean": statistics.fmean(flat), "ci_lo": means[int(0.025 * len(means))],
            "ci_hi": means[int(0.975 * len(means))], "p": min(p, 1.0),
            "n": len(flat), "n_clusters": len(ks)}


def summarize(rows, label):
    if not rows:
        print(f"{label}: n=0")
        return None
    ev = lambda r: r["event_slug"] or r["slug"]          # noqa: E731
    g = cluster_boot(rows, ev, lambda r: r["roi_gross"] * 100)
    n = cluster_boot(rows, ev, lambda r: r["roi_net"] * 100)
    t = cluster_boot(rows, ev, lambda r: r["roi_net_t25"] * 100)
    wins = sum(1 for r in rows if r["won"])
    fee_c = statistics.fmean([r["fee_c"] for r in rows])
    q = statistics.fmean([r["q"] for r in rows])
    print(f"\n{label}")
    print(f"  n={len(rows)} picks / {g['n_clusters']} events | win {wins/len(rows):.1%} | "
          f"avg entry {q:.3f} | avg fee {fee_c:.2f}c/share")
    print(f"  ROI gross    {g['mean']:+6.2f}%  CI[{g['ci_lo']:+.2f},{g['ci_hi']:+.2f}] p={g['p']:.3f}")
    print(f"  ROI net fee  {n['mean']:+6.2f}%  CI[{n['ci_lo']:+.2f},{n['ci_hi']:+.2f}] p={n['p']:.3f}"
          f"   <- what we ACTUALLY keep on US")
    print(f"  ROI @25%tier {t['mean']:+6.2f}%  CI[{t['ci_lo']:+.2f},{t['ci_hi']:+.2f}] p={t['p']:.3f}")
    print(f"  fee drag: {g['mean']-n['mean']:.2f}pp "
          f"({(g['mean']-n['mean'])/abs(g['mean'])*100 if g['mean'] else 0:.0f}% of gross edge)")
    return {"label": label, "n": len(rows), "gross": g, "net": n, "net_t25": t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d_from", default="2026-06-29")
    ap.add_argument("--to", dest="d_to", default="2026-07-15")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    con = psycopg2.connect(PG_DSN)
    sigs = load_signals(con, a.d_from, a.d_to)
    print(f"favorite-band resolved signals {a.d_from}..{a.d_to}: {len(sigs):,}")
    mapped, skipped = map_all(con, sigs)
    print(f"mapped to a US instrument (conf>={M.THRESHOLD}): {len(mapped):,}  "
          f"(skipped: {skipped})")
    setl = settlements(con, a.d_from, a.d_to)
    con.close()

    mapped = attach_us_entry(mapped)
    got = sum(1 for s in mapped if s["us_px"] is not None)
    print(f"with a real US print within {MAX_ENTRY_LAG_MIN}min of firing: {got:,}")

    print("\n" + "=" * 92)
    print("US BACKTEST — favorite arm at US prices, US settlement, US fees")
    print("=" * 92)
    rows = price_it(mapped, setl, HAIRCUT_C)
    print(f"priced + settled on US: {len(rows):,}   "
          f"(entry = first real US print + {HAIRCUT_C:.1f}c ask haircut)")
    if not rows:
        print("\nNO TRADEABLE SAMPLE — cannot backtest. Report the coverage wall honestly.")
        return

    res = {"all": summarize(rows, "ALL mapped favorite-band picks")}

    v2 = [r for r in rows if (r["total_usd"] or 0) >= 1000
          and (r["best_backer_rank"] or 99) < 5]
    res["v2"] = summarize(v2, "favorite_v2 gates (liquidity>=$1k, rank<5)")

    nofif = [r for r in v2 if "fwc" not in (r["us_slug"] or "")]
    res["v2_nonfifwc"] = summarize(nofif, "favorite_v2, non-FIFWC")

    # DOES IT SURVIVE THE ASK? The single most dangerous assumption in this backtest.
    print("\n" + "=" * 92)
    print("EXECUTION REALISM — we are the TAKER, so we pay the ASK, not the print")
    print("=" * 92)
    print("median US spread is 1.0c (measured). A print sits at bid OR ask; we always buy the ask.")
    print(f"{'haircut':>10}{'n':>7}{'ROI gross':>12}{'ROI net':>12}{'95% CI (net)':>22}{'p':>8}")
    print("-" * 92)
    hair = {}
    for h in (0.0, 0.5, 1.0):
        sub = price_it(mapped, setl, h)
        ev = lambda r: r["event_slug"] or r["slug"]      # noqa: E731
        g = cluster_boot(sub, ev, lambda r: r["roi_gross"] * 100)
        n = cluster_boot(sub, ev, lambda r: r["roi_net"] * 100)
        tag = {0.0: "print", 0.5: "half-sprd", 1.0: "full-sprd"}[h]
        ci = "[{:+.2f},{:+.2f}]".format(n["ci_lo"], n["ci_hi"])
        print(f"{tag:>10}{len(sub):>7}{g['mean']:>+11.2f}%{n['mean']:>+11.2f}%"
              f"{ci:>22}{n['p']:>8.3f}")
        hair[tag] = {"n": len(sub), "gross": g, "net": n}
    print("-" * 92)
    res["haircut"] = hair

    # THE QUESTION: is ROI FLAT across the band? ("tilt deep" only pays if it is)
    print("\n" + "=" * 92)
    print("ROI(p) ACROSS THE BAND — does the edge SURVIVE going deep? (the UV-11 prerequisite)")
    print("=" * 92)
    print(f"{'band':>12}{'n':>6}{'ev':>5}{'win%':>6}{'fee/sh':>8}"
          f"{'ROI net':>10}{'95% CI (net)':>20}{'p':>7}  verdict")
    print("-" * 92)
    bands = {}
    for lo, hi in BANDS:
        sub = [r for r in rows if lo <= r["q"] < hi]
        if len(sub) < 20:
            print(f"{f'{lo:.2f}-{hi:.2f}':>12}{len(sub):>6}   -- too few")
            continue
        ev = lambda r: r["event_slug"] or r["slug"]      # noqa: E731
        g = cluster_boot(sub, ev, lambda r: r["roi_gross"] * 100)
        n = cluster_boot(sub, ev, lambda r: r["roi_net"] * 100)
        wins = sum(1 for r in sub if r["won"]) / len(sub)
        fee_c = statistics.fmean([r["fee_c"] for r in sub])
        v = ("EDGE" if n["ci_lo"] > 0 else
             "NEGATIVE" if n["ci_hi"] < 0 else "no edge (straddles 0)")
        ci = "[{:+.2f},{:+.2f}]".format(n["ci_lo"], n["ci_hi"])
        band = f"{lo:.2f}-{hi:.2f}"
        print(f"{band:>12}{len(sub):>6}{g['n_clusters']:>5}{wins:>5.0%}"
              f"{fee_c:>7.2f}c{n['mean']:>+9.2f}%{ci:>20}{n['p']:>7.3f}  {v}")
        bands[f"{lo}-{hi}"] = {"n": len(sub), "gross": g, "net": n, "win": wins}
    print("-" * 92)
    res["bands"] = bands

    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1, default=str)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
