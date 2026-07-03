#!/usr/bin/env python3
"""
SEED SOFTNESS×SKILL MAP INTO THE map_state STORE — Phase 4 (2026-07-03).

The softness×skill combined verdicts are expressed as a NEW DIMENSION (`catmix` =
category × market-type × band) in the EXISTING append-only map_state.py store — NOT a
parallel store (guardrail / [[extend-dont-rebuild]]). The frozen state machine
(ENTER-on-record, EXIT-on-recent, STALE/THRASH guards) then governs these cells exactly as
it governs the entry-10 slice dimensions.

map_state's entry rules are skill-ROI based and know nothing about softness. The softness axis
is folded into the metrics via a DOCUMENTED, verdict-preserving crosswalk so that
`map_state.step()` REPRODUCES softness_map's pre-registered PRIORITIZE/NEUTRAL/DODGE verdict:

  DODGE      → n_events := the driving sample (≥ floor), roi_ub := −ε (< 0), at_fire_true,
               K2-stable  ⇒ step's entry_dodge fires.   (covers both softness-sharp and
               skill-−EV DODGEs; the softness upper bound bounds realizable ROI from above.)
  PRIORITIZE → fdr_pass, roi_lb := +ε (> 0), splits ≥ 2, freq_recent ≥ 1, n_events ≥ floor,
               at_fire_true  ⇒ step's entry_prioritize fires. (softness ≥ 0 already checked
               upstream by softness_map._verdict.)
  else       → metrics meet no entry rule ⇒ NEUTRAL.

The state machine reads ROI/surplus/p_emp/fdr — those are preserved in map evidence. The full
softness numbers (softness, soft CI, n_blind_fav) live in the report entry + softness_map's own
tables (map_state._evidence is frozen and keeps only its metric set); the crosswalk above is the
auditable bridge. v001 (the entry-10 slice map) is carried forward unchanged from its stored
evidence — no spurious transitions.

Modes:
  ./seed_softness_map.py --self-test   # crosswalk reproduces each verdict class via step()
  ./seed_softness_map.py               # append v002 from the live DB (refuses to overwrite)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import map_state as ms
import softness_map as sm

DIM = "catmix"                       # the new map dimension: category × market-type × band
POP = sm.STRAT                       # "favorite"
EFFECTIVE = "2026-07-03T18:00:00Z"   # this run's map-version effective time (fixed; no clock)
EPS = 0.02


def _driving_n(v):
    """The sample that DRIVES the verdict — skill fires if measurable, else the blind pool."""
    nf = v.get("n_events") or 0
    if nf and nf >= sm.SKILL_N_FLOOR:
        return nf
    return v.get("n_blind_fav") or 0


def verdict_to_metrics(cellkey_parts, v):
    """(cat,mtype,band), softness_map verdict dict → map_state metrics that REPRODUCE it."""
    cat, mt, band = cellkey_parts
    n = _driving_n(v)
    base = dict(pop=POP, dim=DIM, cell=f"{cat}|{mt}|{band}",
                n_events=n, roi=v.get("roi"), surplus=v.get("surplus"),
                p_emp=v.get("p_emp"),
                # evidence passthrough (auditable; not read by the entry rules)
                softness=v.get("softness"), soft_lb=v.get("soft_lb"), soft_ub=v.get("soft_ub"),
                n_blind_fav=v.get("n_blind_fav"),
                splits=v.get("days_pos", 0), freq_recent=0.0,
                unstable=False, at_fire_true=True, fdr_pass=False,
                roi_lb=v.get("roi_lb"), roi_ub=v.get("roi_ub"))
    verd = v["verdict"]
    if verd == "DODGE":
        base.update(n_events=max(n, ms.N_FLOOR), roi_ub=-EPS, roi_lb=None, fdr_pass=False)
    elif verd == "PRIORITIZE":
        base.update(n_events=max(n, ms.N_FLOOR), roi_lb=EPS, fdr_pass=True,
                    splits=max(v.get("days_pos", 0), 2), freq_recent=1.0)
    else:  # NEUTRAL / INDETERMINATE → meet no entry rule
        base.update(roi_lb=(-EPS if (base.get("roi_lb") or 0) <= 0 else base["roi_lb"]),
                    roi_ub=(EPS if (base.get("roi_ub") or 0) >= 0 else base["roi_ub"]),
                    fdr_pass=False)
    return base


def build_whole(res):
    """softness_map result → {cell_key: metrics} for the catmix dimension."""
    whole = {}
    for cellparts, v in res["verdicts"].items():
        m = verdict_to_metrics(cellparts, v)
        whole[ms.cell_key(POP, DIM, m["cell"])] = m
    return whole


def carry_prior(prev):
    """Reconstruct prior-version cells' metrics from their stored evidence (identity carry)."""
    out = {}
    if not prev:
        return out
    for key, c in prev["cells"].items():
        ev = c.get("evidence_whole") or {}
        out[key] = dict(pop=c.get("pop"), dim=c.get("dim"), cell=c.get("cell"),
                        n_events=ev.get("n_events", 0), roi=ev.get("roi"),
                        roi_lb=ev.get("roi_lb"), roi_ub=ev.get("roi_ub"),
                        surplus=ev.get("surplus"), p_emp=ev.get("p_emp"),
                        fdr_pass=ev.get("fdr_pass", False), splits=ev.get("splits", 0),
                        freq_recent=ev.get("freq_recent", 0.0),
                        unstable=ev.get("unstable", False),
                        at_fire_true=ev.get("at_fire_true", False))
    return out


def make_version(prev, res, effective=EFFECTIVE):
    whole = carry_prior(prev)
    whole.update(build_whole(res))          # new dim adds keys; no collision with prior dims
    cp = (prev or {}).get("checkpoint_index", 0) + 1
    return ms.step(prev, whole, whole, checkpoint_idx=cp, effective_from=effective,
                   meta={"source": "softness_map.py (entry 20 — softness×skill map)",
                         "dimension": DIM,
                         "note": "category × market-type × band; softness folded into "
                                 "metrics via documented verdict-preserving crosswalk"})


def main():
    prev = ms.latest_version()
    res = sm.analyze(sm.fetch())
    v = make_version(prev, res)
    path = ms.write_version(v)
    catmix = {k: c for k, c in v["cells"].items() if c["dim"] == DIM}
    nd = sum(1 for c in catmix.values() if c["state"] == ms.DODGE)
    npri = sum(1 for c in catmix.values() if c["state"] == ms.PRIORITIZE)
    print(f"seeded map v{v['version']} → {path}")
    print(f"  effective_from {v['effective_from']} · dim '{DIM}' cells {len(catmix)} · "
          f"{npri} PRIORITIZE · {nd} DODGE · {len(v['cells'])} total cells (v001 carried)")
    for c in sorted(catmix.values(), key=lambda c: c["state"]):
        if c["state"] != ms.NEUTRAL:
            ev = c["evidence_whole"]
            print(f"  {c['state']:<11}{c['cell']:<26} roi_ub {ms._p(ev,'roi_ub')} "
                  f"surplus {ms._p(ev,'surplus')} N={ev.get('n_events')}  "
                  f"(full softness in reports/softness_map.json)")
    return 0


# --- self-test: the crosswalk must reproduce every verdict class through step() -------------
def _self_test():
    ok = True

    def mkv(verdict, **kw):
        d = dict(verdict=verdict, n_events=kw.get("n_events", 40), n_blind_fav=kw.get("n_blind_fav", 60),
                 roi=kw.get("roi"), roi_lb=kw.get("roi_lb"), roi_ub=kw.get("roi_ub"),
                 surplus=kw.get("surplus", 0.0), p_emp=kw.get("p_emp"), days_pos=kw.get("days_pos", 3),
                 softness=kw.get("softness", 0.05), soft_lb=kw.get("soft_lb"), soft_ub=kw.get("soft_ub"))
        return d

    cases = [
        (("mlb", "deriv", "0.60-0.80"), mkv("DODGE", softness=-0.10, soft_ub=-0.02, n_events=4), ms.DODGE),
        (("soccer", "main", "0.60-0.80"), mkv("PRIORITIZE", roi_lb=0.08, days_pos=4, n_events=40), ms.PRIORITIZE),
        (("tennis", "main", "0.60-0.80"), mkv("NEUTRAL", softness=0.01, roi_lb=-0.11, n_events=30), ms.NEUTRAL),
        (("esports", "main", "0.60-0.80"), mkv("INDETERMINATE", n_events=0, n_blind_fav=76), ms.NEUTRAL),
    ]
    whole = {}
    for parts, v, _ in cases:
        m = verdict_to_metrics(parts, v)
        whole[ms.cell_key(POP, DIM, m["cell"])] = m
    ver = ms.step(None, whole, whole, checkpoint_idx=1, effective_from="2026-07-03T18:00:00Z")
    for parts, v, want in cases:
        key = ms.cell_key(POP, DIM, f"{parts[0]}|{parts[1]}|{parts[2]}")
        got = ver["cells"][key]["state"]
        c = got == want
        ok = ok and c
        print(f"  [{'ok' if c else 'FAIL'}] {v['verdict']:<13} {parts} → step state {got} (want {want})")

    # carrying a prior version must not fabricate transitions on the carried cells
    prevlike = {"version": 1, "checkpoint_index": 1, "cells": {
        ms.cell_key("strict", "regime", "tennis"): {
            "pop": "strict", "dim": "regime", "cell": "tennis", "state": ms.DODGE,
            "evidence_whole": {"n_events": 40, "roi_ub": -0.10, "at_fire_true": True,
                               "unstable": False}}}}
    whole2 = carry_prior(prevlike)
    whole2.update(whole)
    v2 = ms.step(prevlike, whole2, whole2, checkpoint_idx=2, effective_from="2026-07-03T18:00:00Z")
    carried = v2["cells"][ms.cell_key("strict", "regime", "tennis")]
    c_carry = carried["state"] == ms.DODGE and not carried["flipped_last"]
    ok = ok and c_carry
    print(f"  [{'ok' if c_carry else 'FAIL'}] v001 cell carried unchanged (DODGE held, no flip)")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(main())
