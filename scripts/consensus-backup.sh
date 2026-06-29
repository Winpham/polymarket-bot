#!/bin/bash
# Daily backup of the forward record. The resolved outcomes / surplus history
# CANNOT be recreated (you can't backfill a market's resolution after the fact),
# so a rolling local dump protects the one irreplaceable asset. Run by launchd.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
REPO="$HOME/polymarket-bot"
cd "$REPO" 2>/dev/null || exit 0
BK="$REPO/backups"
mkdir -p "$BK"

docker info >/dev/null 2>&1 || exit 0
PG="$(docker compose -f docker-compose.consensus.yml --env-file .env.consensus ps -q postgres 2>/dev/null)"
[ -z "$PG" ] && exit 0

F="$BK/consensus-$(date +%Y%m%d-%H%M).sql.gz"
if docker exec "$PG" pg_dump -U bot polymarket 2>/dev/null | gzip > "$F" && [ -s "$F" ]; then
  # Rotate: keep the most recent 14 daily dumps.
  ls -1t "$BK"/consensus-*.sql.gz 2>/dev/null | tail -n +15 | xargs rm -f 2>/dev/null
  echo "$(date '+%F %T') backup OK -> $(basename "$F") ($(du -h "$F" | cut -f1))" >> "$REPO/.backup.log"
else
  rm -f "$F"
  echo "$(date '+%F %T') backup FAILED" >> "$REPO/.backup.log"
fi
