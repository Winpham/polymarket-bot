#!/usr/bin/env python3
"""
ROUTER FALSE-POSITIVE ATTACK SUITE — adversarial verification of the proven-trader router's
first read (+10.2% MM-excluded forward cohort return, entry 2026-07-04-proven-router).

The first read had four unclosed false-positive channels. Each gets a pre-named attack; the
router's forward thesis (R1) survives ONLY if it survives all of them:

  A1 WITHIN-EVENT LEAK (the known within-match leak class): trader_scorecard.py splits each
     wallet's fills into H1/H2 halves BY FILL — one event's fills can straddle the boundary,
     so H1 "selection" and H2 "evaluation" share resolved outcomes. Fix: EVENT-SAFE halves
     (whole events assigned by first-fill time). If corr/cohort-forward collapses ⇒ the
     persistence was leakage.
  A2 CORRELATED EVENTS / FAKE N: the +10.2% was a mean over 32 wallets who bet the SAME
     games. Fix: pool the cohort's H2 fills, dedup to one observation per EVENT, then
     day-cluster the SE (effective N = distinct days, the D16/D17 convention) and report the
     one-sided 95% LB, not the point.
  A3 NO BLIND BASELINE (favorite-longshot bias): raw copy-return ≥ 0 is NOT skill — blind
     45–90¢ favorites have a positive base rate, and "good favorite days" lift everyone.
     Fix: per-event surplus over the SAME-DAY fleet mean (day-matched population blind), plus
     a PERMUTATION NULL: 1000 random same-size cohorts from the eligible pool — where does
     the real cohort's surplus sit in that distribution?
  A4 MARKET-MOVERS THE EXISTING DETECTOR ALREADY FLAGGED: the scorecard used only the interim
     microstructure screens; the repo ALREADY flags wallets via classify_trader_types
     (followed_traders.trader_type='bot', fpd≥400). Reconcile both detectors on the eligible
     pool, report disagreement, and re-run everything excluding the UNION (belt+suspenders).
     Plus a SURVIVORSHIP probe: do inactive (dropped-off-leaderboard) wallets keep accruing
     fills? If capture stops at deactivation, decayed wallets' forward records are censored
     and every forward number is inflated.

Also emits the DAY-LEVEL profile of the cohort forward (fraction of profitable days, worst
days) — the honest input to the "can all days be profitable" question.

Read-only, paper-only. ./router_verify.py [--perms 1000]; --selftest for the split/pool logic.
Writes reports/router_verify.json.
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

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "router_verify.json")
MIN_HALF = tsc.MIN_HALF
Z95 = 1.6449


# ---------------------------------------------------------------- data shaping
def fetch_fills_with_sport():
    return tsc.q(f"""
      SELECT lower(wallet) AS wallet, COALESCE(event_slug, condition_id) AS ev,
             (ts AT TIME ZONE 'UTC')::date AS day, EXTRACT(EPOCH FROM ts) AS ts,
             price, outcome_won::int AS won, COALESCE(sport, 'other') AS sport
      FROM trader_fills
      WHERE side = 'BUY' AND resolved AND outcome_won IS NOT NULL
        AND price >= {tsc.BAND_LO} AND price < {tsc.BAND_HI}
        AND ts >= NOW() - INTERVAL '{tsc.WINDOW_DAYS} days'""")


def fetch_bot_flags():
    rows = tsc.q("SELECT lower(proxy_wallet) AS wallet, trader_type FROM followed_traders")
    return {r["wallet"]: r["trader_type"] for r in rows}


def wallet_events(rows, spreads):
    """wallet -> [ (first_ts, ev, day, sport, mean_fill_ret, n_fills) ] sorted by first_ts."""
    acc = defaultdict(lambda: defaultdict(lambda: [math.inf, None, None, [], 0]))
    for r in rows:
        e = tsc.reprice(float(r["price"]), spreads)
        ret = (int(r["won"]) - e) / e - tsc.FEE
        a = acc[r["wallet"]][r["ev"]]
        a[0] = min(a[0], float(r["ts"]))
        a[1] = a[1] or r["day"]
        a[2] = a[2] or r["sport"]
        a[3].append(ret)
        a[4] += 1
    out = {}
    for w, evs in acc.items():
        lst = [(a[0], ev, a[1], a[2], sum(a[3]) / len(a[3]), a[4]) for ev, a in evs.items()]
        lst.sort()
        out[w] = lst
    return out


def event_safe_halves(evs):
    """Split whole events (ordered by first fill) so fill counts split ~half.
    Returns (h1_events, h2_events) or None if either half < MIN_HALF fills."""
    total = sum(e[5] for e in evs)
    cum, cut = 0, 0
    for i, e in enumerate(evs):
        cum += e[5]
        if cum >= total / 2:
            cut = i + 1
            break
    h1, h2 = evs[:cut], evs[cut:]
    if sum(e[5] for e in h1) < MIN_HALF or sum(e[5] for e in h2) < MIN_HALF:
        return None
    return h1, h2


def clustered_ret(events):
    return sum(e[4] for e in events) / len(events)


def pool_events(wallet_list, halves, which):
    """Pool wallets' H2 (or H1) events, dedup by ev (mean across wallets) →
    {ev: (day, sport, ret)}."""
    by_ev = defaultdict(list)
    for w in wallet_list:
        for e in halves[w][which]:
            by_ev[e[1]].append(e)
    return {ev: (es[0][2], es[0][3], sum(x[4] for x in es) / len(es))
            for ev, es in by_ev.items()}


def day_stats(pooled, fleet_day):
    """Day-clustered mean/LB of raw ret and of surplus over the day-matched fleet blind."""
    by_day_raw, by_day_sur = defaultdict(list), defaultdict(list)
    for _, (day, _, ret) in pooled.items():
        by_day_raw[day].append(ret)
        if day in fleet_day:
            by_day_sur[day].append(ret - fleet_day[day])
    def agg(by_day):
        days = sorted(by_day)
        dm = [sum(v) / len(v) for v in (by_day[d] for d in days)]
        n = len(dm)
        if n == 0:
            return {"mean": None, "lb": None, "n_days": 0}
        mean = sum(dm) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in dm) / (n - 1)) if n > 1 else float("nan")
        return {"mean": mean, "lb": mean - Z95 * sd / math.sqrt(n) if n > 1 else None,
                "n_days": n, "day_means": dict(zip([str(d) for d in days], dm))}
    return agg(by_day_raw), agg(by_day_sur)


# ---------------------------------------------------------------- main analyses
def run(perms):
    spreads = tsc.fetch_band_spreads()
    rows = fetch_fills_with_sport()
    micro = tsc.fetch_micro()
    bots = fetch_bot_flags()
    wev = wallet_events(rows, spreads)

    # Fleet day blind: ALL wallets' events, dedup by ev, day means (the population base rate).
    all_pool = pool_events(list(wev), {w: (None, wev[w]) for w in wev}, 1)
    fleet_day = defaultdict(list)
    for _, (day, _, ret) in all_pool.items():
        fleet_day[day].append(ret)
    fleet_day = {d: sum(v) / len(v) for d, v in fleet_day.items()}

    # A4: reconcile the two MM detectors on the half-eligible pool.
    halves = {}
    for w, evs in wev.items():
        h = event_safe_halves(evs)
        if h:
            halves[w] = h
    def micro_mm(w):
        return tsc.is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0}))
    def bot_mm(w):
        return bots.get(w) == "bot"
    pool_all = sorted(halves)
    recon = {"eligible_pool": len(pool_all),
             "micro_only": sum(1 for w in pool_all if micro_mm(w) and not bot_mm(w)),
             "bot_only": sum(1 for w in pool_all if bot_mm(w) and not micro_mm(w)),
             "both": sum(1 for w in pool_all if bot_mm(w) and micro_mm(w)),
             "neither": sum(1 for w in pool_all if not bot_mm(w) and not micro_mm(w))}
    excluded_union = {w for w in pool_all if micro_mm(w) or bot_mm(w)}
    eligible = [w for w in pool_all if w not in excluded_union]

    # A1: event-safe persistence + cohort (vs the fill-split numbers from the first read).
    h1r = {w: clustered_ret(halves[w][0]) for w in eligible}
    h2r = {w: clustered_ret(halves[w][1]) for w in eligible}
    corr = tsc.pearson([h1r[w] for w in eligible], [h2r[w] for w in eligible])
    cohort = sorted(w for w in eligible if h1r[w] >= 0.10)
    coh_mid = [w for w in eligible if 0 <= h1r[w] < 0.10]
    coh_neg = [w for w in eligible if h1r[w] < 0]

    # A2+A3: pooled event-dedup forward with day-clustered LB + surplus over fleet blind.
    pooled = pool_events(cohort, halves, 1)
    raw, sur = day_stats(pooled, fleet_day)
    mids = day_stats(pool_events(coh_mid, halves, 1), fleet_day)[1] if coh_mid else None
    negs = day_stats(pool_events(coh_neg, halves, 1), fleet_day)[1] if coh_neg else None

    # A3 permutation null: random same-size cohorts from the eligible pool.
    obs = sur["mean"]
    null_ge = 0
    nulls = []
    rng = random.Random(20260704)
    for _ in range(perms):
        draw = rng.sample(eligible, min(len(cohort), len(eligible)))
        _, s = day_stats(pool_events(draw, halves, 1), fleet_day)
        if s["mean"] is not None:
            nulls.append(s["mean"])
            if s["mean"] >= obs:
                null_ge += 1
    p_emp = (null_ge + 1) / (len(nulls) + 1) if nulls else None

    # Regime split of the cohort forward (is it all one tournament?).
    by_sport, by_month = defaultdict(list), defaultdict(list)
    for _, (day, sport, ret) in pooled.items():
        sur_ev = ret - fleet_day.get(day, 0.0)
        by_sport[sport].append(sur_ev)
        by_month[str(day)[:7]].append(sur_ev)
    regime = {"sport": {k: {"surplus": sum(v) / len(v), "n_events": len(v)}
                        for k, v in sorted(by_sport.items())},
              "month": {k: {"surplus": sum(v) / len(v), "n_events": len(v)}
                        for k, v in sorted(by_month.items())}}

    # Day-level profitability profile (raw + surplus) for the cohort forward.
    dm = raw.get("day_means", {})
    dms = sur.get("day_means", {})
    profile = {
        "n_days": raw["n_days"],
        "pct_days_raw_positive": (sum(1 for v in dm.values() if v > 0) / len(dm)) if dm else None,
        "pct_days_surplus_positive": (sum(1 for v in dms.values() if v > 0) / len(dms)) if dms else None,
        "worst_days_raw": sorted(dm.items(), key=lambda kv: kv[1])[:3],
        "best_days_raw": sorted(dm.items(), key=lambda kv: -kv[1])[:3],
    }

    # A4 survivorship probe: does capture continue after a wallet drops off the leaderboard?
    surv = tsc.q("""
      SELECT active, COUNT(*) AS n,
             COUNT(*) FILTER (WHERE last_fill > last_seen_on_lb + INTERVAL '1 day') AS fills_after_drop
      FROM followed_traders t
      LEFT JOIN LATERAL (
        SELECT MAX(ts) AS last_fill FROM trader_fills f WHERE f.wallet = lower(t.proxy_wallet)
      ) lf ON TRUE
      GROUP BY active""")

    # Follow-set members under the UNION exclusion (does the live set change?).
    scored = tsc.clustered([r for r in rows], spreads)
    fs_micro = tsc.members(scored, micro)
    fs_union = [w for w in fs_micro if not bot_mm(w)]

    out = {
        "meta": {"perms": perms, "cohort_rule": "event-safe H1>=0.10, >=100 fills/half, "
                                                "MM excluded by UNION(microstructure, trader_type='bot')"},
        "a4_mm_reconciliation": recon,
        "a4_survivorship": surv,
        "followset_micro_only": fs_micro,
        "followset_union": fs_union,
        "a1_event_safe": {"corr_h1_h2": corr, "n_wallets": len(eligible),
                          "cohort_n": len(cohort), "cohort": cohort},
        "a2_forward_cohort": {"raw": {k: raw[k] for k in ("mean", "lb", "n_days")},
                              "surplus_vs_fleet_day": {k: sur[k] for k in ("mean", "lb", "n_days")},
                              "mid_surplus": {k: mids[k] for k in ("mean", "lb", "n_days")} if mids else None,
                              "neg_surplus": {k: negs[k] for k in ("mean", "lb", "n_days")} if negs else None},
        "a3_permutation_null": {"observed_surplus": obs, "p_emp": p_emp,
                                "null_mean": sum(nulls) / len(nulls) if nulls else None,
                                "null_p95": sorted(nulls)[int(0.95 * len(nulls))] if nulls else None},
        "regime_split": regime,
        "day_profile": profile,
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"A4 MM reconciliation on {recon['eligible_pool']} half-eligible wallets: "
          f"both={recon['both']} micro_only={recon['micro_only']} bot_only={recon['bot_only']} "
          f"clean={recon['neither']}")
    print(f"follow-set micro-only={fs_micro} → union={fs_union}")
    print(f"A1 event-safe: corr={corr:.3f} (n={len(eligible)}), cohort n={len(cohort)}")
    print(f"A2 forward: raw mean={raw['mean']:+.3f} LB={raw['lb']:+.3f} over {raw['n_days']} days | "
          f"surplus mean={sur['mean']:+.3f} LB={sur['lb']:+.3f}")
    if mids:
        print(f"   mid surplus={mids['mean']:+.3f}, neg surplus={negs['mean']:+.3f}" if negs else "")
    print(f"A3 permutation null: observed={obs:+.3f} p_emp={p_emp:.4f} "
          f"null_mean={out['a3_permutation_null']['null_mean']:+.4f} "
          f"null_p95={out['a3_permutation_null']['null_p95']:+.4f}")
    print(f"regime: {json.dumps(regime['sport'], default=str)}")
    print(f"months: {json.dumps(regime['month'], default=str)}")
    print(f"day profile: {profile['n_days']} days, raw-positive "
          f"{profile['pct_days_raw_positive']:.0%}, surplus-positive "
          f"{profile['pct_days_surplus_positive']:.0%}, worst {profile['worst_days_raw']}")
    print(f"survivorship: {surv}")
    print(f"wrote {REPORT}")


# ---------------------------------------------------------------- selftest
def selftest():
    # Event-safe split assigns WHOLE events: a straddling event never lands in both halves.
    evs = [(t, f"ev{t}", f"d{t}", "soccer", 0.1, 40) for t in range(6)]  # 240 fills, 6 events
    h = event_safe_halves(evs)
    assert h and not (set(e[1] for e in h[0]) & set(e[1] for e in h[1])), "halves share events"
    assert sum(e[5] for e in h[0]) >= MIN_HALF and sum(e[5] for e in h[1]) >= MIN_HALF

    # Pooling dedups shared events across wallets (fake-N killer).
    halves = {"a": ([], [(0, "evX", "d0", "s", 0.2, 5)]),
              "b": ([], [(0, "evX", "d0", "s", 0.0, 5), (1, "evY", "d1", "s", 0.1, 5)])}
    pooled = pool_events(["a", "b"], halves, 1)
    assert len(pooled) == 2 and abs(pooled["evX"][2] - 0.1) < 1e-9, "event dedup broken"

    # Day stats: surplus vs a flat fleet blind of +0.05.
    raw, sur = day_stats(pooled, {"d0": 0.05, "d1": 0.05})
    assert abs(raw["mean"] - 0.1) < 1e-9 and abs(sur["mean"] - 0.05) < 1e-9
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--perms", type=int, default=1000)
    a = ap.parse_args()
    selftest() if a.selftest else run(a.perms)
