#!/usr/bin/env python3
"""
PER-NICHE TRADER ROSTERS — who are the real top 50-100 of THIS space?

Ranking traders by past surplus and taking the top-50 is EXACTLY the procedure this
project has already refuted five separate ways (past-PnL ranking rho ~ -0.05; per-cell
specialisation p=0.79 against a permutation null). Growing the candidate pool from 3k to
~200k wallets makes a naive top-50 MORE contaminated, not less: with more candidates, the
extreme order statistics under pure noise get more extreme. The prior naive scan crowned a
"+0.69 surplus/fill specialist" that had traded TWO markets.

So the harvest is a POWER lever, not a signal. This script is the gate that decides whether
any of it is real. It is built to return ZERO and say so.

Metric (reusing the repo's canonical surplus math, specialist_mining.py):
    advantage a = won - price                     (BUY fills, resolved outcomes)
    blind cell baseline be = mean(a) over ALL fills in (niche x price-band)
                             -- computed on the FULL HARVESTED POPULATION, which is what
                                "blind" actually means in a niche (not our whale pool)
    surplus  s = a - be
    copyable surplus = s - tau                    (tau = follower tax, >= 1.3c floor)
Clustered at the MARKET, which is the inference unit. Never the fill.

Gates (pre-registered in NICHE-ROSTERS-PLAN.md before any result was seen):
  K5  N-floor: >= 20 distinct COMPLETE-tape resolved markets in the niche.
  K4  Copyability: edge must survive at OUR price net of the follower tax; market-makers
      / spread-capturers excluded via the maker/taker label (uncopyable profit).
  K3  Permutation null: shuffle wallet labels within (niche x band), rerun the WHOLE
      pipeline, count certified. Observed must beat the null's p95.
  K2  PERSISTENCE (make-or-break): rank in window A, measure the SAME wallets in disjoint
      later window B. No out-of-sample edge => the roster is noise => NULL for that niche.
  BH-FDR q=0.10 across the wallet x niche family.

TRUNCATION: markets whose tape hit the API's 4000-row ceiling are EXCLUDED from scoring.
The tape is newest-first, so truncation drops the EARLIEST entrants -- the informed early
money -- and would bias every number. They still count for population discovery. Coverage
is reported, never silently dropped.

Usage:
  ./roster.py --self-test        # K0 battery on synthetic fixtures (no DB)
  ./roster.py                    # score every harvested niche
  ./roster.py --niche weather
"""
import argparse
import csv
import io
import json
import math
import os
import random
import statistics
import subprocess
import sys
from collections import defaultdict

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# ---- pre-registered constants (fixed BEFORE looking at any result) ----
N_FLOOR = 20          # K5: distinct complete-tape resolved markets per wallet per niche
N_FLOOR_SPLIT = 8     # K2: min markets in EACH of window A and B to be persistence-testable
TAX_FLOOR = 0.013     # measured follower tax floor (1.3c) -- winners had already moved
MARGIN = 0.03         # capture cost (slippage 1% + fee 2%), mirrors promotion.rs
ALPHA = 0.05
FDR_Q = 0.10
N_PERM = 1000
MAKER_MM = 0.80       # maker_frac at/above this = liquidity provider (uncopyable)
TWOSIDE_MM = 0.50     # traded both outcomes in >= half their markets = round-trip churn
SEED = 20260714
ROSTER_SIZE = 100     # the "top 50-100" the roster reports (pre-gate ranking)


def psql(sql):
    out = subprocess.run(PG, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


# ---------------------------------------------------------------------------
# Data: per (wallet, niche, market) surplus over the population-blind cell baseline.
# Only BUY fills on COMPLETE-tape markets with a known resolution.
# ---------------------------------------------------------------------------
FETCH_SQL = r"""
WITH res AS (          -- resolution comes from OUR tape; no extra API calls needed
  SELECT condition_id, outcome_index, BOOL_OR(outcome_won) AS won
  FROM trader_fills
  WHERE resolved AND outcome_won IS NOT NULL
  GROUP BY 1,2
),
ok AS (                -- complete-tape markets only (truncation biases against early money)
  SELECT condition_id, niche FROM harvest_markets WHERE NOT truncated
),
base AS (
  SELECT h.wallet, h.niche, h.condition_id,
         -- 20 FINE bands (0.05 wide), not the legacy 5. Advantage (won - price) varies
         -- strongly WITHIN a coarse band, so a wallet that habitually buys at the cheap
         -- end of a wide band looks "skilled" for a purely mechanical reason. Finer bands
         -- control that confound WITHOUT adding hypotheses (still one test per wallet).
         width_bucket(h.price, 0.0, 1.0, 20)       AS band,
         (r.won::int)::float8 - h.price            AS a,
         h.price, h.size_usd, h.is_maker, h.ts, h.outcome_index
  FROM harvest_fills h
  JOIN ok  USING (condition_id)
  JOIN res r ON r.condition_id = h.condition_id AND r.outcome_index = h.outcome_index
  WHERE h.side = 'BUY'
),
blind AS (             -- the blind baseline of the FULL POPULATION, per niche x band
  SELECT niche, band, AVG(a) AS be FROM base GROUP BY 1,2
)
SELECT b.wallet, b.niche, b.condition_id,
       AVG(b.a - bl.be)                              AS surplus,
       AVG(b.a)                                      AS raw_adv,
       AVG(b.price)                                  AS price,
       SUM(b.size_usd)                               AS usd,
       COUNT(*)                                      AS n_fills,
       AVG((b.is_maker)::int::float8)                AS maker_frac,
       COUNT(DISTINCT b.outcome_index)               AS n_sides,
       EXTRACT(EPOCH FROM MAX(b.ts))                 AS ts
FROM base b JOIN blind bl USING (niche, band)
GROUP BY 1,2,3;
"""


def fetch():
    rows = psql(FETCH_SQL)
    cells = defaultdict(list)     # (wallet, niche) -> [market records]
    for r in rows:
        try:
            cells[(r["wallet"], r["niche"])].append({
                "mkt": r["condition_id"],
                "surplus": float(r["surplus"]),
                "raw_adv": float(r["raw_adv"]),
                "price": float(r["price"]),
                "usd": float(r["usd"]),
                "n_fills": int(r["n_fills"]),
                "maker_frac": float(r["maker_frac"]) if r["maker_frac"] not in ("", None) else 0.0,
                "n_sides": int(r["n_sides"]),
                "ts": float(r["ts"]) if r["ts"] else 0.0,
            })
        except (ValueError, TypeError):
            continue
    return cells


# ---------------------------------------------------------------------------
# Mechanism: uncopyable profit. A maker earns the spread we would have to PAY.
# ---------------------------------------------------------------------------
def is_mm(mkts):
    maker = statistics.fmean([m["maker_frac"] for m in mkts])
    two = sum(1 for m in mkts if m["n_sides"] >= 2) / len(mkts)
    if maker >= MAKER_MM:
        return True, f"maker_frac={maker:.2f}"
    if two >= TWOSIDE_MM and maker >= 0.5:
        return True, f"two_sided={two:.2f} maker={maker:.2f}"
    return False, None


def stats(mkts, tax):
    """Market-clustered mean + SE of COPYABLE surplus. The market is the unit."""
    s = [m["surplus"] - tax for m in mkts]
    n = len(s)
    mean = statistics.fmean(s)
    sd = statistics.stdev(s) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else float("inf")
    return mean, se, n


def lower_bound(mean, se, n_comp):
    """Bonferroni-split lower bound, mirroring promotion.rs::surplus_bounds."""
    if se in (0.0, float("inf")):
        return -float("inf")
    z = 1.96 + math.log(max(n_comp, 1)) ** 0.5 * 0.5   # widen for multiplicity
    return mean - z * se


def bh_fdr(pvals, q=FDR_Q):
    """Benjamini-Hochberg. Returns the set of indices that survive."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    keep = set()
    for rank, i in enumerate(idx, 1):
        if pvals[i] <= q * rank / m:
            keep = set(idx[:rank])
    return keep


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def certify(cells, niche, tax, floor=N_FLOOR, verbose=False):
    """The full gate. Returns (certified, eligible, excluded_mm)."""
    elig, mm_excl = [], 0
    for (w, nz), mkts in cells.items():
        if nz != niche or len(mkts) < floor:
            continue
        bad, _ = is_mm(mkts)
        if bad:
            mm_excl += 1
            continue
        elig.append((w, mkts))
    if not elig:
        return [], [], mm_excl
    n_comp = len(elig)
    recs = []
    for w, mkts in elig:
        mean, se, n = stats(mkts, tax)
        lb = lower_bound(mean, se, n_comp)
        z = mean / se if se > 0 else 0.0
        # SKILL is relative to the cell baseline; BANKABILITY is absolute. A wallet can
        # beat a negative baseline (the vig) and still lose money, so we carry both and
        # never let the relative number stand in for the money number.
        raw = statistics.fmean([m.get("raw_adv", m["surplus"]) - tax for m in mkts])
        recs.append({"wallet": w, "mean": mean, "se": se, "n": n, "lb": lb,
                     "p": norm_sf(z), "usd": sum(m["usd"] for m in mkts),
                     "raw_adv": raw,
                     "maker": statistics.fmean([m["maker_frac"] for m in mkts]),
                     "mkts": mkts})
    keep = bh_fdr([r["p"] for r in recs])
    cert = [r for i, r in enumerate(recs) if i in keep and r["lb"] > 0]
    return cert, recs, mm_excl


# ---------------------------------------------------------------------------
# K3 -- permutation null. How many "specialists" does pure noise manufacture here?
# Shuffle wallet labels across the niche's (market, surplus) records, preserving each
# wallet's market COUNT and the market/price structure. Rerun the WHOLE pipeline.
# ---------------------------------------------------------------------------
def perm_null(cells, niche, tax, floor, n_perm=N_PERM, seed=SEED):
    """Vectorised. Reproduces certify()'s arithmetic EXACTLY (lower_bound + BH-FDR +
    lb>0), just without the Python object churn -- the pure loop was ~11 min for ONE
    niche, which does not survive a full sweep."""
    import numpy as np
    # Eligible, non-MM wallets only -- the null must describe the population the gate
    # actually judges. Records keep their PRICE BAND so the null can be band-stratified:
    # each record is replaced by a random surplus drawn from ITS OWN band. That preserves
    # every wallet's N and its band composition exactly, and destroys only the wallet
    # identity -- which is the thing whose reality we are testing. An unstratified draw
    # would let band-mix differences masquerade as skill (or hide it).
    elig = [mk for (w, nz), mk in cells.items()
            if nz == niche and len(mk) >= floor and not is_mm(mk)[0]]
    if not elig:
        return [], 0
    sizes = np.array([len(mk) for mk in elig], dtype=np.int64)
    bands = np.array([min(int(m["price"] * 20), 19) for mk in elig for m in mk],
                     dtype=np.int64)
    pool_all = np.array([m["surplus"] for mk in elig for m in mk], dtype=np.float64)
    # per-band pools, and the slot indices each band must fill
    band_pool, band_slots = {}, {}
    for b in np.unique(bands):
        band_pool[int(b)] = pool_all[bands == b]
        band_slots[int(b)] = np.nonzero(bands == b)[0]
    n_comp = int(sizes.size)
    z_mult = 1.96 + math.log(max(n_comp, 1)) ** 0.5 * 0.5
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    total = int(sizes.sum())
    rng = np.random.default_rng(seed)
    q_ladder = FDR_Q * np.arange(1, n_comp + 1) / n_comp
    counts = []
    for _ in range(n_perm):
        draw = np.empty(total, dtype=np.float64)
        for b, slots in band_slots.items():
            p = band_pool[b]
            draw[slots] = p[rng.integers(0, p.size, slots.size)]
        draw -= tax
        s1 = np.add.reduceat(draw, starts)
        s2 = np.add.reduceat(draw * draw, starts)
        mean = s1 / sizes
        var = np.maximum((s2 - sizes * mean ** 2) / np.maximum(sizes - 1, 1), 0.0)
        se = np.sqrt(var / sizes)
        with np.errstate(divide="ignore", invalid="ignore"):
            lb = mean - z_mult * se
            zs = np.where(se > 0, mean / se, 0.0)
        p = 0.5 * erfc_vec(zs / math.sqrt(2))
        order = np.argsort(p)
        surv = p[order] <= q_ladder
        k = np.nonzero(surv)[0]
        if k.size == 0:
            counts.append(0)
            continue
        keep = order[:k[-1] + 1]
        counts.append(int(np.count_nonzero(lb[keep] > 0)))
    counts.sort()
    p95 = counts[int(0.95 * len(counts))] if counts else 0
    return counts, p95


def erfc_vec(x):
    import numpy as np
    from scipy.special import erfc as _e          # noqa
    return _e(np.asarray(x))


# ---------------------------------------------------------------------------
# K2 -- PERSISTENCE. The make-or-break. Rank in A, measure in B.
# ---------------------------------------------------------------------------
def persistence(cells, niche, tax, floor=N_FLOOR_SPLIT, top_n=50):
    """Rank in window A, measure the SAME wallets in disjoint later window B.

    The split is assigned at the MARKET level, globally -- not per wallet. If the same
    market could fall in A for one wallet and B for another, the two windows would share
    resolution OUTCOMES (one coin-flip informing both sides of the split), which inflates
    apparent persistence. Disjoint market sets make that leak impossible.
    """
    mkt_ts = {}
    for (w, nz), mk in cells.items():
        if nz != niche:
            continue
        for m in mk:
            mkt_ts[m["mkt"]] = max(mkt_ts.get(m["mkt"], 0.0), m["ts"])
    if not mkt_ts:
        return None
    order = sorted(mkt_ts.values())
    cut = order[len(order) // 2]
    win_A = {k for k, v in mkt_ts.items() if v <= cut}   # disjoint by construction
    ab = {}
    for (w, nz), mk in cells.items():
        if nz != niche:
            continue
        if is_mm(mk)[0]:
            continue
        A = [m for m in mk if m["mkt"] in win_A]
        B = [m for m in mk if m["mkt"] not in win_A]
        if len(A) >= floor and len(B) >= floor:
            ab[w] = (A, B)
    if len(ab) < 10:
        return {"n_testable": len(ab), "underpowered": True, "cut": cut}
    ranked = sorted(ab.items(), key=lambda kv: statistics.fmean(
        [m["surplus"] for m in kv[1][0]]), reverse=True)
    top = ranked[:min(top_n, max(1, len(ranked) // 4))]

    # The window-B observations are (wallet, market) records, and MANY WALLETS SHARE THE
    # SAME MARKET -- one market's resolution moves all of them together. Treating them as
    # independent understates the SE badly (effective N is the number of distinct MARKETS,
    # not records) and would make a null look like an edge. So the CI is a block bootstrap
    # CLUSTERED ON THE MARKET, which is the real unit of independent information.
    b_rec = [(m["mkt"], m["surplus"] - tax) for _, (A, B) in top for m in B]
    mean = statistics.fmean([v for _, v in b_rec]) if b_rec else 0.0
    lo, hi, n_clu = cluster_boot(b_rec)
    rest = [m["surplus"] - tax for w, (A, B) in ranked[len(top):] for m in B]
    rest_mean = statistics.fmean(rest) if rest else 0.0
    # rank correlation A vs B (does within-niche ranking transfer at all?)
    xs = [statistics.fmean([m["surplus"] for m in A]) for _, (A, B) in ranked]
    ys = [statistics.fmean([m["surplus"] for m in B]) for _, (A, B) in ranked]
    rho = spearman(xs, ys)
    return {"n_testable": len(ab), "underpowered": False, "cut": cut,
            "top_n": len(top), "b_mean": mean, "b_lb": lo, "b_hi": hi,
            "b_n_obs": len(b_rec), "b_n_markets": n_clu,
            "rest_mean": rest_mean, "rho": rho}


def cluster_boot(recs, n_boot=2000, seed=SEED):
    """Block bootstrap clustered on the MARKET. recs = [(market, value)].
    Resamples whole markets, so shared-outcome correlation is respected."""
    import numpy as np
    if not recs:
        return 0.0, 0.0, 0
    by = defaultdict(list)
    for m, v in recs:
        by[m].append(v)
    keys = list(by)
    blocks = [np.array(by[k], dtype=np.float64) for k in keys]
    sums = np.array([b.sum() for b in blocks])
    lens = np.array([b.size for b in blocks])
    rng = np.random.default_rng(seed)
    k = len(keys)
    idx = rng.integers(0, k, (n_boot, k))
    means = sums[idx].sum(axis=1) / np.maximum(lens[idx].sum(axis=1), 1)
    return (float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)), k)


def spearman(x, y):
    n = len(x)
    if n < 3:
        return float("nan")
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(o):
            r[i] = pos
        return r
    rx, ry = rank(x), rank(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


# ---------------------------------------------------------------------------
# K0 -- self-test on synthetic fixtures. The gate must catch what we know is fake.
# ---------------------------------------------------------------------------
def self_test():
    rng = random.Random(7)
    print("K0 gate battery\n" + "=" * 64)
    ok = True

    def mk(n, mean, sd, maker=0.0, sides=1, seed=0):
        r = random.Random(seed)
        out = []
        for i in range(n):
            s = r.gauss(mean, sd)
            out.append({"mkt": f"m{i}", "surplus": s, "raw_adv": s, "price": 0.7,
                        "usd": 100, "n_fills": 3, "maker_frac": maker,
                        "n_sides": sides, "ts": 1000 + i})
        return out

    # 1. a coin-flip fleet must certify ~nobody (this is the winner's-curse trap)
    cells = {(f"noise{i}", "t"): mk(30, 0.0, 0.15, seed=i) for i in range(300)}
    c, recs, _ = certify(cells, "t", TAX_FLOOR)
    p1 = len(c) == 0
    print(f"  noise fleet (300 wallets, zero true edge): certified={len(c)}  "
          f"{'PASS' if p1 else 'FAIL -- gate leaks winners-curse'}")
    ok &= p1

    # 2. a genuinely skilled, copyable wallet must survive
    cells[("real", "t")] = mk(40, 0.10, 0.12, seed=99)
    c, _, _ = certify(cells, "t", TAX_FLOOR)
    p2 = any(r["wallet"] == "real" for r in c)
    print(f"  injected TRUE +10% specialist: {'certified' if p2 else 'MISSED'}  "
          f"{'PASS' if p2 else 'FAIL -- gate has no power'}")
    ok &= p2

    # 3. a market-maker must be excluded even with huge raw edge
    cells[("mm", "t")] = mk(40, 0.30, 0.05, maker=0.95, sides=2, seed=5)
    c, _, mmx = certify(cells, "t", TAX_FLOOR)
    p3 = not any(r["wallet"] == "mm" for r in c) and mmx >= 1
    print(f"  market-maker (+30% raw, maker_frac .95): {'excluded' if p3 else 'LEAKED'}  "
          f"{'PASS' if p3 else 'FAIL -- uncopyable profit certified'}")
    ok &= p3

    # 4. small-N artifact must be structurally impossible
    cells[("tiny", "t")] = mk(2, 0.69, 0.01, seed=3)
    c, _, _ = certify(cells, "t", TAX_FLOOR)
    p4 = not any(r["wallet"] == "tiny" for r in c)
    print(f"  small-N artifact (+0.69 on 2 markets): {'blocked by N-floor' if p4 else 'CERTIFIED'}  "
          f"{'PASS' if p4 else 'FAIL'}")
    ok &= p4

    # 5. an edge that exists at THEIR price but dies at OURS must not certify
    cells2 = {(f"n{i}", "t"): mk(30, 0.0, 0.15, seed=100 + i) for i in range(100)}
    cells2[("thin", "t")] = mk(40, 0.010, 0.05, seed=11)   # +1.0% raw < 1.3c tax
    c, _, _ = certify(cells2, "t", TAX_FLOOR)
    p5 = not any(r["wallet"] == "thin" for r in c)
    print(f"  edge +1.0% < 1.3c follower tax: {'killed by copyability' if p5 else 'CERTIFIED'}  "
          f"{'PASS' if p5 else 'FAIL'}")
    ok &= p5

    # 6. persistence must detect a PURE-NOISE roster as non-persistent
    noise = {(f"z{i}", "t"): mk(20, 0.0, 0.15, seed=500 + i) for i in range(120)}
    pr = persistence(noise, "t", TAX_FLOOR)
    p6 = pr and not pr.get("underpowered") and abs(pr["rho"]) < 0.25 and pr["b_lb"] <= 0
    print(f"  persistence on pure noise: rho={pr['rho']:+.3f} B_lb={pr['b_lb']:+.4f}  "
          f"{'PASS (correctly non-persistent)' if p6 else 'FAIL'}")
    ok &= bool(p6)

    # 7. persistence must DETECT a real persistent edge (power check)
    real = {(f"z{i}", "t"): mk(20, 0.0, 0.15, seed=900 + i) for i in range(100)}
    for i in range(20):
        real[(f"good{i}", "t")] = mk(20, 0.12, 0.12, seed=1500 + i)
    pr2 = persistence(real, "t", TAX_FLOOR)
    p7 = pr2 and not pr2.get("underpowered") and pr2["rho"] > 0.2 and pr2["b_lb"] > 0
    print(f"  persistence on TRUE edge: rho={pr2['rho']:+.3f} B_lb={pr2['b_lb']:+.4f}  "
          f"{'PASS (detects real edge)' if p7 else 'FAIL -- test is blind'}")
    ok &= bool(p7)

    print("=" * 64)
    print("K0", "PASS -- gate rejects noise, MMs, small-N and uncopyable edge; "
                "detects real edge" if ok else "FAIL -- STOP")
    return 0 if ok else 1


def tracked_wallets():
    """The leaderboard-sourced pool -- every wallet we have EVER known."""
    return {r["wallet"].lower() for r in psql("SELECT DISTINCT wallet FROM trader_fills")}


def hidden_vs_tracked(cells, niche, tax, tracked, floor=N_FLOOR):
    """THE decision-relevant comparison: in this niche, are the wallets the leaderboard
    structurally could not show us actually BETTER than the ones it did?

    If hidden ~= tracked, the whole market-side reframe is wrong and widening the net buys
    nothing. Reported per niche, on the same gate-eligible footing (>= N_FLOOR markets,
    non-MM), so it is not a comparison of apples to whales."""
    grp = {"tracked": [], "hidden": []}
    for (w, nz), mk in cells.items():
        if nz != niche or len(mk) < floor or is_mm(mk)[0]:
            continue
        mean, se, n = stats(mk, tax)
        grp["tracked" if w.lower() in tracked else "hidden"].append(mean)
    out = {}
    for k, v in grp.items():
        if not v:
            out[k] = None
            continue
        v.sort()
        out[k] = {"n": len(v), "median": v[len(v) // 2],
                  "pct_positive": sum(1 for x in v if x > 0) / len(v),
                  "p90": v[int(0.9 * len(v))] if len(v) > 1 else v[0]}
    return out


def measure_tax(niche):
    """Follower tax: how far the price has already moved by the time we could act.
    Conservative floor at 1.3c (the truth-audit measurement)."""
    return TAX_FLOOR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--niche", default=None)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", default="reports/niche")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    cells = fetch()
    tracked = tracked_wallets()
    niches = sorted({nz for (_, nz) in cells}) if not a.niche else [a.niche]
    os.makedirs(a.out, exist_ok=True)
    summary = []

    for nz in niches:
        pop = {w for (w, x) in cells if x == nz}
        tax = measure_tax(nz)
        cert, recs, mm_excl = certify(cells, nz, tax)
        counts, p95 = perm_null(cells, nz, tax, N_FLOOR)
        null_mean = statistics.fmean(counts) if counts else 0.0
        pers = persistence(cells, nz, tax)
        hvt = hidden_vs_tracked(cells, nz, tax, tracked)

        # the roster the user asked for: top-100 by copyable surplus lower bound
        roster = sorted(recs, key=lambda r: r["lb"], reverse=True)[:ROSTER_SIZE]

        beats_null = len(cert) > p95
        row = {"niche": nz, "population": len(pop), "eligible": len(recs),
               "mm_excluded": mm_excl, "certified": len(cert),
               "null_mean": null_mean, "null_p95": p95, "beats_null": beats_null,
               "persistence": pers, "tax": tax, "hidden_vs_tracked": hvt,
               "roster": [{"wallet": r["wallet"], "n_markets": r["n"],
                           "copyable_surplus": r["mean"], "lb": r["lb"],
                           "abs_advantage_net_tax": r["raw_adv"],
                           "maker_frac": r["maker"], "usd": r["usd"]} for r in roster]}
        summary.append(row)

        print(f"\n{'='*70}\nNICHE: {nz}")
        print(f"  population (harvested wallets) : {len(pop):,}")
        print(f"  eligible (>= {N_FLOOR} mkts, non-MM): {len(recs):,}   "
              f"(MM excluded: {mm_excl:,})")
        print(f"  CERTIFIED (gate + FDR)         : {len(cert)}")
        print(f"  permutation null               : mean={null_mean:.1f} p95={p95} "
              f"=> {'BEATS NULL' if beats_null else 'DOES NOT BEAT NULL (noise)'}")
        if pers and not pers.get("underpowered"):
            print(f"  K2 PERSISTENCE  rank rho(A,B)  : {pers['rho']:+.3f}")
            print(f"     top-{pers['top_n']} of A, measured in B : {pers['b_mean']:+.4f} "
                  f"[95% CI {pers['b_lb']:+.4f}, {pers['b_hi']:+.4f}] "
                  f"market-clustered on {pers['b_n_markets']} markets")
            print(f"     rest-of-field in B          : {pers['rest_mean']:+.4f}")
            print(f"     => {'PERSISTS' if pers['b_lb'] > 0 else 'DOES NOT PERSIST -- roster is noise'}")
        elif pers:
            print(f"  K2 PERSISTENCE: UNDERPOWERED (only {pers['n_testable']} wallets "
                  f"with >= {N_FLOOR_SPLIT} markets in BOTH windows)")
        t, h = hvt.get("tracked"), hvt.get("hidden")
        if t and h:
            print(f"  hidden vs tracked (gate-eligible, same footing):")
            print(f"     leaderboard-tracked  n={t['n']:<5d} median={t['median']:+.4f} "
                  f"pos={t['pct_positive']:.0%} p90={t['p90']:+.4f}")
            print(f"     HIDDEN (harvest-only) n={h['n']:<5d} median={h['median']:+.4f} "
                  f"pos={h['pct_positive']:.0%} p90={h['p90']:+.4f}")

    with open(os.path.join(a.out, "rosters.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nwrote {a.out}/rosters.json")


if __name__ == "__main__":
    main()
