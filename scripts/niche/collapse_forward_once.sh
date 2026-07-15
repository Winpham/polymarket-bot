#!/usr/bin/env bash
# One scan+settle tick for the collapse forward paper test. Invoked by launchd on a timer, so there
# is no long-lived process to be reaped. Read-only except the append-only collapse_paper_signals.
set -u
cd /Users/tuepham/polymarket-bot || exit 1
python3 scripts/niche/collapse_forward.py --scan
python3 scripts/niche/collapse_forward.py --settle
