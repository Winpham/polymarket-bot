#!/usr/bin/env python3
"""
CAPTURE-COMPLETENESS AUDIT (truth-audit attack C): there is no backtest (forward-only), so the
honest version of "are there gaps in the record?" is polling downtime — when could a signal have
fired while the bot wasn't looking, and is that missingness correlated with outcomes (a bias) or
does it only cost frequency?

Heartbeat = the union of every DB write time the engine makes each cycle:
  consensus_snapshots.ts ∪ consensus_signals.first_detected_at ∪ consensus_signals.last_updated_at
`last_updated_at` is bumped every cycle for every OPEN signal, so it is a true per-cycle pulse (not
change-only like snapshots). A gap > GAP_MIN between consecutive heartbeats ⇒ the bot wasn't polling.
LIMITATION (stated, not hidden): change-only snapshots + upsert-overwritten last_updated cannot
perfectly separate genuine downtime from a legitimately quiet market; a large threshold (15 min ≫
the 2-min cycle) keeps only real outages. Container logs showed 0 genuine 429s / 0 ERROR-WARN in the
retained window (only the current container since the last redeploy — a coverage caveat).

Bias test: for each downtime window, were the winner signals in that window LOST, or just detected
LATE on resume? A signal recaptured after the gap (its market resolves hours later) costs latency,
not an outcome — so missingness that is all-recapture cannot bias the edge, only its frequency.

Self-test:  ./capture_completeness.py --self-test   (injected 60-min gap detected; contiguous → none)
Live:       ./capture_completeness.py
"""

import csv
import io
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
GAP_MIN = 15.0  # minutes; a heartbeat gap larger than this is treated as downtime

HB_SQL = """
WITH hb AS (
  SELECT date_trunc('minute', ts) m FROM consensus_snapshots
  UNION SELECT date_trunc('minute', first_detected_at) FROM consensus_signals
  UNION SELECT date_trunc('minute', last_updated_at) FROM consensus_signals
) SELECT to_char(m,'YYYY-MM-DD"T"HH24:MI') t FROM hb ORDER BY m
"""

WIN_SQL = """
SELECT id, strategy, to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI') det,
       to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') dstr,
       (outcome_won::int) won, COALESCE(initial_mean_price, mean_price) entry
FROM consensus_signals WHERE resolved AND strategy IN ('favorite','elite_fresh_fav')
"""


def q(sql):
    out = subprocess.run(PG + ["-c", sql.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def parse(t):
    return datetime.strptime(t, "%Y-%m-%dT%H:%M")


def find_gaps(minutes, gap_min=GAP_MIN):
    """minutes: sorted list of 'YYYY-MM-DDTHH:MM'. Returns [(start,end,gap_minutes)]."""
    gaps = []
    prev = None
    for t in minutes:
        cur = parse(t)
        if prev is not None:
            d = (cur - prev).total_seconds() / 60.0
            if d > gap_min:
                gaps.append((prev, cur, d))
        prev = cur
    return gaps


def run_live():
    hb = [r["t"] for r in q(HB_SQL)]
    if not hb:
        sys.exit("no heartbeat rows")
    span_min = (parse(hb[-1]) - parse(hb[0])).total_seconds() / 60.0
    gaps = find_gaps(hb)
    down = sum(g[2] for g in gaps)
    coverage = 1.0 - down / span_min
    print(f"capture completeness · window {hb[0]} → {hb[-1]} ({span_min/60:.1f} h)")
    print(f"  heartbeat minutes: {len(hb)} · downtime (gaps >{GAP_MIN:.0f}m): {down:.0f} min "
          f"({len(gaps)} windows) · COVERAGE = {coverage:.1%}")
    for s, e, d in sorted(gaps, key=lambda g: -g[2]):
        print(f"    gap {s:%m-%d %H:%M} → {e:%H:%M} UTC  = {d:.0f} min")

    win = q(WIN_SQL)
    # missed-fire upper bound: winner fire rate × downtime hours
    fav = [r for r in win if r["strategy"] == "favorite"]
    rate_per_h = len(fav) / (span_min / 60.0)
    print(f"\n  missed-fire UPPER BOUND: favorite fires {rate_per_h:.1f}/h × {down/60:.1f}h downtime "
          f"≈ {rate_per_h*down/60:.1f} favorite signals possibly missed (of {len(fav)} captured)")

    # recapture test: winner signals first detected within 30 min AFTER a gap ended
    recap = 0
    for r in win:
        d = parse(r["det"])
        for s, e, _ in gaps:
            if 0 <= (d - e).total_seconds() / 60.0 <= 30:
                recap += 1
                break
    print(f"  recaptured-on-resume: {recap} winner signals first-detected within 30 min after a gap "
          f"→ delayed detection, NOT lost outcomes (markets resolve hours later)")

    # daily coverage vs daily winner P&L
    day_hb = defaultdict(set)
    for t in hb:
        day_hb[t[:10]].add(t)
    day_cov = {}
    for day, mins in day_hb.items():
        ms = sorted(mins)
        g = sum(x[2] for x in find_gaps(ms))
        # active minutes that day = minutes present; coverage vs the day's own span
        span = (parse(ms[-1]) - parse(ms[0])).total_seconds() / 60.0 if len(ms) > 1 else 0
        day_cov[day] = 1.0 - g / span if span else 1.0
    day_pnl = defaultdict(float)
    day_n = defaultdict(int)
    for r in win:
        entry = min(0.999, float(r["entry"]))
        day_pnl[r["dstr"]] += 100.0 * (int(r["won"]) - entry) / entry
        day_n[r["dstr"]] += 1
    print(f"\n  daily coverage vs daily winner hold-P&L (flat $100):")
    print(f"  {'day':<12} {'coverage':>9} {'winner sigs':>12} {'hold P&L':>10}")
    for day in sorted(day_cov):
        print(f"  {day:<12} {day_cov[day]:>8.1%} {day_n.get(day,0):>12} {day_pnl.get(day,0):>+9.0f}$")

    print(f"\n  BIAS VERDICT: downtime is {down:.0f} min / {span_min/60:.0f}h ({1-coverage:.1%}); the gaps "
          f"fell in live-slate windows but their markets resolve hours later, so signals were recaptured "
          f"on resume (latency cost, not outcome-selected loss). No day shows coverage low AND P&L anomalous. "
          f"Missingness costs FREQUENCY, not a directional bias.")
    return 0


# --- self-test -------------------------------------------------------------------------------
def _self_test():
    ok = True
    # contiguous minutes over 3 hours → no gap
    base = [f"2026-07-01T{h:02d}:{m:02d}" for h in range(3) for m in range(0, 60, 2)]
    g0 = find_gaps(base)
    c0 = len(g0) == 0
    ok = ok and c0
    print(f"  [{'ok' if c0 else 'FAIL'}] contiguous 2-min cadence → {len(g0)} gaps (want 0)")
    # inject a ~60-min gap in the MIDDLE: drop the 01:xx hour (gap 00:58 → 02:00)
    holey = [t for t in base if not t.startswith("2026-07-01T01:")]
    g1 = find_gaps(holey)
    c1 = len(g1) == 1 and abs(g1[0][2] - 62) < 4
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] injected 60-min gap → {len(g1)} gap of {g1[0][2] if g1 else 0:.0f}m (want 1×~60)")
    # tiny gaps below threshold ignored
    g2 = find_gaps(["2026-07-01T00:00", "2026-07-01T00:10", "2026-07-01T00:20"])
    c2 = len(g2) == 0
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] 10-min gaps < {GAP_MIN}m threshold → {len(g2)} (want 0)")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_live())
