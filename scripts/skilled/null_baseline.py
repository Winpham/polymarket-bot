#!/usr/bin/env python3
"""
WS-0.2 — FROZEN retrospective NULL baseline for the "Identify the Genuinely Skilled" run.

Reproduces, on the CURRENT snapshot, that past-performance ranking of traders does not
persist early->late. Three signals, all event-clustered, split by PLACEMENT DAY (leak-free):

  (a) blind-surplus rank   : per-wallet mean surplus (a - blind_edge[band]); early rank vs
                             late mean  -> Spearman persistence across wallets.
  (b) realized ROI rank    : per-wallet mean directional advantage a=(won-price); same.
  (c) success-rate select  : top-tercile wallets by early success-rate (win frac); their
                             LATE blind-surplus (edge retained) vs the fleet.

Unit of persistence = the WALLET; each wallet's signal is an event-clustered mean over
ev=COALESCE(event_slug,condition_id). N reported = #wallets meeting MIN_EV in BOTH windows.
Cluster-bootstrap CI resamples WALLETS. NON-MM (directional) cohort only (churner screen).

READ-ONLY. Writes reports/skilled/null_baseline.json. `--selftest` runs synthetic checks, no DB.
"""
import argparse, json, math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(os.path.dirname(HERE)) + "/scripts"   # wt/<slug>/scripts
sys.path.insert(0, SCRIPTS)
import mm_common as mc   # noqa: E402

MIN_EV = 10          # events per HALF per wallet (within-wallet equal time-halves, R3 method)
REPORT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "reports", "skilled", "null_baseline.json")


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    if len(xs) < 3:
        return float("nan")
    rx, ry = _rank(xs), _rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    sxx = sum((rx[i] - mx) ** 2 for i in range(n))
    syy = sum((ry[i] - my) ** 2 for i in range(n))
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def boot_ci(xs, ys, stat, n_boot=2000, seed_stream=None):
    """Cluster bootstrap over paired wallet points (index resample). Deterministic LCG (no
    Math.random equivalent needed); returns (lo, hi, point) at 95%."""
    n = len(xs)
    point = stat(xs, ys)
    if n < 5:
        return (float("nan"), float("nan"), point)
    # simple deterministic LCG for reproducibility without Date/random
    s = 0x2545F4914F6CDD1D
    reps = []
    for _ in range(n_boot):
        bx, by = [], []
        for _ in range(n):
            s = (6364136223846793005 * s + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
            idx = (s >> 17) % n
            bx.append(xs[idx]); by.append(ys[idx])
        v = stat(bx, by)
        if v == v:
            reps.append(v)
    reps.sort()
    lo = reps[int(0.025 * len(reps))]
    hi = reps[int(0.975 * len(reps))]
    return (lo, hi, point)


def load(split=None):
    """Within-wallet equal time-halves split (leak-free, R3 method): each wallet's events are
    ordered by placement day and split at the wallet's own median into early/late halves. This
    maximizes power on time-concentrated data where a global calendar split is nearly empty."""
    rows = mc.wallet_event_surplus()          # all resolved BUY fills, event rows
    micro = mc.microstructure()               # lifetime churner screen
    days = sorted({r["day"] for r in rows})
    if not days:
        return None
    # group rows by wallet -> ev -> rows, capturing each event's earliest day
    by_w = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_w[r["wallet"]][r["ev"]].append(r)
    per = {}   # wallet -> {"E": {ev:[rows]}, "L": {ev:[rows]}}
    for w, evmap in by_w.items():
        ev_day = {ev: min(x["day"] for x in rr) for ev, rr in evmap.items()}
        evs = sorted(evmap.keys(), key=lambda e: ev_day[e])
        mid = len(evs) // 2
        early = {e: evmap[e] for e in evs[:mid]}
        late = {e: evmap[e] for e in evs[mid:]}
        per[w] = {"E": early, "L": late}
    return per, micro, "within-wallet-median", days


def wallet_window_stats(evmap):
    """Given ev->list-of-rows, return (n_events, mean_surplus, mean_a, win_frac) as event-means."""
    if not evmap:
        return None
    s_list, a_list, w_list = [], [], []
    for ev, rr in evmap.items():
        s_list.append(sum(x["surplus"] for x in rr) / len(rr))
        a_list.append(sum(x["a"] for x in rr) / len(rr))
        w_list.append(sum(1 for x in rr if x["a"] > 0) / len(rr))  # a>0 iff won (BUY: won-price>0)
    n = len(s_list)
    return n, sum(s_list) / n, sum(a_list) / n, sum(w_list) / n


def run(split=None):
    loaded = load(split)
    if loaded is None:
        return {"error": "no data"}
    per, micro, split, days = loaded
    # build paired early/late per wallet, NON-MM only
    surplus_e, surplus_l, roi_e, roi_l, succ_e = [], [], [], [], []
    wallets = []
    for w, wins in per.items():
        m = micro.get(w)
        if m is None or mc.is_churner(m):
            continue
        se = wallet_window_stats(wins["E"])
        sl = wallet_window_stats(wins["L"])
        if not se or not sl:
            continue
        if se[0] < MIN_EV or sl[0] < MIN_EV:
            continue
        wallets.append(w)
        surplus_e.append(se[1]); surplus_l.append(sl[1])
        roi_e.append(se[2]); roi_l.append(sl[2])
        succ_e.append(se[3])
    n = len(wallets)
    out = {"snapshot_days": [days[0], days[-1]], "split_day": str(split),
           "n_wallets_both_windows": n, "min_ev_per_window": MIN_EV, "cohort": "non-MM directional"}
    if n < 5:
        out["verdict"] = "INDETERMINATE-BY-POWER (too few wallets with both windows)"
        return out

    # (a) blind-surplus persistence
    lo, hi, pt = boot_ci(surplus_e, surplus_l, spearman)
    out["a_blind_surplus_persistence"] = {"spearman": pt, "ci95": [lo, hi],
        "null": (lo <= 0), "interp": "early surplus rank vs late surplus"}
    # (b) ROI persistence
    lo, hi, pt = boot_ci(roi_e, roi_l, spearman)
    out["b_roi_persistence"] = {"spearman": pt, "ci95": [lo, hi], "null": (lo <= 0)}
    # (c) success-rate selection: top tercile by early success -> late blind surplus vs fleet
    order = sorted(range(n), key=lambda i: succ_e[i], reverse=True)
    k = max(1, n // 3)
    top = order[:k]
    fleet_late = sum(surplus_l) / n
    top_late = sum(surplus_l[i] for i in top) / k
    # bootstrap CI on (top_late - fleet_late) edge-retained
    def edge_ret(idxs, _):
        tl = sum(surplus_l[i] for i in idxs if i in set(top)) / max(1, sum(1 for i in idxs if i in set(top)))
        fl = sum(surplus_l[i] for i in idxs) / len(idxs)
        return tl - fl
    idx = list(range(n))
    lo, hi, pt = boot_ci(idx, idx, edge_ret)
    out["c_success_rate_selection"] = {"top_tercile_late_surplus": top_late,
        "fleet_late_surplus": fleet_late, "edge_retained": top_late - fleet_late,
        "edge_retained_ci95": [lo, hi], "null": (lo <= 0), "k_top": k}
    nulls = [out["a_blind_surplus_persistence"]["null"], out["b_roi_persistence"]["null"],
             out["c_success_rate_selection"]["null"]]
    out["verdict"] = ("WALL CONFIRMED — all past-PnL signals NULL (CI includes/below 0)"
                      if all(nulls) else "UNEXPECTED — a past-PnL signal shows LB>0; investigate before trusting")
    return out


def selftest():
    # synthetic: persistence spearman on perfectly correlated data -> ~1
    xs = [float(i) for i in range(20)]
    assert abs(spearman(xs, xs) - 1.0) < 1e-9
    assert abs(spearman(xs, [-y for y in xs]) + 1.0) < 1e-9
    lo, hi, pt = boot_ci(xs, xs, spearman, n_boot=500)
    assert pt > 0.99 and lo > 0.5
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--split", default=None, help="YYYY-MM-DD placement-day split")
    args = ap.parse_args()
    if args.selftest:
        selftest(); sys.exit(0)
    res = run(args.split)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps(res, indent=2, default=str))
