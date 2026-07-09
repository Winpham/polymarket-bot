#!/usr/bin/env python3
"""
EDGE-REFINEMENT SEARCH (harden-edge, P3) — is there a SUB-REGION of the favorite arm that beats the
champion under the belief-blind gate, OUT-OF-SAMPLE? Each candidate is a CHALLENGER = the favorite
picks filtered by ONE feature axis (price sub-band, freshness, book-depth, backer-quality) or a 2-way
combo. Every candidate is scored with the EXACT belief-blind machinery of selection_null.py (imported,
not re-implemented): event-clustered surplus over the band-matched `_blind` baseline, a (band×day)-
matched permutation null → p_emp, z, one-sided 95% LB, and the per-regime surplus for the
≥2-disjoint-non-soccer-regime rule.

A candidate CLEARS the belief-blind gate iff: p_emp ≤ 0.01 AND LB > +3% AND ≥2 non-soccer regimes > 0.
That is NECESSARY, not sufficient — adoption ALSO needs beats-champion-on-realizable + an independent
skeptic pass (§3). This harness reports the belief-blind screen + a Bonferroni multiplicity guard; the
anti-goal-seeking mandate says MOST candidates SHOULD fail — that is the screen working, not the run
failing. It ADOPTS NOTHING.

Read-only, paper-only. DB via the same docker-exec path as selection_null.py.
  ./edge_refine_search.py            # score every candidate; writes reports/edge_refine_search.json
"""
import io
import csv
import json
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn  # reuse band(), regime(), clustered_surplus(), null_pvalue(), PG, SEED

MARGIN = 0.03
P_BAR = 0.01
Z_LB = 1.64  # one-sided 95%
N_PERM = 2000

# favorite universe with the refinement features (mirror selection_null's ev/entry/won/day exactly)
FAV_SQL = """
SELECT COALESCE(event_slug, condition_id) AS ev, event_slug,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
       initial_recency_mins AS rec, initial_total_usd AS usd,
       initial_net_count AS netc, initial_best_backer_rank AS rank,
       initial_price_std AS pstd
FROM consensus_signals
WHERE resolved AND strategy='favorite' AND COALESCE(initial_mean_price, mean_price) BETWEEN 0.65 AND 0.98;
"""


def fetch_fav():
    out = subprocess.run(sn.PG + ["-c", FAV_SQL], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["entry"] = float(r["entry"]); r["won"] = int(r["won"])
        for k in ("rec", "usd", "netc", "rank", "pstd"):
            r[k] = float(r[k]) if r[k] not in ("", None) else None
        rows.append(r)
    return rows


def score(subset, blind_cells, blind_edge, rng):
    """Return the belief-blind read for a favorite subset (list of fav rows)."""
    picks = [(r["ev"], sn.band(r["entry"]), r["won"] - r["entry"]) for r in subset]
    obs, n_ev = sn.clustered_surplus(picks, blind_edge)
    if n_ev < 10:
        return {"n_ev": n_ev, "obs": obs, "readable": False}
    meta = [(sn.band(r["entry"]), r["day"]) for r in subset]
    draws = sn.null_pvalue(meta, blind_cells, blind_edge, rng, N_PERM)
    if len(draws) < 1000:
        return {"n_ev": n_ev, "obs": obs, "readable": False, "note": "null unmatchable"}
    mu = sum(draws) / len(draws)
    sd = (sum((x - mu) ** 2 for x in draws) / len(draws)) ** 0.5
    z = (obs - mu) / sd if sd > 0 else 0.0
    p = sum(1 for x in draws if x >= obs) / len(draws)
    lb = obs - Z_LB * sd
    # per-regime surplus for the >=2-non-soccer rule
    reg = {}
    for r in subset:
        rg = sn.regime(r["event_slug"])
        reg.setdefault(rg, []).append((r["ev"], sn.band(r["entry"]), r["won"] - r["entry"]))
    reg_surplus = {}
    for rg, ps in reg.items():
        s, ne = sn.clustered_surplus(ps, blind_edge)
        reg_surplus[rg] = (round(s, 4), ne)
    non_soccer_pos = sum(1 for rg, (s, ne) in reg_surplus.items()
                         if rg != "soccer" and ne >= 3 and s > 0)
    gate = (p <= P_BAR and lb > MARGIN and non_soccer_pos >= 2)
    return {"n_ev": n_ev, "obs": round(obs, 4), "null_mu": round(mu, 4), "null_sd": round(sd, 4),
            "z": round(z, 2), "p_emp": round(p, 4), "lb": round(lb, 4),
            "non_soccer_pos": non_soccer_pos, "regimes": reg_surplus,
            "belief_blind_gate": gate, "readable": True}


def main():
    rng = random.Random(sn.SEED)
    allrows = sn.fetch()
    blind = [r for r in allrows if r["strategy"] == "_blind"]
    from collections import defaultdict
    blind_cells = defaultdict(list); blind_band = defaultdict(list)
    for r in blind:
        b = sn.band(r["entry"]); a = r["won"] - r["entry"]
        blind_cells[(b, r["day"])].append((r["ev"], a)); blind_band[b].append(a)
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}

    fav = fetch_fav()
    withfeat = [r for r in fav if r["usd"] is not None]  # 208-row capture-era subset
    med_usd = sorted(r["usd"] for r in withfeat)[len(withfeat) // 2] if withfeat else 0
    p75_usd = sorted(r["usd"] for r in withfeat)[int(len(withfeat) * .75)] if withfeat else 0

    C = {
        "CHAMPION favorite (all)": fav,
        "band 0.65-0.80": [r for r in fav if r["entry"] < 0.80],
        "band 0.80-0.90": [r for r in fav if 0.80 <= r["entry"] < 0.90],
        "band 0.90-0.98": [r for r in fav if r["entry"] >= 0.90],
        "band 0.70-0.95": [r for r in fav if 0.70 <= r["entry"] <= 0.95],
        "band 0.75-0.98": [r for r in fav if r["entry"] >= 0.75],
        "fresh <=180m": [r for r in withfeat if r["rec"] is not None and r["rec"] <= 180],
        "fresh <=60m": [r for r in withfeat if r["rec"] is not None and r["rec"] <= 60],
        "fresh <=5m": [r for r in withfeat if r["rec"] is not None and r["rec"] <= 5],
        "depth > median": [r for r in withfeat if r["usd"] > med_usd],
        "depth > p75": [r for r in withfeat if r["usd"] > p75_usd],
        "netcount >=5": [r for r in fav if r["netc"] is not None and r["netc"] >= 5],
        "netcount >=6": [r for r in fav if r["netc"] is not None and r["netc"] >= 6],
        "elite rank <=10": [r for r in withfeat if r["rank"] is not None and r["rank"] <= 10],
        "elite rank <=3": [r for r in withfeat if r["rank"] is not None and r["rank"] <= 3],
        "tight pstd <=0.05": [r for r in withfeat if r["pstd"] is not None and r["pstd"] <= 0.05],
        "fresh<=180 & depth>med": [r for r in withfeat if r["rec"] is not None and r["rec"] <= 180 and r["usd"] > med_usd],
        "band0.80-0.98 & netc>=5": [r for r in fav if r["entry"] >= 0.80 and r["netc"] is not None and r["netc"] >= 5],
    }

    print(f"EDGE-REFINEMENT SEARCH · {N_PERM} draws · seed {sn.SEED} · gate: p<=1% ∧ LB>3% ∧ ≥2 non-soccer regimes")
    print(f"{'candidate':<26}{'nEv':>4}{'obs':>9}{'LB':>9}{'p_emp':>8}{'nsR':>4}  gate")
    results = {}
    survivors = []
    for name, sub in C.items():
        r = score(sub, blind_cells, blind_edge, rng)
        results[name] = r
        if not r.get("readable"):
            print(f"{name:<26}{r['n_ev']:>4}   —    (below readout floor / unmatchable)")
            continue
        flag = "✅ CLEARS" if r["belief_blind_gate"] else "—"
        print(f"{name:<26}{r['n_ev']:>4}{r['obs']:>+8.2%}{r['lb']:>+8.2%}{r['p_emp']:>8.4f}{r['non_soccer_pos']:>4}  {flag}")
        if r["belief_blind_gate"] and name != "CHAMPION favorite (all)":
            survivors.append(name)

    n_tested = sum(1 for r in results.values() if r.get("readable")) - 1  # exclude champion row
    champ = results["CHAMPION favorite (all)"]
    print(f"\nmultiplicity: {n_tested} challengers tested → Bonferroni-adjust p by ×{n_tested} before believing any single row.")
    print(f"champion favorite (all): obs {champ['obs']:+.2%} · LB {champ['lb']:+.2%} · p {champ['p_emp']:.4f}")
    if survivors:
        print(f"\n⚠ {len(survivors)} candidate(s) CLEAR the belief-blind gate: {survivors}")
        print("  → NOT adopted. Each still needs: beats-champion-on-realizable + Bonferroni-survival + independent skeptic pass (§3).")
    else:
        print("\nNo challenger clears the belief-blind gate beyond the champion. CHAMPION STANDS — the screen worked.")
    json.dump({"n_tested": n_tested, "champion": champ, "survivors": survivors, "results": results},
              open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "reports", "edge_refine_search.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
