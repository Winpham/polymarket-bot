#!/usr/bin/env python3
"""
WS-2 — reduced-variance retrospective signals. Do lower-variance-than-ROI rankings of past
picks persist early->late where mean-ROI does not?

Signals (each a per-wallet scalar from the EARLY half, non-MM cohort, event-clustered):
  sign_consistency : fraction of early events with surplus>0 (robust location, low variance)
  eb_shrinkage     : empirical-Bayes posterior mean of early event-surplus (shrunk by
                     within-wallet variance toward the fleet mean)
  calibration_slope: OLS slope of event win-indicator on event price over early events
                     (do their selections' realized frequency track price with skill-shaped slope)

Gate (pre-registered): a signal is real iff Spearman(early_signal, late_surplus) lower bound>0
AND the top-tercile-by-signal forward (late) surplus lower bound>0. Expectation: NULL.

READ-ONLY. Writes reports/skilled/ws2_reduced_variance.json.  --selftest for synthetic checks.
"""
import argparse, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skill_common as sk   # noqa: E402

REPORT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "reports", "skilled", "ws2_reduced_variance.json")


def ols_slope(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return 0.0
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / sxx


def early_signals(evmap):
    """per-event lists over the EARLY half; return dict of scalar signals + late target."""
    s, wf, pr = [], [], []
    for ev, rr in evmap.items():
        s.append(sum(x["surplus"] for x in rr) / len(rr))
        wf.append(sum(1 for x in rr if x["a"] > 0) / len(rr))
        pr.append(sum((1.0 if x["a"] > 0 else 0.0) - x["a"] for x in rr) / len(rr))
    n = len(s)
    mean_s = sum(s) / n
    var_s = sum((x - mean_s) ** 2 for x in s) / max(1, n - 1)
    return {"n": n, "mean_surplus": mean_s, "var_surplus": var_s,
            "sign_consistency": sum(1 for x in s if x > 0) / n,
            "calibration_slope": ols_slope(pr, wf), "_s": s}


def run(min_ev_half=10):
    wallets, _ = sk.load_events(min_ev_half)
    W = list(wallets.keys())
    n = len(W)
    if n < 10:
        return {"error": "too few wallets", "n": n}
    early = {w: early_signals(wallets[w]["E"]) for w in W}
    late = {w: (lambda ev: sum(sum(x["surplus"] for x in rr) / len(rr) for rr in ev.values()) / len(ev))
            (wallets[w]["L"]) for w in W}
    # empirical-Bayes shrinkage: posterior = fleet + (m-fleet)*tau2/(tau2 + within/n)
    fleet = sum(early[w]["mean_surplus"] for w in W) / n
    tau2 = max(1e-9, sum((early[w]["mean_surplus"] - fleet) ** 2 for w in W) / (n - 1)
               - sum(early[w]["var_surplus"] / early[w]["n"] for w in W) / n)
    for w in W:
        se2 = early[w]["var_surplus"] / early[w]["n"]
        early[w]["eb_shrinkage"] = fleet + (early[w]["mean_surplus"] - fleet) * tau2 / (tau2 + se2)

    signals = ["mean_surplus", "sign_consistency", "eb_shrinkage", "calibration_slope"]
    out = {"n_wallets": n, "cohort": "non-MM directional", "min_ev_half": min_ev_half,
           "fleet_late_surplus": sum(late.values()) / n, "tau2": tau2, "signals": {}}
    for sig in signals:
        xs = [early[w][sig] for w in W]
        ys = [late[w] for w in W]
        pairs = list(zip(xs, ys))
        lo, hi, pt = sk.boot_ci(pairs, lambda ps: sk.spearman([p[0] for p in ps], [p[1] for p in ps]))
        # top tercile by signal -> forward late surplus LB
        order = sorted(range(n), key=lambda i: xs[i], reverse=True)
        k = max(3, n // 3)
        top_late = [ys[i] for i in order[:k]]
        tlb = sk.mean_lb(top_late)
        gate = (lo > 0) and (tlb > 0)
        out["signals"][sig] = {
            "persistence_spearman": pt, "persistence_ci95": [lo, hi],
            "top_tercile_late_surplus_mean": sum(top_late) / k, "top_tercile_late_LB": tlb,
            "k_top": k, "GATE_PASS": gate,
            "verdict": "SURVIVES-INSAMPLE (needs WS-5 multiplicity)" if gate else "NULL"}
    any_pass = any(out["signals"][s]["GATE_PASS"] for s in signals)
    out["verdict"] = ("candidate(s) survive in-sample -> WS-5" if any_pass
                      else "ALL NULL — no reduced-variance retrospective signal persists")
    return out


def selftest():
    assert abs(ols_slope([0, 1, 2, 3], [0, 2, 4, 6]) - 2.0) < 1e-9
    assert abs(ols_slope([0, 1, 2], [5, 5, 5])) < 1e-9
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--min-ev-half", type=int, default=10)
    a = ap.parse_args()
    if a.selftest:
        selftest(); sys.exit(0)
    res = run(a.min_ev_half)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps(res, indent=2, default=str))
