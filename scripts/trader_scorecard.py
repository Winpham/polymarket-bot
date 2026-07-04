#!/usr/bin/env python3
"""
PROVEN-TRADER ROUTER SCORECARD — the read-only audit/replication instrument for the
`proven_router` arm (PREREG_2026-07-04T094304Z_proven_router.md).

The LIVE follow-set is computed in Rust (`refresh_router_followset`, migration 039) on the
trust-refresh cadence. This script re-derives the identical scorecard read-only and reports:

  1. The full per-wallet distribution (not just members) at OUR repriced entry —
     `our_entry = price + FOLLOWER_TAX + band_spread(band)`, `ret = (won−e)/e − FEE`,
     event-clustered at COALESCE(event_slug, condition_id) — so the follow-set is auditable
     against the population it was drawn from (the anti-survivorship discipline: the top of a
     ranked noisy population ALWAYS looks superhuman; report the whole distribution).
  2. The R3 persistence replication: within-wallet H1→H2 copy-return correlation (equal-halves
     by time per wallet, ≥MIN_HALF fills/half) and the FORWARD (H2) return of the H1 ≥ +10%
     cohort vs mid vs negative — WITH and WITHOUT the MM microstructure exclusion. This is the
     deep-dive's 0.338 / +16.2% finding, now reproducible on demand as the record accrues.
  3. Drift check: the latest `router_followset` batch (what the arm ACTUALLY counts) vs this
     script's recomputation — any mismatch beyond re-score timing is a bug, surfaced loudly.

KILL/HONESTY: membership uses the FROZEN pre-registered thresholds; nothing here is tunable
without amending the prereg. The follow-set's forward validity (R1) is judged by the standing
gate on the arm's own signals, never by this script. Read-only, paper-only.

  ./trader_scorecard.py             # live read; writes reports/trader_scorecard.json
  ./trader_scorecard.py --selftest  # synthetic fixtures with known answers; no DB
"""

import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
from collections import defaultdict

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
FEE = 0.02
FOLLOWER_TAX = 0.013     # copyability.py convention (D-truth-audit / entry 13)
BAND_LO, BAND_HI = 0.45, 0.90
WINDOW_DAYS = 365
MIN_FILLS = 100          # frozen membership floor
MIN_DAYS = 15
MIN_RETURN = 0.10
MM_RTR, MM_TSR, MM_SBR = 0.30, 0.25, 0.50   # interim microstructure screens (prereg)
MIN_HALF = 100           # deep-dive replication: ≥100 fills per half
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "trader_scorecard.json")


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def band(p):
    """width_bucket(p, 0, 1, 5) — same bands as the Rust re-scorer."""
    return min(int(p * 5) + 1, 5) if p < 1.0 else 6


def fetch_band_spreads():
    rows = q("""
      SELECT width_bucket(initial_mean_price, 0.0, 1.0, 5) AS band,
             AVG(GREATEST(entry_ask - entry_ask_mid, 0)) AS spread
      FROM consensus_signals
      WHERE entry_ask IS NOT NULL AND entry_ask_mid IS NOT NULL AND entry_ask_at IS NOT NULL
        AND EXTRACT(EPOCH FROM (entry_ask_at - first_detected_at)) <= 900
      GROUP BY 1""")
    return {int(r["band"]): float(r["spread"]) for r in rows if r["spread"]}


def fetch_fills():
    """Scored fills (band, window, resolved BUYs) with reprice inputs; one row per fill."""
    return q(f"""
      SELECT lower(wallet) AS wallet, COALESCE(event_slug, condition_id) AS ev,
             (ts AT TIME ZONE 'UTC')::date AS day, EXTRACT(EPOCH FROM ts) AS ts,
             price, outcome_won::int AS won
      FROM trader_fills
      WHERE side = 'BUY' AND resolved AND outcome_won IS NOT NULL
        AND price >= {BAND_LO} AND price < {BAND_HI}
        AND ts >= NOW() - INTERVAL '{WINDOW_DAYS} days'""")


def fetch_micro():
    rows = q("""
      WITH pos AS (
        SELECT lower(wallet) AS wallet, condition_id, outcome_index,
               COALESCE(SUM(size_usd) FILTER (WHERE side='BUY'), 0)  AS buy_usd,
               COALESCE(SUM(size_usd) FILTER (WHERE side='SELL'), 0) AS sell_usd,
               COUNT(*) FILTER (WHERE side='BUY')  AS n_buy,
               COUNT(*) FILTER (WHERE side='SELL') AS n_sell
        FROM trader_fills GROUP BY 1, 2, 3),
      sided AS (
        SELECT wallet, condition_id, COUNT(*) FILTER (WHERE n_buy > 0) AS n_out_held
        FROM pos GROUP BY 1, 2),
      two AS (SELECT wallet, AVG((n_out_held >= 2)::int)::float8 AS tsr FROM sided GROUP BY 1)
      SELECT p.wallet,
             AVG((p.n_sell > 0 AND p.n_buy > 0)::int)::float8 AS rtr,
             (SUM(LEAST(p.sell_usd, p.buy_usd)) / NULLIF(SUM(p.buy_usd), 0))::float8 AS sbr,
             t.tsr
      FROM pos p JOIN two t USING (wallet) GROUP BY p.wallet, t.tsr""")
    return {r["wallet"]: {"rtr": float(r["rtr"] or 0), "sbr": float(r["sbr"] or 0),
                          "tsr": float(r["tsr"] or 0)} for r in rows}


def reprice(price, spreads):
    return price + FOLLOWER_TAX + spreads.get(band(price), 0.0)


def is_mm(m):
    return m["rtr"] >= MM_RTR or m["tsr"] >= MM_TSR or m["sbr"] >= MM_SBR


def fetch_bot_flags():
    """The repo's OTHER MM detector (classify_trader_types, fpd>=400): wallet -> trader_type.
    router_verify A4 found the two detectors disagree on 51/161 wallets — membership excludes
    the UNION (mirrors the Rust re-scorer's NOT EXISTS bot-flag clause)."""
    rows = q("SELECT lower(proxy_wallet) AS wallet, trader_type FROM followed_traders")
    return {r["wallet"]: r["trader_type"] for r in rows}


def clustered(rows, spreads):
    """rows → per-wallet {copy_return (event-clustered), n_fills, n_days, n_events}."""
    ev = defaultdict(list)          # (wallet, ev) -> rets
    days = defaultdict(set)
    for r in rows:
        e = reprice(float(r["price"]), spreads)
        ev[(r["wallet"], r["ev"])].append((int(r["won"]) - e) / e - FEE)
        days[r["wallet"]].add(r["day"])
    by_wallet = defaultdict(list)   # wallet -> (ev_ret, n_fills_in_ev)
    for (w, _), rets in ev.items():
        by_wallet[w].append((sum(rets) / len(rets), len(rets)))
    out = {}
    for w, evs in by_wallet.items():
        rets = [x[0] for x in evs]
        out[w] = {"copy_return": sum(rets) / len(rets),
                  "n_events": len(rets),
                  "n_fills": sum(x[1] for x in evs),
                  "n_days": len(days[w])}
    return out


def members(scored, micro, bots=None):
    bots = bots or {}
    return sorted(w for w, s in scored.items()
                  if s["n_fills"] >= MIN_FILLS and s["n_days"] >= MIN_DAYS
                  and s["copy_return"] >= MIN_RETURN
                  and not is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0}))
                  and bots.get(w) != "bot")


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def persistence(rows, spreads, micro, exclude_mm):
    """R3: within-wallet H1→H2 (equal-halves by time) copy-return corr + cohort forwards."""
    per_wallet = defaultdict(list)
    for r in rows:
        per_wallet[r["wallet"]].append(r)
    h1v, h2v, cohorts = [], [], {"gte10": [], "mid": [], "neg": []}
    n_excluded = 0
    for w, rs in per_wallet.items():
        if exclude_mm and is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0})):
            n_excluded += 1
            continue
        rs.sort(key=lambda r: float(r["ts"]))
        half = len(rs) // 2
        a, b = rs[:half], rs[half:]
        if len(a) < MIN_HALF or len(b) < MIN_HALF:
            continue
        ca = clustered(a, spreads)[w]["copy_return"]
        cb = clustered(b, spreads)[w]["copy_return"]
        h1v.append(ca)
        h2v.append(cb)
        key = "gte10" if ca >= 0.10 else ("neg" if ca < 0 else "mid")
        cohorts[key].append(cb)
    fwd = {k: (sum(v) / len(v) if v else None, len(v)) for k, v in cohorts.items()}
    return {"corr_h1_h2": pearson(h1v, h2v), "n_wallets": len(h1v),
            "n_mm_excluded": n_excluded,
            "forward_h2_return": {k: {"mean": v[0], "n": v[1]} for k, v in fwd.items()}}


def latest_followset():
    """Latest published batch; [] when the table doesn't exist yet (pre-first-deploy)
    or no batch has been written (drift check reads as all-script_only then)."""
    exists = q("SELECT (to_regclass('router_followset') IS NOT NULL)::int AS ok")
    if not exists or exists[0]["ok"] != "1":
        return []
    rows = q("""
      SELECT wallet FROM router_followset
      WHERE scored_at = (SELECT MAX(scored_at) FROM router_followset)""")
    return sorted(r["wallet"] for r in rows)


# ---------------------------------------------------------------- selftest
def selftest():
    """Synthetic fixtures with known answers — must pass before any live read."""
    spreads = {}  # no spread model: reprice = price + tax

    def mk(wallet, n, won_rate, price=0.70, days=30):
        rows = []
        for i in range(n):
            rows.append({"wallet": wallet, "ev": f"{wallet}-ev{i}",
                         "day": f"d{i % days}", "ts": i,
                         "price": price, "won": 1 if (i % 100) < won_rate * 100 else 0})
        return rows

    # Skilled wallet: 85% hit at 0.70 ⇒ ret ≈ .85/.713 − 1.02 ≈ +0.17 ⇒ member.
    # Noise wallet: 72% hit ⇒ ≈ +0.0 ⇒ out. Churner: skilled but MM-flagged ⇒ out.
    rows = mk("skilled", 200, 0.85) + mk("noise", 200, 0.72) + mk("churner", 200, 0.85)
    micro = {"skilled": {"rtr": 0.03, "sbr": 0.04, "tsr": 0.01},
             "noise": {"rtr": 0.05, "sbr": 0.05, "tsr": 0.02},
             "churner": {"rtr": 0.78, "sbr": 0.92, "tsr": 0.64}}
    scored = clustered(rows, spreads)
    got = members(scored, micro)
    assert got == ["skilled"], f"membership: expected ['skilled'], got {got}"
    assert scored["skilled"]["copy_return"] > 0.10 and scored["noise"]["copy_return"] < 0.10

    # Thin wallet (<100 fills) never members regardless of return.
    thin = clustered(mk("thin", 50, 0.95), spreads)
    assert members(thin, {}) == [], "thin wallets must not member"

    # Persistence: persistent wallets (same skill both halves) ⇒ corr > 0 across a
    # skill spectrum; the ≥10% cohort's forward mean must exceed the negative cohort's.
    prows = []
    for i, wr in enumerate([0.90, 0.85, 0.80, 0.76, 0.72, 0.68]):
        prows += mk(f"w{i}", 2 * MIN_HALF, wr)
    p = persistence(prows, spreads, {}, exclude_mm=False)
    assert p["corr_h1_h2"] > 0.5, f"persistent fixture corr: {p['corr_h1_h2']}"
    f = p["forward_h2_return"]
    assert f["gte10"]["mean"] > f["neg"]["mean"], "cohort ordering violated"
    # MM exclusion drops the flagged wallet from the persistence set.
    p2 = persistence(prows, spreads, {"w0": {"rtr": 0.9, "sbr": 0.9, "tsr": 0.9}},
                     exclude_mm=True)
    assert p2["n_wallets"] == p["n_wallets"] - 1 and p2["n_mm_excluded"] == 1
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    spreads = fetch_band_spreads()
    rows = fetch_fills()
    micro = fetch_micro()
    bots = fetch_bot_flags()
    scored = clustered(rows, spreads)
    mem = members(scored, micro, bots)

    # Drift check vs the arm's actual set (latest batch; timing skew is expected
    # between re-scores, a persistent mismatch is a bug).
    live = latest_followset()
    drift = {"script_only": sorted(set(mem) - set(live)),
             "live_only": sorted(set(live) - set(mem))}

    dist = sorted(({"wallet": w, **{k: round(v, 4) if isinstance(v, float) else v
                                    for k, v in s.items()},
                    "mm_excluded": is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0}))}
                   for w, s in scored.items() if s["n_fills"] >= 30),
                  key=lambda r: -r["copy_return"])

    out = {
        "meta": {"fee": FEE, "follower_tax": FOLLOWER_TAX, "band": [BAND_LO, BAND_HI],
                 "window_days": WINDOW_DAYS, "min_fills": MIN_FILLS, "min_days": MIN_DAYS,
                 "min_return": MIN_RETURN, "mm_screens": {"rtr": MM_RTR, "tsr": MM_TSR,
                                                          "sbr": MM_SBR},
                 "band_spreads": {str(k): round(v, 4) for k, v in sorted(spreads.items())},
                 "prereg": "PREREG_2026-07-04T094304Z_proven_router.md"},
        "followset": mem,
        "followset_live": live,
        "drift": drift,
        "n_wallets_scored": len(scored),
        "distribution_top": dist[:40],
        "persistence_with_mm": persistence(rows, spreads, micro, exclude_mm=False),
        "persistence_mm_excluded": persistence(rows, spreads, micro, exclude_mm=True),
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    p, px = out["persistence_with_mm"], out["persistence_mm_excluded"]
    print(f"scored {len(scored)} wallets; follow-set = {len(mem)} {mem}")
    print(f"live follow-set = {len(live)}; drift script_only={drift['script_only']} "
          f"live_only={drift['live_only']}")
    print(f"R3 persistence corr H1→H2: with-MM {p['corr_h1_h2']:.3f} (n={p['n_wallets']}) | "
          f"MM-excluded {px['corr_h1_h2']:.3f} (n={px['n_wallets']}, "
          f"excluded {px['n_mm_excluded']})")
    for k in ("gte10", "mid", "neg"):
        f_ = px["forward_h2_return"][k]
        m = f"{f_['mean']:+.3f}" if f_["mean"] is not None else "—"
        print(f"  forward H2 ({k:>5}, MM-excl): {m}  n={f_['n']}")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
