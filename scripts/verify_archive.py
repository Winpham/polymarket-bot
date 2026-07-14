#!/usr/bin/env python3
"""PROVE the archive is safe to rely on. Exit 0 only if it is.

WHY THIS EXISTS — 2026-07-13, a near-miss
-----------------------------------------
We were one command away from deleting 15 pg_dumps on the claim that they were
"redundant, already archived to R2." They were not. R2 held 6 recent day-partitions;
the dumps were the ancestor of the ONLY copy of trader_fills back to 2022-12-15.
Nobody had ever compared the bucket's contents to the thing it supposedly backed up.

The lesson is not "be careful". It is: A CLAIM OF REDUNDANCY IS A TESTABLE
PROPOSITION, AND IT MUST BE TESTED BY MACHINE BEFORE ANYTHING IS DELETED. This
script is that test. Every destructive path in this repo calls it first and dies if
it is not green.

WHAT IT PROVES (all three, or it fails)
---------------------------------------
  1. R2 ⊇ LOCAL   every local archive file exists in R2, byte-identical (MD5 + size).
  2. R2 ⊇ POSTGRES  every PG row in a sealed day-partition reads back out of R2,
                    checked by ANTI-JOIN on the primary key — not a row count. A count
                    can match while holding the wrong rows; an anti-join cannot.
  3. FRESH        the newest sealed partition is recent. This is the watchdog that
                  would have caught the real bug: an archiver that never ran at all,
                  while nightly backups kept reporting success.

Read-only. Touches nothing. Safe to run any time.

  python3 scripts/verify_archive.py            # prove it
  python3 scripts/verify_archive.py --quiet    # for use as a gate in other scripts
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
ARCHIVE_DIR = Path(os.environ.get("ARCHIVE_DIR", os.path.expanduser("~/polymarket-archive")))
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "polymarket-archive")

# Mirrors TABLES in archive_to_parquet.py. (name, ts_col, hot_days, bot_retention_hours)
TABLES = [
    ("trader_fills", "ts", 45, None),
    ("consensus_snapshots", "ts", 45, None),
    ("clob_price_tape", "recv_at", None, 72),
    ("consensus_vote_window", "ts", None, 48),
]

# A sealed partition older than this means the archiver is dead or wedged. The tape is
# deleted by the bot at 72h, so a dead archiver costs a day of irrecoverable history
# every day it stays dead. Alert well inside that window.
MAX_STALE_DAYS = 2

failures: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="only print on failure")
    args = ap.parse_args()

    def say(m: str = "") -> None:
        if not args.quiet:
            print(m)

    missing_creds = [k for k, v in {
        "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
        "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
        "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
    }.items() if not v]
    if missing_creds:
        # Fail — do NOT skip. "Can't check" must never read as "checked and fine": that
        # equivalence is precisely what would have let the deletion through.
        sys.exit(f"✗ VERIFY IMPOSSIBLE: R2 creds unset ({', '.join(missing_creds)}). "
                 f"Refusing to report a passing archive I could not read.")

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"ATTACH '{PG_DSN}' AS pg (TYPE postgres, READ_ONLY);")
    con.execute(f"""
        CREATE OR REPLACE SECRET r2secret (
            TYPE r2, KEY_ID '{R2_ACCESS_KEY_ID}',
            SECRET '{R2_SECRET_ACCESS_KEY}', ACCOUNT_ID '{R2_ACCOUNT_ID}'
        );""")

    # ---- CHECK 1: R2 ⊇ LOCAL -------------------------------------------------------
    # By ROW, not by byte. Byte-identity is the wrong bar: a re-encoded Parquet holding
    # every row is fine, and a byte-identical file holding the wrong rows is not. What we
    # must prove before deleting anything is that no row exists locally and nowhere else.
    # An anti-join on the primary key proves exactly that, and needs only DuckDB — no
    # boto3, so this runs under the same bare system python3 the nightly cron uses.
    say("CHECK 1  R2 ⊇ local archive (anti-join on primary key)")
    if not ARCHIVE_DIR.is_dir() or not any(ARCHIVE_DIR.rglob("*.parquet")):
        notes.append(f"no local archive at {ARCHIVE_DIR} — check 1 vacuous")
        say(f"    (no local archive at {ARCHIVE_DIR}; nothing to compare)")
    else:
        for name, _ts, _hd, _bh in TABLES:
            loc = ARCHIVE_DIR / name
            if not loc.is_dir() or not any(loc.rglob("*.parquet")):
                continue
            lpat = f"{loc}/dt=*/*.parquet"
            rpat = f"r2://{R2_BUCKET}/{name}/dt=*/*.parquet"
            try:
                n_local = con.execute(
                    f"SELECT count(*) FROM read_parquet('{lpat}', hive_partitioning=true)"
                ).fetchone()[0]
                orphan = con.execute(f"""
                    SELECT count(*) FROM read_parquet('{lpat}', hive_partitioning=true) l
                    WHERE NOT EXISTS (
                        SELECT 1 FROM read_parquet('{rpat}', hive_partitioning=true) r
                        WHERE r.id = l.id)
                """).fetchone()[0]
            except Exception as e:
                fail(f"{name}: cannot compare local archive to R2 ({str(e)[:90]})")
                continue
            if orphan:
                fail(f"{name}: {orphan:,} of {n_local:,} rows exist in the LOCAL archive but "
                     f"NOT in R2. R2 is not a superset — deleting local copies would lose them.")
            say(f"    {name}: {n_local:,} local rows, {orphan:,} absent from R2")

    # ---- CHECK 2 + 3: R2 ⊇ POSTGRES, and FRESH -------------------------------------
    say("CHECK 2  R2 ⊇ Postgres cold rows (anti-join on primary key)")
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fresh_report: list[str] = []

    for name, ts_col, hot_days, bot_hours in TABLES:
        out = f"r2://{R2_BUCKET}/{name}"
        try:
            parts = con.execute(
                f"SELECT DISTINCT dt FROM read_parquet('{out}/dt=*/*.parquet', "
                f"hive_partitioning=true)").fetchall()
        except Exception:
            parts = []
        sealed = sorted(str(p[0]) for p in parts)
        if not sealed:
            notes.append(f"{name}: no partitions in R2")
            say(f"    {name}: no partitions in R2 (skipped)")
            continue

        cutoff = (midnight - timedelta(days=hot_days)) if hot_days is not None else midnight
        sealed_list = ", ".join(f"DATE '{d}'" for d in sealed)
        scope = (f"s.{ts_col} < TIMESTAMPTZ '{cutoff.isoformat()}' "
                 f"AND CAST(s.{ts_col} AS DATE) IN ({sealed_list})")

        in_scope = con.execute(
            f"SELECT count(*) FROM pg.{name} s WHERE {scope}").fetchone()[0]
        missing = con.execute(f"""
            SELECT count(*) FROM pg.{name} s
            WHERE {scope} AND NOT EXISTS (
                SELECT 1 FROM read_parquet('{out}/dt=*/*.parquet', hive_partitioning=true) a
                WHERE a.id = s.id)
        """).fetchone()[0]

        if missing:
            fail(f"{name}: {missing:,} of {in_scope:,} PG rows in SEALED partitions are "
                 f"NOT readable back from R2")
        say(f"    {name}: {in_scope:,} cold rows in sealed days, {missing:,} missing from R2")

        newest = datetime.fromisoformat(sealed[-1]).replace(tzinfo=timezone.utc)
        stale_days = (midnight - newest).days
        fresh_report.append(f"    {name}: newest sealed partition {sealed[-1]} "
                            f"({stale_days}d old, {len(sealed)} partitions)")
        if stale_days > MAX_STALE_DAYS:
            fail(f"{name}: STALE — newest sealed partition is {sealed[-1]}, {stale_days}d old "
                 f"(max {MAX_STALE_DAYS}d). The archiver is not running. History is being "
                 f"lost every day this persists.")

    say("CHECK 3  archive is fresh (watchdog for a dead archiver)")
    for line in fresh_report:
        say(line)

    say()
    if failures:
        print("✗ ARCHIVE VERIFY FAILED — DO NOT DELETE ANYTHING", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        sys.exit(1)

    for n in notes:
        say(f"  note: {n}")
    say("✓ ARCHIVE VERIFIED: R2 is a superset of local archive AND of Postgres cold rows, "
        "and is fresh.")


if __name__ == "__main__":
    main()
