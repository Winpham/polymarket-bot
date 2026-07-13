#!/usr/bin/env python3
"""
ATFIRE-RECON — reconstruct the at-fire CLOB mid for evergreen picks the `_blind` arm never covered.

WHY (the second half of the resolution defect, 2026-07-12):
The realizable-PROXY basis for every weather measurement is the **at-fire mid** — the CLOB mid ~10-15
min after convergence, i.e. what a fast COPIER would pay, as opposed to the sharps' own fill (which is
a directional ceiling, not a copyable price). Historically that number came from the `_blind` arm's
`initial_mean_price`. But `_blind` scores the INCUMBENT rank-40 book, and weather's specialist backers
sit at rank 41-250 — the exact conversion gap the weather arm exists to close. So `_blind` weather
coverage collapsed to ZERO from 07-10 (07-06: 1593 signals -> 07-10 onward: 0), and the live
`weather_fav` arm only began capturing on 07-12.

Net: after the resolver backfill, week 28 has resolved OUTCOMES but NO price basis — so the decisive
LODO-by-week gate STILL could not run. This instrument recovers the basis from an INDEPENDENT public
source: the CLOB `prices-history` endpoint (~10-min fidelity), read at `ts0 + LAG_MIN` where `ts0` is
the convergence instant. That is the same quantity `_blind.initial_mean_price` records, from a
different path.

**It is only trustworthy if it AGREES with the recorded basis where both exist**, so `--validate`
reconstructs week-27 picks (which DO have `_blind` mids) and reports MAE / bias / correlation against
them. A reconstruction that does not track the recorded mid is REJECTED, not used. Nothing here writes
to the DB; the cache is a report artifact.

  ./atfire_recon.py --family highest-temperature --build      # cache reconstructed mids
  ./atfire_recon.py --family highest-temperature --validate   # recon vs recorded _blind mid
  ./atfire_recon.py --selftest
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C  # noqa: E402

CLOB = "https://clob.polymarket.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) polymarket-bot/atfire-recon"
WIDE_CUTOFF = 250
LO, HI = 0.71, 0.98

# The copier's lag: the at-fire mid is the price a follower sees ~10-15 min after the sharps converge.
# 12 min sits in the middle of that window and matches the `_blind` arm's own capture cadence (its
# first housekeeping pass). Frozen BEFORE looking at any week-28 outcome — never tuned to a result.
LAG_MIN = 12
# prices-history is ~10-min fidelity, so accept the first tick within 45 min of the target and no
# earlier than ts0 (never a pre-convergence price — that would leak the sharps' entry, not the copier's).
MAX_SLIP_MIN = 45

REPORTS = Path(__file__).resolve().parent.parent / "reports"


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


def price_at(history, ts0, lag_min=LAG_MIN, max_slip_min=MAX_SLIP_MIN):
    """The at-fire mid: first tick at/after ts0+lag, within max_slip. None if the series doesn't cover it.

    NEVER returns a tick before ts0 — a pre-convergence price is the sharps' entry, not the copier's,
    and using it would manufacture edge out of the very lag we are trying to charge ourselves.
    """
    if not history:
        return None
    target = ts0 + lag_min * 60
    best = None
    for tick in history:
        t = tick.get("t")
        p = tick.get("p")
        if t is None or p is None or t < ts0:
            continue
        if t >= target and (best is None or t < best[0]):
            best = (t, float(p))
    if best is None:
        return None
    if best[0] - target > max_slip_min * 60:
        return None  # series gaps past the acceptable window — report nothing rather than guess
    p = best[1]
    return p if 0.0 < p < 1.0 else None


def fetch_convergence(family, since):
    """Wider-universe convergence picks for one family, WITH the convergence instant ts0 (epoch)
    and the resolved outcome. Mirrors weather_scan's conv CTE (>=3 one-sided backers, band, resolved)."""
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, MIN(ft.rank) rank, AVG(f.price) px,
             MIN(f.ts) ts, MAX(f.slug) slug, BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='{since}' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{family}'
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
      (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
    conv AS (
      SELECT condition_id, outcome_index, MAX(slug) slug, count(*) nb, AVG(px) sharp_px,
             BOOL_OR(rz) rz, BOOL_OR(won) won, MIN(ts) ts0
      FROM e1 GROUP BY 1,2
      HAVING count(*)>=3 AND AVG(px) BETWEEN {LO} AND {HI})
    SELECT c.condition_id, c.outcome_index, c.slug, c.nb, c.sharp_px, c.won,
           EXTRACT(EPOCH FROM c.ts0)::bigint, c.ts0::date, b.initial_mean_price
    FROM conv c
    LEFT JOIN consensus_signals b ON b.condition_id=c.condition_id
      AND b.outcome_index=c.outcome_index AND b.strategy='_blind'
    WHERE c.rz AND c.won IS NOT NULL;
    """)
    out = []
    for r in rows:
        cond, oi, slug, nb, sharp, won, ts0, day, blind_mid = (r + [None] * 9)[:9]
        out.append({
            "cond": cond, "oi": int(oi), "slug": slug, "nb": int(nb),
            "sharp_px": float(sharp), "won": won == "t", "ts0": int(ts0), "day": day,
            "blind_mid": float(blind_mid) if blind_mid not in (None, "") else None,
        })
    return out


def reconstruct(picks, workers=8):
    """Fetch each pick's token price history and read the at-fire mid. Returns picks + 'recon'."""
    def one(p):
        mkt = _get(f"{CLOB}/markets/{p['cond']}")
        if not mkt:
            return None
        toks = mkt.get("tokens") or []
        if p["oi"] >= len(toks):
            return None
        tok = toks[p["oi"]].get("token_id")
        if not tok:
            return None
        hist = _get(f"{CLOB}/prices-history?market={tok}&interval=max&fidelity=1")
        if not hist:
            return None
        return price_at((hist or {}).get("history") or [], p["ts0"])

    with ThreadPoolExecutor(max_workers=workers) as ex:
        mids = list(ex.map(one, picks))
    for p, m in zip(picks, mids):
        p["recon"] = m
    return picks


def validate(picks):
    """Recon vs the RECORDED `_blind` at-fire mid, on picks where both exist. The gate on trusting
    the reconstruction for the weeks where `_blind` is absent."""
    both = [p for p in picks if p.get("recon") is not None and p.get("blind_mid") is not None]
    if not both:
        return {"n": 0, "verdict": "NO OVERLAP — cannot validate"}
    errs = [p["recon"] - p["blind_mid"] for p in both]
    n = len(errs)
    mae = sum(abs(e) for e in errs) / n
    bias = sum(errs) / n
    mx, my = (sum(p["recon"] for p in both) / n, sum(p["blind_mid"] for p in both) / n)
    cov = sum((p["recon"] - mx) * (p["blind_mid"] - my) for p in both)
    vx = sum((p["recon"] - mx) ** 2 for p in both) ** 0.5
    vy = sum((p["blind_mid"] - my) ** 2 for p in both) ** 0.5
    corr = cov / (vx * vy) if vx > 0 and vy > 0 else 0.0
    within_2c = sum(1 for e in errs if abs(e) <= 0.02) / n
    # Frozen acceptance bar: the reconstruction must track the recorded mid tightly and without a
    # systematic tilt. A NEGATIVE bias would flatter the edge (we'd claim a cheaper entry than real).
    ok = mae <= 0.03 and abs(bias) <= 0.01 and corr >= 0.90
    return {
        "n": n, "mae": round(mae, 4), "bias": round(bias, 4), "corr": round(corr, 3),
        "within_2c": round(within_2c, 3),
        "acceptance": "mae<=0.03 and |bias|<=0.01 and corr>=0.90",
        "verdict": "ACCEPT — recon tracks the recorded mid" if ok else "REJECT — recon does not track the recorded mid",
        "accepted": ok,
    }


def cache_path(family):
    return REPORTS / f"ATFIRE-RECON-{family}.json"


def selftest():
    ok = True
    # at/after target, nearest tick wins
    h = [{"t": 1000, "p": 0.5}, {"t": 1720, "p": 0.8}, {"t": 2400, "p": 0.9}]
    got = price_at(h, 1000, lag_min=12, max_slip_min=45)   # target = 1720
    if got != 0.8:
        print(f"FAIL price_at exact: {got}"); ok = False
    # NEVER a pre-convergence tick, even if it's the only one
    if price_at([{"t": 500, "p": 0.7}], 1000) is not None:
        print("FAIL price_at leaked a pre-ts0 tick"); ok = False
    # gap past max slip -> None (report nothing rather than guess)
    if price_at([{"t": 1000, "p": 0.5}, {"t": 99999, "p": 0.9}], 1000) is not None:
        print("FAIL price_at ignored max slip"); ok = False
    # degenerate prices rejected
    if price_at([{"t": 1720, "p": 0.0}], 1000) is not None:
        print("FAIL price_at accepted p=0"); ok = False
    if price_at([], 1000) is not None or price_at(None, 1000) is not None:
        print("FAIL price_at on empty"); ok = False
    # validate: a perfect reconstruction ACCEPTS; a 10c-biased one REJECTS
    perfect = [{"recon": 0.8, "blind_mid": 0.8}, {"recon": 0.75, "blind_mid": 0.75},
               {"recon": 0.9, "blind_mid": 0.9}, {"recon": 0.72, "blind_mid": 0.72}]
    if not validate(perfect)["accepted"]:
        print("FAIL validate rejected a perfect recon"); ok = False
    biased = [{"recon": p["recon"] - 0.10, "blind_mid": p["blind_mid"]} for p in perfect]
    if validate(biased)["accepted"]:
        print("FAIL validate accepted a 10c-biased recon"); ok = False
    print("atfire_recon selftest: PASS" if ok else "atfire_recon selftest: FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="highest-temperature")
    ap.add_argument("--since", default="2026-07-01")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(selftest())

    picks = fetch_convergence(a.family, a.since)
    print(f"convergence picks (resolved, band {LO}-{HI}): {len(picks)}  family={a.family}")
    picks = reconstruct(picks)
    got = [p for p in picks if p["recon"] is not None]
    print(f"reconstructed at-fire mid: {len(got)}/{len(picks)}")

    v = validate(picks)
    print(f"VALIDATION vs recorded _blind mid: {json.dumps(v)}")

    if a.build:
        if not v.get("accepted"):
            print("REFUSING to write cache — reconstruction failed its acceptance bar.")
            raise SystemExit(1)
        cache = {f"{p['cond']}:{p['oi']}": p["recon"] for p in got}
        cache_path(a.family).write_text(json.dumps(
            {"family": a.family, "lag_min": LAG_MIN, "validation": v, "mids": cache}, indent=2))
        print(f"wrote {cache_path(a.family).name}  ({len(cache)} mids)")


if __name__ == "__main__":
    main()
