#!/bin/bash
# TAPE WATCHDOG: is the forward tape still moving? Shout if not.
#
# THE SIBLING OF archive-watchdog.sh, AND IT EXISTS FOR THE SAME REASON ON A NEW SURFACE.
# ---------------------------------------------------------------------------------------
# archive-watchdog.sh asks "is the SEALED ARCHIVE fresh?" -- because a job that never runs
# sends no failure, and on 2026-07-13 silence read as health.
#
# On 2026-07-14 the identical failure happened one layer up. Postgres was DOWN for ~2 hours
# (host disk 96% -> the Docker VM filesystem went read-only). The bot could not write. And
# the whole time:
#
#       $ docker ps
#       polymarket-bot-postgres-1   Up 19 hours (healthy)
#
# The healthcheck lied and NOTHING NOTICED. Nothing was asking "is the LIVE TAPE moving?"
#
# Why that is expensive rather than merely embarrassing: the at-fire US quote capture went
# live that same day and CANNOT BE BACKFILLED. And a gap in an append-only tape is invisible
# after the fact -- it looks exactly like a quiet market. GATE A's whole premise is "the
# tapes accrue"; a 30-day forward window with a silent hole in it is not a forward window.
#
# The brief's Hard Rule 2 is "fail closed on stale data." This is that rule, in a cron slot.
set -uo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
# Resolve the repo from THIS SCRIPT'S OWN LOCATION, not from $HOME. A watchdog that only runs
# in one checkout is a watchdog you cannot test before you need it -- and an untested alarm is
# the thing this file exists to abolish. This way it runs identically from a worktree.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$REPO/.tape-watchdog.log"
cd "$REPO" || exit 1

set -a
# shellcheck disable=SC1091
[ -f "$REPO/.env.consensus" ] && . "$REPO/.env.consensus"
set +a

ts() { date '+%F %T'; }

OUT="$(python3 "$REPO/scripts/tape_freshness.py" 2>&1)"
RC=$?

if [ $RC -eq 0 ]; then
  echo "$(ts) tape OK — all forward tapes fresh" >> "$LOG"
  exit 0
fi

echo "$(ts) TAPE STALE:" >> "$LOG"
echo "$OUT" >> "$LOG"

# Minimal-noise policy: we push ONLY when Tue must act now. A dead tape is exactly that --
# every minute of silence is forward evidence that can never be recovered.
if [ -n "${NTFY_TOPIC:-}" ]; then
  curl -fsS -H "Title: polymarket TAPE STALE — data is being LOST" -H "Priority: urgent" \
    -d "The forward tape has stopped moving. It CANNOT be backfilled, and a gap looks like a
quiet market after the fact. Check the DB is actually up — 'docker ps' has reported
'healthy' through a total outage before (2026-07-14). Details in $LOG:
$(echo "$OUT" | tail -6)" \
    "${NTFY_SERVER:-https://ntfy.sh}/$NTFY_TOPIC" >/dev/null 2>&1 || true
fi
exit 1
