#!/usr/bin/env python3
"""PHASE A — pull the ENTIRE Polymarket US market universe into a local Parquet cache.

Read-only, public gateway (gateway.polymarket.us), no auth, no order placed. Reading a
public API is not trading — this is the INFORMATION side of the design.

TWO GATEWAY GOTCHAS, both learned the hard way, both silent:

  1. Every query param except `limit`/`offset` is IGNORED. `?category=climate`, `?sport=`,
     `?q=` and even `?orderBy=` return the SAME unfiltered first page. A naive filtered
     fetch looks like it worked and quietly gives you the wrong rows. Filter CLIENT-SIDE.
     (Same class of bug as the data-api ignoring `startTs`, which cost us 96.8% of a
     history once.)
  2. There are ~223k markets, not the ~20k a truncated scan suggests. An early scan that
     stopped at 22k concluded "climate is dead, newest market is 2026-05-06" — both false
     artifacts of truncation. Page to genuine exhaustion (empty page), never to a bound.

Usage:  python3 scripts/us_fetch_markets.py [--out ~/polymarket-archive/us_markets.parquet]
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request

import pyarrow as pa
import pyarrow.parquet as pq

GW = "https://gateway.polymarket.us"
PAGE = 500

KEEP = [
    "id", "slug", "question", "category", "marketType", "sportsMarketType",
    "sportsMarketTypeV2", "active", "closed", "archived", "startDate", "endDate",
    "gameStartTime", "createdAt", "orderPriceMinTickSize", "minimumTradeQty",
    "feeCoefficient", "outcomePrices", "outcomes",
]


def get(url: str, tries: int = 4):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "research/1.0"})
            with urllib.request.urlopen(r, timeout=40) as resp:
                return json.load(resp)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(0.6 * (i + 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/polymarket-archive/us_markets.parquet"))
    args = ap.parse_args()

    rows, off, t0 = [], 0, time.time()
    while True:
        ms = get(f"{GW}/v1/markets?limit={PAGE}&offset={off}").get("markets", [])
        if not ms:  # genuine exhaustion — never stop on a bound
            break
        for m in ms:
            r = {k: m.get(k) for k in KEEP}
            for j in ("outcomePrices", "outcomes"):
                if r[j] is not None and not isinstance(r[j], str):
                    r[j] = json.dumps(r[j])
            # marketSides carries the tradable legs + their orientation
            sides = m.get("marketSides") or []
            r["n_sides"] = len(sides)
            r["side_ids"] = json.dumps([s.get("identifier") for s in sides])
            r["side_long"] = json.dumps([s.get("long") for s in sides])
            r["side_desc"] = json.dumps([s.get("description") for s in sides])
            rows.append(r)
        off += len(ms)
        if off % 10000 == 0:
            print(f"  {off:,} markets ({time.time()-t0:.0f}s)", flush=True)

    print(f"\nfetched {len(rows):,} markets in {time.time()-t0:.0f}s")
    cols = list(rows[0].keys())
    tbl = pa.Table.from_arrays(
        [pa.array([str(r[c]) if r[c] is not None else None for r in rows], type=pa.string())
         for c in cols],
        names=cols,
    )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    pq.write_table(tbl, args.out, compression="zstd", compression_level=9)
    print(f"wrote {args.out} ({os.path.getsize(args.out)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
