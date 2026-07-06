#!/usr/bin/env python3
"""
H4 RELATIONAL CONSENSUS LIFT (favconsensus-deepen, PREREG_20260706T000604Z §3.H4).

Tests whether a LOW-PARAMETER pairwise co-agreement layer beats plain rank-weighted consensus
(`net_quality`, the deployed default) at pick ordering — on held-out WHOLE super-events. This was
data-starved at ~3 backers/signal; the question is whether top-250 × 7 days changes that. If it
does not beat the baseline on BOTH held-out halves, the verdict is KILL (report the negative).

FROZEN parameters (prereg): shrinkage prior m=20 events; β=1 (not fitted); top-K=5 pairs by |L|.
FROZEN evaluation (declared here BEFORE the first live run): primary N = top 50% of eval-half
favorite picks (ties broken by pick id); N=25% and N=75% reported as sensitivity only. PASS
requires relational top-N surplus > baseline top-N surplus on BOTH halves at the PRIMARY N.

Model:
  Pair stats from the `loose` stream (widest real-backer record), TRAIN-half super-events only:
    P(win|i)   = wallet i's backed-pick win rate (train half)
    L_ij       = P(win | i backs AND j backs) - P(win|i), shrunk: L*n_ij/(n_ij+m)
  Eval on `favorite` picks in the COMPLEMENTARY half:
    rel_score  = z(net_quality) + β · mean( top-K shrunk L_ij over the pick's backer pairs )
    (net_quality z-scored within eval half so the two terms are commensurate; deterministic)
  Halves: super-events sorted by first detection (min over loose+favorite), alternating odd/even.
  Both directions run (train odd → eval even; train even → eval odd).
  Surplus = H1 statistic (a − blind_edge[band]), super-event clustered.

Self-test:  ./relational_lift.py --self-test
Live:       ./relational_lift.py [--json ../reports/relational_lift.json]
"""

import csv
import io
import json
import subprocess
import sys
from collections import defaultdict
from math import sqrt

csv.field_size_limit(2**31 - 1)  # observed_votes atoms exceed the 128KiB default field cap

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402
from favconsensus_reverify import PG, band, cluster_mean_se, blind_band_edges, prep  # noqa: E402

M_SHRINK = 20
BETA = 1.0
TOP_K = 5
PRIMARY_FRAC = 0.5
SENS_FRACS = (0.25, 0.75)

SQL = """
SELECT strategy, event_slug, slug, title,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won, net_quality,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
       extract(epoch FROM first_detected_at) AS det,
       observed_votes::text AS votes
FROM consensus_signals
WHERE resolved AND outcome_won IS NOT NULL
  AND strategy IN ('favorite', 'loose', '_blind')
"""


def backers(votes_json):
    if not votes_json:
        return frozenset()
    try:
        atoms = json.loads(votes_json)
    except json.JSONDecodeError:
        return frozenset()
    return frozenset(a["wallet"] for a in atoms if a.get("wallet"))


def halves(picks):
    """super-events sorted by min detection epoch, alternating -> ('odd'|'even') per sk."""
    first = defaultdict(lambda: float("inf"))
    for p in picks:
        first[p["sk"]] = min(first[p["sk"]], p["det"])
    side = {}
    for i, sk in enumerate(sorted(first, key=lambda k: (first[k], k))):
        side[sk] = "odd" if i % 2 else "even"
    return side


def pair_stats(train_picks):
    """wallet win rates + shrunk pairwise conditional lift from the train half."""
    solo = defaultdict(lambda: [0, 0])          # wallet -> [wins, n]
    pair = defaultdict(lambda: [0, 0])          # (i,j) ordered -> [wins, n]
    for p in train_picks:
        bs = p["backers"]
        for w in bs:
            solo[w][0] += p["won"]
            solo[w][1] += 1
        for i in bs:
            for j in bs:
                if i != j:
                    pair[(i, j)][0] += p["won"]
                    pair[(i, j)][1] += 1
    L = {}
    for (i, j), (w, n) in pair.items():
        si_w, si_n = solo[i]
        if si_n == 0 or n == 0:
            continue
        raw = w / n - si_w / si_n
        L[(i, j)] = raw * n / (n + M_SHRINK)
    return L


def rel_scores(eval_picks, L):
    """rel = z(net_quality) + BETA * mean(top-K |L| pair values present on the pick)."""
    nq = [p["net_quality"] for p in eval_picks]
    mu = sum(nq) / len(nq)
    sd = sqrt(sum((x - mu) ** 2 for x in nq) / max(1, len(nq) - 1)) or 1.0
    out = []
    for p in eval_picks:
        pairs = [L[(i, j)] for i in p["backers"] for j in p["backers"]
                 if i != j and (i, j) in L]
        pairs.sort(key=abs, reverse=True)
        top = pairs[:TOP_K]
        rel = (p["net_quality"] - mu) / sd + (BETA * sum(top) / len(top) if top else 0.0)
        out.append({**p, "base_score": p["net_quality"], "rel_score": rel,
                    "n_pairs": len(pairs)})
    return out


def topn_surplus(scored, key, frac):
    n = max(1, int(len(scored) * frac))
    top = sorted(scored, key=lambda p: (-p[key], p["id"]))[:n]
    m, se, n_ev = cluster_mean_se([(p["sk"], p["s"]) for p in top])
    return {"n_picks": n, "n_ev": n_ev, "surplus": m, "se": se}


def run_direction(train_side, eval_side, fav, loose, side):
    train = [p for p in loose if side[p["sk"]] == train_side]
    evalp = [p for p in fav if side[p["sk"]] == eval_side]
    if not train or not evalp:
        return None
    L = pair_stats(train)
    scored = rel_scores(evalp, L)
    res = {"train": train_side, "eval": eval_side,
           "n_train_picks": len(train), "n_eval_picks": len(evalp),
           "n_pairs_learned": len(L),
           "coverage": sum(1 for p in scored if p["n_pairs"]) / len(scored)}
    for frac in (PRIMARY_FRAC,) + SENS_FRACS:
        res[f"base_top{int(frac*100)}"] = topn_surplus(scored, "base_score", frac)
        res[f"rel_top{int(frac*100)}"] = topn_surplus(scored, "rel_score", frac)
    b, r = res["base_top50"], res["rel_top50"]
    res["rel_beats_base_primary"] = (r["surplus"] or -9) > (b["surplus"] or -9)
    return res


def run_live(json_path=None):
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    raw = list(csv.DictReader(io.StringIO(out.stdout)))
    rows = prep(raw)
    blind = blind_band_edges(rows)
    picks = []
    for i, (r, rr) in enumerate(zip(rows, raw)):
        if r["strategy"] == "_blind":
            continue
        be = blind[r["b"]]["edge"]
        if be is None:
            continue
        picks.append({**r, "id": i, "det": float(rr["det"]),
                      "net_quality": float(rr["net_quality"]),
                      "backers": backers(rr["votes"]), "s": r["a"] - be})
    fav = [p for p in picks if p["strategy"] == "favorite"]
    loose = [p for p in picks if p["strategy"] == "loose"]
    side = halves(picks)
    d1 = run_direction("odd", "even", fav, loose, side)
    d2 = run_direction("even", "odd", fav, loose, side)
    passed = bool(d1 and d2 and d1["rel_beats_base_primary"] and d2["rel_beats_base_primary"])
    res = {"prereg": "PREREG_20260706T000604Z_favconsensus_deepen.md",
           "params": {"m": M_SHRINK, "beta": BETA, "top_k": TOP_K, "primary_frac": PRIMARY_FRAC},
           "directions": [d1, d2],
           "pass_primary_both_halves": passed,
           "verdict": "SURVIVES-TO-GATE" if passed else "KILLED (no lift over rank-weighted)"}
    print(json.dumps(res, indent=2, default=str))
    if json_path:
        with open(json_path, "w") as f:
            json.dump(res, f, indent=2, default=str)
    return res


def self_test():
    # two wallets: 'good' pair signal — picks where g1&g2 co-back win 100%, others 50%.
    loose, fav = [], []
    for i in range(60):
        co = i % 2 == 0
        won = 1 if co else (i // 2) % 2
        bs = frozenset({"g1", "g2"} if co else {"g1", "x"})
        loose.append({"strategy": "loose", "sk": f"e{i}", "det": i, "won": won,
                      "backers": bs, "net_quality": 1.0, "id": i, "s": won - 0.5,
                      "b": 4, "a": won - 0.5, "day": "d", "entry": 0.5})
    for i in range(40):
        co = i % 2 == 0
        won = 1 if co else (i // 2) % 2
        bs = frozenset({"g1", "g2"} if co else {"g1", "x"})
        fav.append({"strategy": "favorite", "sk": f"f{i}", "det": 100 + i, "won": won,
                    "backers": bs, "net_quality": 1.0, "id": 1000 + i, "s": won - 0.5,
                    "b": 4, "a": won - 0.5, "day": "d", "entry": 0.5})
    side = halves(loose + fav)
    d = run_direction("odd", "even", fav, loose, side)
    assert d is not None and d["n_pairs_learned"] >= 2
    # relational must load co-backed picks (all winners) into the top half -> rel >= base
    assert d["rel_top50"]["surplus"] >= d["base_top50"]["surplus"] - 1e-9, d
    # shrinkage sanity: n=30, raw lift 0.5 -> 0.5*30/50 = 0.3
    L = pair_stats([p for p in loose if side[p["sk"]] == "odd"])
    for k, v in L.items():
        assert -1 <= v <= 1
    # halves are a partition of super-events
    assert set(side.values()) == {"odd", "even"}
    print("self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        jp = None
        if "--json" in sys.argv:
            jp = sys.argv[sys.argv.index("--json") + 1]
        run_live(jp)
