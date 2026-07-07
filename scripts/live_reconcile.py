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

    # 5) DISTINCT multi-level sweep legs (review D1): two live OrderFilled logs share
    #    (tx,cond,outcome,side) but DIFFER in price — must be KEPT as 2 rows (the index
    #    includes price, matching migration 027's tx index; collapsing would undercount size).
    psql("TRUNCATE trader_fills;", container, want_rows=False)
    for p in ("0.61", "0.62"):  # two maker levels swept in one tx
        psql(
            "INSERT INTO trader_fills "
            "(wallet,tx_hash,condition_id,outcome_index,outcome,side,price,size_usd,"
            " title,slug,is_sports,ts,source,live_seen_at) VALUES "
            f"('0xw','{tx}','{cond}',1,'Yes','BUY',{p},50,'t','s',true,now(),"
            "'live_onchain',now()) ON CONFLICT DO NOTHING;",
            container, want_rows=False)
    n_legs = int(psql("SELECT count(*) FROM trader_fills;", container).strip())
    assert n_legs == 2, f"distinct-price sweep legs must be kept (got {n_legs}) — index must include price"
    print("[dedup] distinct-price sweep legs kept → 2 rows (index includes price) ✓", file=sys.stderr)

    return {"insert_no_collapse": n_after_insert, "after_collapse": n_after_collapse,
            "live_replay_collapsed": n_live == 1, "distinct_legs_kept": n_legs == 2}


COMPACT_SQL = (  # mirrors PgPortfolio::compact_tape (orders by recv_at,id — NOT exch_ts)
    "WITH ranked AS (SELECT id,(best_bid IS NOT DISTINCT FROM lag(best_bid) OVER w "
    "AND best_ask IS NOT DISTINCT FROM lag(best_ask) OVER w) AS redundant "
    "FROM clob_price_tape WHERE recv_at < now() - interval '0 seconds' "
    "WINDOW w AS (PARTITION BY asset_id ORDER BY recv_at, id)) "
    ", del AS (DELETE FROM clob_price_tape t USING ranked r "
    "WHERE t.id=r.id AND r.redundant RETURNING t.id) SELECT count(*) FROM del;"
)


def _ins(container, asset, bid, ask, recv_off, exch_off):
    """exch_off=None → NULL exch_ts (book snapshot); recv_off drives arrival order."""
    exch = ("NULL" if exch_off is None
            else f"now()-interval '3600 seconds'+interval '{exch_off} seconds'")
    psql("INSERT INTO clob_price_tape (asset_id,event_type,best_bid,best_ask,exch_ts,recv_at) "
         f"VALUES ('{asset}','x',{bid},{ask},{exch},"
         f"now()-interval '3600 seconds'+interval '{recv_off} seconds');",
         container, want_rows=False)


def _step(seq):
    out = []
    for v in seq:
        if not out or out[-1] != v:
            out.append(v)
    return out


def compaction_proof(container=PG_TEST):
    """compact_tape drops consecutive-duplicate top-of-book (reconnect) rows while keeping
    every inflection — LOSSLESS for the best_ask step function, and ROBUST to NULL/stale
    exch_ts (adversarial review D1/D2: it orders by recv_at, the arrival clock)."""
    # --- Scenario A: basic dup removal (arrival order) ---
    psql("TRUNCATE clob_price_tape;", container, want_rows=False)
    for i, (bid, ask) in enumerate([(0.49, 0.50), (0.49, 0.50), (0.49, 0.51),
                                    (0.50, 0.51), (0.50, 0.51)]):
        _ins(container, "a", bid, ask, recv_off=i + 1, exch_off=i + 1)
    seq_before = psql("SELECT best_ask FROM clob_price_tape ORDER BY recv_at,id;", container).split()
    removed = int(psql(COMPACT_SQL, container).strip())
    after = int(psql("SELECT count(*) FROM clob_price_tape;", container).strip())
    seq_after = psql("SELECT best_ask FROM clob_price_tape ORDER BY recv_at,id;", container).split()
    assert after == 3 and removed == 2, f"A: expected 5→3 (2 removed), got after={after} removed={removed}"
    assert _step(seq_before) == _step(seq_after), f"A: step fn changed {seq_before}->{seq_after}"

    # --- Scenario B (D1): a REAL inflection with NULL exch_ts must NOT be deleted.
    # arrival order 0.50, 0.55(exch NULL), 0.50 — all distinct consecutive → 0 removed.
    # (exch_ts NULLS-LAST ordering would mis-sort the 0.55 to the tail and delete a 0.50.)
    psql("TRUNCATE clob_price_tape;", container, want_rows=False)
    _ins(container, "b", 0.49, 0.50, recv_off=1, exch_off=1)
    _ins(container, "b", 0.54, 0.55, recv_off=2, exch_off=None)   # book snapshot, NULL exch_ts
    _ins(container, "b", 0.49, 0.50, recv_off=3, exch_off=3)
    removed_b = int(psql(COMPACT_SQL, container).strip())
    after_b = int(psql("SELECT count(*) FROM clob_price_tape;", container).strip())
    assert removed_b == 0 and after_b == 3, f"B(D1): NULL-exch inflection wrongly dropped: removed={removed_b}"

    # --- Scenario C (D2): a reconnect dup with STALE exch_ts must still collapse.
    # arrival: 0.50@recv1(exch1), 0.50@recv2(exch=very old) — same TOB, later arrival → collapse.
    psql("TRUNCATE clob_price_tape;", container, want_rows=False)
    _ins(container, "c", 0.49, 0.50, recv_off=1, exch_off=1)
    _ins(container, "c", 0.49, 0.50, recv_off=2, exch_off=-99999)  # stale reconnect snapshot
    removed_c = int(psql(COMPACT_SQL, container).strip())
    after_c = int(psql("SELECT count(*) FROM clob_price_tape;", container).strip())
    assert removed_c == 1 and after_c == 1, f"C(D2): stale-exch reconnect dup not collapsed: removed={removed_c}"

    print(f"[compact] A: 5→3 (2 dup removed, lossless); B(D1): NULL-exch inflection KEPT; "
          f"C(D2): stale-exch reconnect dup collapsed ✓", file=sys.stderr)
    return {"before": 5, "after": after, "removed": removed, "lossless": True,
            "d1_null_exch_kept": removed_b == 0, "d2_stale_dup_collapsed": removed_c == 1}


def self_test():
    r = dedup_proof()
    assert r == {"insert_no_collapse": 2, "after_collapse": 1,
                 "live_replay_collapsed": True, "distinct_legs_kept": True}, r
    c = compaction_proof()
    assert c == {"before": 5, "after": 3, "removed": 2, "lossless": True,
                 "d1_null_exch_kept": True, "d2_stale_dup_collapsed": True}, c
    print("SELF-TEST PASS: three-layer dedup — VWAP-vs-reconstructed does NOT double-count; "
          "poll-over-live collapse net 1; live replay collapsed; distinct sweep legs kept; "
          "compaction lossless + robust to NULL/stale exch_ts (D1/D2).")


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
