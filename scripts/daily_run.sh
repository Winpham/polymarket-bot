#!/bin/bash
# Daily refresh for the honest paper-trading tracker (scripts/paper_tracker.py).
# READ-ONLY: it only re-renders reports/PAPER-TRACKER.{json,md} from the live
# honest_paper_ledger + consensus_signals tables. Deploys nothing, arms nothing,
# writes no DB rows. Safe to re-run at any cadence; each run just overwrites the
# two report files with the current state.
#
# No OS-level scheduler is wired to this script yet -- unlike consensus-backup.sh
# (see com.tue.consensus.updater.plist / com.tue.consensus.backup.plist under
# ~/Library/LaunchAgents/), there is no daily/report cadence in this repo today.
# To make refresh ONGOING rather than manual, point a launchd agent or cron entry
# at this script (e.g. daily at 08:00):
#   0 8 * * * $HOME/polymarket-bot/scripts/daily_run.sh
# (adding that schedule is an OS-level change outside this script's own scope --
# a deliberate call for Tue, matching the "no launchd/cron edits" guardrail this
# run was built under.)
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
REPO="${REPO:-$HOME/polymarket-bot}"   # overridable for testing from a worktree
cd "$REPO" 2>/dev/null || exit 0
LOG="$REPO/.paper_tracker.log"
ts() { date "+%Y-%m-%d %H:%M:%S"; }

docker info >/dev/null 2>&1 || { echo "$(ts) docker not running -- skip" >> "$LOG"; exit 0; }
docker exec polymarket-bot-postgres-1 pg_isready -U bot -d polymarket >/dev/null 2>&1 \
  || { echo "$(ts) postgres container not ready -- skip" >> "$LOG"; exit 0; }

if python3 scripts/paper_tracker.py >> "$LOG" 2>&1; then
  echo "$(ts) paper_tracker OK -> reports/PAPER-TRACKER.{json,md}" >> "$LOG"
else
  echo "$(ts) paper_tracker FAILED (see above in this log) -- champion anchor may not have tied out" >> "$LOG"
fi
