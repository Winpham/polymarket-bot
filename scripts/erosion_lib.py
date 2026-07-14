#!/usr/bin/env python3
"""
erosion_lib — shared, read-only data layer for the favorite-edge erosion forensics run.

THE CENTRAL MEASUREMENT DECISION (read before using any number this produces)
---------------------------------------------------------------------------
The incumbent daily table prices each leg at `COALESCE(entry_ask, initial_mean_price)`.
`entry_ask` coverage is NOT stationary: it runs ~5% of legs on 06-29 and ~70% on 07-13
(migration 040 / capture work landed mid-window). `entry_ask` also sits systematically
ABOVE `initial_mean_price` (+1.5c on average, same legs). So the incumbent metric silently
swaps in a MORE EXPENSIVE price source for a GROWING share of legs as the window advances.

That means a downward drift in the incumbent series is CONFOUNDED with capture coverage
by construction. Any honest time-comparison must hold the price basis fixed.

Bases offered here:
  imp   : initial_mean_price for every leg, every day.  100% coverage on all 16 days.
          The ONLY basis with a stationary source mix -> the basis for all time-comparisons.
  ask   : entry_ask where present (else drop the leg). Consistent SOURCE, but the captured
          SUBSET's composition swings 5%->70%, so cross-time comparisons on it are unsound.
          Kept for level-calibration only, never for trend.
  coal  : COALESCE(entry_ask, initial_mean_price) -- the INCUMBENT, contaminated basis.
          Reproduced only to demonstrate the artifact.

Nothing here writes to the DB.
"""

import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import superkey  # noqa: E402

BAND_LO, BAND_HI = 0.71, 0.98
FEE = lambda p: 0.03 * p * (1.0 - p)  # noqa: E731  -- corrected spread/fee, frozen

_SQL = """
COPY (
  SELECT strategy,
         condition_id,
         coalesce(event_slug,'') AS event_slug,
         coalesce(slug,'')       AS slug,
         coalesce(title,'')      AS title,
         first_detected_at::date AS d,
         initial_mean_price,
         entry_ask,
         resolved,
         outcome_won,
         net_count,
         n_backers
  FROM consensus_signals
  WHERE strategy IN ('favorite','_blind')
    AND initial_mean_price IS NOT NULL
) TO STDOUT WITH (FORMAT csv, HEADER true)
"""


def fetch():
    """Read-only pull of favorite + _blind legs. Returns list of dicts."""
    out = subprocess.run(
        ["docker", "exec", "-i", "polymarket-bot-postgres-1",
         "psql", "-U", "bot", "-d", "polymarket", "-c", _SQL],
        capture_output=True, text=True, check=True,
    ).stdout
    import csv
    import io
    rows = []
    for r in csv.DictReader(io.StringIO(out)):
        rows.append({
            "strategy": r["strategy"],
            "condition_id": r["condition_id"],
            "event_slug": r["event_slug"],
            "slug": r["slug"],
            "title": r["title"],
            "d": r["d"],
            "imp": float(r["initial_mean_price"]),
            "ask": float(r["entry_ask"]) if r["entry_ask"] else None,
            "resolved": r["resolved"] == "t",
            "won": (r["outcome_won"] == "t") if r["outcome_won"] else None,
            "net_count": int(r["net_count"]) if r["net_count"] else 0,
            "n_backers": int(r["n_backers"]) if r["n_backers"] else 0,
        })
    return rows


def price(r, basis):
    """Entry price for leg r under the named basis. None => leg not usable on this basis."""
    if basis == "imp":
        return r["imp"]
    if basis == "ask":
        return r["ask"]
    if basis == "coal":
        return r["ask"] if r["ask"] is not None else r["imp"]
    raise ValueError(f"unknown basis {basis!r}")


def legs(rows, strategy="favorite", basis="imp", lo=BAND_LO, hi=BAND_HI, resolved_only=True):
    """Band-filtered, priced legs. Band membership uses the SAME basis as the P&L
    (mixing them is how the incumbent metric leaks capture coverage into band membership)."""
    out = []
    for r in rows:
        if r["strategy"] != strategy:
            continue
        p = price(r, basis)
        if p is None or not (lo <= p <= hi):
            continue
        if resolved_only and (not r["resolved"] or r["won"] is None):
            continue
        out.append({**r, "p": p, "key": superkey.super_event(r["event_slug"], r["slug"]) or r["condition_id"]})
    return out


def pnl(leg):
    """Flat-SHARES P&L per share and turnover per share. ROI-on-turnover = sum(pnl)/sum(turn)."""
    p = leg["p"]
    gross = (1.0 - p) if leg["won"] else (-p)
    return gross - FEE(p), p


def match_roi(ls):
    """Cluster legs to the MATCH (superkey) -> {key: (pnl, turnover)}. The unit of risk."""
    agg = defaultdict(lambda: [0.0, 0.0])
    for l in ls:
        g, t = pnl(l)
        agg[l["key"]][0] += g
        agg[l["key"]][1] += t
    return {k: (v[0], v[1]) for k, v in agg.items()}


def roi_on_turnover(ls):
    m = match_roi(ls)
    tp = sum(v[0] for v in m.values())
    tt = sum(v[1] for v in m.values())
    return (tp / tt if tt else 0.0), len(m), tt


def match_day(ls):
    """{superkey: earliest day} -- a match belongs to the day it first fired."""
    out = {}
    for l in ls:
        k = l["key"]
        if k not in out or l["d"] < out[k]:
            out[k] = l["d"]
    return out


def blind_edge_by_band(rows, basis="imp", nbands=5):
    """Structural (belief-blind) edge per price band from the _blind arm, same basis.
    Skill = favorite ROI - blind ROI at the same band mix."""
    agg = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        if r["strategy"] != "_blind" or not r["resolved"] or r["won"] is None:
            continue
        p = price(r, basis)
        if p is None or not (0.0 < p < 1.0):
            continue
        b = min(int(p * nbands), nbands - 1)
        g = (1.0 - p) if r["won"] else (-p)
        agg[b][0] += g - FEE(p)
        agg[b][1] += p
    return {b: (v[0] / v[1] if v[1] else 0.0) for b, v in agg.items()}, nbands


def blind_expected(ls, blind, nbands):
    """Turnover-weighted blind ROI for the SAME band mix as `ls` -> the belief-blind baseline."""
    num = den = 0.0
    for l in ls:
        b = min(int(l["p"] * nbands), nbands - 1)
        e = blind.get(b, 0.0)
        num += e * l["p"]
        den += l["p"]
    return (num / den) if den else 0.0
