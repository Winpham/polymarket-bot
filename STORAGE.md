# Storage architecture — the hot/cold split

**Written 2026-07-13, the day the disk filled and took prod down.**

## What happened, and why the fix is not "buy a bigger disk"

The host disk hit 100% (134 MB free). The Docker VM's ext4 journal aborted, containerd's
content store corrupted, the daemon wedged, and **prod went down**. The proximate trigger
was a 4.87 GB Docker build context (`.dockerignore` did not exclude `backups/`). The real
cause is that **Postgres was being used as an archive when it is only good as a hot buffer.**

Measured that day:

| table | rows | Postgres | Parquet+zstd | ratio |
|---|---|---|---|---|
| `trader_fills` | 10.26M | 7,470 MB | 450 MB | 7.8× |
| `clob_price_tape` | 2.78M | 4,519 MB | 47 MB | 13.3× |
| `consensus_vote_window` | 1.39M | 1,342 MB | 23 MB | 19.3× |
| **total** | **~14.5M** | **~14.5 GB** | **520 MB** | **~28×** |

**Every row we have ever collected is 520 MB.** We were burning a 460 GB disk to hold half a
gigabyte of information — and `trader_fills` was growing **~1.15M rows/day with no retention
at all** (`TRADER_FILLS_RETENTION_DAYS=0`), so the disk was going to die again within weeks.

Two distinct problems were hiding behind one symptom:

1. **Index bloat.** `clob_price_tape` churns constantly (72h retention, delete-heavy) and its
   B-tree indexes had grown to **3,612 MB against a 906 MB heap — 4× its own data.**
   `REINDEX TABLE CONCURRENTLY` (no lock, no downtime) took the DB from **14.5 GB → 10 GB**.
2. **Unbounded growth.** Fixed by the hot/cold split below.

## The design

**Postgres holds a bounded HOT window. Parquet holds everything else.**

The hot window is **not a guess** — it is set from the longest lookback the live bot actually
performs, so pruning can never change a trading decision:

| knob | value | binds |
|---|---|---|
| `CONSENSUS_WINDOW_HOURS` | 48 (2d) | consensus votes |
| `LIVE_TAPE_LOOKBACK_HOURS` | 6 | tape universe |
| `TAPE_RETENTION_HOURS` | 72 (3d) | tape self-prunes |
| **`TRADER_FILLS_RESOLVE_RECENT_DAYS`** | **30** | **← the binding constraint** |

So `trader_fills` keeps **45 days** (30 + margin). Cold rows go to date-partitioned Parquet.

This is not only cheaper, it is a **faster research substrate**. Our real workload is
full-column analytical scans — backtests, LODO-by-week, permutation nulls, band studies —
which is exactly what columnar Parquet is for. A `GROUP BY` over the entire 3.5-year archive
runs in **0.22 s** with zero Postgres involvement.

## Running it

```bash
python3 scripts/archive_to_parquet.py --dry-run   # report only, touches nothing
python3 scripts/archive_to_parquet.py             # export + verify, no prune (safe)
python3 scripts/archive_to_parquet.py --prune     # the nightly job
python3 scripts/archive_to_parquet.py --prune --r2  # mirror to Cloudflare R2
```

It runs nightly at 04:00 from `scripts/consensus-backup.sh` (launchd
`com.tue.consensus.backup`), **before** the `pg_dump` — so the dump is a dump of the hot
buffer, not of all history.

## Reading the archive

```python
import duckdb
con = duckdb.connect()
fills = "~/polymarket-archive/trader_fills/dt=*/*.parquet"   # or r2://bucket/trader_fills/...
con.execute(f"SELECT count(*) FROM read_parquet('{fills}', hive_partitioning=true)")
```

`hive_partitioning=true` exposes `dt` as a real column, so `WHERE dt >= '2026-06-01'` skips
whole files. To query hot + cold together, `UNION ALL` the Parquet with the Postgres table
(Postgres is reachable at `127.0.0.1:5432`, loopback-only).

## The three invariants — do not "optimise" these away

Each was learned by breaking it, on real data, in this order:

1. **The cutoff is ONE frozen, timezone-aware UTC instant**, shared by the count, the export,
   and the delete. Inlining `now()` per statement let the boundary creep between statements.
   Worse, casting to a naive `::TIMESTAMP` made DuckDB (`-07:00`) and Postgres (`UTC`) read
   the same literal as **two instants 7 hours apart** — the export cut at 20:57 UTC while the
   DELETE cut at 13:57 UTC (a measured 7,354-row disagreement). That run was *lucky*: it
   archived more than it deleted. **On a host east of UTC the sign flips and the DELETE
   outruns the export, destroying rows that were never archived.**

2. **Partitions are IMMUTABLE — each day is sealed exactly once.** Re-exporting into an
   existing partition duplicates (`OVERWRITE_OR_IGNORE` + a `{uuid}` filename drops a *new*
   file beside the old one: 14,721 dupes across 4 runs, which would silently inflate every
   backtest). And "just overwrite the partition instead" is **worse** — after a prune the
   source no longer holds what it already archived, so a rewrite would replace a complete
   file with a partial one. That is unrecoverable destruction. Hence: skip days already
   present, and only ever seal days that are *wholly* cold (a UTC-midnight boundary).

3. **VERIFY is an anti-join on the primary key, not a row count.** The invariant is *"every
   row about to be deleted provably exists in the archive"* — checked by reading the Parquet
   back from the destination. A count match can pass while holding the wrong rows; a count
   match also breaks by design on the second run, because the archive legitimately
   accumulates. **Nothing is deleted until this passes; `--prune` is opt-in.**

## Cloudflare R2 (needs Tue — 5 minutes, once)

Local Parquet fixes the disk, but it is still **one laptop, one disk** — and that disk just
proved it can take prod down. R2 makes the archive durable and off-box.

1. Cloudflare dashboard → **R2** → *Create bucket* → name it `polymarket-archive`.
2. **R2 → Manage API Tokens → Create token** (Object Read & Write, scoped to that bucket).
3. Put these in `.env.consensus` (gitignored):
   ```
   R2_ACCOUNT_ID=...
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   R2_BUCKET=polymarket-archive
   ```
4. `python3 scripts/archive_to_parquet.py --r2` (no `--prune` the first time).

**Why R2 and not S3:** 10 GB free and **$0 egress, forever.** Egress-free is the whole point —
we re-scan the archive constantly for backtests, and S3 would bill for every one. Our entire
history is 520 MB, i.e. ~5% of the free tier, and beyond that R2 is $0.015/GB/month.

## What is NOT in scope

**Obsidian is not a database.** Rows go to Parquet. *Conclusions* — the verdicts, the
retractions, `DECISIONS.md`, the certification results — are what belong in the brain,
because those are re-read and reasoned over. Rows → Parquet. Findings → Obsidian.

Free managed Postgres tiers (Supabase 500 MB, Neon 0.5 GB) **cannot hold the bulk** and it is
dishonest to pretend otherwise. They would comfortably hold the *hot* state (~70k rows) if we
ever want the bot off this laptop — that is a separate, later decision.
