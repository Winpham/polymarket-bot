#!/bin/bash
# Daily watchdog: is the archive actually fresh? Shout if not.
#
# WHY THIS IS A SEPARATE JOB FROM THE NIGHTLY (the whole point)
# ------------------------------------------------------------
# consensus-backup.sh alerts when the archiver RUNS AND FAILS. It cannot alert when the
# archiver never runs at all — a job that is not running sends no failure. On 2026-07-13
# that was the real bug: the archive step had never executed once, while every nightly
# backup reported success. Silence read as health.
#
# This job is the independent observer. It does not care why the archive is stale — dead
# launchd, renamed script, tripped disk guard, wrong env — it only asks the question that
# matters: IS THE NEWEST SEALED PARTITION RECENT? The bot deletes the tape at 72h, so a
# stale archive is history being destroyed on a clock.
set -uo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
REPO="$HOME/polymarket-bot"
LOG="$REPO/.backup.log"
cd "$REPO" || exit 1

set -a
# shellcheck disable=SC1091
[ -f "$REPO/.env.consensus" ] && . "$REPO/.env.consensus"
set +a

ts() { date '+%F %T'; }

OUT="$(python3 "$REPO/scripts/verify_archive.py" 2>&1)"
if [ $? -eq 0 ]; then
  echo "$(ts) watchdog OK — archive verified (R2 superset, fresh)" >> "$LOG"
  exit 0
fi

echo "$(ts) watchdog FAILED:" >> "$LOG"
echo "$OUT" >> "$LOG"

if [ -n "${NTFY_TOPIC:-}" ]; then
  curl -fsS -H "Title: polymarket ARCHIVE UNSAFE" -H "Priority: urgent" \
    -d "verify_archive.py failed. The archive is stale, incomplete, or unreadable — and the tape is deleted at 72h, so history is being lost. DO NOT delete any dump. Details in $LOG:
$(echo "$OUT" | tail -6)" \
    "${NTFY_SERVER:-https://ntfy.sh}/$NTFY_TOPIC" >/dev/null 2>&1 || true
fi
exit 1
