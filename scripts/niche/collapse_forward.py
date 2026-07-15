#!/usr/bin/env python3
"""
FORWARD PAPER HARNESS — the pre-registered collapse-model test, running on LIVE US prices.

This is the machine that resolves the sharp open question: is the model's selection edge enough to
overcome a possibly-overpriced US favourite baseline, NET of everything, on the book we actually
trade? Retrospective US data can't answer it (settlement artifacts). This can, because it accrues
CLEAN data — we control the entry timestamp (the real ask we'd pay) and settle only when a market
truly matures, so none of the T&S winner-drop / bad-tick artifacts occur.

Frozen model: model/collapse_model_frozen.pkl (sha256[:16]=ff23718d558ff0a1). NOT retrained.
Universe: the pre-registration's — {soccer,tennis,esports,ufc}, standard game markets only (exotic
submarkets excluded), from the live us_mid_tape feed. Gate: EV = pwin - ask - fee(ask) > 0 (stored;
EV>0.01/0.03 evaluated downstream). One signal per market (first qualifying >=0.80 crossing).

SUBCOMMANDS (all READ-ONLY except the append-only collapse_paper_signals table):
  --scan     detect new qualifying markets in the current live snapshot, append signals
  --settle   resolve matured signals (state EXPIRED/CLOSED, or terminal price), fill net
  --report   print the accruing paper P&L (event-clustered), by sport, vs the pre-reg gate

  psql pinned ON_ERROR_STOP=1 + parallel workers off (the DB serves the live bot).

  ./collapse_forward.py --self-test
  ./collapse_forward.py --scan && ./collapse_forward.py --settle && ./collapse_forward.py --report
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "-q"]
GUARD = ("SET work_mem='64MB'; SET statement_timeout='300s'; "
         "SET max_parallel_workers_per_gather=0; ")
MODEL = "model/collapse_model_frozen.pkl"
META = "model/collapse_model_frozen.meta.json"
BAND_LO = 0.80
THETA_US = 0.06
SPORTS = ("soccer", "mlb", "tennis", "esports", "nba", "nhl", "ufc")
NICHE_IDX = {n: i for i, n in enumerate(SPORTS)}
TRADEABLE = ("soccer", "tennis", "esports", "ufc")
FEATS = ["p", "persistence", "n_prints", "elapsed", "max_p", "dd_from_max", "vol",
         "n_dips", "n_flips", "drift_15m", "drift_1h", "staleness", "mean_p_1h", "niche"]
EXOTIC = re.compile(r"astatc|exact|corn|cor-|stat|gte|lte|-g-|neg-|pt5|total|over|under|"
                    r"handicap|nrfi|assist|halftime|-set-|first-set|-map-|-team-total|-tt-|scorer")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def fee_us(p):
    return THETA_US * p * (1 - p)


def grade_niche(sym):
    s = sym.lower()
    if re.search(r"fwc|fifwc|asc|epl|ucl|mls|lliga|seri|bund", s):
        return "soccer"
    if re.search(r"atp|wta", s):
        return "tennis"
    if re.search(r"cs2|dota|lol|val", s):
        return "esports"
    if "ufc" in s:
        return "ufc"
    return None


def is_exotic(sym):
    return bool(EXOTIC.search(sym.lower()))


def event_key(sym):
    m = DATE_RE.search(sym)
    return sym[:m.end()] if m else sym


def sql(q, fetch=True):
    o = subprocess.run(PG + (["--csv"] if fetch else []), input=GUARD + q,
                       capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1200])
    if not fetch:
        return None
    import csv
    import io
    return list(csv.DictReader(io.StringIO(o.stdout)))


def featurize(path, i, niche):
    """path=[(epoch,price)] ascending; uses path[:i+1] only. Same 14 features as the frozen model."""
    t, p = path[i]
    hist = path[:i + 1]
    ps = np.array([x[1] for x in hist], float)
    ts = np.array([x[0] for x in hist], float)
    start = None
    for (tt, pp) in hist:
        start = (tt if start is None else start) if pp >= BAND_LO else None
    persistence = 0.0 if start is None else t - start
    max_p = float(ps.max())
    recent = ps[-30:]
    vol = float(recent.std()) if len(recent) > 2 else 0.0
    n_dips = int(np.sum((ps[:-1] >= BAND_LO) & (ps[1:] < BAND_LO))) if len(ps) > 1 else 0
    n_flips = int(np.sum((ps[:-1] >= .5) != (ps[1:] >= .5))) if len(ps) > 1 else 0

    def px_ago(sec):
        j = min(max(np.searchsorted(ts, t - sec), 0), len(ps) - 1)
        return float(ps[j])

    m1h = ts >= (t - 3600)
    return [p, persistence, float(len(hist)), float(t - ts[0]), max_p, max_p - p, vol,
            float(n_dips), float(n_flips), p - px_ago(900), p - px_ago(3600),
            float(t - ts[-2]) if len(ts) > 1 else 0.0,
            float(ps[m1h].mean()) if m1h.any() else p, float(NICHE_IDX.get(niche, -1))]


def self_test():
    assert grade_niche("asc-fwc-fra-swe-2026-06-30-x") == "soccer"
    assert grade_niche("atp-a-b-2026-07-11") == "tennis" and grade_niche("xyz") is None
    assert is_exotic("mlb-a-b-2026-07-01-nrfi") and not is_exotic("atp-a-b-2026-07-11")
    assert event_key("cs2-a-b-2026-07-08-x") == "cs2-a-b-2026-07-08"
    # no lookahead
    path = [(0, .5), (100, .85), (200, .86), (300, .10)]
    assert featurize(path, 2, "soccer") == featurize(path[:3] + [(300, .99)], 2, "soccer")
    assert abs(fee_us(.9) - .06 * .09) < 1e-12
    assert NICHE_IDX["soccer"] == 0 and NICHE_IDX["esports"] == 3
    print("self-test OK  (niche/exotic gates, no-lookahead, frozen niche vocab, US fee)")
    return 0


# ---------------------------------------------------------------------------- scan
def scan():
    import pickle
    clf = pickle.load(open(MODEL, "rb"))
    sha = json.load(open(META))["sha256_16"]

    have = {r["us_slug"] for r in sql("SELECT us_slug FROM collapse_paper_signals;")}
    # candidate slugs: currently OPEN, mid >=0.80, tradeable sport, standard market, not yet recorded
    cands = sql("""
        SELECT DISTINCT us_slug FROM us_mid_tape
        WHERE state='MARKET_STATE_OPEN' AND mid >= 0.80;""")
    cands = [r["us_slug"] for r in cands
             if r["us_slug"] not in have
             and grade_niche(r["us_slug"]) in TRADEABLE and not is_exotic(r["us_slug"])]
    if not cands:
        print("scan: no new qualifying markets")
        return
    print(f"scan: {len(cands)} new candidate markets")

    inserted = clean = 0
    for i in range(0, len(cands), 200):
        chunk = cands[i:i + 200]
        lit = ",".join("'" + s.replace("'", "''") + "'" for s in chunk)
        rows = sql(f"""
            SELECT us_slug, EXTRACT(EPOCH FROM recv_at) t, mid, best_ask
            FROM us_mid_tape WHERE us_slug IN ({lit}) AND mid IS NOT NULL
            ORDER BY us_slug, recv_at;""")
        paths = defaultdict(list)
        asks = defaultdict(list)
        for r in rows:
            paths[r["us_slug"]].append((float(r["t"]), float(r["mid"])))
            asks[r["us_slug"]].append((float(r["t"]),
                                       float(r["best_ask"]) if r["best_ask"] else float(r["mid"])))
        for slug, path in paths.items():
            if len(path) < 5:
                continue
            # first index where mid crosses >=0.80 (the one-DP entry)
            j = next((k for k, (t, p) in enumerate(path) if p >= BAND_LO), None)
            if j is None:
                continue
            # CLEAN forward-caught iff we witnessed the market BELOW 0.80 before the crossing (j>0).
            # If its very first observed snapshot is already >=0.80, the crossing predates our
            # observation => warm-up (truncated feature path), excluded from the pre-reg gate.
            warmup = (j == 0)
            niche = grade_niche(slug)
            feats = featurize(path, j, niche)
            pwin = float(clf.predict_proba(np.array([feats], float))[:, 1][0])
            ask = asks[slug][j][1] if j < len(asks[slug]) else path[j][1]
            ask = max(ask, path[j][1])                 # ask >= mid
            ev = pwin - ask - fee_us(ask)
            if ev <= 0.0:                               # gate: only record EV>0 (store for thresholds)
                continue
            sig_ts = path[j][0]
            fj = json.dumps(dict(zip(FEATS, feats)))
            # append-only; ON CONFLICT DO NOTHING keeps it idempotent (one per slug)
            sql(f"""INSERT INTO collapse_paper_signals
                    (us_slug,niche,event_key,signal_ts,entry_ask,entry_mid,model_pwin,ev,
                     features,model_sha,warmup)
                    VALUES ('{slug.replace("'","''")}','{niche}','{event_key(slug)}',
                            to_timestamp({sig_ts}),{ask},{path[j][1]},{pwin},{ev},
                            '{fj.replace("'","''")}'::jsonb,'{sha}',{str(warmup).upper()})
                    ON CONFLICT (us_slug) DO NOTHING;""", fetch=False)
            inserted += 1
            if not warmup:
                clean += 1
    print(f"scan: recorded {inserted} new signals ({clean} clean forward-caught, "
          f"{inserted-clean} warm-up)")


# ---------------------------------------------------------------------------- settle
def settle():
    un = sql("SELECT us_slug, entry_ask FROM collapse_paper_signals WHERE NOT settled;")
    if not un:
        print("settle: nothing pending")
        return
    n = 0
    for r in un:
        slug = r["us_slug"]
        lit = "'" + slug.replace("'", "''") + "'"
        st = sql(f"""SELECT state, last_trade_px, mid, EXTRACT(EPOCH FROM MAX(recv_at)) t
                     FROM us_mid_tape WHERE us_slug={lit}
                     GROUP BY state,last_trade_px,mid
                     ORDER BY MAX(recv_at) DESC LIMIT 1;""")
        if not st:
            continue
        s = st[0]
        # a market is settled only when it has reached a TERMINAL state
        if s["state"] not in ("MARKET_STATE_EXPIRED", "MARKET_STATE_CLOSED"):
            continue
        px = float(s["last_trade_px"]) if s["last_trade_px"] else float(s["mid"] or 0.5)
        outcome = 1.0 if px >= 0.5 else 0.0
        entry = float(r["entry_ask"])
        net = outcome - entry - fee_us(entry)
        sql(f"""UPDATE collapse_paper_signals
                SET settled=TRUE, outcome={outcome}, settle_ts=to_timestamp({float(s['t'])}),
                    settle_src='state_{s["state"].split("_")[-1].lower()}', net={net}
                WHERE us_slug={lit};""", fetch=False)
        n += 1
    print(f"settle: resolved {n} markets")


# ---------------------------------------------------------------------------- report
def report():
    rows = sql("""SELECT niche, event_key, entry_ask, ev, outcome, net, settled, warmup
                  FROM collapse_paper_signals;""")
    tot = len(rows)
    clean = [r for r in rows if r["warmup"] == "f"]
    warm = [r for r in rows if r["warmup"] == "t"]
    settled = [r for r in clean if r["settled"] == "t"]
    print(f"FORWARD PAPER LEDGER — {tot} signals: {len(clean)} CLEAN forward-caught "
          f"({len(settled)} settled), {len(warm)} warm-up (excluded from the gate)")
    if warm:
        ws = [r for r in warm if r["settled"] == "t"]
        if ws:
            wr = np.mean([float(r["net"]) / float(r["entry_ask"]) for r in ws])
            print(f"  [warm-up, NOT the gate — feed-history-limited, late-caught: "
                  f"{wr*100:+.1f}% ROI on {len(ws)} settled]")
    if len(settled) < 1:
        print("  CLEAN forward test: no settled signals yet — the clock is running. Keep --scan on a")
        print("  timer; re-run --report as markets resolve. Gate needs >=60 clean settled events.")
        return

    def boot_roi(rws):
        by = defaultdict(list)
        for r in rws:
            by[r["event_key"]].append((float(r["net"]), float(r["entry_ask"])))
        cl = list(by)
        if len(cl) < 5:
            return None
        roi = np.array([sum(x[0] for x in by[c]) / sum(x[1] for x in by[c]) for c in cl])
        rng = np.random.default_rng(20260714)
        bs = roi[rng.integers(0, len(cl), (4000, len(cl)))].mean(1)
        return (float(roi.mean()), float(np.percentile(bs, 2.5)),
                float(np.percentile(bs, 97.5)), float((bs <= 0).mean()), len(cl))

    print(f"\n  {'threshold':>12s} {'ROI/turn':>10s} {'95% CI':>20s} {'p':>7s} {'events':>7s}")
    for thr in (0.00, 0.01, 0.03):
        sub = [r for r in settled if float(r["ev"]) > thr]
        b = boot_roi(sub)
        if b:
            print(f"  EV>{thr:>+8.2f} {b[0]*100:>+9.2f}% "
                  f"[{b[1]*100:+.2f}%,{b[2]*100:+.2f}%] {b[3]:>7.3f} {b[4]:>7,}")
        else:
            print(f"  EV>{thr:>+8.2f}   -- <5 events, underpowered --")
    print("\n  by sport (EV>0.01, settled):")
    for n in TRADEABLE:
        b = boot_roi([r for r in settled if r["niche"] == n and float(r["ev"]) > 0.01])
        if b:
            print(f"    {n:>8s} {b[0]*100:>+7.2f}% [{b[1]*100:+.1f}%,{b[2]*100:+.1f}%] {b[4]} ev")
    print("\n  PRE-REG GATE (PREREG_20260715): ROI LB>0 over >=60 events, point >=+2.0%, "
          "positive in >=2 of {soccer,tennis,esports}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--settle", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if not os.path.exists(MODEL):
        sys.exit(f"frozen model missing: {MODEL}")
    if a.scan:
        scan()
    if a.settle:
        settle()
    if a.report:
        report()
    if not (a.scan or a.settle or a.report):
        ap.print_help()


if __name__ == "__main__":
    main()
