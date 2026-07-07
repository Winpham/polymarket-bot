#!/usr/bin/env python3
"""P0 coverage oracle — tape_coverage_observable_pct (feeds GATE 1).

Joins a captured tape (probe_f1_tape.py --mode capture output) to the tracked
sharp fills whose ts falls inside the capture window, and reports what fraction
of OBSERVABLE (two-sided-quotable) fills had at least one tape tick within +/-TOL
of the fill's exchange clock (ts). This is a LOWER BOUND on live coverage: the
probe subscribes to a STATIC 6h-lookback universe, while live_tape.rs refreshes
the subscription periodically, so a live system covers >= this number.

Read-only against the production DB (docker exec psql) + the captured JSONL.
"""
import argparse
import json
import subprocess
import sys
from bisect import bisect_left
from datetime import datetime, timezone

PG_CONTAINER = "polymarket-bot-postgres-1"
TOLS = [5, 30, 120]  # seconds; report coverage at each


def psql(sql):
    out = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", "bot", "-d", "polymarket",
         "-tAF", "\x1f", "-c", sql],
        capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return out.stdout


def load_tape(tape_path):
    """asset_id -> sorted list of exch_ts epoch-seconds (from the tape)."""
    ticks = {}
    with open(tape_path) as f:
        for line in f:
            if not line.strip():
                continue
            t = json.loads(line)
            a = t.get("asset_id")
            ems = t.get("exch_ts_ms")
            if not a or not ems:
                # fall back to recv_at if exch_ts missing (rare)
                if not a or not t.get("recv_at"):
                    continue
                sec = float(t["recv_at"])
            else:
                sec = int(ems) / 1000.0
            ticks.setdefault(a, []).append(sec)
    for a in ticks:
        ticks[a].sort()
    return ticks


def nearest_gap(sorted_secs, target):
    """min |tick - target| over the sorted list."""
    if not sorted_secs:
        return None
    i = bisect_left(sorted_secs, target)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(sorted_secs):
            g = abs(sorted_secs[j] - target)
            if best is None or g < best:
                best = g
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tape", default="reports/tape_capture.jsonl")
    ap.add_argument("--token-map", default="reports/token_map.json")
    ap.add_argument("--probe-out", default="reports/live_ingestion_probe.json")
    args = ap.parse_args()

    meta = json.load(open(args.tape + ".assets.json"))
    win_start, win_end = meta["window_start"], meta["window_end"]
    start_iso = datetime.fromtimestamp(win_start, timezone.utc).isoformat()
    end_iso = datetime.fromtimestamp(win_end, timezone.utc).isoformat()
    print(f"[cov] window {start_iso} .. {end_iso}", file=sys.stderr)

    tm = json.load(open(args.token_map))["token_map"]
    # (condition_id, outcome_index) -> (token_id, quotable)
    key2tok = {}
    for tid, v in tm.items():
        key2tok[(v["condition_id"], v["outcome_index"])] = (tid, v["quotable"])

    tape = load_tape(args.tape)

    # tracked sharp fills whose ts is inside the capture window
    sql = (
        "SELECT condition_id, outcome_index, extract(epoch from ts), tx_hash, price, side "
        "FROM trader_fills "
        f"WHERE ts >= '{start_iso}' AND ts <= '{end_iso}' AND is_sports "
        "AND wallet IN (SELECT lower(proxy_wallet) FROM followed_traders)")
    rows = [ln.split("\x1f") for ln in psql(sql).splitlines() if ln.strip()]
    print(f"[cov] {len(rows)} tracked sharp fills in window", file=sys.stderr)

    total = len(rows)
    observable = 0
    unquotable = 0
    unknown_market = 0     # condition not in token map (new / unresolvable)
    not_subscribed = 0     # quotable but asset never appeared on tape
    covered = {t: 0 for t in TOLS}
    gaps = []
    for cond, oidx_s, ts_s, tx, price_s, side in rows:
        oidx = int(oidx_s)
        ts = float(ts_s)  # epoch seconds from SQL (tz-safe)
        tok_info = key2tok.get((cond, oidx))
        if tok_info is None:
            unknown_market += 1
            continue
        tid, quotable = tok_info
        if not quotable:
            unquotable += 1
            continue
        observable += 1
        secs = tape.get(tid)
        if not secs:
            not_subscribed += 1
            continue
        g = nearest_gap(secs, ts)
        gaps.append(g)
        for t in TOLS:
            if g is not None and g <= t:
                covered[t] += 1

    cov_pct = {t: round(100.0 * covered[t] / max(1, observable), 2) for t in TOLS}
    result = {
        "window_start": start_iso, "window_end": end_iso,
        "window_minutes": round((win_end - win_start) / 60, 1),
        "total_tracked_fills": total,
        "observable_fills": observable,
        "unquotable_fills": unquotable,
        "unknown_market_fills": unknown_market,
        "not_subscribed_fills": not_subscribed,
        "coverage_observable_pct_by_tol": cov_pct,
        # headline number the gate uses (30s TOL): can we reconstruct the price near the fill
        "tape_coverage_observable_pct": cov_pct[30],
        "median_gap_s": round(sorted(g for g in gaps if g is not None)[len(gaps)//2], 2) if gaps else None,
    }
    print(json.dumps(result, indent=1), file=sys.stderr)

    try:
        report = json.load(open(args.probe_out))
    except (FileNotFoundError, ValueError):
        report = {}
    report.setdefault("f1_clob_ws", {})["tape_coverage_observable_pct"] = result["tape_coverage_observable_pct"]
    report["coverage_detail"] = result
    json.dump(report, open(args.probe_out, "w"), indent=1)
    print(f"[cov] tape_coverage_observable_pct(30s) = {result['tape_coverage_observable_pct']}%",
          file=sys.stderr)


if __name__ == "__main__":
    main()
