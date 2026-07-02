#!/usr/bin/env python3
"""
MAP STATE — the adaptive PRIORITIZE / NEUTRAL / DODGE overlay as a versioned, append-only,
auditable state machine (entry 11, D14).

The slice study (entry 10) produced a FROZEN map. This module makes it a LIVING map: a
sequence of immutable versions, each stamped with an `effective_from` timestamp, where a
cell's verdict can flip in BOTH directions at pre-registered checkpoints — never by vibes,
always at the bar. A cut that can't un-cut itself is a scar, not a strategy.

THE STATE MACHINE (frozen — see reports/entries/2026-07-02-11-adaptive-overlay.md):

  state ∈ {DODGE, NEUTRAL, PRIORITIZE}  (+ per-cell flags STALE, THRASH)

  ENTRY (uses the WHOLE record — power):
    NEUTRAL → DODGE       realizable-ROI bootstrap UB < 0 ∧ N ≥ 20 ∧ K2-stable ∧ at-fire-true
    NEUTRAL → PRIORITIZE  the entry-10 rule verbatim (FDR-surviving null ∧ realizable-ROI
                          LB > 0 ∧ N ≥ 20 ∧ ≥2 splits positive ∧ freq_recent ≥ 1/day ∧
                          K2-stable ∧ at-fire-true)
  EXIT / REHAB (uses the RECENT window — adaptivity; N_recent ≥ 20 required):
    DODGE → NEUTRAL       the DODGE entry criterion FAILS on the recent window
    PRIORITIZE → NEUTRAL  the PRIORITIZE entry criterion FAILS on the recent window
    Silence is NOT rehabilitation: N_recent < 20 ⇒ state HELD, cell flagged STALE.
  HYSTERESIS / ANTI-THRASH:
    a cell that flips at TWO consecutive checkpoints is frozen at NEUTRAL and flagged
    THRASH (sticky) — noise-driven cells must not steer anything.

The asymmetry (whole-record ENTRY, recent-window EXIT) is deliberate and frozen: enter on
power, leave on adaptivity. `at_fire_true` = the dimension is knowable at fire (drift dims
are †-capped: they may nominate, never bind).

Storage: append-only JSON versions under reports/map/ (v001.json, v002.json, …) + a
manifest.json (version, effective_from, file, sha256). Immutable history, effective-from
lookup via current_map(at_ts), per-transition evidence. NO migration (guardrail 3: prefer
zero) — a map version is a git-tracked artifact, not DB state.

Modes:
  ./map_state.py --selftest    # hermetic synthetic checkpoint sequences (no DB):
                               #   enter DODGE on injected loss; rehab on recent flip;
                               #   STALE (not rehab) on silence; THRASH freeze on
                               #   alternation; ZERO transitions on stable noise (K2).
  ./map_state.py --seed        # seed map v1 from reports/slice_study.json (entry 10)
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_DIR = os.path.join(HERE, "..", "reports", "map")
MANIFEST = os.path.join(MAP_DIR, "manifest.json")

# Frozen thresholds — identical to slice_study's verdict rule (do NOT re-tune; adaptive
# means re-reading the same procedure on new data, never re-fitting the procedure).
N_FLOOR = 20
FREQ_FLOOR = 1.0
V1_EFFECTIVE = "2026-07-02T16:45:00Z"
RECENT_WINDOW_DESC = ("max(last 14 UTC days, span of the last 100 population events) — "
                      "at checkpoint #1 the record is 4 days so recent == whole")

DODGE, NEUTRAL, PRIORITIZE = "DODGE", "NEUTRAL", "PRIORITIZE"


# --- the two entry criteria (byte-identical to slice_study's PRIORITIZE/DODGE rule) ----
def entry_dodge(m):
    return bool(m and m.get("roi_ub") is not None and m["roi_ub"] < 0
                and m.get("n_events", 0) >= N_FLOOR and not m.get("unstable", False)
                and m.get("at_fire_true", False))


def entry_prioritize(m):
    return bool(m and m.get("fdr_pass") and m.get("roi_lb") is not None and m["roi_lb"] > 0
                and m.get("n_events", 0) >= N_FLOOR and m.get("splits", 0) >= 2
                and m.get("freq_recent", 0.0) >= FREQ_FLOOR and not m.get("unstable", False)
                and m.get("at_fire_true", False))


def cell_key(pop, dim, cell):
    return f"{pop}|{dim}|{cell}"


# --- the pure state-machine step (no DB, no I/O — this is what the self-test drives) ---
def step(prev_version, whole, recent, checkpoint_idx, effective_from, meta=None):
    """Apply the frozen state machine to produce the next map version.

    prev_version : previous version dict, or None for the very first version.
    whole/recent : {cell_key: metrics} for the whole record and the recent window.
                   metrics keys: n_events, roi_lb, roi_ub, fdr_pass, splits,
                   freq_recent, unstable, at_fire_true (+ any passthrough for evidence).
    Returns a new version dict (append-only; never mutates prev_version).
    """
    prev_cells = (prev_version or {}).get("cells", {})
    keys = set(whole) | set(prev_cells)
    new_cells, transitions, stale_keys, thrash_keys = {}, [], [], []

    for key in sorted(keys):
        w, r = whole.get(key), recent.get(key)
        pc = prev_cells.get(key, {})
        prev_state = pc.get("state", NEUTRAL)
        prev_flip = pc.get("flipped_last", False)
        prev_thrash = pc.get("thrash", False)
        prev_stale_since = pc.get("stale_since", None)
        is_stale = False

        if prev_thrash:                       # THRASH is sticky: frozen NEUTRAL forever
            new_state = NEUTRAL
        elif prev_state == DODGE:
            if r and r.get("n_events", 0) >= N_FLOOR:
                new_state = DODGE if entry_dodge(r) else NEUTRAL   # rehab on recent
            else:
                new_state, is_stale = DODGE, True                  # silence ⇒ hold + STALE
        elif prev_state == PRIORITIZE:
            if r and r.get("n_events", 0) >= N_FLOOR:
                new_state = PRIORITIZE if entry_prioritize(r) else NEUTRAL
            else:
                new_state, is_stale = PRIORITIZE, True
        else:                                 # NEUTRAL: entry on the whole record
            if entry_dodge(w):
                new_state = DODGE
            elif entry_prioritize(w):
                new_state = PRIORITIZE
            else:
                new_state = NEUTRAL

        flip = new_state != prev_state
        is_thrash = prev_thrash
        if flip and prev_flip and not prev_thrash:     # 2 consecutive flips ⇒ freeze
            new_state, is_thrash = NEUTRAL, True
            flip = new_state != prev_state

        # stale age bookkeeping
        if is_stale:
            stale_since = prev_stale_since if prev_stale_since is not None else checkpoint_idx
        else:
            stale_since = None
        stale_age = (checkpoint_idx - stale_since) if stale_since is not None else 0

        ev = _evidence(w)
        rec = _evidence(r)
        new_cells[key] = {
            "pop": (w or pc).get("pop"), "dim": (w or pc).get("dim"),
            "cell": (w or pc).get("cell"),
            "state": new_state, "flipped_last": flip,
            "thrash": is_thrash, "stale": is_stale,
            "stale_since": stale_since, "stale_age_checkpoints": stale_age,
            "evidence_whole": ev, "evidence_recent": rec,
        }
        if flip:
            transitions.append({"cell": key, "from": prev_state, "to": new_state,
                                "reason": _reason(prev_state, new_state, is_thrash, w, r),
                                "evidence_whole": ev, "evidence_recent": rec})
        if is_thrash:
            thrash_keys.append(key)
        if is_stale:
            stale_keys.append(key)

    return {
        "version": ((prev_version or {}).get("version", 0)) + 1,
        "effective_from": effective_from,
        "checkpoint_index": checkpoint_idx,
        "recent_window": RECENT_WINDOW_DESC,
        "meta": meta or {},
        "cells": new_cells,
        "transitions": transitions,
        "flags": {"stale": sorted(stale_keys), "thrash": sorted(thrash_keys)},
    }


def _evidence(m):
    if not m:
        return None
    return {k: m.get(k) for k in ("n_events", "roi", "roi_lb", "roi_ub", "surplus",
                                  "p_emp", "fdr_pass", "splits", "freq_recent",
                                  "unstable", "at_fire_true")}


def _reason(frm, to, thrash, w, r):
    if thrash:
        return "THRASH: flipped at two consecutive checkpoints ⇒ frozen NEUTRAL (sticky)"
    if frm == NEUTRAL and to == DODGE:
        return (f"ENTER DODGE (whole): roi_ub={_p(w,'roi_ub')} < 0 at N={w.get('n_events')}"
                ", K2-stable, at-fire-true")
    if frm == NEUTRAL and to == PRIORITIZE:
        return (f"ENTER PRIORITIZE (whole): FDR-null ∧ roi_lb={_p(w,'roi_lb')} > 0 at "
                f"N={w.get('n_events')}, {w.get('splits')} splits, freq={w.get('freq_recent')}")
    if frm == DODGE and to == NEUTRAL:
        return (f"REHAB (recent): DODGE entry criterion fails on recent window "
                f"(roi_ub={_p(r,'roi_ub')} ≥ 0 at N_recent={r.get('n_events') if r else None})")
    if frm == PRIORITIZE and to == NEUTRAL:
        return ("DEMOTE (recent): PRIORITIZE entry criterion fails on recent window "
                f"(N_recent={r.get('n_events') if r else None})")
    return f"{frm} → {to}"


def _p(m, k):
    v = (m or {}).get(k)
    return "None" if v is None else f"{v:+.3f}"


# ----------------------------- append-only storage ------------------------------------
def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_manifest():
    if not os.path.exists(MANIFEST):
        return []
    with open(MANIFEST) as f:
        return json.load(f)


def write_version(version):
    """Persist a version immutably: refuse to overwrite an existing version file."""
    os.makedirs(MAP_DIR, exist_ok=True)
    n = version["version"]
    fname = f"v{n:03d}.json"
    path = os.path.join(MAP_DIR, fname)
    if os.path.exists(path):
        raise SystemExit(f"refusing to overwrite immutable map version {path}")
    with open(path, "w") as f:
        json.dump(version, f, indent=1, default=str)
    manifest = load_manifest()
    manifest.append({"version": n, "effective_from": version["effective_from"],
                     "file": fname, "sha256": _sha256(path),
                     "checkpoint_index": version.get("checkpoint_index"),
                     "n_transitions": len(version.get("transitions", [])),
                     "n_dodge": sum(1 for c in version["cells"].values()
                                    if c["state"] == DODGE)})
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=1)
    return path


def load_version(n):
    with open(os.path.join(MAP_DIR, f"v{n:03d}.json")) as f:
        return json.load(f)


def latest_version():
    m = load_manifest()
    return load_version(m[-1]["version"]) if m else None


def current_map(at_ts):
    """The map version effective at ISO-8601 `at_ts` (the latest with eff_from ≤ at_ts)."""
    m = load_manifest()
    eligible = [e for e in m if e["effective_from"] <= at_ts]
    if not eligible:
        return None
    return load_version(max(eligible, key=lambda e: e["effective_from"])["version"])


# ------------------------- seed map v1 from the slice study ----------------------------
def _slice_to_metrics(cells):
    """slice_study.json cells → {key: metrics}. Verdict → binding state; †/UNSTABLE and
    drift-defined cells are NEUTRAL for binding (they nominate, never bind)."""
    whole = {}
    for c in cells:
        key = cell_key(c["pop"], c["dim"], c["cell"])
        whole[key] = {
            "pop": c["pop"], "dim": c["dim"], "cell": c["cell"],
            "n_events": c["n_events"], "roi": c.get("roi"),
            "roi_lb": c.get("roi_lb"), "roi_ub": c.get("roi_ub"),
            "surplus": c.get("surplus"), "p_emp": c.get("p_emp"),
            "fdr_pass": c.get("fdr_pass", False),
            "splits": max(c.get("days_pos", 0), c.get("regimes_pos", 0)),
            "freq_recent": c.get("freq_recent", 0.0),
            "unstable": c.get("unstable", False),
            "at_fire_true": not c.get("capped", False),
        }
    return whole


def seed_v1(slice_json_path, effective_from=V1_EFFECTIVE):
    with open(slice_json_path) as f:
        art = json.load(f)
    whole = _slice_to_metrics(art["cells"])
    # v1: no prior state — states derived directly from the pinned verdicts via ENTRY on
    # the whole record (recent == whole at seed), so the seed is reproducible from the map
    # rules, not hand-copied.
    v1 = step(None, whole, whole, checkpoint_idx=1, effective_from=effective_from,
              meta={"source": "slice_study.json (entry 10)",
                    "seed_note": "map v1 — entry-10 verdicts, effective 2026-07-02T16:45Z",
                    "slice_meta": art.get("meta", {})})
    return v1


# --------------------------------- self-test ------------------------------------------
def _m(pop, dim, cell, n, roi_ub=None, roi_lb=None, fdr=False, splits=0, freq=0.0,
       unstable=False, at_fire=True):
    return {"pop": pop, "dim": dim, "cell": cell, "n_events": n, "roi_ub": roi_ub,
            "roi_lb": roi_lb, "fdr_pass": fdr, "splits": splits, "freq_recent": freq,
            "unstable": unstable, "at_fire_true": at_fire, "roi": None, "surplus": None,
            "p_emp": None}


def selftest():
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("pass" if cond else "FAIL") + ": " + msg)
        ok = ok and cond

    K = cell_key("strict", "regime", "tennis")

    # (a) NEUTRAL → DODGE on injected reliable loss (whole roi_ub < 0, N ≥ 20).
    v1 = step(None, {K: _m("strict", "regime", "tennis", 40, roi_ub=-0.10)},
              {K: _m("strict", "regime", "tennis", 40, roi_ub=-0.10)},
              1, "2026-07-02T16:45:00Z")
    check(v1["cells"][K]["state"] == DODGE, "(a) enter DODGE on injected reliable loss")

    # (b) DODGE → NEUTRAL rehab when the RECENT window flips positive (N_recent ≥ 20).
    v2 = step(v1, {K: _m("strict", "regime", "tennis", 60, roi_ub=-0.05)},
              {K: _m("strict", "regime", "tennis", 30, roi_ub=+0.08)},
              2, "2026-07-09T16:45:00Z")
    check(v2["cells"][K]["state"] == NEUTRAL and not v2["cells"][K]["stale"],
          "(b) rehabilitate DODGE when recent window flips positive")

    # (c) NOT rehab on data silence (N_recent < 20) ⇒ HOLD DODGE + STALE.
    v2s = step(v1, {K: _m("strict", "regime", "tennis", 60, roi_ub=-0.05)},
               {K: _m("strict", "regime", "tennis", 5, roi_ub=+0.20)},
               2, "2026-07-09T16:45:00Z")
    check(v2s["cells"][K]["state"] == DODGE and v2s["cells"][K]["stale"],
          "(c) silence (N_recent<20) holds DODGE and flags STALE, not rehab")

    # (d) THRASH freeze on alternating evidence (flip at two consecutive checkpoints).
    a1 = step(None, {K: _m("strict", "regime", "tennis", 40, roi_ub=-0.10)},
              {K: _m("strict", "regime", "tennis", 40, roi_ub=-0.10)},
              1, "2026-07-02T16:45:00Z")            # NEUTRAL→DODGE (flip #1)
    a2 = step(a1, {K: _m("strict", "regime", "tennis", 60, roi_ub=-0.05)},
              {K: _m("strict", "regime", "tennis", 30, roi_ub=+0.08)},
              2, "2026-07-09T16:45:00Z")            # DODGE→NEUTRAL (flip #2) ⇒ THRASH
    check(a2["cells"][K]["thrash"] and a2["cells"][K]["state"] == NEUTRAL,
          "(d) two consecutive flips ⇒ frozen NEUTRAL + THRASH")
    a3 = step(a2, {K: _m("strict", "regime", "tennis", 80, roi_ub=-0.12)},
              {K: _m("strict", "regime", "tennis", 40, roi_ub=-0.12)},
              3, "2026-07-16T16:45:00Z")            # would re-enter DODGE — but sticky
    check(a3["cells"][K]["state"] == NEUTRAL and a3["cells"][K]["thrash"],
          "(d') THRASH is sticky — cell stays frozen NEUTRAL on later strong evidence")

    # (e) ZERO transitions on stable-noise fixtures (the K2 bar): metrics that never meet
    # any entry criterion, held across three checkpoints.
    noise = {cell_key("strict", "regime", f"n{i}"):
             _m("strict", "regime", f"n{i}", 40, roi_ub=+0.05, roi_lb=-0.05, fdr=False)
             for i in range(12)}
    n1 = step(None, noise, noise, 1, "2026-07-02T16:45:00Z")
    n2 = step(n1, noise, noise, 2, "2026-07-09T16:45:00Z")
    n3 = step(n2, noise, noise, 3, "2026-07-16T16:45:00Z")
    total_tx = len(n1["transitions"]) + len(n2["transitions"]) + len(n3["transitions"])
    check(total_tx == 0, f"(e) stable-noise fixture ⇒ 0 transitions (got {total_tx})")

    # (e') a PRIORITIZE cell survives on a still-qualifying recent window (no false demote).
    P = cell_key("favorite", "horizon", "<6h")
    pw = _m("favorite", "horizon", "<6h", 84, roi_lb=+0.07, fdr=True, splits=4, freq=20.0)
    p1 = step(None, {P: pw}, {P: pw}, 1, "2026-07-02T16:45:00Z")
    p2 = step(p1, {P: pw}, {P: _m("favorite", "horizon", "<6h", 30, roi_lb=+0.05,
                                  fdr=True, splits=3, freq=8.0)},
              2, "2026-07-09T16:45:00Z")
    check(p1["cells"][P]["state"] == PRIORITIZE and p2["cells"][P]["state"] == PRIORITIZE,
          "(e') PRIORITIZE holds while recent window still qualifies")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
    elif "--seed" in sys.argv:
        slice_json = os.path.join(HERE, "..", "reports", "slice_study.json")
        v1 = seed_v1(slice_json)
        path = write_version(v1)
        nd = sum(1 for c in v1["cells"].values() if c["state"] == DODGE)
        npri = sum(1 for c in v1["cells"].values() if c["state"] == PRIORITIZE)
        print(f"seeded map v1 → {path}")
        print(f"  effective_from {v1['effective_from']} · {len(v1['cells'])} cells · "
              f"{npri} PRIORITIZE · {nd} DODGE")
        for c in v1["cells"].values():
            if c["state"] == DODGE:
                print(f"  DODGE  {c['pop']}|{c['dim']}|{c['cell']}  "
                      f"roi_ub={_p(c['evidence_whole'],'roi_ub')} "
                      f"N={c['evidence_whole']['n_events']}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
