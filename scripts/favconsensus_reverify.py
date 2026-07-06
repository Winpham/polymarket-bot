#!/usr/bin/env python3
"""
H1 CORE RE-VERIFY (favconsensus-deepen run, PREREG_20260706T000604Z §3.H1).

Re-measures the four seed claims of REFINED-STRATEGY.md on the FULL graded record
(7 days, top-250 universe) with the shipped statistic — no new modeling:

  H1.1 favorite surplus-over-blind > 0            (pooled, super-event clustered, Bonferroni k=4)
  H1.2 band decomposition                          (0.6-0.8 premium vs 0.8-1.0 — the sweet spot)
  H1.3 longshot block                              (consensus <0.45 entry surplus <= 0)
  H1.4 flat-SHARES vs flat-$ P&L sign              ($100-flat vs 100-share, full graded record)

Statistic identical to consensus.rs scoreboard / selection_null.py / adversarial_battery.py:
  a = won - entry, entry = COALESCE(initial_mean_price, mean_price)
  surplus = a - blind_edge[band] (5x0.2 bands, _blind event-clustered band means)
  cluster key = superkey.super_event (match level); SEs at super-event AND UTC-day grain.
Splits: sport-category (market_taxonomy.category) and frozen time blocks
  A = day <= 2026-07-01, B = day >= 2026-07-02.

Self-test:  ./favconsensus_reverify.py --self-test   (synthetic fixture; exits non-zero on fail)
Live:       ./favconsensus_reverify.py [--json reports/favconsensus_reverify.json]
"""

import csv
import io
import json
import subprocess
import sys
from collections import defaultdict
from math import sqrt
from statistics import NormalDist

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402
from market_taxonomy import category  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
K_BONF = 4            # H1 family size (prereg §3.H1)
ALPHA = 0.05
BLOCK_SPLIT = "2026-07-02"   # frozen: A = day < split, B = day >= split
LONGSHOT_MAX = 0.45

SQL = """
SELECT strategy, event_slug, slug, title,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day
FROM consensus_signals
WHERE resolved AND outcome_won IS NOT NULL
  AND strategy IN ('favorite', '_blind')
"""


def band(p):
    if p < 0:
        return 1
    if p >= 1:
        return 5
    return int(p * 5) + 1


def cluster_mean_se(pairs):
    """pairs = [(cluster_key, value)] -> (mean, se, n_clusters) clustering to key means first."""
    ev = defaultdict(list)
    for k, v in pairs:
        ev[k].append(v)
    means = [sum(v) / len(v) for v in ev.values()]
    n = len(means)
    if n == 0:
        return None, None, 0
    m = sum(means) / n
    if n == 1:
        return m, None, 1
    var = sum((x - m) ** 2 for x in means) / (n - 1)
    return m, sqrt(var / n), n


def blind_band_edges(rows):
    """band -> event-clustered mean of a over _blind picks (the matched baseline)."""
    out = {}
    for b in range(1, 6):
        pairs = [(r["sk"], r["a"]) for r in rows if r["strategy"] == "_blind" and r["b"] == b]
        m, _, n = cluster_mean_se(pairs)
        out[b] = {"edge": m, "n_ev": n}
    return out


def lb(mean, se, k=K_BONF):
    if mean is None or se is None:
        return None
    z = NormalDist().inv_cdf(1 - ALPHA / k)
    return mean - z * se


def prep(raw):
    rows = []
    for r in raw:
        entry = float(r["entry"])
        rows.append({
            "strategy": r["strategy"],
            "entry": entry,
            "won": int(r["won"]),
            "a": int(r["won"]) - entry,
            "b": band(entry),
            "day": r["day"],
            "sk": super_event(r.get("event_slug"), r.get("slug")),
            "cat": category(r.get("slug") or "", r.get("title") or ""),
        })
    return rows


def surplus_rows(rows, blind):
    out = []
    for r in rows:
        if r["strategy"] != "favorite":
            continue
        be = blind[r["b"]]["edge"]
        if be is None:
            continue
        out.append({**r, "s": r["a"] - be})
    return out


def stat_block(sr, label):
    ev = cluster_mean_se([(r["sk"], r["s"]) for r in sr])
    dy = cluster_mean_se([(r["day"], r["s"]) for r in sr])
    return {
        "label": label, "n_rows": len(sr),
        "surplus_ev": ev[0], "se_ev": ev[1], "n_ev": ev[2], "lb_ev": lb(ev[0], ev[1]),
        "surplus_day": dy[0], "se_day": dy[1], "n_day": dy[2], "lb_day": lb(dy[0], dy[1]),
    }


def pnl_sizing(rows):
    """H1.4: favorite picks, $100 flat-dollar vs 100-share flat-shares, at at-fire entry."""
    fd = fs = 0.0
    for r in rows:
        if r["strategy"] != "favorite":
            continue
        if r["entry"] <= 0 or r["entry"] >= 1:
            continue
        fd += 100.0 * (r["won"] / r["entry"] - 1.0)          # $100 buys 100/entry shares
        fs += 100.0 * (r["won"] - r["entry"])                # 100 shares cost 100*entry
    return {"flat_dollar_pnl": round(fd, 2), "flat_shares_pnl": round(fs, 2)}


def run_live(json_path=None):
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = prep(list(csv.DictReader(io.StringIO(out.stdout))))
    blind = blind_band_edges(rows)
    sr = surplus_rows(rows, blind)

    res = {"prereg": "PREREG_20260706T000604Z_favconsensus_deepen.md", "k_bonferroni": K_BONF,
           "blind_band_edges": blind}

    # H1.1 pooled + H1.2 per band
    res["H1_1_pooled"] = stat_block(sr, "favorite pooled")
    res["H1_2_bands"] = {b: stat_block([r for r in sr if r["b"] == b], f"band{b}")
                         for b in sorted({r["b"] for r in sr})}
    # H1.3 longshots (<0.45 at-fire entry)
    res["H1_3_longshot"] = stat_block([r for r in sr if r["entry"] < LONGSHOT_MAX],
                                      "favorite <0.45 entry")
    # H1.4 sizing sign
    res["H1_4_sizing"] = pnl_sizing(rows)
    # splits: sport-category and frozen time blocks (context for gate 5)
    res["by_category"] = {c: stat_block([r for r in sr if r["cat"] == c], c)
                          for c in sorted({r["cat"] for r in sr})}
    res["by_block"] = {
        "A_le_0701": stat_block([r for r in sr if r["day"] < BLOCK_SPLIT], "block A"),
        "B_ge_0702": stat_block([r for r in sr if r["day"] >= BLOCK_SPLIT], "block B"),
    }

    print(json.dumps(res, indent=2, default=str))
    if json_path:
        with open(json_path, "w") as f:
            json.dump(res, f, indent=2, default=str)
    return res


def self_test():
    # synthetic: blind band-4 edge 0, favorite wins 80% at entry 0.7 -> surplus ~ +0.1
    raw = []
    for i in range(50):
        raw.append({"strategy": "_blind", "event_slug": f"ev-b-{i}", "slug": f"ev-b-{i}",
                    "title": "x", "entry": "0.7", "won": str(int(i % 10 < 7)),
                    "day": f"2026-07-{(i % 5) + 1:02d}"})
    for i in range(40):
        raw.append({"strategy": "favorite", "event_slug": f"ev-f-{i}", "slug": f"ev-f-{i}",
                    "title": "x", "entry": "0.7", "won": str(int(i % 10 < 8)),
                    "day": f"2026-07-{(i % 5) + 1:02d}"})
    rows = prep(raw)
    blind = blind_band_edges(rows)
    assert abs(blind[4]["edge"] - 0.0) < 1e-9, blind[4]
    sr = surplus_rows(rows, blind)
    st = stat_block(sr, "t")
    assert abs(st["surplus_ev"] - 0.10) < 1e-9, st
    assert st["n_ev"] == 40
    pnl = pnl_sizing(rows)
    # flat-shares: 100*(0.8-0.7)*40 = +400 ; flat-$: 100*(0.8/0.7-1)*40 ~ +571
    assert abs(pnl["flat_shares_pnl"] - 400.0) < 1e-6, pnl
    assert abs(pnl["flat_dollar_pnl"] - 571.43) < 0.5, pnl
    # cluster collapse: duplicate rows in one super-event must not inflate n_ev
    m, se, n = cluster_mean_se([("e1", 1.0), ("e1", 0.0), ("e2", 0.5)])
    assert n == 2 and abs(m - 0.5) < 1e-9
    print("self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        jp = None
        if "--json" in sys.argv:
            jp = sys.argv[sys.argv.index("--json") + 1]
        run_live(jp)
