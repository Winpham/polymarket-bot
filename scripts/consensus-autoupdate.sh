#!/bin/bash
# Auto-update + keep-alive for the consensus bot. Run by a launchd agent every
# few minutes (and at login). It:
#   1. starts Docker Desktop if it isn't running (survives reboots),
#   2. fast-forwards the repo to its upstream if one is configured (safe, ff-only),
#   3. rebuilds + recreates the stack whenever HEAD advances (new commits land)
#      or the stack is down — so future improvements deploy automatically.
# Idempotent and quiet; appends to .autoupdate.log.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

REPO="$HOME/polymarket-bot"
ENV_FILE=".env.consensus"
COMPOSE_FILE="docker-compose.consensus.yml"
cd "$REPO" 2>/dev/null || exit 0
LOG="$REPO/.autoupdate.log"
ts() { date "+%Y-%m-%d %H:%M:%S"; }
compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

# Need the env file (the ntfy topic) to run.
[ -f "$ENV_FILE" ] || { echo "$(ts) missing $ENV_FILE" >> "$LOG"; exit 0; }

# Start Docker Desktop if the daemon isn't up yet; retry next interval.
if ! docker info >/dev/null 2>&1; then
  open -a Docker >/dev/null 2>&1
  echo "$(ts) docker not ready — launched Docker.app, will retry" >> "$LOG"
  exit 0
fi

# Fast-forward to upstream if one exists (won't clobber local-only work).
git fetch --quiet 2>/dev/null
if git rev-parse '@{u}' >/dev/null 2>&1; then
  git merge --ff-only '@{u}' >/dev/null 2>&1 && echo "$(ts) fast-forwarded to upstream" >> "$LOG"
fi

HEAD="$(git rev-parse HEAD 2>/dev/null)"
LAST="$(cat .last_built_commit 2>/dev/null)"
UP="$(compose ps -q copy-trading-bot 2>/dev/null)"

# Paths whose changes actually affect the running image.
CODE_RE='^(common/|copy-trading-bot/|migrations/|Cargo\.|Dockerfile\.consensus|docker-compose\.consensus\.yml)'

NEED_REBUILD=0
REASON=""
if [ -z "$UP" ]; then
  NEED_REBUILD=1; REASON="stack down"
elif [ -z "$LAST" ]; then
  NEED_REBUILD=1; REASON="first run"
elif [ "$HEAD" != "$LAST" ]; then
  if git diff --name-only "$LAST" "$HEAD" 2>/dev/null | grep -qE "$CODE_RE"; then
    NEED_REBUILD=1; REASON="code changed $LAST..$HEAD"
  else
    # New commits but no code change (docs/reports) — record HEAD, skip rebuild.
    echo "$HEAD" > .last_built_commit
    echo "$(ts) no code change $LAST..$HEAD — skipped rebuild" >> "$LOG"
  fi
fi

if [ "$NEED_REBUILD" = "1" ]; then
  echo "$(ts) (re)deploying — $REASON" >> "$LOG"
  if compose up -d --build >> "$LOG" 2>&1; then
    echo "$HEAD" > .last_built_commit
    echo "$(ts) deploy OK ($HEAD)" >> "$LOG"
  else
    echo "$(ts) deploy FAILED" >> "$LOG"
  fi
fi
