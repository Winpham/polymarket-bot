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


def load_us_yes_players():
    """slug -> (yes_player_name, {both player names}). ORIENTATION SOURCE: the YES contract's player is
    outcomes[i] where side_long[i] is true — NOT the slug's first-listed name (verified: for
    aec-atp-caralc-joafon the YES side is 'Joao Fonseca', not Alcaraz). Buying the wrong side is a
    silent, catastrophic loss, so orientation is read here, never inferred from slug order."""
    import duckdb
    f = os.path.expanduser("~/polymarket-archive/us_markets.parquet")
    con = duckdb.connect()
    rows = con.execute("SELECT slug, outcomes, side_long FROM read_parquet('%s') "
                       "WHERE slug LIKE 'aec-atp-%%' OR slug LIKE 'aec-wta-%%'" % f).fetchall()
    m = {}
    for slug, outcomes, side_long in rows:
        # duckdb returns these list columns as JSON strings, e.g. '["A","B"]' / '[true, false]'
        try:
            outs = json.loads(outcomes) if isinstance(outcomes, str) else list(outcomes)
            sides = json.loads(side_long) if isinstance(side_long, str) else list(side_long)
        except (TypeError, ValueError):
            continue
        if not outs or not sides or len(outs) != len(sides):
            continue
        yi = next((i for i, b in enumerate(sides) if b), None)
        if yi is None:
            continue
        m[slug] = (outs[yi], set(outs))
    return m


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


def match_state(ls_a, ls_b, is_bo5):
    """(ls_a, ls_b) = per-set game counts for player A / B. Returns (near_decided, leader_idx, reason).
    LEADER = more completed sets; ties broken by the current in-progress set's game lead (so a level
    match with B serving for it correctly names B, not A). NEAR-DECIDED (commanding / serving-for-match):
      bo3: leader has >=1 completed set AND leads the current set by >=3 games (one game from the match);
      bo5: leader is up >=2 completed sets with a net set lead AND at least level in the current set."""
    wa, wb = _sets_won(ls_a, ls_b)
    cur_a = ls_a[-1] if ls_a else 0
    cur_b = ls_b[-1] if ls_b else 0
    mm = max(cur_a, cur_b)
    cur_completed = mm >= 6 and (abs(cur_a - cur_b) >= 2 or mm == 7)
    cur_lead_a = 0 if cur_completed else (cur_a - cur_b)      # A's game lead in the in-progress set
    if wa != wb:
        lead = 0 if wa > wb else 1
    else:
        lead = 0 if cur_lead_a >= 0 else 1                    # sets level -> whoever leads the current set
    wl, wo = (wa, wb) if lead == 0 else (wb, wa)
    cl = cur_lead_a if lead == 0 else -cur_lead_a             # leader's game lead in the current set
    if is_bo5:
        nd = wl >= 2 and (wl - wo) >= 1 and cl >= 0
    else:
        nd = wl >= 1 and cl >= 3
    return nd, lead, f"sets {wl}-{wo}, cur +{cl}"


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
                    nd, lead, reason = match_state(ls[0], ls[1], is_bo5)
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
    yes_map = load_us_yes_players()          # slug -> (yes_player, {both names})  [orientation source]
    have = {r["us_slug"] for r in sql("SELECT us_slug FROM finalhour_paper_signals;")}
    open_mkts = sql("""
        SELECT DISTINCT ON (us_slug) us_slug, mid, best_ask, best_bid, spread,
               EXTRACT(EPOCH FROM recv_at) t, state
        FROM us_mid_tape
        WHERE state='MARKET_STATE_OPEN' AND (us_slug LIKE 'aec-atp-%' OR us_slug LIKE 'aec-wta-%')
              AND recv_at > now() - interval '10 minutes' AND mid IS NOT NULL AND best_ask IS NOT NULL
        ORDER BY us_slug, recv_at DESC;""")
    inserted = considered = 0
    for t in triggers:
        lead_tok = name_toks(t["leader_name"])
        allt = name_toks(" ".join(t["names"]))
        for r in open_mkts:
            slug = r["us_slug"]
            if slug in have or slug not in yes_map:
                continue
            yes_player, players = yes_map[slug]
            # (1) this market must be THIS matchup: both players' names present
            if len(allt & name_toks(" ".join(players))) < 2:
                continue
            # (2) ORIENTATION: the YES side we would buy must be the ESPN leader, else it is an
            #     inverted (losing-side) bet — skip. Never inferred from slug order.
            if len(name_toks(yes_player) & lead_tok) < 1:
                continue
            considered += 1
            ask = float(r["best_ask"])
            # (3) gate the price ACTUALLY PAID (ask), not the mid — a wide market can have mid in-band
            #     but ask out of band, where fee+spread erase the edge.
            if not (BAND_LO <= ask <= BAND_HI):
                continue
            mid = float(r["mid"])
            bid = float(r["best_bid"]) if r["best_bid"] else mid
            spread = float(r["spread"]) if r["spread"] else (ask - bid)
            hist = sql(f"SELECT EXTRACT(EPOCH FROM (max(recv_at)-min(recv_at))) age "
                       f"FROM us_mid_tape WHERE us_slug={q_lit(slug)};")
            age = float(hist[0]["age"]) if hist and hist[0]["age"] else 0.0
            warmup = age < WARMUP_MIN_S
            mm = re.search(r"(\d{4}-\d{2}-\d{2})", slug)
            evk = slug[:mm.end()] if mm else slug
            print(f"  TRIGGER {slug}  YES={yes_player}  ask={ask:.3f} mid={mid:.3f}  "
                  f"[{t['feed_src']}: {t['feed_state']}]  warmup={warmup}")
            if not dry:
                sql(f"""INSERT INTO finalhour_paper_signals
                        (us_slug,sport,event_key,signal_ts,entry_ask,entry_mid,entry_spread,
                         feed_state,feed_src,warmup)
                        VALUES ({q_lit(slug)},{q_lit(t['sport'])},{q_lit(evk)},
                                to_timestamp({float(r['t'])}),{ask},{mid},{spread},
                                {q_lit(t['feed_state'])},{q_lit(t['feed_src'])},{str(warmup).upper()})
                        ON CONFLICT (us_slug) DO NOTHING;""", fetch=False)
                have.add(slug)
            inserted += 1
            break
    if triggers and considered == 0:
        print("scan: WARNING — near-decided matches exist but 0 US markets matched by "
              "name+orientation (check the us_markets.parquet join / player-name overlap).")
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
                ltp, md = st[0]["last_trade_px"], st[0]["mid"]
                if ltp not in (None, "") or md not in (None, ""):   # never default a null market to a WIN
                    px = float(ltp) if ltp not in (None, "") else float(md)
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
    # match_state returns (near_decided, leader_idx, reason)
    nd, lead, _ = match_state([6, 6, 3], [3, 4, 3], is_bo5=True)   # A up 2 sets, 3rd level -> fire, A leads
    assert nd and lead == 0
    assert not match_state([6, 3], [4, 6], is_bo5=True)[0]         # bo5 at 1 set each -> no
    nd, lead, _ = match_state([6, 5], [3, 2], is_bo5=False)        # A up a set, serving for match -> fire
    assert nd and lead == 0
    assert not match_state([6, 3], [4, 3], is_bo5=False)[0]        # up a set but current tight -> no
    # DECIDING-SET leader tie-break: sets level 1-1, B serving for the match in the 3rd -> B is leader
    nd, lead, _ = match_state([6, 3, 2], [3, 6, 5], is_bo5=False)
    assert nd and lead == 1, (nd, lead)
    # name matching must work on FULL names (the bug that made the harness inert): ESPN full name vs
    # the us_markets outcome name — NOT the truncated slug code.
    assert len(name_toks("Caty McNally") & name_toks("Xinyu Wang Caty McNally")) >= 1
    assert len(name_toks("Caty McNally") & name_toks("catmcn xinwan 2026")) == 0  # slug codes never match
    assert "sabalenka" in name_toks("Aryna Sabalenka")
    print("self-test OK (fee, set-counting, match_state leader+deciding-set, full-name matching)")
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
