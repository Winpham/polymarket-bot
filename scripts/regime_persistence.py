#!/usr/bin/env python3
"""
CROSS-REGIME PERSISTENCE — the binding stationarity test. Extends persistence_tracker.py from a
pure TEMPORAL out-of-sample split to a TEMPORAL + CROSS-REGIME test whose verdict rests ONLY on
`recurring` regimes (expiring regimes are reported but EXCLUDED — the crux, PREREG §4/§6).

Two legs, BOTH required for PERSISTS:

  leg (a) TEMPORAL — reuse persistence_tracker's leak-free cutoff split and its FROZEN constants
     (PERSIST_MIN_CLUSTERS=10, MARGIN=0.03, Z=1.96); read the OUT edge per regime_type; the verdict
     uses RECURRING-regime OUT day-clusters only. PENDING if < floor; PASS if LB(recurring OUT) >
     MARGIN; REFUTED if the recurring OUT upper bound < 0.

  leg (b) CROSS-REGIME TRANSFER — leave-one-recurring-regime-out: fit "edge exists" (matched-baseline
     surplus > 0) on all-but-one recurring regime, test LB>MARGIN on the held-out recurring regime;
     count how many of ≥ TRANSFER_MIN_REGIMES (=2) hold out successfully. Then the MATCHED
     regime-permutation null (permute regime labels, preserving regime SIZES, N=1000×; recompute the
     transfer count) is used as a CONCENTRATION GUARD (corrected direction — see
     PREREG_20260704T192839Z_..._ADDENDUM.md): p_conc = fraction of null draws ≤ real; a CONCENTRATED
     (one-lucky-regime) edge sits in the null's LOWER tail (permutation spreads its mass → inflates
     the null count) ⇒ p_conc<0.05 ⇒ concentration-flagged ⇒ leg(b) fails. leg(b) PASS = count≥2 AND
     NOT concentration-flagged. (An upper-tail "beat" is mechanically impossible for a distributed
     edge; the D29 MM-filter lesson — a transfer claim must beat a matched null — is served by this
     guard PLUS leg (a)'s temporal out-of-sample evidence.)

Verdict ladder (PREREG §6, on recurring evidence): SOCCER-ARTIFACT / PENDING / PERSISTS(-NET, the
net_positive leg is Item 4) / REFUTED. Reuses regime_edge (baseline + event extraction + cluster
count + concentration) and persistence_tracker (constants) byte-identically. Read-only, paper-only.

Modes:
  ./regime_persistence.py                # live; default cutoff = median day; writes JSON
  ./regime_persistence.py --cutoff DATE  # OUT = rows on/after DATE
  ./regime_persistence.py --selftest     # PERSISTS / SOCCER-ARTIFACT / PENDING / REFUTED all exercised
"""

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_edge as reg           # _matched_baseline, _events, _regime_read, _band_spreads, ARMS, Z, MARGIN
import persistence_tracker as pt    # PERSIST_MIN_CLUSTERS, MARGIN, Z (frozen constants)
import regime_classify as rc

PREREG = "reports/PREREG_20260704T191458Z_regime_persistence.md"
PERSIST_MIN_CLUSTERS = pt.PERSIST_MIN_CLUSTERS   # 10 (frozen, reused)
MARGIN = pt.MARGIN                                # 0.03
Z = pt.Z                                          # 1.96
TRANSFER_MIN_REGIMES = 2                           # PREREG §4/§7
N_PERM_REGIME = 1000                               # PREREG §7
SEED = 20260704                                    # PREREG §7
REPORT_DIR = reg.REPORT_DIR
ARMS = reg.ARMS


def build_events(rows, arm):
    blind = [r for r in rows if r["strategy"] == "_blind"]
    baseline = reg._matched_baseline(blind)
    prows = [r for r in rows if r["strategy"] == arm]
    return reg._events(prows, baseline)


def _read(ev_subset, spreads):
    """Wrap regime_edge._regime_read and add the upper bound (hi = 2·surplus − lb)."""
    r = reg._regime_read(ev_subset, spreads)
    if r is None:
        return None
    r["hi"] = (2 * r["surplus"] - r["lb"]) if r["lb"] is not None else None
    return r


# ---------------------------------------------------------------------------------------------
# leg (a): temporal OUT split, recurring-only verdict.
# ---------------------------------------------------------------------------------------------
def temporal_leg(ev, cutoff, spreads):
    out_ev = {k: v for k, v in ev.items() if v["day"] >= cutoff}
    in_ev = {k: v for k, v in ev.items() if v["day"] < cutoff}
    out_rec = {k: v for k, v in out_ev.items() if not rc.is_expiring_for_verdict(v["regime_type"])}
    out_exp = {k: v for k, v in out_ev.items() if rc.is_expiring_for_verdict(v["regime_type"])}
    rec = _read(out_rec, spreads)
    exp = _read(out_exp, spreads)
    full = _read(out_ev, spreads)
    if rec is None or rec["n_clusters"] < PERSIST_MIN_CLUSTERS:
        verdict = "PENDING"
    elif rec["lb"] is not None and rec["lb"] > MARGIN:
        verdict = "PASS"
    elif rec["hi"] is not None and rec["hi"] < 0:
        verdict = "REFUTED"
    else:
        verdict = "INDETERMINATE"
    return {"cutoff": cutoff, "n_in": len(in_ev), "n_out": len(out_ev),
            "recurring_out": rec, "expiring_out": exp, "all_out": full, "verdict": verdict}


# ---------------------------------------------------------------------------------------------
# leg (b): leave-one-recurring-regime-out transfer + regime-permutation null.
# ---------------------------------------------------------------------------------------------
def _transfer_count(ev_recurring, regime_of, spreads, min_events=2):
    """# of recurring regimes that, when held out, (i) leave a fit pool with surplus>0 and
    (ii) themselves clear LB>MARGIN. Regimes with < min_events are un-testable (can't clear)."""
    regimes = defaultdict(dict)
    for k, v in ev_recurring.items():
        regimes[regime_of[k]][k] = v
    ids = list(regimes)
    count = 0
    detail = {}
    for h in ids:
        held = regimes[h]
        fit = {k: v for rid in ids if rid != h for k, v in regimes[rid].items()}
        held_r = _read(held, spreads)
        fit_r = _read(fit, spreads) if fit else None
        edge_on_fit = (fit_r is not None and fit_r["surplus"] > 0)
        clears = (len(held) >= min_events and held_r is not None
                  and held_r["lb"] is not None and held_r["lb"] > MARGIN)
        ok = bool(edge_on_fit and clears)
        detail[h] = {"n_events": len(held),
                     "held_surplus": None if held_r is None else held_r["surplus"],
                     "held_lb": None if held_r is None else held_r["lb"],
                     "fit_surplus": None if fit_r is None else fit_r["surplus"],
                     "transfers": ok}
        count += int(ok)
    return count, detail


def transfer_leg(ev, spreads, rng):
    ev_rec = {k: v for k, v in ev.items() if not rc.is_expiring_for_verdict(v["regime_type"])}
    regime_of = {k: v["regime_id"] for k, v in ev_rec.items()}
    n_regimes = len(set(regime_of.values()))
    real_count, detail = _transfer_count(ev_rec, regime_of, spreads)

    # matched regime-permutation null: keep regime SIZES, randomly reassign events → recompute count.
    keys = list(ev_rec.keys())
    sizes = defaultdict(int)
    for rid in regime_of.values():
        sizes[rid] += 1
    labels = []
    for rid, n in sizes.items():
        labels += [rid] * n
    null_counts = []
    if n_regimes >= 2 and len(keys) >= 2:
        for _ in range(N_PERM_REGIME):
            perm = labels[:]
            rng.shuffle(perm)
            pmap = {keys[i]: perm[i] for i in range(len(keys))}
            c, _ = _transfer_count(ev_rec, pmap, spreads)
            null_counts.append(c)
    # Corrected v2 (ADDENDUM 20260704T192839Z): the regime-label null is a CONCENTRATION guard.
    # p_conc = fraction of null draws ≤ real; real in the LOWER tail (p_conc<0.05) ⇒ concentration
    # artifact. leg(b) PASS = count≥min AND NOT concentration-flagged. (An upper-tail "beat" is
    # mechanically impossible for a distributed edge — permutation spreads mass and inflates the
    # null count; documented in the ADDENDUM.)
    p_conc = (sum(1 for c in null_counts if c <= real_count) / len(null_counts)) if null_counts else None
    concentration_flagged = (p_conc is not None and p_conc < 0.05)
    passes = (real_count >= TRANSFER_MIN_REGIMES and not concentration_flagged and p_conc is not None)
    null_dist = {}
    for c in null_counts:
        null_dist[c] = null_dist.get(c, 0) + 1
    return {"n_recurring_regimes": n_regimes, "real_transfer_count": real_count,
            "required": TRANSFER_MIN_REGIMES, "p_conc": p_conc,
            "concentration_flagged": concentration_flagged,
            "null_mean": (float(np.mean(null_counts)) if null_counts else None),
            "null_dist": {str(k): v for k, v in sorted(null_dist.items())},
            "per_regime": detail, "passes": passes}


# ---------------------------------------------------------------------------------------------
def verdict_ladder(temporal, transfer, expiring_edge_share):
    """PREREG §6, on recurring evidence. PERSISTS here still needs Item 4 net_positive → PERSISTS-NET."""
    a_pass = temporal["verdict"] == "PASS"
    a_refuted = temporal["verdict"] == "REFUTED"
    b_pass = transfer["passes"]
    rec_below_floor = (temporal["verdict"] == "PENDING"
                       or transfer["n_recurring_regimes"] < TRANSFER_MIN_REGIMES
                       or transfer["real_transfer_count"] < TRANSFER_MIN_REGIMES)
    expiring_carried = expiring_edge_share is not None and expiring_edge_share >= 0.5

    if a_refuted:
        return "REFUTED", "recurring OUT-of-sample upper bound < 0 — the edge decayed out of sample on recurring regimes"
    if a_pass and b_pass:
        return "PERSISTS", ("both legs pass on recurring regimes — PERSISTS-NET pending Item 4's "
                            "net_positive check on ≥2 recurring regimes")
    if rec_below_floor:
        if expiring_carried:
            return "SOCCER-ARTIFACT", (f"edge is expiring-carried ({expiring_edge_share:.0%} of edge mass) and "
                                       f"recurring regimes are below the floor — not yet certifiable")
        return "PENDING", "recurring regimes below the cluster/transfer floor — the accrual wall"
    if expiring_carried:
        return "SOCCER-ARTIFACT", (f"edge is expiring-carried ({expiring_edge_share:.0%}) and the recurring "
                                   f"legs are inconclusive")
    return "PENDING", "recurring evidence accrued but inconclusive — keep accruing"


def analyze(rows, cutoff=None, spreads=None):
    import random
    if spreads is None:
        spreads = reg._band_spreads()
    rng = random.Random(SEED)
    # concentration (expiring edge share) comes from regime_edge, single source of truth.
    edge = reg.analyze(rows, spreads=spreads)
    out = {"meta": {"prereg": PREREG, "persist_min_clusters": PERSIST_MIN_CLUSTERS,
                    "margin": MARGIN, "transfer_min_regimes": TRANSFER_MIN_REGIMES,
                    "n_perm_regime": N_PERM_REGIME, "seed": SEED}, "arms": {}}
    for arm in ARMS:
        ev = build_events(rows, arm)
        if not ev:
            out["arms"][arm] = {"n_events": 0, "note": "no resolved data (arm empty) → PENDING"}
            continue
        days = sorted({v["day"] for v in ev.values()})
        cut = cutoff or (days[len(days) // 2] if len(days) > 1 else days[0])
        temporal = temporal_leg(ev, cut, spreads)
        transfer = transfer_leg(ev, spreads, rng)
        exp_share = edge["arms"].get(arm, {}).get("concentration", {}).get("expiring_edge_mass_share")
        vd, why = verdict_ladder(temporal, transfer, exp_share)
        out["arms"][arm] = {"n_events": len(ev), "cutoff": cut, "temporal": temporal,
                            "transfer": transfer, "expiring_edge_mass_share": exp_share,
                            "verdict": vd, "why": why}
    return out


def _f(x, spec="+.2%"):
    return "  n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, spec)


def run_live(cutoff=None):
    rows = reg.smod.fetch()
    res = analyze(rows, cutoff=cutoff)
    print("CROSS-REGIME PERSISTENCE · temporal + cross-regime transfer · verdict on RECURRING regimes only")
    print(f"  frozen: {PREREG} · floor {PERSIST_MIN_CLUSTERS} OUT clusters · transfer ≥{TRANSFER_MIN_REGIMES} regimes · "
          f"perm null {N_PERM_REGIME}×\n")
    for arm in ARMS:
        a = res["arms"][arm]
        if a.get("n_events", 0) == 0:
            print(f"── {arm}: {a['note']} ──\n")
            continue
        t = a["temporal"]; tr = a["transfer"]
        rec = t["recurring_out"]; exp = t["expiring_out"]
        print(f"── {arm} · cutoff {a['cutoff']} (OUT = on/after) · {t['n_in']} IN / {t['n_out']} OUT events ──")
        print(f"  leg(a) TEMPORAL — recurring OUT: "
              + (f"{rec['n_clusters']} clusters · surplus {_f(rec['surplus'])} · CR LB {_f(rec['lb'])} → {t['verdict']}"
                 if rec else f"no recurring OUT events → {t['verdict']}"))
        if exp:
            print(f"                    (expiring OUT, reported/excluded: {exp['n_clusters']} clusters · surplus {_f(exp['surplus'])})")
        print(f"  leg(b) TRANSFER — {tr['n_recurring_regimes']} recurring regimes · real transfer count "
              f"{tr['real_transfer_count']}/{tr['required']} · concentration-guard p_conc {_f(tr['p_conc'],'.3f')} "
              f"(null mean {_f(tr['null_mean'],'.2f')}, flagged={tr['concentration_flagged']}) → {'PASS' if tr['passes'] else 'fail'}")
        for rid, d in sorted(tr["per_regime"].items(), key=lambda kv: -(kv[1]['n_events'])):
            print(f"      hold-out {rid:<24} n={d['n_events']:>2} held-surplus {_f(d['held_surplus'])} "
                  f"LB {_f(d['held_lb'])} fit {_f(d['fit_surplus'])} → {'transfers' if d['transfers'] else 'no'}")
        print(f"  null distribution (transfer count → freq): {tr['null_dist']}")
        print(f"\n  VERDICT [{arm}]: {a['verdict']} — {a['why']}\n")
    out = os.path.join(REPORT_DIR, "regime_persistence.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"artifact → reports/regime_persistence.json")
    return res


# ---------------------------------------------------------------------------------------------
# Self-test: all four verdicts on synthetic favorite events.
# ---------------------------------------------------------------------------------------------
def _ev(regime_id, sport, rtype, surplus, day):
    return {"surplus": float(surplus), "entry": 0.75, "day": day, "month": day[:7],
            "regime_id": regime_id, "sport": sport, "regime_type": rtype}


def _synth(kind, rng):
    """Build an event dict {ev_key: fields}. Days 2026-07-01..20 (OUT = day>=11 → 10 OUT days)."""
    days = [f"2026-07-{d:02d}" for d in range(1, 21)]
    ev = {}
    idx = 0
    def add(rid, sport, rtype, mu, sd, days_used, n_per_day):
        nonlocal idx
        for day in days_used:
            for _ in range(n_per_day):
                ev[f"e{idx}"] = _ev(rid, sport, rtype, rng.gauss(mu, sd), day)
                idx += 1
    if kind == "persist":
        # 3 clean strong recurring regimes present on ALL days (incl. all 10 OUT days), none
        # concentrated. Real LOO: each holds out → count 3 ≥ 2. Regime-label permutation of 3 equal
        # regimes reproduces count 3 → real NOT in the null's lower tail (p_conc=1.0) → not
        # concentration-flagged → leg(b) PASS; legA PASS (10 OUT clusters, LB>margin) → PERSISTS.
        for rid, sport in (("mlb|2026-07", "mlb"), ("nba/cbb|2026-07", "nba/cbb"), ("nhl|2026-07", "nhl")):
            add(rid, sport, "recurring", 0.16, 0.03, days, 4)
    elif kind == "soccer":
        # edge ONLY in one expiring regime (soccer=WC); recurring flat/thin.
        add("soccer|2026-07", "soccer", "expiring", 0.14, 0.04, days, 6)
        add("mlb|2026-07", "mlb", "recurring", 0.00, 0.04, days[:3], 2)      # thin flat recurring
    elif kind == "pending":
        # recurring edge present but only 3 OUT clusters (below the 10 floor); NO expiring regime.
        add("mlb|2026-07", "mlb", "recurring", 0.15, 0.03, days[10:13], 5)   # 3 OUT days only
        add("nba/cbb|2026-07", "nba/cbb", "recurring", 0.15, 0.03, days[10:13], 5)
    elif kind == "refuted":
        # recurring edge IN-sample, decays sharply OUT (upper bound < 0) across ≥10 OUT clusters.
        add("mlb|2026-07", "mlb", "recurring", 0.15, 0.03, days[:10], 6)     # IN: strong
        add("mlb|2026-07", "mlb", "recurring", -0.14, 0.02, days[10:], 8)    # OUT: decayed hard, tight
        add("nba/cbb|2026-07", "nba/cbb", "recurring", -0.14, 0.02, days[10:], 8)
    return ev


def _selftest():
    import random
    ok = True
    spreads = {}
    for kind, want in (("persist", "PERSISTS"), ("soccer", "SOCCER-ARTIFACT"),
                       ("pending", "PENDING"), ("refuted", "REFUTED")):
        rng = random.Random(SEED)
        ev = _synth(kind, random.Random(99))
        # temporal cutoff = day 11 (OUT = days 11..20)
        temporal = temporal_leg(ev, "2026-07-11", spreads)
        transfer = transfer_leg(ev, spreads, rng)
        # expiring edge share for the ladder
        exp_mass = sum(abs(v["surplus"]) for v in ev.values() if rc.is_expiring_for_verdict(v["regime_type"]))
        tot = sum(abs(v["surplus"]) for v in ev.values()) or 1.0
        vd, why = verdict_ladder(temporal, transfer, exp_mass / tot)
        good = vd == want
        ok = ok and good
        rec = temporal["recurring_out"]
        rec_s = "no-rec-out" if rec is None else f"{rec['n_clusters']}cl LB {_f(rec['lb'])}"
        print(f"  [{'ok' if good else 'FAIL'}] {kind:<8} → {vd:<16} (want {want}) · "
              f"legA {temporal['verdict']}/{rec_s} · legB {transfer['real_transfer_count']}/{transfer['required']} "
              f"p_conc={_f(transfer['p_conc'],'.3f')} pass={transfer['passes']}")

    # empty-arm graceful (proven_router-like)
    res = analyze([{"strategy": "_blind", "slug": "mlb-a-b-2026-07-01", "title": "A vs B", "event_slug": "mlb-a-b-2026-07-01",
                    "condition_id": "x", "entry": 0.75, "won": 1, "day": "2026-07-01"}], spreads={})
    c_empty = res["arms"]["proven_router"]["n_events"] == 0
    ok = ok and c_empty
    print(f"  [{'ok' if c_empty else 'FAIL'}] empty arm → n_events 0 (graceful)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    cutoff = None
    if "--cutoff" in sys.argv:
        cutoff = sys.argv[sys.argv.index("--cutoff") + 1]
    run_live(cutoff)
