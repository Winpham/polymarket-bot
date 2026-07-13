#!/bin/bash
# Nightly: ARCHIVE the cold tail to Parquet, then dump the (now small) hot DB.
#
# Order matters. The archiver prunes Postgres down to its hot window first, so the pg_dump
# that follows is a dump of the HOT BUFFER, not of the whole history. History lives in the
# Parquet archive, which is the durable long-term record.
#
# WHY THE DISK GUARD EXISTS (read before removing it):
# On 2026-07-13 this script's own dump filled the host disk. The Docker VM's ext4 journal
# aborted, containerd's content store corrupted, the daemon wedged, and PROD WENT DOWN. A
# backup job must never be the thing that kills the database it is backing up. If the disk
# is tight, we now skip and shout rather than write into the last free byte.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
REPO="$HOME/polymarket-bot"
cd "$REPO" 2>/dev/null || exit 0
BK="$REPO/backups"
LOG="$REPO/.backup.log"
mkdir -p "$BK"

ts() { date '+%F %T'; }

# --- disk guard -------------------------------------------------------------------------
# Require headroom for a dump (~1 GB today) plus a wide margin. Bail BEFORE writing.
FREE_MB=$(df -m /System/Volumes/Data 2>/dev/null | awk 'NR==2 {print $4}')
MIN_FREE_MB=${MIN_FREE_MB:-15000}   # 15 GB
if [ -n "$FREE_MB" ] && [ "$FREE_MB" -lt "$MIN_FREE_MB" ]; then
  echo "$(ts) ABORT: only ${FREE_MB}MB free (< ${MIN_FREE_MB}MB). Not writing a dump onto a full disk." >> "$LOG"
  exit 1
fi

docker info >/dev/null 2>&1 || exit 0
PG="$(docker compose -f docker-compose.consensus.yml --env-file .env.consensus ps -q postgres 2>/dev/null)"
[ -z "$PG" ] && exit 0

# --- 1. archive the cold tail, then prune Postgres ---------------------------------------
# Fail-closed by construction: the archiver verifies every row is readable back from the
# archive before it deletes anything. If it exits non-zero we still take the dump — a
# failed archive must never cost us a backup.
if python3 "$REPO/scripts/archive_to_parquet.py" --prune >> "$LOG" 2>&1; then
  echo "$(ts) archive OK" >> "$LOG"
else
  echo "$(ts) archive FAILED (continuing to dump — a failed archive must not skip the backup)" >> "$LOG"
fi

# --- 2. dump the hot DB ------------------------------------------------------------------
F="$BK/consensus-$(date +%Y%m%d-%H%M).sql.gz"
if docker exec "$PG" pg_dump -U bot polymarket 2>/dev/null | gzip > "$F" && [ -s "$F" ]; then
  # Keep 7 daily dumps. Was 14, but each was ~870 MB and growing — 12+ GB of rolling dumps
  # on the same disk as the database is what set the original fire. The Parquet archive is
  # now the durable long-term record; these dumps only need to cover recent operator error.
  ls -1t "$BK"/consensus-*.sql.gz 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null
  echo "$(ts) backup OK -> $(basename "$F") ($(du -h "$F" | cut -f1)); free=$(df -m /System/Volumes/Data | awk 'NR==2{print $4}')MB" >> "$LOG"
else
  rm -f "$F"
  echo "$(ts) backup FAILED" >> "$LOG"
fi
