#!/bin/bash
# Forward-deployment accrual — re-runs the paper tracker so it picks up newly-resolved favorite
# bets. Read-only on the DB. Safe to run repeatedly (idempotent: recomputes from the frozen ts).
# Logs one status line per run. Installed via com.tue.sizing-tracker (launchd, every 6h).
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
REPO="$HOME/polymarket-bot"
LOG="$REPO/reports/sizing/accrual_log.txt"
cd "$REPO" || exit 0
ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# skip quietly if the DB container isn't up (laptop asleep / docker down)
if ! docker ps --filter name=polymarket-bot-postgres-1 --format '{{.Names}}' | grep -q postgres; then
  echo "$ts  SKIP (db container down)" >> "$LOG"
  exit 0
fi

out="$(/usr/bin/python3 scripts/sizing/forward_deploy.py 2>&1)"
verdict="$(echo "$out" | grep -E '^VERDICT:' | sed 's/^VERDICT: //')"
fwd="$(echo "$out" | grep -Eo '[0-9]+ FORWARD' | head -1)"
echo "$ts  ${fwd:-0 FORWARD}  |  ${verdict:-run-error}" >> "$LOG"
