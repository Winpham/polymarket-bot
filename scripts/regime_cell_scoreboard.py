#!/usr/bin/env python3
"""
H2 REGIME CELL SCOREBOARD + ABSTENTION (favconsensus-deepen, PREREG_20260706T000604Z §3.H2).

The reliability fix is SUPPLY, not thresholds: score every (sport-category × band{4,5} ×
time-block{A,B}) cell of the `favorite` stream with the full frozen gate, so accrual can be
steered at the cells that are close. Per cell:

  surplus-over-blind (super-event clustered)  +  Bonferroni LB over the counted family
  (= cells with >=10 graded super-events)     +  per-cell selection-matched permutation null
  (draws from _blind matched to the cell's band×day profile, N_PERM=2000, seed 20260706)
  +  events-needed: n* s.t. surplus - z·sd/sqrt(n*) = MARGIN (accrual distance, same sd).

ABSTENTION (frozen in prereg — no variants scored):
  (a) bands 1-3 (favorite never fires there — vacuous, reported),
  (b) map-state v002 DODGE overlap: mlb×deriv×band4 picks,
  (c) any sport-category with <10 graded favorite super-events.
Judged ONLY by Δ(pooled LB) and Δ(fraction of positive UTC days), abstained vs full.

Self-test:  ./regime_cell_scoreboard.py --self-test
Live:       ./regime_cell_scoreboard.py [--json ../reports/regime_cell_scoreboard.json]
"""

import csv
import io
import json
import random
import subprocess
import sys
from collections import defaultdict
from math import ceil, sqrt
from statistics import NormalDist

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402
from market_taxonomy import category, market_type  # noqa: E402
from favconsensus_reverify import (  # noqa: E402
    PG, band, cluster_mean_se, blind_band_edges, prep, surplus_rows, BLOCK_SPLIT)

SEED = 20260706
N_PERM = 2000
ALPHA = 0.05
MARGIN = 0.03
FLOOR = 30
MIN_CELL = 10

SQL = """
SELECT strategy, event_slug, slug, title,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day
FROM consensus_signals
WHERE resolved AND outcome_won IS NOT NULL
  AND strategy IN ('favorite', '_blind')
"""


def cell_key(r):
    blk = "A" if r["day"] < BLOCK_SPLIT else "B"
    return (r["cat"], r["b"], blk)


def perm_null(cell_rows, blind_rows, blind_edges, n_perm=N_PERM, rng=None):
    """One-sided p: fraction of matched random _blind selections with surplus >= observed."""
    rng = rng or random.Random(SEED)
    pool = defaultdict(list)          # (band, day) -> blind rows
    for r in blind_rows:
        pool[(r["b"], r["day"])].append(r)
    profile = [(r["b"], r["day"]) for r in cell_rows]
    if any(not pool[k] for k in profile):
        return None, 0
    obs_ev = defaultdict(list)
    for r in cell_rows:
        obs_ev[r["sk"]].append(r["a"] - blind_edges[r["b"]]["edge"])
    obs = _evmean(obs_ev)
    ge = 0
    valid = 0
    for _ in range(n_perm):
        ev = defaultdict(list)
        for k in profile:
            d = rng.choice(pool[k])
            ev[d["sk"]].append(d["a"] - blind_edges[d["b"]]["edge"])
        m = _evmean(ev)
        valid += 1
        if m >= obs:
            ge += 1
    return (ge + 1) / (valid + 1), valid


def _evmean(evdict):
    means = [sum(v) / len(v) for v in evdict.values()]
    return sum(means) / len(means)


def score_cells(sr, blind_rows, blind_edges, rng):
    cells = defaultdict(list)
    for r in sr:
        cells[cell_key(r)].append(r)
    counted = {k: v for k, v in cells.items() if len({r["sk"] for r in v}) >= MIN_CELL}
    k_bonf = max(1, len(counted))
    z = NormalDist().inv_cdf(1 - ALPHA / k_bonf)
    out = []
    for k, rows_ in sorted(cells.items()):
        m, se, n_ev = cluster_mean_se([(r["sk"], r["s"]) for r in rows_])
        entry = {"cell": f"{k[0]}|band{k[1]}|{k[2]}", "n_rows": len(rows_), "n_ev": n_ev,
                 "surplus": m, "se": se, "counted": k in counted}
        if k in counted and se is not None:
            sd = se * sqrt(n_ev)
            entry["lb"] = m - z * se
            entry["p_perm"] = perm_null(rows_, blind_rows, blind_edges, rng=rng)[0]
            entry["events_needed_margin"] = (
                None if m <= MARGIN else max(FLOOR, ceil((z * sd / (m - MARGIN)) ** 2)))
            gates = {
                "lb_gt_margin": entry["lb"] is not None and entry["lb"] > MARGIN,
                "floor_30": n_ev >= FLOOR,
                "null_p": entry["p_perm"] is not None and entry["p_perm"] <= 0.01,
            }
            entry["gates"] = gates
            entry["verdict"] = ("CERTIFIED-CELL" if all(gates.values())
                                else ("INDETERMINATE-BY-POWER" if m > 0 else "NEGATIVE"))
        out.append(entry)
    return out, k_bonf


def abstention_read(sr):
    """Frozen rule: drop mlb×deriv×band4 picks + cats with <10 favorite super-events."""
    cat_ev = defaultdict(set)
    for r in sr:
        cat_ev[r["cat"]].add(r["sk"])
    thin = {c for c, s in cat_ev.items() if len(s) < MIN_CELL}
    kept = [r for r in sr
            if r["cat"] not in thin
            and not (r["cat"] == "mlb" and r["mtype"] == "deriv" and r["b"] == 4)]
    def read(rows_):
        m, se, n_ev = cluster_mean_se([(r["sk"], r["s"]) for r in rows_])
        z = NormalDist().inv_cdf(1 - ALPHA / 2)  # single pooled comparison, two variants reported
        day = defaultdict(list)
        for r in rows_:
            day[r["day"]].append(r["s"])
        pos_days = sum(1 for v in day.values() if sum(v) / len(v) > 0)
        return {"n_ev": n_ev, "surplus": m, "lb": None if se is None else m - z * se,
                "pos_days": pos_days, "n_days": len(day)}
    return {"abstained_cats": sorted(thin), "full": read(sr), "abstain": read(kept)}


def run_live(json_path=None):
    rng = random.Random(SEED)
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = prep(list(csv.DictReader(io.StringIO(out.stdout))))
    # attach market_type (needed for the DODGE overlap) — re-query titles kept in prep? prep drops
    # slug/title; recompute here from the raw csv instead.
    out2 = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    raw = list(csv.DictReader(io.StringIO(out2.stdout)))
    for r, rr in zip(rows, raw):
        r["mtype"] = market_type(rr.get("slug") or "", rr.get("title") or "") or "?"
    blind_rows = [r for r in rows if r["strategy"] == "_blind"]
    blind = blind_band_edges(rows)
    sr = surplus_rows(rows, blind)

    cells, k_bonf = score_cells(sr, blind_rows, blind, rng)
    res = {"prereg": "PREREG_20260706T000604Z_favconsensus_deepen.md",
           "k_bonferroni_cells": k_bonf, "cells": cells,
           "abstention": abstention_read(sr)}
    print(json.dumps(res, indent=2, default=str))
    if json_path:
        with open(json_path, "w") as f:
            json.dump(res, f, indent=2, default=str)
    return res


def self_test():
    rng = random.Random(1)
    # two cells, one strong (should clear), one weak
    sr, blind_rows = [], []
    for i in range(80):
        day = f"2026-07-{(i % 4) + 1:02d}"
        blind_rows.append({"strategy": "_blind", "entry": 0.7, "won": i % 10 < 7,
                           "a": (1 if i % 10 < 7 else 0) - 0.7, "b": 4, "day": day,
                           "sk": f"b{i}", "cat": "mlb", "mtype": "main"})
    blind = {4: {"edge": 0.0, "n_ev": 80}}
    for i in range(40):
        day = f"2026-07-{(i % 4) + 1:02d}"
        won = i % 10 < 9
        sr.append({"entry": 0.7, "won": won, "a": (1 if won else 0) - 0.7, "b": 4,
                   "day": day, "sk": f"s{i}", "cat": "mlb", "mtype": "main",
                   "s": (1 if won else 0) - 0.7})
    cells, k = score_cells(sr, blind_rows, blind, rng)
    counted = [c for c in cells if c["counted"]]
    assert len(counted) == 2, [c["cell"] for c in cells]  # A and B blocks
    assert all(c["surplus"] > 0.15 for c in counted), counted
    ab = abstention_read(sr)
    assert ab["full"]["n_ev"] == 40 and ab["abstain"]["n_ev"] == 40  # nothing to drop
    # thin-cat drop
    sr2 = sr + [dict(sr[0], cat="nhl", sk="x1")]
    ab2 = abstention_read(sr2)
    assert "nhl" in ab2["abstained_cats"] and ab2["abstain"]["n_ev"] == 40
    print("self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        jp = None
        if "--json" in sys.argv:
            jp = sys.argv[sys.argv.index("--json") + 1]
        run_live(jp)
