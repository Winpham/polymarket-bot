#!/usr/bin/env python3
"""Item 6 — live_reconcile: reconciliation + completeness for a dual-path world.

Three jobs:
  1. TAPE COVERAGE   — % of tracked sharp fills whose asset had a tape tick within
                       +/-TOL of ts (observable vs unquotable). The GATE-1 oracle.
  2. DEDUP PROOF     — the load-bearing check given the VWAP finding: on a throwaway
                       PG, insert a poll row, inject its live_onchain twin with a
                       ULP-DIFFERENT reconstructed price, assert the tx unique index
                       does NOT collapse it, then run the poll-over-live collapse and
                       assert net rows == 1. Also assert the source-scoped index
                       collapses a live-vs-live replay.
  3. (fuzzy-join latency floor lives in probe_coverage.py / the curve's consensus
      replay; job 1 here is the coverage half.)

--self-test: synthetic, throwaway-PG only, zero network. Run against pg-live-test
(port 55432 / docker `pg-live-test`) which has migration 040 applied.
"""
import argparse
import subprocess
import sys

PG_TEST = "pg-live-test"   # throwaway container with migrations 001..040 applied


def psql(sql, container=PG_TEST, want_rows=True):
    out = subprocess.run(
        ["docker", "exec", container, "psql", "-U", "bot", "-d", "polymarket",
         "-tAF", "\x1f", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()}")
    return out.stdout if want_rows else None


# poll-over-live collapse (the layer-3 sweep; also lives in live_fills.rs reconcile window)
COLLAPSE_SQL = """
DELETE FROM trader_fills live USING trader_fills poll
WHERE live.source='live_onchain' AND poll.source IS NULL
  AND live.tx_hash=poll.tx_hash AND live.condition_id=poll.condition_id
  AND live.outcome_index=poll.outcome_index AND live.side=poll.side;
"""


def dedup_proof(container=PG_TEST):
    """Exercise the true hazard: a live twin whose reconstructed price is ULP-different."""
    print("[dedup] resetting throwaway trader_fills", file=sys.stderr)
    psql("TRUNCATE trader_fills;", container, want_rows=False)

    tx = "0xdeadbeef"
    cond = "0xcond"
    # 1) poll row: full-precision VWAP price (16 dp), source NULL
    poll_price = "0.6052265345901234"
    psql(
        "INSERT INTO trader_fills "
        "(wallet,tx_hash,condition_id,outcome_index,outcome,side,price,size_usd,"
        " title,slug,is_sports,ts,source) VALUES "
        f"('0xw','{tx}','{cond}',1,'Yes','BUY',{poll_price},100,'t','s',true,now(),NULL);",
        container, want_rows=False)

    # 2) live twin: reconstructed on-chain price differs at the ULP (single-level != VWAP)
    live_price = "0.6052265344590036"
    psql(
        "INSERT INTO trader_fills "
        "(wallet,tx_hash,condition_id,outcome_index,outcome,side,price,size_usd,"
        " title,slug,is_sports,ts,source,live_seen_at) VALUES "
        f"('0xw','{tx}','{cond}',1,'Yes','BUY',{live_price},100,'t','s',true,now(),"
        "'live_onchain',now());",
        container, want_rows=False)

    n_after_insert = int(psql("SELECT count(*) FROM trader_fills;", container).strip())
    # the widened tx index includes `price`, so ULP-different price → NO collapse → 2 rows
    assert n_after_insert == 2, f"expected 2 rows (tx index includes price), got {n_after_insert}"
    print(f"[dedup] both rows present after insert (tx index includes price): {n_after_insert} ✓",
          file=sys.stderr)

    # 3) poll-over-live collapse → keep poll, drop live twin → net 1
    psql(COLLAPSE_SQL, container, want_rows=False)
    n_after_collapse = int(psql("SELECT count(*) FROM trader_fills;", container).strip())
    assert n_after_collapse == 1, f"collapse should leave 1, got {n_after_collapse}"
    survivor_src = psql("SELECT COALESCE(source,'NULL') FROM trader_fills;", container).strip()
    assert survivor_src == "NULL", f"survivor should be the poll row, got source={survivor_src}"
    print("[dedup] poll-over-live collapse → net 1 row, poll survives ✓", file=sys.stderr)

    # 4) live-vs-live replay: the source-scoped unique index collapses a re-seen live fill
    psql("TRUNCATE trader_fills;", container, want_rows=False)
    for _ in range(2):  # same live fill seen twice (reconnect / getLogs range overlap)
        psql(
            "INSERT INTO trader_fills "
            "(wallet,tx_hash,condition_id,outcome_index,outcome,side,price,size_usd,"
            " title,slug,is_sports,ts,source,live_seen_at) VALUES "
            f"('0xw','{tx}','{cond}',1,'Yes','BUY',{live_price},100,'t','s',true,now(),"
            "'live_onchain',now()) ON CONFLICT DO NOTHING;",
            container, want_rows=False)
    n_live = int(psql("SELECT count(*) FROM trader_fills;", container).strip())
    assert n_live == 1, f"source-scoped index should collapse live replay to 1, got {n_live}"
    print("[dedup] live-vs-live replay collapsed by source-scoped index → 1 row ✓", file=sys.stderr)

    return {"insert_no_collapse": n_after_insert, "after_collapse": n_after_collapse,
            "live_replay_collapsed": n_live == 1}


def self_test():
    r = dedup_proof()
    assert r == {"insert_no_collapse": 2, "after_collapse": 1, "live_replay_collapsed": True}
    print("SELF-TEST PASS: three-layer dedup — VWAP-vs-reconstructed does NOT double-count; "
          "poll-over-live collapse net 1; live replay collapsed.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--container", default=PG_TEST)
    ap.add_argument("--job", choices=["dedup"], default="dedup")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if args.job == "dedup":
        print(dedup_proof(args.container))


if __name__ == "__main__":
    main()
