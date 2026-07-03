#!/usr/bin/env python3
"""
WS-1 — FORWARD CLV/λ ACCRUAL MONITOR. The self-running apparatus that turns dense-capture data into a
trustworthy λ̂ as it accrues, and says — on each reading — whether λ has crossed the profitability
floor yet. This is the loop that makes "measure λ for real" (D22 WS-A) run itself once DENSE_CAPTURE
is on: the instrument (`clv_lambda.py`) already auto-switches proxy→trajectory; this watches it climb.

Each reading records: trajectory coverage %, the λ̂ + CI (proxy while coverage < floor, REAL once it
crosses), and the FLOOR VERDICT — does λ̂'s CI lower bound clear the pilot's min_lambda (0.25, WS-D)?
Appends to reports/clv_accrual_log.jsonl (append-only) so the trend is visible over the accrual weeks.

State machine (honest, never over-claims):
  EMPTY            trajectory coverage 0% — dense capture not running yet (deploy pending).
  ACCRUING         0 < coverage < 50% — proxy λ̂ only; real λ not yet measurable (K1).
  MEASURED         coverage ≥ 50% — REAL λ̂ from closing mids; the floor verdict is now trustworthy.
  Floor: CLEARS (CI_lo > 0.25) → the edge-reality gate for a pilot is met; BELOW → not (default today).

Read-only, paper-only. Certifies nothing (persistence/D7 still govern real money); it tracks ONE gate.
  ./clv_monitor.py                  # take a reading, append to the log, print the panel + verdict
  ./clv_monitor.py --selftest       # state-machine + floor-verdict logic on synthetic readings
  ./clv_monitor.py --history        # print the accrual log
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

COVERAGE_FLOOR = 0.50      # K1: trajectory coverage below this ⇒ proxy-only (INDETERMINATE)
MIN_LAMBDA = 0.25         # WS-D pilot edge floor
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
LOG = os.path.join(REPORT_DIR, "clv_accrual_log.jsonl")


def classify(coverage, lam_lo):
    if coverage <= 0.0:
        state = "EMPTY"
    elif coverage < COVERAGE_FLOOR:
        state = "ACCRUING"
    else:
        state = "MEASURED"
    trustworthy = state == "MEASURED"
    floor = "CLEARS" if (trustworthy and lam_lo > MIN_LAMBDA) else ("BELOW" if trustworthy else "n/a")
    return state, trustworthy, floor


def take_reading(strategy, draws, seed, now_iso):
    import clv_lambda as cl
    res = cl.measure(strategy, draws, seed)
    coverage = res["trajectory_coverage"]
    lam = res["lambda_hat"]
    lam_lo, lam_hi = res["lambda_ci"]
    state, trustworthy, floor = classify(coverage, lam_lo)
    return {
        "ts": now_iso, "strategy": strategy,
        "n_positions": res["n_total"], "n_events": res["n_events"],
        "trajectory_coverage": coverage, "state": state,
        "lambda_hat": lam, "lambda_ci": [lam_lo, lam_hi], "lambda_trustworthy": trustworthy,
        "null_p": res["null_p"], "clv_explained_frac": res["clv_explained_frac"],
        "floor_min_lambda": MIN_LAMBDA, "floor_verdict": floor,
    }


def append_log(rec):
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


def read_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG) as f:
        return [json.loads(line) for line in f if line.strip()]


def print_panel(rec, history):
    print("=" * 80)
    print(f"WS-1 · CLV/λ ACCRUAL MONITOR · {rec['strategy']} · {rec['ts']}")
    print("=" * 80)
    print(f"state: {rec['state']}   ·   trajectory coverage: {rec['trajectory_coverage']:.1%}   "
          f"(floor {COVERAGE_FLOOR:.0%})")
    tag = "REAL" if rec["lambda_trustworthy"] else "proxy (NOT trustworthy)"
    print(f"λ̂ = {rec['lambda_hat']:.3f}  CI [{rec['lambda_ci'][0]:.3f}, {rec['lambda_ci'][1]:.3f}]  ({tag})")
    print(f"CLV null p = {rec['null_p']:.4f}   ·   CLV-explained {rec['clv_explained_frac']:.1%} of surplus")
    print("-" * 80)
    if rec["state"] == "EMPTY":
        print("VERDICT: EMPTY — dense capture is not writing trajectory. Deploy Option B "
              "(DENSE_CAPTURE=true) to start accruing real CLV. λ stays a proxy until then.")
    elif rec["state"] == "ACCRUING":
        print(f"VERDICT: ACCRUING ({rec['trajectory_coverage']:.0%} < {COVERAGE_FLOOR:.0%}) — real λ not "
              "yet measurable; keep accruing. The proxy above is a hint, not a gate.")
    else:
        cross = "CLEARS the floor ✓ — the edge-reality gate for a pilot is MET" if rec["floor_verdict"] == "CLEARS" \
            else f"is BELOW the {MIN_LAMBDA} floor — edge-reality gate NOT met"
        print(f"VERDICT: MEASURED — λ̂ CI lower bound {rec['lambda_ci'][0]:.3f} {cross}.")
    print(f"(reading #{len(history)}; log → {os.path.relpath(LOG, os.path.dirname(REPORT_DIR))})")
    print("Persistence (D7) still governs real money — this tracks ONE gate (edge-reality), not the whole go.")


def selftest():
    ok = True
    cases = [
        (0.0, 0.5, "EMPTY", False, "n/a"),
        (0.30, 0.9, "ACCRUING", False, "n/a"),
        (0.70, 0.30, "MEASURED", True, "CLEARS"),
        (0.70, 0.10, "MEASURED", True, "BELOW"),
        (0.50, 0.26, "MEASURED", True, "CLEARS"),
    ]
    for cov, lam_lo, exp_state, exp_trust, exp_floor in cases:
        s, t, f = classify(cov, lam_lo)
        good = s == exp_state and t == exp_trust and f == exp_floor
        ok = ok and good
        print(f"  [{'ok' if good else 'FAIL'}] cov {cov:.0%} lo {lam_lo:.2f} → {s}/{t}/{f} "
              f"(exp {exp_state}/{exp_trust}/{exp_floor})")
    # today's honest expectation: EMPTY (coverage 0) ⇒ floor n/a, not a false CLEARS
    s, t, f = classify(0.0, 0.99)
    guard = s == "EMPTY" and f == "n/a"
    ok = ok and guard
    print(f"  [{'ok' if guard else 'FAIL'}] high proxy λ at 0% coverage does NOT read as CLEARS (no laundering)")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="favorite")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260703)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--history", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.history:
        for r in read_log():
            print(f"{r['ts']}  {r['strategy']:<16} cov {r['trajectory_coverage']:.0%}  "
                  f"λ̂ {r['lambda_hat']:.3f} [{r['lambda_ci'][0]:.3f},{r['lambda_ci'][1]:.3f}]  "
                  f"{r['state']}/{r['floor_verdict']}")
        return
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = take_reading(args.strategy, args.draws, args.seed, now_iso)
    append_log(rec)
    print_panel(rec, read_log())


if __name__ == "__main__":
    main()
