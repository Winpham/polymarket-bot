#!/usr/bin/env python3
"""
SIZED SHADOW BOOK — read-only surfacing of the Kelly-sized shadow labels.

The sized book (`decide()` kernel) writes rows under `{strategy}__k12` LABELS in
the EXISTING `honest_paper_ledger`, alongside the untouched flat champion. Those
labels do NOT auto-appear in the honest scoreboard panel (`honest_pnl_by_strategy`
reads `consensus_signals` GROUP BY strategy, and the shadow label has no signal
rows of its own — it reuses `favorite`'s signals via `source_strategy`). This
script surfaces them straight off the ledger.

Per shadow label it reports the same stats as Rust `LedgerStats::from_rows`
(the board's own accounting), computed here read-only:
  bets, turnover (Σstake), total P&L (Σpnl), ROI-on-turnover (Σpnl/Σstake,
  STAKE-WEIGHTED — so Kelly sizing is visible), win-rate, peak, max drawdown ($),
  daily-returns Sharpe.

Read-only: SELECT only, no writes, no schema, no network, no LLM. The champion
`favorite` book is never touched.

Usage:
  ./sized_book.py               # live: print stats for every %__k% shadow label
  ./sized_book.py --selftest    # no DB: verify the stat math on synthetic rows
"""

import csv
import io
import math
import subprocess
import sys
from collections import defaultdict

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# `strategy ~ '__k'` (POSIX regex; `_` is a literal underscore) matches the sized
# shadow labels (favorite__k12, …) without LIKE-escape quoting pitfalls.
SQL = """
SELECT strategy, resolved_at, stake, pnl, outcome_won, entry
FROM honest_paper_ledger
WHERE strategy ~ '__k'
ORDER BY strategy, resolved_at, id
"""


def fetch():
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        rows.append(dict(
            strategy=r["strategy"],
            resolved_at=r["resolved_at"],
            stake=float(r["stake"]),
            pnl=float(r["pnl"]),
            won=r["outcome_won"] in ("t", "true", "1"),
            entry=float(r["entry"]),
        ))
    return rows


def stats(rows):
    """Mirror of LedgerStats::from_rows (stake-weighted ROI, max DD, daily Sharpe)."""
    bets = len(rows)
    turnover = sum(r["stake"] for r in rows)
    total_pnl = sum(r["pnl"] for r in rows)
    wins = sum(1 for r in rows if r["won"])
    roi = total_pnl / turnover if turnover > 0 else float("nan")
    win_rate = wins / bets if bets else float("nan")
    # running equity → peak, max drawdown
    equity = 0.0
    peak = float("-inf")
    max_dd = 0.0
    for r in rows:
        equity += r["pnl"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    # daily-returns Sharpe (de-correlates within-day bets), matching the Rust panel
    by_day = defaultdict(float)
    for r in rows:
        by_day[r["resolved_at"][:10]] += r["pnl"]
    days = list(by_day.values())
    if len(days) >= 2:
        mean = sum(days) / len(days)
        sd = math.sqrt(sum((d - mean) ** 2 for d in days) / (len(days) - 1))
        sharpe = mean / sd if sd > 0 else 0.0
    else:
        sharpe = 0.0
    return dict(bets=bets, turnover=turnover, total_pnl=total_pnl, roi=roi,
                win_rate=win_rate, peak=max(peak, 0.0), max_dd=max_dd, sharpe=sharpe)


def run_live():
    rows = fetch()
    if not rows:
        print("SIZED SHADOW BOOK — no %__k% rows yet.")
        print("  Expected while k=0: the kernel books stake=0 until kernel_gate.json certifies an")
        print("  edge (today readiness_fraction=0.0). Nothing to show is the correct state.")
        return 0
    by_label = defaultdict(list)
    for r in rows:
        by_label[r["strategy"]].append(r)
    print("SIZED SHADOW BOOK — Kelly-sized shadow labels (paper, read-only; champion untouched)\n")
    print(f"{'label':<20} {'bets':>5} {'turnover$':>11} {'pnl$':>10} {'ROI-turn':>9} "
          f"{'win%':>5} {'maxDD$':>9} {'sharpe':>7}")
    for label in sorted(by_label):
        s = stats(by_label[label])
        print(f"{label:<20} {s['bets']:>5} {s['turnover']:>11.2f} {s['total_pnl']:>+10.2f} "
              f"{s['roi']:>+8.2%} {s['win_rate']:>4.0%} {s['max_dd']:>9.2f} {s['sharpe']:>7.2f}")
    print("\nROI-on-turnover is STAKE-WEIGHTED (Σpnl/Σstake) — the sized book's realizable edge.")
    print("Verdict is readable only after FORWARD weeks; k=0 today means no rows accrue yet.")
    return 0


def _self_test():
    ok = True
    # two winners ($120 stake, +$40 each) and one loser ($60 stake, -$60), 2 days
    rows = [
        dict(resolved_at="2026-07-01T10:00:00Z", stake=120.0, pnl=40.0, won=True, entry=0.75),
        dict(resolved_at="2026-07-01T12:00:00Z", stake=60.0, pnl=-60.0, won=False, entry=0.80),
        dict(resolved_at="2026-07-02T09:00:00Z", stake=120.0, pnl=40.0, won=True, entry=0.75),
    ]
    s = stats(rows)
    c1 = s["bets"] == 3 and abs(s["turnover"] - 300.0) < 1e-9
    c2 = abs(s["total_pnl"] - 20.0) < 1e-9 and abs(s["roi"] - 20.0 / 300.0) < 1e-9
    # equity path 40, -20, 20 → peak 40, trough -20 → maxDD 60
    c3 = abs(s["max_dd"] - 60.0) < 1e-9 and abs(s["peak"] - 40.0) < 1e-9
    # win rate 2/3
    c4 = abs(s["win_rate"] - 2.0 / 3.0) < 1e-9
    # daily pnl: day1 = 40-60 = -20, day2 = 40 → mean 10, sd = sqrt(((-30)^2+30^2)/1)=42.43 → sharpe .2357
    c5 = abs(s["sharpe"] - (10.0 / math.sqrt((900.0 + 900.0)))) < 1e-6
    for name, c in [("counts+turnover", c1), ("pnl+stake-weighted-ROI", c2),
                    ("peak+maxDD", c3), ("win-rate", c4), ("daily-sharpe", c5)]:
        print(f"  [{'ok' if c else 'FAIL'}] {name}")
        ok = ok and c
    # empty → nan ROI, no crash
    e = stats([])
    c6 = e["bets"] == 0 and math.isnan(e["roi"])
    print(f"  [{'ok' if c6 else 'FAIL'}] empty book handled")
    ok = ok and c6
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_live())
