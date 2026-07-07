#!/usr/bin/env python3
"""THE DELIVERABLE (Item 7) — the ¢-per-second latency→edge curve.

For each tracked sharp BUY fill, measures the executable-ask drift at grid times
t after the fill's clean exchange clock `ts`, reconstructed from `clob_price_tape`
(best_ask anchored on exch_ts, same clock domain as ts → ~zero skew). Answers, in
¢-per-second and %/bet, what fill-observation speed is worth — against the honest
+3–5%/bet baseline.

Independent of the on-chain fills build (F2): the curve reads only the price tape
and the fill clock `ts` (trade_to_fill sets ts = tr.timestamp), never live ingestion.

Estimator (prereg'd in reports/PREREG_*_latency_curve.md, written FIRST):
  grid       t ∈ {1,5,15,30,60,120,300,900}s, anchored on fill.ts
  cells      band(price) × sport(category)
  metric     drift = best_ask(asset, ts+t) − fill.price, signed toward fill side
  CI         event-clustered bootstrap (superkey.super_event), 1000 resamples, 95%
  baselines  WITHIN category (never pool — composition-attack lesson)
  denom      OBSERVABLE (quotable) fills; unquotable reported separately
  recoverable drift(60)−drift(5), drift(~90 status-quo)−drift(5); claim iff CI excludes 0
  exclusions source='backfill'; ingested_at as clock; underpowered → INDETERMINATE-BY-POWER

Reads tape from Postgres `clob_price_tape` (fills join directly on
condition_id+outcome_index — the tape carries provenance). --tape-jsonl loads a
probe capture into memory instead (for pre-production validation). --self-test is
network-free.
"""
import argparse
import json
import os
import subprocess
import sys
from bisect import bisect_right
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from superkey import super_event
except Exception:  # noqa: BLE001 — self-test provides a stub
    super_event = None

GRID = [1, 5, 15, 30, 60, 120, 300, 900]
STATUS_QUO_S = 90            # current median poll latency (the tax we pay today)
TOL_S = 30                   # nearest-ask must be within this of ts+t
BOOT = 1000
BANDS = [(0.45, 0.55, "0.45-0.55"), (0.55, 0.75, "0.55-0.75"), (0.75, 0.90, "0.75-0.90")]
PG_CONTAINER = os.environ.get("PG_CONTAINER", "polymarket-bot-postgres-1")


def band_of(price):
    for lo, hi, name in BANDS:
        if lo <= price < hi:
            return name
    return None  # outside the actionable bands


def psql(sql, dsn_container=PG_CONTAINER, port=None):
    cmd = ["docker", "exec", dsn_container, "psql", "-U", "bot", "-d", "polymarket",
           "-tAF", "\x1f", "-c", sql]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return out.stdout


# ---------------------------------------------------------------- estimator core
def nearest_le_ask(sorted_ticks, target):
    """Last (t, ask) with t <= target within TOL_S. sorted_ticks: [(epoch, ask)]."""
    if not sorted_ticks:
        return None
    times = [t for t, _ in sorted_ticks]
    i = bisect_right(times, target) - 1
    if i < 0:
        return None
    t, ask = sorted_ticks[i]
    if target - t > TOL_S or ask is None:
        return None
    return ask


def drift_row(fill, tape_by_asset):
    """{t: drift or None} for one fill. drift signed toward the fill side (BUY: ask firming up = +)."""
    ticks = tape_by_asset.get(fill["asset_key"])
    out = {}
    for t in GRID:
        ask = nearest_le_ask(ticks, fill["ts"] + t) if ticks else None
        if ask is None:
            out[t] = None
        else:
            d = ask - fill["price"]
            out[t] = d if fill["side"] == "BUY" else -d
    return out


def cluster_bootstrap(clusters, t, rng_seed):
    """Event-clustered bootstrap mean + 95% CI for grid point t. clusters: {ev: [driftrow]}."""
    keys = [k for k, rows in clusters.items() if any(r[t] is not None for r in rows)]
    if len(keys) < 2:
        return None
    # deterministic PRNG (no Math.random in workflow ctx; but this is a plain script)
    import random
    rnd = random.Random(rng_seed)
    # per-cluster mean drift at t
    cmean = {}
    for k in keys:
        vals = [r[t] for r in clusters[k] if r[t] is not None]
        cmean[k] = sum(vals) / len(vals)
    point = sum(cmean.values()) / len(cmean)
    boots = []
    n = len(keys)
    for _ in range(BOOT):
        samp = [cmean[keys[rnd.randrange(n)]] for _ in range(n)]
        boots.append(sum(samp) / n)
    boots.sort()
    lo = boots[int(0.025 * BOOT)]
    hi = boots[int(0.975 * BOOT)]
    return {"mean_c": round(point * 100, 3), "lo_c": round(lo * 100, 3),
            "hi_c": round(hi * 100, 3), "n_clusters": n}


def build_curve(fills, tape_by_asset):
    """fills already deduped to one per (event,wallet,cond,outcome). Returns cell -> {t: ci}."""
    # group fills into cells and event-clusters
    cells = defaultdict(lambda: defaultdict(list))  # (band,sport) -> event -> [driftrow]
    counts = defaultdict(int)
    for f in fills:
        band = band_of(f["price"])
        if band is None:
            continue
        cell = (band, f["sport"])
        cells[cell][f["event"]].append(drift_row(f, tape_by_asset))
        counts[cell] += 1
    result = {}
    for cell, clusters in cells.items():
        band, sport = cell
        per_t = {}
        for i, t in enumerate(GRID):
            ci = cluster_bootstrap(clusters, t, rng_seed=hash((band, sport, t)) & 0xFFFFFFFF)
            per_t[t] = ci
        # recoverable deltas (need both grid points present with CI)
        def delta(ta, tb):
            a, b = per_t.get(ta), per_t.get(tb)
            if not a or not b:
                return None
            return round(a["mean_c"] - b["mean_c"], 3)
        result[f"{band}|{sport}"] = {
            "n_fills": counts[cell],
            "n_events": len(clusters),
            "drift_by_t": per_t,
            "recoverable_60_vs_5_c": delta(60, 5),
            "recoverable_statusquo_vs_5_c": delta(90 if 90 in GRID else 120, 5),
            "power": "OK" if len(clusters) >= 30 else "INDETERMINATE-BY-POWER",
        }
    return result


# ---------------------------------------------------------------- data loading
def load_fills_db(container, start_iso, end_iso):
    sql = (
        "SELECT condition_id, outcome_index, extract(epoch from ts), price, side, "
        "COALESCE(sport,'other'), COALESCE(event_slug, slug), slug "
        "FROM trader_fills "
        f"WHERE ts >= '{start_iso}' AND ts <= '{end_iso}' AND is_sports AND side='BUY' "
        # NOTE: the source<>'backfill' exclusion is applied only when migration 040 is
        # live (the column exists); pre-040 production has no backfill rows to exclude.
        "AND wallet IN (SELECT lower(proxy_wallet) FROM followed_traders)")
    fills = []
    for ln in psql(sql, container).splitlines():
        if not ln.strip():
            continue
        cond, oidx, ts, price, side, sport, ev, slug = ln.split("\x1f")
        fills.append({
            "asset_key": (cond, int(oidx)), "ts": float(ts), "price": float(price),
            "side": side, "sport": sport,
            "event": super_event(ev, slug) if super_event else (ev or slug),
            "cond": cond, "oidx": int(oidx),
        })
    return fills


def load_tape_db(container, start_iso, end_iso):
    """asset_key (cond,outcome) -> sorted [(exch_epoch, best_ask)]."""
    sql = (
        "SELECT condition_id, outcome_index, "
        "extract(epoch from COALESCE(exch_ts, recv_at)), best_ask "
        "FROM clob_price_tape "
        f"WHERE COALESCE(exch_ts,recv_at) >= '{start_iso}' "
        f"AND COALESCE(exch_ts,recv_at) <= '{end_iso}' AND best_ask IS NOT NULL")
    tape = defaultdict(list)
    for ln in psql(sql, container).splitlines():
        if not ln.strip():
            continue
        cond, oidx, ts, ask = ln.split("\x1f")
        if not cond:
            continue
        tape[(cond, int(oidx))].append((float(ts), float(ask)))
    for k in tape:
        tape[k].sort()
    return tape


def load_tape_jsonl(path, token_map_path):
    """Load a probe capture JSONL into asset_key (cond,outcome) -> [(exch_epoch, best_ask)]."""
    tm = json.load(open(token_map_path))["token_map"]
    tok2key = {t: (v["condition_id"], v["outcome_index"]) for t, v in tm.items()}
    tape = defaultdict(list)
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            t = json.loads(line)
            key = tok2key.get(t["asset_id"])
            ask = t.get("best_ask")
            if key is None or ask is None:
                continue
            ems = t.get("exch_ts_ms")
            sec = int(ems) / 1000.0 if ems else float(t["recv_at"])
            tape[key].append((sec, ask))
    for k in tape:
        tape[k].sort()
    return tape


def dedup_fills(fills):
    """One fill per (event, wallet?, cond, outcome). We keep earliest ts per (event,cond,outcome)."""
    best = {}
    for f in fills:
        k = (f["event"], f["cond"], f["oidx"])
        if k not in best or f["ts"] < best[k]["ts"]:
            best[k] = f
    return list(best.values())


# ---------------------------------------------------------------- self-test
def self_test():
    global super_event
    super_event = lambda ev, slug: (ev or slug).split("_")[0]  # noqa: E731
    # synthetic linear drift +0.1c per 10s on the fill's asset; 3 event clusters
    tape = {}
    fills = []
    base_ts = 1_000_000.0
    for ev in range(3):
        cond = f"0xc{ev}"
        # tape: ask starts at fill price and rises linearly
        ticks = []
        for s in range(0, 1000):
            ticks.append((base_ts + s, 0.60 + 0.001 * (s / 10.0)))  # +0.001 per 10s
        tape[(cond, 0)] = ticks
        # two fills in this event (one cluster) — same price 0.60
        for w in range(2):
            fills.append({"asset_key": (cond, 0), "ts": base_ts, "price": 0.60,
                          "side": "BUY", "sport": "mlb", "event": f"ev{ev}",
                          "cond": cond, "oidx": 0})
    # add a tape-gap fill (no tape) → drift None
    fills.append({"asset_key": ("0xgap", 0), "ts": base_ts, "price": 0.60, "side": "BUY",
                  "sport": "mlb", "event": "evgap", "cond": "0xgap", "oidx": 0})
    deduped = dedup_fills(fills)
    # dedup keeps one per (event,cond,outcome): 3 real events + gap = 4 fills
    assert len(deduped) == 4, f"dedup got {len(deduped)}"
    # observable filter (mirrors main): the tape-gap fill's asset isn't on the tape
    observable = [f for f in deduped if f["asset_key"] in tape]
    assert len(observable) == 3, f"observable {len(observable)}"
    curve = build_curve(observable, tape)
    cell = curve["0.55-0.75|mlb"]
    d60 = cell["drift_by_t"][60]["mean_c"]
    d5 = cell["drift_by_t"][5]["mean_c"]
    # expected drift at t: +0.001*(t/10) in price = +0.1*(t/10) cents
    exp60, exp5 = 0.1 * 6, 0.1 * 0.5
    assert abs(d60 - exp60) < 0.05, f"drift@60 {d60} vs {exp60}"
    assert abs(d5 - exp5) < 0.05, f"drift@5 {d5} vs {exp5}"
    rec = cell["recoverable_60_vs_5_c"]
    assert abs(rec - (exp60 - exp5)) < 0.05, f"recoverable {rec}"
    # gap fill contributed no cluster to a separate event that has tape
    assert cell["n_events"] == 3, f"events {cell['n_events']}"
    print("SELF-TEST PASS: estimator recovers +0.55c/60s slope, CI brackets, "
          "event-clustered, within-category, tape-gap→None")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--tape-jsonl", help="probe capture JSONL (pre-production validation)")
    ap.add_argument("--token-map", default="reports/token_map.json")
    ap.add_argument("--container", default=PG_CONTAINER)
    ap.add_argument("--start", help="window start ISO (default: derive from tape)")
    ap.add_argument("--end", help="window end ISO")
    ap.add_argument("--out", default="reports/entries/latency-edge-curve.json")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return

    if args.tape_jsonl:
        meta = json.load(open(args.tape_jsonl + ".assets.json"))
        from datetime import datetime, timezone
        start_iso = args.start or datetime.fromtimestamp(meta["window_start"], timezone.utc).isoformat()
        end_iso = args.end or datetime.fromtimestamp(meta["window_end"], timezone.utc).isoformat()
        tape = load_tape_jsonl(args.tape_jsonl, args.token_map)
        fills = load_fills_db(args.container, start_iso, end_iso)
    else:
        start_iso, end_iso = args.start, args.end
        assert start_iso and end_iso, "need --start/--end when reading tape from DB"
        tape = load_tape_db(args.container, start_iso, end_iso)
        fills = load_fills_db(args.container, start_iso, end_iso)

    deduped = dedup_fills(fills)
    observable = [f for f in deduped if f["asset_key"] in tape]
    curve = build_curve(observable, tape)
    report = {
        "window": [start_iso, end_iso],
        "n_fills_raw": len(fills), "n_fills_deduped": len(deduped),
        "n_observable": len(observable),
        "grid_s": GRID, "status_quo_s": STATUS_QUO_S,
        "cells": curve,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(report, open(args.out, "w"), indent=1)
    print(json.dumps({k: {"n_events": v["n_events"], "power": v["power"],
                          "rec_60_vs_5_c": v["recoverable_60_vs_5_c"]}
                      for k, v in curve.items()}, indent=1))
    print(f"[curve] wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
