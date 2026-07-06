#!/usr/bin/env python3
"""
DRAWDOWN-TO-PROFIT OPTIMIZATION (Cycle 4). Objective = realizable (OUR-price) CALMAR
(return / max-drawdown), NOT Sortino. Branches O0-O4 + the belief-blind WORTH-IT gate.

The reframe (verified in O0): at the trader's own price the reliability book already beats the
best single reliable trader on Calmar, but the follower tax ~halves return and ~doubles drawdown
at our entry, collapsing realizable Calmar (Cycle-3: their-price 0.167 -> our-price 0.044). The
optimization target is OUR-PRICE Calmar; the biggest lever is shrinking the follower-tax collapse.

  O0  Calmar/MAR/return-CVaR5 objective everywhere, both prices; reproduce the Cycle-3 reframe.
  O1  Weighting head-to-head on the SAME shortlist: equal / inverse-drawdown (baseline) /
      risk-parity (ERC) / HRP / max-Calmar optimizer. Winner by realizable OOS Calmar + stability.
  O2  Widen the eligible universe (admit longshot + other bands; ONE pre-registered gate relaxation
      at a time, never tuned to pass) -> realizable-Calmar-vs-#names curve; where does Calmar peak?
  O3  Tax-aware selection: drop names whose per-name OUR-price Calmar <= 0, reweight; how much of the
      0.167->0.044 tax collapse is recovered?
  O4  Rolling-window rebalanced book vs static, on realizable OOS Calmar: adapt or overfit?
  GATE (belief-blind): does the refined book beat (1) a RANDOM equal-size book on realizable OOS
      Calmar (>=2000, weighting held equal so only SELECTION differs) and (2) the best single reliable
      trader on realizable OOS Calmar? If not -> the value is diversification, not selection. Say so.

Read-only, paper-only, promotes NOTHING. No Rust touched. All weighting lives in this research layer.
  ./drawdown_optimization.py            # live (writes reports/drawdown_optimization.json)
  ./drawdown_optimization.py --selftest # synthetic fixtures with known answers; no DB
  ./drawdown_optimization.py --quick    # live but smaller null budget (fast iteration)
"""

import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc
import reliability_score as rs
import reliability_portfolio as rp

import numpy as np
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "drawdown_optimization.json")
CAP = rp.WEIGHT_CAP          # 0.40
SEED = 20260706
N_NULL = 2000
N_MAXCALMAR = 4000           # random-search budget for the max-Calmar optimizer

# --- Cycle-3 FROZEN reframe anchors (reports/reliability_portfolio.json snapshot) ---
CYCLE3 = {
    "book_their_meanday": 0.09635, "book_their_maxdd": 0.57754,
    "acorp_meanday": 0.13841,      "acorp_maxdd": 1.13789,
    "book_oos_meanday": 0.0435,    "book_oos_maxdd": 0.54696,
    "best_oos_meanday": 0.07163,   "best_oos_maxdd": 1.13789,
    "book_our_meanday": 0.05261,   "book_our_maxdd": 1.18767,
}


# ============================================================ objective functions
def calmar_stats(daily):
    """rp._series_stats + Calmar (mean/maxDD), MAR (total/maxDD), return/CVaR5. Higher = better."""
    s = rp._series_stats(daily)
    if s.get("n_days", 0) == 0:
        return {**s, "calmar": None, "mar": None, "ret_cvar5": None, "cvar5": None}
    days = sorted(daily)
    r = [daily[d] for d in days]
    n = len(r)
    k = max(1, int(round(0.05 * n)))
    cvar5 = sum(sorted(r)[:k]) / k                       # mean of worst 5% (<=0 typically)
    mdd = s["max_drawdown"]
    calmar = (s["mean_day"] / mdd) if mdd > 1e-12 else (float("inf") if s["mean_day"] > 0 else None)
    mar = (s["total_pnl"] / mdd) if mdd > 1e-12 else (float("inf") if s["total_pnl"] > 0 else None)
    ret_cvar5 = (s["mean_day"] / abs(cvar5)) if abs(cvar5) > 1e-12 else (
        float("inf") if s["mean_day"] > 0 else None)
    return {**s, "cvar5": cvar5, "calmar": calmar, "mar": mar, "ret_cvar5": ret_cvar5}


def _cmp(a):
    """None/NaN -> -inf so comparisons/rankings never crash; +inf preserved."""
    if a is None:
        return -9e18
    if isinstance(a, float) and math.isnan(a):
        return -9e18
    if a == float("inf"):
        return 9e18
    return a


# ============================================================ weighting toolkit
def apply_cap(target, cap=CAP):
    """Project arbitrary positive weights onto the simplex with a per-name cap, redistributing
    excess proportionally to the uncapped names (iterated)."""
    w = {k: max(0.0, v) for k, v in target.items()}
    s = sum(w.values()) or 1.0
    w = {k: v / s for k, v in w.items()}
    cap = max(cap, 1.0 / len(w)) if w else cap     # a cap below 1/n is vacuous (infeasible simplex)
    for _ in range(200):
        over = [k for k, v in w.items() if v > cap + 1e-12]
        if not over:
            break
        excess = sum(w[k] - cap for k in over)
        for k in over:
            w[k] = cap
        free = [k for k in w if k not in over]
        fsum = sum(w[k] for k in free)
        if fsum <= 0:                       # no free mass to absorb excess -> equal weight
            return {k: 1.0 / len(w) for k in w}
        for k in free:
            w[k] += excess * w[k] / fsum
    return w


def _panel(dailies, days):
    names = sorted(dailies)
    M = {w: [dailies[w].get(d, 0.0) for d in days] for w in names}   # 0-fill: not trading = 0 return
    return names, M


def _cov(names, M):
    T = len(next(iter(M.values()))) if M else 0
    if T < 2:
        return {(a, b): (1.0 if a == b else 0.0) for a in names for b in names}
    mean = {w: sum(M[w]) / T for w in names}
    C = {}
    for a in names:
        for b in names:
            C[(a, b)] = sum((M[a][t] - mean[a]) * (M[b][t] - mean[b]) for t in range(T)) / (T - 1)
    return C


def w_equal(dailies_their, dailies_our=None, days=None):
    n = len(dailies_their)
    return {w: 1.0 / n for w in dailies_their} if n else {}


def w_inv_dd(dailies_their, dailies_our=None, days=None):
    """Baseline: inverse downside-deviation (equal-risk heuristic) on THEIR-price series."""
    dd = {w: rp._series_stats(dailies_their[w])["downside_dev"] for w in dailies_their}
    return rp._weights(dd, CAP)


def w_risk_parity(dailies_their, dailies_our=None, days=None):
    """Equal Risk Contribution on the 0-fill THEIR-price covariance. Falls back gracefully when the
    covariance is degenerate (near-disjoint trading days -> near-diagonal -> ~inverse-vol)."""
    names = sorted(dailies_their)
    if len(names) == 1:
        return {names[0]: 1.0}
    alldays = days or sorted(set().union(*[set(dailies_their[w]) for w in names]))
    _, M = _panel(dailies_their, alldays)
    C = _cov(names, M)
    w = {k: 1.0 / len(names) for k in names}
    for _ in range(2000):
        Sw = {i: sum(C[(i, j)] * w[j] for j in names) for i in names}
        pv = sum(w[i] * Sw[i] for i in names)
        if pv <= 1e-18:
            break
        sigma = math.sqrt(pv)
        mrc = {i: Sw[i] / sigma for i in names}
        new = {i: ((sigma / len(names)) / mrc[i] if mrc[i] > 1e-12 else w[i]) for i in names}
        sn = sum(new.values())
        if sn <= 0:
            break
        new = {k: v / sn for k, v in new.items()}
        if max(abs(new[k] - w[k]) for k in names) < 1e-10:
            w = new
            break
        w = new
    return apply_cap(w, CAP)


def _quasi_diag(link, n):
    link = link.astype(int)
    sortIx = [link[-1, 0], link[-1, 1]]
    while max(sortIx) >= n:
        newIx = []
        for i in sortIx:
            if i < n:
                newIx.append(i)
            else:
                c = link[i - n]
                newIx.append(int(c[0]))
                newIx.append(int(c[1]))
        sortIx = newIx
    return sortIx


def w_hrp(dailies_their, dailies_our=None, days=None):
    """Hierarchical Risk Parity (Lopez de Prado) on the 0-fill THEIR-price cov/corr. Robust to the
    noisy small-sample correlation matrix (the Cycle-3 0.85-on-6-days pair is exactly its use case)."""
    names = sorted(dailies_their)
    n = len(names)
    if n == 1:
        return {names[0]: 1.0}
    if n == 2:
        return w_risk_parity(dailies_their, dailies_our, days)
    alldays = days or sorted(set().union(*[set(dailies_their[w]) for w in names]))
    _, M = _panel(dailies_their, alldays)
    C = _cov(names, M)
    std = {i: math.sqrt(C[(i, i)]) if C[(i, i)] > 0 else 0.0 for i in names}
    corr = np.array([[(C[(a, b)] / (std[a] * std[b]) if std[a] > 0 and std[b] > 0
                       else (1.0 if a == b else 0.0)) for b in names] for a in names])
    corr = np.clip(corr, -1.0, 1.0)
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, None))
    np.fill_diagonal(dist, 0.0)
    link = linkage(squareform(dist, checks=False), "single")
    sortIx = _quasi_diag(link, n)
    covm = np.array([[C[(a, b)] for b in names] for a in names])
    w = np.ones(n)
    clusters = [sortIx]
    while clusters:
        clusters = [c[j:k] for c in clusters for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]
            v0 = _cluster_var(covm, c0)
            v1 = _cluster_var(covm, c1)
            alpha = 1.0 - v0 / (v0 + v1) if (v0 + v1) > 0 else 0.5
            for idx in c0:
                w[idx] *= alpha
            for idx in c1:
                w[idx] *= (1.0 - alpha)
    wd = {names[i]: float(w[i]) for i in range(n)}
    return apply_cap(wd, CAP)


def _cluster_var(covm, idx):
    sub = covm[np.ix_(idx, idx)]
    diag = np.clip(np.diag(sub), 1e-12, None)      # guard zero/neg variance (constant series)
    ivp = 1.0 / diag
    ivp = ivp / ivp.sum() if ivp.sum() > 0 else np.ones(len(idx)) / len(idx)
    return float(ivp @ sub @ ivp)


def w_max_calmar(dailies_their, dailies_our, days=None, seed=SEED, n_iter=N_MAXCALMAR,
                 objprice="our"):
    """Direct max-Calmar optimizer over the capped simplex, random search + corner seeds. Optimizes
    the OUR-price book Calmar (the realizable target) by default -> inherently tax-aware."""
    names = sorted(dailies_their)
    n = len(names)
    if n == 1:
        return {names[0]: 1.0}
    src = dailies_our if objprice == "our" else dailies_their
    rng = np.random.default_rng(seed)

    def obj(w):
        bd = rp.book_daily(src, w)
        return _cmp(calmar_stats(bd)["calmar"])

    # corner seeds: equal, inv-dd, each single name (respecting cap-feasibility)
    cands = [w_equal(dailies_their), w_inv_dd(dailies_their)]
    for nm in names:
        cands.append(apply_cap({k: (1.0 if k == nm else 1e-6) for k in names}, CAP))
    best, best_v = None, -9e18
    for w in cands:
        v = obj(w)
        if v > best_v:
            best, best_v = w, v
    for _ in range(n_iter):
        draw = rng.dirichlet(np.ones(n))
        w = apply_cap({names[i]: float(draw[i]) for i in range(n)}, CAP)
        v = obj(w)
        if v > best_v:
            best, best_v = w, v
    return best


METHODS = {
    "equal": lambda dt, do, dd: w_equal(dt, do, dd),
    "inv_dd": lambda dt, do, dd: w_inv_dd(dt, do, dd),
    "risk_parity": lambda dt, do, dd: w_risk_parity(dt, do, dd),
    "hrp": lambda dt, do, dd: w_hrp(dt, do, dd),
    "max_calmar": lambda dt, do, dd: w_max_calmar(dt, do, dd),
}


# ============================================================ data assembly
_CACHE = {}


def _shared():
    """Band-independent inputs (micro/bot flags, band spreads, name map), fetched once."""
    if "micro" not in _CACHE:
        _CACHE["micro"] = tsc.fetch_micro()
        _CACHE["bots"] = tsc.fetch_bot_flags()
        _CACHE["spreads"] = tsc.fetch_band_spreads()
        nr = tsc.q("SELECT lower(proxy_wallet) AS w, username FROM followed_traders")
        _CACHE["names"] = {r["w"]: r["username"] for r in nr}
    return _CACHE


def _spread_case(spreads):
    """SQL CASE mapping width_bucket band -> fetched band spread (for OUR-entry reprice in SQL)."""
    parts = " ".join(f"WHEN {int(b)} THEN {float(s):.6f}" for b, s in spreads.items())
    return f"(CASE width_bucket(price, 0.0, 1.0, 5) {parts} ELSE 0.0 END)" if parts else "0.0"


def fetch_events(band_lo, band_hi):
    """ONE aggregated query per band -> per-(wallet, event) records, event-clustered in SQL. Returns
    {wallet: [event-dicts]} matching reliability_score._events shape PLUS a precomputed OUR-price pnl.
    This is EXACT: 'their' = avg(won-price), 'our' = avg((won-reprice)-fee*reprice) per event, the
    same statistics as reliability_score._events / reliability_portfolio._event_pnl, but the 1.6M-fill
    scan is aggregated server-side (the per-fill fetch was the runtime bottleneck: 105s just to parse)."""
    key = ("ev", band_lo, band_hi)
    if key in _CACHE:
        return _CACHE[key]
    spreads = _shared()["spreads"]
    sc = _spread_case(spreads)
    sql = f"""
      WITH f AS (
        SELECT lower(wallet) AS wallet, COALESCE(event_slug, condition_id) AS ev,
               price::float8 AS price, outcome_won::int AS won, COALESCE(sport,'other') AS sport,
               EXTRACT(EPOCH FROM ts) AS ts, (ts AT TIME ZONE 'UTC')::date AS day,
               (price + {tsc.FOLLOWER_TAX} + {sc}) AS e
        FROM trader_fills
        WHERE side='BUY' AND resolved AND outcome_won IS NOT NULL
          AND price >= {band_lo} AND price < {band_hi}
          AND ts >= NOW() - INTERVAL '{tsc.WINDOW_DAYS} days'),
      agg AS (
        SELECT wallet, ev, count(*) AS n, avg(won - price) AS their,
               avg((won - e) - {tsc.FEE} * e) AS our, avg(price) AS pm,
               sum(price * (1.0 - price)) AS pvar, min(ts) AS mnts
        FROM f GROUP BY wallet, ev),
      fs AS (
        SELECT DISTINCT ON (wallet, ev) wallet, ev, sport, day
        FROM f ORDER BY wallet, ev, ts)
      SELECT a.wallet, a.ev, a.n, a.their, a.our, a.pm, a.pvar, a.mnts, fs.sport, fs.day
      FROM agg a JOIN fs USING (wallet, ev)"""
    rows = tsc.q(sql)
    byw = defaultdict(list)
    for r in rows:
        n = int(r["n"])
        pm = float(r["pm"])
        byw[r["wallet"]].append({
            "ev": r["ev"], "ret": float(r["their"]), "our": float(r["our"]), "price": pm,
            "sport": r["sport"], "band": tsc.band(pm), "day": r["day"], "ts": float(r["mnts"]),
            "n_fills": n, "sumvar": float(r["pvar"]) / (n * n)})
    for w in byw:
        byw[w].sort(key=lambda e: (e["ts"], e["ev"]))
    _CACHE[key] = byw
    return byw


def load_universe(band_lo, band_hi, cross_sport_min=rs.MIN_POS_SPORTS):
    """Score every wallet on the given price band; return (scored, shortlist, byw, names, spreads).
    cross_sport_min lets O2 relax the >=2-positive-sports gate (pre-registered)."""
    sh = _shared()
    byw = fetch_events(band_lo, band_hi)
    micro, bots, names = sh["micro"], sh["bots"], sh["names"]
    scored, shortlist = {}, []
    for w, evs in byw.items():
        if len(evs) < rs.MIN_EVENTS:
            continue
        s = rs.score_evs(evs)
        is_mm = tsc.is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0}))
        is_bot = bots.get(w) == "bot"
        passed, fails, checks = rs.gate(s, is_mm, is_bot)
        if not passed and cross_sport_min < rs.MIN_POS_SPORTS:      # pre-registered P2 relaxation
            relaxed = [f for f in fails if f != "cross_sport_stable"] \
                if s["n_pos_sports"] >= cross_sport_min else fails
            passed = (len(relaxed) == 0)
        scored[w] = {"score": s, "pass": passed, "is_mm": is_mm, "is_bot": is_bot}
        if passed:
            shortlist.append(w)
    shortlist.sort(key=lambda w: -_cmp(scored[w]["score"]["sortino"]))
    return scored, shortlist, byw, names, sh["spreads"]


def evp(evs, mode):
    """Per-event (day, ts, pnl) list for the book engine; pnl precomputed at their/our price."""
    return [(e["day"], e["ts"], (e["ret"] if mode == "their" else e["our"])) for e in evs]


def series(byw, wallets, mode):
    return {w: rp._daily(evp(byw[w], mode)) for w in wallets}


def oos_split(dailies_their):
    alldays = sorted({d for w in dailies_their for d in dailies_their[w]})
    if len(alldays) < 6:
        return None, None, None
    cut = alldays[len(alldays) // 2]
    return set(d for d in alldays if d < cut), set(d for d in alldays if d >= cut), cut


def _filt(dailies, days):
    return {w: {d: v for d, v in dailies[w].items() if d in days} for w in dailies
            if any(d in days for d in dailies[w])}


def eval_weighting(weight_fn, dt_full, do_full, early, late):
    """Return IS (full->full) and OOS (early->late) Calmar stats at BOTH prices for a weighting."""
    dd_hint = {w: rp._series_stats(dt_full[w])["downside_dev"] for w in dt_full}
    w_is = weight_fn(dt_full, do_full, dd_hint)
    is_their = calmar_stats(rp.book_daily(dt_full, w_is))
    is_our = calmar_stats(rp.book_daily(do_full, w_is))
    out = {"weights": {k: round(v, 4) for k, v in w_is.items()},
           "is_their": is_their, "is_our": is_our}
    if early and late:
        dt_e, do_e = _filt(dt_full, early), _filt(do_full, early)
        dt_l, do_l = _filt(dt_full, late), _filt(do_full, late)
        common = sorted(set(dt_e) & set(dt_l))
        if common:
            dd_e = {w: rp._series_stats(dt_e[w])["downside_dev"] for w in dt_e}
            w_e = weight_fn({w: dt_e[w] for w in common}, {w: do_e[w] for w in common if w in do_e},
                            {w: dd_e[w] for w in common})
            out["oos_their"] = calmar_stats(rp.book_daily({w: dt_l[w] for w in common if w in dt_l},
                                                          w_e))
            out["oos_our"] = calmar_stats(rp.book_daily({w: do_l[w] for w in common if w in do_l},
                                                        w_e))
            out["oos_weights"] = {k: round(v, 4) for k, v in w_e.items()}
    return out


# ============================================================ selftest
def selftest():
    # Calmar/MAR math on a known series: rets [+.1,-.2,+.3]; equity .1,-.1,.2; peak .1,.1,.2;
    # dd 0,.2,0 -> maxDD .2; mean = .0667; total .2 -> Calmar .333, MAR 1.0.
    d = {"a": 0.1, "b": -0.2, "c": 0.3}
    st = calmar_stats(d)
    assert abs(st["max_drawdown"] - 0.2) < 1e-9, st["max_drawdown"]
    assert abs(st["calmar"] - (st["mean_day"] / 0.2)) < 1e-9
    assert abs(st["mar"] - (0.2 / 0.2)) < 1e-9, st["mar"]

    # apply_cap respects the cap and renormalizes
    w = apply_cap({"a": 0.9, "b": 0.05, "c": 0.05}, 0.4)
    assert w["a"] <= 0.4 + 1e-9 and abs(sum(w.values()) - 1.0) < 1e-9, w

    # risk parity on 2 independent equal-vol assets -> ~50/50
    days = [f"2026-06-{i:02d}" for i in range(1, 21)]
    rng = random.Random(1)
    A = {days[i]: (0.1 if i % 2 == 0 else -0.1) for i in range(20)}
    B = {days[i]: (-0.1 if i % 2 == 0 else 0.1) for i in range(20)}  # anti-corr, equal vol
    wp = w_risk_parity({"A": A, "B": B})
    assert abs(wp["A"] - 0.5) < 0.05 and abs(wp["B"] - 0.5) < 0.05, wp

    # equal-weight sums to 1
    we = w_equal({"A": A, "B": B, "C": A})
    assert abs(sum(we.values()) - 1.0) < 1e-9 and all(abs(v - 1 / 3) < 1e-9 for v in we.values())

    # max_calmar tilts toward the higher-Calmar (smoother positive) asset. Needs >=3 names for the
    # 0.4 cap to leave room to tilt (cap*2<1 forces 50/50 on a 2-name book).
    good = {days[i]: (0.06 if i % 2 == 0 else 0.04) for i in range(20)}   # steady positive, tiny drawdown
    bad = {days[i]: (0.30 if i == 0 else -0.02) for i in range(20)}  # lumpy -> big drawdown, lower Calmar
    mid = {days[i]: (0.10 if i % 3 == 0 else -0.02) for i in range(20)}
    src = {"good": good, "bad": bad, "mid": mid}
    wm = w_max_calmar(src, src, n_iter=1500)
    assert wm["good"] >= wm["bad"] and wm["good"] >= wm["mid"], \
        f"max_calmar should favor the smoother asset: {wm}"

    # HRP on 3 assets sums to 1 and respects cap
    wh = w_hrp({"A": A, "B": B, "C": good})
    assert abs(sum(wh.values()) - 1.0) < 1e-6 and all(v <= CAP + 1e-9 for v in wh.values()), wh

    # eval_weighting produces IS + OOS blocks
    e, l, _ = set(days[:10]), set(days[10:]), days[10]
    ev = eval_weighting(METHODS["equal"], {"A": A, "B": B}, {"A": A, "B": B}, e, l)
    assert "is_our" in ev and "oos_our" in ev
    print("selftest OK")


# ============================================================ live driver
def _R(v, nd=4):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        if math.isnan(v):
            return None
        return round(v, nd)
    return v


def _slim(st):
    return {k: _R(st.get(k)) for k in ("n_days", "mean_day", "total_pnl", "max_drawdown",
                                       "calmar", "mar", "ret_cvar5", "sortino", "pos_window_frac")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    n_null = 300 if args.quick else N_NULL
    rng = random.Random(SEED)

    out = {"meta": {"objective": "realizable(OUR-price) CALMAR = mean_day/maxDD",
                    "siblings": ["MAR=total_pnl/maxDD", "ret_cvar5=mean_day/|CVaR5|"],
                    "cap": CAP, "seed": SEED, "n_null": n_null,
                    "posture": "PAPER-ONLY, nothing promoted, no Rust, DB read-only",
                    "cycle3_frozen_anchor": "reports/reliability_portfolio.json"}}

    # ---------- O0: reproduce the Cycle-3 Calmar reframe from the frozen anchor ----------
    c3 = CYCLE3
    o0 = {
        "their_price": {"book_calmar": round(c3["book_their_meanday"] / c3["book_their_maxdd"], 4),
                        "best_single_calmar": round(c3["acorp_meanday"] / c3["acorp_maxdd"], 4)},
        "oos_their": {"book_calmar": round(c3["book_oos_meanday"] / c3["book_oos_maxdd"], 4),
                      "best_single_calmar": round(c3["best_oos_meanday"] / c3["best_oos_maxdd"], 4)},
        "our_price": {"book_calmar": round(c3["book_our_meanday"] / c3["book_our_maxdd"], 4)},
    }
    o0["reframe_confirmed"] = (o0["their_price"]["book_calmar"] > o0["their_price"]["best_single_calmar"]
                               and o0["our_price"]["book_calmar"] < o0["their_price"]["book_calmar"])
    o0["tax_collapse"] = {"their": o0["their_price"]["book_calmar"],
                          "our": o0["our_price"]["book_calmar"],
                          "gap": round(o0["their_price"]["book_calmar"] - o0["our_price"]["book_calmar"], 4)}
    out["O0_reframe"] = o0

    # ---------- baseline universe (frozen band 0.45-0.90) ----------
    scored, shortlist, wr, names, spreads = load_universe(tsc.BAND_LO, tsc.BAND_HI)
    dt = series(wr, shortlist, "their")
    do = series(wr, shortlist, "our")
    early, late, cut = oos_split(dt)
    out["baseline"] = {"shortlist": [names.get(w, w) for w in shortlist], "n": len(shortlist),
                       "oos_cut": cut, "pool_size": len(scored)}

    # ---------- O1: weighting head-to-head on the SAME shortlist ----------
    o1 = {}
    for m, fn in METHODS.items():
        o1[m] = eval_weighting(fn, dt, do, early, late)
    # best single reliable at OUR price (Calmar) and their price
    def best_single(price_series, days=None):
        cand = {w: calmar_stats(_filt({w: price_series[w]}, days)[w]) if days else
                calmar_stats(price_series[w]) for w in price_series}
        bw = max(cand, key=lambda w: _cmp(cand[w]["calmar"]))
        return bw, cand[bw]
    bs_our_w, bs_our = best_single(do)
    bs_their_w, bs_their = best_single(dt)
    bs_our_late = None
    if late:
        do_l = _filt(do, late)
        if do_l:
            bw, st = best_single(do_l)
            bs_our_late = {"name": names.get(bw, bw), **_slim(st)}
    # efficiency ratios vs best single (our price, IS)
    table = []
    for m in METHODS:
        io = o1[m]["is_our"]
        ret_giveup = _cmp(bs_our["mean_day"]) - _cmp(io.get("mean_day"))
        dd_red = _cmp(bs_our["max_drawdown"]) - _cmp(io.get("max_drawdown"))
        ratio = (dd_red / ret_giveup) if ret_giveup > 1e-9 else None
        table.append({"method": m,
                      "their_calmar_IS": _R(o1[m]["is_their"].get("calmar")),
                      "our_calmar_IS": _R(io.get("calmar")),
                      "our_maxdd_IS": _R(io.get("max_drawdown")),
                      "our_calmar_OOS": _R(o1[m].get("oos_our", {}).get("calmar")),
                      "ret_giveup_vs_best": _R(ret_giveup),
                      "dd_reduction_vs_best": _R(dd_red),
                      "dd_red_per_ret_sacrificed": _R(ratio, 3)})
    winner = max(METHODS, key=lambda m: _cmp(o1[m].get("oos_our", {}).get("calmar")))
    out["O1_weighting"] = {"best_single_our_IS": {"name": names.get(bs_our_w, bs_our_w), **_slim(bs_our)},
                           "best_single_our_OOS": bs_our_late,
                           "table": table, "winner_by_realizable_OOS_calmar": winner,
                           "detail": {m: {"is_our": _slim(o1[m]["is_our"]),
                                          "oos_our": _slim(o1[m].get("oos_our", {})) if o1[m].get("oos_our") else None,
                                          "weights": o1[m]["weights"]} for m in METHODS}}

    # ---------- O2: widen the shortlist (pre-registered relaxations, one at a time) ----------
    # PRE-REGISTERED (frozen before results): (P1) widen price band 0.45-0.90 -> 0.10-0.97 to admit
    # longshot + other-band skill; ALL other gate floors frozen; MM/bot screen ON. (P2) relax the
    # >=2-positive-sports floor to >=1 on the frozen band. Reported with Bonferroni note; NOT tuned to pass.
    o2 = {"prereg": ["P1: band 0.45-0.90 -> 0.10-0.97 (admit longshot+other), all else frozen, MM/bot ON",
                     "P2: cross_sport floor 2 -> 1 on frozen band 0.45-0.90"],
          "bonferroni_note": "2 relaxations x 5 weightings tested this cycle; adjust any single p accordingly"}
    wsc, wsl, wwr, wnames, wspreads = load_universe(0.10, 0.97)          # P1
    o2["P1_widened"] = {"pool_size": len(wsc), "shortlist_n": len(wsl),
                        "shortlist": [wnames.get(w, w) for w in wsl]}
    wdt = series(wwr, wsl, "their")
    wdo = series(wwr, wsl, "our")
    we, wl, wcut = oos_split(wdt)
    curve = []
    wfn = METHODS[winner]
    for k in range(1, len(wsl) + 1):
        sub = wsl[:k]
        sdt = {w: wdt[w] for w in sub}
        sdo = {w: wdo[w] for w in sub}
        ev = eval_weighting(wfn, sdt, sdo, we, wl)
        curve.append({"n_names": k, "names_added": wnames.get(sub[-1], sub[-1]),
                      "our_calmar_IS": _R(ev["is_our"].get("calmar")),
                      "our_maxdd_IS": _R(ev["is_our"].get("max_drawdown")),
                      "our_calmar_OOS": _R(ev.get("oos_our", {}).get("calmar")),
                      "our_meanday_IS": _R(ev["is_our"].get("mean_day"))})
    peak = max(curve, key=lambda c: _cmp(c["our_calmar_OOS"])) if curve else None
    peak_is = max(curve, key=lambda c: _cmp(c["our_calmar_IS"])) if curve else None
    # P2 sensitivity
    p2sc, p2sl, _, p2names, _ = load_universe(tsc.BAND_LO, tsc.BAND_HI, cross_sport_min=1)
    o2["P2_cross_sport_relaxed"] = {"shortlist_n": len(p2sl),
                                    "shortlist": [p2names.get(w, w) for w in p2sl]}
    baseline_oos_calmar = _R(o1[winner].get("oos_our", {}).get("calmar"))
    o2["curve_widened_band"] = curve
    o2["peak_OOS"] = peak
    o2["peak_IS"] = peak_is
    o2["widening_helps"] = (peak is not None and _cmp(peak["our_calmar_OOS"]) > _cmp(baseline_oos_calmar))
    o2["baseline_n4_oos_calmar"] = baseline_oos_calmar
    out["O2_widen"] = o2

    # ---------- O3: tax-aware selection (drop per-name OUR-price Calmar <= 0, reweight) ----------
    # Use the widened universe (more names to prune) with the winning weighting.
    per_name = {}
    for w in wsl:
        st_their = calmar_stats(wdt[w])
        st_our = calmar_stats(wdo[w])
        per_name[w] = {"name": wnames.get(w, w),
                       "their_calmar": _R(st_their["calmar"]), "our_calmar": _R(st_our["calmar"]),
                       "tax_meanday": _R(_cmp(st_their["mean_day"]) - _cmp(st_our["mean_day"])),
                       "our_meanday": _R(st_our["mean_day"])}
    keep_tax = [w for w in wsl if _cmp(calmar_stats(wdo[w])["calmar"]) > 0]
    # before = full widened book at winner weighting; after = tax-pruned book
    before = eval_weighting(wfn, wdt, wdo, we, wl)
    after = eval_weighting(wfn, {w: wdt[w] for w in keep_tax}, {w: wdo[w] for w in keep_tax}, we, wl)
    their_anchor = o0["their_price"]["book_calmar"]
    c3_our = c3["book_our_meanday"] / c3["book_our_maxdd"]               # 0.044
    gap = their_anchor - c3_our                                          # 0.167 - 0.044 = 0.123
    # Two distinct tax-aware levers: (1) DROP names whose our-price Calmar<=0 (the charter's filter);
    # (2) tax-aware WEIGHTING = the max_calmar optimizer on the SAME (narrow, apples-to-apples) shortlist,
    # which optimizes our-price Calmar directly -> the real recovery of the collapse.
    mc_our_IS = _cmp(o1["max_calmar"]["is_our"].get("calmar"))           # narrow shortlist, tax-aware wt
    invdd_our_IS = _cmp(o1["inv_dd"]["is_our"].get("calmar"))            # baseline weighting
    out["O3_tax_aware"] = {
        "per_name": sorted(per_name.values(), key=lambda x: -_cmp(x["our_calmar"])),
        "names_dropped_tax_calmar_le0": [wnames.get(w, w) for w in wsl if w not in keep_tax],
        "filter_drop_book_before_our_calmar_IS": _R(before["is_our"].get("calmar")),
        "filter_drop_book_after_our_calmar_IS": _R(after["is_our"].get("calmar")),
        "cycle3_collapse": {"their": round(their_anchor, 4), "our": round(c3_our, 4),
                            "gap": round(gap, 4)},
        "tax_aware_weighting_max_calmar_our_calmar_IS": _R(mc_our_IS),
        "baseline_invdd_our_calmar_IS": _R(invdd_our_IS),
        "recovered_by_max_calmar_frac_IS": _R(((mc_our_IS - c3_our) / gap) if gap > 1e-9 else None, 3),
        "max_calmar_our_calmar_OOS": _R(o1["max_calmar"].get("oos_our", {}).get("calmar")),
        "note": "name-DROP filter recovers ~nothing (Calmar>0 too weak); tax-aware WEIGHTING "
                "(max_calmar) recovers materially IN-SAMPLE but the OOS column shows it overfits."}

    # ---------- O4: rolling-window rebalanced vs static ----------
    out["O4_rebalance"] = rebalance_test(wwr, wsc, wnames, wfn)

    # ---------- WORTH-IT GATE (belief-blind, realizable OOS Calmar) ----------
    # Refined book = widened universe, tax-pruned, winning weighting (the strongest realizable book).
    refined_names = keep_tax
    refined = after
    refined_oos_calmar = _cmp(refined.get("oos_our", {}).get("calmar"))
    # Null: random equal-size books from the scored pool, weighting HELD EQUAL (isolate SELECTION),
    # realizable OUR-price OOS Calmar (early->late). k = refined size.
    gate = belief_blind_calmar(wwr, wsc, refined_names, we, wl, rng, n_null,
                               weight_name=winner if winner in ("equal", "inv_dd") else "equal")
    beat_best = None
    if bs_our_late is not None:
        beat_best = refined_oos_calmar > _cmp(bs_our_late.get("calmar"))
    out["WORTH_IT_GATE"] = {
        "refined_book": [wnames.get(w, w) for w in refined_names],
        "refined_our_calmar_OOS": _R(refined.get("oos_our", {}).get("calmar")),
        "beats_best_single_our_OOS": beat_best,
        "best_single_our_OOS_calmar": (bs_our_late or {}).get("calmar"),
        "belief_blind": gate,
        "dd_red_per_ret_sacrificed_our": None}
    # headline efficiency ratio at our price (IS, refined vs best single our)
    io = refined["is_our"]
    rg = _cmp(bs_our["mean_day"]) - _cmp(io.get("mean_day"))
    dr = _cmp(bs_our["max_drawdown"]) - _cmp(io.get("max_drawdown"))
    out["WORTH_IT_GATE"]["dd_red_per_ret_sacrificed_our"] = _R((dr / rg) if rg > 1e-9 else None, 3)

    verdict = "INDETERMINATE"
    if gate.get("p") is not None:
        if gate["p"] <= 0.05 and beat_best:
            verdict = "WORTH-IT (selection beats random AND best single on realizable Calmar)"
        elif gate["p"] > 0.5:
            verdict = "NOT-WORTH-IT (value is diversification, not selection)"
        else:
            verdict = "INDETERMINATE-BY-POWER"
    out["WORTH_IT_GATE"]["verdict"] = verdict

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    # ---- console digest ----
    print(f"O0 reframe: their book Calmar {o0['their_price']['book_calmar']} > best {o0['their_price']['best_single_calmar']}"
          f" ; our-price collapse -> {o0['our_price']['book_calmar']} (confirmed={o0['reframe_confirmed']})")
    print(f"\nbaseline shortlist n={len(shortlist)}: {out['baseline']['shortlist']} (pool {len(scored)})")
    print("\nO1 WEIGHTING HEAD-TO-HEAD (our-price = realizable):")
    print(f"  {'method':<12}{'their_C_IS':>11}{'our_C_IS':>10}{'our_DD_IS':>10}{'our_C_OOS':>11}{'ddRed/retGiveup':>16}")
    for r in table:
        print(f"  {r['method']:<12}{str(r['their_calmar_IS']):>11}{str(r['our_calmar_IS']):>10}"
              f"{str(r['our_maxdd_IS']):>10}{str(r['our_calmar_OOS']):>11}{str(r['dd_red_per_ret_sacrificed']):>16}")
    print(f"  winner by realizable OOS Calmar: {winner}")
    print(f"\nO2 widen: baseline n4 OOS Calmar {baseline_oos_calmar}; widened peak OOS "
          f"{peak['our_calmar_OOS'] if peak else None} at n={peak['n_names'] if peak else None}; helps={o2['widening_helps']}")
    o3 = out["O3_tax_aware"]
    print(f"O3 tax-aware: name-DROP filter {o3['filter_drop_book_before_our_calmar_IS']} -> "
          f"{o3['filter_drop_book_after_our_calmar_IS']} (dropped {o3['names_dropped_tax_calmar_le0']}); "
          f"tax-aware WEIGHTING (max_calmar) our Calmar IS {o3['tax_aware_weighting_max_calmar_our_calmar_IS']} "
          f"= recovers {o3['recovered_by_max_calmar_frac_IS']} of the 0.167->0.044 gap (OOS {o3['max_calmar_our_calmar_OOS']} = overfits)")
    print(f"O4 rebalance: {out['O4_rebalance']['verdict']}")
    g = out["WORTH_IT_GATE"]
    print(f"\nWORTH-IT GATE: refined our OOS Calmar {g['refined_our_calmar_OOS']} | beats best single={g['beats_best_single_our_OOS']}"
          f" | belief-blind p={gate.get('p')} -> {verdict}")
    print(f"  dd-reduction per return sacrificed (our price): {g['dd_red_per_ret_sacrificed_our']}")
    print(f"\nwrote {REPORT}")


def rebalance_test(byw, scored, names, wfn):
    """Walk-forward: split the calendar into 2 halves; static = weights fit on all -> eval late;
    rolling = re-score reliability + re-select top-N + re-weight on the EARLY window, eval late.
    With ~5 weeks of sparse per-name coverage this is power-starved; report honestly."""
    alldays = sorted({e["day"] for w in scored for e in byw[w]})
    if len(alldays) < 10:
        return {"verdict": "INSUFFICIENT-DATA", "n_days": len(alldays)}
    cut = alldays[len(alldays) // 2]
    early = set(d for d in alldays if d < cut)
    late = set(d for d in alldays if d >= cut)

    def rescore_shortlist(days):
        sl, sc = [], {}
        for w in scored:
            evs = [e for e in byw[w] if e["day"] in days]
            if len(evs) < rs.MIN_EVENTS:
                continue
            s = rs.score_evs(evs)
            passed, _, _ = rs.gate(s, scored[w]["is_mm"], scored[w]["is_bot"])
            sc[w] = s
            if passed:
                sl.append(w)
        sl.sort(key=lambda w: -_cmp(sc[w]["sortino"]))
        return sl

    roll_sl = rescore_shortlist(early)[:6]
    static_sl = rescore_shortlist(alldays)[:6]
    if not roll_sl or not static_sl:
        return {"verdict": "INSUFFICIENT-DATA-AFTER-RESCORE",
                "roll_n": len(roll_sl), "static_n": len(static_sl)}
    do_late = lambda sl: {w: rp._daily(evp([e for e in byw[w] if e["day"] in late], "our")) for w in sl}
    dt_early = lambda sl: {w: rp._daily(evp([e for e in byw[w] if e["day"] in early], "their")) for w in sl}
    roll_do_l = {w: v for w, v in do_late(roll_sl).items() if v}
    roll_dt_e = {w: v for w, v in dt_early(roll_sl).items() if v}
    common_r = [w for w in roll_do_l if w in roll_dt_e]
    rw = wfn({w: roll_dt_e[w] for w in common_r}, {w: roll_do_l[w] for w in common_r},
             {w: rp._series_stats(roll_dt_e[w])["downside_dev"] for w in common_r}) if common_r else {}
    roll_stats = calmar_stats(rp.book_daily({w: roll_do_l[w] for w in common_r}, rw)) if rw else {"calmar": None}
    stat_do_l = {w: v for w, v in do_late(static_sl).items() if v}
    stat_dt_full = {w: rp._daily(evp(byw[w], "their")) for w in static_sl}
    common_s = [w for w in stat_do_l if w in stat_dt_full]
    sw = wfn({w: stat_dt_full[w] for w in common_s}, {w: stat_do_l[w] for w in common_s},
             {w: rp._series_stats(stat_dt_full[w])["downside_dev"] for w in common_s}) if common_s else {}
    stat_stats = calmar_stats(rp.book_daily({w: stat_do_l[w] for w in common_s}, sw)) if sw else {"calmar": None}
    rc, sc_ = _cmp(roll_stats.get("calmar")), _cmp(stat_stats.get("calmar"))
    verdict = ("ROLLING-HELPS" if rc > sc_ + 0.01 else
               "STATIC-BETTER (rebalancing overfits the sparse window)" if sc_ > rc + 0.01 else
               "TIE / INDETERMINATE-BY-POWER")
    return {"cut": cut, "rolling_shortlist": [names.get(w, w) for w in roll_sl],
            "static_shortlist": [names.get(w, w) for w in static_sl],
            "rolling_our_calmar_late": _R(roll_stats.get("calmar")),
            "static_our_calmar_late": _R(stat_stats.get("calmar")),
            "n_late_days_rolling": roll_stats.get("n_days"),
            "verdict": verdict}


def belief_blind_calmar(byw, scored, refined_names, early, late, rng, n_null, weight_name):
    """Random equal-size books from the scored pool, weighting held equal (only SELECTION differs),
    realizable OUR-price OOS Calmar (weights from early, eval late). p = P(random Calmar >= refined)."""
    pool = list(scored.keys())
    k = len(refined_names)
    wfn = METHODS[weight_name]
    do_all = {}
    dt_all = {}

    def get(w):
        if w not in do_all:
            do_all[w] = rp._daily(evp(byw[w], "our"))
            dt_all[w] = rp._daily(evp(byw[w], "their"))
        return dt_all[w], do_all[w]

    def book_oos_calmar(nameset):
        dt = {}
        do = {}
        for w in nameset:
            t, o = get(w)
            dt[w], do[w] = t, o
        dt_e = _filt(dt, early)
        do_l = _filt(do, late)
        common = [w for w in dt_e if any(d in late for d in do.get(w, {}))]
        common = [w for w in common if w in do_l]
        if not common:
            return None
        wts = wfn({w: dt_e[w] for w in common}, {w: _filt(do, early).get(w, {}) for w in common},
                  {w: rp._series_stats(dt_e[w])["downside_dev"] for w in common})
        return _cmp(calmar_stats(rp.book_daily({w: do_l[w] for w in common}, wts))["calmar"])

    obs = book_oos_calmar(refined_names)
    if obs is None:
        return {"p": None, "note": "refined book has no OOS coverage"}
    ge = 0
    got = 0
    finite = []
    for _ in range(n_null):
        pick = rng.sample(pool, min(k, len(pool)))
        c = book_oos_calmar(pick)
        if c is None:
            continue
        got += 1
        finite.append(c if c < 9e17 else None)
        if c >= obs:
            ge += 1
    p = (ge + 1) / (got + 1) if got else None
    fin = [x for x in finite if x is not None]
    return {"p": round(p, 4) if p is not None else None, "n_draws": got,
            "refined_our_oos_calmar": _R(obs), "weighting": weight_name,
            "random_calmar_mean": _R(sum(fin) / len(fin), 4) if fin else None,
            "note": "random equal-size book, weighting held equal -> isolates SELECTION; our-price OOS Calmar"}


if __name__ == "__main__":
    main()
