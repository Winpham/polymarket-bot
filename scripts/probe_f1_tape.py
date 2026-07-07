#!/usr/bin/env python3
"""P0-A — probe_f1_tape: the MEASUREMENT-GATE probe.

Connects the CLOB market websocket (same protocol as trading-bot/src/scanner/ws.rs),
subscribes to the tracked-only token universe (from build_token_map.py), and:

  --escalate : find the REAL per-connection subscription max (validates/overwrites
               the untested MAX_SUBSCRIPTIONS=200 constant, ws.rs:14).
  --capture  : run a >=30-min sharded capture writing a raw tick tape (JSONL) and
               measuring disconnects, reconnect recovery, events/s, best_ask/exch_ts
               presence, and per-asset tick times (input to the coverage oracle).

Endpoint/subscribe/PING are byte-identical to ws.rs. Event types under
custom_feature_enabled=true are `book` (snapshot) + `price_change` (deltas) — see
reports/PROTOCOL_FINDINGS.md. Both carry a top-level ms-epoch `timestamp` (exch_ts)
and price_change carries best_bid+best_ask directly.

Writes tape to a local JSONL (NOT the production DB — clob_price_tape doesn't exist
until migration 040). Read-only w.r.t. everything in the workspace.
"""
import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict

import websockets

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PING_INTERVAL = 10.0  # ws.rs:10


def load_assets(token_map_path, quotable_only=True):
    d = json.load(open(token_map_path))
    tm = d["token_map"]
    assets = [t for t, v in tm.items() if (v.get("quotable") or not quotable_only)]
    return assets, tm


def _tick_from_book(it, recv_at):
    bids = it.get("bids") or []
    asks = it.get("asks") or []
    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    bid_prices = [p for p in (_f(b.get("price")) for b in bids) if p is not None]
    ask_prices = [p for p in (_f(a.get("price")) for a in asks) if p is not None]
    return {
        "asset_id": it.get("asset_id"),
        "event_type": "book",
        "best_bid": max(bid_prices) if bid_prices else None,
        "best_ask": min(ask_prices) if ask_prices else None,
        "last_price": _f(it.get("last_trade_price")),
        "last_size": None,
        "side": None,
        "exch_ts_ms": it.get("timestamp"),
        "recv_at": recv_at,
    }


def _ticks_from_price_change(it, recv_at):
    top_ts = it.get("timestamp")
    out = []
    for ch in it.get("price_changes", []):
        def _f(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None
        out.append({
            "asset_id": ch.get("asset_id"),
            "event_type": "price_change",
            "best_bid": _f(ch.get("best_bid")),
            "best_ask": _f(ch.get("best_ask")),
            "last_price": _f(ch.get("price")),
            "last_size": _f(ch.get("size")),
            "side": ch.get("side"),
            "exch_ts_ms": ch.get("timestamp") or top_ts,
            "recv_at": recv_at,
        })
    return out


def parse_message(msg, recv_at):
    """Return a list of tick dicts from one WS frame."""
    if msg == "PONG" or not msg:
        return []
    try:
        data = json.loads(msg)
    except (ValueError, TypeError):
        return []
    items = data if isinstance(data, list) else [data]
    ticks = []
    for it in items:
        et = it.get("event_type")
        if et == "book":
            ticks.append(_tick_from_book(it, recv_at))
        elif et == "price_change":
            ticks.extend(_ticks_from_price_change(it, recv_at))
        # ignore last_trade_price/best_bid_ask/market_resolved for the tape
    return ticks


class Stats:
    def __init__(self):
        self.events = 0
        self.by_type = defaultdict(int)
        self.best_ask_present = 0
        self.exch_ts_present = 0
        self.distinct_assets = set()
        self.disconnects = 0
        self.recovery_s = []
        self.asset_last_recv = {}   # asset_id -> last recv_at (epoch)
        self.asset_first_recv = {}
        self.t_start = time.time()

    def record(self, tick):
        self.events += 1
        self.by_type[tick["event_type"]] += 1
        if tick.get("best_ask") is not None:
            self.best_ask_present += 1
        if tick.get("exch_ts_ms"):
            self.exch_ts_present += 1
        a = tick.get("asset_id")
        if a:
            self.distinct_assets.add(a)
            r = tick["recv_at"]
            self.asset_last_recv[a] = r
            self.asset_first_recv.setdefault(a, r)

    def summary(self):
        elapsed = max(1e-9, time.time() - self.t_start)
        recovery_sorted = sorted(self.recovery_s)
        p50 = (recovery_sorted[len(recovery_sorted) // 2]
               if recovery_sorted else None)
        return {
            "events": self.events,
            "by_type": dict(self.by_type),
            "events_per_sec": round(self.events / elapsed, 2),
            "distinct_assets_seen": len(self.distinct_assets),
            "best_ask_present_pct": round(100.0 * self.best_ask_present / max(1, self.events), 2),
            "exch_ts_present_pct": round(100.0 * self.exch_ts_present / max(1, self.events), 2),
            "disconnects": self.disconnects,
            "reconnect_recovery_s_p50": round(p50, 2) if p50 is not None else None,
            "elapsed_s": round(elapsed, 1),
        }


async def conn_worker(shard, stats, tick_writer, deadline, label, resub_event=None):
    """One sharded connection: connect/subscribe/PING/read, reconnect on drop."""
    sub = json.dumps({"assets_ids": shard, "type": "market",
                      "custom_feature_enabled": True})
    while time.time() < deadline:
        drop_t = None
        try:
            async with websockets.connect(WS_URL, max_size=None, ping_interval=None,
                                          open_timeout=20, close_timeout=5) as ws:
                await ws.send(sub)
                last_ping = time.time()
                first_after_reconnect = True
                while time.time() < deadline:
                    now = time.time()
                    if now - last_ping >= PING_INTERVAL:
                        await ws.send("PING")
                        last_ping = now
                    try:
                        msg = await asyncio.wait_for(ws.recv(),
                                                     timeout=PING_INTERVAL)
                    except asyncio.TimeoutError:
                        continue
                    recv_at = time.time()
                    if first_after_reconnect and drop_t is not None:
                        stats.recovery_s.append(recv_at - drop_t)
                        first_after_reconnect = False
                        drop_t = None
                    for tick in parse_message(msg, recv_at):
                        if tick.get("asset_id"):
                            stats.record(tick)
                            if tick_writer:
                                tick_writer(tick)
        except Exception as e:  # noqa: BLE001 — reconnect on any drop
            stats.disconnects += 1
            drop_t = time.time()
            if time.time() >= deadline:
                break
            await asyncio.sleep(1.0)  # backoff, then re-subscribe (gap-free by design)
    return label


async def escalate(assets):
    """Find the real per-connection subscription ceiling."""
    results = []
    for n in [200, 500, 1000, 2000, min(4000, len(assets))]:
        if n > len(assets):
            n = len(assets)
        shard = assets[:n]
        stats = Stats()
        deadline = time.time() + 45
        try:
            await asyncio.wait_for(conn_worker(shard, stats, None, deadline, f"n{n}"),
                                   timeout=60)
        except asyncio.TimeoutError:
            pass
        s = stats.summary()
        results.append({
            "n_subscribed": n, "distinct_assets_seen": s["distinct_assets_seen"],
            "coverage_pct": round(100.0 * s["distinct_assets_seen"] / max(1, n), 1),
            "disconnects": s["disconnects"], "events_per_sec": s["events_per_sec"],
        })
        print(f"[escalate] n={n}: saw {s['distinct_assets_seen']} distinct "
              f"({results[-1]['coverage_pct']}%), {s['disconnects']} disconnects, "
              f"{s['events_per_sec']} ev/s", file=sys.stderr)
        if n == len(assets):
            break
    return results


async def capture(assets, shard_size, minutes, tape_path, dedup_onchange=True):
    n_conns = (len(assets) + shard_size - 1) // shard_size
    shards = [assets[i:i + shard_size] for i in range(0, len(assets), shard_size)]
    print(f"[capture] {len(assets)} assets, shard={shard_size} -> {n_conns} connections, "
          f"{minutes} min, dedup_onchange={dedup_onchange}", file=sys.stderr)
    stats = Stats()
    deadline = time.time() + minutes * 60
    tape_f = open(tape_path, "w")
    write_count = [0]       # rows actually persisted (post-dedup)
    raw_count = [0]         # raw events seen
    last_top = {}           # asset_id -> (best_bid, best_ask, last_price)

    def tick_writer(tick):
        # On-change dedup: persist only when top-of-book (bid/ask) or last trade
        # price moves for this asset. LOSSLESS for the curve (best_ask is a step
        # function) — drops redundant same-price reprints, the bulk of quote churn.
        raw_count[0] += 1
        if dedup_onchange:
            a = tick["asset_id"]
            key = (tick.get("best_bid"), tick.get("best_ask"), tick.get("last_price"))
            if last_top.get(a) == key:
                return
            last_top[a] = key
        tape_f.write(json.dumps(tick) + "\n")
        write_count[0] += 1
        if write_count[0] % 5000 == 0:
            tape_f.flush()

    tasks = [asyncio.create_task(conn_worker(sh, stats, tick_writer, deadline, f"s{i}"))
             for i, sh in enumerate(shards)]
    # periodic progress
    async def progress():
        while time.time() < deadline:
            await asyncio.sleep(60)
            s = stats.summary()
            print(f"[capture] +{int(s['elapsed_s'])}s events={s['events']} "
                  f"ev/s={s['events_per_sec']} assets={s['distinct_assets_seen']} "
                  f"disc={s['disconnects']} best_ask%={s['best_ask_present_pct']}",
                  file=sys.stderr)
    prog = asyncio.create_task(progress())
    await asyncio.gather(*tasks, return_exceptions=True)
    prog.cancel()
    tape_f.flush()
    tape_f.close()
    stats.raw_events = raw_count[0]
    stats.stored_rows = write_count[0]
    return stats, n_conns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-map", default="reports/token_map.json")
    ap.add_argument("--mode", choices=["escalate", "capture"], required=True)
    ap.add_argument("--shard-size", type=int, default=500)
    ap.add_argument("--minutes", type=int, default=35)
    ap.add_argument("--tape-out", default="reports/tape_capture.jsonl")
    ap.add_argument("--probe-out", default="reports/live_ingestion_probe.json")
    ap.add_argument("--all-tokens", action="store_true",
                    help="subscribe to all tokens, not just quotable")
    ap.add_argument("--raw", action="store_true",
                    help="capture EVERY event (no on-change dedup) for the compression study")
    args = ap.parse_args()

    assets, _ = load_assets(args.token_map, quotable_only=not args.all_tokens)
    print(f"[f1] loaded {len(assets)} assets from {args.token_map}", file=sys.stderr)

    block = {"endpoint": WS_URL, "assets_target_tracked": len(assets)}
    if args.mode == "escalate":
        results = asyncio.run(escalate(assets))
        # real max = largest n with >=90% coverage and 0 disconnects
        best = 200
        for r in results:
            if r["coverage_pct"] >= 90 and r["disconnects"] == 0:
                best = r["n_subscribed"]
        block["escalation"] = results
        block["max_subs_per_conn_observed"] = best
        print(f"[f1] max_subs_per_conn_observed = {best}", file=sys.stderr)
    else:
        # --raw captures every event (no on-change dedup) so keying/compaction
        # strategies can be compared offline for the compression study.
        stats, n_conns = asyncio.run(
            capture(assets, args.shard_size, args.minutes, args.tape_out,
                    dedup_onchange=not args.raw))
        s = stats.summary()
        block.update(s)
        block["shard_size"] = args.shard_size
        block["connections_needed"] = n_conns
        block["tape_path"] = args.tape_out
        # storage sizing: raw event rate vs on-change-deduped stored-row rate.
        elapsed = max(1e-9, s["elapsed_s"])
        raw = getattr(stats, "raw_events", s["events"])
        stored = getattr(stats, "stored_rows", s["events"])
        block["raw_events"] = raw
        block["stored_rows_after_onchange_dedup"] = stored
        block["dedup_keep_pct"] = round(100.0 * stored / max(1, raw), 2)
        block["stored_rows_per_sec"] = round(stored / elapsed, 2)
        block["est_stored_rows_per_day"] = int(stored / elapsed * 86400)
        block["est_stored_rows_72h"] = int(stored / elapsed * 86400 * 3)
        # dump per-asset last-tick times for the coverage oracle
        with open(args.tape_out + ".assets.json", "w") as f:
            json.dump({"asset_first_recv": stats.asset_first_recv,
                       "asset_last_recv": stats.asset_last_recv,
                       "window_start": stats.t_start,
                       "window_end": time.time()}, f)
        print(f"[f1] capture done: {json.dumps(s)}", file=sys.stderr)

    # merge into the probe report
    try:
        report = json.load(open(args.probe_out))
    except (FileNotFoundError, ValueError):
        report = {}
    report.setdefault("f1_clob_ws", {}).update(block)
    json.dump(report, open(args.probe_out, "w"), indent=1)
    print(f"[f1] merged into {args.probe_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
