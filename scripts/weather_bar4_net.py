#!/usr/bin/env python3
"""
BAR #4 — realizable net-EV of weather_fav at the REAL captured decision-time ask, on OFFICIAL
settlement (Polymarket CLOB resolution `outcome_won`; weather is intl-only so this IS the official
label), net of the CORRECTED fee. Also serves §4 (cost re-net: corrected fee vs the phantom 3%).

Basis (frozen): realizable ROI-on-turnover per pick = (won - a)/a - fee/a, where
  a   = entry_ask  (the real decision-time ask actually captured on the arm signal, D4-clean lane).
  fee = FEE_RATE * a * (1-a)   (the corrected Polymarket taker fee; ~0.5c at the favourite band,
        vs the phantom flat 3% = 3c the old verdicts charged). Day-clustered (heat domes correlate
        cities within a day ⇒ the resolution DAY is the honest independent unit). One-sided 95% LB by
        day-cluster bootstrap.

Reports band 0.71-0.90 (primary cert cell) and full 0.71-0.98, with n + dispersion + n_days.
λ (bar #2) gates; this only re-scales. Read-only.
"""
import csv
import io
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1", "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
FEE_RATE = 0.03            # corrected fee: FEE_RATE * p * (1-p)  (prereg convention)
OLD_COST = 0.03           # the phantom flat 3%-of-turnover the old verdicts charged
SEED = 20260715
REPORTS = Path(__file__).resolve().parent.parent / "reports"

SQL = """
SELECT (resolved_at AT TIME ZONE 'UTC')::date AS day,
       initial_mean_price AS imp, entry_ask AS ask, entry_ask_mid AS ask_mid,
       (outcome_won::int) AS won
FROM consensus_signals
WHERE strategy='weather_fav' AND resolved AND outcome_won IS NOT NULL
  AND entry_ask IS NOT NULL AND entry_ask>0 AND initial_mean_price IS NOT NULL
"""


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def day_clustered_mean(pairs):
    m = defaultdict(list)
    for d, v in pairs:
        m[d].append(v)
    means = {d: sum(v) / len(v) for d, v in m.items()}
    return (sum(means.values()) / len(means) if means else float("nan")), means


def boot_lb(day_means, rng, n=5000, alpha=0.05):
    keys = list(day_means.keys())
    if len(keys) < 2:
        return float("nan")
    draws = []
    for _ in range(n):
        s = [day_means[keys[rng.randrange(len(keys))]] for _ in keys]
        draws.append(sum(s) / len(s))
    draws.sort()
    return draws[int(alpha * len(draws))]


def measure(rows, lo, hi):
    sub = [r for r in rows if lo <= float(r["imp"]) < hi]
    if not sub:
        return {"band": [lo, hi], "n": 0}
    rng = random.Random(SEED)
    # realizable ROI at ask, corrected fee
    roi_corr, roi_old, roi_grossmid = [], [], []
    fees = []
    for r in sub:
        a = float(r["ask"]); won = int(r["won"]); mid = float(r["ask_mid"])
        fee = FEE_RATE * a * (1 - a)
        fees.append(fee)
        roi_corr.append((r["day"], (won - a) / a - fee / a))
        roi_old.append((r["day"], (won - a) / a - OLD_COST))
        roi_grossmid.append((r["day"], (won - mid) / mid))  # gross at mid, no fee (the copyable proxy)
    m_corr, dm_corr = day_clustered_mean(roi_corr)
    m_old, _ = day_clustered_mean(roi_old)
    m_gross, _ = day_clustered_mean(roi_grossmid)
    lb_corr = boot_lb(dm_corr, rng)
    win = sum(int(r["won"]) for r in sub) / len(sub)
    return {
        "band": [lo, hi], "n": len(sub), "n_days": len(dm_corr),
        "win_rate": round(win, 3),
        "mean_ask": round(sum(float(r["ask"]) for r in sub) / len(sub), 4),
        "mean_fee_cents": round(100 * sum(fees) / len(fees), 3),
        "roi_at_ask_corrected_fee": round(m_corr, 4), "roi_LB_corrected": round(lb_corr, 4),
        "roi_at_ask_OLD_3pct": round(m_old, 4),
        "roi_at_mid_gross": round(m_gross, 4),
        "day_means_corrected": {d: round(v, 4) for d, v in sorted(dm_corr.items())},
    }


def main():
    rows = q(SQL)
    res = {
        "note": "official settlement = Polymarket CLOB resolution (weather intl-only, no US DMR). "
                "Fee corrected to FEE_RATE*p*(1-p); old verdicts used a flat 3%. λ (bar#2) gates.",
        "fee_rate": FEE_RATE,
        "band_0.71_0.90": measure(rows, 0.71, 0.90),
        "band_0.71_0.98": measure(rows, 0.71, 0.98),
        "band_0.90_0.98_deepchalk": measure(rows, 0.90, 0.98),
    }
    print(json.dumps(res, indent=2))
    (REPORTS / "weather_bar4_net.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
