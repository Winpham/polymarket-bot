#!/usr/bin/env python3
"""Salvage the data that exists ONLY inside old pg_dumps, into the Parquet archive.

WHY
---
Two tables self-prune, so the live DB is NOT a superset of the old dumps:

  clob_price_tape        TAPE_RETENTION_HOURS=72  -> DB holds only the last 3 days
  consensus_vote_window  prune_window_votes(48h)  -> DB holds only the last 2 days

The tape went live 2026-07-07 and the vote window has been running for weeks, so the
history outside those windows exists NOWHERE except the nightly dumps. Deleting the dumps
without this step would permanently destroy:

  - ~7 days of top-of-book price curve (the raw material for entry-ask / basis research)
  - ~2 weeks of raw consensus VOTE ATOMS (what the wide-pool / supply-frontier re-runs
    replay; consensus_signals keeps a JSONB summary per FIRED signal, but the atoms cover
    markets that never fired — i.e. the counterfactual)

trader_fills needs no salvage: it is append-only and today's archiver already exported
everything older than the 45d hot window before pruning.

WHAT IT DOES
------------
Streams each dump (never unpacks 5.2 GB to disk), pulls those two COPY blocks, dedupes by
primary key across ALL dumps, and writes date-partitioned Parquet into the same archive
layout the nightly archiver uses. Then the dumps are genuinely redundant.

Usage:  python3 scripts/salvage_dumps_to_parquet.py [--out ~/polymarket-archive]
"""
from __future__ import annotations

import argparse
import glob
import gzip
import os
import sys

import pyarrow as pa
import pyarrow.parquet as pq

TARGETS = {
    "clob_price_tape": "recv_at",
    "consensus_vote_window": "ts",
}


def stream_copy_blocks(path: str):
    """Yield (table, cols, row_list) for each COPY block we care about."""
    cur = None
    cols: list[str] = []
    rows: list[str] = []
    with gzip.open(path, "rt", errors="replace") as f:
        for line in f:
            if cur is None:
                if line.startswith("COPY public."):
                    tbl = line.split()[1].split(".", 1)[1]
                    if tbl in TARGETS:
                        cols = [c.strip().strip('"')
                                for c in line[line.index("(") + 1:line.index(")")].split(",")]
                        cur, rows = tbl, []
                continue
            if line.startswith("\\."):
                yield cur, cols, rows
                cur, rows = None, []
                continue
            rows.append(line.rstrip("\n"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/polymarket-archive"))
    ap.add_argument("--dumps", default=os.path.expanduser("~/polymarket-bot/backups"))
    args = ap.parse_args()

    dumps = sorted(glob.glob(f"{args.dumps}/*.sql.gz"))
    if not dumps:
        sys.exit(f"no dumps found in {args.dumps}")
    print(f"salvaging from {len(dumps)} dumps\n")

    # id -> row, deduped across every dump. Keyed on the PK so overlapping retention
    # windows across consecutive dumps collapse to one copy.
    seen: dict[str, dict[str, list]] = {t: {} for t in TARGETS}
    schema: dict[str, list[str]] = {}

    for d in dumps:
        got = []
        for tbl, cols, rows in stream_copy_blocks(d):
            schema.setdefault(tbl, cols)
            if schema[tbl] != cols:
                sys.exit(f"SCHEMA DRIFT in {tbl} at {os.path.basename(d)} — refusing to merge")
            idx = cols.index("id")
            new = 0
            for r in rows:
                parts = r.split("\t")
                if len(parts) != len(cols):
                    continue
                rid = parts[idx]
                if rid not in seen[tbl]:
                    seen[tbl][rid] = parts
                    new += 1
            got.append(f"{tbl}: {len(rows):,} rows ({new:,} new)")
        print(f"  {os.path.basename(d):<40} {' | '.join(got) if got else '(no target tables)'}")

    print()
    for tbl, ts_col in TARGETS.items():
        recs = seen[tbl]
        if not recs:
            print(f"{tbl}: nothing salvaged")
            continue
        cols = schema[tbl]
        ti = cols.index(ts_col)
        ncol = len(cols)
        colvals: list[list] = [[] for _ in range(ncol)]
        dts: list[str] = []
        for parts in recs.values():
            for i, p in enumerate(parts):
                colvals[i].append(None if p == "\\N" else p)
            dts.append((parts[ti] or "")[:10])  # YYYY-MM-DD partition key

        arrays = [pa.array(c, type=pa.string()) for c in colvals] + [pa.array(dts, pa.string())]
        table = pa.Table.from_arrays(arrays, names=cols + ["dt"])
        out = f"{args.out}/{tbl}"
        pq.write_to_dataset(
            table, root_path=out, partition_cols=["dt"],
            compression="zstd", compression_level=9,
            existing_data_behavior="delete_matching",
        )
        size = sum(os.path.getsize(p) for p in glob.glob(f"{out}/**/*.parquet", recursive=True))
        days = sorted({d for d in dts if d})
        print(f"{tbl}: {len(recs):,} unique rows  ->  {out}  "
              f"({size/1e6:.1f} MB, {len(days)} days: {days[0]} .. {days[-1]})")


if __name__ == "__main__":
    main()
