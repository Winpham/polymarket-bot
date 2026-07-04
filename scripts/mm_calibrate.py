#!/usr/bin/env python3
"""
mm_calibrate — Tier-1, LABELED calibration of the LIVE microstructure screen (brief §4a).

FIRST DELIVERABLE (the docstring's literal ask): how good are the thresholds ALREADY DEPLOYED —
round_trip_rate<0.30 AND two_sided_rate<0.25 AND sell_buy_ratio<0.50 (consensus.rs:1649-1651)?
We measure their FP/FN against a labeled set, per-axis + ensemble AUC, a label-permutation null,
a threshold grid sweep (freezing tau_2s=0.30 per precedent, floating ≤1 knob), and leave-one-out
stability of any chosen operating point.

LABELED SET (provenance recorded, per brief):
  MM  = economic BUY-BOTH-HOLD arbers, identified by PRICE-SUM economics (median two-leg price
        sum ≤ 1.10 over ≥20 paired markets, both-outcome fraction ≥ 0.50) — the mm_premise_probe.sql
        arb signature, which is ORTHOGONAL to the rate thresholds under test — PLUS the flagship
        $51M churner 0x204f72 (explicit).
  HUM = the two D23 soccer humans 0xe9a6ed2e4d / 0x56f0321917 (+10-11% tax-surviving surplus,
        DECISIONS.md:733) PLUS active directional bettors (both-hold fraction < 0.10, ≥20 UTC days,
        ≥200 fills).

CIRCULARITY CAVEAT (must be read with the result): the HUMAN label leans on a low both-hold
fraction, which is close to the two_sided_rate axis under test, so Tier-1 separation is PARTLY
CIRCULAR and OVER-states discrimination. Tier-1 is NECESSARY, NOT SUFFICIENT. The binding
validation is Tier-2 (mm_persistence_effect.py). The MM side is less circular (price-sum arb is a
distinct economic fact from the three rates).

READ-ONLY. PAPER-ONLY.

Modes:
  ./mm_calibrate.py                 # measure live thresholds + sweep + null + LOO
  ./mm_calibrate.py --nperm K       # permutation draws (default 2000)
  ./mm_calibrate.py --selftest      # separable synthetic must yield AUC~1 and p<0.01
"""

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mm_common as mc

N_PERM = 2000
SEED = 20260704
# live thresholds under test
LIVE = {"rt": 0.30, "ts": 0.25, "sb": 0.50}


def labeled_set():
    """Return {wallet: ('MM'|'HUM', provenance)} with mixed, recorded provenance."""
    arb_sql = """
    WITH legs AS (
      SELECT lower(wallet) wallet, condition_id, outcome_index,
             sum(size_usd)/NULLIF(sum(size_usd/NULLIF(price,0)),0) leg_price
      FROM trader_fills WHERE side='BUY' AND resolved GROUP BY 1,2,3),
    mkt AS (SELECT wallet, condition_id, count(*) n_sides, sum(leg_price) two_leg_sum
            FROM legs GROUP BY 1,2),
    days AS (SELECT lower(wallet) wallet, count(DISTINCT (ts AT TIME ZONE 'UTC')::date) nd,
                    count(*) nf FROM trader_fills WHERE resolved AND side='BUY' GROUP BY 1),
    w AS (SELECT m.wallet, count(*) mkts, count(*) FILTER (WHERE n_sides>=2) both_mkts,
                 percentile_cont(0.5) WITHIN GROUP (ORDER BY two_leg_sum)
                   FILTER (WHERE n_sides>=2) med_sum
          FROM mkt m GROUP BY 1)
    SELECT w.wallet, w.mkts,
           (w.both_mkts::float/NULLIF(w.mkts,0)) both_frac, w.med_sum, d.nd, d.nf
    FROM w JOIN days d USING(wallet);
    """
    labels = {}
    for r in mc.q(arb_sql):
        w = r[0]
        mkts = int(float(r[1])) if r[1] else 0
        bf = mc._fnum(r[2])
        ms = mc._fnum(r[3])
        nd = int(float(r[4])) if r[4] else 0
        nf = int(float(r[5])) if r[5] else 0
        if bf is None:
            continue
        # MM: economic buy-both-hold arb (orthogonal price-sum signature)
        if mkts >= 20 and bf >= 0.50 and ms is not None and ms <= 1.10:
            labels[w] = ("MM", f"arb both_frac={bf:.2f} med_sum={ms:.3f} mkts={mkts}")
        # HUM: active directional bettor (low both-hold), non-arb
        elif bf < 0.10 and nd >= 20 and nf >= 200:
            labels[w] = ("HUM", f"directional both_frac={bf:.2f} n_days={nd} n_fills={nf}")
    # explicit provenance overrides
    for w in list(labels):
        if w.startswith("0x204f72"):
            labels[w] = ("MM", "flagship $51M buy-both-hold churner (mm_premise_probe)")
    for w in mc.microstructure():
        if w.startswith("0xe9a6ed2e4d"):
            labels[w] = ("HUM", "D23 soccer human +11% tax-surviving (DECISIONS.md:733)")
        if w.startswith("0x56f0321917"):
            labels[w] = ("HUM", "D23 soccer human +10% tax-surviving (DECISIONS.md:733)")
    return labels


def _auc(scores, ispos):
    """Mann-Whitney AUC: P(score_pos > score_neg). scores higher = more MM-like."""
    pos = [s for s, y in zip(scores, ispos) if y]
    neg = [s for s, y in zip(scores, ispos) if not y]
    if not pos or not neg:
        return None
    c = 0.0
    for p in pos:
        for n in neg:
            c += 1.0 if p > n else (0.5 if p == n else 0.0)
    return c / (len(pos) * len(neg))


def evaluate(labels, micro):
    lab = [(w, y, micro[w]) for w, (y, _) in labels.items() if w in micro]
    ispos = [y == "MM" for _, y, _ in lab]
    rt = [m["rt"] for _, _, m in lab]
    ts = [m["ts"] for _, _, m in lab]
    sb = [m["sb"] for _, _, m in lab]
    ens = [max(m["rt"] / LIVE["rt"], m["ts"] / LIVE["ts"], m["sb"] / LIVE["sb"])
           for _, _, m in lab]  # >=1 ⇒ live screen flags as churner
    # live-threshold confusion
    tp = fp = tn = fn = 0
    for (_, y, m) in lab:
        flagged = mc.is_churner(m)
        if y == "MM":
            tp += flagged
            fn += not flagged
        else:
            fp += flagged
            tn += not flagged
    return {
        "n_mm": sum(ispos), "n_hum": sum(not x for x in ispos),
        "confusion_live": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "fpr": (fp / (fp + tn)) if (fp + tn) else None,
        "fnr": (fn / (fn + tp)) if (fn + tp) else None,
        "auc_rt": _auc(rt, ispos), "auc_ts": _auc(ts, ispos),
        "auc_sb": _auc(sb, ispos), "auc_ensemble": _auc(ens, ispos),
        "_lab": lab, "_ispos": ispos, "_ens": ens,
    }


def perm_null(ispos, ens, nperm, seed):
    obs = _auc(ens, ispos)
    if obs is None:
        return obs, None
    rng = np.random.default_rng(seed)
    y = np.array(ispos)
    ge = 0
    for _ in range(nperm):
        yp = rng.permutation(y)
        a = _auc(ens, list(yp))
        if a is not None and a >= obs:
            ge += 1
    return obs, (ge + 1) / (nperm + 1)


def sweep_loo(lab, ispos):
    """Freeze tau_2s=0.30 (precedent); float ONE knob (tau_rt) on a grid; report the operating
    point maximising balanced accuracy AND its leave-one-out stability."""
    taus = [round(0.10 + 0.05 * i, 2) for i in range(9)]  # 0.10..0.50

    def bal_acc(t_rt, subset):
        tp = fp = tn = fn = 0
        for (_, y, m) in subset:
            flagged = not (m["rt"] < t_rt and m["ts"] < 0.30 and m["sb"] < LIVE["sb"])
            if y == "MM":
                tp += flagged; fn += not flagged
            else:
                fp += flagged; tn += not flagged
        sens = tp / (tp + fn) if (tp + fn) else 0
        spec = tn / (tn + fp) if (tn + fp) else 0
        return 0.5 * (sens + spec)
    grid = [(t, bal_acc(t, lab)) for t in taus]
    best = max(grid, key=lambda kv: kv[1])
    # LOO: drop each labeled wallet, re-pick best tau; report the spread of chosen tau
    loo_taus = []
    for i in range(len(lab)):
        sub = lab[:i] + lab[i + 1:]
        g = [(t, bal_acc(t, sub)) for t in taus]
        loo_taus.append(max(g, key=lambda kv: kv[1])[0])
    return {"grid": grid, "best_tau_rt": best[0], "best_bal_acc": best[1],
            "loo_tau_min": min(loo_taus), "loo_tau_max": max(loo_taus),
            "loo_tau_std": float(np.std(loo_taus))}


def run(nperm=N_PERM, quiet=False):
    labels = labeled_set()
    micro = mc.microstructure()
    ev = evaluate(labels, micro)
    obs_auc, p = perm_null(ev["_ispos"], ev["_ens"], nperm, SEED)
    sw = sweep_loo(ev["_lab"], ev["_ispos"])
    res = {
        "n_mm": ev["n_mm"], "n_hum": ev["n_hum"],
        "live_thresholds": LIVE,
        "confusion_live": ev["confusion_live"],
        "false_positive_rate": ev["fpr"], "false_negative_rate": ev["fnr"],
        "auc": {"round_trip": ev["auc_rt"], "two_sided": ev["auc_ts"],
                "sell_buy": ev["auc_sb"], "ensemble": ev["auc_ensemble"]},
        "perm_null_p": p,
        "sweep": {k: v for k, v in sw.items() if k != "grid"},
        "grid": [[t, round(a, 3)] for t, a in sw["grid"]],
        "labels": {w[:12]: {"label": y, "prov": pr} for w, (y, pr) in labels.items()},
    }
    if not quiet:
        _print(res)
    return res


def _print(r):
    print(f"MM CALIBRATE (Tier-1, labeled) · {r['n_mm']} MM + {r['n_hum']} HUM\n")
    c = r["confusion_live"]
    print(f"  LIVE thresholds rt<{LIVE['rt']} AND ts<{LIVE['ts']} AND sb<{LIVE['sb']}:")
    print(f"    confusion: TP={c['tp']} FP={c['fp']} TN={c['tn']} FN={c['fn']}")
    fpr = 'n/a' if r['false_positive_rate'] is None else f"{r['false_positive_rate']:.1%}"
    fnr = 'n/a' if r['false_negative_rate'] is None else f"{r['false_negative_rate']:.1%}"
    print(f"    FP-rate (human flagged as MM) {fpr} · FN-rate (MM kept) {fnr}")
    a = r["auc"]
    def f(x): return 'n/a' if x is None else f'{x:.3f}'
    print(f"  AUC  rt {f(a['round_trip'])} · ts {f(a['two_sided'])} · sb {f(a['sell_buy'])} · "
          f"ensemble {f(a['ensemble'])}")
    pnull = 'n/a' if r['perm_null_p'] is None else f"{r['perm_null_p']:.4f}"
    print(f"  label-permutation null p = {pnull}")
    s = r["sweep"]
    print(f"  sweep (freeze ts=0.30, float rt): best rt={s['best_tau_rt']} "
          f"bal-acc {s['best_bal_acc']:.3f} · LOO tau∈[{s['loo_tau_min']},{s['loo_tau_max']}] "
          f"std {s['loo_tau_std']:.3f}")


def selftest():
    """Separable synthetic: MMs high rates, HUMs ~0. AUC must be ~1 and null p small."""
    rng = np.random.default_rng(3)
    micro = {}
    labels = {}
    for i in range(15):
        w = f"0xmm{i:03d}"
        micro[w] = {"rt": rng.uniform(0.4, 0.8), "ts": rng.uniform(0.3, 0.7),
                    "sb": rng.uniform(0.4, 0.8), "vol": 1e6, "n_pos": 300, "n_fills": 1000}
        labels[w] = ("MM", "synthetic")
    for i in range(20):
        w = f"0xhh{i:03d}"
        micro[w] = {"rt": rng.uniform(0, 0.1), "ts": rng.uniform(0, 0.1),
                    "sb": rng.uniform(0, 0.1), "vol": 1e4, "n_pos": 80, "n_fills": 300}
        labels[w] = ("HUM", "synthetic")
    ev = evaluate(labels, micro)
    auc = ev["auc_ensemble"]
    _, p = perm_null(ev["_ispos"], ev["_ens"], 1000, 1)
    ok = auc is not None and auc > 0.95 and p is not None and p < 0.01
    print(f"  [{'ok' if ok else 'FAIL'}] AUC={auc:.3f} p={p:.4f} (want AUC>0.95, p<0.01)")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    nperm = int(sys.argv[sys.argv.index("--nperm") + 1]) if "--nperm" in sys.argv else N_PERM
    res = run(nperm)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports",
                       "mm_calibrate.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("\nartifact → reports/mm_calibrate.json")


if __name__ == "__main__":
    main()
