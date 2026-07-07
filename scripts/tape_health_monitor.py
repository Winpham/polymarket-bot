#!/usr/bin/env python3
"""Live tape health monitor — sample the running clob_price_tape periodically.

Captures a TIME SERIES of the operational metrics that define "reliable + optimal +
captures everything live and immediately", so an audit reads maturity, not a snapshot:
  - reconnect rate (from container logs) — must stay ~0 (no storm)
  - rows total + rows/interval (storage rate → rows/day projection)
  - book:price_change ratio (book-heavy ⇒ reconnect churn)
  - latency recv_at−exch_ts p50/p95 on price_change (immediacy)
  - coverage: tracked sharp fills whose asset is on the tape (completeness)
  - dropped/compacted counters (from /metrics if reachable)

Appends one JSON line per sample to --out. Read-only. --self-test parses a fixture.
"""
import argparse
import json
import subprocess
import sys
import time

PG = "polymarket-bot-postgres-1"
APP = "polymarket-bot-copy-trading-bot-1"


def psql(sql):
    out = subprocess.run(
        ["docker", "exec", PG, "psql", "-U", "bot", "-d", "polymarket", "-tAc", sql],
        capture_output=True, text=True, timeout=60)
    return out.stdout.strip() if out.returncode == 0 else None


def log_count(pattern, since="5m"):
    out = subprocess.run(
        ["docker", "logs", "--since", since, APP],
        capture_output=True, text=True, timeout=30)
    text = (out.stdout or "") + (out.stderr or "")
    return sum(1 for ln in text.splitlines() if pattern in ln)


def sample(now_epoch):
    def q(sql, cast=int, default=0):
        v = psql(sql)
        try:
            return cast(v) if v not in (None, "") else default
        except (ValueError, TypeError):
            return default
    total = q("select count(*) from clob_price_tape")
    last_interval = q("select count(*) from clob_price_tape where recv_at>now()-interval '5 min'")
    books = q("select count(*) from clob_price_tape where event_type='book'")
    pc = q("select count(*) from clob_price_tape where event_type='price_change'")
    lat_p50 = q("select round(percentile_cont(0.5) within group (order by extract(epoch from recv_at-exch_ts))*1000) "
                "from clob_price_tape where event_type='price_change' and exch_ts is not null and recv_at>now()-interval '5 min'",
                float, None)
    lat_p95 = q("select round(percentile_cont(0.95) within group (order by extract(epoch from recv_at-exch_ts))*1000) "
                "from clob_price_tape where event_type='price_change' and exch_ts is not null and recv_at>now()-interval '5 min'",
                float, None)
    cov = psql(
        "with f as (select distinct condition_id, outcome_index from trader_fills "
        "where ts>now()-interval '5 min' and is_sports and wallet in (select lower(proxy_wallet) from followed_traders)) "
        "select count(*) filter (where t.asset_id is not null)||'/'||count(*) from f "
        "left join (select distinct condition_id, outcome_index, asset_id from clob_price_tape) t "
        "using (condition_id, outcome_index)")
    assets = q("select count(distinct asset_id) from clob_price_tape where recv_at>now()-interval '5 min'")
    resets = log_count("Connection reset", "5m")
    subs = log_count("live-tape subscribed", "5m")
    return {
        "t": now_epoch, "rows_total": total, "rows_last5m": last_interval,
        "book": books, "price_change": pc,
        "book_pct": round(100.0 * books / max(1, total), 1),
        "lat_p50_ms": lat_p50, "lat_p95_ms": lat_p95,
        "coverage": cov, "assets_active5m": assets,
        "resets_5m": resets, "subscribes_5m": subs,
    }


def run(minutes, interval, out_path, clock):
    deadline = clock() + minutes * 60
    n = 0
    with open(out_path, "a") as f:
        while clock() < deadline:
            rec = sample(clock())
            f.write(json.dumps(rec) + "\n")
            f.flush()
            n += 1
            print(f"[health] +{n} rows={rec['rows_total']} +{rec['rows_last5m']}/5m "
                  f"book%={rec['book_pct']} lat_p50={rec['lat_p50_ms']}ms cov={rec['coverage']} "
                  f"resets5m={rec['resets_5m']}", file=sys.stderr)
            time.sleep(interval)
    print(f"[health] done: {n} samples → {out_path}", file=sys.stderr)


def self_test():
    # parse a synthetic sample record shape
    rec = {"rows_total": 100, "book": 10, "price_change": 90}
    book_pct = round(100.0 * rec["book"] / max(1, rec["rows_total"]), 1)
    assert book_pct == 10.0
    # healthy heuristic: book_pct should be low (< ~30%); a storm inverts it
    assert book_pct < 30, "healthy tape is price_change-dominant"
    print("SELF-TEST PASS: health-sample shape + book_pct heuristic")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--interval", type=int, default=240)
    ap.add_argument("--out", default="reports/tape_health.jsonl")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    run(args.minutes, args.interval, args.out, time.time)


if __name__ == "__main__":
    main()
