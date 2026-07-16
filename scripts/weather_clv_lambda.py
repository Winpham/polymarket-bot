#!/usr/bin/env python3
"""
WEATHER CLV / λ INSTRUMENT — compute, for the FIRST TIME, the information fraction λ of the weather arm.

The single most important missing test in the whole investigation. λ = CLV / surplus tells us whether
the weather-favourite edge is INFORMATION the market later confirms (bankable) or a static
favourite-longshot / variance premium (the mirage that loses real money). Every prior arm that got this
test read λ≈0 (champion indeterminate @16% coverage, collapse λ=0.000).

DATA REALITY (from the §1 census, 2026-07-15):
  * weather markets are INTL-only (0/643 join the US DMR) ⇒ the official settlement label IS the
    Polymarket CLOB resolution `outcome_won` (highest-temperature markets resolve to the observed high).
  * `signal_price_trajectory` coverage for weather_fav = 0% ⇒ the clv_lambda.py trajectory route is
    DEAD for weather. There is no captured pre-resolution mid in the DB.
  * The ONLY route to a close price is the public CLOB `prices-history` endpoint (same source
    atfire_recon.py uses). Per the hard rule (§3.1 / brief rule 4) we may NOT run any λ/null on an
    unvalidated price source: this script VALIDATES the endpoint against the arm's now-captured real
    `entry_ask_mid` (203 rows, absent at the 07-12 atfire_recon run — which is why that one failed at
    MAE 22¢ validating against the STRUCTURALLY-ABSENT `_blind` weather mid) BEFORE computing anything.

WEATHER-SPECIFIC HAZARD (stated up front, mirrors the phase-9 finalhour correction):
  A weather market's price converges to 0/1 as the day's high is REVEALED through the resolution day.
  A "close" mid of 0.98 the evening of resolution is hindsight, not a forecast. So λ measured at the
  last-non-degenerate tick OVERSTATES information. We therefore measure λ at CONTROLLED horizons before
  resolution (res − H) and report the whole trajectory. The honest λ is the one at a FAIR tradeable
  lead, not the degenerate last tick.

CLV basis (frozen): mid-to-mid, so the spread/fee (a separate cost, bar #4) does not contaminate the
information test.
  entry_mid = captured `entry_ask_mid` (the real CLOB mid at decision; validated against recon).
  close_mid(H) = reconstructed mid nearest (res_ts − H), degenerate-guarded to [GLO, GHI].
  surplus = won − entry_mid ; CLV(H) = close_mid(H) − entry_mid ; resid(H) = won − close_mid(H).
  λ(H) = clustered_mean(CLV) / clustered_mean(surplus), day-clustered, bootstrap CI.

Usage:
  ./weather_clv_lambda.py --build      # fetch+cache prices-history for resolved weather_fav
  ./weather_clv_lambda.py              # validate + measure; writes reports/clv_lambda_weather.json
  ./weather_clv_lambda.py --selftest
"""
import argparse
import csv
import io
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from math import sqrt
from pathlib import Path

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
CLOB = "https://clob.polymarket.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) polymarket-bot/weather-clv"
GLO, GHI = 0.02, 0.98               # degenerate-price guard
BAND_LO, BAND_HI = 0.71, 0.90       # primary certification band
DRAWS = 2000
SEED = 20260715
COVERAGE_BAR = 0.50
REPORTS = Path(__file__).resolve().parent.parent / "reports"
CACHE = REPORTS / "cache_weather_prices"
# Controlled pre-resolution horizons (hours). "last" = last non-degenerate tick (overstates, shown for
# comparison to the collapse/champion method). Entry-anchored surplus is horizon-independent.
HORIZONS_H = [24, 12, 6, 3, 2, 1]

SIG_SQL = """
SELECT condition_id, outcome_index,
       initial_mean_price AS imp,
       entry_ask_mid AS ask_mid,
       entry_ask AS ask,
       EXTRACT(epoch FROM entry_ask_at)::bigint AS ask_ts,
       EXTRACT(epoch FROM resolved_at)::bigint  AS res_ts,
       (outcome_won::int) AS won,
       to_char(resolved_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals
WHERE strategy='weather_fav' AND resolved AND outcome_won IS NOT NULL
  AND entry_ask_mid IS NOT NULL AND entry_ask_at IS NOT NULL AND resolved_at IS NOT NULL
"""


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def _get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(0.5 * (attempt + 1))
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None


def fetch_signals():
    rows = []
    for r in q(SIG_SQL):
        rows.append({
            "cond": r["condition_id"], "oi": int(r["outcome_index"]),
            "imp": float(r["imp"]) if r["imp"] not in (None, "") else None,
            "ask_mid": float(r["ask_mid"]), "ask": float(r["ask"]) if r["ask"] not in (None, "") else None,
            "ask_ts": int(r["ask_ts"]), "res_ts": int(r["res_ts"]),
            "won": int(r["won"]), "day": r["day"],
        })
    return rows


def cache_file(cond, oi):
    return CACHE / f"{cond}_{oi}.json"


def build_cache(rows, workers=8):
    CACHE.mkdir(parents=True, exist_ok=True)

    def one(p):
        cf = cache_file(p["cond"], p["oi"])
        if cf.exists():
            return "cached"
        mkt = _get(f"{CLOB}/markets/{p['cond']}")
        if not mkt:
            cf.write_text(json.dumps({"err": "no_market"}))
            return "no_market"
        toks = mkt.get("tokens") or []
        if p["oi"] >= len(toks):
            cf.write_text(json.dumps({"err": "oi_oob", "ntok": len(toks)}))
            return "oi_oob"
        tok = toks[p["oi"]].get("token_id")
        outcome = toks[p["oi"]].get("outcome")
        if not tok:
            cf.write_text(json.dumps({"err": "no_token"}))
            return "no_token"
        hist = _get(f"{CLOB}/prices-history?market={tok}&interval=max&fidelity=1")
        h = (hist or {}).get("history") or []
        cf.write_text(json.dumps({"outcome": outcome, "history": h}))
        return "ok" if h else "empty"

    counts = defaultdict(int)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(one, rows):
            counts[res] += 1
    return dict(counts)


def load_hist(cond, oi):
    cf = cache_file(cond, oi)
    if not cf.exists():
        return None
    d = json.loads(cf.read_text())
    if "history" not in d:
        return None
    return d["history"]


def mid_at(hist, ts, max_slip_min=90, direction="after"):
    """Mid nearest ts. direction 'after' = first tick >= ts (for entry validation);
    'before' = last tick <= ts (for close). Degenerate ticks allowed here; caller guards.
    Returns (t, p) or None if no tick within max_slip."""
    if not hist:
        return None
    best = None
    for tick in hist:
        t = tick.get("t")
        p = tick.get("p")
        if t is None or p is None:
            continue
        if direction == "after":
            if t >= ts and (best is None or t < best[0]):
                best = (t, float(p))
        else:  # before
            if t <= ts and (best is None or t > best[0]):
                best = (t, float(p))
    if best is None:
        return None
    if abs(best[0] - ts) > max_slip_min * 60:
        return None
    return best


def close_mid(hist, res_ts, horizon_h):
    """The degenerate-guarded market mid at (res_ts - horizon_h). horizon_h=None ⇒ last non-degen tick.
    Returns close price or None."""
    if not hist:
        return None
    if horizon_h is None:
        cand = [(t["t"], float(t["p"])) for t in hist
                if t.get("t") is not None and t.get("p") is not None
                and t["t"] <= res_ts and GLO <= float(t["p"]) <= GHI]
        if not cand:
            return None
        cand.sort()
        return cand[-1][1]
    target = res_ts - horizon_h * 3600
    got = mid_at(hist, target, max_slip_min=180, direction="before")
    if got is None:
        # allow the nearest tick after the target too, within slip
        got = mid_at(hist, target, max_slip_min=180, direction="after")
    if got is None:
        return None
    p = got[1]
    return p if GLO <= p <= GHI else None


# ---- clustered stats ---------------------------------------------------------------------------
def clustered_mean(pairs):
    m = defaultdict(list)
    for ev, v in pairs:
        m[ev].append(v)
    if not m:
        return float("nan"), 0
    means = [sum(v) / len(v) for v in m.values()]
    return sum(means) / len(means), len(means)


def boot_ci(day_vals, stat_fn, rng, n=DRAWS, alpha=0.05):
    keys = list(day_vals.keys())
    if not keys:
        return (float("nan"), float("nan"))
    draws = []
    for _ in range(n):
        sample = [keys[rng.randrange(len(keys))] for _ in keys]
        v = stat_fn(sample)
        if v == v:
            draws.append(v)
    draws.sort()
    if not draws:
        return (float("nan"), float("nan"))
    lo = draws[int(alpha / 2 * len(draws))]
    hi = draws[int((1 - alpha / 2) * len(draws)) - 1]
    return lo, hi


def validate_source(rows):
    """Reconstruct the entry mid at ask_ts and compare to the captured entry_ask_mid."""
    errs = []
    for p in rows:
        hist = load_hist(p["cond"], p["oi"])
        got = mid_at(hist, p["ask_ts"], max_slip_min=90, direction="after") if hist else None
        if got is None:
            got = mid_at(hist, p["ask_ts"], max_slip_min=90, direction="before") if hist else None
        if got is None:
            continue
        errs.append((p, got[1] - p["ask_mid"]))
    n = len(errs)
    if n == 0:
        return {"n": 0, "verdict": "NO OVERLAP"}
    e = [x for _, x in errs]
    mae = sum(abs(x) for x in e) / n
    bias = sum(e) / n
    mx = sum(mid_at(load_hist(p["cond"], p["oi"]), p["ask_ts"], 90, "after")[1]
             if mid_at(load_hist(p["cond"], p["oi"]), p["ask_ts"], 90, "after") else 0 for p, _ in errs)  # noqa
    # correlation recon vs captured
    R = [(mid_at(load_hist(p["cond"], p["oi"]), p["ask_ts"], 90, "after")
          or mid_at(load_hist(p["cond"], p["oi"]), p["ask_ts"], 90, "before"))[1] for p, _ in errs]
    Cm = [p["ask_mid"] for p, _ in errs]
    rm, cm = sum(R) / n, sum(Cm) / n
    cov = sum((R[i] - rm) * (Cm[i] - cm) for i in range(n))
    vr = sqrt(sum((x - rm) ** 2 for x in R)); vc = sqrt(sum((x - cm) ** 2 for x in Cm))
    corr = cov / (vr * vc) if vr > 0 and vc > 0 else 0.0
    ok = mae <= 0.03 and abs(bias) <= 0.01 and corr >= 0.90
    return {"n": n, "mae": round(mae, 4), "bias": round(bias, 4), "corr": round(corr, 3),
            "acceptance": "mae<=0.03 & |bias|<=0.01 & corr>=0.90",
            "accepted": ok,
            "verdict": "ACCEPT — endpoint tracks captured entry_ask_mid" if ok
            else "REJECT — endpoint does not track captured mid"}


def measure_lambda(rows, entry_key, horizon_h, rng):
    """λ at a given horizon using entry_key ('ask_mid' or 'imp')."""
    usable = []
    for p in rows:
        hist = load_hist(p["cond"], p["oi"])
        if not hist:
            continue
        entry = p.get(entry_key)
        if entry is None:
            continue
        c = close_mid(hist, p["res_ts"], horizon_h)
        if c is None:
            continue
        usable.append({"ev": p["day"], "entry": entry, "close": c, "won": p["won"]})
    n = len(usable)
    if n == 0:
        return {"horizon_h": horizon_h, "n": 0, "coverage": 0.0}
    coverage = n / len(rows)
    surplus = [(u["ev"], u["won"] - u["entry"]) for u in usable]
    clv = [(u["ev"], u["close"] - u["entry"]) for u in usable]
    resid = [(u["ev"], u["won"] - u["close"]) for u in usable]
    m_sur, ndays = clustered_mean(surplus)
    m_clv, _ = clustered_mean(clv)
    m_res, _ = clustered_mean(resid)
    # per-day maps
    day_clv = defaultdict(list); day_sur = defaultdict(list)
    for ev, v in clv: day_clv[ev].append(v)
    for ev, v in surplus: day_sur[ev].append(v)
    days = {d: (sum(day_clv[d]) / len(day_clv[d]), sum(day_sur[d]) / len(day_sur[d])) for d in day_clv}

    def clv_of(keys):
        return sum(days[k][0] for k in keys) / len(keys)

    def lam_of(keys):
        c = sum(days[k][0] for k in keys) / len(keys)
        d = sum(days[k][1] for k in keys) / len(keys)
        return (c / d) if d > 0 else float("nan")

    clv_lo, clv_hi = boot_ci(days, clv_of, rng)
    lam_lo, lam_hi = boot_ci(days, lam_of, rng)
    p_clv_le0 = None  # one-sided: fraction of bootstrap CLV draws <= 0
    keys = list(days.keys())
    neg = 0; tot = 0
    for _ in range(DRAWS):
        s = [keys[rng.randrange(len(keys))] for _ in keys]
        v = clv_of(s)
        if v == v:
            tot += 1; neg += (v <= 0)
    p_clv_le0 = neg / tot if tot else float("nan")
    lam_hat = (m_clv / m_sur) if m_sur > 0 else float("nan")
    return {
        "horizon_h": horizon_h, "n": n, "n_days": ndays, "coverage": round(coverage, 3),
        "mean_surplus": round(m_sur, 4), "mean_clv": round(m_clv, 4), "mean_resid": round(m_res, 4),
        "clv_ci": [round(clv_lo, 4), round(clv_hi, 4)], "p_clv_le0": round(p_clv_le0, 3),
        "lambda_hat": round(lam_hat, 3) if lam_hat == lam_hat else None,
        "lambda_ci": [round(lam_lo, 3) if lam_lo == lam_lo else None,
                      round(lam_hi, 3) if lam_hi == lam_hi else None],
    }


def run(band_only=True):
    rows = fetch_signals()
    if band_only:
        rows = [r for r in rows if r["imp"] is not None and BAND_LO <= r["imp"] < BAND_HI]
    rng = random.Random(SEED)
    val = validate_source(rows)
    out = {"n_signals": len(rows), "band": [BAND_LO, BAND_HI] if band_only else "all",
           "validation": val, "horizons": {}}
    if not val.get("accepted"):
        out["verdict"] = ("PRICE SOURCE UNVALIDATED — λ NOT COMPUTED (hard rule 4). "
                          f"{val.get('verdict')}")
        return out
    # last-non-degen (overstates) + controlled horizons, both entry bases
    for label, hz in [("last", None)] + [(f"{h}h", h) for h in HORIZONS_H]:
        out["horizons"][label] = {
            "ask_mid_basis": measure_lambda(rows, "ask_mid", hz, random.Random(SEED)),
            "imp_basis": measure_lambda(rows, "imp", hz, random.Random(SEED)),
        }
    # headline λ = the fairest tradeable horizon with >=50% coverage, ask_mid basis
    headline = None
    for h in ["6h", "3h", "2h", "12h", "1h", "24h", "last"]:
        m = out["horizons"][h]["ask_mid_basis"]
        if m.get("coverage", 0) >= COVERAGE_BAR:
            headline = {"horizon": h, **m}
            break
    out["headline_lambda"] = headline
    if headline:
        lb = headline["lambda_ci"][0]
        passes = (lb is not None and lb > 0 and headline["coverage"] >= COVERAGE_BAR
                  and headline["p_clv_le0"] < 0.05)
        out["bar2_pass"] = passes
        out["verdict"] = (
            f"λ={headline['lambda_hat']} CI[{headline['lambda_ci'][0]},{headline['lambda_ci'][1]}] "
            f"@ {headline['coverage']:.0%} cov, horizon={headline['horizon']}, "
            f"CLV p(≤0)={headline['p_clv_le0']} ⇒ BAR#2 " + ("PASS" if passes else "FAIL"))
    return out


def selftest():
    ok = True
    # close_mid: last-non-degen excludes the degenerate 0.995 print
    h = [{"t": 100, "p": 0.80}, {"t": 200, "p": 0.90}, {"t": 300, "p": 0.995}]
    if close_mid(h, 400, None) != 0.90:
        print("FAIL close_mid last-non-degen"); ok = False
    # close_mid at horizon picks the pre-target tick
    if close_mid(h, 400, None) != 0.90:
        ok = ok
    got = close_mid([{"t": 100, "p": 0.80}, {"t": 400, "p": 0.90}], 460, horizon_h=None)
    if got != 0.90:
        print("FAIL close_mid horizon-none"); ok = False
    # mid_at after/before
    if mid_at(h, 150, 10, "after") != (200, 0.90):
        print("FAIL mid_at after"); ok = False
    if mid_at(h, 250, 10, "before") != (200, 0.90):
        print("FAIL mid_at before"); ok = False
    # clustered mean
    m, nd = clustered_mean([("d1", 0.1), ("d1", 0.3), ("d2", 0.2)])
    if abs(m - 0.2) > 1e-9 or nd != 2:
        print("FAIL clustered_mean"); ok = False
    print("weather_clv_lambda selftest: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--all-bands", action="store_true", help="measure on 0.71-0.98 not just 0.71-0.90")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(selftest())
    if a.build:
        rows = fetch_signals()
        print(f"building price cache for {len(rows)} resolved weather_fav signals...")
        print(json.dumps(build_cache(rows)))
        return
    res = run(band_only=not a.all_bands)
    print(json.dumps(res, indent=2))
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / "clv_lambda_weather.json"
    path.write_text(json.dumps(res, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
