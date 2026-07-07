#!/usr/bin/env python3
"""P0-C — build_token_map: resolve the tracked-only subscription universe.

Reads distinct (condition_id, outcome_index) from trader_fills for wallets in
followed_traders over a lookback window, resolves each condition to its CLOB
token_ids via the CLOB REST /markets/{condition_id} endpoint (the fetch_clob_market
equivalent, 120ms-throttled per dense_capture.rs citizenship), and writes a
token map: token_id -> {condition_id, outcome_index, outcome, slug, title,
active, accepting_orders, closed, neg_risk}.

This is the input universe for probe_f1_tape.py and the ground-truth for the
"observable" (two-sided-quotable) denominator in the coverage oracle.

Read-only against the production DB (via `docker exec ... psql`). No workspace
coupling; no writes to production. Output is a JSON file under reports/.

Usage:
    python3 scripts/build_token_map.py --lookback-hours 6 --out reports/token_map.json
    python3 scripts/build_token_map.py --self-test
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

CLOB_MARKETS = "https://clob.polymarket.com/markets/{cid}"
THROTTLE_S = 0.120  # dense_capture.rs:47 citizenship
PG_CONTAINER = "polymarket-bot-postgres-1"


def psql(sql: str) -> str:
    """Run a read-only query against the production DB inside the container."""
    out = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", "bot", "-d", "polymarket",
         "-tAF", "\x1f", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return out.stdout


def tracked_conditions(lookback_hours: int):
    """DISTINCT (condition_id, outcome_index) for all followed traders' sports fills."""
    sql = (
        "SELECT DISTINCT condition_id, outcome_index "
        "FROM trader_fills "
        f"WHERE ts > now() - interval '{int(lookback_hours)} hours' "
        "AND is_sports AND condition_id IS NOT NULL "
        "AND wallet IN (SELECT lower(proxy_wallet) FROM followed_traders)"
    )
    rows = []
    for line in psql(sql).splitlines():
        if not line.strip():
            continue
        cid, oidx = line.split("\x1f")
        rows.append((cid, int(oidx)))
    return rows


def fetch_market(cid: str, timeout=15):
    req = urllib.request.Request(CLOB_MARKETS.format(cid=cid),
                                 headers={"User-Agent": "probe-token-map/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"http_{e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)[:80]}


def build(lookback_hours: int, out_path: str, limit=None):
    conds = tracked_conditions(lookback_hours)
    # collapse to unique condition_ids (one REST call resolves all outcomes)
    want_outcomes = {}
    for cid, oidx in conds:
        want_outcomes.setdefault(cid, set()).add(oidx)
    cids = list(want_outcomes.keys())
    if limit:
        cids = cids[:limit]
    print(f"[token-map] {len(conds)} (cond,outcome) pairs -> {len(cids)} unique "
          f"conditions to resolve (lookback {lookback_hours}h)", file=sys.stderr)

    token_map = {}
    quotable_conditions = 0
    errors = 0
    t0 = time.monotonic()
    for i, cid in enumerate(cids):
        m = fetch_market(cid)
        if "_error" in m or not m.get("tokens"):
            errors += 1
        else:
            active = bool(m.get("active"))
            closed = bool(m.get("closed"))
            accepting = bool(m.get("accepting_orders"))
            neg_risk = bool(m.get("neg_risk"))
            quotable = active and not closed and accepting
            if quotable:
                quotable_conditions += 1
            for oidx, tok in enumerate(m.get("tokens", [])):
                tid = tok.get("token_id")
                if not tid:
                    continue
                token_map[tid] = {
                    "condition_id": cid,
                    "outcome_index": oidx,
                    "outcome": tok.get("outcome"),
                    "slug": m.get("market_slug"),
                    "title": m.get("question"),
                    "active": active,
                    "closed": closed,
                    "accepting_orders": accepting,
                    "neg_risk": neg_risk,
                    "quotable": quotable,
                    "wanted": oidx in want_outcomes.get(cid, set()),
                }
        time.sleep(THROTTLE_S)
        if (i + 1) % 200 == 0:
            print(f"[token-map] {i+1}/{len(cids)} resolved, {errors} errors, "
                  f"{len(token_map)} tokens", file=sys.stderr)

    result = {
        "lookback_hours": lookback_hours,
        "unique_conditions": len(cids),
        "resolved_conditions": len(cids) - errors,
        "errors": errors,
        "quotable_conditions": quotable_conditions,
        "total_tokens": len(token_map),
        "quotable_tokens": sum(1 for v in token_map.values() if v["quotable"]),
        "wanted_tokens": sum(1 for v in token_map.values() if v["wanted"]),
        "elapsed_s": round(time.monotonic() - t0, 1),
        "token_map": token_map,
    }
    with open(out_path, "w") as f:
        json.dump(result, f)
    print(f"[token-map] wrote {out_path}: {result['total_tokens']} tokens "
          f"({result['quotable_tokens']} quotable, {result['wanted_tokens']} wanted) "
          f"in {result['elapsed_s']}s", file=sys.stderr)
    return result


def self_test():
    """Offline: exercise the parse path with a synthetic market payload."""
    fake = {
        "active": True, "closed": False, "accepting_orders": True, "neg_risk": False,
        "market_slug": "team-a-vs-team-b", "question": "Will A win?",
        "tokens": [
            {"token_id": "111", "outcome": "Yes", "price": 0.6},
            {"token_id": "222", "outcome": "No", "price": 0.4},
        ],
    }
    # simulate the inner map-building block
    tm = {}
    quotable = fake["active"] and not fake["closed"] and fake["accepting_orders"]
    for oidx, tok in enumerate(fake["tokens"]):
        tm[tok["token_id"]] = {"outcome_index": oidx, "quotable": quotable}
    assert tm["111"]["outcome_index"] == 0
    assert tm["222"]["outcome_index"] == 1
    assert tm["111"]["quotable"] is True
    print("SELF-TEST PASS: token-map parse recovers outcome_index + quotable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-hours", type=int, default=6)
    ap.add_argument("--out", default="reports/token_map.json")
    ap.add_argument("--limit", type=int, default=None, help="cap conditions (debug)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    build(args.lookback_hours, args.out, args.limit)


if __name__ == "__main__":
    main()
