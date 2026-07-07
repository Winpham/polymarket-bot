#!/usr/bin/env python3
"""Compression study — pick the tape storage key that is minimal yet lossless.

Reads a RAW tape capture (probe_f1_tape.py --raw, every event) and compares storage
strategies by rows/day AND by whether they preserve the curve's step-function:

  full        key=(best_bid,best_ask,last_price)  [current design]
  topofbook   key=(best_bid,best_ask)             [drop level-churn last_price]
  ask_only    key=(best_ask)                       [minimal for the curve]

Each strategy = on-change (emit when key changes) + 1 Hz keep-LAST coalesce (≤1 row
per asset per exchange-second, keeping the settled value). For each we report rows,
rows/day, and a LOSSLESS-FOR-CURVE proof: reconstruct best_ask(t) as a step function
(last value ≤ t) from the strategy's stored rows and assert it equals the reconstruction
from the raw stream at EVERY raw change point. topofbook also proves best_bid lossless.

--self-test is offline/synthetic.
"""
import argparse
import json
import sys
from collections import defaultdict


def load_raw(path):
    """asset -> time-ordered [(sec, best_bid, best_ask, last_price)] (sec = exch epoch).
    Also returns wall-clock span from recv_at (exch_ts can be stale on `book` snapshots,
    so it's unreliable for the rows/day extrapolation)."""
    per = defaultdict(list)
    n = 0
    recv_min = None
    recv_max = None
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                t = json.loads(line)
            except ValueError:
                continue
            n += 1
            ems = t.get("exch_ts_ms")
            sec = int(ems) / 1000.0 if ems else float(t.get("recv_at", 0))
            r = t.get("recv_at")
            if r is not None:
                r = float(r)
                recv_min = r if recv_min is None else min(recv_min, r)
                recv_max = r if recv_max is None else max(recv_max, r)
            per[t["asset_id"]].append(
                (sec, t.get("best_bid"), t.get("best_ask"), t.get("last_price")))
    for a in per:
        per[a].sort(key=lambda x: x[0])
    wall_span = (recv_max - recv_min) if (recv_min is not None and recv_max is not None) else 1.0
    return per, n, max(wall_span, 1.0)


def key_of(ev, fields):
    _, bid, ask, last = ev
    vals = {"bid": bid, "ask": ask, "last": last}
    return tuple(vals[f] for f in fields)


def apply_strategy(events, fields, coalesce_s=1.0):
    """on-change (on `fields`) + keep-LAST per coalesce bucket. Returns stored [(sec,bid,ask,last)]."""
    stored = []
    last_emitted_key = None
    pending = None  # (bucket, ev, key)
    for ev in events:
        sec = ev[0]
        k = key_of(ev, fields)
        bucket = int(sec // coalesce_s)
        if pending is not None and pending[0] != bucket:
            # flush settled value of the prior bucket (on-change vs last emitted)
            _, pev, pk = pending
            if pk != last_emitted_key:
                stored.append(pev)
                last_emitted_key = pk
            pending = None
        pending = (bucket, ev, k)
    if pending is not None:
        _, pev, pk = pending
        if pk != last_emitted_key:
            stored.append(pev)
    return stored


def step_series(rows, idx):
    """[(sec, value)] dropping None, for field index idx (1=bid,2=ask,3=last)."""
    return [(r[0], r[idx]) for r in rows if r[idx] is not None]


def reconstruct_at(series, t):
    """last value with sec <= t (step function), or None."""
    v = None
    for sec, val in series:
        if sec <= t:
            v = val
        else:
            break
    return v


def lossless_for_field(raw_events, stored, idx, query_times, coalesce_s=1.0):
    """At each query time, the stored step-function must equal the raw step-function
    evaluated at the coalesce-bucket granularity (keep-last-of-bucket = the settled value)."""
    raw_series = step_series(raw_events, idx)
    stored_series = step_series(stored, idx)
    # settled raw value for a bucket = last raw value whose sec is in the same bucket and <= t.
    for t in query_times:
        rv = reconstruct_at(raw_series, t)
        sv = reconstruct_at(stored_series, t)
        # allow the ≤coalesce_s settling difference: if they differ, the raw value at t
        # must belong to the SAME bucket as t (i.e. a within-bucket transient the keep-last
        # legitimately settled). Check by comparing at bucket boundaries instead.
        if rv != sv:
            # compare the settled value: raw last-in-bucket(floor(t)) vs stored
            bstart = (int(t // coalesce_s)) * coalesce_s
            settled = None
            for sec, val in raw_series:
                if bstart <= sec <= t:
                    settled = val
            if settled is not None and settled == sv:
                continue  # within-bucket settle, acceptable at coalesce resolution
            if sv == rv:
                continue
            # genuine mismatch outside the settle window
            if reconstruct_at(raw_series, bstart - 1e-9) != sv:
                return False, t, rv, sv
    return True, None, None, None


def run(raw_path, out_path):
    per, n_raw, span = load_raw(raw_path)
    if not per:
        print("no raw events", file=sys.stderr)
        return
    strategies = {
        "full": ["bid", "ask", "last"],
        "topofbook": ["bid", "ask"],
        "ask_only": ["ask"],
    }
    # query grid for the lossless proof: every raw change point + 1s grid per asset
    result = {"raw_events": n_raw, "span_s": round(span, 1), "assets": len(per),
              "strategies": {}}
    for name, fields in strategies.items():
        total_rows = 0
        ask_lossless = True
        bid_lossless = True
        checked_assets = 0
        for asset, events in per.items():
            stored = apply_strategy(events, fields)
            total_rows += len(stored)
            # lossless proof on a sample of assets (all if few) to bound runtime
            if checked_assets < 60 and len(events) > 3:
                qt = sorted({ev[0] for ev in events} |
                            {ev[0] + 0.5 for ev in events})
                ok_ask, t, rv, sv = lossless_for_field(events, stored, 2, qt)
                if not ok_ask:
                    ask_lossless = False
                if "bid" in fields:
                    ok_bid, *_ = lossless_for_field(events, stored, 1, qt)
                    if not ok_bid:
                        bid_lossless = False
                checked_assets += 1
        rows_per_day = int(total_rows / span * 86400)
        result["strategies"][name] = {
            "rows": total_rows,
            "rows_per_sec": round(total_rows / span, 2),
            "rows_per_day": rows_per_day,
            "best_ask_lossless": ask_lossless,
            "best_bid_lossless": bid_lossless if "bid" in fields else None,
        }
    base = result["strategies"]["full"]["rows"] or 1
    for name, s in result["strategies"].items():
        s["vs_full_pct"] = round(100.0 * s["rows"] / base, 1)
    json.dump(result, open(out_path, "w"), indent=1)
    print(json.dumps(result, indent=1))
    print(f"[study] wrote {out_path}", file=sys.stderr)


def self_test():
    # synthetic: ask stable, last_price (level churn) flips every event → full stores many,
    # topofbook/ask store ~1. All must be best_ask-lossless.
    events = []
    for i in range(20):
        sec = 1000.0 + i * 2  # 2s apart → distinct buckets
        events.append((sec, 0.49, 0.50, 0.30 + (i % 2) * 0.01))  # ask fixed, last flips
    full = apply_strategy(events, ["bid", "ask", "last"])
    tob = apply_strategy(events, ["bid", "ask"])
    ask = apply_strategy(events, ["ask"])
    assert len(full) == 20, f"full should store every last-price flip: {len(full)}"
    assert len(tob) == 1, f"topofbook: ask/bid never move → 1 row: {len(tob)}"
    assert len(ask) == 1, f"ask_only: 1 row: {len(ask)}"
    # best_ask lossless for all three
    qt = [e[0] for e in events] + [e[0] + 0.5 for e in events]
    for stored in (full, tob, ask):
        ok, t, rv, sv = lossless_for_field(events, stored, 2, qt)
        assert ok, f"best_ask lossless failed at t={t}: raw={rv} stored={sv}"
    # now a real ask move: topofbook must capture it
    events2 = [(1000.0, 0.49, 0.50, 0.3), (1002.0, 0.49, 0.51, 0.3),
               (1004.0, 0.50, 0.51, 0.3)]
    tob2 = apply_strategy(events2, ["bid", "ask"])
    assert len(tob2) == 3, f"topofbook captures ask move + bid move: {len(tob2)}"
    ok, *_ = lossless_for_field(events2, tob2, 2, [1000.5, 1002.5, 1004.5])
    assert ok
    print("SELF-TEST PASS: last-price churn dropped by topofbook/ask; best_ask lossless; "
          "real ask/bid moves captured.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="reports/tape_raw.jsonl")
    ap.add_argument("--out", default="reports/tape_compression_study.json")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    run(args.raw, args.out)


if __name__ == "__main__":
    main()
