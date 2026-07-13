#!/usr/bin/env python3
"""Hot/cold split: archive the bulk time-series to date-partitioned Parquet, then prune Postgres.

WHY THIS EXISTS
---------------
On 2026-07-13 the host disk hit 100% and took prod down: the Docker VM's ext4 journal
aborted, containerd's content store corrupted, and the daemon wedged. The proximate
cause was a 4.87 GB build context, but the real cause is that Postgres is being used as
an ARCHIVE when it is only good as a HOT BUFFER.

Measured that day:

  table                  rows      Postgres    Parquet+zstd   ratio
  trader_fills          10.26M      7,470 MB       450 MB      7.8x   <- +1.15M rows/DAY, retention=FOREVER
  clob_price_tape        2.78M      4,519 MB        47 MB     13.3x
  consensus_vote_window  1.39M      1,342 MB        23 MB     19.3x
  ------------------------------------------------------------------
  total                             ~14.5 GB       520 MB     ~28x

Every row we have ever collected is 520 MB as Parquet. We were burning a 460 GB disk to
hold half a gigabyte of information, and `trader_fills` alone was growing ~860 MB/day
with no retention — the disk was going to die again within weeks.

So: Postgres keeps a bounded HOT window (everything the live bot reads), and everything
older goes to Parquet, which is both the durable archive AND a faster research substrate
(these are full-column analytical scans — backtests, LODO-by-week, permutation nulls —
which is exactly what columnar Parquet is for).

THE HOT WINDOW IS NOT A GUESS. It is set from the longest lookback the live bot actually
performs, so pruning can never change a trading decision:

  CONSENSUS_WINDOW_HOURS           = 48   (2d)   consensus votes
  LIVE_TAPE_LOOKBACK_HOURS         = 6           tape subscription universe
  TAPE_RETENTION_HOURS             = 72   (3d)   tape already self-prunes
  TRADER_FILLS_RESOLVE_RECENT_DAYS = 30   (30d)  <-- the binding constraint

30 days is therefore the floor for trader_fills. We default to 45 for margin.

SAFETY — the ordering is the whole design
-----------------------------------------
EXPORT -> VERIFY -> only then DELETE. A partition is never dropped from Postgres until
its Parquet has been read BACK from the destination and its row count matched against the
source. If verification fails, nothing is deleted and the run exits non-zero. `--prune` is
opt-in; the default is export-only, so the first run can never lose a row.

Usage
-----
  # dry run — shows what WOULD be archived, touches nothing
  python3 scripts/archive_to_parquet.py --dry-run

  # export to local archive only (no prune) — safe, idempotent
  python3 scripts/archive_to_parquet.py

  # export + verify + prune Postgres (the nightly job)
  python3 scripts/archive_to_parquet.py --prune

  # also mirror to Cloudflare R2 (set R2_* env vars first)
  python3 scripts/archive_to_parquet.py --prune --r2
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import duckdb

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
ARCHIVE_DIR = os.environ.get("ARCHIVE_DIR", os.path.expanduser("~/polymarket-archive"))

# R2 (S3-compatible). DuckDB speaks R2 natively — no boto3.
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "polymarket-archive")


@dataclass(frozen=True)
class Table:
    name: str
    ts_col: str                    # the time column that defines a partition
    reason: str                    # why these settings — so nobody "optimises" them and breaks it
    hot_days: int | None = None    # WE own deletion: prune rows older than this
    bot_retention_hours: int | None = None  # THE BOT owns deletion: we archive-only, never prune


# TWO KINDS OF TABLE. Getting this distinction wrong silently destroys data every night.
#
#   (a) WE own deletion  (hot_days set). Append-only, no bot-side retention. We export the
#       cold tail and prune it. The hot window is set from the longest lookback the live bot
#       performs, so pruning can never change a trading decision.
#
#   (b) THE BOT owns deletion  (bot_retention_hours set). The bot ALREADY deletes these on a
#       short timer. We must archive them BEFORE it does, and we must never prune them
#       ourselves — the bot still needs them inside its window.
#
# The first version of this file treated (b) as (a): it gave clob_price_tape a 7-day hot
# window and consensus_vote_window a 14-day one. But the bot deletes the tape at 72h and the
# vote atoms at 48h, so those rows COULD NEVER REACH 7 OR 14 DAYS OLD. The archiver would
# have archived exactly nothing from them, forever, while the bot quietly deleted ~1.2M tape
# rows and ~600k vote atoms a day. (Confirmed by salvage: 8.65M tape rows and 4.24M vote
# atoms existed ONLY inside old pg_dumps, nowhere in the live DB.)
TABLES = [
    Table("trader_fills", "ts",
          "WE own it: no bot retention. TRADER_FILLS_RESOLVE_RECENT_DAYS=30 is the binding "
          "read; 45 gives margin.",
          hot_days=45),
    Table("consensus_snapshots", "ts",
          "WE own it: research-only, no live read path and no bot retention.",
          hot_days=45),
    Table("clob_price_tape", "recv_at",
          "BOT owns it: TAPE_RETENTION_HOURS=72 deletes at 3d. Archive-only — seal each "
          "completed day while it is still inside that window.",
          bot_retention_hours=72),
    Table("consensus_vote_window", "ts",
          "BOT owns it: prune_window_votes() deletes at CONSENSUS_WINDOW_HOURS=48. The bot "
          "NEEDS the full 48h, so we must never prune — archive-only.",
          bot_retention_hours=48),
]


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"ATTACH '{PG_DSN}' AS pg (TYPE postgres, READ_ONLY);")
    return con


def attach_r2(con: duckdb.DuckDBPyConnection) -> None:
    missing = [k for k, v in {
        "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
        "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
        "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
    }.items() if not v]
    if missing:
        sys.exit(f"--r2 requested but these env vars are unset: {', '.join(missing)}")
    con.execute(f"""
        CREATE OR REPLACE SECRET r2secret (
            TYPE r2,
            KEY_ID '{R2_ACCESS_KEY_ID}',
            SECRET '{R2_SECRET_ACCESS_KEY}',
            ACCOUNT_ID '{R2_ACCOUNT_ID}'
        );
    """)


def _archive_exists(con, out: str) -> bool:
    """Does this table's archive prefix have any parquet yet? (R2 has no cheap isdir())"""
    try:
        con.execute(f"SELECT 1 FROM read_parquet('{out}/dt=*/*.parquet') LIMIT 1").fetchall()
        return True
    except Exception:
        return False


def has_column(con, table: str, col: str) -> bool:
    rows = con.execute(
        "SELECT 1 FROM duckdb_columns() WHERE database_name='pg' AND table_name=? AND column_name=?",
        [table, col],
    ).fetchall()
    return bool(rows)


def archive_table(con, t: Table, dest: str, prune: bool, dry_run: bool) -> tuple[int, int]:
    """Returns (rows_archived, rows_pruned)."""
    if not has_column(con, t.name, t.ts_col):
        print(f"  ! {t.name}: no column {t.ts_col!r} — SKIPPED (schema drift?)")
        return (0, 0)

    src = f"pg.{t.name}"

    # FREEZE the cutoff to ONE absolute instant, in UTC, and use that same instant for the
    # count, the export, AND the delete. Two separate bugs live here; both are load-bearing.
    #
    # 1. A MOVING cutoff. Do not inline `now() - INTERVAL n DAY` into each query — `now()`
    #    re-evaluates per statement, so the boundary creeps forward between the count and
    #    the export. On the first real run the export picked up exactly one row that had
    #    aged past it in the intervening seconds (source 1,167,018 vs archive 1,167,019)
    #    and verification correctly refused to prune.
    #
    # 2. A NAIVE cutoff. Do not cast to `::TIMESTAMP` and hand the bare string to Postgres.
    #    DuckDB's session was -07:00 while Postgres's was UTC, so the same literal meant
    #    two different instants SEVEN HOURS apart: the export cut at 20:57 UTC and the
    #    DELETE cut at 13:57 UTC (measured — a 7,354-row disagreement). That run was lucky:
    #    it archived MORE than it deleted. Run this on a host EAST of UTC and the sign
    #    flips — the DELETE outruns the export and removes rows that were never archived.
    #    Silent data loss is the one outcome this script exists to prevent.
    #
    # So: an explicit timezone-aware UTC instant, TIMESTAMPTZ on the DuckDB side and a
    # tz-aware datetime on the psycopg2 side. No implicit conversion anywhere.
    #
    # Snap to UTC MIDNIGHT, not an exact now-minus-N instant. A day-partition must be either
    # entirely archived or entirely hot — never split — or the same day would be written by
    # two different runs, which is the duplication we just outlawed. Snapping down also only
    # ever makes the hot window LONGER, never shorter, so it cannot cut below the bot's
    # lookback.
    now = datetime.now(timezone.utc)
    midnight_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    may_prune = prune and t.hot_days is not None
    if t.hot_days is not None:
        cutoff = (now - timedelta(days=t.hot_days)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        label = f"hot={t.hot_days}d, WE prune"
    else:
        # Bot-owned retention: everything up to LAST midnight is a completed day and is fair
        # game to seal. We never prune — the bot's own retention does the deleting, and it
        # still needs these rows inside its window.
        cutoff = midnight_today
        label = f"bot deletes at {t.bot_retention_hours}h, ARCHIVE-ONLY"
    cut = f"TIMESTAMPTZ '{cutoff.isoformat()}'"

    cold, hot = con.execute(
        f"SELECT count(*) FILTER (WHERE {t.ts_col} <  {cut}),"
        f"       count(*) FILTER (WHERE {t.ts_col} >= {cut}) FROM {src}"
    ).fetchone()

    print(f"\n=== {t.name}  ({label})")
    print(f"    {t.reason}")
    print(f"    archivable: {cold:>12,}    stays in PG: {hot:>12,}")
    if cold == 0:
        print("    nothing to archive")
        return (0, 0)
    if dry_run:
        print("    [dry-run] would export + verify" + (" + prune" if may_prune else ""))
        return (0, 0)

    out = f"{dest}/{t.name}"

    # PARTITIONS ARE IMMUTABLE: each day is written EXACTLY ONCE, and a day already in the
    # archive is never rewritten. Both halves matter, and both were learned the hard way.
    #
    #  - Re-exporting into an existing partition DUPLICATES. `OVERWRITE_OR_IGNORE` with a
    #    `{uuid}` filename drops a NEW file into the existing dt=… dir and leaves the old
    #    one, so every re-run silently doubles rows (measured: 14,721 dupes across 4 runs).
    #    That inflates every count in every backtest.
    #
    #  - But "just overwrite the partition instead" is WORSE. After a prune, the source no
    #    longer holds the rows it already archived, so re-exporting that day would write
    #    only the remainder and OVERWRITE the complete file with a partial one. That is
    #    real, unrecoverable data destruction.
    #
    # So we skip any day already present, and we only ever archive days that are WHOLLY
    # cold (date < cutoff_date, a UTC midnight boundary). A whole-day boundary is what makes
    # a partition complete-once: a late-arriving fill can never land in a day we already
    # sealed, because that day is already >45d old.
    already = set()
    part_root = f"{out}"
    if dest.startswith("r2://"):
        rows = con.execute(
            f"SELECT DISTINCT dt FROM read_parquet('{out}/dt=*/*.parquet', hive_partitioning=true)"
        ).fetchall() if _archive_exists(con, out) else []
        already = {str(r[0]) for r in rows}
    elif os.path.isdir(part_root):
        already = {d.split("=", 1)[1] for d in os.listdir(part_root) if d.startswith("dt=")}

    days = [str(r[0]) for r in con.execute(
        f"SELECT DISTINCT CAST({t.ts_col} AS DATE) d FROM {src} WHERE {t.ts_col} < {cut} ORDER BY 1"
    ).fetchall()]
    todo = [d for d in days if d not in already]

    # A bot-retention table can hand us a day it has ALREADY started deleting. Sealing that
    # would write a PARTIAL day and mark it done forever (partitions are immutable), quietly
    # baking a hole into the archive. A day D is only whole while  now < (D+1 00:00) + retention.
    # Anything past that we refuse to seal, and we say so loudly — a skipped day here means
    # rows were lost before we ever saw them, which is an operational alarm, not a footnote.
    if t.bot_retention_hours is not None:
        whole, partial = [], []
        for d in todo:
            end_of_day = datetime.fromisoformat(d).replace(tzinfo=timezone.utc) + timedelta(days=1)
            (whole if now < end_of_day + timedelta(hours=t.bot_retention_hours)
             else partial).append(d)
        if partial:
            print(f"    ⚠ REFUSING to seal {len(partial)} day(s) the bot has already begun "
                  f"deleting (past its {t.bot_retention_hours}h retention): {', '.join(partial)}")
            print(f"    ⚠ those days are INCOMPLETE in Postgres. If they are not already in the "
                  f"archive, that data is GONE — the nightly job did not run in time.")
        todo = whole

    if not todo:
        print(f"    all {len(days)} completed day-partitions already sealed in the archive")
    else:
        print(f"    sealing {len(todo)} new day-partition(s) "
              f"({len(days) - len(todo)} already present, left untouched)")
        day_list = ", ".join(f"DATE '{d}'" for d in todo)
        con.execute(f"""
            COPY (
                SELECT *, CAST({t.ts_col} AS DATE) AS dt
                FROM {src}
                WHERE {t.ts_col} < {cut}
                  AND CAST({t.ts_col} AS DATE) IN ({day_list})
            ) TO '{out}' (
                FORMAT parquet, COMPRESSION zstd,
                PARTITION_BY (dt), APPEND,
                FILENAME_PATTERN 'part'
            );
        """)
        print(f"    exported -> {out}/dt=*/")

    # VERIFY — the invariant is "every row we are about to DELETE provably exists in the
    # archive", checked as an anti-join on the primary key.
    #
    # NOT "archive row count == source cold count". That only holds on a virgin archive: the
    # archive ACCUMULATES across nightly runs, so on the second run it legitimately holds
    # every previously-archived row too, and a count comparison fails forever (measured:
    # source cold 7,367 vs archive 1,174,394 — both correct, the check was wrong).
    #
    # The anti-join is also the STRONGER check. A count match can pass while holding the
    # wrong rows; "zero source rows missing from the archive" cannot. It reads the Parquet
    # back from the destination, so it exercises the real read path we would rely on to
    # recover.
    # Scope BOTH the verify and the prune to the days we have actually SEALED. A
    # bot-retention table can legitimately hold rows in a day we refused to seal (because the
    # bot already began deleting it); those rows are not in the archive and never will be, so
    # verifying against them would fail the run, and — far worse — a cutoff-based DELETE would
    # remove them. We only ever touch days that are provably in the archive.
    sealed = sorted(already | set(todo))
    if not sealed:
        return (0, 0)
    sealed_list = ", ".join(f"DATE '{d}'" for d in sealed)
    scope = f"s.{t.ts_col} < {cut} AND CAST(s.{t.ts_col} AS DATE) IN ({sealed_list})"

    in_scope = con.execute(f"SELECT count(*) FROM {src} s WHERE {scope}").fetchone()[0]
    missing = con.execute(f"""
        SELECT count(*) FROM {src} s
        WHERE {scope}
          AND NOT EXISTS (
            SELECT 1 FROM read_parquet('{out}/dt=*/*.parquet', hive_partitioning=true) a
            WHERE a.id = s.id
          )
    """).fetchone()[0]
    if missing:
        sys.exit(
            f"    ✗ VERIFY FAILED for {t.name}: {missing:,} of {in_scope:,} rows in sealed "
            f"partitions are NOT readable back from the archive. NOTHING PRUNED."
        )
    print(f"    ✓ verified: all {in_scope:,} rows in sealed partitions read back from the archive")

    if not may_prune:
        why = ("bot owns retention — archive-only by design"
               if t.bot_retention_hours is not None else "prune not requested")
        print(f"    (Postgres untouched — {why})")
        return (cold, 0)

    # Safe to delete: written, read back, and scoped to sealed days only.
    import psycopg2  # only needed for the write path; DuckDB's pg attach is READ_ONLY
    with psycopg2.connect(PG_DSN) as pc, pc.cursor() as cur:
        cur.execute(
            f"DELETE FROM {t.name} WHERE {t.ts_col} < %s "
            f"AND CAST({t.ts_col} AS DATE) IN ({sealed_list})",
            (cutoff,),
        )
        pruned = cur.rowcount
        pc.commit()
    print(f"    ✓ pruned {pruned:,} rows from Postgres")
    return (cold, pruned)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prune", action="store_true",
                    help="DELETE archived rows from Postgres (only after verify passes)")
    ap.add_argument("--r2", action="store_true", help="write to Cloudflare R2 instead of local disk")
    ap.add_argument("--dry-run", action="store_true", help="report only; touch nothing")
    args = ap.parse_args()

    con = connect()
    if args.r2:
        attach_r2(con)
        dest = f"r2://{R2_BUCKET}"
    else:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        dest = ARCHIVE_DIR

    print(f"archive destination: {dest}")
    print(f"prune Postgres     : {args.prune}")

    tot_a = tot_p = 0
    for t in TABLES:
        a, p = archive_table(con, t, dest, args.prune, args.dry_run)
        tot_a += a
        tot_p += p

    print(f"\n=== TOTAL archived: {tot_a:,} rows   pruned from Postgres: {tot_p:,} rows")
    if tot_p:
        print("NOTE: Postgres does not return disk space on DELETE. Reclaim it with:")
        print("  docker exec polymarket-bot-postgres-1 psql -U bot -d polymarket \\")
        print("    -c 'VACUUM (FULL, ANALYZE) trader_fills;'")


if __name__ == "__main__":
    main()
