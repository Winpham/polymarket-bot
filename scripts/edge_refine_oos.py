#!/usr/bin/env python3
"""
EDGE-REFINEMENT OOS CHECK (harden-edge, P3) — the decisive test for the price-band survivors of
edge_refine_search.py. The full-record belief-blind gate is NECESSARY but a nested price-band slice
can clear it as an in-sample fishing artifact. The guard's real adoption rule is BEATS-CHAMPION
OUT-OF-SAMPLE. So split the record at the persistence cutoff (2026-07-04) and read each config's
belief-blind surplus/LB IN-sample vs OUT-of-sample. A refinement is only real if it beats the champion
(0.65-0.98) OUT-of-sample, not merely in-sample.

Read-only. Reuses selection_null + edge_refine_search machinery. Adopts nothing.
"""
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn
import edge_refine_search as ers

CUTOFF = "2026-07-04"

CONFIGS = {
    "champion 0.65-0.98": lambda r: True,
    "band 0.70-0.95": lambda r: 0.70 <= r["entry"] <= 0.95,
    "band 0.75-0.98": lambda r: r["entry"] >= 0.75,
    "band 0.80-0.98": lambda r: r["entry"] >= 0.80,
}


def main():
    rng = random.Random(sn.SEED)
    allrows = sn.fetch()
    blind = [r for r in allrows if r["strategy"] == "_blind"]
    blind_cells = defaultdict(list); blind_band = defaultdict(list)
    for r in blind:
        b = sn.band(r["entry"]); a = r["won"] - r["entry"]
        blind_cells[(b, r["day"])].append((r["ev"], a)); blind_band[b].append(a)
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}
    fav = ers.fetch_fav()

    print(f"OOS SPLIT at {CUTOFF} (IN = day < cutoff, OUT = day >= cutoff) · belief-blind surplus/LB")
    print(f"{'config':<22}{'IN nEv':>7}{'IN obs':>9}{'IN LB':>8}   {'OUT nEv':>7}{'OUT obs':>9}{'OUT LB':>8}{'  OUT p':>8}")
    champ_out = None
    rows = {}
    for name, pred in CONFIGS.items():
        sub = [r for r in fav if pred(r)]
        insamp = [r for r in sub if r["day"] < CUTOFF]
        outsamp = [r for r in sub if r["day"] >= CUTOFF]
        ri = ers.score(insamp, blind_cells, blind_edge, rng)
        ro = ers.score(outsamp, blind_cells, blind_edge, rng)
        rows[name] = (ri, ro)
        if name == "champion 0.65-0.98":
            champ_out = ro
        def fmt(r, key, spec="+.2%"):
            v = r.get(key)
            return format(v, spec) if isinstance(v, (int, float)) and r.get("readable") else "  —  "
        print(f"{name:<22}{ri.get('n_ev',0):>7}{fmt(ri,'obs'):>9}{fmt(ri,'lb'):>8}   "
              f"{ro.get('n_ev',0):>7}{fmt(ro,'obs'):>9}{fmt(ro,'lb'):>8}"
              f"{(format(ro['p_emp'],'.4f') if ro.get('readable') else '  —  '):>8}")

    print()
    co = champ_out
    for name, (ri, ro) in rows.items():
        if name == "champion 0.65-0.98":
            continue
        if not (ro.get("readable") and co.get("readable")):
            print(f"  {name}: OUT below readout floor (n={ro.get('n_ev')}) — OOS INDETERMINATE-BY-POWER")
            continue
        beats = ro["obs"] > co["obs"] and ro["lb"] > co["lb"]
        verdict = "beats champion OUT-of-sample" if beats else "does NOT beat champion OUT-of-sample"
        print(f"  {name}: OUT obs {ro['obs']:+.2%} (champ {co['obs']:+.2%}) · OUT LB {ro['lb']:+.2%} "
              f"(champ {co['lb']:+.2%}) → {verdict}")
    print("\nAdoption requires beats-champion OUT-of-sample AND belief-blind gate AND independent skeptic. "
          "Nested price-band slices carry garden-of-forking-paths risk beyond the ×14 Bonferroni.")


if __name__ == "__main__":
    main()
