#!/usr/bin/env bash
# Continuous forward-test driver: scan for new crossings + settle matured markets, on a timer.
# Keeps the pre-registered collapse-model paper test accruing on live US prices.
# Run under launchd/nohup. Read-only except the append-only collapse_paper_signals table.
set -u
cd "$(dirname "$0")/../.." || exit 1
INTERVAL="${COLLAPSE_FWD_INTERVAL:-600}"   # 10 min
echo "collapse forward loop: every ${INTERVAL}s"
while true; do
  python3 scripts/niche/collapse_forward.py --scan  >> .collapse_forward.log 2>&1
  python3 scripts/niche/collapse_forward.py --settle >> .collapse_forward.log 2>&1
  sleep "$INTERVAL"
done
