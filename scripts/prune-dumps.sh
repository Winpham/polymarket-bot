#!/bin/bash
# The ONLY sanctioned way to delete a pg_dump. Never `rm` one by hand.
#
# WHY — 2026-07-13 near-miss
# --------------------------
# We came within one command of deleting 15 dumps as "redundant, already in R2." They
# were not. R2 held 6 recent day-partitions; the dumps were the ancestor of the only
# copy of trader_fills back to 2022-12-15. The claim of redundancy had never been
# tested against the bucket.
#
# So redundancy is no longer something anyone gets to assert. It is proven here, by
# machine, or nothing is deleted:
#
#   GATE 1  the Parquet archive verifies (R2 ⊇ local ⊇ Postgres cold, and fresh)
#   GATE 2  a full dump still survives — offsite in R2 AND locally
#
# GATE 2 is separate on purpose. The Parquet archive covers FOUR tables. A pg_dump
# covers EVERY table. A green archive says nothing about the other tables, so it can
# never license deleting your last full-DB snapshot. Conflating those two is the same
# reasoning error that caused the near-miss, one level up.
set -uo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
REPO="$HOME/polymarket-bot"
BK="$REPO/backups"
KEEP="${KEEP:-2}"            # full dumps retained LOCALLY (newest first)
cd "$REPO" || exit 1

set -a
# shellcheck disable=SC1091
[ -f "$REPO/.env.consensus" ] && . "$REPO/.env.consensus"
set +a

DRY=1
[ "${1:-}" = "--apply" ] && DRY=0

# ---- GATE 1: the archive must verify ---------------------------------------------
echo "GATE 1  verifying the Parquet archive…"
if ! python3 "$REPO/scripts/verify_archive.py"; then
  echo "✗ ABORT: archive did not verify. Nothing deleted." >&2
  exit 1
fi

# ---- GATE 2: a full dump must survive, offsite AND local -------------------------
NEWEST="$(ls -1t "$BK"/consensus-*.sql.gz 2>/dev/null | head -1)"
if [ -z "$NEWEST" ]; then
  echo "✗ ABORT: no full dump found in $BK. Refusing to prune what I cannot verify." >&2
  exit 1
fi
BASE="$(basename "$NEWEST")"

echo "GATE 2  newest full dump: $BASE — confirming it is in R2…"
LOCAL_BYTES="$(wc -c < "$NEWEST" | tr -d ' ')"
R2_BYTES="$(python3 "$REPO/scripts/r2_head.py" "dumps/$BASE")"

if [ "${R2_BYTES:-0}" != "$LOCAL_BYTES" ]; then
  echo "✗ ABORT: $BASE is not in R2 intact (local ${LOCAL_BYTES}B vs R2 ${R2_BYTES:-0}B)." >&2
  echo "  Upload it first. A dump that exists in exactly one place is not a backup." >&2
  exit 1
fi
echo "        ✓ $BASE present in R2, ${R2_BYTES} bytes, matches local"

# ---- both gates green: prune ------------------------------------------------------
DOOMED="$(ls -1t "$BK"/consensus-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)))"
if [ -z "$DOOMED" ]; then
  echo "nothing to prune (≤ $KEEP dumps on disk)"
  exit 0
fi

echo
echo "would delete $(echo "$DOOMED" | wc -l | tr -d ' ') dump(s), keeping the newest $KEEP:"
echo "$DOOMED" | sed 's/^/  - /'
if [ "$DRY" = 1 ]; then
  echo
  echo "DRY RUN. Re-run with --apply to actually delete."
  exit 0
fi
echo "$DOOMED" | xargs rm -f
echo "✓ pruned. free=$(df -m /System/Volumes/Data | awk 'NR==2{print $4}')MB"
