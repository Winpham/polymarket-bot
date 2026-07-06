#!/usr/bin/env python3
"""
ADVERSARIAL AUDIT — does the `favorite` +6.9%/bet paper-P&L survive a REALISTIC
follower entry?  (team-lead attack brief, favconsensus-deepen run)

THE CLAIM UNDER ATTACK
  `favorite` earns ~+6.9%/bet after costs, measured at entry =
  at-fire COALESCE(initial_mean_price, mean_price) + 0.5c, fee 2%xentry, 100 shares,
  349 resolved picks, 8 UTC days, ~7-8 non-negative days.

SUSPICION
  at-fire mean_price is the SHARPS' fill; a follower only sees a price minutes later,
  after the book moved the sharps' way. If the honest entry is 1-2c worse the day
  table changes materially.

ATTACKS (all on the SAME 349 picks; fee 2%xentry, 100 shares throughout)
  A1  Four entry conventions, per-day + per-bet ROI + negative-day count:
        (a) COALESCE(initial_mean_price,mean_price)+0.5c        -- the claim baseline
        (b) initial_market_price+0.5c                           -- honest first-observed mid
        (c) entry_ask (already executable; coverage reported)   -- what a buyer actually pays
        (d) initial_market_price + 1.74c  (measured favorite fire->observed drift, copy_tax) -- worst-defensible
  A2  Coverage: N per convention; (b)/(c) run on a SUBSET, so (a) is reported on the
      SAME subset (like-for-like) beside each.
  A3  Sidedness: (initial_market_price - mean_price) and (entry_ask - mean_price)
      distribution (mean/median/p25/p75) -- is the move ADVERSE for a buyer?
  A4  Winner-inflation: A3 split by won/lost. drift(won) >> drift(lost) => at-fire
      P&L overstates what a follower keeps.
  A5  Timing feasibility from signal_price_trajectory: can a bot at 60-120s get near (b)?
  Bonus SELECTION check: do the picks with NO observable follower price carry the edge?

Read-only DB (docker psql).  scipy+stdlib only. No network, no ANTHROPIC_API_KEY, no child claude.
  ./audit_entry_realism.py --self-test    # synthetic fixture, assert-based, no DB
  ./audit_entry_realism.py                # live; writes reports/audit_entry_realism.json
"""

import csv
import io
import json
import os
import subprocess
import sys
from statistics import mean, median

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "audit_entry_realism.json")
HAIRCUT = 0.005          # the claim's 0.5c entry haircut
FEE = 0.02               # 2% x entry, expressed as a stake-fraction (fee$ = 2*entry / stake 100*entry)
DRIFT_D = 0.0174         # measured favorite fire->observed drift (copy_tax favorite pooled mean, ~1.74c)

SQL = """
SELECT to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day,
       (outcome_won::int)                       AS won,
       mean_price                               AS mean_price,
       COALESCE(initial_mean_price, mean_price) AS coalesced,
       initial_market_price                     AS imp,
       entry_ask                                AS ask
FROM consensus_signals
WHERE resolved AND outcome_won IS NOT NULL AND strategy = 'favorite'
"""

# earliest executable (ask NOT NULL) trajectory point in [60,120]s and in [60,900]s after fire
TRAJ_SQL = """
WITH f AS (SELECT id, mean_price FROM consensus_signals
           WHERE resolved AND outcome_won IS NOT NULL AND strategy='favorite')
SELECT t.secs_after_fire AS lag, (t.ask - f.mean_price) AS ask_drift
FROM signal_price_trajectory t JOIN f ON f.id = t.signal_id
WHERE t.ask IS NOT NULL AND t.secs_after_fire >= 60
"""


def _f(v):
    return float(v) if v not in (None, "", "NULL") else None


def _q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


# ---------- pure, self-testable core -----------------------------------------------------------
def roi(won, entry):
    """per-bet ROI at price `entry`: (won-entry)/entry - fee.  100 shares cost 100*entry;
    fee$ = FEE*entry*100 => fee as stake-fraction = FEE. None if entry<=0/>=1 (unfillable)."""
    if entry is None or entry <= 0 or entry >= 1:
        return None
    return (won - entry) / entry - FEE


def summarize(rows, entry_key):
    """per-bet mean ROI, per-day mean ROI, negative-day count, N, over rows with a usable entry."""
    vals, byday = [], {}
    for r in rows:
        e = r[entry_key]
        v = roi(r["won"], e)
        if v is None:
            continue
        vals.append(v)
        byday.setdefault(r["day"], []).append(v)
    if not vals:
        return {"n": 0, "per_bet": None, "per_day": None, "neg_days": None, "days": {}}
    day_roi = {d: mean(vs) for d, vs in byday.items()}
    return {
        "n": len(vals),
        "per_bet": round(mean(vals), 4),
        "per_day": round(mean(day_roi.values()), 4),
        "neg_days": sum(1 for v in day_roi.values() if v < 0),
        "n_days": len(day_roi),
        "days": {d: round(v, 4) for d, v in sorted(day_roi.items())},
    }


def dist(vals):
    vals = sorted(v for v in vals if v is not None)
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "p25": None, "p75": None}

    def pct(q):
        if n == 1:
            return vals[0]
        i = q * (n - 1)
        lo = int(i)
        frac = i - lo
        hi = min(lo + 1, n - 1)
        return vals[lo] * (1 - frac) + vals[hi] * frac
    return {"n": n, "mean": round(mean(vals), 4), "median": round(median(vals), 4),
            "p25": round(pct(0.25), 4), "p75": round(pct(0.75), 4)}


def build_entries(raw):
    """attach the four convention entry prices to each pick row."""
    rows = []
    for r in raw:
        won = int(r["won"])
        mp = _f(r["mean_price"])
        coal = _f(r["coalesced"])
        imp = _f(r["imp"])
        ask = _f(r["ask"])
        rows.append({
            "day": r["day"], "won": won, "mean_price": mp, "imp": imp, "ask": ask,
            "e_a": (coal + HAIRCUT) if coal is not None else None,        # claim
            "e_b": (imp + HAIRCUT) if imp is not None else None,         # honest first-observed
            "e_c": ask,                                                  # executable ask
            "e_d": (imp + DRIFT_D) if imp is not None else None,        # worst-defensible
        })
    return rows


def analyze(rows):
    has_b = [r for r in rows if r["e_b"] is not None]
    has_c = [r for r in rows if r["e_c"] is not None]
    n = len(rows)

    a1 = {
        "a_claim_full": summarize(rows, "e_a"),
        "b_imp":        summarize(has_b, "e_b"),
        "a_on_b_subset": summarize(has_b, "e_a"),      # like-for-like
        "c_ask":        summarize(has_c, "e_c"),
        "a_on_c_subset": summarize(has_c, "e_a"),      # like-for-like
        "d_worst":      summarize(has_b, "e_d"),
    }
    a2 = {"n_total": n,
          "cov_b_imp": round(len(has_b) / n, 3),
          "cov_c_ask": round(len(has_c) / n, 3)}

    def drift(rs, key):
        return dist([r[key] - r["mean_price"] for r in rs
                     if r[key] is not None and r["mean_price"] is not None])
    a3 = {
        "imp_minus_mean_all": drift(rows, "imp"),
        "ask_minus_mean_all": drift(rows, "ask"),
    }
    won = [r for r in rows if r["won"] == 1]
    lost = [r for r in rows if r["won"] == 0]
    a4 = {
        "imp_drift_won":  drift(won, "imp"),
        "imp_drift_lost": drift(lost, "imp"),
        "ask_drift_won":  drift(won, "ask"),
        "ask_drift_lost": drift(lost, "ask"),
    }
    # selection: do the picks WITHOUT an observable follower price carry the edge?
    no_imp = [r for r in rows if r["imp"] is None]
    sel = {
        "with_imp":    {"n": len(has_b),
                        "winrate": round(mean(r["won"] for r in has_b), 3) if has_b else None,
                        "a_roi": summarize(has_b, "e_a")["per_bet"]},
        "without_imp": {"n": len(no_imp),
                        "winrate": round(mean(r["won"] for r in no_imp), 3) if no_imp else None,
                        "a_roi": summarize(no_imp, "e_a")["per_bet"] if no_imp else None},
    }
    return {"A1_conventions": a1, "A2_coverage": a2, "A3_sidedness": a3,
            "A4_winner_inflation": a4, "SELECTION_uncaptured": sel}


def a5_timing(traj_rows):
    close = dist([_f(r["ask_drift"]) for r in traj_rows if 60 <= int(r["lag"]) <= 120])
    wide = dist([_f(r["ask_drift"]) for r in traj_rows])
    lags = sorted(int(r["lag"]) for r in traj_rows)
    return {
        "n_traj_ge60s": len(traj_rows),
        "median_lag_s": (median(lags) if lags else None),
        "ask_drift_60_120s": close,
        "ask_drift_all_ge60s": wide,
        "note": ("dense-capture is near-absent for favorite: too few 60-120s points to "
                 "prove a bot can reach convention (b) in time."),
    }


# ---------- self-test (synthetic; no DB) -------------------------------------------------------
def self_test():
    # roi(): won=1 @0.50 -> (1-.5)/.5 - .02 = 0.98 ; won=0 @0.50 -> -1 - .02 = -1.02
    assert abs(roi(1, 0.50) - 0.98) < 1e-9
    assert abs(roi(0, 0.50) + 1.02) < 1e-9
    assert roi(1, 0.0) is None and roi(1, 1.0) is None      # unfillable clipped
    # summarize: 2 days, day1 two wins @0.50 (+0.98 each), day2 one loss @0.50 (-1.02)
    rows = [{"day": "d1", "won": 1, "e": 0.5}, {"day": "d1", "won": 1, "e": 0.5},
            {"day": "d2", "won": 0, "e": 0.5}]
    s = summarize(rows, "e")
    assert s["n"] == 3 and s["neg_days"] == 1 and s["n_days"] == 2
    assert abs(s["per_bet"] - ((0.98 + 0.98 - 1.02) / 3)) < 1e-4      # per-bet equal-weight (4dp)
    assert abs(s["per_day"] - ((0.98 + -1.02) / 2)) < 1e-4           # per-day equal-weight (4dp)
    # dist: known percentiles on 0..4 (mean 2, median 2, p25 1, p75 3)
    d = dist([0, 1, 2, 3, 4])
    assert d["median"] == 2 and d["p25"] == 1 and d["p75"] == 3 and d["mean"] == 2
    assert dist([])["n"] == 0
    # build_entries: haircut/drift wiring; missing imp/ask -> None (excluded, not imputed)
    raw = [{"day": "d1", "won": "1", "mean_price": "0.60", "coalesced": "0.62",
            "imp": "0.61", "ask": "0.63"},
           {"day": "d1", "won": "0", "mean_price": "0.60", "coalesced": "0.60",
            "imp": "", "ask": ""}]
    be = build_entries(raw)
    assert abs(be[0]["e_a"] - 0.625) < 1e-9 and abs(be[0]["e_b"] - 0.615) < 1e-9
    assert abs(be[0]["e_d"] - (0.61 + 0.0174)) < 1e-9 and be[0]["e_c"] == 0.63
    assert be[1]["e_b"] is None and be[1]["e_c"] is None and be[1]["e_d"] is None
    # winner-inflation direction: adverse drift on winners, favorable on losers -> A4 sign holds
    syn = [{"day": "d", "won": 1, "mean_price": 0.7, "imp": 0.73, "ask": None,
            "e_a": None, "e_b": None, "e_c": None, "e_d": None},
           {"day": "d", "won": 0, "mean_price": 0.7, "imp": 0.66, "ask": None,
            "e_a": None, "e_b": None, "e_c": None, "e_d": None}]
    a4 = analyze(syn)["A4_winner_inflation"]
    assert a4["imp_drift_won"]["median"] > a4["imp_drift_lost"]["median"]
    print("self-test OK")


def main():
    raw = _q(SQL)
    rows = build_entries(raw)
    res = analyze(rows)
    res["A5_timing"] = a5_timing(_q(TRAJ_SQL))
    res["_meta"] = {"claim": "favorite ~+6.9%/bet after costs, 349 picks, 8 UTC days",
                    "haircut": HAIRCUT, "fee": FEE, "worst_drift": DRIFT_D,
                    "conventions": {"a": "COALESCE(initial_mean_price,mean_price)+0.5c [claim]",
                                    "b": "initial_market_price+0.5c [honest observed]",
                                    "c": "entry_ask [executable]",
                                    "d": "initial_market_price+1.74c [worst-defensible]"}}
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
