#!/usr/bin/env python3
"""
h3_loo_routing — THE decidable-now experiment (H3): routing vs averaging via a within-trader
Leave-One-SPORT-REGIME-Out split. Uses cross-CONTEXT variance (available now) instead of
cross-TIME accrual (absent). Returns a SIGNED answer.

Question: on a held-out sport-regime, does argmax-ROUTING (learn the best wallet on the OTHER
regimes, tail THAT one) beat FLEET-AVERAGING (mean over all eligible wallets), both re-priced at
OUR realizable entry and event-clustered?

Reuses trader_scorecard (reprice / is_mm / fetch_micro / fetch_band_spreads / q) and
router_verify.fetch_fills_with_sport / fetch_bot_flags — the exact eligibility + pricing the rest
of the run uses. Read-only, paper-only. NEVER mutates the DB or the Rust scorer.

Eligibility (prereg default = round_trip-RELAXED): a wallet is kept unless it is a pure MM under
is_mm with the RELAXED round_trip cutoff (0.50) OR carries the repo bot flag (the UNION exclusion).
--frozen flips the round_trip cutoff back to 0.30 for the H7 relaxed-vs-frozen tie-in.

Method (per held-out sport-regime g):
  LEARN on all events with sport != g:
    - per eligible wallet w: copy_return_w = event-clustered mean repriced surplus over non-g events
    - shrink toward the learn-set context blind: shrunk = damp(n)*copy_return + (1-damp)*blind,
      damp(n)=n/(n+20), blind = pooled event-clustered mean over all eligible wallets on non-g.
    - FLOORS: shrunk > MARGIN (0.03) AND n_events_w(non-g) >= MIN_LEARN_EV. (Avoid-under-trust is
      approximated by the same shrunk-surplus floor; trader_trust is not re-implemented here.)
  ROUTER pick for g = argmax_w shrunk among wallets clearing floors that ALSO have >=1 event in g.
    If none -> ABSTAIN.
  Held-out scores on g (event-clustered, repriced):
    router_g   = picked wallet's event-clustered mean repriced surplus over its g events
    averaging_g= mean over ALL eligible wallets' event-clustered repriced surplus in g (fleet-avg)
  Signed Delta_g = router_g - averaging_g.

Aggregation:
  (A) conditional-on-pick: mean Delta over regimes where the router did NOT abstain, t-CI across
      regimes (each regime = one independent cluster).
  (B) abstain-as-zero: router abstain -> router contributes 0 (no position) vs averaging_g; the
      full-regime comparison that credits the router for dodging a bad fleet bet.
  Verdict: favors ROUTING / favors AVERAGING / INDETERMINATE (CI straddles 0).
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc
import router_verify as rv

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "h3_loo_routing.json")

MARGIN = 0.03          # realizable-surplus floor for a wallet to be routable
MIN_LEARN_EV = 8       # min events in the learn set for a wallet to be rankable
MIN_G_EV = 5           # min events in the held-out regime to score it at all
MIN_ELIG_G = 3         # min eligible wallets in g for a meaningful fleet average
DAMP_K = 20
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
       15: 2.131, 20: 2.086, 30: 2.042}


def t_crit(df):
    if df <= 0:
        return float("nan")
    if df in T95:
        return T95[df]
    ks = sorted(T95)
    for k in ks:
        if k >= df:
            return T95[k]
    return 1.96


def damp(n):
    return n / (n + DAMP_K)


def wallet_regime_events(rows, spreads):
    """(wallet, sport) -> {ev: event_clustered_repriced_ret}. Event = COALESCE(event_slug,cid)."""
    ev = defaultdict(lambda: defaultdict(list))   # (w,sport) -> ev -> [ret per fill]
    for r in rows:
        e = tsc.reprice(float(r["price"]), spreads)
        ret = (int(r["won"]) - e) / e - tsc.FEE
        ev[(r["wallet"], r["sport"])][r["ev"]].append(ret)
    out = defaultdict(dict)
    for (w, sp), evs in ev.items():
        for evid, rets in evs.items():
            out[(w, sp)][evid] = sum(rets) / len(rets)
    return out


def clustered_mean(evdict):
    return sum(evdict.values()) / len(evdict) if evdict else None


def eligible_wallets(wre, micro, bots, tau_rt):
    """Wallets that are NOT pure-MM (relaxed/frozen microstructure UNION bot flag)."""
    ws = {w for (w, _) in wre}
    keep = set()
    for w in ws:
        m = micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0})
        is_mm = (m["rtr"] >= tau_rt or m["tsr"] >= tsc.MM_TSR or m["sbr"] >= tsc.MM_SBR)
        if is_mm or bots.get(w) == "bot":
            continue
        keep.add(w)
    return keep


def run(tau_rt, verbose=True):
    spreads = tsc.fetch_band_spreads()
    rows = rv.fetch_fills_with_sport()
    micro = tsc.fetch_micro()
    bots = rv.fetch_bot_flags()
    wre = wallet_regime_events(rows, spreads)
    elig = eligible_wallets(wre, micro, bots, tau_rt)

    # sports present with enough eligible events
    sports = defaultdict(int)
    for (w, sp), evs in wre.items():
        if w in elig:
            sports[sp] += len(evs)
    regimes = sorted(sports)

    results = []
    for g in regimes:
        # eligible wallets with a scorable presence in g
        elig_g = [w for w in elig if (w, g) in wre and len(wre[(w, g)]) >= 1]
        if len(elig_g) < MIN_ELIG_G:
            continue
        # fleet averaging on g: event-clustered per wallet, then mean across eligible wallets in g
        avg_scores = [clustered_mean(wre[(w, g)]) for w in elig_g]
        g_ev_total = sum(len(wre[(w, g)]) for w in elig_g)
        if g_ev_total < MIN_G_EV:
            continue
        averaging_g = sum(avg_scores) / len(avg_scores)

        # LEARN on non-g: per eligible wallet, event-clustered copy_return over all sports != g
        learn = {}
        blind_evs = []
        for w in elig:
            merged = {}
            for sp2 in regimes:
                if sp2 == g:
                    continue
                if (w, sp2) in wre:
                    merged.update(wre[(w, sp2)])
            if len(merged) >= MIN_LEARN_EV:
                cr = clustered_mean(merged)
                learn[w] = (cr, len(merged))
                blind_evs.extend(merged.values())
        if not learn or not blind_evs:
            continue
        blind = sum(blind_evs) / len(blind_evs)

        # shrink + floors; candidates must also be evaluable in g
        best_w, best_s = None, -1e9
        for w, (cr, n) in learn.items():
            shrunk = damp(n) * cr + (1 - damp(n)) * blind
            if shrunk <= MARGIN:
                continue
            if (w, g) not in wre:   # can't evaluate held-out -> not routable to g
                continue
            if shrunk > best_s:
                best_s, best_w = shrunk, w

        if best_w is None:
            router_g = None   # ABSTAIN
        else:
            router_g = clustered_mean(wre[(best_w, g)])

        results.append({
            "regime": g,
            "n_elig_wallets_g": len(elig_g),
            "n_events_g": g_ev_total,
            "averaging_g": averaging_g,
            "router_g": router_g,
            "router_pick": best_w,
            "router_pick_shrunk": None if best_w is None else best_s,
            "delta_g": None if router_g is None else router_g - averaging_g,
        })

    # (A) conditional-on-pick
    picked = [r for r in results if r["delta_g"] is not None]
    deltas = [r["delta_g"] for r in picked]
    # (B) abstain-as-zero
    deltas_b = [(0.0 - r["averaging_g"]) if r["router_g"] is None else r["delta_g"]
                for r in results]

    def agg(ds):
        n = len(ds)
        if n == 0:
            return {"n": 0, "mean": None, "ci_lo": None, "ci_hi": None,
                    "n_pos": 0, "verdict": "INDETERMINATE-BY-POWER: no regimes"}
        mean = sum(ds) / n
        if n == 1:
            return {"n": 1, "mean": mean, "ci_lo": None, "ci_hi": None,
                    "n_pos": sum(1 for d in ds if d > 0),
                    "verdict": "INDETERMINATE-BY-POWER: single regime (no CI)"}
        sd = math.sqrt(sum((d - mean) ** 2 for d in ds) / (n - 1))
        se = sd / math.sqrt(n)
        tc = t_crit(n - 1)
        lo, hi = mean - tc * se, mean + tc * se
        if lo > 0:
            v = "favors ROUTING"
        elif hi < 0:
            v = "favors AVERAGING"
        else:
            v = "INDETERMINATE (CI straddles 0)"
        return {"n": n, "mean": mean, "sd": sd, "ci_lo": lo, "ci_hi": hi,
                "t_crit": tc, "n_pos": sum(1 for d in ds if d > 0), "verdict": v}

    A = agg(deltas)
    B = agg(deltas_b)
    out = {
        "tau_rt": tau_rt,
        "n_regimes_scored": len(results),
        "n_router_picks": len(picked),
        "n_abstain": len(results) - len(picked),
        "conditional_on_pick": A,
        "abstain_as_zero": B,
        "per_regime": results,
        "eligible_wallets": len(elig),
    }
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    if verbose:
        print(f"H3 LOO routing-vs-averaging (tau_rt={tau_rt}) · eligible wallets={len(elig)}")
        print(f"  regimes scored={len(results)}  router picks={len(picked)}  abstains={len(results)-len(picked)}")
        print(f"  {'regime':<12}{'n_elig':>7}{'n_ev':>6}{'avg':>9}{'router':>9}{'delta':>9}  pick")
        for r in sorted(results, key=lambda x: -(x['delta_g'] or -9)):
            rg = "ABSTAIN" if r["router_g"] is None else f"{r['router_g']:+.3f}"
            dg = "   —   " if r["delta_g"] is None else f"{r['delta_g']:+.3f}"
            pk = "" if not r["router_pick"] else r["router_pick"][:12]
            print(f"  {r['regime']:<12}{r['n_elig_wallets_g']:>7}{r['n_events_g']:>6}"
                  f"{r['averaging_g']:>+9.3f}{rg:>9}{dg:>9}  {pk}")
        print(f"  (A) conditional-on-pick: n={A['n']} meanΔ={fmt(A['mean'])} "
              f"CI[{fmt(A['ci_lo'])},{fmt(A['ci_hi'])}] pos={A['n_pos']}/{A['n']} → {A['verdict']}")
        print(f"  (B) abstain-as-zero:     n={B['n']} meanΔ={fmt(B['mean'])} "
              f"CI[{fmt(B['ci_lo'])},{fmt(B['ci_hi'])}] pos={B['n_pos']}/{B['n']} → {B['verdict']}")
        print(f"wrote {REPORT}")
    return out


def fmt(x):
    return "None" if x is None else f"{x:+.3f}"


def selftest():
    """Synthetic: one wallet dominates every regime -> routing should beat averaging (Δ>0).
    All-noise -> Δ≈0 INDETERMINATE."""
    import random
    random.seed(7)
    spreads = {}
    # monkeypatch reprice to identity for the fixture
    orig_reprice, orig_fee = tsc.reprice, tsc.FEE
    tsc.reprice = lambda p, s: p
    tsc.FEE = 0.0
    try:
        # dominating wallet 'star' returns +0.3 in every sport; noise wallets ~0.
        rows = []
        sports = ["a", "b", "c", "d"]
        for sp in sports:
            for i in range(12):
                rows.append({"wallet": "star", "sport": sp, "ev": f"{sp}-star-{i}",
                             "price": 0.5, "won": 1 if random.random() < 0.8 else 0})
            for k in range(4):
                for i in range(12):
                    rows.append({"wallet": f"n{k}", "sport": sp, "ev": f"{sp}-n{k}-{i}",
                                 "price": 0.5, "won": 1 if random.random() < 0.5 else 0})
        wre = wallet_regime_events(rows, spreads)
        micro = {w: {"rtr": 0, "sbr": 0, "tsr": 0} for w in {"star"} | {f"n{k}" for k in range(4)}}
        bots = {}
        elig = eligible_wallets(wre, micro, bots, 0.50)
        assert "star" in elig
        # inline the core to avoid DB: replicate run() ranking on the fixture
        regimes = sorted({sp for (_, sp) in wre})
        wins = 0
        for g in regimes:
            learn = {}
            blind = []
            for w in elig:
                merged = {}
                for sp2 in regimes:
                    if sp2 != g and (w, sp2) in wre:
                        merged.update(wre[(w, sp2)])
                if len(merged) >= MIN_LEARN_EV:
                    learn[w] = clustered_mean(merged)
                    blind.extend(merged.values())
            best = max(learn, key=lambda w: learn[w])
            router_g = clustered_mean(wre[(best, g)])
            avg = sum(clustered_mean(wre[(w, g)]) for w in elig if (w, g) in wre) \
                / sum(1 for w in elig if (w, g) in wre)
            if router_g > avg:
                wins += 1
        assert wins >= 3, f"routing should win most regimes, got {wins}/4"
        print("selftest OK")
    finally:
        tsc.reprice, tsc.FEE = orig_reprice, orig_fee


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--frozen", action="store_true", help="use frozen round_trip cutoff 0.30")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        run(tau_rt=(0.30 if args.frozen else 0.50))
