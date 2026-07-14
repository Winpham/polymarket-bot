#!/usr/bin/env bash
# Keepalive wrapper for the read-only US sidecars.
#
# The ingesters already reconnect internally on a WS drop (backoff to 30s). This wrapper covers
# the one thing they can't: death of the PROCESS itself (crash, OOM, reaped background job on a
# long autonomous run). It re-launches and keeps going, appending to one log.
#
# NOT a launch unit: nothing schedules this. Default-OFF survives — an operator (or a run) starts
# it explicitly. Read-only; never places an order.
#
#   ./scripts/us_keepalive.sh us_tape_ingest.py           # forever, restart on death
#   ./scripts/us_keepalive.sh us_book_sampler.py --loop 60
set -u
cd "$(dirname "$0")/.."
export ARCHIVE_PG_DSN="${ARCHIVE_PG_DSN:-postgresql://bot:bot@127.0.0.1:5432/polymarket}"
script="$1"; shift
log="/tmp/us-${script%.py}.log"
echo "=== keepalive start $(date -u +%FT%TZ) : $script $* ===" >>"$log"
n=0
while true; do
  n=$((n + 1))
  echo "--- launch #$n $(date -u +%FT%TZ) ---" >>"$log"
  python3 "scripts/$script" "$@" >>"$log" 2>&1
  echo "--- exited rc=$? $(date -u +%FT%TZ), relaunching in 5s ---" >>"$log"
  sleep 5
done
