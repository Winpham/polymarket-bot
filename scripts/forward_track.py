#!/usr/bin/env python3
"""
FORWARD-TRACK INSTRUMENT (beat-best-trader, Cycle 6) — the dormancy accrual monitor.

Read-only, snapshot-only. Re-run periodically with NO code change; it just ACCRUES. For each play frozen
in the pre-registration seal (reports/PREREG_FORWARD_TRACK_<seal>.md) it computes forward (post-seal)
realizable performance at the MEASURED band-aware follower tax (~1.0c, from reports/real_tax.json — Win #1
baked in, NOT the old flat 0.013), runs the FULL frozen gate, and emits a per-play readiness row:

  STATUS ∈ {HOLD, INDETERMINATE-BY-POWER, GO-CANDIDATE}
  current value vs EACH gate threshold · the FIRST binding failure · distinct forward events/days/
  non-soccer regimes accrued · what's-still-needed + a rough ETA.

If ANY play clears EVERY gate → STATUS = GO-CANDIDATE and a loud
  "ESCALATE TO HUMAN — do NOT auto-promote/arm" banner (a GO on thin data is more likely a bug than an
  edge; we demand the months). The instrument promotes NOTHING and arms NOTHING.

FORWARD-ONLY: every DB row is filtered first_seen (fill ts) >= the SEAL timestamp. No pre-seal data
enters any computation. Metric = realizable Calmar (mean_day / maxDD) at the measured tax, event-clustered
at COALESCE(event_slug, condition_id), flat-SHARES, out-of-sample = forward.

The gate is ORDERED; the FIRST failing check is the binding constraint. At the seal, forward events ~ 0,
so every play reports INDETERMINATE-BY-POWER (binding = power/persistence accrual, MONTHS). Expensive
belief-blind nulls (checks 3/5/6/7) are DOWNSTREAM of the power + persistence accrual gates (checks 1 & 8)
which bind first for months; they are reported PENDING and are re-computed by the companion instruments
(selection_null.py / best_trader_benchmark.py / drawdown_optimization.py) in the same accrual cycle once
power clears. forward_track owns the cheap, self-contained gates (power, realizable-Calmar, beats-best-
single, persistence-regimes) + reads the recovered edge-reality lambda.

  ./forward_track.py            # live forward snapshot; writes reports/forward_track.json
  ./forward_track.py --selftest # synthetic plays with known answers (clears-all -> GO-CANDIDATE+escalate;
                                #   thin -> INDETERMINATE-BY-POWER; unprofitable -> HOLD); NO DB.

PAPER-ONLY · promotes NOTHING · arms NOTHING · no Rust · DB read-only · cost-zero (Max-only).
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc
import reliability_portfolio as rp
import drawdown_optimization as do

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
REPORT = os.path.join(REPORT_DIR, "forward_track.json")

# ---- FROZEN by PREREG_FORWARD_TRACK_2026-07-06T062517Z.md (do NOT edit; a change is a NEW seal) ----
SEAL = "2026-07-06T06:25:17Z"
PREREG = "PREREG_FORWARD_TRACK_2026-07-06T062517Z.md"

WALLET = {
    "master-wuji":    "0x96a3a4d0f0a91074a43ce8dc39d1f092a717d944",
    "acorp":          "0x99e42eb9038705165b22f821e27659c1dc41e4c4",
    "Sportbetting76": "0xe5241830e8876c115d7dc8311ad9f43d85fdd34f",
    "DaBossHogg":     "0x6157d529ae129fe08f22a27ed42e741d2eaa9fb4",
}
# PLAY-A = single-best reliable TAIL; PLAY-B = high-volume LOW-longshot alternative; PLAY-C = survivor book.
PLAYS = {
    "play_A_tail":    {"role": "single-best reliable TAIL", "members": ["master-wuji"]},
    "play_B_dabosshogg": {"role": "high-volume LOW-longshot alternative", "members": ["DaBossHogg"]},
    "play_C_book":    {"role": "equal-weight survivor BOOK (diversification benchmark)",
                       "members": ["master-wuji", "acorp", "Sportbetting76", "DaBossHogg"]},
}

# ---- FROZEN gate floors (mirror the seal §3) ----
POWER_FLOOR = 30            # (1) distinct forward resolved events
REGIME_FLOOR = 2           # (8) disjoint NON-SOCCER regimes
REGIME_MIN_EV = 8          # a sport x month must have >= this many events to count as a real regime
BELIEF_P = 0.01            # (3) belief-blind beats-random p
SELECTION_P = 0.01         # (5) selection_null p (with --calibrate PASS)
PROMO_LB = 0.03            # (6) promotion day-deflated LB
PILOT_LB = 0.02            # (7) pilot LB
PILOT_EVENTS = 50          # (7)
PILOT_REGIMES = 5          # (7)
PILOT_POS = 0.70           # (7)
PILOT_LIQ = 2000.0         # (7)
LAMBDA_FLOOR = 0.25        # (9) edge-reality lambda CI-lower
BAND_LO, BAND_HI = tsc.BAND_LO, tsc.BAND_HI   # 0.45-0.90 favorite band (metric scope; unchanged)
LONGSHOT_PRICE = 0.35      # eligibility screen (informational here)


# ============================================================ measured band-aware tax (Win #1)
def load_tax_by_band():
    """Per-band MEASURED follower tax (market-clustered mean) from real_tax.json; fall back to the
    modeled FOLLOWER_TAX only for a band with no measured value. Returns {band_int: tax}."""
    try:
        rt = json.load(open(os.path.join(REPORT_DIR, "real_tax.json")))
    except Exception:
        return {}
    out = {}
    for k, v in (rt.get("by_band") or {}).items():
        t = v.get("real_tax_market_clustered_mean")
        if t is not None:
            out[int(k[1:])] = float(t)
    return out


def tax_for(price, tax_by_band):
    return tax_by_band.get(tsc.band(price), tsc.FOLLOWER_TAX)


# ============================================================ forward DB read (snapshot-only)
def fetch_forward(wallets):
    """Forward-only (fill ts >= SEAL) resolved BUY events for the given wallets, event-clustered in SQL.
    Returns {wallet_lower: [event-dicts]} with per-event their-price return, mean price, sport, day,
    calendar-month (regime), n_fills. ALL prices (the longshot screen needs the full range); the Calmar
    metric later restricts to the frozen favorite band."""
    if not wallets:
        return {}
    inlist = ",".join(f"'{w.lower()}'" for w in wallets)
    sql = f"""
      WITH f AS (
        SELECT lower(wallet) AS wallet, COALESCE(event_slug, condition_id) AS ev,
               price::float8 AS price, outcome_won::int AS won, COALESCE(sport,'other') AS sport,
               EXTRACT(EPOCH FROM ts) AS ts, (ts AT TIME ZONE 'UTC')::date AS day,
               to_char(ts AT TIME ZONE 'UTC','YYYY-MM') AS ym
        FROM trader_fills
        WHERE side='BUY' AND resolved AND outcome_won IS NOT NULL
          AND lower(wallet) IN ({inlist})
          AND ts >= '{SEAL}'),
      agg AS (
        SELECT wallet, ev, count(*) AS n, avg(won - price) AS their, avg(price) AS pm, min(ts) AS mnts
        FROM f GROUP BY wallet, ev),
      fs AS (
        SELECT DISTINCT ON (wallet, ev) wallet, ev, sport, day, ym
        FROM f ORDER BY wallet, ev, ts)
      SELECT a.wallet, a.ev, a.n, a.their, a.pm, a.mnts, fs.sport, fs.day, fs.ym
      FROM agg a JOIN fs USING (wallet, ev)"""
    rows = tsc.q(sql)
    byw = defaultdict(list)
    for r in rows:
        pm = float(r["pm"])
        byw[r["wallet"]].append({
            "ev": r["ev"], "their": float(r["their"]), "price": pm, "band": tsc.band(pm),
            "sport": r["sport"], "day": r["day"], "ym": r["ym"], "ts": float(r["mnts"]),
            "n_fills": int(r["n"])})
    for w in byw:
        byw[w].sort(key=lambda e: (e["ts"], e["ev"]))
    return byw


def realizable_pnl(e, tax_by_band):
    """Per-event realizable (OUR-price) P&L at the measured tax: their-price return minus the follower
    tax minus fee on the repriced entry. Matches drawdown_optimization's our-price reprice."""
    tax = tax_for(e["price"], tax_by_band)
    entry = e["price"] + tax
    return e["their"] - tax - tsc.FEE * entry


# ============================================================ per-play forward metrics
def play_metrics(members, byw, tax_by_band, best_single_calmar=None):
    """Compute the forward metrics dict for one play. `members` = usernames; byw keyed by lower wallet.
    Realizable Calmar is on the frozen favorite band (0.45-0.90); accrual counts are over that band."""
    evs = []
    for nm in members:
        w = WALLET[nm].lower()
        evs.extend(byw.get(w, []))
    band_evs = [e for e in evs if BAND_LO <= e["price"] < BAND_HI]
    n_events = len(band_evs)
    n_days = len({e["day"] for e in band_evs})

    # distinct NON-SOCCER regimes = sport x calendar-month with >= REGIME_MIN_EV events, excluding soccer
    reg = defaultdict(int)
    for e in band_evs:
        if e["sport"] != "soccer":
            reg[f"{e['sport']}|{e['ym']}"] += 1
    regimes = sorted(k for k, c in reg.items() if c >= REGIME_MIN_EV)
    non_soccer_regimes = len(regimes)

    # realizable (measured-tax) Calmar, book = equal weight across members present each day
    per_wallet_daily = {}
    for nm in members:
        w = WALLET[nm].lower()
        wevs = [e for e in byw.get(w, []) if BAND_LO <= e["price"] < BAND_HI]
        if wevs:
            per_wallet_daily[nm] = rp._daily([(e["day"], e["ts"], realizable_pnl(e, tax_by_band))
                                              for e in wevs])
    calmar = None
    if per_wallet_daily:
        if len(per_wallet_daily) == 1:
            daily = next(iter(per_wallet_daily.values()))
        else:
            w_eq = {nm: 1.0 / len(per_wallet_daily) for nm in per_wallet_daily}
            daily = rp.book_daily(per_wallet_daily, w_eq)
        if daily:
            calmar = do.calmar_stats(daily).get("calmar")

    beats_best = None
    if calmar is not None and best_single_calmar is not None:
        beats_best = do._cmp(calmar) >= do._cmp(best_single_calmar)

    return {
        "n_events": n_events, "n_days": n_days,
        "non_soccer_regimes": non_soccer_regimes, "regimes": regimes,
        "realizable_calmar": calmar, "best_single_calmar": best_single_calmar,
        "beats_best_single": beats_best,
        # downstream nulls (checks 3/5/6/7): PENDING until power+persistence clear; computed by the
        # companion instruments in the accrual cycle. None here = not-yet-computable (power-blocked).
        "beats_random_p": None, "selection_null_p": None, "selection_calibrate": None,
        "promotion_lb": None,
        "pilot_lb": None, "pilot_events": n_events, "pilot_pos_regimes": None,
        "pilot_pos_frac": None, "pilot_liquidity": None,
    }


# ============================================================ the frozen gate (PURE — fixture-testable)
def _pf(x, spec="+.3f"):
    if x is None:
        return "n/a"
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return "inf" if (isinstance(x, float) and x > 0) else "n/a"
    return format(x, spec)


def build_gate_rows(m):
    """Pure: map a metrics dict to the ordered list of gate rows (seal §3). Each row:
    {check,name,current,threshold,passed(bool|None),kind,eta}. kind in
    {power,accrual,value,data,downstream}; a failed power/accrual/data/downstream (or a None metric) =>
    INDETERMINATE-BY-POWER; a failed VALUE with a computed metric => HOLD."""
    rows = []
    cal = m.get("realizable_calmar")

    def row(check, name, current, threshold, passed, kind, eta):
        rows.append({"check": check, "name": name, "current": current, "threshold": threshold,
                     "passed": passed, "kind": kind, "eta": eta})

    # (1) power
    row(1, "power_events", f"{m['n_events']} forward events", f">= {POWER_FLOOR}",
        m["n_events"] >= POWER_FLOOR, "power", "weeks")
    # (2) realizable edge exists (positive Calmar at measured tax)
    row(2, "realizable_calmar_positive",
        f"realizable Calmar {_pf(cal)}", "> 0",
        (do._cmp(cal) > 0) if cal is not None else None, "value" if cal is not None else "data",
        "weeks")
    # (3) beats a RANDOM equal-size book, belief-blind
    p = m.get("beats_random_p")
    row(3, "beats_random_book_belief_blind",
        f"belief-blind p {_pf(p,'.4f') if p is not None else 'PENDING (blocked upstream)'}",
        f"p <= {BELIEF_P}", (p is not None and p <= BELIEF_P) if p is not None else None,
        "downstream", "months")
    # (4) beats the single-best benchmark
    row(4, "beats_best_single",
        f"play Calmar {_pf(cal)} vs best-single {_pf(m.get('best_single_calmar'))}",
        "play Calmar >= best single reliable trader", m.get("beats_best_single"),
        "value" if m.get("beats_best_single") is not None else "data", "months")
    # (5) selection_null p <= 0.01 with --calibrate PASS
    sp, sc = m.get("selection_null_p"), m.get("selection_calibrate")
    row(5, "selection_null",
        f"selection_null p {_pf(sp,'.4f') if sp is not None else 'PENDING (blocked upstream)'}"
        f"{'' if sc is None else f', calibrate={sc}'}",
        f"p <= {SELECTION_P} AND calibrate PASS",
        ((sp is not None and sp <= SELECTION_P and sc is True) if sp is not None else None),
        "downstream", "months")
    # (6) promotion_verdict (day-deflated LB)
    plb = m.get("promotion_lb")
    row(6, "promotion_verdict",
        f"day-deflated LB {_pf(plb) if plb is not None else 'PENDING (blocked upstream)'}",
        f">= {POWER_FLOOR} events, Bonferroni, day-deflated SE, LB > {PROMO_LB}",
        (plb is not None and plb > PROMO_LB and m["n_events"] >= POWER_FLOOR) if plb is not None else None,
        "downstream", "months")
    # (7) pilot_verdict
    plb2 = m.get("pilot_lb")
    pilot_ok = None
    if plb2 is not None:
        pilot_ok = (plb2 > PILOT_LB and m.get("pilot_events", 0) >= PILOT_EVENTS
                    and (m.get("pilot_pos_regimes") or 0) >= PILOT_REGIMES
                    and (m.get("pilot_pos_frac") or 0) >= PILOT_POS
                    and (m.get("pilot_liquidity") or 0) >= PILOT_LIQ)
    row(7, "pilot_verdict",
        (f"LB {_pf(plb2)}, ev {m.get('pilot_events')}, +regimes {m.get('pilot_pos_regimes')}, "
         f"+frac {_pf(m.get('pilot_pos_frac'),'.0%') if m.get('pilot_pos_frac') is not None else 'n/a'}, "
         f"liq {m.get('pilot_liquidity')}") if plb2 is not None else "PENDING (blocked upstream)",
        f"LB > {PILOT_LB}, >= {PILOT_EVENTS} ev, >= {PILOT_REGIMES} +regimes, "
        f">= {PILOT_POS:.0%} +, liq >= ${PILOT_LIQ:.0f}",
        pilot_ok, "downstream", "months")
    # (8) persistence across >= 2 disjoint NON-SOCCER regimes
    row(8, "persistence_non_soccer",
        f"{m['non_soccer_regimes']} non-soccer regimes ({', '.join(m['regimes']) or 'none'})",
        f">= {REGIME_FLOOR} disjoint non-soccer regimes (>= {REGIME_MIN_EV} ev each, non-expiring)",
        m["non_soccer_regimes"] >= REGIME_FLOOR, "accrual", "months")
    # (9) edge-reality lambda CI-lower >= 0.25
    lo, cov = m.get("lambda_ci_lo"), m.get("lambda_coverage")
    lam_pass = None
    if lo is not None:
        lam_pass = (lo >= LAMBDA_FLOOR and (cov is None or cov >= 0.50))
    cov_str = ("" if cov is None else " at coverage " + _pf(cov, ".0%"))
    lo_str = ("n/a" if lo is None else _pf(lo, ".3f"))
    row(9, "edge_reality_lambda",
        f"lambda CI-lo {lo_str}{cov_str}",
        f"CI-lo >= {LAMBDA_FLOOR} at >= 50% coverage",
        lam_pass, "data", "months")
    return rows


def classify(rows):
    """Return (status, first_binding_row_or_None). GO-CANDIDATE iff every row passed True."""
    unmet = [r for r in rows if r["passed"] is not True]
    if not unmet:
        return "GO-CANDIDATE", None
    first = min(unmet, key=lambda r: r["check"])
    if first["kind"] == "value" and first["passed"] is False:
        return "HOLD", first
    # power / accrual / data / downstream, or a not-yet-computable (None) metric
    return "INDETERMINATE-BY-POWER", first


def needs_for(first):
    """What's-still-needed + ETA for a play's first binding failure."""
    if first is None:
        return "clears every gate — ESCALATE TO HUMAN", "none"
    txt = {
        "power_events": f"accrue >= {POWER_FLOOR} forward resolved events",
        "realizable_calmar_positive": "forward realizable Calmar must turn positive at the measured tax",
        "beats_random_book_belief_blind": "run the belief-blind random-book null once power clears",
        "beats_best_single": "book must beat the best single reliable trader on realizable Calmar",
        "selection_null": "selection_null p <= 0.01 with --calibrate PASS",
        "promotion_verdict": "day-deflated Bonferroni LB > 3% on >= 30 forward events",
        "pilot_verdict": "pilot floors: LB>2%, >=50 ev, >=5 +regimes, >=70% +, liq>=$2000",
        "persistence_non_soccer": "accrue >= 2 disjoint NON-SOCCER regimes (esports/NFL/NBA), non-expiring",
        "edge_reality_lambda": "dense-capture coverage to >= 50% so measured lambda CI-lo clears 0.25",
    }.get(first["name"], first["name"])
    return txt, first["eta"]


# ============================================================ live driver
def run():
    tax_by_band = load_tax_by_band()
    # recovered edge-reality lambda (standing read; the current best coverage) — informational input
    lo = cov = None
    try:
        clv = json.load(open(os.path.join(REPORT_DIR, "clv_lambda_marketkey.json")))
        lo = (clv.get("lambda_ci") or [None, None])[0]
        cov = clv.get("trajectory_coverage")
    except Exception:
        pass

    all_wallets = sorted({WALLET[nm] for p in PLAYS.values() for nm in p["members"]})
    byw = fetch_forward(all_wallets)

    # best single reliable trader forward realizable Calmar (the check-4 bar): max over PLAY-C survivors
    survivors = PLAYS["play_C_book"]["members"]
    best_single_calmar = None
    best_single_name = None
    for nm in survivors:
        mm = play_metrics([nm], byw, tax_by_band)
        c = mm["realizable_calmar"]
        if c is not None and (best_single_calmar is None or do._cmp(c) > do._cmp(best_single_calmar)):
            best_single_calmar, best_single_name = c, nm

    plays_out = {}
    any_go = False
    for pid, spec in PLAYS.items():
        m = play_metrics(spec["members"], byw, tax_by_band,
                         best_single_calmar=best_single_calmar if pid == "play_C_book" else None)
        m["lambda_ci_lo"], m["lambda_coverage"] = lo, cov
        rows = build_gate_rows(m)
        status, first = classify(rows)
        need, eta = needs_for(first)
        any_go = any_go or (status == "GO-CANDIDATE")
        plays_out[pid] = {
            "role": spec["role"], "members": spec["members"], "status": status,
            "n_events": m["n_events"], "n_days": m["n_days"],
            "non_soccer_regimes": m["non_soccer_regimes"], "regimes": m["regimes"],
            "realizable_calmar": do._R(m["realizable_calmar"]) if m["realizable_calmar"] is not None else None,
            "first_binding": (first["name"] if first else None),
            "needs": need, "eta": eta,
            "gate": rows,
        }

    out = {"meta": {"seal": SEAL, "prereg": PREREG, "metric": "realizable Calmar at MEASURED band-aware tax",
                    "tax_by_band": {str(k): round(v, 4) for k, v in sorted(tax_by_band.items())} or "modeled",
                    "forward_only": f"fill ts >= {SEAL}",
                    "best_single": {"name": best_single_name, "calmar": do._R(best_single_calmar)
                                    if best_single_calmar is not None else None},
                    "posture": "PAPER-ONLY, promotes NOTHING, arms NOTHING, no Rust, DB read-only"},
           "escalate": any_go, "plays": plays_out}
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)
    _print(out)
    return out


def _print(out):
    print("=" * 100)
    print(f"FORWARD-TRACK · seal {out['meta']['seal']} · metric = {out['meta']['metric']}")
    print(f"forward-only: {out['meta']['forward_only']} · tax_by_band={out['meta']['tax_by_band']}")
    print("=" * 100)
    hdr = f"{'play':<20}{'status':<24}{'ev':>5}{'d':>4}{'regimes':>9}{'calmar':>9}  first-binding / needs"
    print(hdr); print("-" * len(hdr))
    for pid, p in out["plays"].items():
        print(f"{pid:<20}{p['status']:<24}{p['n_events']:>5}{p['n_days']:>4}"
              f"{p['non_soccer_regimes']:>9}{str(p['realizable_calmar']):>9}  "
              f"{p['first_binding']}: {p['needs']} ({p['eta']})")
    print("-" * len(hdr))
    if out["escalate"]:
        print("\n" + "!" * 100)
        print("!!  GO-CANDIDATE — ESCALATE TO HUMAN. Do NOT auto-promote or auto-arm.")
        print("!!  A GO on thin data is more likely a BUG than an edge. Demand the months of independent")
        print("!!  non-soccer persistence, verify by hand, then it is Tue's call behind the 4 GO gates.")
        print("!" * 100)
    else:
        print("\nNo GO-CANDIDATE. Binding constraint is the accrual horizon (power + non-soccer persistence,")
        print("MONTHS). Re-run weekly with NO code change; the instrument just accrues. Nothing promoted.")
    print(f"\nwrote {REPORT}")


# ============================================================ selftest (no DB)
def selftest():
    ok = True

    def check(cond, label):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'ok' if cond else 'FAIL'}] {label}")

    # (A) synthetic play that CLEARS EVERYTHING -> GO-CANDIDATE + escalate
    m_go = {"n_events": 120, "n_days": 40, "non_soccer_regimes": 4,
            "regimes": ["nba|2026-10", "nfl|2026-09", "cs2|2026-11", "nhl|2026-12"],
            "realizable_calmar": 0.30, "best_single_calmar": 0.10, "beats_best_single": True,
            "beats_random_p": 0.002, "selection_null_p": 0.004, "selection_calibrate": True,
            "promotion_lb": 0.06, "pilot_lb": 0.05, "pilot_events": 80, "pilot_pos_regimes": 6,
            "pilot_pos_frac": 0.78, "pilot_liquidity": 5000.0,
            "lambda_ci_lo": 0.31, "lambda_coverage": 0.62}
    rows = build_gate_rows(m_go)
    status, first = classify(rows)
    check(status == "GO-CANDIDATE" and first is None, f"clears-all -> GO-CANDIDATE (got {status})")
    check(all(r["passed"] is True for r in rows), "clears-all -> every gate row passed")

    # (B) thin play (0 forward events) -> INDETERMINATE-BY-POWER, binding = power_events, escalate False
    m_thin = {"n_events": 0, "n_days": 0, "non_soccer_regimes": 0, "regimes": [],
              "realizable_calmar": None, "best_single_calmar": None, "beats_best_single": None,
              "beats_random_p": None, "selection_null_p": None, "selection_calibrate": None,
              "promotion_lb": None, "pilot_lb": None, "pilot_events": 0, "pilot_pos_regimes": None,
              "pilot_pos_frac": None, "pilot_liquidity": None,
              "lambda_ci_lo": 0.065, "lambda_coverage": 0.199}
    rows = build_gate_rows(m_thin)
    status, first = classify(rows)
    check(status == "INDETERMINATE-BY-POWER" and first["name"] == "power_events",
          f"thin -> INDETERMINATE-BY-POWER, binding=power_events (got {status}/{first['name']})")

    # (C) powered but UNPROFITABLE forward Calmar -> HOLD (value failure, not power)
    m_hold = dict(m_thin)
    m_hold.update({"n_events": 90, "n_days": 30, "non_soccer_regimes": 3,
                   "regimes": ["nba|2026-10", "nfl|2026-09", "cs2|2026-11"],
                   "realizable_calmar": -0.12, "best_single_calmar": 0.05, "beats_best_single": False})
    rows = build_gate_rows(m_hold)
    status, first = classify(rows)
    check(status == "HOLD" and first["name"] == "realizable_calmar_positive",
          f"powered+unprofitable -> HOLD, binding=realizable_calmar_positive (got {status}/{first['name']})")

    # (D) powered + profitable but only 1 non-soccer regime AND lambda below floor -> the SOCCER-ARTIFACT
    #     lesson: persistence (check 8) binds before lambda; power-type -> INDETERMINATE-BY-POWER.
    m_soccer = dict(m_go)
    m_soccer.update({"non_soccer_regimes": 1, "regimes": ["nba|2026-10"],
                     "beats_random_p": 0.002, "selection_null_p": 0.004, "selection_calibrate": True})
    rows = build_gate_rows(m_soccer)
    status, first = classify(rows)
    check(status == "INDETERMINATE-BY-POWER" and first["name"] == "persistence_non_soccer",
          f"1-regime -> INDETERMINATE-BY-POWER, binding=persistence_non_soccer (got {status}/{first['name']})")

    # (E) downstream PENDING (belief-blind None) blocks GO even when everything cheap passes -> not GO
    m_pend = dict(m_go)
    m_pend.update({"beats_random_p": None})   # null not yet computed
    rows = build_gate_rows(m_pend)
    status, first = classify(rows)
    check(status == "INDETERMINATE-BY-POWER" and first["name"] == "beats_random_book_belief_blind",
          f"pending-null -> INDETERMINATE-BY-POWER, not a false GO (got {status})")

    # (F) needs_for maps the escalation case
    need, eta = needs_for(None)
    check("ESCALATE" in need and eta == "none", "needs_for(None) -> escalation text")

    # (G) tax_for falls back to FOLLOWER_TAX for an unmeasured band; uses measured where present.
    #     band(0.70)==4, so a {4: ...} map is the measured value, an empty map falls back.
    b70 = tsc.band(0.70)
    check(abs(tax_for(0.70, {b70: 0.009}) - 0.009) < 1e-12
          and abs(tax_for(0.70, {}) - tsc.FOLLOWER_TAX) < 1e-12, "tax_for: measured band + fallback")

    # (H) realizable_pnl sign: a favorite that loses is negative; a strong winner net-positive after tax+fee
    e_win = {"their": 0.20, "price": 0.70}
    e_los = {"their": -0.70, "price": 0.70}
    check(realizable_pnl(e_win, {b70: 0.01}) > 0 and realizable_pnl(e_los, {b70: 0.01}) < 0,
          "realizable_pnl: winner>0, loser<0 at measured tax")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        selftest()
        return
    run()


if __name__ == "__main__":
    main()
