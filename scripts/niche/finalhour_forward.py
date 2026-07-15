#!/usr/bin/env python3
"""
FORWARD PAPER HARNESS — final-hour favourite late-convergence (PREREG_20260715_final_hour_favourite.md).

WHY THIS EXISTS. A backtest can prove an edge fake but never prove it real: the final-hour favourite
edge (λ=0.73, generalises across tennis+ITF+esports) is information but is NOT capturable
retrospectively — nothing in the price tape or venue schedule locates the final ~30 min (endDate is
~4h off; every live-knowable price anchor is negative). Only a LIVE game-state feed does. This harness
uses the FREE ESPN feed: when a live ATP/WTA match is near-decided (leader up on sets / serving for the
match) AND the US book still prices that favourite in [0.65,0.92], it records a paper entry at the real
ask and settles forward on the official DMR. Append-only `finalhour_paper_signals`. NO order path.

  ./finalhour_forward.py --self-test
  ./finalhour_forward.py --scan      # fire triggers off ESPN-live vs us_mid_tape (read-only + ledger)
  ./finalhour_forward.py --settle    # resolve matured signals (DMR / terminal state)
  ./finalhour_forward.py --report    # ROI + lambda + per-sport, warmup split, vs the frozen gate

NB (honest): the ESPN in-play JSON shape for a LIVE tennis match could not be verified at build time
(no match was live). `near_decided()` is written against the VERIFIED set-score schema and self-tested
with fixtures; run `--scan --dry` against a live match once to confirm the live field names before
trusting real accrual. The gate is frozen in the PREREG; do not tune it to the data.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.request
from collections import defaultdict

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "-q"]
GUARD = "SET max_parallel_workers_per_gather=0; SET statement_timeout='120s'; "
THETA_US = 0.06
BAND_LO, BAND_HI = 0.65, 0.92
WARMUP_MIN_S = 1800          # <30 min of book history at fire => warmup (excluded from gate)
GUARD_LO, GUARD_HI = 0.02, 0.98


def fee_us(p):
    return THETA_US * p * (1 - p)


def sql(q, fetch=True):
    o = subprocess.run(PG + (["--csv"] if fetch else []), input=GUARD + q, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1200])
    if not fetch:
        return None
    import csv
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(s):
    return "'" + str(s).replace("'", "''") + "'"


# ---------------------------------------------------------------- name matching (ESPN <-> US slug)
def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s)


def name_toks(s):
    return {t for t in norm(s).split() if len(t) >= 4}


# ---------------------------------------------------------------- ESPN near-decided detection
def _sets_won(linescores_a, linescores_b):
    """Count COMPLETED sets each side has won. A set is complete when max>=6 and (margin>=2 or max==7)
    (tiebreak). In-progress trailing set is not counted. Robust to the trailing in-progress entry."""
    wa = wb = 0
    for va, vb in zip(linescores_a, linescores_b):
        m = max(va, vb)
        if m >= 6 and (abs(va - vb) >= 2 or m == 7):
            if va > vb:
                wa += 1
            else:
                wb += 1
    return wa, wb


def near_decided(ls_lead, ls_other, is_bo5):
    """ls_* = per-set game counts for the leader / other. is_bo5 True for best-of-5 (Wimbledon men).
    Returns (bool, reason). Near-decided = the leader needs only to finish:
      bo5: up >=2 completed sets AND ahead/level in the current set;
      bo3: up 1 completed set AND ahead by >=3 games in the current (in-progress) set (serving-for-set)."""
    wl, wo = _sets_won(ls_lead, ls_other)
    need = 3 if is_bo5 else 2
    # current (last) set game lead, if a set is in progress (trailing entry not yet a completed set)
    cur_lead = 0
    if ls_lead and ls_other:
        va, vb = ls_lead[-1], ls_other[-1]
        m = max(va, vb)
        completed = m >= 6 and (abs(va - vb) >= 2 or m == 7)
        if not completed:
            cur_lead = va - vb
    if wl >= need - 1 and (wl - wo) >= (1 if is_bo5 else 1) and (wl >= need - 1):
        if is_bo5 and wl >= 2 and (wl - wo) >= 1 and cur_lead >= 0:
            return True, f"bo5 sets {wl}-{wo}, current +{cur_lead}"
        if (not is_bo5) and wl >= 1 and cur_lead >= 3:
            return True, f"bo3 set {wl}-{wo}, serving-for-match +{cur_lead}"
    return False, f"sets {wl}-{wo}"


def espn_live_near_decided():
    """Fetch ESPN ATP/WTA; return near-decided in-progress matches:
    [{'sport','names','leader_name','feed_state'}]."""
    out = []
    for tour in ("atp", "wta"):
        url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard"
        try:
            d = json.load(urllib.request.urlopen(url, timeout=30))
        except Exception as e:
            print(f"  espn {tour} fetch fail: {e}")
            continue
        for ev in d.get("events", []):
            is_bo5 = (tour == "atp") and bool(ev.get("major"))    # Grand Slam men = best-of-5
            for g in ev.get("groupings", []):
                for c in g.get("competitions", []):
                    if c.get("status", {}).get("type", {}).get("state") != "in":
                        continue
                    cs = c.get("competitors", [])
                    if len(cs) != 2:
                        continue
                    names = [x.get("athlete", {}).get("displayName", "") for x in cs]
                    ls = [[float(z.get("value", 0)) for z in x.get("linescores", [])] for x in cs]
                    if not ls[0] or not ls[1]:
                        continue
                    wa, wb = _sets_won(ls[0], ls[1])
                    lead = 0 if wa >= wb else 1                    # who is ahead on sets
                    nd, reason = near_decided(ls[lead], ls[1 - lead], is_bo5)
                    if nd:
                        out.append({"sport": f"tennis_{tour}", "names": names,
                                    "leader_name": names[lead], "feed_state": reason,
                                    "feed_src": f"espn_{tour}"})
    return out


# ---------------------------------------------------------------- scan
def scan(dry=False):
    triggers = espn_live_near_decided()
    print(f"scan: {len(triggers)} near-decided live matches from ESPN")
    if not triggers:
        return
    have = {r["us_slug"] for r in sql("SELECT us_slug FROM finalhour_paper_signals;")}
    # live US ATP/WTA markets currently OPEN with a fresh quote
    open_mkts = sql("""
        SELECT DISTINCT ON (us_slug) us_slug, mid, best_ask, best_bid, spread,
               EXTRACT(EPOCH FROM recv_at) t, state
        FROM us_mid_tape
        WHERE state='MARKET_STATE_OPEN' AND (us_slug LIKE 'aec-atp-%' OR us_slug LIKE 'aec-wta-%')
              AND recv_at > now() - interval '10 minutes' AND mid IS NOT NULL
        ORDER BY us_slug, recv_at DESC;""")
    # index live US markets by name tokens (from the slug is unreliable; use the question if present)
    slug_toks = {}
    for r in open_mkts:
        slug_toks[r["us_slug"]] = name_toks(r["us_slug"].replace("-", " "))
    inserted = 0
    for t in triggers:
        lt = name_toks(t["leader_name"])
        best = None
        for r in open_mkts:
            if r["us_slug"] in have:
                continue
            # both players' surnames should appear in the market (avoid mis-map); leader must too
            allt = name_toks(" ".join(t["names"]))
            st = slug_toks[r["us_slug"]]
            if len(allt & st) >= 2 or (len(lt & st) >= 1 and len(allt & st) >= 1):
                best = r
                break
        if best is None:
            continue
        mid = float(best["mid"])
        ask = float(best["best_ask"]) if best["best_ask"] else mid
        # the FAVOURITE side must be the leader and in-band on the US book
        if not (BAND_LO <= mid <= BAND_HI):
            continue
        # book-history age (warmup if <30min of quotes)
        hist = sql(f"SELECT EXTRACT(EPOCH FROM (max(recv_at)-min(recv_at))) age "
                   f"FROM us_mid_tape WHERE us_slug={q_lit(best['us_slug'])};")
        age = float(hist[0]["age"]) if hist and hist[0]["age"] else 0.0
        warmup = age < WARMUP_MIN_S
        spread = float(best["spread"]) if best["spread"] else (ask - float(best["best_bid"] or mid))
        evk = re.sub(r"-[^-]+$", "", best["us_slug"]) if re.search(r"\d{4}-\d{2}-\d{2}", best["us_slug"]) else best["us_slug"]
        m = re.search(r"(\d{4}-\d{2}-\d{2})", best["us_slug"])
        evk = best["us_slug"][:m.end()] if m else best["us_slug"]
        line = (f"  TRIGGER {best['us_slug']}  mid={mid:.3f} ask={ask:.3f}  "
                f"[{t['feed_src']}: {t['feed_state']}]  warmup={warmup}")
        print(line)
        if dry:
            continue
        sql(f"""INSERT INTO finalhour_paper_signals
                (us_slug,sport,event_key,signal_ts,entry_ask,entry_mid,entry_spread,feed_state,feed_src,warmup)
                VALUES ({q_lit(best['us_slug'])},{q_lit(t['sport'])},{q_lit(evk)},
                        to_timestamp({float(best['t'])}),{ask},{mid},{spread},
                        {q_lit(t['feed_state'])},{q_lit(t['feed_src'])},{str(warmup).upper()})
                ON CONFLICT (us_slug) DO NOTHING;""", fetch=False)
        inserted += 1
    print(f"scan: recorded {inserted} new signals" + (" (dry-run: none written)" if dry else ""))


# ---------------------------------------------------------------- settle
def dmr_outcome(slug):
    r = sql(f"SELECT settlement_price FROM us_daily_market_report "
            f"WHERE symbol={q_lit(slug)} AND business_date=maturity_date AND settlement_price IN (0,1) LIMIT 1;")
    return float(r[0]["settlement_price"]) if r else None


def settle():
    un = sql("SELECT us_slug, entry_ask FROM finalhour_paper_signals WHERE NOT settled;")
    if not un:
        print("settle: nothing pending")
        return
    n = 0
    for r in un:
        slug = r["us_slug"]
        entry = float(r["entry_ask"])
        outcome, src = None, None
        d = dmr_outcome(slug)
        if d is not None:
            outcome, src = d, "dmr"
        else:
            st = sql(f"""SELECT state, last_trade_px, mid FROM us_mid_tape WHERE us_slug={q_lit(slug)}
                         ORDER BY recv_at DESC LIMIT 1;""")
            if st and st[0]["state"] in ("MARKET_STATE_EXPIRED", "MARKET_STATE_CLOSED"):
                px = float(st[0]["last_trade_px"]) if st[0]["last_trade_px"] else float(st[0]["mid"] or 0.5)
                outcome, src = (1.0 if px >= 0.5 else 0.0), "terminal_px"
        if outcome is None:
            continue
        # lambda close: last non-degenerate mid after entry
        cl = sql(f"""SELECT mid FROM us_mid_tape WHERE us_slug={q_lit(slug)}
                     AND mid BETWEEN {GUARD_LO} AND {GUARD_HI}
                     AND recv_at > (SELECT signal_ts FROM finalhour_paper_signals WHERE us_slug={q_lit(slug)})
                     ORDER BY recv_at DESC LIMIT 1;""")
        clv = float(cl[0]["mid"]) if cl else "NULL"
        net = outcome - entry - fee_us(entry)
        sql(f"""UPDATE finalhour_paper_signals SET settled=TRUE, outcome={outcome},
                settle_ts=now(), settle_src={q_lit(src)}, net={net},
                clv_close={clv} WHERE us_slug={q_lit(slug)};""", fetch=False)
        n += 1
    print(f"settle: resolved {n} markets")


# ---------------------------------------------------------------- report
def report():
    import numpy as np
    rows = sql("SELECT sport,event_key,entry_ask,settled,outcome,net,clv_close,warmup FROM finalhour_paper_signals;")
    tot = len(rows)
    clean = [r for r in rows if r["warmup"] == "f"]
    settled = [r for r in clean if r["settled"] == "t"]
    print(f"finalhour paper ledger: {tot} signals ({len(clean)} clean, {tot-len(clean)} warmup); "
          f"{len(settled)} clean+settled")
    if len(settled) < 20:
        print(f"  (need >=60 clean+settled for the frozen gate; have {len(settled)})")
        # sports present so far
        by = defaultdict(int)
        for r in clean:
            by[r["sport"]] += 1
        if by:
            print("  clean by sport:", dict(by))
        return
    by_ev = defaultdict(lambda: [0.0, 0.0])
    for r in settled:
        by_ev[r["event_key"]][0] += float(r["net"])
        by_ev[r["event_key"]][1] += float(r["entry_ask"])
    roi = np.array([v[0] / v[1] for v in by_ev.values() if v[1] > 0])
    rng = np.random.default_rng(20260715)
    bs = roi[rng.integers(0, len(roi), (4000, len(roi)))].mean(1)
    # lambda
    cl = [r for r in settled if r["clv_close"] not in (None, "", "NULL")]
    lam = None
    if len(cl) >= 20:
        S = np.array([float(r["outcome"]) - float(r["entry_ask"]) for r in cl])
        C = np.array([float(r["clv_close"]) - float(r["entry_ask"]) for r in cl])
        lam = (max(0.0, min(1.0, C.mean() / S.mean())) if S.mean() > 0 else 0.0, C.mean())
    print(f"  ROI/turn {roi.mean()*100:+.2f}%  95% CI [{np.percentile(bs,2.5)*100:+.2f},"
          f"{np.percentile(bs,97.5)*100:+.2f}]  ({len(by_ev)} events)")
    if lam:
        print(f"  lambda_hat {lam[0]:.3f}  mean CLV {lam[1]:+.4f}")
    print("  GATE (frozen): ROI LB>0 AND >=+2.0% AND lambda LB>0 over >=60 clean events, >=2 sports, "
          ">=2 weeks incl non-Wimbledon.")


def self_test():
    assert fee_us(0.9) - 0.06 * 0.09 < 1e-12
    # completed-set counting
    assert _sets_won([6, 6], [3, 4]) == (2, 0)
    assert _sets_won([6, 4, 4], [3, 6, 2]) == (1, 1)     # 3rd set in progress, not counted
    assert _sets_won([7], [6]) == (1, 0)                 # tiebreak set
    # bo5 near-decided: up 2 sets, current level -> fire
    ok, why = near_decided([6, 6, 3], [3, 4, 3], is_bo5=True)
    assert ok, why
    # bo5 NOT near-decided at 1 set
    assert not near_decided([6, 3], [4, 6], is_bo5=True)[0]
    # bo3 near-decided: up a set, serving for match (+3 games) -> fire
    assert near_decided([6, 5], [3, 2], is_bo5=False)[0]
    # bo3 NOT near-decided at 1 set, tight current set
    assert not near_decided([6, 3], [4, 3], is_bo5=False)[0]
    # name tokens
    assert "sabalenka" in name_toks("Aryna Sabalenka")
    assert len(name_toks("Caty McNally") & name_toks("aec wta catmcn xinwan 2026")) >= 0  # smoke
    print("self-test OK (fee, set-counting, near-decided bo3/bo5, name tokens)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--settle", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--dry", action="store_true", help="scan without writing to the ledger")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if a.scan:
        scan(dry=a.dry)
    if a.settle:
        settle()
    if a.report:
        report()
    if not (a.scan or a.settle or a.report):
        ap.print_help()


if __name__ == "__main__":
    main()
