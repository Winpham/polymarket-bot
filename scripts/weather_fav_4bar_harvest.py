#!/usr/bin/env python3
"""
weather_fav — the 4-bar gauntlet on the HARVEST-TAPE edge window (independent, higher-powered, OFFLINE).

The committed 1c140f1 cert computed lambda (the crux) on only 2 stalled resolution-day clusters
(07-13/14) via a live CLOB fetch — the exact window the brief says to ignore. This recomputes lambda +
all four bars on the window where the +7.9% edge actually lives (the july 1-8 consensus picks), using
the `harvest_fills` intl taker tape as the close source (the SAME source collapse_lambda_wf.py uses).
No live endpoint, ~4x the day-clusters, ~81% forward-close coverage.

SELECTION (frozen, leak-free) = the weather_fav arm's own rule: >=3 wider-universe (rank<=250) one-sided
backers converge on a highest-temperature favorite, mean backer price in band, resolved. Decision time
ts0 = MIN(backer ts). Entry = the `_blind` at-fire mid (initial_mean_price) for the same (cond,outcome).

CLOSE (frozen) = last harvest BUY print for (cond,outcome) with ts <= res_ts - H*3600, degen-guarded to
[0.02,0.98]. res_ts = `_blind resolved_at`. last-tick OVERSTATES (weather price -> 0/1 as the day's high
is revealed); the honest lambda is the fairest tradeable lead with >=50% coverage.

CLUSTERING: bootstrap clustered on the resolution DAY (same-day cross-city temperature is correlated).

  ./weather_fav_4bar_harvest.py --selftest
  ./weather_fav_4bar_harvest.py                 # full run; writes reports/weather_fav_4bar_harvest.json
  ./weather_fav_4bar_harvest.py --max-day 2026-07-12   # clean window only (brief: ignore last ~2 days)
"""
import argparse
import csv
import io
import json
import os
import pickle
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
GUARD_SQL = ("SET work_mem='128MB'; SET statement_timeout='900s'; "
             "SET max_parallel_workers_per_gather=0; ")
GO_LIVE = "2026-06-29"
FAMILY = "highest-temperature"
WIDE_CUTOFF = 250
MIN_BACKERS = 3
GLO, GHI = 0.02, 0.98
FEE_RATE = 0.05                      # weather taker theta (collapse_risk.THETA['weather']); NOT stale 0.03
SEED = 20260715
N_BOOT = 4000
COVERAGE_BAR = 0.50
BATCH = 200
HORIZONS_H = [24, 12, 6, 3, 1]      # controlled pre-resolution leads (hours). None = last non-degen tick.
CACHE = "reports/.weather_fav_4bar_cache.pkl"


def fee(p):
    return FEE_RATE * p * (1 - p)


def psql(sql):
    o = subprocess.run(PG, input=GUARD_SQL + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1500])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


PICK_SQL = f"""
WITH e AS (
  SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, MIN(ft.rank) rank,
         AVG(f.price) px, MIN(f.ts) ts0, MAX(f.slug) slug
  FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
  WHERE f.side='BUY' AND f.ts>='{GO_LIVE}' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{FAMILY}'
  GROUP BY 1,2,3),
e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
  (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w
     AND x.outcome_index<>e.outcome_index)),
conv AS (
  SELECT condition_id, outcome_index, MAX(slug) slug, count(*) nb, AVG(px) sharp_px, MIN(ts0) ts0
  FROM e1 GROUP BY 1,2
  HAVING count(*)>={MIN_BACKERS} AND AVG(px) BETWEEN 0.71 AND 0.98)
SELECT c.condition_id, c.outcome_index, c.slug, c.nb, c.sharp_px,
       b.initial_mean_price AS atfire, (b.outcome_won::int) AS won,
       EXTRACT(epoch FROM c.ts0)::bigint AS ts0,
       EXTRACT(epoch FROM b.resolved_at)::bigint AS res_ts,
       to_char(b.resolved_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS res_day
FROM conv c
JOIN consensus_signals b ON b.condition_id=c.condition_id AND b.outcome_index=c.outcome_index
  AND b.strategy='_blind'
WHERE b.resolved AND b.outcome_won IS NOT NULL AND b.initial_mean_price IS NOT NULL;
"""


def build():
    if os.path.exists(CACHE):
        print(f"loading cache {CACHE}", file=sys.stderr)
        with open(CACHE, "rb") as f:
            return pickle.load(f)

    picks = []
    for r in psql(PICK_SQL):
        picks.append({
            "cond": r["condition_id"], "oi": int(r["outcome_index"]), "slug": r["slug"],
            "nb": int(r["nb"]), "sharp": float(r["sharp_px"]), "atfire": float(r["atfire"]),
            "won": int(r["won"]), "ts0": int(r["ts0"]), "res_ts": int(r["res_ts"]),
            "day": r["res_day"],
        })
    print(f"{len(picks):,} testable weather_fav picks / {len({p['day'] for p in picks})} res-days",
          file=sys.stderr)

    # harvest tape per (cond, outcome) — all BUY prints, sorted ascending
    conds = sorted({p["cond"] for p in picks})
    tape = defaultdict(list)
    for i in range(0, len(conds), BATCH):
        ch = conds[i:i + BATCH]
        for r in psql(f"""
              SELECT condition_id, outcome_index, EXTRACT(epoch FROM ts)::bigint t, price p
              FROM harvest_fills
              WHERE side='BUY' AND condition_id IN ({q_lit(ch)});"""):
            tape[(r["condition_id"], int(r["outcome_index"]))].append(
                (int(r["t"]), float(r["p"])))
        sys.stderr.write(f"\r  tape {min(i+BATCH,len(conds)):,}/{len(conds):,} conds")
        sys.stderr.flush()
    sys.stderr.write("\n")
    for k in tape:
        tape[k].sort()
    tape = dict(tape)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump((picks, tape), f)
    return picks, tape


# ------------------------------------------------------------------ close routing (frozen)
def close_at(prints, res_ts, horizon_h, after_ts=None):
    """Last non-degenerate BUY print with ts <= res_ts - horizon_h*3600 (horizon_h=None => <= res_ts)
    AND ts > after_ts (strictly after the decision, leak-free). Degen-guarded to [GLO,GHI]."""
    if not prints:
        return None
    cutoff = res_ts if horizon_h is None else res_ts - horizon_h * 3600
    best = None
    for (t, p) in prints:
        if t <= cutoff and GLO <= p <= GHI and (after_ts is None or t > after_ts):
            if best is None or t > best[0]:
                best = (t, p)
    return best[1] if best else None


def entry_from_tape(prints, ts0, max_slip_h=6):
    """First non-degenerate BUY print with ts >= ts0 (within max_slip_h) — the realizable taker entry
    (an actual executed ask), spread-neutral vs the taker-print close. Returns price or None."""
    if not prints:
        return None
    best = None
    for (t, p) in prints:
        if t >= ts0 and GLO <= p <= GHI:
            if best is None or t < best[0]:
                best = (t, p)
    if best is None or best[0] - ts0 > max_slip_h * 3600:
        return None
    return best[1]


# ------------------------------------------------------------------ day-clustered stats
def day_boot(day_pairs, stat="mean", n_boot=N_BOOT, seed=SEED):
    """day_pairs = {day: [values]}. Resample DAYS with replacement; stat over pooled day-means.
    Returns dict(point, lo, hi, p_le0, n_days, n_rows)."""
    days = list(day_pairs)
    if len(days) < 2:
        return None
    day_means = {d: float(np.mean(day_pairs[d])) for d in days}
    means = np.array([day_means[d] for d in days], float)
    rng = np.random.default_rng(seed)
    bs = means[rng.integers(0, len(days), (n_boot, len(days)))].mean(1)
    n_rows = sum(len(v) for v in day_pairs.values())
    return {"point": float(means.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p_le0": float((bs <= 0).mean()),
            "n_days": len(days), "n_rows": n_rows}


def roi_day_boot(rows, n_boot=N_BOOT, seed=SEED):
    """rows = [(day, net, turnover)] -> day-clustered ROI-on-turnover (sum net / sum turnover per day)."""
    by = defaultdict(lambda: [0.0, 0.0])
    for day, net, tn in rows:
        by[day][0] += net
        by[day][1] += tn
    days = [d for d in by if by[d][1] > 0]
    if len(days) < 2:
        return None
    roi = np.array([by[d][0] / by[d][1] for d in days], float)
    rng = np.random.default_rng(seed)
    bs = roi[rng.integers(0, len(days), (n_boot, len(days))).reshape(n_boot, len(days))].mean(1)
    return {"roi": float(roi.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p_le0": float((bs <= 0).mean()),
            "n_days": len(days), "n_rows": len(rows)}


# ------------------------------------------------------------------ bars
def _entry_of(p, tape, entry_basis):
    """entry_basis 'atfire' = _blind at-fire mid (mid, may bias CLV up vs taker-print close);
    'tape' = first harvest BUY print >= ts0 (executed ask, spread-neutral vs close). Returns price|None."""
    if entry_basis == "atfire":
        return p["atfire"]
    return entry_from_tape(tape.get((p["cond"], p["oi"]), []), p["ts0"])


def bar2_lambda(picks, tape, band, entry_basis="atfire"):
    """lambda = day-clustered mean(CLV)/mean(surplus) at controlled horizons + last-tick.
    Closes strictly AFTER the decision ts0 (leak-free)."""
    lo, hi = band
    sel = [p for p in picks if lo <= p["atfire"] < hi]
    out = {"band": band, "entry_basis": entry_basis, "n_selected": len(sel), "horizons": {}}
    for label, hz in [("last", None)] + [(f"{h}h", h) for h in HORIZONS_H]:
        clv_d, sur_d = defaultdict(list), defaultdict(list)
        n_cov = 0
        for p in sel:
            entry = _entry_of(p, tape, entry_basis)
            if entry is None:
                continue
            c = close_at(tape.get((p["cond"], p["oi"]), []), p["res_ts"], hz, after_ts=p["ts0"])
            if c is None:
                continue
            n_cov += 1
            clv_d[p["day"]].append(c - entry)
            sur_d[p["day"]].append(p["won"] - entry)
        cov = n_cov / len(sel) if sel else 0.0
        clv = day_boot(clv_d)
        sur = day_boot(sur_d)
        if clv is None or sur is None or sur["point"] == 0:
            out["horizons"][label] = {"n": n_cov, "coverage": round(cov, 3), "insufficient": True}
            continue
        # lambda bootstrap: resample days jointly for CLV and surplus
        days = list(clv_d)
        cm = np.array([np.mean(clv_d[d]) for d in days])
        sm = np.array([np.mean(sur_d[d]) for d in days])
        rng = np.random.default_rng(SEED)
        idx = rng.integers(0, len(days), (N_BOOT, len(days)))
        cbs, sbs = cm[idx].mean(1), sm[idx].mean(1)
        lam_bs = np.clip(cbs / np.where(np.abs(sbs) < 1e-9, np.nan, sbs), -2, 2)
        lam_bs = lam_bs[~np.isnan(lam_bs)]
        lam_hat = clv["point"] / sur["point"]
        out["horizons"][label] = {
            "n": n_cov, "coverage": round(cov, 3), "n_days": clv["n_days"],
            "mean_surplus": round(sur["point"], 4),
            "mean_clv": round(clv["point"], 4),
            "clv_ci": [round(clv["lo"], 4), round(clv["hi"], 4)],
            "clv_p_le0": round(clv["p_le0"], 3),
            "mean_resid": round(sur["point"] - clv["point"], 4),
            "lambda_hat": round(float(lam_hat), 3),
            "lambda_ci": [round(float(np.percentile(lam_bs, 2.5)), 3),
                          round(float(np.percentile(lam_bs, 97.5)), 3)] if len(lam_bs) else None,
        }
    # headline = fairest tradeable horizon (longest lead first) with >=COVERAGE_BAR coverage
    headline = None
    for h in ["24h", "12h", "6h", "3h", "1h", "last"]:
        m = out["horizons"].get(h, {})
        if not m.get("insufficient") and m.get("coverage", 0) >= COVERAGE_BAR:
            headline = {"horizon": h, **m}
            break
    out["headline"] = headline
    if headline:
        lam_lb = headline["lambda_ci"][0] if headline["lambda_ci"] else None
        clv_lb = headline["clv_ci"][0]
        out["bar2_pass"] = bool(lam_lb is not None and lam_lb > 0 and clv_lb > 0)
    else:
        out["bar2_pass"] = False
    return out


def bar1_walkforward(picks, band, folds=3):
    lo, hi = band
    sel = [p for p in picks if lo <= p["atfire"] < hi]
    days = sorted({p["day"] for p in sel})
    rows = [(p["day"], (p["won"] - p["atfire"] - fee(p["atfire"])), p["atfire"]) for p in sel]
    pooled = roi_day_boot(rows)
    # expanding-window folds over ordered days
    fold_res = []
    if len(days) >= folds + 1:
        edges = [int(round(x)) for x in np.linspace(0, len(days), folds + 2)]
        blocks = [set(days[edges[i]:edges[i + 1]]) for i in range(folds + 1)]
        for b in range(1, folds + 1):
            test_days = blocks[b]
            tr = [r for r in rows if r[0] in test_days]
            rr = roi_day_boot(tr)
            fold_res.append({"fold": b, "test_days": sorted(test_days),
                             "roi": round(rr["roi"], 4) if rr else None,
                             "lo": round(rr["lo"], 4) if rr else None,
                             "n_days": rr["n_days"] if rr else 0} if rr else
                            {"fold": b, "test_days": sorted(test_days), "insufficient": True})
    per_day = {}
    dd = defaultdict(lambda: [0.0, 0.0])
    for day, net, tn in rows:
        dd[day][0] += net
        dd[day][1] += tn
    for d in sorted(dd):
        per_day[d] = round(dd[d][0] / dd[d][1], 4) if dd[d][1] else None
    return {"band": band, "n": len(sel), "n_days": len(days),
            "pooled_roi": round(pooled["roi"], 4) if pooled else None,
            "pooled_ci": [round(pooled["lo"], 4), round(pooled["hi"], 4)] if pooled else None,
            "pooled_p_le0": round(pooled["p_le0"], 3) if pooled else None,
            "folds": fold_res, "per_day_roi": per_day,
            "calendar_blocked": len(days) < folds + 1,
            "bar1_pass": bool(pooled and pooled["lo"] > 0 and len(days) >= folds + 1
                              and all(f.get("roi", -1) is not None and f.get("roi", -1) > -0.02
                                      for f in fold_res))}


def bar3_brier(picks, band):
    """Sharp converged price vs blind at-fire mid as forecasts of `won`, pooled + per day-block."""
    lo, hi = band
    sel = [p for p in picks if lo <= p["atfire"] < hi]
    y = np.array([p["won"] for p in sel], float)
    ps = np.clip(np.array([p["sharp"] for p in sel], float), 0, 1)
    pb = np.clip(np.array([p["atfire"] for p in sel], float), 0, 1)
    bs_sharp = float(np.mean((ps - y) ** 2))
    bs_blind = float(np.mean((pb - y) ** 2))
    # per-day-block stability
    by = defaultdict(list)
    for i, p in enumerate(sel):
        by[p["day"]].append(i)
    per_day = {}
    wins = 0
    for d in sorted(by):
        ix = by[d]
        s = float(np.mean((ps[ix] - y[ix]) ** 2))
        bl = float(np.mean((pb[ix] - y[ix]) ** 2))
        per_day[d] = {"sharp": round(s, 4), "blind": round(bl, 4), "sharp_wins": s < bl}
        wins += (s < bl)
    return {"band": band, "n": len(sel), "brier_sharp": round(bs_sharp, 5),
            "brier_blind": round(bs_blind, 5), "sharp_beats_blind": bs_sharp < bs_blind,
            "per_day": per_day, "days_sharp_wins": f"{wins}/{len(by)}",
            "bar3_pass": bool(bs_sharp < bs_blind and wins > len(by) / 2)}


def bar4_ask(picks, tape, band):
    """Realizable at the executed ask, official settlement, corrected fee (rate 0.05), day-clustered.
    Two entry bases: 'atfire' (_blind mid, optimistic) and 'tape' (first executed BUY print >= ts0 = a
    real ask, the realizable copier entry)."""
    lo, hi = band
    sel = [p for p in picks if lo <= p["atfire"] < hi]
    res = {"band": band, "n_selected": len(sel), "bases": {}}
    for basis in ("atfire", "tape"):
        rows, rows3, gross_rows, entries, fees, wins = [], [], [], [], [], []
        for p in sel:
            e = _entry_of(p, tape, basis)
            if e is None:
                continue
            rows.append((p["day"], p["won"] - e - fee(e), e))
            rows3.append((p["day"], p["won"] - e - 0.03 * e * (1 - e), e))
            gross_rows.append((p["day"], p["won"] - e, e))
            entries.append(e); fees.append(fee(e)); wins.append(p["won"])
        r = roi_day_boot(rows); r3 = roi_day_boot(rows3); g = roi_day_boot(gross_rows)
        res["bases"][basis] = {
            "n": len(rows), "n_days": r["n_days"] if r else 0,
            "win_rate": round(float(np.mean(wins)), 3) if wins else None,
            "mean_entry": round(float(np.mean(entries)), 4) if entries else None,
            "mean_fee_cents": round(float(np.mean(fees)) * 100, 3) if fees else None,
            "roi_gross": round(g["roi"], 4) if g else None,
            "roi_net_fee05": round(r["roi"], 4) if r else None,
            "roi_net_fee05_ci": [round(r["lo"], 4), round(r["hi"], 4)] if r else None,
            "roi_net_fee05_p_le0": round(r["p_le0"], 3) if r else None,
            "roi_net_OLD_fee03": round(r3["roi"], 4) if r3 else None,
        }
    tp = res["bases"]["tape"]
    res["note"] = ("'tape' entry = first executed BUY print at/after convergence = a REAL ask (the "
                   "realizable copier fill). 'atfire' = _blind mid (optimistic). Spread tax = "
                   "atfire→tape ROI gap. n_days<20 ⇒ any pass is FRAGILE.")
    res["bar4_pass"] = bool(tp["roi_net_fee05_ci"] and tp["roi_net_fee05_ci"][0] > 0
                            and tp["n_days"] >= 20)
    res["bar4_pass_fragile"] = bool(tp["roi_net_fee05_ci"] and tp["roi_net_fee05_ci"][0] > 0
                                    and tp["n_days"] < 20)
    return res


def run(max_day=None):
    picks, tape = build()
    if max_day:
        picks = [p for p in picks if p["day"] <= max_day]
    days = sorted({p["day"] for p in picks})
    out = {"as_of": "2026-07-15", "run": "weather_fav 4-bar on harvest-tape edge window",
           "fee_rate": FEE_RATE, "max_day": max_day, "n_picks": len(picks),
           "res_days": days, "n_days": len(days), "bands": {}}
    for band in ([0.71, 0.90], [0.71, 0.98]):
        key = f"{band[0]:.2f}-{band[1]:.2f}"
        out["bands"][key] = {
            "bar1_walkforward": bar1_walkforward(picks, band),
            "bar2_lambda_atfire": bar2_lambda(picks, tape, band, entry_basis="atfire"),
            "bar2_lambda_tape": bar2_lambda(picks, tape, band, entry_basis="tape"),
            "bar3_brier": bar3_brier(picks, band),
            "bar4_ask": bar4_ask(picks, tape, band),
        }
    return out


# ------------------------------------------------------------------ selftest
def selftest():
    ok = True
    # close_at: last non-degen <= res_ts-H; excludes degenerate & future prints
    prints = [(0, 0.80), (3600, 0.85), (7200, 0.995), (9000, 0.90)]
    if close_at(prints, 10000, None) != 0.90:
        print("FAIL close_at last-tick"); ok = False
    # at -2h (res 10000 -> cutoff 2800): only (0,0.80) qualifies
    if close_at(prints, 10000, 2) != 0.80:
        print("FAIL close_at horizon"); ok = False
    # degenerate 0.995 never chosen
    if close_at([(0, 0.995), (10, 0.995)], 100, None) is not None:
        print("FAIL close_at degen guard"); ok = False
    # future strictly excluded (cutoff)
    if close_at([(5000, 0.9)], 4000, None) is not None:
        print("FAIL close_at future"); ok = False
    # after_ts: prints at/before decision excluded (leak-free)
    if close_at([(100, 0.8), (500, 0.9)], 10000, None, after_ts=300) != 0.9:
        print("FAIL close_at after_ts"); ok = False
    if close_at([(100, 0.8)], 10000, None, after_ts=300) is not None:
        print("FAIL close_at after_ts excl"); ok = False
    # entry_from_tape: first non-degen print >= ts0 within slip
    if entry_from_tape([(90, 0.995), (100, 0.82), (200, 0.85)], 100) != 0.82:
        print("FAIL entry_from_tape"); ok = False
    if entry_from_tape([(100, 0.82)], 100 + 7 * 3600) is not None:
        print("FAIL entry_from_tape slip"); ok = False
    # day_boot clusters on day
    r = day_boot({"d1": [0.1, 0.3], "d2": [0.2], "d3": [0.2]})
    if r["n_days"] != 3 or abs(r["point"] - (0.2 + 0.2 + 0.2) / 3) > 1e-9:
        print("FAIL day_boot"); ok = False
    # roi_day_boot: 2 days, ROI = mean of per-day ROI
    rr = roi_day_boot([("d1", 0.05, 0.85), ("d2", 0.0, 0.85)])
    if rr["n_days"] != 2:
        print("FAIL roi_day_boot"); ok = False
    # fee at 0.05 rate
    if abs(fee(0.9) - 0.05 * 0.9 * 0.1) > 1e-12:
        print("FAIL fee"); ok = False
    # bar3 brier: perfect sharp beats noisy blind
    fake = [{"atfire": 0.5, "sharp": 1.0, "won": 1, "day": "d1"},
            {"atfire": 0.5, "sharp": 0.0, "won": 0, "day": "d2"}]
    b3 = bar3_brier(fake, [0.0, 1.0])
    if not b3["sharp_beats_blind"]:
        print("FAIL bar3 brier"); ok = False
    print("weather_fav_4bar_harvest selftest: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--max-day", default=None, help="drop picks resolving after this YYYY-MM-DD")
    ap.add_argument("--out", default="reports/weather_fav_4bar_harvest.json")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    out = run(a.max_day)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
