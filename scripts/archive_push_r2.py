#!/usr/bin/env python3
"""Compact the local Parquet archive and push it to R2 byte-exactly.

WHY NOT JUST `COPY ... TO 'r2://...'`
-------------------------------------
The first R2 push did exactly that — re-materialised the archive through DuckDB's
threaded PARTITION_BY writer straight to R2. It produced CORRUPT OBJECTS: reading back
threw `No magic bytes found at end of file` on
`trader_fills/dt=2025-10-21/part5.parquet`, i.e. a truncated parquet with no footer.
trader_fills took 1,415s while the other two took 14s, because it had 5,258 tiny local
files fanning into a threaded remote write that raced on `part{N}` names.

So we do the two jobs separately, and verify each:

  1. COMPACT locally — one file per day partition, written by DuckDB to LOCAL disk where a
     failure is cheap and visible. Verified against the source row/id counts before the old
     files are dropped.
  2. UPLOAD byte-exactly — a plain S3 PUT of each finished local file, with the MD5 checked
     against the returned ETag. No re-encoding in flight, so a parquet footer cannot be lost
     in transit. What lands in R2 is bit-identical to what we verified on disk.

Then read the whole thing back FROM R2 and match the counts. An archive you have not read
back from its destination is not a backup, it is a hope.

Usage:  python3 scripts/archive_push_r2.py [--compact-only] [--skip-compact]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import os
import shutil
import sys

import boto3
import duckdb
from botocore.config import Config

ARCH = os.path.expanduser(os.environ.get("ARCHIVE_DIR", "~/polymarket-archive"))
TABLES = ["trader_fills", "clob_price_tape", "consensus_vote_window"]

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_KEY = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "polymarket-archive")


def compact(con, t: str) -> None:
    src = f"{ARCH}/{t}"
    glob_ = f"{src}/dt=*/*.parquet"
    files = glob.glob(glob_)
    if not files:
        print(f"  {t}: no local files, skipping")
        return
    n0, u0 = con.execute(
        f"SELECT count(*), count(DISTINCT id) FROM read_parquet('{glob_}', hive_partitioning=true)"
    ).fetchone()
    if len(files) <= 60:
        print(f"  {t}: {len(files)} files already compact ({n0:,} rows) — leaving alone")
        return

    tmp = f"{ARCH}/.{t}.compact"
    shutil.rmtree(tmp, ignore_errors=True)
    # threads=1: one file per partition, and no concurrent writers racing on a filename.
    con.execute("SET threads=1;")
    con.execute(f"""
        COPY (SELECT * FROM read_parquet('{glob_}', hive_partitioning=true))
        TO '{tmp}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (dt),
                    OVERWRITE, FILENAME_PATTERN 'part');
    """)
    con.execute("SET threads TO DEFAULT;")

    n1, u1 = con.execute(
        f"SELECT count(*), count(DISTINCT id) FROM read_parquet('{tmp}/dt=*/*.parquet', hive_partitioning=true)"
    ).fetchone()
    if (n1, u1) != (n0, u0):
        sys.exit(f"  ✗ COMPACT FAILED for {t}: {n0:,}/{u0:,} -> {n1:,}/{u1:,}. Original left intact at {src}")
    shutil.rmtree(src)
    os.rename(tmp, src)
    print(f"  {t}: {len(files):,} -> {len(glob.glob(glob_)):,} files, {n1:,} rows verified")


def s3():
    if not all([R2_ACCOUNT_ID, R2_KEY, R2_SECRET]):
        sys.exit("R2_* env vars unset — source .env.consensus first")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_KEY,
        aws_secret_access_key=R2_SECRET,
        config=Config(retries={"max_attempts": 5, "mode": "standard"}, region_name="auto"),
    )


def upload(cli, t: str) -> tuple[int, int]:
    files = sorted(glob.glob(f"{ARCH}/{t}/dt=*/*.parquet"))
    sent = bad = 0
    for f in files:
        key = os.path.relpath(f, ARCH)
        body = open(f, "rb").read()
        md5 = hashlib.md5(body).hexdigest()
        r = cli.put_object(Bucket=R2_BUCKET, Key=key, Body=body)
        # Single-part PUT => ETag IS the MD5. If it disagrees, the bytes in R2 are not our
        # bytes — that is exactly the failure the DuckDB path hid.
        if r.get("ETag", "").strip('"') != md5:
            print(f"    ✗ CHECKSUM MISMATCH {key}")
            bad += 1
        else:
            sent += 1
    print(f"  {t}: uploaded {sent:,} files"
          + (f"  ✗ {bad} CHECKSUM FAILURES" if bad else "  (all checksums match)"))
    return sent, bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compact-only", action="store_true")
    ap.add_argument("--skip-compact", action="store_true")
    a = ap.parse_args()

    con = duckdb.connect()
    if not a.skip_compact:
        print("COMPACT (local):")
        for t in TABLES:
            compact(con, t)
    if a.compact_only:
        return

    print("\nUPLOAD (byte-exact PUT + MD5/ETag check):")
    cli = s3()
    # Clear the corrupt first-attempt objects so nothing stale survives under the prefix.
    for t in TABLES:
        tok = None
        while True:
            kw = {"Bucket": R2_BUCKET, "Prefix": f"{t}/"}
            if tok:
                kw["ContinuationToken"] = tok
            r = cli.list_objects_v2(**kw)
            objs = [{"Key": o["Key"]} for o in r.get("Contents", [])]
            if objs:
                cli.delete_objects(Bucket=R2_BUCKET, Delete={"Objects": objs})
            if not r.get("IsTruncated"):
                break
            tok = r.get("NextContinuationToken")
    bad_total = 0
    for t in TABLES:
        _, bad = upload(cli, t)
        bad_total += bad
    if bad_total:
        sys.exit(f"\n✗ {bad_total} checksum failures — R2 does NOT hold a faithful copy.")

    print("\nVERIFY (read back FROM R2, cloud only):")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET unsafe_disable_etag_checks = true;")
    con.execute(f"""CREATE OR REPLACE SECRET r2s (TYPE r2, KEY_ID '{R2_KEY}',
        SECRET '{R2_SECRET}', ACCOUNT_ID '{R2_ACCOUNT_ID}');""")
    ok = True
    for t in TABLES:
        loc = con.execute(f"SELECT count(*), count(DISTINCT id) FROM read_parquet('{ARCH}/{t}/dt=*/*.parquet', hive_partitioning=true)").fetchone()
        rem = con.execute(f"SELECT count(*), count(DISTINCT id) FROM read_parquet('r2://{R2_BUCKET}/{t}/dt=*/*.parquet', hive_partitioning=true)").fetchone()
        good = loc == rem and rem[0] == rem[1]
        ok &= good
        print(f"  {t:24} local {loc[0]:>10,} | R2 {rem[0]:>10,} | dupes {rem[0]-rem[1]:>3} | {'✓' if good else '✗ MISMATCH'}")
    print("\n✓ R2 holds a verified, duplicate-free copy of the archive." if ok
          else "\n✗ R2 copy does NOT match local. Do not rely on it.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
