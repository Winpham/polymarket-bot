#!/usr/bin/env python3
"""
SCOREBOARD PARITY — safe-swap proof for the at-fire entry fix (2026-07-02 run, K1).

Runs BOTH scoreboard statistics against the live DB:
  OLD (drifted): a = outcome_won − mean_price          (upsert-overwritten entry; pre-run main)
  NEW (at-fire): a = outcome_won − COALESCE(initial_mean_price, mean_price)   (set-once entry)
identical in every other respect (band-blind baseline, event clustering, SD), and prints the
per-strategy before/after with the Bonferroni lower bound at the 3% capture margin.

K1 (binding): distinct_events must be IDENTICAL per strategy between OLD and NEW — the fix may
only change surplus values, never the sample. Exits non-zero on any N mismatch.
"""

import csv
import io
import subprocess
import sys
from math import sqrt
from statistics import NormalDist

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
MARGIN = 0.03
ALPHA = 0.05

TEMPLATE = """
WITH adv AS (
    SELECT strategy, COALESCE(event_slug, condition_id) AS ev, resolved, outcome_won,
           width_bucket({entry}, 0.0, 1.0, 5) AS band,
           (outcome_won::int)::double precision - {entry} AS a
    FROM consensus_signals
),
blind AS (
    SELECT band, AVG(a) AS blind_edge
    FROM adv WHERE strategy = '_blind' AND resolved GROUP BY band
),
sig AS (
    SELECT v.strategy, v.ev, v.resolved, v.a - COALESCE(b.blind_edge, 0) AS surplus
    FROM adv v LEFT JOIN blind b USING (band) WHERE v.strategy <> '_blind'
),
evt AS (
    SELECT strategy, ev, AVG(surplus) AS ev_surplus FROM sig WHERE resolved GROUP BY strategy, ev
)
SELECT strategy, COUNT(*) AS n_events, AVG(ev_surplus) AS surplus,
       STDDEV_SAMP(ev_surplus) AS surplus_sd
FROM evt GROUP BY strategy ORDER BY strategy
"""

OLD_ENTRY = "mean_price"
NEW_ENTRY = "COALESCE(initial_mean_price, mean_price)"


def run(entry):
    sql = TEMPLATE.format(entry=entry)
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    res = {}
    for r in csv.DictReader(io.StringIO(out.stdout)):
        res[r["strategy"]] = (
            int(r["n_events"]),
            float(r["surplus"]) if r["surplus"] else None,
            float(r["surplus_sd"]) if r["surplus_sd"] else None,
        )
    return res


def lb(surplus, sd, n, fam_n):
    if surplus is None or sd is None or n < 1:
        return None
    z = NormalDist().inv_cdf(1 - min(0.5, max(1e-6, ALPHA / max(1, fam_n))))
    return surplus - z * sd / sqrt(n)


def main():
    old, new = run(OLD_ENTRY), run(NEW_ENTRY)
    fam_n = len(new)  # every variant here is family=core (enrich::family)
    print(f"scoreboard parity · OLD entry = drifted mean_price · NEW = at-fire initial_mean_price")
    print(f"Bonferroni family n = {fam_n} · capture margin = {MARGIN:.0%} · floor N≥30")
    print(f"{'strategy':<18} {'N_old':>5} {'N_new':>5} {'surplus_old':>11} {'surplus_new':>11} "
          f"{'Δ':>7} {'LB_old':>8} {'LB_new':>8}  gate@3%")
    bad = 0
    for s in sorted(set(old) | set(new)):
        n_o, s_o, sd_o = old.get(s, (0, None, None))
        n_n, s_n, sd_n = new.get(s, (0, None, None))
        if n_o != n_n:
            bad += 1
        lo_o, lo_n = lb(s_o, sd_o, n_o, fam_n), lb(s_n, sd_n, n_n, fam_n)
        fmt = lambda x: f"{x:+.2%}" if x is not None else "—"
        delta = f"{(s_n - s_o):+.2%}" if (s_o is not None and s_n is not None) else "—"
        gate = "✅ PROMOTABLE" if (lo_n is not None and n_n >= 30 and lo_n > MARGIN) else "⏳"
        mark = "  ⚠ N CHANGED" if n_o != n_n else ""
        print(f"{s:<18} {n_o:>5} {n_n:>5} {fmt(s_o):>11} {fmt(s_n):>11} {delta:>7} "
              f"{fmt(lo_o):>8} {fmt(lo_n):>8}  {gate}{mark}")
    if bad:
        print(f"\nK1 VIOLATION: {bad} strategies changed N — the swap is NOT sample-preserving.")
        sys.exit(1)
    print("\nK1 OK: distinct-event N identical for every strategy; deltas are drift-removal only.")


if __name__ == "__main__":
    main()
