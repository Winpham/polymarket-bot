#!/usr/bin/env python3
"""
ADVERSARIAL RE-VERIFY of the favconsensus-deepen seed claims (C1-C4).

Fresh, self-contained. Independently re-derives the surplus-over-blind statistic with
its OWN clustering/banding/blind-baseline code (does NOT import favconsensus_reverify.py
or regime_cell_scoreboard.py). Only shared repo conventions are reused: superkey.super_event
and market_taxonomy.category (both re-checked on the slugs actually encountered, attack A4).

Statistic under attack (from reports/*.json):
  a       = outcome_won - COALESCE(initial_mean_price, mean_price)
  band    = 5 x 0.2 bins of entry (band4=[0.6,0.8), band5=[0.8,1.0))
  blind[b]= super-event-clustered mean of a over _blind picks in band b (GLOBAL, per-band)
  surplus = a - blind[band];  clustered by super_event; LB = mean - z(k)*se
  block A = utc-day < 2026-07-02 ; block B >= 2026-07-02

Attacks A1..A6 (see teammate brief). Run:  python3 scripts/verify_favconsensus.py
Self-test:                                  python3 scripts/verify_favconsensus.py --self-test
"""

import csv
import io
import json
import random
import subprocess
import sys
from collections import defaultdict
from math import sqrt, ceil
from statistics import NormalDist

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event          # shared convention (A4 re-checks its output)
from market_taxonomy import category      # shared convention

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
BLOCK_SPLIT = "2026-07-02"
ALPHA = 0.05
K_BONF = 4          # C1 family size claimed
Z = NormalDist()

SQL = """
SELECT strategy, condition_id, outcome_index, outcome_label,
       event_slug, slug, title,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day,
       to_char(resolved_at        AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS') AS resolved_at,
       to_char(first_detected_at  AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS') AS detected_at
FROM consensus_signals
WHERE resolved AND outcome_won IS NOT NULL
  AND strategy IN ('favorite','_blind')
"""

# grading cross-check: every strategy's resolution for a (condition_id, outcome_index)
SQL_GRADE = """
SELECT condition_id, outcome_index,
       count(DISTINCT (outcome_won::int)) AS distinct_wons,
       string_agg(DISTINCT (outcome_won::int)::text, ',') AS wons,
       count(*) AS n
FROM consensus_signals
WHERE resolved AND outcome_won IS NOT NULL
GROUP BY condition_id, outcome_index
HAVING count(DISTINCT (outcome_won::int)) > 1
"""


def z_for(k):
    return Z.inv_cdf(1 - ALPHA / k)


def my_band(p):
    if p < 0:
        return 1
    if p >= 1:
        return 5
    return int(p * 5) + 1


def evmean_se(pairs):
    """pairs=[(cluster,value)] -> (mean, se, n_clusters) via cluster-mean-first."""
    g = defaultdict(list)
    for k, v in pairs:
        g[k].append(v)
    means = [sum(v) / len(v) for v in g.values()]
    n = len(means)
    if n == 0:
        return None, None, 0
    m = sum(means) / n
    if n == 1:
        return m, None, 1
    var = sum((x - m) ** 2 for x in means) / (n - 1)
    return m, sqrt(var / n), n


def fetch(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def prep(raw):
    rows = []
    for r in raw:
        entry = float(r["entry"])
        sk = super_event(r.get("event_slug"), r.get("slug"))
        rows.append(dict(
            strategy=r["strategy"], condition_id=r["condition_id"],
            outcome_index=r["outcome_index"], slug=r.get("slug") or "",
            event_slug=r.get("event_slug") or "", title=r.get("title") or "",
            entry=entry, won=int(r["won"]), a=int(r["won"]) - entry,
            b=my_band(entry), day=r["day"], sk=sk,
            cat=category(r.get("slug") or "", r.get("title") or ""),
            resolved_at=r.get("resolved_at") or "", detected_at=r.get("detected_at") or "",
        ))
    return rows


def blind_edges(rows, per_category=False):
    """band -> event-clustered mean a over _blind picks. per_category -> (cat,band) key."""
    out = {}
    keys = set()
    for r in rows:
        if r["strategy"] != "_blind":
            continue
        keys.add((r["cat"], r["b"]) if per_category else r["b"])
    for key in keys:
        if per_category:
            cat, b = key
            pairs = [(r["sk"], r["a"]) for r in rows
                     if r["strategy"] == "_blind" and r["cat"] == cat and r["b"] == b]
        else:
            pairs = [(r["sk"], r["a"]) for r in rows
                     if r["strategy"] == "_blind" and r["b"] == key]
        m, _, n = evmean_se(pairs)
        out[key] = (m, n)
    return out


def surplus(favrows, edges, per_category=False):
    out = []
    for r in favrows:
        key = (r["cat"], r["b"]) if per_category else r["b"]
        if key not in edges or edges[key][0] is None:
            continue
        out.append(dict(r, s=r["a"] - edges[key][0]))
    return out


def stat(sr, k=K_BONF):
    m, se, n = evmean_se([(r["sk"], r["s"]) for r in sr])
    lbv = None if (m is None or se is None) else m - z_for(k) * se
    return dict(n_rows=len(sr), surplus=m, se=se, n_ev=n, lb=lbv)


def perm_null(cell_rows, blind_rows, edges, seed, n_perm=2000):
    """One-sided p matched on (band, utc-day), drawing from _blind pool."""
    rng = random.Random(seed)
    pool = defaultdict(list)
    for r in blind_rows:
        pool[(r["b"], r["day"])].append(r)
    profile = [(r["b"], r["day"]) for r in cell_rows]
    if any(not pool[k] for k in profile):
        return None
    obs = evmean_se([(r["sk"], r["s"]) for r in cell_rows])[0]
    ge = 0
    for _ in range(n_perm):
        g = defaultdict(list)
        for k in profile:
            d = rng.choice(pool[k])
            g[d["sk"]].append(d["a"] - edges[d["b"]][0])
        m = sum(sum(v) / len(v) for v in g.values()) / len(g)
        if m >= obs:
            ge += 1
    return (ge + 1) / (n_perm + 1)


# ---------------------------------------------------------------- attacks
def run():
    raw = fetch(SQL)
    rows = prep(raw)
    fav = [r for r in rows if r["strategy"] == "favorite"]
    blind_rows = [r for r in rows if r["strategy"] == "_blind"]
    edges = blind_edges(rows)
    sr = surplus(fav, edges)
    res = {"n_fav": len(fav), "n_blind": len(blind_rows),
           "blind_edges": {b: {"edge": edges[b][0], "n_ev": edges[b][1]} for b in sorted(edges)}}

    def cell(pred):
        return [r for r in sr if pred(r)]

    C1 = stat(sr)
    C2 = stat(cell(lambda r: r["cat"] == "mlb"))
    C3 = stat(cell(lambda r: r["cat"] == "soccer" and r["b"] == 4 and r["day"] >= BLOCK_SPLIT))
    C4 = stat(cell(lambda r: r["cat"] == "tennis" and r["b"] == 5 and r["day"] < BLOCK_SPLIT))

    # --- A1 re-derivation (claimed vs recomputed) ---
    claim = {"C1": dict(surplus=0.08390915, lb=0.01964689, n_ev=101),
             "C2": dict(surplus=0.22380329, lb=0.16271207, n_ev=14),
             "C3": dict(surplus=0.16996917, lb=0.05694359, n_ev=14),
             "C4": dict(surplus=0.12852444, lb=0.10263743, n_ev=16)}
    got = {"C1": C1, "C2": C2, "C3": C3, "C4": C4}
    a1 = {}
    for c in claim:
        ds = abs((got[c]["surplus"] or 0) - claim[c]["surplus"]) * 100
        dl = abs((got[c]["lb"] or 0) - claim[c]["lb"]) * 100
        dn = (got[c]["n_ev"] or 0) - claim[c]["n_ev"]
        a1[c] = dict(recomputed=got[c], d_surplus_pp=round(ds, 3), d_lb_pp=round(dl, 3),
                     d_n_ev=dn, flag=(ds > 0.5 or dl > 1.0 or dn != 0))
    res["A1"] = a1

    # --- A2 grading integrity ---
    grade_conflicts = fetch(SQL_GRADE)
    # per (cond, outcome) conflicts involving a favorite pick
    fav_keys = {(r["condition_id"], r["outcome_index"]) for r in fav}
    conflict_on_fav = [g for g in grade_conflicts
                       if (g["condition_id"], g["outcome_index"]) in fav_keys]
    res["A2"] = dict(
        total_grade_conflicts=len(grade_conflicts),
        conflicts_touching_favorite=len(conflict_on_fav),
        conflict_examples=[dict(condition_id=g["condition_id"], outcome_index=g["outcome_index"],
                                wons=g["wons"], n=g["n"]) for g in conflict_on_fav[:5]],
        fav_entry_oob=sum(1 for r in fav if r["entry"] <= 0 or r["entry"] >= 1),
        fav_resolved_before_detected=sum(
            1 for r in fav if r["resolved_at"] and r["resolved_at"] < r["detected_at"]),
    )

    # --- A3 leave-one-out on C2 (mlb) and C3 (soccer|band4|B) ---
    def loo(rows_):
        base = evmean_se([(r["sk"], r["s"]) for r in rows_])[0]
        by_ev = defaultdict(list)
        for r in rows_:
            by_ev[r["sk"]].append(r)
        keys = list(by_ev)
        outs = []
        for drop in keys:
            kept = [r for r in rows_ if r["sk"] != drop]
            outs.append(evmean_se([(r["sk"], r["s"]) for r in kept])[0])
        wins = sum(1 for r in rows_ if r["won"] == 1)
        losses = sum(1 for r in rows_ if r["won"] == 0)
        return dict(base_surplus=base, n_ev=len(keys),
                    days=sorted({r["day"] for r in rows_}), n_days=len({r["day"] for r in rows_}),
                    wins=wins, losses=losses,
                    loo_min=min(outs), loo_max=max(outs),
                    flips_sign=(min(outs) < 0 < base) or (max(outs) > 0 > base),
                    halves=(min(outs) < base / 2 if base > 0 else False))
    c2rows = cell(lambda r: r["cat"] == "mlb")
    c3rows = cell(lambda r: r["cat"] == "soccer" and r["b"] == 4 and r["day"] >= BLOCK_SPLIT)
    res["A3"] = {"C2_mlb": loo(c2rows), "C3_soccer_b4_B": loo(c3rows)}

    # --- A4 super-event honesty for mlb + soccer|band4|B cells ---
    def sk_audit(rows_):
        by_sk = defaultdict(list)
        for r in rows_:
            by_sk[r["sk"]].append(r)
        multi = {}
        for sk, rs in by_sk.items():
            slugstems = sorted({r["slug"] for r in rs})
            multi[sk] = dict(n_rows=len(rs), slugs=slugstems[:6],
                             event_slugs=sorted({r["event_slug"] for r in rs}))
        # heuristic: a super_event whose slugs imply >1 distinct matchup (differing team stem
        # before the date) = over-merge; report the raw for manual read.
        return dict(n_super_events=len(by_sk), detail=multi)
    res["A4"] = {"mlb": sk_audit(c2rows), "soccer_b4_B": sk_audit(c3rows)}

    # --- A5 fresh permutation null, seed 987654321, matched (band x utc-day) ---
    res["A5"] = dict(
        C1_p=perm_null(sr, blind_rows, edges, seed=987654321, n_perm=2000),
        C3_p=perm_null(c3rows, blind_rows, edges, seed=987654321, n_perm=2000),
        claimed_C1_p=0.0005, claimed_C3_p=0.0065)

    # --- A6 within-category band-matched blind baseline (composition attack) ---
    edges_cat = blind_edges(rows, per_category=True)
    sr_cat = surplus(fav, edges_cat, per_category=True)
    C1_wc = stat(sr_cat)

    def cat_matched_perm(cell_rows, seed, n_perm=2000):
        """selection null matched on (category, band, utc-day) vs _blind, within-cat baseline."""
        rng = random.Random(seed)
        pool = defaultdict(list)
        for r in blind_rows:
            pool[(r["cat"], r["b"], r["day"])].append(r)
        profile = [(r["cat"], r["b"], r["day"]) for r in cell_rows]
        if any(not pool[k] for k in profile):
            return None
        obs = evmean_se([(r["sk"], r["a"] - edges_cat[(r["cat"], r["b"])][0])
                         for r in cell_rows])[0]
        ge = 0
        for _ in range(n_perm):
            g = defaultdict(list)
            for k in profile:
                d = rng.choice(pool[k])
                g[d["sk"]].append(d["a"] - edges_cat[(d["cat"], d["b"])][0])
            m = sum(sum(v) / len(v) for v in g.values()) / len(g)
            if m >= obs:
                ge += 1
        return (ge + 1) / (n_perm + 1)

    def wc_cell(name, global_stat, cellrows):
        src = surplus(cellrows, edges_cat, per_category=True)
        st = stat(src)
        red = (None if not global_stat["surplus"] else
               round(100 * (1 - (st["surplus"] or 0) / global_stat["surplus"]), 1))
        return dict(name=name,
                    global_surplus=global_stat["surplus"], global_lb=global_stat["lb"],
                    withincat_surplus=st["surplus"], withincat_lb=st["lb"], n_ev=st["n_ev"],
                    reduction_pct=red, cat_matched_perm_p=cat_matched_perm(cellrows, 987654321),
                    cat_band_blind_edge={  # the baseline that does the damage
                        f"{cellrows[0]['cat']}|band{cellrows[0]['b']}":
                        edges_cat.get((cellrows[0]["cat"], cellrows[0]["b"]), (None,))[0]}
                    if cellrows else None)

    res["A6"] = dict(
        pooled_global_baseline=dict(surplus=C1["surplus"], lb=C1["lb"], n_ev=C1["n_ev"]),
        pooled_within_category=dict(surplus=C1_wc["surplus"], lb=C1_wc["lb"],
                                    n_ev=C1_wc["n_ev"], n_rows=C1_wc["n_rows"]),
        pooled_reduction_pct=(None if not C1["surplus"] else
                              round(100 * (1 - (C1_wc["surplus"] or 0) / C1["surplus"]), 1)),
        dropped_fav_rows=len(sr) - len(sr_cat),
        cells=dict(
            C2_mlb=wc_cell("C2_mlb", C2, c2rows),
            C3_soccer_b4_B=wc_cell("C3_soccer_b4_B", C3, c3rows),
            C4_tennis_b5_A=wc_cell("C4_tennis_b5_A", C4,
                                   cell(lambda r: r["cat"] == "tennis" and r["b"] == 5
                                        and r["day"] < BLOCK_SPLIT)),
        ),
    )
    return res


# ---------------------------------------------------------------- self-test
def _self_test():
    ok = True

    def chk(cond, msg):
        nonlocal ok
        print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
        ok = ok and cond

    chk(my_band(0.0) == 1 and my_band(0.59) == 3 and my_band(0.6) == 4
        and my_band(0.79) == 4 and my_band(0.8) == 5 and my_band(0.999) == 5
        and my_band(1.0) == 5 and my_band(-0.1) == 1, "band boundaries")
    # cluster collapse: dup rows in one event don't inflate n
    m, se, n = evmean_se([("e1", 1.0), ("e1", 0.0), ("e2", 0.5)])
    chk(n == 2 and abs(m - 0.5) < 1e-12, "cluster-mean-first collapses dups")
    # known-answer surplus: blind band4 edge 0, favorite 80% at 0.7 -> +0.1
    rws = []
    for i in range(50):
        rws.append(dict(strategy="_blind", cat="mlb", b=4, sk=f"b{i}",
                        a=(1 if i % 10 < 7 else 0) - 0.7, won=int(i % 10 < 7),
                        entry=0.7, day="2026-07-01", slug="", event_slug="",
                        title="", condition_id="", outcome_index="0",
                        resolved_at="", detected_at=""))
    for i in range(40):
        rws.append(dict(strategy="favorite", cat="mlb", b=4, sk=f"f{i}",
                        a=(1 if i % 10 < 8 else 0) - 0.7, won=int(i % 10 < 8),
                        entry=0.7, day="2026-07-01", slug="", event_slug="",
                        title="", condition_id="", outcome_index="0",
                        resolved_at="", detected_at=""))
    e = blind_edges(rws)
    chk(abs(e[4][0]) < 1e-9, "blind band4 edge ~0 on balanced fixture")
    srx = surplus([r for r in rws if r["strategy"] == "favorite"], e)
    st = stat(srx)
    chk(abs(st["surplus"] - 0.10) < 1e-9 and st["n_ev"] == 40, "known-answer surplus +0.10")
    # LB monotone in k
    chk(z_for(1) < z_for(4), "bonferroni z grows with k")
    # perm-null on a genuinely-null fixture (favorite drawn same as blind) ~ not tiny
    fav_null = [dict(r, s=r["a"] - e[4][0]) for r in rws if r["strategy"] == "favorite"]
    # make favorite identical distribution to blind -> p should be far from 0
    for r in fav_null:
        r["won"] = int(int(r["sk"][1:]) % 10 < 7)
        r["a"] = r["won"] - 0.7
        r["s"] = r["a"] - e[4][0]
    p = perm_null(fav_null, [r for r in rws if r["strategy"] == "_blind"], e,
                  seed=1, n_perm=500)
    chk(p is not None and p > 0.05, f"perm-null not tiny on null fixture (p={p})")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    out = run()
    print(json.dumps(out, indent=2, default=str))
    jp = "reports/verify_favconsensus.json"
    if "--json" in sys.argv:
        jp = sys.argv[sys.argv.index("--json") + 1]
    with open(jp, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nwrote", jp)
