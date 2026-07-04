#!/usr/bin/env python3
"""
UNIFIED RISK BOOK — the one sizing/risk policy that SURVIVED every verification, applied
forward to the live paper stream as a single virtual book. Read-only, paper-only.

THE PICK (why this policy and not the others — every knob has a decision record):
  * flat-SHARES base sizing        — the only convention that survived everything: flat-$ flips
    the P&L sign (refined-strategy anchor); P0 flat is ~4× safer on CVaR than any ⅛-Kelly
    policy (D21); the stress test's #1 fix is "abandon ⅛-Kelly" (VERDICT.md F1: at half-edge,
    ⅛-Kelly breaches the 30% DD ceiling in 44% of years).
  * λ̂-GATED Kelly ladder, parked  — D22 pinned the de-lever knee at ⅟₁₂ (OBJ-max feasible,
    P(maxDD>25%)≤10%) with ⅟₁₆ conservative, and flat-shares as the floor at λ≈0. λ̂ is
    MEASURED weak (0.15, fallback-dominated, INDETERMINATE) ⇒ the ladder stays at the floor:
    flat until λ̂ CI-lower ≥ 0.25 (→ ⅟₁₆), ≥ 0.50 (→ ⅟₁₂). ¼ and ⅙ are ruled out (infeasible).
  * 13%/day deploy cap             — the sizing run's blended-median-optimal under
    P(ruin)≤5%-even-if-the-edge-is-fake (optimal_deploy.json; hard ceiling 16%).
  * 2% per-bet cap                 — the stress fix's band-5 hard cap (≤2% of bankroll/bet).
  * longshot block (entry ≥ 0.45)  — the documented poison (−28%…−67% sub-45¢).
  * NO per-game cap                — D21's verified correction of D20: caps bound the rare
    single-game block but WORSEN CVaR by shedding +EV diversifying volume. The Kelly
    fraction, not the cap, is the first-order lever.
  * DODGE-cell steering            — applied at SELECTION time by the live map_state overlay
    (D14/D24 governance); this book does not re-apply it (one owner per decision).
  * per-slate stop −5u             — kept as a brake; documented as NOT bounding cross-regime
    drawdown (stress F6) — no safety claim is made for it.
  * REJECTED alternatives: kelly_eighth_capped (D15 → overturned by the stress test);
    per-game caps (D20 → corrected by D21); ¼/⅙-Kelly (D22 infeasible); orthogonal
    multi-edge book (D17: 0/12 strategies add a second edge — the menu is [favorite] until
    something certifies; proven_router auto-joins this book the day it has ledger rows).

The instrument: chronological virtual bankroll over the arms' honest_paper_ledger rows
(realizable entries), day budget = 13% × start-of-day bankroll, per-bet $ = min(budget/n_day,
2% × bankroll), skip entries < 0.45. Reports equity, maxDD, CVaR-ish tail, P(day>0), and the
flat-$100 baseline on the SAME bets. Forward-sealed at first run (reports/unified_freeze_ts.txt):
rows resolved before the seal are SEED (illustrative), after it are forward evidence. Verdict
stays INDETERMINATE until ≥20 forward day-blocks (same honesty gate as the sizing run).

  ./unified_book.py             # writes reports/unified_book.json + risk_policy.json
  ./unified_book.py --selftest
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY_FILE = os.path.join(ROOT, "reports", "risk_policy.json")
REPORT = os.path.join(ROOT, "reports", "unified_book.json")
FREEZE_FILE = os.path.join(ROOT, "reports", "unified_freeze_ts.txt")
LAMBDA_FILE = os.path.join(ROOT, "reports", "clv_lambda.json")

POLICY = {
    "policy": "unified_v1",
    "sizing_base": "flat_shares",
    "kelly_ladder": [{"lambda_ci_lower_min": 0.25, "k": "1/16"},
                     {"lambda_ci_lower_min": 0.50, "k": "1/12"}],
    "kelly_ruled_out": ["1/4", "1/6"],
    "deploy_cap_per_day": 0.13,
    "deploy_hard_ceiling": 0.16,
    "per_bet_cap": 0.02,
    "entry_floor": 0.45,
    "per_game_cap": None,
    "slate_stop_units": -5,
    "dodge_overlay": "map_state (selection-time, not re-applied here)",
    "arms": ["favorite", "proven_router"],
    "bankroll_start": 10000.0,
    "provenance": {
        "flat_shares": "refined-strategy anchor + D21 (4x CVaR) + stress VERDICT F1",
        "ladder": "D22 corr_risk_delever (1/12 knee, 1/16 conservative, flat floor at lambda~0)",
        "deploy_cap": "reports/sizing/optimal_deploy.json (ruin<=5% even-if-fake)",
        "per_bet_cap": "stress VERDICT fix #1",
        "no_game_cap": "D21 corr_risk_verify",
        "rejected": "kelly_eighth_capped (D15, overturned by stress test)",
    },
}


def lambda_ci_lower():
    """λ̂ CI-lower if a certified trajectory read exists; None while fallback-dominated."""
    try:
        d = json.load(open(LAMBDA_FILE))
        if "INDETERMINATE" in str(d.get("verdict", "")):
            return None
        ci = d.get("lambda_ci") or d.get("ci")
        return float(ci[0]) if ci else None
    except Exception:
        return None


def active_kelly(lam_lb):
    """The ladder: flat-shares floor until λ̂ CI-lower clears the D22 rungs."""
    if lam_lb is None:
        return None, "flat_shares (lambda INDETERMINATE - ladder parked at the floor)"
    k = None
    for rung in POLICY["kelly_ladder"]:
        if lam_lb >= rung["lambda_ci_lower_min"]:
            k = rung["k"]
    return k, (f"kelly {k} (lambda CI-lower {lam_lb:.2f})" if k else
               f"flat_shares (lambda CI-lower {lam_lb:.2f} < 0.25)")


def fetch_ledger(arms):
    arm_list = ",".join(f"'{a}'" for a in arms)
    return tsc.q(f"""
      SELECT strategy, (resolved_at AT TIME ZONE 'UTC')::date AS day, resolved_at,
             entry, outcome_won::int AS won
      FROM honest_paper_ledger
      WHERE strategy IN ({arm_list}) AND entry > 0
      ORDER BY resolved_at, id""")


def run_book(rows, freeze_day=None):
    """Chronological virtual book under the policy. Returns summary + day P&L."""
    b = POLICY["bankroll_start"]
    peak, max_dd = b, 0.0
    day_pnl, equity = {}, []
    by_day = defaultdict(list)
    for r in rows:
        if float(r["entry"]) < POLICY["entry_floor"]:
            continue
        by_day[r["day"]].append(r)
    for day in sorted(by_day):
        bets = by_day[day]
        budget = POLICY["deploy_cap_per_day"] * b
        per_bet = min(budget / len(bets), POLICY["per_bet_cap"] * b)
        pnl = 0.0
        for r in bets:
            e = float(r["entry"])
            ret = (int(r["won"]) - e) / e - tsc.FEE
            pnl += per_bet * ret
        b += pnl
        day_pnl[str(day)] = pnl
        peak = max(peak, b)
        max_dd = max(max_dd, (peak - b) / peak)
        equity.append((str(day), round(b, 2)))
        if b <= 0.2 * POLICY["bankroll_start"]:
            break  # ruin line — report it, never hide it
    days = list(day_pnl.values())
    fwd = {d: p for d, p in day_pnl.items() if freeze_day and d >= freeze_day}
    return {
        "final_bankroll": round(b, 2),
        "total_pnl": round(b - POLICY["bankroll_start"], 2),
        "max_drawdown": round(max_dd, 4),
        "n_days": len(days),
        "pct_days_positive": round(sum(1 for p in days if p > 0) / len(days), 3) if days else None,
        "worst_day": round(min(days), 2) if days else None,
        "tail_mean_worst5pct": round(
            sum(sorted(days)[:max(1, len(days) // 20)]) / max(1, len(days) // 20), 2)
        if days else None,
        "forward_days": len(fwd),
        "forward_pnl": round(sum(fwd.values()), 2) if fwd else 0.0,
        "equity_tail": equity[-10:],
    }


def flat_baseline(rows):
    """The same bets at flat $100 — the incumbent convention, for comparison."""
    pnl_by_day = defaultdict(float)
    for r in rows:
        e = float(r["entry"])
        if e < POLICY["entry_floor"]:
            continue
        pnl_by_day[str(r["day"])] += 100.0 * ((int(r["won"]) - e) / e - tsc.FEE)
    days = list(pnl_by_day.values())
    return {"total_pnl": round(sum(days), 2),
            "pct_days_positive": round(sum(1 for p in days if p > 0) / len(days), 3) if days else None,
            "worst_day": round(min(days), 2) if days else None}


def selftest():
    rows = []
    # 40 winning-biased favorite bets over 8 days; one catastrophic day.
    for d in range(8):
        for i in range(5):
            rows.append({"strategy": "favorite", "day": f"2026-06-{10+d:02d}",
                         "entry": 0.70, "won": 0 if (d == 3) else 1})
    s = run_book(rows)
    assert s["n_days"] == 8 and s["worst_day"] < 0, "worst day must be the all-loss day"
    # Caps: one day with 1 bet — stake must be per_bet_cap-bound (2%), not 13%.
    one = run_book([{"strategy": "favorite", "day": "2026-06-01", "entry": 0.5, "won": 1}])
    exp = POLICY["bankroll_start"] * POLICY["per_bet_cap"] * ((1 - 0.5) / 0.5 - tsc.FEE)
    assert abs(one["total_pnl"] - round(exp, 2)) < 0.02, "per-bet cap not binding"
    # Longshot block.
    assert run_book([{"strategy": "favorite", "day": "d", "entry": 0.30, "won": 1}])["n_days"] == 0
    # Ladder parks on None lambda.
    k, why = active_kelly(None)
    assert k is None and "floor" in why
    assert active_kelly(0.3)[0] == "1/16" and active_kelly(0.6)[0] == "1/12"
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    lam = lambda_ci_lower()
    k, sizing_mode = active_kelly(lam)
    rows = fetch_ledger(POLICY["arms"])
    now_day = tsc.q("SELECT (NOW() AT TIME ZONE 'UTC')::date AS d")[0]["d"]
    if os.path.exists(FREEZE_FILE):
        freeze_day = open(FREEZE_FILE).read().strip()
    else:
        freeze_day = str(now_day)
        with open(FREEZE_FILE, "w") as f:
            f.write(freeze_day)

    book = run_book(rows, freeze_day)
    base = flat_baseline(rows)
    arms_present = sorted({r["strategy"] for r in rows})
    verdict = ("INDETERMINATE — forward accrual "
               f"{book['forward_days']}/20 day-blocks (seed record is illustrative only)")

    out = {"policy": POLICY, "sizing_mode_today": sizing_mode,
           "lambda_ci_lower": lam, "freeze_day": freeze_day,
           "arms_present": arms_present, "book": book,
           "flat_100_baseline": base, "verdict": verdict}
    with open(POLICY_FILE, "w") as f:
        json.dump(POLICY, f, indent=2)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2)

    print(f"UNIFIED BOOK ({sizing_mode}) — arms present: {arms_present}")
    print(f"  bankroll {POLICY['bankroll_start']:.0f} → {book['final_bankroll']:.0f} "
          f"(pnl {book['total_pnl']:+.0f}) over {book['n_days']} days | "
          f"maxDD {book['max_drawdown']:.1%} | days>0 {book['pct_days_positive']:.0%} | "
          f"worst day {book['worst_day']:+.0f}")
    print(f"  flat-$100 baseline: pnl {base['total_pnl']:+.0f}, days>0 "
          f"{base['pct_days_positive']:.0%}, worst {base['worst_day']:+.0f}")
    print(f"  forward: {book['forward_days']} day-blocks, pnl {book['forward_pnl']:+.0f} "
          f"(seal {freeze_day})")
    print(f"  verdict: {verdict}")
    print(f"wrote {REPORT} + {POLICY_FILE}")


if __name__ == "__main__":
    main()
