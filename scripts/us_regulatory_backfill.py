#!/usr/bin/env python3
"""US-VENUE REGULATORY BACKFILL — the durable, no-account history spine. READ-ONLY.

Two CFTC-DCM public reports on polymarketexchange.com (robots.txt = Allow: /), updated ~6PM ET:

  Daily Market Report  → Postgres us_daily_market_report (migration 044)
      Small, structured EOD fundamentals: OI, volume, price ranges, SETTLEMENT price.
      257 files back to 2025-10-30. This is the historical ground-truth store.

  Time & Sales tape    → cold parquet archive (NOT Postgres)
      ~1.9M anonymized prints/day, ~5.4GB total. Cold by design (hot/cold split); the tape's
      aggregates already live in the DMR, so nothing is lost by keeping it cold. Written as
      one parquet per business date under $US_ARCHIVE_DIR/us_time_sales/.

Both loaders are IDEMPOTENT (skip business-dates already present) and INCREMENTAL (--daily does
just the newest missing days). A regulatory surface can't be silently removed, so this feed is
the most reliable rung we have.

Usage:
    python3 scripts/us_regulatory_backfill.py --dmr                 # full DMR backfill → PG
    python3 scripts/us_regulatory_backfill.py --tape --max-days 3   # newest 3 T&S days → parquet
    python3 scripts/us_regulatory_backfill.py --daily              # incremental: newest DMR + T&S
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
import urllib.request

import psycopg2
from psycopg2.extras import execute_values

BASE = "https://www.polymarketexchange.com/files"
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
ARCHIVE_DIR = os.path.expanduser(os.environ.get("US_ARCHIVE_DIR", "~/polymarket-archive"))
UA = "polymarket-bot-research/1.0 (KYC customer; tue.w.pham@gmail.com)"
_MIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "migrations", "044_us_daily_market_report.sql")


def _get(url, tries=4, binary=False):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read() if binary else r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(0.8 * (i + 1))


def manifest(kind):
    import json
    d = json.loads(_get(f"{BASE}/{kind}/manifest.json"))
    return sorted(d.get("files", []), key=lambda x: x["filename"])


def ensure_schema(con):
    with open(_MIG) as f:
        con.cursor().execute(f.read())
    con.commit()


def _bd(fn):  # 'YYYYMMDD-...csv' → 'YYYY-MM-DD'
    d = fn[:8]
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def _f(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _d(v):  # date-ish text → 'YYYY-MM-DD' or None
    v = (v or "").strip()
    return v[:10] if len(v) >= 10 and v[4] == "-" else None


_DMR_COLS = ["business_date", "symbol", "report_id", "maturity_date", "maturity_time",
             "strike_price", "description", "open_interest", "trade_volume", "block_volume",
             "efp_volume", "efr_volume", "threshold_volume", "other_volume",
             "low_bid_price", "high_bid_price", "low_offer_price", "high_offer_price",
             "low_trade_price", "high_trade_price", "settlement_price"]


def load_dmr(con, files, max_days=None):
    cur = con.cursor()
    cur.execute("SELECT DISTINCT business_date::text FROM us_daily_market_report")
    have = {r[0] for r in cur.fetchall()}
    todo = [f for f in files if _bd(f["filename"]) not in have]
    if max_days:
        todo = todo[-max_days:]
    print(f"DMR: {len(files)} published, {len(have)} loaded, {len(todo)} to fetch", flush=True)
    total = 0
    for f in todo:
        bd = _bd(f["filename"])
        try:
            text = _get(f"{BASE}/daily-market-report/{f['filename']}")
        except Exception as e:
            print(f"  {bd}: fetch failed ({type(e).__name__}) — skip", flush=True)
            continue
        rows = []
        for r in csv.DictReader(io.StringIO(text)):
            rows.append((
                r.get("Business Date", bd)[:10] or bd, r["Symbol"], r.get("Report ID"),
                _d(r.get("Maturity Date")), r.get("Maturity Time"), _f(r.get("Strike Price")),
                r.get("Description"), _f(r.get("Open Interest")), _f(r.get("Trade Volume")),
                _f(r.get("Block Volume")), _f(r.get("Exchange for Physical Volume")),
                _f(r.get("Exchange for Risk Volume")), _f(r.get("Threshold Volume")),
                _f(r.get("Other Volume")), _f(r.get("Low Bid Price")), _f(r.get("High Bid Price")),
                _f(r.get("Low Offer Price")), _f(r.get("High Offer Price")),
                _f(r.get("Low Trade Price")), _f(r.get("High Trade Price")),
                _f(r.get("Settlement Price"))))
        if rows:
            execute_values(cur,
                           f"INSERT INTO us_daily_market_report ({','.join(_DMR_COLS)}) VALUES %s "
                           "ON CONFLICT (business_date, symbol) DO NOTHING", rows)
            con.commit()
            total += len(rows)
        print(f"  {bd}: {len(rows)} contracts", flush=True)
    print(f"DMR done: +{total} rows", flush=True)


def load_tape_cold(files, max_days=None):
    """T&S → parquet in the cold archive. Idempotent by presence of the output file."""
    try:
        import pyarrow as pa
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq
    except ImportError:
        sys.exit("us_regulatory_backfill --tape: pyarrow required")
    outdir = os.path.join(ARCHIVE_DIR, "us_time_sales")
    os.makedirs(outdir, exist_ok=True)
    todo = [f for f in files
            if not os.path.exists(os.path.join(outdir, _bd(f["filename"]) + ".parquet"))]
    if max_days:
        todo = todo[-max_days:]
    print(f"T&S: {len(files)} published, {len(todo)} to archive → {outdir}", flush=True)
    for f in todo:
        bd = _bd(f["filename"])
        out = os.path.join(outdir, bd + ".parquet")
        try:
            raw = _get(f"{BASE}/time-and-sales/{f['filename']}", binary=True)
            tbl = pacsv.read_csv(io.BytesIO(raw))
            pq.write_table(tbl, out, compression="zstd")
            print(f"  {bd}: {tbl.num_rows:,} prints → {os.path.getsize(out)/1e6:.1f}MB parquet",
                  flush=True)
        except Exception as e:
            print(f"  {bd}: failed ({type(e).__name__}: {str(e)[:80]}) — skip", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dmr", action="store_true", help="backfill Daily Market Report → Postgres")
    ap.add_argument("--tape", action="store_true", help="archive Time & Sales → cold parquet")
    ap.add_argument("--daily", action="store_true", help="incremental: newest DMR + T&S day")
    ap.add_argument("--max-days", type=int, default=None, help="cap days (newest N)")
    a = ap.parse_args()
    if not (a.dmr or a.tape or a.daily):
        ap.error("choose --dmr, --tape, or --daily")
    con = psycopg2.connect(PG_DSN)
    ensure_schema(con)
    if a.dmr or a.daily:
        load_dmr(con, manifest("daily-market-report"), max_days=1 if a.daily else a.max_days)
    if a.tape or a.daily:
        load_tape_cold(manifest("time-and-sales"), max_days=1 if a.daily else a.max_days)
    con.close()


if __name__ == "__main__":
    main()
