#!/usr/bin/env python3
"""
fade_persistence — THREAD C (Cycle 2): is the soccer/directional/band5 FADE a REAL RECURRING
within-soccer structural edge (heavy-favorite overhype in soccer — bankable seasonally even if it
doesn't transfer to tennis/cs2), or a one-World-Cup / few-day ARTIFACT?

Cycle 1: soccer/directional/band5 NO net +8.2% (p=0.001 across-sport null) but 0/3 transfer to
non-soccer band5 → HOLD (SOCCER-ARTIFACT). Transfer failing only says it's soccer-specific; it does
NOT say whether it's a recurring soccer edge. This instrument answers the recurring question with two
WITHIN-SOCCER tests:

  (1) TEMPORAL PERSISTENCE — split soccer-band5-directional blind events into EARLY vs LATE days;
      the fade NO-side net edge must hold (same sign, positive) in BOTH halves. A real structural
      overhype recurs; a tournament artifact is carried by a few days and flips sign.
  (2) DAY-BLOCK BOOTSTRAP — resample DAYS with replacement (the independent cluster is the day, not
      the event — within-day events share the same slate) → CI on the fade net edge. If the CI
      straddles 0, the "edge" is a few-day fluke, not robust.
  (3) WITHIN-SOCCER NULL — is the directional sub-cell's negative gap special vs a null that shuffles
      `won` among ALL soccer-band5 events (preserving the soccer-band5 base rate, destroying the
      directional structure)? Uses ONLY soccer — no borrowed power from other sports.

Fade NO-side per-event FLAT-SHARES surplus (guardrail: flat-shares, never leveraged ROI — band5
NO is an 8x longshot whose ROI is unusably skewed). Matches softness_fade.net_no aggregated:
  fade_ret = (entry - won) - HAIRCUT - FEE*(1 - entry)
  (= -(won-entry) - costs; positive when the priced-in favorite LOSES more than 1-entry implies).

Read-only, paper-only. Certifies nothing; classifies the fade as RECURRING vs ARTIFACT.
  ./fade_persistence.py --selftest
  ./fade_persistence.py            # writes reports/fade_persistence.json
"""

import argparse
import csv
import io
import json
import os
import random
import subprocess
import sys
from collections import defaultdict
from math import sqrt

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
HAIRCUT, FEE = 0.01, 0.02
BAND5_LO, BAND5_HI = 0.80, 1.0
N_BOOT = 5000
SEED = 20260705
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "fade_persistence.json")

SQL = """
SELECT (first_detected_at AT TIME ZONE 'UTC')::date AS day,
       COALESCE(event_slug, condition_id) AS ev, slug,
       initial_mean_price AS entry, (outcome_won::int) AS won,
       (event_slug LIKE 'fifwc%') AS is_soccer
FROM consensus_signals
WHERE strategy='_blind' AND resolved AND initial_mean_price >= 0.80 AND initial_mean_price < 1.0
"""

DIRECTIONAL_EXCLUDE = ("total", "exact", "correct-score", "spread", "handicap", "-by-", "margin",
                       "over-under", "o-u-", "goals", "-runs", "points")


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def is_directional(slug):
    s = (slug or "").lower()
    return not any(tok in s for tok in DIRECTIONAL_EXCLUDE)


def fade_ret(entry, won):
    """FLAT-SHARES NO-side surplus per share (bounded), matching softness_fade.net_no."""
    return (entry - won) - HAIRCUT - FEE * (1.0 - entry)


def day_clustered(rows, key=lambda r: r["day"], val=None):
    """mean over day-clusters of (per-day mean value). Returns (mean, n_days, per_day list)."""
    by = defaultdict(list)
    for r in rows:
        by[key(r)].append(val(r))
    days = sorted(by)
    dm = [sum(by[d]) / len(by[d]) for d in days]
    if not dm:
        return None, 0, []
    return sum(dm) / len(dm), len(dm), dm


def boot_days(rows, val, n=N_BOOT, seed=SEED):
    """Day-block bootstrap CI of the day-clustered mean (resample DAYS with replacement)."""
    by = defaultdict(list)
    for r in rows:
        by[r["day"]].append(val(r))
    days = sorted(by)
    if len(days) < 3:
        return None
    day_means = {d: sum(by[d]) / len(by[d]) for d in days}
    rng = random.Random(seed)
    boots = []
    for _ in range(n):
        samp = [day_means[days[rng.randrange(len(days))]] for _ in days]
        boots.append(sum(samp) / len(samp))
    boots.sort()
    return {"point": sum(day_means.values()) / len(day_means),
            "ci_lo": boots[int(0.025 * n)], "ci_hi": boots[int(0.975 * n)], "n_days": len(days)}


def within_soccer_null(soccer_b5, direc_evs, n=2000, seed=SEED):
    """Shuffle `won` among ALL soccer-band5 events; recompute the directional sub-cell's day-clustered
    fade net edge; p = P(null >= observed). Tests whether 'directional' is specially soft within
    soccer band5, using only soccer data (no cross-sport power)."""
    direc_set = set(direc_evs)
    obs_rows = [r for r in soccer_b5 if r["ev"] in direc_set]
    obs, _, _ = day_clustered(obs_rows, val=lambda r: fade_ret(r["entry"], r["won"]))
    if obs is None:
        return None
    wons = [r["won"] for r in soccer_b5]
    rng = random.Random(seed)
    ge = 0
    for _ in range(n):
        perm = wons[:]
        rng.shuffle(perm)
        # reassign shuffled won to the same rows, then recompute directional sub-cell
        shuffled = [{"day": r["day"], "ev": r["ev"], "entry": r["entry"], "won": perm[i],
                     "_dir": r["ev"] in direc_set} for i, r in enumerate(soccer_b5)]
        drows = [r for r in shuffled if r["_dir"]]
        m, _, _ = day_clustered(drows, val=lambda r: fade_ret(r["entry"], r["won"]))
        if m is not None and m >= obs:
            ge += 1
    return {"obs": obs, "p_emp": (ge + 1) / (n + 1)}


def run(early=("2026-06-29", "2026-07-01"), late=("2026-07-02", "2026-07-05"), verbose=True):
    rows = q(SQL)
    for r in rows:
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
        r["day"] = str(r["day"])
        r["is_soccer"] = (r["is_soccer"] in ("t", "true", "True", True))
    soccer_b5 = [r for r in rows if r["is_soccer"]]
    direc = [r for r in soccer_b5 if is_directional(r["slug"])]
    direc_evs = [r["ev"] for r in direc]

    def fret(r):
        return fade_ret(r["entry"], r["won"])

    overall, nd_all, _ = day_clustered(direc, val=fret)
    boot_all = boot_days(direc, fret)
    early_rows = [r for r in direc if early[0] <= r["day"] <= early[1]]
    late_rows = [r for r in direc if late[0] <= r["day"] <= late[1]]
    e_m, e_nd, e_dm = day_clustered(early_rows, val=fret)
    l_m, l_nd, l_dm = day_clustered(late_rows, val=fret)
    boot_e = boot_days(early_rows, fret)
    boot_l = boot_days(late_rows, fret)
    wnull = within_soccer_null(soccer_b5, direc_evs)

    # per-day table (fade net edge + n)
    by_day = defaultdict(list)
    for r in direc:
        by_day[r["day"]].append(fret(r))
    per_day = {d: {"fade_net": sum(v) / len(v), "n": len(v)} for d, v in sorted(by_day.items())}
    n_days_pos = sum(1 for v in per_day.values() if v["fade_net"] > 0)

    # verdict
    both_positive = (e_m is not None and l_m is not None and e_m > 0 and l_m > 0)
    boot_robust = (boot_all is not None and boot_all["ci_lo"] > 0)
    null_special = (wnull is not None and wnull["p_emp"] <= 0.05)
    sign_stable = (n_days_pos / len(per_day) >= 0.6) if per_day else False
    if boot_robust and both_positive and sign_stable:
        verdict = "RECURRING within-soccer fade (both halves positive, day-bootstrap CI>0, sign-stable)"
    elif (not both_positive) or (not sign_stable):
        verdict = ("ARTIFACT / few-day: fade does NOT persist within soccer "
                   f"(day-sign {n_days_pos}/{len(per_day)} positive; halves e={fmt(e_m)} l={fmt(l_m)})")
    else:
        verdict = "INDETERMINATE-BY-POWER within soccer (halves same sign but day-bootstrap CI straddles 0)"

    out = {
        "windows": {"early": early, "late": late},
        "n_soccer_b5": len(soccer_b5), "n_directional": len(direc), "n_days": nd_all,
        "overall_fade_net": overall, "bootstrap_all": boot_all,
        "early": {"fade_net": e_m, "n_days": e_nd, "bootstrap": boot_e},
        "late": {"fade_net": l_m, "n_days": l_nd, "bootstrap": boot_l},
        "per_day": per_day, "n_days_positive": n_days_pos,
        "within_soccer_null": wnull,
        "verdict": verdict,
    }
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    if verbose:
        print(f"FADE PERSISTENCE (soccer/directional/band5) · {len(direc)} events / {nd_all} days")
        ba = boot_all
        print(f"  overall fade NO net = {fmt(overall)}  day-bootstrap CI"
              f"[{fmt(ba['ci_lo']) if ba else 'na'},{fmt(ba['ci_hi']) if ba else 'na'}]")
        print(f"  EARLY {early}: {fmt(e_m)} ({e_nd}d)   LATE {late}: {fmt(l_m)} ({l_nd}d)")
        print(f"  per-day fade net (n): " +
              "  ".join(f"{d[5:]}:{v['fade_net']:+.3f}({v['n']})" for d, v in per_day.items()))
        print(f"  days positive: {n_days_pos}/{len(per_day)}")
        if wnull:
            print(f"  within-soccer null: obs={fmt(wnull['obs'])} p_emp={wnull['p_emp']:.3f}")
        print(f"  VERDICT: {verdict}")
        print(f"wrote {REPORT}")
    return out


def fmt(x):
    return "None" if x is None else f"{x:+.3f}"


def selftest():
    """F1 RECURRING: favorites overpriced EVERY day (won<entry consistently) → fade net>0 both halves,
       day-bootstrap CI>0.  F2 ARTIFACT: one big early day carries it, other days flip → not persistent."""
    global q, within_soccer_null
    # F1: recurring overhype — 8 days, each favorites win ~0.70 at price 0.90 → NO pays well every day
    f1 = []
    for di, day in enumerate(["2026-06-29", "2026-06-30", "2026-07-01",
                              "2026-07-02", "2026-07-03", "2026-07-04"]):
        for i in range(20):
            f1.append({"day": day, "ev": f"{day}-{i}", "slug": "fifwc-a-vs-b",
                       "entry": 0.90, "won": 1 if (i % 10) < 7 else 0, "is_soccer": True})
    r1 = _run_fixture(f1)
    assert r1["early"]["fade_net"] > 0 and r1["late"]["fade_net"] > 0, f"F1 halves: {r1}"
    assert r1["bootstrap_all"]["ci_lo"] > 0, f"F1 boot: {r1['bootstrap_all']}"
    assert "RECURRING" in r1["verdict"], f"F1 verdict={r1['verdict']}"

    # F2: artifact — 6/29 huge overhype, all other days favorites WIN (fade loses)
    f2 = []
    for i in range(50):
        f2.append({"day": "2026-06-29", "ev": f"early-{i}", "slug": "fifwc-a-vs-b",
                   "entry": 0.90, "won": 0 if i < 40 else 1, "is_soccer": True})  # fade wins big
    for day in ["2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"]:
        for i in range(15):
            f2.append({"day": day, "ev": f"{day}-{i}", "slug": "fifwc-a-vs-b",
                       "entry": 0.90, "won": 1, "is_soccer": True})  # favorites win → fade loses
    r2 = _run_fixture(f2)
    assert "ARTIFACT" in r2["verdict"], f"F2 verdict={r2['verdict']}"
    print("selftest OK")


def _run_fixture(rows):
    """Run the core (no DB, no within-soccer null) on injected rows."""
    for r in rows:
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
    direc = [r for r in rows if is_directional(r["slug"])]
    def fret(r):
        return fade_ret(r["entry"], r["won"])
    overall, nd_all, _ = day_clustered(direc, val=fret)
    boot_all = boot_days(direc, fret)
    early = ("2026-06-29", "2026-07-01"); late = ("2026-07-02", "2026-07-05")
    e_m, e_nd, _ = day_clustered([r for r in direc if early[0] <= r["day"] <= early[1]], val=fret)
    l_m, l_nd, _ = day_clustered([r for r in direc if late[0] <= r["day"] <= late[1]], val=fret)
    by_day = defaultdict(list)
    for r in direc:
        by_day[r["day"]].append(fret(r))
    per_day = {d: {"fade_net": sum(v) / len(v), "n": len(v)} for d, v in sorted(by_day.items())}
    n_days_pos = sum(1 for v in per_day.values() if v["fade_net"] > 0)
    both_positive = (e_m is not None and l_m is not None and e_m > 0 and l_m > 0)
    boot_robust = (boot_all is not None and boot_all["ci_lo"] > 0)
    sign_stable = (n_days_pos / len(per_day) >= 0.6) if per_day else False
    if boot_robust and both_positive and sign_stable:
        verdict = "RECURRING within-soccer fade"
    elif (not both_positive) or (not sign_stable):
        verdict = "ARTIFACT / few-day"
    else:
        verdict = "INDETERMINATE-BY-POWER"
    return {"overall_fade_net": overall, "bootstrap_all": boot_all,
            "early": {"fade_net": e_m}, "late": {"fade_net": l_m},
            "n_days_positive": n_days_pos, "verdict": verdict}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        run()
