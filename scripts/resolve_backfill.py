#!/usr/bin/env python3
"""
RESOLVE-BACKFILL — repair the starved `trader_fills` resolution for a bounded market family.

WHY THIS EXISTS (the defect, evidenced 2026-07-12):
`Portfolio::trader_fill_unresolved_conditions` selects the unresolved-condition work queue with
    SELECT condition_id FROM trader_fills WHERE resolved=FALSE AND side='BUY'
      AND ts < NOW()-6h GROUP BY condition_id ORDER BY MIN(ts) LIMIT 200
— a strict oldest-first FIFO with a per-cycle cap. The head of that FIFO is occupied by markets that
**can never resolve**: delisted 2022 World Cup markets and, decisively, long-dated OPEN markets
(`will-*-win-the-2028-*-presidential-nomination`) that do not settle for YEARS. A condition that fails
to resolve stays `resolved=FALSE`, so it returns to the head of the queue on the very next cycle,
forever. Measured: **all 200/200 budget slots go to conditions older than 2026-06-01; the newest
condition the resolver ever reaches is 2026-04-12.** It has never once touched a July market.

Consequence: recent `trader_fills` resolution is 100% starved. The only reason ANY recent weather
resolved is the *separate* consensus-signal path, and `_blind` stopped covering weather after 07-06 —
which is why weather resolution falls off a cliff (07-06: 75% -> 07-08: 0.9%). This is a CAPTURE
DEFECT, not capture lag: it does not self-heal, so the "second disjoint week" that every frozen weather
gate requires (>=2 disjoint weeks + LODO-by-week) could never arrive.

This script drains that backlog for a bounded slug family, mirroring the Rust resolution convention
EXACTLY (`housekeeping.rs` step 2 + `Portfolio::resolve_trader_fills`):
  - fetch GET https://clob.polymarket.com/markets/{condition_id}
  - resolve ONLY if `closed` AND some token has `winner=true`  (winner_index = that token's position)
  - a closed market with NO winner token (void/refund) is SKIPPED — we do not charge every BUY a loss
  - UPDATE trader_fills SET resolved, outcome_won=(outcome_index=winner), advantage (BUY only), resolved_at
It writes the same rows the daemon would have written, nothing more. It is a repair, not a new pipeline;
`common/src/storage/consensus.rs` carries the durable fix (a recency lane) so the queue cannot re-starve.

Bounded by construction: --family (slug regex), --max-conditions, --since. Read-only except the
resolution accrual write. Self-test: ./resolve_backfill.py --selftest
"""

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import urllib.error
import urllib.request

CLOB = "https://clob.polymarket.com/markets/"
# The CLOB rejects urllib's default User-Agent; the Rust client sends a normal one.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) polymarket-bot/resolve-backfill"
PSQL = ["docker", "exec", "-i", "polymarket-bot-postgres-1", "psql", "-U", "bot", "-d", "polymarket"]


def psql(sql, quiet=False):
    """Run SQL, return list of column-lists (tab-separated, tuples-only)."""
    r = subprocess.run(
        PSQL + ["-At", "-F", "\t", "-c", sql], capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        if not quiet:
            print(r.stderr, file=sys.stderr)
        raise RuntimeError(f"psql failed: {r.stderr[:200]}")
    return [ln.split("\t") for ln in r.stdout.strip().splitlines() if ln]


def sql_lit(s):
    """Single-quote a SQL string literal (defensive: these come from argv, not the DB)."""
    return "'" + s.replace("'", "''") + "'"


def fetch_market(cond, retries=3):
    """CLOB market for a condition_id. Returns dict or None (network/parse failure)."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(CLOB + cond, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # unknown to the CLOB — nothing we can do, don't retry
            time.sleep(0.5 * (attempt + 1))
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None


def winner_index(market):
    """Mirror housekeeping.rs EXACTLY: resolvable iff closed AND a token has winner=true.

    Returns the winning token's POSITION (outcome_index), or None if the market is open, void
    (closed with no winner token — refund), or malformed. Never guesses.
    """
    if not market or not market.get("closed"):
        return None
    for i, t in enumerate(market.get("tokens") or []):
        if t.get("winner"):
            return i
    return None  # void / refund — SKIP, do not charge BUYs a loss


def resolve_batch(conds, winner):
    """The accrual write — identical semantics to `Portfolio::resolve_trader_fills`, but applied to
    every condition sharing a `winner` index in ONE statement (per-condition round trips through
    `docker exec psql` are ~1000x the cost of the UPDATE itself). Batched by winner index, so the SET
    clause stays literally the Rust one."""
    if not conds:
        return 0
    ids = ",".join(sql_lit(c) for c in conds)
    rows = psql(
        f"""
        WITH upd AS (
          UPDATE trader_fills SET
            resolved    = TRUE,
            outcome_won = (outcome_index = {winner}),
            advantage   = CASE WHEN side = 'BUY'
                               THEN ((outcome_index = {winner})::int)::double precision - price
                               ELSE NULL END,
            resolved_at = NOW()
          WHERE condition_id IN ({ids}) AND resolved = FALSE
          RETURNING 1)
        SELECT count(*) FROM upd;
        """
    )
    return int(rows[0][0]) if rows else 0


def backlog(family, since, cap):
    """Unresolved conditions in the family, newest-first (the starved end of the FIFO)."""
    rows = psql(
        f"""
        SELECT condition_id, MIN(ts)::date FROM trader_fills
        WHERE resolved = FALSE AND side = 'BUY' AND slug ~ {sql_lit(family)}
          AND ts >= {sql_lit(since)} AND ts < NOW() - interval '6 hours'
        GROUP BY condition_id ORDER BY MIN(ts) DESC LIMIT {int(cap)};
        """
    )
    return [(r[0], r[1]) for r in rows]


def selftest():
    """Pure-logic checks on the resolution convention — no DB, no network."""
    # closed + winner at index 1 -> 1
    assert winner_index({"closed": True, "tokens": [{"winner": False}, {"winner": True}]}) == 1
    # closed + winner at index 0 -> 0 (must not be confused with "no winner")
    assert winner_index({"closed": True, "tokens": [{"winner": True}, {"winner": False}]}) == 0
    # OPEN market -> None (the 2028-nomination case that head-of-line-blocks the live FIFO)
    assert winner_index({"closed": False, "tokens": [{"winner": True}]}) is None
    # closed, NO winner token (void/refund) -> None: must SKIP, never charge BUYs a loss
    assert winner_index({"closed": True, "tokens": [{"winner": False}, {"winner": False}]}) is None
    # degenerate inputs
    assert winner_index({"closed": True, "tokens": []}) is None
    assert winner_index(None) is None
    assert winner_index({}) is None
    # multi-outcome (>2 tokens) picks the right position
    assert (
        winner_index(
            {"closed": True, "tokens": [{"winner": False}, {"winner": False}, {"winner": True}]}
        )
        == 2
    )
    # SQL literal quoting is injection-safe
    assert sql_lit("a'b") == "'a''b'"
    print("resolve_backfill selftest: OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="temperature", help="slug regex (bounds the repair)")
    ap.add_argument("--since", default="2026-07-01")
    ap.add_argument("--max-conditions", type=int, default=6000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    conds = backlog(a.family, a.since, a.max_conditions)
    print(f"backlog: {len(conds)} unresolved conditions  family=~{a.family}  since={a.since}")
    if not conds:
        return

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        markets = list(ex.map(lambda c: fetch_market(c[0]), conds))

    by_winner = defaultdict(list)  # winner_index -> [condition_id]
    skipped_open = skipped_void = failed = 0
    for (cond, _day), mkt in zip(conds, markets):
        if mkt is None:
            failed += 1
            continue
        w = winner_index(mkt)
        if w is None:
            if mkt.get("closed"):
                skipped_void += 1  # void/refund — correctly left unresolved
            else:
                skipped_open += 1  # genuinely still open
            continue
        by_winner[w].append(cond)

    conds_resolved = sum(len(v) for v in by_winner.values())
    fills_resolved = 0
    if not a.dry_run:
        for w, cs in sorted(by_winner.items()):
            for i in range(0, len(cs), 500):  # keep statement size sane
                fills_resolved += resolve_batch(cs[i : i + 500], w)

    print(
        f"conditions_resolved={conds_resolved}  fills_resolved={fills_resolved}  "
        f"still_open={skipped_open}  void_skipped={skipped_void}  fetch_failed={failed}  "
        f"({time.time() - t0:.0f}s){'  [DRY RUN]' if a.dry_run else ''}"
    )


if __name__ == "__main__":
    main()
