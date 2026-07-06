#!/usr/bin/env python3
"""
skill_common — shared read-only helpers for the "Identify the Genuinely Skilled" WS-2/3/4 tests.

Everything here is event-clustered, leak-free (placement-day time axis), and computed on the
NON-MM (directional) cohort via the vindicated churner screen. It reuses mm_common's DB access
and surplus algebra so these tests score the SAME quantities as the live system.

READ-ONLY. No DB writes, no order placement.
"""
import math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(os.path.dirname(HERE)) + "/scripts"
sys.path.insert(0, SCRIPTS)
import mm_common as mc   # noqa: E402


def load_events(min_ev_half=10):
    """Return (wallets, micro) where wallets = { w: {"E":{ev:rows}, "L":{ev:rows}, "all":{ev:rows}} }
    for NON-MM wallets with >= min_ev_half events in BOTH within-wallet time-halves.
    Split is within-wallet median of event earliest-day (leak-free, maximizes power)."""
    rows = mc.wallet_event_surplus()
    micro = mc.microstructure()
    by_w = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_w[r["wallet"]][r["ev"]].append(r)
    out = {}
    for w, evmap in by_w.items():
        m = micro.get(w)
        if m is None or mc.is_churner(m):
            continue
        ev_day = {ev: min(x["day"] for x in rr) for ev, rr in evmap.items()}
        evs = sorted(evmap.keys(), key=lambda e: ev_day[e])
        mid = len(evs) // 2
        early = {e: evmap[e] for e in evs[:mid]}
        late = {e: evmap[e] for e in evs[mid:]}
        if len(early) < min_ev_half or len(late) < min_ev_half:
            continue
        out[w] = {"E": early, "L": late, "all": evmap, "n_early": len(early), "n_late": len(late)}
    return out, micro


def ev_means(evmap):
    """event-clustered means over ev->rows: (n_events, mean_surplus, mean_a, win_frac, mean_price)."""
    s, a, wf, pr = [], [], [], []
    for ev, rr in evmap.items():
        s.append(sum(x["surplus"] for x in rr) / len(rr))
        a.append(sum(x["a"] for x in rr) / len(rr))
        wf.append(sum(1 for x in rr if x["a"] > 0) / len(rr))
        # price = won - a  (a = won - price)  -> price = won - a; use per-row and average
        pr.append(sum((1.0 if x["a"] > 0 else 0.0) - x["a"] for x in rr) / len(rr))
    n = len(s)
    return n, sum(s) / n, sum(a) / n, sum(wf) / n, sum(pr) / n


# ---- stats ----
def rank(xs):
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
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    sxx = sum((rx[i] - mx) ** 2 for i in range(n))
    syy = sum((ry[i] - my) ** 2 for i in range(n))
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


class LCG:
    """Deterministic RNG (Date/random unavailable in some contexts; reproducible everywhere)."""
    def __init__(self, seed=0x2545F4914F6CDD1D):
        self.s = seed & 0xFFFFFFFFFFFFFFFF
    def nxt(self):
        self.s = (6364136223846793005 * self.s + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self.s
    def idx(self, n):
        return (self.nxt() >> 17) % n


def boot_ci(vals, stat, n_boot=2000, seed=0x2545F4914F6CDD1D):
    """Cluster bootstrap over a list of items; `stat(resampled_list)`; 95% CI + point."""
    n = len(vals)
    point = stat(vals)
    if n < 5:
        return (float("nan"), float("nan"), point)
    rng = LCG(seed)
    reps = []
    for _ in range(n_boot):
        bs = [vals[rng.idx(n)] for _ in range(n)]
        v = stat(bs)
        if v == v:
            reps.append(v)
    reps.sort()
    return (reps[int(0.025 * len(reps))], reps[int(0.975 * len(reps))], point)


def mean_lb(xs, z=1.6449):
    """one-sided lower bound (z*se) on the mean of xs."""
    n = len(xs)
    if n < 2:
        return float("nan")
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m - z * math.sqrt(v / n)
