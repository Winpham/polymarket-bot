#!/usr/bin/env python3
"""
§3.2 MIRAGE HEAD-TO-HEAD — blind weather-favourite-band pool vs the sharp-selected weather_fav picks,
priced at a NEUTRAL reference (res - 24h, NOT entry-anchored), settled official, same band × day.

If blind ≈ sharp-selected ⇒ the mid-favourite BAND does the work (structural favourite-longshot
premium) and the copy apparatus is unnecessary. If sharp-selected > blind by a CLV-confirmed margin ⇒
genuine forecast selection. (λ, computed separately, is the CLV test; this is the realized head-to-head.)

Price source is the CLOB prices-history endpoint, VALIDATED to MAE 1.5c against captured entry_ask_mid
in weather_clv_lambda.py — so this null is run on a validated basis (hard rule 4 satisfied).

Blind universe = every weather (highest-temperature) market-outcome any tracked trader touched that
resolved on the 2 clean days, sampled for API cost; favourite = the outcome whose neutral mid ∈ band.
Settlement = trader_fills.outcome_won (Polymarket CLOB resolution). Day-clustered.
"""
import csv
import io
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1", "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
CLOB = "https://clob.polymarket.com"
UA = "Mozilla/5.0 polymarket-bot/weather-blind"
BAND_LO, BAND_HI = 0.71, 0.90
NEUTRAL_H = 24
SEED = 20260715
DAYS = ("2026-07-13", "2026-07-14")
REPORTS = Path(__file__).resolve().parent.parent / "reports"
CACHE = REPORTS / "cache_weather_prices"      # shared with weather_clv_lambda (favourite outcomes)
BCACHE = REPORTS / "cache_blind_prices"


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def _get(url, retries=3):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(0.4 * (a + 1))
        except Exception:
            time.sleep(0.4 * (a + 1))
    return None


def mid_before(hist, ts, max_slip_min=180):
    if not hist:
        return None
    best = None
    for t in hist:
        tt, p = t.get("t"), t.get("p")
        if tt is None or p is None:
            continue
        if tt <= ts and (best is None or tt > best[0]):
            best = (tt, float(p))
    if best is None or abs(best[0] - ts) > max_slip_min * 60:
        return None
    return best[1]


def blind_candidates(limit_per_day):
    rng = random.Random(SEED)
    rows = q(f"""
      SELECT condition_id, outcome_index,
             EXTRACT(epoch FROM MAX(resolved_at))::bigint AS res_ts,
             (resolved_at AT TIME ZONE 'UTC')::date AS day,
             BOOL_OR(outcome_won)::int AS won
      FROM trader_fills
      WHERE slug ~ 'highest-temperature' AND resolved AND outcome_won IS NOT NULL
        AND (resolved_at AT TIME ZONE 'UTC')::date IN ('{DAYS[0]}','{DAYS[1]}')
      GROUP BY condition_id, outcome_index, (resolved_at AT TIME ZONE 'UTC')::date
    """)
    byday = defaultdict(list)
    for r in rows:
        byday[r["day"]].append(r)
    out = []
    for d, rs in byday.items():
        rng.shuffle(rs)
        out.extend(rs[:limit_per_day])
    return out


def reconstruct(cands, workers=10):
    BCACHE.mkdir(parents=True, exist_ok=True)

    def one(r):
        key = f"{r['condition_id']}_{r['outcome_index']}"
        cf = BCACHE / f"{key}.json"
        if cf.exists():
            h = json.loads(cf.read_text()).get("history")
        else:
            mkt = _get(f"{CLOB}/markets/{r['condition_id']}")
            toks = (mkt or {}).get("tokens") or []
            oi = int(r["outcome_index"])
            if oi >= len(toks) or not toks[oi].get("token_id"):
                cf.write_text(json.dumps({"history": []}))
                return None
            hist = _get(f"{CLOB}/prices-history?market={toks[oi]['token_id']}&interval=max&fidelity=1")
            h = (hist or {}).get("history") or []
            cf.write_text(json.dumps({"history": h}))
        mid = mid_before(h, int(r["res_ts"]) - NEUTRAL_H * 3600)
        if mid is None:
            return None
        return {"day": r["day"], "mid": mid, "won": int(r["won"])}

    res = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for x in ex.map(one, cands):
            if x:
                res.append(x)
    return res


def day_clustered(pairs):
    m = defaultdict(list)
    for d, v in pairs:
        m[d].append(v)
    means = {d: sum(v) / len(v) for d, v in m.items()}
    return (sum(means.values()) / len(means) if means else float("nan")), means


def sharp_at_neutral():
    """weather_fav band picks, ROI at the res-24h neutral mid, from the shared favourite-price cache."""
    sig = q(f"""
      SELECT condition_id, outcome_index, initial_mean_price AS imp,
             EXTRACT(epoch FROM resolved_at)::bigint AS res_ts,
             (resolved_at AT TIME ZONE 'UTC')::date AS day, (outcome_won::int) AS won
      FROM consensus_signals WHERE strategy='weather_fav' AND resolved AND outcome_won IS NOT NULL
        AND entry_ask_mid IS NOT NULL AND initial_mean_price>={BAND_LO} AND initial_mean_price<{BAND_HI}
        AND (resolved_at AT TIME ZONE 'UTC')::date IN ('{DAYS[0]}','{DAYS[1]}')
    """)
    out = []
    for r in sig:
        cf = CACHE / f"{r['condition_id']}_{r['outcome_index']}.json"
        if not cf.exists():
            continue
        h = json.loads(cf.read_text()).get("history")
        mid = mid_before(h, int(r["res_ts"]) - NEUTRAL_H * 3600)
        if mid is None or not (BAND_LO <= mid < BAND_HI):
            continue
        out.append({"day": r["day"], "mid": mid, "won": int(r["won"])})
    return out


def roi(items):
    pairs = [(x["day"], (x["won"] - x["mid"]) / x["mid"]) for x in items]
    m, dm = day_clustered(pairs)
    return {"n": len(items), "n_days": len(dm),
            "mean_neutral_mid": round(sum(x["mid"] for x in items) / len(items), 4) if items else None,
            "win_rate": round(sum(x["won"] for x in items) / len(items), 3) if items else None,
            "roi_at_neutral_mid": round(m, 4) if m == m else None,
            "day_means": {d: round(v, 4) for d, v in sorted(dm.items())}}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-per-day", type=int, default=700)
    a = ap.parse_args()
    cands = blind_candidates(a.limit_per_day)
    print(f"blind candidates sampled: {len(cands)}", file=sys.stderr)
    recon = reconstruct(cands)
    blind_band = [x for x in recon if BAND_LO <= x["mid"] < BAND_HI]
    sharp = sharp_at_neutral()
    res = {
        "neutral_reference": f"res-{NEUTRAL_H}h", "band": [BAND_LO, BAND_HI],
        "blind_pool_reconstructed": len(recon), "blind_in_band": len(blind_band),
        "blind_favourite_band": roi(blind_band),
        "sharp_selected_weather_fav_band": roi(sharp),
    }
    b = res["blind_favourite_band"]["roi_at_neutral_mid"]
    s = res["sharp_selected_weather_fav_band"]["roi_at_neutral_mid"]
    if b is not None and s is not None:
        res["sharp_minus_blind"] = round(s - b, 4)
        res["verdict"] = (
            f"blind {b:+.4f} vs sharp {s:+.4f} (Δ={s-b:+.4f}). "
            + ("blind≈sharp ⇒ the BAND does the work (structural premium); sharp adds ~nothing."
               if abs(s - b) < 0.02 else
               "sharp exceeds blind — but check CLV (λ) confirms it, else it is 2-day realized variance."))
    print(json.dumps(res, indent=2))
    (REPORTS / "weather_blind_pool.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
