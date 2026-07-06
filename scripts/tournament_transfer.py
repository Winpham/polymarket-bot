#!/usr/bin/env python3
"""
TOURNAMENT-TRANSFER — does the favorite-softness edge repeat across DIFFERENT tournaments?

Re-parameterizes the regime axis from sport×month to TOURNAMENT IDENTITY (World Cup, Wimbledon,
LoL-MSI, …) and tests the thesis the merged "SOCCER-ARTIFACT" run under-served: tournaments are a
PERPETUAL class (one ends, the next begins), so an edge carried by high-profile tournament markets
is not "expiring" — it is durable IFF it TRANSFERS across different tournaments. Leave-one-tournament-
out: fit "edge exists" on all-but-one tournament, test the held-out tournament's small-cluster-t LB >
margin; count how many of ≥2 hold out. A matched tournament-permutation null guards concentration,
reported with honest diagnostics (guard_can_fire / min_p_conc / beat_null) — never a bare "PASS".

THE HONESTY CRUX (PREREG §4): today's tournaments (World Cup + Wimbledon + …) are CONTEMPORANEOUS
(one 6-day window), so a transfer here is cross-SPORT, NOT forward-in-time. That is NECESSARY but NOT
SUFFICIENT for real money — a FORWARD verdict needs a time-SEPARATED tournament (a later one we did
not fit on). And even a forward transfer stays gated on edge-reality (λ) and net-positive-after-cost;
real money is a Tue-gated decision, never armed here.

Reuses the merged, audited machinery byte-identically: regime_edge (matched baseline, event key,
small-cluster t LB via lb_small_cluster, per-regime read incl. net_taker), regime_persistence
(_transfer_count), regime_classify (classify_tournament). Frozen in
reports/PREREG_20260705T024128Z_tournament_transfer.md. Read-only, paper-only, promotes nothing.

Modes:
  ./tournament_transfer.py             # per-tournament table + cross-tournament transfer + verdict; JSON
  ./tournament_transfer.py --selftest  # transfers→CONTEMPORANEOUS/FORWARD; idiosyncratic; refuted; pending
"""

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_edge as reg            # _matched_baseline, _regime_read, lb_small_cluster, _band_spreads, smod
import regime_persistence as rp      # _transfer_count (generic over a regime_of map)
import regime_classify as rc         # classify_tournament
from market_taxonomy import category

PREREG = "reports/PREREG_20260705T024128Z_tournament_transfer.md"
MARGIN = 0.03
TRANSFER_MIN_TOURNAMENTS = 2
N_PERM = 1000
SEED = 20260705
REPORT_DIR = reg.REPORT_DIR


def _events_tournament(prows, baseline):
    """Per-event: surplus over matched baseline, entry, day, tournament_id, is_tournament, sport."""
    by_ev = defaultdict(list)
    for r in prows:
        by_ev[reg.smod.evk(r)].append(r)
    ev = {}
    for k, rs in by_ev.items():
        s = float(np.mean([(r["won"] - r["entry"]) - baseline(r) for r in rs]))
        entry = float(np.mean([r["entry"] for r in rs]))
        day = min(str(r["day"]) for r in rs)
        r0 = rs[0]
        cat = category(r0["slug"], r0["title"])
        tid, is_t = rc.classify_tournament(cat, None, r0["slug"], r0["title"])
        ev[k] = {"surplus": s, "entry": entry, "day": day, "tournament_id": tid,
                 "is_tournament": is_t, "sport": cat}
    return ev


def _read(sub, spreads):
    r = reg._regime_read(sub, spreads)
    if r is None:
        return None
    r["hi"] = (2 * r["surplus"] - r["lb"]) if r["lb"] is not None else None
    return r


def _time_separated(spans, ids):
    """True if ANY pair among `ids` has disjoint date ranges (a forward, time-separated instance)."""
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = spans[ids[i]], spans[ids[j]]
            if a[1] < b[0] or b[1] < a[0]:
                return True
    return False


def transfer(ev_t, spreads, rng):
    """Leave-one-tournament-out transfer + tournament-permutation null (honest diagnostics)."""
    tour_of = {k: v["tournament_id"] for k, v in ev_t.items()}
    n_tour = len(set(tour_of.values()))
    real_count, detail = rp._transfer_count(ev_t, tour_of, spreads)
    keys = list(ev_t.keys())
    sizes = defaultdict(int)
    for tid in tour_of.values():
        sizes[tid] += 1
    labels = []
    for tid, n in sizes.items():
        labels += [tid] * n
    null_counts = []
    if n_tour >= 2 and len(keys) >= 2:
        for _ in range(N_PERM):
            perm = labels[:]
            rng.shuffle(perm)
            pmap = {keys[i]: perm[i] for i in range(len(keys))}
            c, _ = rp._transfer_count(ev_t, pmap, spreads)
            null_counts.append(c)
    p_conc = (sum(1 for c in null_counts if c <= real_count) / len(null_counts)) if null_counts else None
    min_p_conc = (null_counts.count(0) / len(null_counts)) if null_counts else None
    guard_can_fire = (min_p_conc is not None and min_p_conc < 0.05)
    p_beat = (sum(1 for c in null_counts if c >= real_count) / len(null_counts)) if null_counts else None
    beat_null_can_pass = (p_beat is not None and p_beat <= 0.05)
    dist = {}
    for c in null_counts:
        dist[c] = dist.get(c, 0) + 1
    return {"n_tournaments_testable": n_tour, "real_transfer_count": real_count,
            "required": TRANSFER_MIN_TOURNAMENTS, "p_conc": p_conc, "min_p_conc": min_p_conc,
            "guard_can_fire": guard_can_fire, "p_beat": p_beat, "beat_null_can_pass": beat_null_can_pass,
            "null_dist": {str(k): v for k, v in sorted(dist.items())}, "per_tournament": detail,
            "count_ok": real_count >= TRANSFER_MIN_TOURNAMENTS,
            "guard_inert_note": (None if guard_can_fire else
                                 "tournament-permutation null non-discriminating (guard cannot fire) → "
                                 "leg is a RAW transfer count, not a passed test")}


def verdict(tournaments, tr, spans):
    testable = [tid for tid, t in tournaments.items()
                if t["is_tournament"] and t["read"] and t["read"]["n_clusters"] >= 2]
    # REFUTED: a testable tournament whose own edge upper bound < 0 (decayed)
    for tid in testable:
        hi = tournaments[tid]["read"].get("hi")
        if hi is not None and hi < 0:
            return "REFUTED", f"tournament '{tid}' edge upper bound {hi:+.1%} < 0 — decayed on a held-out tournament"
    if len(testable) < TRANSFER_MIN_TOURNAMENTS:
        return "PENDING", (f"only {len(testable)} tournament(s) with computable (G≥2) data "
                           f"(< {TRANSFER_MIN_TOURNAMENTS}) — accrue more tournaments")
    if tr["real_transfer_count"] < TRANSFER_MIN_TOURNAMENTS:
        # ADDENDUM 20260705T030000Z: split power-limitation from idiosyncrasy by sign-consistency.
        surps = [tournaments[t]["read"]["surplus"] for t in testable]
        pos_frac = (sum(1 for s in surps if s > 0) / len(surps)) if surps else 0.0
        med = float(np.median(surps)) if surps else 0.0
        if pos_frac >= 0.6:
            return "TOURNAMENT-POWER-LIMITED", (
                f"{tr['real_transfer_count']}/{TRANSFER_MIN_TOURNAMENTS} clear the margin, but "
                f"{pos_frac:.0%} of {len(testable)} tournaments are sign-consistent POSITIVE "
                f"(median {med:+.1%}) — the edge is CONSISTENT but too few clusters/tournament to clear "
                f"cost individually. INDETERMINATE — accrue more tournaments (NOT an artifact, NOT bankable)")
        return "TOURNAMENT-IDIOSYNCRATIC", (f"only {tr['real_transfer_count']}/{TRANSFER_MIN_TOURNAMENTS} "
                                            f"transfer and edges DISAGREE across tournaments (pos_frac {pos_frac:.0%}) — artifact stands")
    transferring = [tid for tid, d in tr["per_tournament"].items() if d["transfers"]]
    forward = _time_separated(spans, [t for t in transferring if t in spans]) if len(transferring) >= 2 else False
    if forward:
        return "CROSS-TOURNAMENT-FORWARD", (f"{tr['real_transfer_count']} tournaments transfer AND ≥1 is "
                                            f"time-separated → forward persistence of the tournament-class edge (still gated: λ + net-cost + Tue)")
    return "CROSS-TOURNAMENT-CONTEMPORANEOUS", (f"{tr['real_transfer_count']} tournaments transfer but all "
                                                f"CONTEMPORANEOUS → edge is not sport-specific (encouraging), forward-in-time UNPROVEN; real money remains gated")


def analyze(rows, spreads=None):
    import random
    if spreads is None:
        spreads = reg._band_spreads()
    rng = random.Random(SEED)
    blind = [r for r in rows if r["strategy"] == "_blind"]
    baseline = reg._matched_baseline(blind)
    prows = [r for r in rows if r["strategy"] == "favorite"]
    ev = _events_tournament(prows, baseline)
    if not ev:
        return {"meta": {"prereg": PREREG}, "n_events": 0, "note": "no favorite data"}
    by_t = defaultdict(dict)
    spans = {}
    for k, v in ev.items():
        by_t[v["tournament_id"]][k] = v
    tournaments = {}
    for tid, sub in by_t.items():
        r = _read(sub, spreads)
        days = sorted({v["day"] for v in sub.values()})
        spans[tid] = (days[0], days[-1])
        tournaments[tid] = {"is_tournament": next(iter(sub.values()))["is_tournament"],
                            "sport": next(iter(sub.values()))["sport"], "n_events": len(sub),
                            "span": [days[0], days[-1]], "read": r}
    ev_t = {k: v for k, v in ev.items() if v["is_tournament"]}
    tr = transfer(ev_t, spreads, rng)
    # only keep tournament spans for is_tournament regimes for the contemporaneity read
    t_spans = {tid: spans[tid] for tid in spans if tournaments[tid]["is_tournament"]}
    vd, why = verdict(tournaments, tr, t_spans)
    all_days = sorted({v["day"] for v in ev.values()})
    testable = [tid for tid, t in tournaments.items()
                if t["is_tournament"] and t["read"] and t["read"]["n_clusters"] >= 2]
    surps = [tournaments[t]["read"]["surplus"] for t in testable]
    diag = {"n_testable_tournaments": len(testable),
            "pos_frac": (sum(1 for s in surps if s > 0) / len(surps)) if surps else None,
            "median_surplus": float(np.median(surps)) if surps else None,
            "testable_ids": sorted(testable)}
    return {"meta": {"prereg": PREREG, "margin": MARGIN, "transfer_min": TRANSFER_MIN_TOURNAMENTS,
                     "record_span": [all_days[0], all_days[-1]]},
            "n_events": len(ev), "tournaments": tournaments, "transfer": tr,
            "diagnostics": diag, "verdict": vd, "why": why}


def _f(x, spec="+.2%"):
    return "  n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, spec)


def run_live():
    res = analyze(reg.smod.fetch())
    print("TOURNAMENT-TRANSFER · does the favorite-softness edge repeat across DIFFERENT tournaments?")
    print(f"  frozen: {PREREG} · record {res['meta']['record_span'][0]}→{res['meta']['record_span'][1]} · "
          f"small-cluster t LB · transfer ≥{TRANSFER_MIN_TOURNAMENTS}\n")
    ts = res["tournaments"]
    hdr = f"  {'tournament':<24}{'is_t':>5}{'ev':>4}{'cl':>4}{'surplus':>9}{'t-LB':>9}{'net_taker':>10}{'span':>14}"
    print(hdr)
    for tid in sorted(ts, key=lambda t: -(ts[t]["read"]["surplus"] if ts[t]["read"] else -9)):
        t = ts[tid]; r = t["read"]
        if not r:
            continue
        flag = "TOUR" if t["is_tournament"] else "lg"
        print(f"  {tid:<24}{flag:>5}{r['n_events']:>4}{r['n_clusters']:>4}{_f(r['surplus']):>9}{_f(r['lb']):>9}"
              f"{_f(r['net_taker']):>10}{t['span'][0][5:]+'–'+t['span'][1][5:]:>14}")
    tr = res["transfer"]
    print(f"\n  CROSS-TOURNAMENT TRANSFER — {tr['n_tournaments_testable']} testable tournaments · "
          f"raw transfer count {tr['real_transfer_count']}/{tr['required']}")
    for tid, d in sorted(tr["per_tournament"].items(), key=lambda kv: -(kv[1]['n_events'])):
        print(f"      hold-out {tid:<22} n={d['n_events']:>2} held-surplus {_f(d['held_surplus'])} "
              f"t-LB {_f(d['held_lb'])} fit {_f(d['fit_surplus'])} → {'transfers' if d['transfers'] else 'no'}")
    print(f"    permutation guard: p_conc {_f(tr['p_conc'],'.3f')} (min achievable {_f(tr['min_p_conc'],'.3f')} — "
          f"{'CAN fire' if tr['guard_can_fire'] else 'CANNOT fire'}); beat-null {_f(tr['p_beat'],'.3f')} "
          f"({'passable' if tr['beat_null_can_pass'] else 'unpassable'})")
    if tr.get("guard_inert_note"):
        print(f"    ⚠ {tr['guard_inert_note']}")
    d = res["diagnostics"]
    print(f"    sign-consistency: {_f(d['pos_frac'],'.0%')} of {d['n_testable_tournaments']} testable "
          f"tournaments POSITIVE (median {_f(d['median_surplus'])}) — POWER-LIMITED (consistent) vs IDIOSYNCRATIC (disagree)")
    print(f"\n  VERDICT: {res['verdict']} — {res['why']}")
    print("  (real money stays gated: cross-tournament transfer is necessary, NOT sufficient — λ + "
          "net-positive-after-cost + Tue remain.)")
    out = os.path.join(REPORT_DIR, "tournament_transfer.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"\nartifact → reports/tournament_transfer.json")
    return res


# --------------------------------------------------------------------------------------------
def _mk(strat, tour_slug, i, entry, won, day, title):
    slug = f"{tour_slug}-x{i}-y{i}-{day}"
    return dict(strategy=strat, event_slug=slug, slug=slug, title=title, condition_id=slug,
                entry=entry, won=won, day=day)


def _selftest():
    import random
    ok = True
    spreads = {}

    def build(kind):
        rng = random.Random(3)   # fresh per scenario → deterministic & independent
        rows = []
        # blind baseline: favorites at 0.75 win ~75% everywhere (matched baseline ≈ 0)
        for disc, title, days in (("fifwc", "A vs. B: O/U 1.5", ["2026-07-01", "2026-07-02", "2026-07-03"]),
                                   ("atp", "Wimbledon ATP: A vs B", ["2026-07-01", "2026-07-02", "2026-07-03"]),
                                   ("lol", "T1 vs TL", ["2026-07-01", "2026-07-02", "2026-07-03"])):
            for day in days:
                for i in range(40):
                    rows.append(_mk("_blind", disc, i, 0.75, int(rng.random() < 0.75), day, title))
        # favorite edge per tournament, by scenario
        def fav(disc, title, days, p):
            for day in days:
                for i in range(100, 112):
                    rows.append(_mk("favorite", disc, i, 0.75, int(rng.random() < p), day, title))
        d3 = ["2026-07-01", "2026-07-02", "2026-07-03"]
        if kind == "contemporaneous":
            fav("fifwc", "A vs. B: O/U 1.5", d3, 0.92); fav("atp", "Wimbledon ATP: A vs B", d3, 0.92)
            fav("lol", "T1 vs TL", d3, 0.92)
        elif kind == "forward":
            fav("fifwc", "A vs. B: O/U 1.5", d3, 0.92)
            fav("atp", "Wimbledon ATP: A vs B", ["2026-07-20", "2026-07-21", "2026-07-22"], 0.92)  # time-separated
        elif kind == "idiosyncratic":
            # edges DISAGREE: 1 strong+, 2 net-negative but with HIGH between-cluster variance (one bad
            # day, one good day) → mean<0 yet CI so wide hi>0 (no REFUTED) ⇒ pos_frac 1/3 → IDIOSYNCRATIC
            fav("fifwc", "A vs. B: O/U 1.5", d3, 0.90)                       # strong + edge
            for disc, title in (("atp", "Wimbledon ATP: A vs B"), ("lol", "T1 vs TL")):
                fav(disc, title, ["2026-07-01"], 0.35)                       # bad day
                fav(disc, title, ["2026-07-02"], 0.85)                       # good day → net −, wide CI
        elif kind == "powerlimited":
            # consistent-positive but THIN edges (p≈0.80 → ~+5% surplus) on few clusters → none clears
            # the 3% margin under small-cluster t, but all sign-consistent positive → POWER-LIMITED
            fav("fifwc", "A vs. B: O/U 1.5", d3, 0.80); fav("atp", "Wimbledon ATP: A vs B", d3, 0.80)
        elif kind == "refuted":
            fav("fifwc", "A vs. B: O/U 1.5", d3, 0.40); fav("atp", "Wimbledon ATP: A vs B", d3, 0.40)  # negative
        elif kind == "pending":
            fav("fifwc", "A vs. B: O/U 1.5", ["2026-07-01"], 0.92)  # one tournament, one day
        return rows

    for kind, want in (("contemporaneous", "CROSS-TOURNAMENT-CONTEMPORANEOUS"),
                       ("forward", "CROSS-TOURNAMENT-FORWARD"),
                       ("powerlimited", "TOURNAMENT-POWER-LIMITED"),
                       ("idiosyncratic", "TOURNAMENT-IDIOSYNCRATIC"),
                       ("refuted", "REFUTED"), ("pending", "PENDING")):
        res = analyze(build(kind), spreads=spreads)
        got = res["verdict"]
        good = got == want
        ok = ok and good
        print(f"  [{'ok' if good else 'FAIL'}] {kind:<16} → {got:<34} (want {want}) · "
              f"transfer {res['transfer']['real_transfer_count']}/{res['transfer']['required']}")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run_live()
