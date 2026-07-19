#!/bin/bash
# Refresh ~/polymarket-archive/us_markets.parquet SAFELY: fetch to a temp file, validate it, and
# only then swap it in. Keeps one backup.
#
# WHY THIS IS AUTOMATED. The snapshot is the orientation source. When it does not cover a match's
# date, orientation cannot be resolved and the harness reports "no signals qualified" -- which is
# INDISTINGUISHABLE from "no edge". On 2026-07-18 the live snapshot was 5 days stale and contained
# ZERO tennis markets for that day; the forward test would have accrued nothing and looked like a
# clean null. Instrument staleness must never be able to masquerade as a verdict.
#
# Read-only against the venue (public gateway, no auth, no order path).
set -euo pipefail

ARCHIVE="$HOME/polymarket-archive/us_markets.parquet"
TMP="$(mktemp -t us_markets_XXXX).parquet"
REPO="$HOME/polymarket-bot/wt/capture"

cleanup() { rm -f "$TMP"; }
trap cleanup EXIT

echo "[$(date -u +%FT%TZ)] fetching US market universe -> $TMP"
/usr/bin/python3 "$REPO/scripts/us_fetch_markets.py" --out "$TMP"

# VALIDATE BEFORE SWAPPING. A truncated or schema-changed pull must never silently replace a good
# snapshot -- that would substitute one silent failure for another.
/usr/bin/python3 - "$TMP" "$ARCHIVE" <<'PY'
import sys, duckdb
new, old = sys.argv[1], sys.argv[2]
c = duckdb.connect()
n_new = c.execute(f"SELECT count(*) FROM '{new}'").fetchone()[0]
t_new = c.execute(f"SELECT count(*) FROM '{new}' WHERE sportsMarketType='tennis_match_winner'").fetchone()[0]
sc_new = [r[0] for r in c.execute(f"DESCRIBE SELECT * FROM '{new}'").fetchall()]
try:
    n_old = c.execute(f"SELECT count(*) FROM '{old}'").fetchone()[0]
    sc_old = [r[0] for r in c.execute(f"DESCRIBE SELECT * FROM '{old}'").fetchall()]
except Exception:
    n_old, sc_old = 0, sc_new
assert n_new > 50_000, f"pull looks truncated: {n_new} rows"
assert t_new > 500, f"too few tennis markets: {t_new}"
assert sc_new == sc_old, "SCHEMA CHANGED -- refusing to swap; inspect before overwriting"
assert n_new >= n_old * 0.8, f"pull shrank sharply ({n_new} vs {n_old}) -- refusing to swap"
print(f"  validated: {n_new} markets ({t_new} tennis), schema stable")
PY

cp -f "$ARCHIVE" "$ARCHIVE.bak" 2>/dev/null || true
cp -f "$TMP" "$ARCHIVE"
echo "[$(date -u +%FT%TZ)] swapped in new snapshot (previous kept at $ARCHIVE.bak)"
