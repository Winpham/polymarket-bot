#!/usr/bin/env python3
"""
WS-4 — TWO-SIDED SOFTNESS / FADE PROBE (the underdog complement to D24's favorite-side map).

Note (multi-chat): a parallel run shipped the richer favorite-SIDE softness×skill map (D24,
category×type×band, softness/skill/ROI separated, map-integrated). THIS instrument's additive angle is
the TWO-SIDED test — it surfaces NO-side / underdog softness (overpriced favorites you FADE) that a
favorite-only (entry≥0.60) map cannot see. Keep both: D24 aims the favorite edge at soft pockets; this
finds where the favorite itself is OVERPRICED. Same blind universe; different question.

Where is the LINE itself soft — bet it directly, no sharps.

The CLV finding (D22/WS-A) says the copy-consensus edge is mostly favorite-longshot BIAS the market
never corrects, not information we front-run. That reframes the goal (per Tue's live-betting posture):
stop being the lazy lagging copycat; find where the MARKET is mispriced and bet the line at OUR price.
This instrument maps market softness = the calibration gap (realized WR − price) over the BLIND
universe (every tracked-trader market, ~10k resolved rows — NOT just consensus picks), per
(sport × market-type × band), and asks which cells are genuinely + bettably soft.

Two reads per cell, kept separate (the truth-audit discipline — selection vs composition):
  RAW gap        = event-clustered mean(won − entry). Positive ⇒ YES underpriced; the raw blind edge.
  EXCESS         = cell gap − the BAND-level blind gap (the generic favorite-longshot curve). Positive
                   excess ⇒ this sport×type is softer than the band's FLB alone explains — the NOVEL
                   signal (a specific soft pocket, not just "favorites win").
Null (per cell): within-BAND label permutation of `won` (preserves the band FLB baseline, destroys
  cell structure) ⇒ p on EXCESS. BH-FDR q=0.10 across tested cells (≥ MIN_EVENTS distinct events).
Bettable: the best SIDE (YES if gap>0 else NO) net of cost (1¢ haircut + 2% fee) > 0 ⇒ a cell you
  could bet the line on directly. A soft cell must be BOTH FDR-real (excess) AND net-positive (raw).

Read-only, paper-only. This maps; it certifies nothing (persistence/D7 still govern real money).
  ./softness_fade.py                # the map + verdict; writes reports/softness_fade.json
  ./softness_fade.py --selftest     # injected soft cell detected; flat cell not; NO/YES side logic
"""

import argparse
import csv
import io
import json
import os
import random
import re
import subprocess
import sys
from collections import defaultdict
from math import sqrt

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
HAIRCUT, FEE = 0.01, 0.02
MIN_EVENTS = 30            # distinct-event floor to test a cell
N_PERM = 2000
SEED = 20260703
FDR_Q = 0.10
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

SPORTS = [
    (re.compile(r"^(fifwc)"), "soccer"),
    (re.compile(r"^(atp|wta|itf)"), "tennis"),
    (re.compile(r"^(mlb)"), "mlb"),
    (re.compile(r"^(btc|eth|sol|xrp|bnb|doge|hype|bitcoin|ethereum)"), "crypto"),
    (re.compile(r"^(cs|counterstrike)"), "cs2"),
]
# market-type from the market slug
RE_EXACT = re.compile(r"exact-score|correct-score")
RE_TOTAL = re.compile(r"total|over-under|o-u-|goals|-runs|points|score-over|score-under")
RE_SPREAD = re.compile(r"spread|handicap|-by-|margin")

SQL = """
SELECT COALESCE(event_slug, condition_id) AS ev, event_slug, slug,
       initial_mean_price AS entry, (outcome_won::int) AS won
FROM consensus_signals
WHERE strategy='_blind' AND resolved AND initial_mean_price IS NOT NULL
"""


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def band(p):
    if p < 0.0:
        return 0
    if p >= 1.0:
        return 6
    return int(p * 5.0) + 1


def sport_of(ev):
    for rx, name in SPORTS:
        if rx.search(ev or ""):
            return name
    return "other"


def market_type(slug):
    s = slug or ""
    if RE_EXACT.search(s):
        return "exact_score"
    if RE_TOTAL.search(s):
        return "total"
    if RE_SPREAD.search(s):
        return "spread"
    return "directional"


def clustered_mean(pairs):
    ev = defaultdict(list)
    for k, v in pairs:
        ev[k].append(v)
    if not ev:
        return float("nan"), 0
    means = [sum(v) / len(v) for v in ev.values()]
    return sum(means) / len(means), len(means)


def load_rows():
    rows = []
    for r in q(SQL):
        entry = float(r["entry"])
        rows.append({"ev": r["ev"], "entry": entry, "won": int(r["won"]),
                     "band": band(entry), "sport": sport_of(r["event_slug"]),
                     "mtype": market_type(r["slug"])})
    return rows


def analyze(rows, rng):
    # band-level FLB baseline (the generic favorite-longshot curve)
    band_gap = {}
    by_band = defaultdict(list)
    for r in rows:
        by_band[r["band"]].append((r["ev"], r["won"] - r["entry"]))
    for b, pairs in by_band.items():
        band_gap[b], _ = clustered_mean(pairs)

    # cells
    cells = defaultdict(list)
    for r in rows:
        cells[(r["sport"], r["mtype"], r["band"])].append(r)

    # for the permutation null: won values grouped by band (shuffle within band)
    band_rows = defaultdict(list)
    for r in rows:
        band_rows[r["band"]].append(r)

    results = []
    for key, crows in cells.items():
        sport, mtype, b = key
        gap, nev = clustered_mean([(r["ev"], r["won"] - r["entry"]) for r in crows])
        if nev < MIN_EVENTS:
            continue
        base = band_gap.get(b, 0.0)
        excess = gap - base
        entry_mean = sum(r["entry"] for r in crows) / len(crows)
        # best side net of cost: YES if gap>0 else NO (buy complement at 1-entry)
        net_yes = gap - HAIRCUT - FEE * entry_mean
        net_no = -gap - HAIRCUT - FEE * (1.0 - entry_mean)
        side = "YES" if net_yes >= net_no else "NO"
        net = max(net_yes, net_no)

        # within-band permutation null on EXCESS (preserve band FLB, destroy cell structure).
        # BOTH tails: +excess ⇒ YES underpriced (soft YES); −excess ⇒ YES overpriced (soft NO/underdog).
        # The bettable side is data-chosen, so use a TWO-SIDED p (2·min tail) before FDR — no double-dip.
        cell_ev = [r["ev"] for r in crows]
        pool = band_rows[b]
        k = len(crows)
        ge = le = 0
        null_excess = []
        for _ in range(N_PERM):
            samp = rng.sample(pool, k) if k <= len(pool) else rng.choices(pool, k=k)
            g, _ = clustered_mean([(cell_ev[i], samp[i]["won"] - crows[i]["entry"]) for i in range(k)])
            ex = g - base
            null_excess.append(ex)
            if ex >= excess:
                ge += 1
            if ex <= excess:
                le += 1
        p_yes = ge / len(null_excess)          # soft-YES tail
        p_no = le / len(null_excess)            # soft-NO (overpriced-YES) tail
        p = min(1.0, 2.0 * min(p_yes, p_no))    # two-sided (side is data-chosen)
        mu = sum(null_excess) / len(null_excess)
        sd = sqrt(sum((x - mu) ** 2 for x in null_excess) / (len(null_excess) - 1)) if len(null_excess) > 1 else float("nan")
        z = (excess - mu) / sd if sd and sd > 0 else float("nan")
        results.append({"sport": sport, "mtype": mtype, "band": b, "n_events": nev,
                        "n_rows": len(crows), "gap": gap, "band_base": base, "excess": excess,
                        "entry_mean": entry_mean, "side": side, "net_edge": net,
                        "z": z, "p": p, "p_yes": p_yes, "p_no": p_no})

    # BH-FDR on p (one-sided, softness). q=0.10.
    results.sort(key=lambda d: d["p"])
    m = len(results)
    thresh = 0.0
    for i, d in enumerate(results, 1):
        if d["p"] <= (i / m) * FDR_Q:
            thresh = (i / m) * FDR_Q
    for d in results:
        # two-sided p already encodes direction; the bettable SIDE (YES/NO) carries the sign.
        d["fdr_soft"] = d["p"] <= thresh
        d["bettable"] = d["net_edge"] > 0
        d["SOFT_CELL"] = d["fdr_soft"] and d["bettable"]
    return results, band_gap


def run():
    rows = load_rows()
    rng = random.Random(SEED)
    results, band_gap = analyze(rows, rng)
    results.sort(key=lambda d: (-d["SOFT_CELL"], -d["net_edge"]))
    _print(results, band_gap, len(rows))
    out = {"meta": {"n_blind_rows": len(rows), "min_events": MIN_EVENTS, "n_perm": N_PERM,
                    "seed": SEED, "fdr_q": FDR_Q,
                    "band_flb": {str(k): round(v, 4) for k, v in sorted(band_gap.items())}},
           "cells": results}
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, "softness_fade.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {path}")
    return out


def _print(results, band_gap, n):
    print("=" * 92)
    print(f"WS-4 · MARKET-SOFTNESS MAP · blind universe {n} rows · band-FLB baseline + within-band null")
    print("=" * 92)
    print("band-level FLB (generic favorite-longshot curve, gap = realized WR − price):")
    print("  " + "  ".join(f"b{b}:{g:+.3f}" for b, g in sorted(band_gap.items())))
    print("-" * 92)
    hdr = f"{'sport':<8}{'type':<12}{'bd':>3}{'ev':>5}{'gap':>8}{'excess':>8}{'z':>6}{'p':>7}{'side':>5}{'net':>8}  verdict"
    print(hdr); print("-" * len(hdr))
    for d in results:
        v = "SOFT ✓" if d["SOFT_CELL"] else ("fdr-only" if d["fdr_soft"] else ("+net" if d["bettable"] else ""))
        print(f"{d['sport']:<8}{d['mtype']:<12}{d['band']:>3}{d['n_events']:>5}{d['gap']:>+8.3f}"
              f"{d['excess']:>+8.3f}{d['z']:>6.2f}{d['p']:>7.3f}{d['side']:>5}{d['net_edge']:>+8.3f}  {v}")
    soft = [d for d in results if d["SOFT_CELL"]]
    print("-" * 92)
    print(f"SOFT CELLS (FDR-real excess ∧ net-positive after cost): {len(soft)}")
    for d in soft:
        print(f"  → {d['sport']}/{d['mtype']}/band{d['band']}: bet {d['side']}, net {d['net_edge']:+.1%} "
              f"over {d['n_events']} events (gap {d['gap']:+.1%}, excess {d['excess']:+.1%}, p={d['p']:.3f})")
    if not soft:
        print("  (none survive both gates — market is efficient beyond generic FLB where powered)")
    print("NOT certification — persistence/D7 still gate real money; this maps where to LOOK.")


def selftest():
    ok = True
    rng = random.Random(1)
    # Build a synthetic blind universe at band3 with SEVERAL calibrated cells (so no single cell
    # dominates the band — the null's valid regime; a cell that IS ~the whole band has a degenerate
    # near-zero-variance null and is excluded from testing in practice), plus ONE small STRONG soft
    # pocket (soccer/total/band3, WR 0.75 at price 0.5).
    rows = []
    for sp in ("soccer", "tennis", "mlb"):          # 3 calibrated directional cells, WR 0.5
        for i in range(300):
            rows.append({"ev": f"cal{sp}{i//2}", "entry": 0.5, "won": 1 if rng.random() < 0.5 else 0,
                         "band": 3, "sport": sp, "mtype": "directional"})
    for i in range(80):    # SOFT pocket: soccer/total/band3 price 0.5 but WR 0.75 (~8% of the band)
        rows.append({"ev": f"soft{i//2}", "entry": 0.5, "won": 1 if rng.random() < 0.75 else 0,
                     "band": 3, "sport": "soccer", "mtype": "total"})
    results, _ = analyze(rows, rng)
    soft = [d for d in results if d["sport"] == "soccer" and d["mtype"] == "total"]
    flat = [d for d in results if d["mtype"] == "directional"]
    c1 = soft and soft[0]["excess"] > 0.05 and soft[0]["p"] < 0.05
    c2 = (not flat) or all(not f["fdr_soft"] for f in flat)
    ok = ok and bool(c1) and bool(c2)
    print(f"  [{'ok' if c1 else 'FAIL'}] injected soft cell detected: excess "
          f"{soft[0]['excess']:+.3f} p {soft[0]['p']:.3f}" if soft else "  FAIL no soft cell built")
    print(f"  [{'ok' if c2 else 'FAIL'}] calibrated directional cell NOT flagged soft")
    # NO-side logic: a cell with gap −0.10 (YES overpriced) should pick side NO with +net
    over = [{"ev": f"o{i//2}", "entry": 0.6, "won": 1 if i % 10 < 5 else 0, "band": 4,
             "sport": "mlb", "mtype": "directional"} for i in range(120)]  # WR 0.5 < price 0.6 → NO soft
    r2, _ = analyze(over + rows, rng)
    mlb = [d for d in r2 if d["sport"] == "mlb"]
    c3 = mlb and mlb[0]["side"] == "NO" and mlb[0]["net_edge"] > 0
    ok = ok and bool(c3)
    print(f"  [{'ok' if c3 else 'FAIL'}] overpriced-YES cell → bet NO, net {mlb[0]['net_edge']:+.3f}"
          if mlb else "  FAIL no mlb cell")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        selftest()
        return
    run()


if __name__ == "__main__":
    main()
