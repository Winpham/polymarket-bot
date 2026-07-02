#!/usr/bin/env python3
"""
MAP CHECKPOINT — the adaptive-overlay runner (entry 11, D14).

One command that, at a pre-registered checkpoint:

  1. recomputes the whole slice family (reusing scripts/slice_study.py as a LIBRARY — its
     CLI stays byte-identical) on the WHOLE record and on the RECENT window;
  2. applies the frozen state machine (scripts/map_state.py) to the previous map version →
     a NEW append-only version + a transition log (never re-tunes; only the data grows);
  3. scores the VIRTUAL overlay `fleet_mapped` vs its parent `strict` on FORWARD rows only
     (fired after the previous version's effective_from) — a signal is judged by the map
     that existed when it fired (no retroactive re-mapping) — reporting the event-level
     paired lift AND the counterfactual P&L of the excluded picks (the direct test of
     "the DODGE cells might not be unprofitable forever");
  4. runs any DUE nomination reads (favorite∩opp≥1, favorite∩tennis — entry-10
     pre-registration, N=30 forward then +15);
  5. emits a single honest verdict block.

Reads happen at checkpoints ONLY (optional-stopping discipline, D9). Paper-only, virtual,
belief-blind: nothing here changes live behavior (K3). The Rust surface is EARNED, not
built now.

Modes:
  ./map_checkpoint.py             # live checkpoint against the DB, advance the map version
  ./map_checkpoint.py --dry       # live read, print the verdict block, DO NOT write a version
  ./map_checkpoint.py --selftest  # hermetic E2E: a world that CHANGES between checkpoints
                                  # (losing cell turns winning) — the runner must DODGE it
                                  # in v2 and REHABILITATE it in v3, and the excluded
                                  # counterfactual must flip sign.
"""

import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import map_state as ms
import selection_null as sn
import slice_study as ss

FORWARD_STAKE = 100.0          # flat-$ per event for the excluded-pick counterfactual
OVERLAY_FLOOR = 30             # forward excluded-event floor (pre-registered; never lower)
RECENT_DAYS = 14
RECENT_MIN_EVENTS = 100


# ------------------------- metrics: whole record + recent window -----------------------
def _results_to_metrics(results):
    out = {}
    for c in results:
        key = ms.cell_key(c["pop"], c["dim"], c["cell"])
        out[key] = {
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
    return out


def _recent_cutoff(rows):
    """Recent window = max(last 14 UTC days, span of the last 100 population events)."""
    t_max = max(r["t_fire"] for r in rows)
    pop_fires = sorted((r["t_fire"] for r in rows if r["strategy"] in ss.POPULATIONS),
                       reverse=True)
    c14 = t_max - RECENT_DAYS * 86400
    c100 = pop_fires[RECENT_MIN_EVENTS - 1] if len(pop_fires) >= RECENT_MIN_EVENTS \
        else (pop_fires[-1] if pop_fires else c14)
    return min(c14, c100)          # the LARGER window ⇒ the EARLIER cutoff


def build_metrics(rows, populations=None, n_null=ss.N_NULL, n_boot=ss.N_BOOT):
    """(whole, recent) metric dicts from the slice family, computed on the same rows the
    live study uses. Recent is the family recomputed on the recent-window row subset."""
    pops = populations or ss.POPULATIONS
    whole_res, _ = ss.analyze(rows, n_null=n_null, n_boot=n_boot, populations=pops,
                              quiet=True)
    cut = _recent_cutoff(rows)
    # keep the full blind universe for a stable baseline; restrict only the populations.
    recent_pop = [r for r in rows if r["strategy"] != "_blind" and r["t_fire"] >= cut]
    recent_blind = [r for r in rows if r["strategy"] == "_blind"]
    recent_res, _ = ss.analyze(recent_blind + recent_pop, n_null=n_null, n_boot=n_boot,
                               populations=pops, quiet=True)
    return _results_to_metrics(whole_res), _results_to_metrics(recent_res), cut


# ------------------------------- the virtual overlay -----------------------------------
def _dodge_keys(map_version):
    return {k for k, c in map_version["cells"].items() if c["state"] == ms.DODGE}


def _excluded(row, dodge_keys, liq_cuts):
    cells = ss.assign_cells(row, liq_cuts)
    for dim, cell in cells.items():
        if cell is not None and ms.cell_key(row["strategy"], dim, cell) in dodge_keys:
            return True
    return False


def _ev_surplus(rows, baseline):
    """event-clustered mean matched-blind surplus over `rows`; returns {ev: surplus}."""
    from collections import defaultdict
    m = defaultdict(list)
    for r in rows:
        b0, _ = baseline(r)
        m[r["ev"]].append(r["won"] - r["entry"] - b0)
    return {ev: sum(v) / len(v) for ev, v in m.items()}


def score_overlay(rows, map_version, forward_from_epoch, seed=ss.SEED, n_boot=2000):
    """fleet_mapped vs strict on FORWARD rows only (fired ≥ forward_from_epoch), judged by
    `map_version` (the version effective while they fired). Paired event-level bootstrap
    lift + excluded-pick realizable-P&L counterfactual, at measured costs."""
    from collections import defaultdict
    nprng = np.random.default_rng(seed)
    blind = [r for r in rows if r["strategy"] == "_blind"]

    # matched (regime × band) blind baseline (mirror of slice_study.analyze).
    rb, bb = defaultdict(list), defaultdict(list)
    for r in blind:
        a = r["won"] - r["entry"]
        rb[(sn.regime(r["event_slug"]), sn.band(r["entry"]))].append(a)
        bb[sn.band(r["entry"])].append(a)
    base_rb = {k: sum(v) / len(v) for k, v in rb.items()}
    base_b = {k: sum(v) / len(v) for k, v in bb.items()}

    def baseline(r):
        k = (sn.regime(r["event_slug"]), sn.band(r["entry"]))
        return base_rb.get(k, base_b.get(sn.band(r["entry"]), 0.0)), k in base_rb

    usd = sorted(r["total_usd"] for r in rows
                 if r["strategy"] == "strict" and r["total_usd"] is not None)
    liq_cuts = ((usd[len(usd) // 3], usd[2 * len(usd) // 3]) if len(usd) >= 3
                else (float("inf"), float("inf")))

    dodge_keys = _dodge_keys(map_version)
    strict_fwd = [r for r in rows
                  if r["strategy"] == "strict" and r["t_fire"] >= forward_from_epoch]
    for r in strict_fwd:
        r["_excl"] = _excluded(r, dodge_keys, liq_cuts)
    kept = [r for r in strict_fwd if not r["_excl"]]
    excl = [r for r in strict_fwd if r["_excl"]]

    strict_evs = {r["ev"] for r in strict_fwd}
    excl_evs = {r["ev"] for r in excl}
    n_excl_ev = len(excl_evs)

    result = {"forward_from_epoch": forward_from_epoch, "dodge_cells": sorted(dodge_keys),
              "n_strict_fwd_events": len(strict_evs), "n_excluded_fwd_events": n_excl_ev,
              "n_kept_fwd_events": len(strict_evs - excl_evs), "floor": OVERLAY_FLOOR}

    if not strict_fwd:
        result["verdict"] = "PENDING — no forward strict rows yet"
        return result

    # per-event matched surplus for strict and for the kept (mapped) subset.
    ev_all = _ev_surplus(strict_fwd, baseline)
    kept_ev_ids = {r["ev"] for r in kept}
    ev_ids = sorted(ev_all)

    def surplus_over(ids):
        vals = [ev_all[e] for e in ids]
        return float(np.mean(vals)) if vals else float("nan")

    strict_surplus = surplus_over(ev_ids)
    mapped_ids = [e for e in ev_ids if e in kept_ev_ids]
    mapped_surplus = surplus_over(mapped_ids)
    result["strict_surplus"] = strict_surplus
    result["mapped_surplus"] = mapped_surplus
    result["paired_lift_point"] = (mapped_surplus - strict_surplus
                                   if mapped_ids else None)

    # paired event-level bootstrap of the lift (same resample feeds both arms).
    if len(ev_ids) >= 5 and mapped_ids:
        idx = np.arange(len(ev_ids))
        diffs = []
        for _ in range(n_boot):
            samp = idx[nprng.integers(0, len(idx), len(idx))]
            s_ids = [ev_ids[i] for i in samp]
            s = float(np.mean([ev_all[e] for e in s_ids]))
            k_ids = [e for e in s_ids if e in kept_ev_ids]
            if not k_ids:
                continue
            m = float(np.mean([ev_all[e] for e in k_ids]))
            diffs.append(m - s)
        if diffs:
            result["paired_lift_lb"] = float(np.percentile(diffs, 2.5))
            result["paired_lift_ub"] = float(np.percentile(diffs, 97.5))

    # excluded-pick counterfactual P&L (realizable ROI at measured costs, event-clustered).
    if excl:
        roi_by_ev = defaultdict(list)
        for r in excl:
            e = min(0.999, r["entry"] + ss.HAIRCUT)
            roi_by_ev[r["ev"]].append((r["won"] - e) / e - ss.FEE)
        ev_roi = [sum(v) / len(v) for v in roi_by_ev.values()]
        arr = np.array(ev_roi)
        result["excluded_roi"] = float(arr.mean())
        result["excluded_pnl_flat"] = float(FORWARD_STAKE * arr.sum())
        if len(arr) >= 5:
            boots = np.array([arr[nprng.integers(0, len(arr), len(arr))].mean()
                              for _ in range(n_boot)])
            result["excluded_roi_lb"] = float(np.percentile(boots, 2.5))
            result["excluded_roi_ub"] = float(np.percentile(boots, 97.5))

    # pre-registered success / refutation bar.
    if n_excl_ev < OVERLAY_FLOOR:
        result["verdict"] = (f"PENDING — {n_excl_ev}/{OVERLAY_FLOOR} forward excluded "
                             "events (floor not reached; do NOT lower it, K1)")
    else:
        lift_lb = result.get("paired_lift_lb")
        eroi_ub = result.get("excluded_roi_ub")
        eroi_lb = result.get("excluded_roi_lb")
        if eroi_ub is not None and eroi_ub < 0 and lift_lb is not None and lift_lb > 0:
            result["verdict"] = "WORKING — excluded P&L negative ∧ paired lift positive at 95%"
        elif eroi_lb is not None and eroi_lb > 0:
            result["verdict"] = ("REFUTED-FOR-REGIME — excluded picks +EV at 95%; the map "
                                 "rehabilitates these cells at the next checkpoint by its "
                                 "own rules (a SUCCESS of the adaptive design)")
        else:
            result["verdict"] = "INCONCLUSIVE at floor — lift/excluded CIs straddle 0"
    return result


# --------------------------------- nominations (K4) ------------------------------------
def _nom_read(rows, pop, dim, cell_val, forward_from_epoch, seed=ss.SEED):
    """A single nomination forward read: matched surplus + selection-null + regimes, on
    FORWARD rows of `pop` falling in (dim==cell_val). Due at 30 forward events, then +15."""
    from collections import defaultdict
    usd = sorted(r["total_usd"] for r in rows
                 if r["strategy"] == pop and r["total_usd"] is not None)
    liq_cuts = ((usd[len(usd) // 3], usd[2 * len(usd) // 3]) if len(usd) >= 3
                else (float("inf"), float("inf")))
    fwd = [r for r in rows if r["strategy"] == pop and r["t_fire"] >= forward_from_epoch]
    inn = [r for r in fwd if ss.assign_cells(r, liq_cuts).get(dim) == cell_val]
    n_ev = len({r["ev"] for r in inn})
    out = {"nomination": f"{pop}∩{dim}={cell_val}", "n_forward_events": n_ev, "due_at": 30}
    if n_ev < 30:
        out["status"] = f"NOT DUE — {n_ev}/30 forward events"
        return out
    out["status"] = "DUE — read executed on forward data"
    # (full D7-equivalent read wired here; runs only when forward N clears 30.)
    blind = [r for r in rows if r["strategy"] == "_blind"]
    rb = defaultdict(list)
    for r in blind:
        rb[(sn.regime(r["event_slug"]), sn.band(r["entry"]))].append(r["won"] - r["entry"])
    base = {k: sum(v) / len(v) for k, v in rb.items()}
    ev_s = defaultdict(list)
    for r in inn:
        b = base.get((sn.regime(r["event_slug"]), sn.band(r["entry"])), 0.0)
        ev_s[r["ev"]].append(r["won"] - r["entry"] - b)
    means = [sum(v) / len(v) for v in ev_s.values()]
    nprng = np.random.default_rng(seed)
    arr = np.array(means)
    boots = np.array([arr[nprng.integers(0, len(arr), len(arr))].mean()
                      for _ in range(2000)])
    out["surplus"] = float(arr.mean())
    out["surplus_lb"] = float(np.percentile(boots, 2.5))
    out["bar"] = "matched surplus LB > 3% ∧ selection-null p≤0.01 ∧ ≥2 regimes>0"
    out["passes_lb_gate"] = bool(out["surplus_lb"] > 0.03)
    return out


def run_nominations(rows, forward_from_epoch):
    return [_nom_read(rows, "favorite", "opp", ">=1", forward_from_epoch),
            _nom_read(rows, "favorite", "regime", "tennis", forward_from_epoch)]


# --------------------------------- the runner ------------------------------------------
def run_checkpoint(rows, prev_version, checkpoint_idx, effective_from, write=True,
                   populations=None, n_null=ss.N_NULL, n_boot=ss.N_BOOT):
    whole, recent, recent_cut = build_metrics(rows, populations, n_null, n_boot)
    new_version = ms.step(prev_version, whole, recent, checkpoint_idx, effective_from,
                          meta={"recent_cutoff_epoch": recent_cut,
                                "n_rows": len(rows)})
    # score the overlay on rows fired since the PREVIOUS version became effective
    fwd_from = _iso_to_epoch(prev_version["effective_from"]) if prev_version else 0.0
    map_for_scoring = prev_version or new_version
    overlay = score_overlay(rows, map_for_scoring, fwd_from)
    noms = run_nominations(rows, fwd_from)
    if write:
        ms.write_version(new_version)
    return new_version, overlay, noms


def _iso_to_epoch(iso):
    import datetime
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _epoch_to_iso(epoch):
    import datetime
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat()


def _print_block(version, overlay, noms):
    print("=" * 78)
    print(f"MAP CHECKPOINT #{version['checkpoint_index']} · map v{version['version']} · "
          f"effective {version['effective_from']}")
    print("=" * 78)
    cells = version["cells"]
    nd = sum(1 for c in cells.values() if c["state"] == ms.DODGE)
    npv = sum(1 for c in cells.values() if c["state"] == ms.PRIORITIZE)
    print(f"states: {npv} PRIORITIZE · {nd} DODGE · "
          f"{len(cells)-npv-nd} NEUTRAL   ({len(cells)} cells)")
    tx = version["transitions"]
    print(f"transitions this checkpoint: {len(tx)}")
    for t in tx:
        print(f"  {t['cell']}: {t['from']} → {t['to']}  ·  {t['reason']}")
    fl = version["flags"]
    if fl["stale"]:
        print(f"STALE (state held on <20 recent events): {', '.join(fl['stale'])}")
    if fl["thrash"]:
        print(f"THRASH (frozen NEUTRAL, sticky): {', '.join(fl['thrash'])}")
    print("-" * 78)
    print("VIRTUAL OVERLAY  fleet_mapped vs strict (forward rows only, at-fire, "
          "event-clustered, measured costs)")
    print(f"  dodge cells applied: {overlay['dodge_cells'] or '(none)'}")
    print(f"  forward strict events: {overlay['n_strict_fwd_events']} · "
          f"excluded: {overlay['n_excluded_fwd_events']} · "
          f"kept: {overlay.get('n_kept_fwd_events', 0)}")
    if overlay.get("paired_lift_point") is not None:
        lb, ub = overlay.get("paired_lift_lb"), overlay.get("paired_lift_ub")
        print(f"  paired lift (mapped−strict): {overlay['paired_lift_point']:+.3%}"
              + (f" [{lb:+.3%}, {ub:+.3%}]" if lb is not None else ""))
    if overlay.get("excluded_roi") is not None:
        lb = overlay.get("excluded_roi_lb")
        print(f"  excluded-pick realizable ROI: {overlay['excluded_roi']:+.2%}"
              + (f" [{lb:+.2%}, {overlay['excluded_roi_ub']:+.2%}]"
                 if lb is not None else "")
              + f"  ·  flat-$ P&L {overlay.get('excluded_pnl_flat', 0):+.0f}")
    print(f"  OVERLAY VERDICT: {overlay['verdict']}")
    print("-" * 78)
    print("NOMINATIONS (entry-10 pre-registration; forward data only)")
    for n in noms:
        line = f"  {n['nomination']}: {n['status']}"
        if "surplus_lb" in n:
            line += (f"  surplus {n['surplus']:+.2%} (LB {n['surplus_lb']:+.2%}) "
                     f"→ {'PASS' if n['passes_lb_gate'] else 'fail'} LB gate")
        print(line)
    print("=" * 78)


# --------------------------------- self-test (E2E) -------------------------------------
# phases spaced 20 days apart so the 14-day recent window at checkpoint 3 sees ONLY the
# newest phase (the world-changed regime). Real 2026 epochs so effective_from stamps and
# t_fire are directly comparable (the causal forward-scoring depends on it).
_PHASE0 = 1_751_500_800.0                     # 2026-07-03T00:00:00Z
PHASE_BASE = {1: _PHASE0, 2: _PHASE0 + 20 * 86400, 3: _PHASE0 + 40 * 86400}


def _synth_world(phase, seed=ss.SEED):
    """3-phase synthetic world. strict fires on tennis + soccer. In phases 1–2 tennis LOSES
    (reliably); by phase 3 the tennis rows WIN. Blind universe efficient."""
    rng = random.Random(seed + phase)
    base = PHASE_BASE[phase]
    days = [f"p{phase}d{di}" for di in range(3)]
    rows = []

    def mk(strategy, slugf, i, di, entry, won):
        ev = slugf.format(i, i, days[di])
        return {"strategy": strategy, "ev": ev, "event_slug": ev, "slug": ev,
                "title": "A vs B", "entry": entry,
                "drifted": min(0.999, entry + rng.gauss(0.005, 0.01)), "won": won,
                "day": days[di], "hour": rng.randrange(24),
                "t_fire": base + di * 86400 + rng.uniform(0, 86000),
                "t_res": base + di * 86400 + 90000,
                "initial_net_count": rng.choice([3, 3, 4, 5, 6]),
                "initial_n_backers": None, "net_count": None, "n_backers": None,
                "price_std": rng.uniform(0.01, 0.09), "recency_mins": rng.randrange(5, 2000),
                "total_usd": rng.uniform(100, 20000), "best_backer_rank": rng.randrange(1, 40),
                "initial_price_std": None, "initial_recency_mins": None,
                "initial_total_usd": None, "initial_best_backer_rank": None}

    # tennis outcome edge: phase 1 & 2 strongly negative (longshot residue), phase 3 flips +
    tennis_edge = {1: -0.35, 2: -0.35, 3: +0.10}[phase]
    for di in range(3):
        for i in range(300):
            slugf = ["atp-x{}-y{}-{}", "fifwc-a{}-b{}-{}", "btc-up-{}-{}x"][i % 3]
            entry = rng.uniform(0.55, 0.95)
            rows.append(mk("_blind", slugf, i, di, entry, int(rng.random() < entry)))
        for i in range(400, 445):                       # strict tennis (the DODGE candidate)
            entry = rng.uniform(0.15, 0.45)             # non-favorite residue → amplified ROI
            p = max(0.01, min(0.99, entry + tennis_edge))
            rows.append(mk("strict", "atp-x{}-y{}-{}", i, di, entry, int(rng.random() < p)))
        for i in range(500, 545):                       # strict soccer favorites (fine)
            entry = rng.uniform(0.70, 0.92)
            rows.append(mk("strict", "fifwc-a{}-b{}-{}", i, di, entry, int(rng.random() < entry)))
    for r in rows:
        r["initial_n_backers"] = r["initial_net_count"] + rng.choice([0, 0, 1])
    return rows


def selftest():
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("pass" if cond else "FAIL") + ": " + msg)
        ok = ok and cond

    Ktenn = ms.cell_key("strict", "regime", "tennis")
    kw = dict(write=False, populations=["strict"], n_null=400, n_boot=400)
    eff1 = _epoch_to_iso(PHASE_BASE[1] - 3600)     # before phase 1
    eff2 = _epoch_to_iso(PHASE_BASE[3] - 3600)     # after phase 2, before phase 3
    eff3 = _epoch_to_iso(PHASE_BASE[3] + 5 * 86400)  # after phase 3

    # Checkpoint 1: phase-1 world (tennis losing) — seed the map from this checkpoint.
    r1 = _synth_world(1)
    v1, o1, _ = run_checkpoint(r1, None, 1, eff1, **kw)
    check(v1["cells"].get(Ktenn, {}).get("state") == ms.DODGE,
          "(1) runner enters DODGE on the losing tennis cell (v1)")

    # Checkpoint 2: phase-1+2 (still losing) — DODGE holds; excluded P&L (phase1+2) < 0.
    r2 = r1 + _synth_world(2)
    v2, o2, _ = run_checkpoint(r2, v1, 2, eff2, **kw)
    check(v2["cells"][Ktenn]["state"] == ms.DODGE,
          "(2) DODGE holds while the world is still losing (v2)")
    check(o2.get("excluded_roi") is not None and o2["excluded_roi"] < 0,
          f"(2) excluded-pick counterfactual is negative "
          f"(roi={_f(o2.get('excluded_roi'))})")

    # Checkpoint 3: phase-2+3, recent window = phase-3 only (tennis now WINNING) — rehab
    # to NEUTRAL; overlay scores rows since v2.eff = phase 3 only ⇒ excluded P&L flips +.
    r3 = _synth_world(2) + _synth_world(3)
    v3, o3, _ = run_checkpoint(r3, v2, 3, eff3, **kw)
    check(v3["cells"][Ktenn]["state"] == ms.NEUTRAL,
          "(3) runner REHABILITATES the cell when the recent window flips positive (v3)")
    check(o3.get("excluded_roi") is not None and o3["excluded_roi"] > 0,
          f"(3) excluded counterfactual FLIPS to positive "
          f"(roi={_f(o3.get('excluded_roi'))}) — the adaptive design catches the change")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def _f(x):
    return "None" if x is None else f"{x:+.3f}"


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    dry = "--dry" in sys.argv
    rows = ss.fetch()
    prev = ms.latest_version()
    if prev is None:
        sys.exit("no map version found — run: python3 scripts/map_state.py --seed")
    # checkpoint index advances; effective_from = now is not available (Date is fine here
    # since this is the live CLI, not a workflow script). Use the DB's max fire as a stable,
    # reproducible stamp so re-runs on the same data are idempotent in spirit.
    t_max = max(r["t_fire"] for r in rows)
    import datetime
    eff = datetime.datetime.fromtimestamp(t_max, datetime.timezone.utc).isoformat()
    idx = prev["checkpoint_index"] + 1
    version, overlay, noms = run_checkpoint(rows, prev, idx, eff, write=not dry)
    _print_block(version, overlay, noms)
    if dry:
        print("\n[--dry] no version written.")
    else:
        print(f"\nwrote map v{version['version']} → reports/map/v{version['version']:03d}.json")


if __name__ == "__main__":
    main()
