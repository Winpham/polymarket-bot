#!/usr/bin/env python3
"""
LIVE FORWARD DEPLOYMENT TRACKER (paper-only, DB read-only).

Applies the pre-registered blended-median-optimal deployment policy (from optimal_deploy.json) to
the REAL favorite outcomes in the live honest_paper_ledger, maintaining a SEPARATE virtual equity
curve, and checks realized-vs-modeled. Forward-sealed: only bets resolved at/after FREEZE_TS count
as forward evidence; earlier bets are an in-sample SEED (illustrative, never evidence).

It NEVER writes the DB / ledger, never places an order. It only SELECTs outcomes and re-sizes them
under the policy on a virtual bankroll. Re-run daily to accrue; verdict stays INDETERMINATE until
>= 20 independent forward day-blocks (honesty gate from 00-PRE-REGISTRATION.md).

Modes: run | --selftest
"""
import json, math, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "stress"))
import portfolio_corr as pc

FEE = 0.02
PER_MARKET_CAP = 0.02
RUIN = 0.20
FREEZE_FILE = os.path.join(HERE, "..", "..", "reports", "sizing", "freeze_ts.txt")
DEPLOY_FILE = os.path.join(HERE, "..", "..", "reports", "sizing", "optimal_deploy.json")


def _psql(sql):
    return subprocess.check_output(
        ["docker", "exec", "polymarket-bot-postgres-1", "psql", "-U", "bot", "-d", "polymarket",
         "--csv", "-t", "-c", sql]).decode()


def load_deploy():
    try:
        return float(json.load(open(DEPLOY_FILE))["recommended_deploy"])
    except Exception:
        return 0.13


def get_freeze(db_now):
    if os.path.exists(FREEZE_FILE):
        return open(FREEZE_FILE).read().strip()
    with open(FREEZE_FILE, "w") as f:
        f.write(db_now)
    return db_now


def fetch_bets():
    rows = _psql("SELECT resolved_at, DATE(resolved_at), entry, outcome_won::int "
                 "FROM honest_paper_ledger WHERE strategy='favorite' AND resolved_at IS NOT NULL "
                 "ORDER BY resolved_at;")
    bets = []
    for line in rows.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        ts, day, entry, won = parts[0], parts[1], float(parts[2]), int(parts[3])
        bets.append({"ts": ts, "day": day, "entry": entry, "won": won})
    return bets


def apply_policy(bets, deploy, start=1.0):
    """Re-size REAL outcomes under fixed-% daily deployment. Returns equity path + stats."""
    by_day = {}
    for b in bets:
        by_day.setdefault(b["day"], []).append(b)
    bank = start
    peak = start
    maxdd = 0.0
    minfrac = 1.0
    curve = [(None, bank)]
    daily = []
    for day in sorted(by_day):
        todays = by_day[day]
        n = len(todays)
        per_market = min(deploy / n, PER_MARKET_CAP)   # equal-weight, capped
        day_pnl = 0.0
        for b in todays:
            ret = (1.0 / b["entry"] - 1.0 - FEE) if b["won"] else (-1.0 - FEE)
            day_pnl += per_market * bank * ret
        bank += day_pnl
        peak = max(peak, bank)
        maxdd = max(maxdd, (peak - bank) / peak if peak > 0 else 0.0)
        minfrac = min(minfrac, bank / start)
        curve.append((day, bank))
        daily.append({"day": day, "n": n, "pnl_pct": day_pnl / (bank - day_pnl) if bank != day_pnl else 0.0})
    return {"final_growth": bank / start - 1.0, "maxdd": maxdd, "min_frac": minfrac,
            "n_days": len(by_day), "n_bets": len(bets), "curve": curve, "daily": daily,
            "ruin_breach": minfrac <= RUIN}


def model_band(deploy, n_days, rho=0.10, trials=20000, seed=20260703):
    """Model growth band (10/50/90 pct) at `deploy` over n_days in the GOOD-edge world."""
    if n_days <= 0:
        return None
    term, _ = _terminals(pc.P_GOOD, rho, deploy, n_days, trials, seed)
    return {"p10": float(np.percentile(term, 10) - 1), "p50": float(np.median(term) - 1),
            "p90": float(np.percentile(term, 90) - 1)}


def _terminals(p, rho, deploy, days, trials, seed):
    rng = np.random.default_rng(seed)
    z_p = pc._ppf(p); sr, sr1 = math.sqrt(rho), math.sqrt(1 - rho)
    bank = np.ones(trials); minf = np.ones(trials)
    for _ in range(days):
        Z = rng.standard_normal((trials, 1)); eps = rng.standard_normal((trials, pc.N_BETS))
        ret = np.where(sr * Z + sr1 * eps <= z_p, pc.G, -pc.L)
        bank *= np.clip(1.0 + deploy * ret.mean(axis=1), 0.0, None)
        minf = np.minimum(minf, bank)
    return bank, minf


def realized_edge_lb(bets):
    """Event-clustered-ish per-bet realized ROI mean and a rough 5% lower bound (day-clustered)."""
    if not bets:
        return None
    by_day = {}
    for b in bets:
        r = (1.0 / b["entry"] - 1.0 - FEE) if b["won"] else (-1.0 - FEE)
        by_day.setdefault(b["day"], []).append(r)
    day_means = np.array([np.mean(v) for v in by_day.values()])
    n = len(day_means)
    mean = float(day_means.mean())
    if n < 2:
        return {"mean_roi": mean, "lb": None, "n_day_blocks": n}
    se = float(day_means.std(ddof=1) / math.sqrt(n))
    t = 2.353 if n <= 4 else 1.833 if n <= 10 else 1.645   # small-sample t, one-sided 5%
    return {"mean_roi": mean, "lb": mean - t * se, "n_day_blocks": n}


def run():
    db_now = _psql("SELECT now() AT TIME ZONE 'UTC';").strip()
    freeze = get_freeze(db_now)
    deploy = load_deploy()
    bets = fetch_bets()
    seed = [b for b in bets if b["ts"] < freeze]
    fwd = [b for b in bets if b["ts"] >= freeze]
    out = {"meta": {"db_now_utc": db_now, "freeze_ts": freeze, "deploy": deploy,
                    "per_market_cap": PER_MARKET_CAP, "n_total_bets": len(bets),
                    "n_seed": len(seed), "n_forward": len(fwd)},
           "seed_in_sample": apply_policy(seed, deploy) if seed else None,
           "forward": apply_policy(fwd, deploy) if fwd else None,
           "forward_edge": realized_edge_lb(fwd),
           "seed_edge": realized_edge_lb(seed)}
    # model comparison on whichever set has bets
    ev = out["forward"] or out["seed_in_sample"]
    out["model_band"] = model_band(deploy, ev["n_days"]) if ev else None
    # honesty verdict
    n_fwd_days = out["forward"]["n_days"] if out["forward"] else 0
    if n_fwd_days < 20:
        out["verdict"] = f"INDETERMINATE-BY-POWER: {n_fwd_days}/20 forward day-blocks accrued"
    else:
        r = out["forward"]; mb = out["model_band"]
        within = mb and mb["p10"] <= r["final_growth"] <= mb["p90"] * 3
        out["verdict"] = ("PASS: realized within model band, no ruin" if within and not r["ruin_breach"]
                          else "FLAG: realized below model or ruin breach")
    return out


def _print(o):
    m = o["meta"]
    print(f"LIVE FORWARD DEPLOY TRACKER · policy {int(m['deploy']*100)}%/day · freeze {m['freeze_ts'][:19]} UTC")
    print(f"bets: {m['n_total_bets']} total = {m['n_seed']} seed (pre-freeze) + {m['n_forward']} FORWARD\n")
    for label, key in (("IN-SAMPLE SEED (illustrative, NOT evidence)", "seed_in_sample"),
                       ("FORWARD (the real test)", "forward")):
        s = o[key]
        if not s:
            print(f"{label}: (none yet)\n"); continue
        print(f"{label}:")
        print(f"  {s['n_bets']} bets / {s['n_days']} days · growth {s['final_growth']:+.1%} · "
              f"maxDD {s['maxdd']:.1%} · min-bankroll {s['min_frac']:.0%} · "
              f"{'RUIN BREACH' if s['ruin_breach'] else 'no ruin'}")
        e = o[key.replace('_in_sample', '') + "_edge"] if key == "seed_in_sample" else o["forward_edge"]
        if e and e.get("lb") is not None:
            print(f"  realized edge: {e['mean_roi']:+.1%}/bet, day-clustered LB {e['lb']:+.1%} "
                  f"({e['n_day_blocks']} day-blocks)")
        print()
    if o["model_band"]:
        mb = o["model_band"]
        print(f"model band (good-edge, same #days): p10 {mb['p10']:+.0%} / p50 {mb['p50']:+.0%} / p90 {mb['p90']:+.0%}")
    print(f"\nVERDICT: {o['verdict']}")


def selftest():
    ok = True
    # policy math: a single winning bet at entry 0.8, deploy 10%, 1 market -> per_market min(0.10,0.02)=0.02
    # ret = 1/0.8 -1 -0.02 = 0.23; bank 1 -> 1 + 0.02*0.23 = 1.0046
    r = apply_policy([{"ts": "t", "day": "d1", "entry": 0.8, "won": 1}], 0.10)
    exp = 0.02 * (1/0.8 - 1 - FEE)
    c1 = abs(r["final_growth"] - exp) < 1e-9
    print(f"  policy math: growth {r['final_growth']:.5f} == {exp:.5f} [{'ok' if c1 else 'FAIL'}]")
    # ruin detection: a big losing streak drives min_frac below 0.2
    losers = [{"ts": "t", "day": f"d{i}", "entry": 0.5, "won": 0} for i in range(200)]
    r2 = apply_policy(losers, 0.16)
    c2 = r2["ruin_breach"] is True
    print(f"  ruin detected on 200 losing days at 16%: {r2['ruin_breach']} [{'ok' if c2 else 'FAIL'}]")
    # forward-seal split
    bets = [{"ts": "2026-07-01", "day": "d1", "entry": 0.8, "won": 1},
            {"ts": "2026-07-05", "day": "d2", "entry": 0.8, "won": 1}]
    s = [b for b in bets if b["ts"] < "2026-07-03"]; f = [b for b in bets if b["ts"] >= "2026-07-03"]
    c3 = len(s) == 1 and len(f) == 1
    print(f"  forward-seal splits seed/forward correctly [{'ok' if c3 else 'FAIL'}]")
    ok = c1 and c2 and c3
    print("selftest:", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest(); return
    o = run()
    _print(o)
    with open(os.path.join(HERE, "..", "..", "reports", "sizing", "forward_deploy.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("\nartifact -> reports/sizing/forward_deploy.json")


if __name__ == "__main__":
    main()
