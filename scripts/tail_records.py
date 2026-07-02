#!/usr/bin/env python3
"""
TAIL-THE-SHARP TRACK RECORDS (deep-pool edge run, Phase 3) — read-only report.

The `sharp_tail_fresh` / `sharp_tail` arms (silent, behind CONSENSUS_TRUST_ARMS)
emit one signal per CERTIFIED trader's entry, decision-time captured. This report
turns their accrual into the per-trader EXECUTABLE track record: for each sharp,
the follower's realizable honest ROI over the tail signals that sharp backed —
"who is actually worth tailing" as a tailable record, not a leaderboard rank.

Metrics (the exact honest_pnl_by_strategy discipline, consensus.rs):
  entry       = COALESCE(entry_ask, initial_market_price + HAIRCUT)
  honest ROI  = (won − entry)/entry − FEE, event-clustered per wallet
  bound       = one-sided lower bound, Bonferroni across the wallets reported,
                N deflated to distinct UTC days (within-day correlation)
  survivor    = lower bound > MARGIN (3% capture cushion) at ≥30 events — the
                same bar as everything else. Below the floor: INDETERMINATE.
Also prints the fresh-vs-lagged CLV comparison (sharp_tail_fresh vs sharp_tail)
— the freshness premium a follower captures by acting inside 3h.

READ-ONLY. Run against a restored snapshot (never prod):
  PG_CONTAINER=pg-report ./scripts/tail_records.py
"""

import csv
import io
import os
import subprocess
import sys
from collections import defaultdict
from statistics import NormalDist

PG_CONTAINER = os.environ.get("PG_CONTAINER", "pg-report")
PG = ["docker", "exec", "-i", PG_CONTAINER,
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

HAIRCUT = 0.01
FEE = 0.02
MARGIN = 0.03
ALPHA = 0.05
MIN_EVENTS = 30

SQL = f"""
SELECT cs.strategy, COALESCE(cs.event_slug, cs.condition_id) AS ev,
       (cs.outcome_won::int) AS won,
       cs.initial_market_price AS p0,
       COALESCE(cs.entry_ask, cs.initial_market_price + {HAIRCUT}) AS entry,
       to_char(cs.first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
       b->>'wallet' AS wallet
FROM consensus_signals cs, jsonb_array_elements(cs.backers::jsonb) b
WHERE cs.strategy IN ('sharp_tail_fresh', 'sharp_tail')
  AND cs.resolved AND cs.initial_market_price IS NOT NULL
"""


def fetch():
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["won"] = int(r["won"])
        r["p0"] = float(r["p0"])
        r["entry"] = float(r["entry"])
        rows.append(r)
    return rows


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def main():
    rows = fetch()
    if not rows:
        print("no resolved tail-arm signals yet — the arms are silent until "
              "CONSENSUS_TRUST_ARMS is on AND a trader is certified. Honest zero.")
        return

    # Per-wallet, per-arm event clustering.
    per = defaultdict(lambda: defaultdict(lambda: {"hroi": [], "clv": [], "days": set()}))
    for r in rows:
        cell = per[(r["strategy"], r["wallet"])][r["ev"]]
        cell["hroi"].append((r["won"] - r["entry"]) / r["entry"] - FEE)
        cell["clv"].append(r["won"] - r["p0"])
        cell["days"].add(r["day"])

    # Collapse: per (arm, wallet) → event-level series.
    records = []
    for (arm, wallet), evs in per.items():
        hroi = [mean(c["hroi"]) for c in evs.values()]
        clv = [mean(c["clv"]) for c in evs.values()]
        days = set().union(*(c["days"] for c in evs.values()))
        records.append({"arm": arm, "wallet": wallet, "n": len(hroi),
                        "days": len(days), "hroi": mean(hroi), "sd": sd(hroi),
                        "clv": mean(clv)})

    n_wallets = len({r["wallet"] for r in records}) or 1
    z = NormalDist().inv_cdf(1.0 - min(max(ALPHA / n_wallets, 1e-6), 0.5))

    for arm in ("sharp_tail_fresh", "sharp_tail"):
        rs = sorted((r for r in records if r["arm"] == arm),
                    key=lambda r: -(r["hroi"] if r["hroi"] == r["hroi"] else -9))
        print(f"\n=== {arm}: {len(rs)} tailed sharps ===")
        for r in rs:
            eff_n = max(1, min(r["days"], r["n"]))  # day-deflated, fail-closed
            if r["n"] >= MIN_EVENTS and r["sd"] == r["sd"]:
                lb = r["hroi"] - z * r["sd"] / eff_n ** 0.5
                verdict = "✅ SURVIVOR" if lb > MARGIN else "⏳ hold"
                btxt = f"lb={lb:+.3f}"
            else:
                verdict, btxt = "⏸ N<floor", "lb=—"
            print(f"{verdict:>11} {r['wallet'][:14]:<14} N={r['n']:>4} "
                  f"days={r['days']:>3} hROI={r['hroi']:+.4f} {btxt} clv={r['clv']:+.4f}")

    # Freshness premium: arm-level CLV comparison over shared wallets.
    f = [r for r in records if r["arm"] == "sharp_tail_fresh"]
    l = [r for r in records if r["arm"] == "sharp_tail"]
    if f and l:
        print(f"\nfreshness premium (CLV, arm-level): fresh {mean([r['clv'] for r in f]):+.4f} "
              f"vs lagged {mean([r['clv'] for r in l]):+.4f}")
    print("\nSURVIVOR = event-clustered honest-ROI lower bound (Bonferroni across "
          f"{n_wallets} wallets, day-deflated N) > {MARGIN:.0%} at ≥{MIN_EVENTS} events. "
          "Paper only; promotion of any survivor stays a deliberate human call.")


if __name__ == "__main__":
    main()
