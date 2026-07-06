#!/usr/bin/env python3
"""
F3 — MULTIPLICITY / NULL-EDGE SURVIVOR.  Is favorite distinguishable from "we searched ~15
arms and kept the best"?

Two questions, both answered with the gate's own machinery (selection_null):
  (A) REAL-FAMILY Bonferroni: run the selection-matched null across EVERY arm that clears the
      10-event floor; report each p and whether favorite survives x(#tested) Bonferroni.
  (B) SYNTHETIC-NULL PIPELINE: draw K pseudo-arms from the `_blind` universe (a null world with
      NO real edge), run the FULL certification pipeline (gate LB>3% AND selection-null p<=0.01
      AND >=2 sport-regimes>0) on each, and measure how often a null SEARCH of K arms certifies
      *somebody*. If that rate is low, "certified-eligible" is not cheap and favorite's
      survival is not a multiplicity artifact. Recalls the market_resid lesson (a +30% surplus
      that a 0-baseline gate false-promoted).

KILL (pre-registered): FWER-adjusted favorite p > 0.05, OR a null search certifies an arm at a
rate (>~1 per search on average / P(any) high) that makes favorite unremarkable.

Modes:
  ./multiplicity.py            # live -> reports/stress/multiplicity.json
  ./multiplicity.py --selftest # planted-edge arm certifies; pure-null search rarely certifies
"""
import io
import json
import os
import random
import sys
from collections import defaultdict
from math import sqrt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import selection_null as sn

SEED = 20260702
N_PERM = 4000          # per-arm null draws (real family)
MARGIN = 0.03          # gate capture margin
P_BAR = 0.01           # selection-null promotion bar
N_SEARCHES = 400       # synthetic-null searches
Z1 = 1.6448536269514722  # one-sided 95% (gate LB convention)


def build_blind(rows):
    blind = [r for r in rows if r["strategy"] == "_blind"]
    blind_cells = defaultdict(list)
    blind_band = defaultdict(list)
    reg_band = defaultdict(lambda: defaultdict(list))
    for r in blind:
        b = sn.band(r["entry"])
        a = r["won"] - r["entry"]
        blind_cells[(b, r["day"])].append((r["ev"], a))
        blind_band[b].append(a)
        reg_band[sn.regime(r["event_slug"])][b].append(a)
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}
    rb = {rg: {b: sum(v) / len(v) for b, v in bands.items()} for rg, bands in reg_band.items()}
    return blind, blind_cells, blind_edge, rb


def gate_lb(picks, blind_edge):
    """Event-clustered surplus mean and a one-sided 95% lower bound (iid-SE over event means).
    Deliberately the OPTIMISTIC (event-N) convention — the same one the promotion gate uses —
    so real and pseudo arms are judged identically."""
    ev_map = defaultdict(list)
    for ev, b, a in picks:
        ev_map[ev].append(a - blind_edge.get(b, 0.0))
    means = [sum(v) / len(v) for v in ev_map.values()]
    n = len(means)
    if n < 2:
        return float("nan"), float("nan"), n
    mu = sum(means) / n
    sd = sqrt(sum((x - mu) ** 2 for x in means) / (n - 1))
    return mu, mu - Z1 * sd / sqrt(n), n


def regime_pass(srows, rb):
    """>=2 disjoint sport-regimes with regime-matched surplus > 0."""
    by_reg = defaultdict(list)
    for ev, b, a, rg in srows:
        base = rb.get(rg, {}).get(b)
        if base is None:
            continue
        by_reg[rg].append((ev, a - base))
    pos = 0
    for rg, picks in by_reg.items():
        ev_map = defaultdict(list)
        for ev, sr in picks:
            ev_map[ev].append(sr)
        m = sum(sum(v) / len(v) for v in ev_map.values()) / len(ev_map)
        if m > 0:
            pos += 1
    return pos


def certify(srows, blind_cells, blind_edge, rb, rng, n_perm):
    """Full pipeline on a set of rows shaped as (ev, band, a, regime, day). Returns dict."""
    picks = [(r[0], r[1], r[2]) for r in srows]
    mu, lb, n = gate_lb(picks, blind_edge)
    if n < 10:
        return {"n": n, "certified": False, "reason": "below floor"}
    meta = [(r[1], r[4]) for r in srows]
    draws = sn.null_pvalue(meta, blind_cells, blind_edge, rng, n_perm)
    if len(draws) < max(500, n_perm // 4):
        return {"n": n, "certified": False, "reason": "null unmatchable"}
    p = sum(1 for x in draws if x >= mu) / len(draws)
    nreg = regime_pass([(r[0], r[1], r[2], r[3]) for r in srows], rb)
    g1 = lb > MARGIN
    g2 = p <= P_BAR
    g3 = nreg >= 2
    return {"n": n, "surplus": mu, "lb": lb, "p": p, "n_pos_regimes": nreg,
            "gate_lb_gt_margin": g1, "null_p_le_bar": g2, "regimes_ge_2": g3,
            "certified": bool(g1 and g2 and g3)}


def rows_shaped(rows, strategy):
    return [(r["ev"], sn.band(r["entry"]), r["won"] - r["entry"],
             sn.regime(r["event_slug"]), r["day"])
            for r in rows if r["strategy"] == strategy]


def run():
    rows = sn.fetch()
    _, blind_cells, blind_edge, rb = build_blind(rows)
    rng = random.Random(SEED)
    strategies = sorted({r["strategy"] for r in rows if r["strategy"] != "_blind"})

    # (A) real family
    fam = []
    for s in strategies:
        srows = rows_shaped(rows, s)
        res = certify(srows, blind_cells, blind_edge, rb, rng, N_PERM)
        res["strategy"] = s
        fam.append(res)
    tested = [f for f in fam if f.get("n", 0) >= 10 and "p" in f]
    k_tested = len(tested)
    fav = next((f for f in fam if f["strategy"] == "favorite"), None)
    fav_bonf = (fav["p"] * k_tested) if (fav and "p" in fav) else float("nan")
    n_certified = sum(1 for f in tested if f["certified"])

    # (B) synthetic-null search: K pseudo-arms drawn from blind, matched to the real arms'
    # SIZES (the null "if the selection rule carried no real edge"). How often does the
    # best-of-K certify?
    blind_rows = [r for r in rows if r["strategy"] == "_blind"]
    real_sizes = [len({r["ev"] for r in rows if r["strategy"] == s}) for s in strategies
                  if len({r["ev"] for r in rows if r["strategy"] == s}) >= 10]
    K = len(real_sizes)
    any_cert = 0
    best_ps = []
    per_search_cert = []
    for si in range(N_SEARCHES):
        srng = random.Random(SEED + 1000 + si)
        certs = 0
        bp = 1.0
        for size in real_sizes:
            sample = srng.sample(blind_rows, min(size, len(blind_rows)))
            shaped = [(r["ev"], sn.band(r["entry"]), r["won"] - r["entry"],
                       sn.regime(r["event_slug"]), r["day"]) for r in sample]
            res = certify(shaped, blind_cells, blind_edge, rb, srng, 800)
            if "p" in res:
                bp = min(bp, res["p"])
            if res.get("certified"):
                certs += 1
        per_search_cert.append(certs)
        best_ps.append(bp)
        if certs > 0:
            any_cert += 1
    p_any = any_cert / N_SEARCHES
    mean_cert = sum(per_search_cert) / len(per_search_cert)

    result = {"meta": {"seed": SEED, "n_perm": N_PERM, "k_tested": k_tested,
                       "n_searches": N_SEARCHES, "K_arms_per_search": K,
                       "margin": MARGIN, "p_bar": P_BAR},
              "real_family": fam,
              "favorite_p": (fav.get("p") if fav else None),
              "favorite_bonferroni_p": fav_bonf,
              "n_arms_certified_real": n_certified,
              "synthetic_null": {"p_any_arm_certifies_per_search": p_any,
                                 "mean_arms_certified_per_search": mean_cert,
                                 "median_best_of_K_p": sorted(best_ps)[len(best_ps) // 2]}}
    return result


def _print(r):
    m = r["meta"]
    print(f"F3 multiplicity · {m['k_tested']} arms tested · {m['n_searches']} synthetic-null "
          f"searches of K={m['K_arms_per_search']}")
    print(f"{'arm':<16}{'n':>5}{'surplus':>9}{'gateLB':>9}{'null p':>9}{'reg+':>5}  cert?")
    for f in sorted(r["real_family"], key=lambda x: -(x.get("surplus") or -9)):
        if "p" not in f:
            print(f"{f['strategy']:<16}{f.get('n',0):>5}   {f.get('reason','')}")
            continue
        c = "CERT" if f["certified"] else (
            "".join(["G1" if not f["gate_lb_gt_margin"] else "",
                     "G2" if not f["null_p_le_bar"] else "",
                     "G3" if not f["regimes_ge_2"] else ""]) or "?")
        print(f"{f['strategy']:<16}{f['n']:>5}{f['surplus']:>+9.2%}{f['lb']:>+9.2%}"
              f"{f['p']:>9.4f}{f['n_pos_regimes']:>5}  {c}")
    print(f"\nfavorite null p = {r['favorite_p']:.4f} · Bonferroni ×{m['k_tested']} = "
          f"{r['favorite_bonferroni_p']:.4f} -> "
          f"{'SURVIVES <0.05' if r['favorite_bonferroni_p'] < 0.05 else 'FAILS'}")
    print(f"real arms certified by full pipeline: {r['n_arms_certified_real']}")
    sn_ = r["synthetic_null"]
    print(f"\nSYNTHETIC NULL (no real edge): P(a search of K arms certifies anyone) = "
          f"{sn_['p_any_arm_certifies_per_search']:.1%}; mean arms certified/search = "
          f"{sn_['mean_arms_certified_per_search']:.3f}; median best-of-K p = "
          f"{sn_['median_best_of_K_p']:.3f}")


def selftest():
    ok = True
    rng = random.Random(SEED)
    # build a small synthetic universe: blind + one planted-edge arm + null draws
    blind = []
    day_list = ["d0", "d1", "d2", "d3"]
    regs = ["tennis", "soccer", "mlb", "other"]
    for i in range(4000):
        rg = regs[i % 4]
        entry = 0.5 + 0.4 * rng.random()
        pref = {"tennis": "atp", "soccer": "fifwc", "mlb": "mlb", "other": "xx"}[rg]
        won = 1 if rng.random() < entry else 0  # blind: fair by construction
        blind.append({"strategy": "_blind", "ev": f"b{i}", "event_slug": f"{pref}-{i}",
                      "entry": entry, "won": won, "day": day_list[i % 4]})
    # planted arm: 60 events, favorites priced 0.80 but win 0.95 (+15 edge), across 3 regimes
    planted = []
    for i in range(60):
        rg = regs[i % 3]
        pref = {"tennis": "atp", "soccer": "fifwc", "mlb": "mlb"}[rg]
        won = 1 if rng.random() < 0.95 else 0
        planted.append({"strategy": "planted", "ev": f"p{i}", "event_slug": f"{pref}-p{i}",
                        "entry": 0.80, "won": won, "day": day_list[i % 4]})
    rows = blind + planted
    _, bc, be, rb = build_blind(rows)
    prng = random.Random(SEED)
    pcert = certify(rows_shaped(rows, "planted"), bc, be, rb, prng, 1500)
    print(f"  planted +15pp edge arm: cert={pcert['certified']} (p={pcert.get('p')}, "
          f"lb={pcert.get('lb'):+.2%}) [{'ok' if pcert['certified'] else 'FAIL'}]")
    ok = ok and pcert["certified"]
    # pure-null search of K=13 arms drawn from blind: should rarely certify
    blist = [r for r in rows if r["strategy"] == "_blind"]
    hits = 0
    for si in range(120):
        srng = random.Random(SEED + si)
        c = 0
        for _ in range(13):
            samp = srng.sample(blist, 60)
            shaped = [(r["ev"], sn.band(r["entry"]), r["won"] - r["entry"],
                       sn.regime(r["event_slug"]), r["day"]) for r in samp]
            if certify(shaped, bc, be, rb, srng, 500).get("certified"):
                c += 1
        if c:
            hits += 1
    rate = hits / 120
    # correctness bound (not the finding): a pure-null search must certify LESS than always and
    # the planted edge must ALWAYS certify — the actual FWER is the reported live number, and a
    # non-trivial pure-null rate is itself the F3 point (multiplicity is real).
    print(f"  pure-null search certifies anyone: {rate:.1%} of 120 searches (correctness: <60%) "
          f"[{'ok' if rate < 0.60 else 'FAIL'}]")
    ok = ok and rate < 0.60
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    r = run()
    _print(r)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "reports", "stress", "multiplicity.json"), "w") as f:
        json.dump(r, f, indent=1, default=str)
    print("\nartifact -> reports/stress/multiplicity.json")


if __name__ == "__main__":
    main()
