#!/usr/bin/env python3
"""
THE DRAWDOWN THE MEAN HID.  (favourites win small & often, lose big & rarely)

The collapse model's MEAN edge is established (+4.14% ROI, EV>0.01, tradeable sports, event-clustered,
p=0.000). The mean is not the risk. A ≥80¢ favourite pays ~+13% when it holds and loses ~100% of the
at-risk stake when it collapses — a left-skewed payoff whose *tail* decides whether a bankroll
survives. "Certified mean, uncharacterised drawdown" is exactly the gap between a candidate and money.

This characterises the tail three ways, all with the EVENT (game) as the unit of risk
(project-polymarket-correlated-risk: bets within a game resolve together, so a game is ONE levered
draw, never N independent ones):

  K1  KELLY FRACTION from the realised per-event return distribution. Report full-Kelly and the
      1/8-Kelly cap (project-polymarket-risk-engine). Growth-optimal sizing is bounded by the WORST
      loss, not the mean.

  K2  RISK OF RUIN / MAX DRAWDOWN by BLOCK BOOTSTRAP. Resample events WITH REPLACEMENT preserving the
      per-event bundle (all a game's bets stay together), build the equity curve at several fixed
      fractions, and read the distribution of max drawdown + P(bankroll halves) + P(ruin).

  K3  SKEW / TAIL diagnostics: win rate, mean win, mean loss, worst single event, and how much of the
      total P&L rides on the best few events (concentration — a fragility tell this repo has been
      burned by).

  ./drawdown_kelly.py --self-test
  ./drawdown_kelly.py
"""
import argparse
import csv
import io
import pickle
import re
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
CACHE = "reports/niche/.collapse_cache.pkl"
SEED = 20260714
THETA = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05, "ufc": .05,
         "esports": .05, "crypto": .07, "weather": .05, "other": .05}
DATE_RE = re.compile(r"^(.*?\d{4}-\d{2}-\d{2})")
TRADEABLE = ("soccer", "tennis", "esports", "ufc")


def fee(p, n):
    return THETA.get(n, .05) * p * (1 - p)


def psql(s):
    o = subprocess.run(PG, input="SET max_parallel_workers_per_gather=0; " + s,
                       capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:800])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def qlit(xs):
    return ",".join("'" + x + "'" for x in xs)


DAY_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def event_key(slug, cid):
    if not slug:
        return cid
    m = DATE_RE.match(slug)
    return m.group(1) if m else cid


def day_of(event):
    m = DAY_RE.search(event)
    return m.group(1) if m else event      # long-form events => their own "day" (conservative)


def event_returns(signals, by_day=False):
    """signals = [(event, won, p, niche)]. Each signal is a flat-CAPITAL bet (stake 1 unit of
    at-risk capital = the entry price). Return on that unit = (won - p - fee)/p. An EVENT's return
    is the MEAN across its bets (correlated bundle => averaged, not summed, so one game = one draw).
    by_day=True bundles at the DAY level instead — the more conservative unit, capturing same-slate
    cross-game correlation (an upset-heavy day where many favourites collapse together)."""
    by = defaultdict(list)
    for ev, won, p, n in signals:
        r = (won - p - fee(p, n)) / p          # return on capital-at-risk for this bet
        by[day_of(ev) if by_day else ev].append(r)
    return np.array([float(np.mean(v)) for v in by.values()], float)


def kelly_fraction(returns):
    """Growth-optimal fraction f maximising E[log(1 + f r)] over the empirical return dist.
    Solved by a grid + refine; clipped to [0, full]. r can be < -1? No: min return >= -1 (lose the
    stake). f in [0,1] keeps 1+f r > 0 as long as min r > -1 (favourite loss = -(p+fee)/p < -1 is
    possible when fee>0). Guard f so 1+f*min_r > 0."""
    r = returns
    rmin = r.min()
    fmax = 0.999 if rmin >= 0 else min(0.999, 0.999 / (-rmin))
    fs = np.linspace(0, fmax, 4000)
    g = np.array([np.mean(np.log1p(f * r)) for f in fs])
    return float(fs[int(np.argmax(g))]), float(g.max())


def max_drawdown(equity):
    peak = np.maximum.accumulate(equity)
    return float(np.max((peak - equity) / peak))


def simulate(returns, f, n_events, n_paths=4000, seed=SEED):
    """Block bootstrap: resample events with replacement, compound at fraction f. Returns
    (median final multiple, P(final<1), P(drawdown>0.5), P(ruin<0.2), median maxDD)."""
    rng = np.random.default_rng(seed)
    finals, dds, halved, ruined = [], [], 0, 0
    for _ in range(n_paths):
        seq = returns[rng.integers(0, len(returns), n_events)]
        eq = np.cumprod(1.0 + f * seq)
        eq = np.concatenate([[1.0], eq])
        finals.append(eq[-1])
        dd = max_drawdown(eq)
        dds.append(dd)
        if eq[-1] < 1.0:
            halved += 0
        if dd >= 0.5:
            halved += 1
        if eq.min() < 0.2:
            ruined += 1
    return (float(np.median(finals)), float(np.mean(np.array(finals) < 1.0)),
            halved / n_paths, ruined / n_paths, float(np.median(dds)))


def self_test():
    # a pure +5% edge every event: Kelly should want a LOT, ruin ~0
    r = np.array([0.05] * 200)
    f, g = kelly_fraction(r)
    assert f > 0.9 and g > 0
    # a symmetric coin flip +/-100%: Kelly ~ 0, ruin high if forced to bet
    r2 = np.array([1.0, -1.0] * 100)
    f2, _ = kelly_fraction(r2)
    assert f2 < 0.05, f"fair coin should want ~0 Kelly, got {f2}"
    # drawdown of a monotone-up curve is 0; of up-then-halve is 0.5
    assert max_drawdown(np.array([1, 2, 3.0])) == 0.0
    assert abs(max_drawdown(np.array([1.0, 2.0, 1.0])) - 0.5) < 1e-9
    # favourite payoff: win prob 0.9 at p=0.9 -> mean ~0, high left skew
    rng = np.random.default_rng(0)
    won = (rng.random(1000) < 0.90).astype(float)
    sig = [(f"e{i}", won[i], 0.90, "soccer") for i in range(1000)]
    er = event_returns(sig)
    assert er.min() < -0.9 and er.max() < 0.2, "favourite loss ~ -100%, win ~ +11%"
    # day-blocking collapses same-day events into one draw
    sig2 = [("mlb-a-b-2026-07-01-ml", 1.0, 0.9, "soccer"),
            ("mlb-a-b-2026-07-01-total", 0.0, 0.9, "soccer"),
            ("nba-c-d-2026-07-02-ml", 1.0, 0.9, "soccer")]
    assert len(event_returns(sig2)) == 3 and len(event_returns(sig2, by_day=True)) == 2, \
        "day-block must bundle same-date events"
    assert day_of("mlb-tex-cle-2026-07-01") == "2026-07-01"
    print("self-test OK  (Kelly bounded by worst loss; drawdown; favourite skew; day-block)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--ev", type=float, default=0.01)
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    from sklearn.ensemble import HistGradientBoostingClassifier

    rows = pickle.load(open(CACHE, "rb"))
    A = [r for r in rows if r["win"] == "A"]
    B = [r for r in rows if r["win"] == "B"]
    Xa = np.array([r["x"] for r in A]); ya = np.array([r["y"] for r in A])
    Xb = np.array([r["x"] for r in B])
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
                                         min_samples_leaf=80, l2_regularization=1.0,
                                         random_state=0).fit(Xa, ya)
    pw = clf.predict_proba(Xb)[:, 1]
    ev = np.array([pw[i] - B[i]["p"] - fee(B[i]["p"], B[i]["niche"]) for i in range(len(B))])

    cids = sorted({r["cid"] for r in B})
    slug = {}
    for i in range(0, len(cids), 400):
        for r in psql(f"SELECT condition_id,slug FROM harvest_markets "
                      f"WHERE condition_id IN ({qlit(cids[i:i+400])});"):
            slug[r["condition_id"]] = r["slug"]

    sig = [(event_key(slug.get(B[i]["cid"]), B[i]["cid"]), B[i]["y"], B[i]["p"], B[i]["niche"])
           for i in range(len(B)) if B[i]["niche"] in TRADEABLE and ev[i] > a.ev]
    er = event_returns(sig)
    dr = event_returns(sig, by_day=True)
    n_ev = len(er)
    n_day = len(dr)
    print(f"tradeable-subset, EV>{a.ev:+.2f}: {len(sig):,} signals across {n_ev:,} EVENTS "
          f"/ {n_day:,} DAYS\n")

    # -------------------------------------------------------------- K3 skew / tail
    wins = er[er > 0]; losses = er[er < 0]
    tot = er.sum()
    order = np.sort(er)[::-1]
    top5_share = order[:max(1, n_ev // 20)].sum() / tot if tot != 0 else float("nan")
    print("K3 -- PAYOFF SHAPE (per event, return on capital-at-risk)")
    print(f"  mean {er.mean():+.4f}   median {np.median(er):+.4f}   sd {er.std():.4f}")
    print(f"  win events {len(wins)/n_ev:.1%} @ mean {wins.mean():+.4f}   "
          f"loss events {len(losses)/n_ev:.1%} @ mean {losses.mean():+.4f}")
    print(f"  worst single event {er.min():+.4f}   best {er.max():+.4f}")
    print(f"  share of total P&L from the top-5% events: {top5_share:.1%}  "
          f"({'CONCENTRATED — fragile' if top5_share > 0.6 else 'broad'})\n")

    # -------------------------------------------------------------- K1 Kelly
    fk, g = kelly_fraction(er)
    print("K1 -- KELLY")
    print(f"  full-Kelly fraction f* = {fk:.3f}   (log-growth {g:+.5f}/event)")
    print(f"  1/8-Kelly (risk-engine cap) = {fk/8:.3f}\n")

    # -------------------------------------------------------------- K2 ruin / drawdown
    horizon = min(n_ev, 500)      # a season-ish horizon
    print(f"K2 -- BLOCK-BOOTSTRAP RUIN & DRAWDOWN over {horizon} events "
          f"(event bundle preserved)")
    print(f"{'fraction':>16s} {'med final x':>12s} {'P(final<1)':>11s} "
          f"{'P(DD>50%)':>10s} {'P(ruin<20%)':>12s} {'med maxDD':>10s}")
    print("-" * 76)
    for lab, f in [("1/8-Kelly", fk / 8), ("1/4-Kelly", fk / 4), ("half-Kelly", fk / 2),
                   ("full-Kelly", fk), ("flat 2%", 0.02), ("flat 5%", 0.05)]:
        med, pf, pdd, ruin, mdd = simulate(er, f, horizon)
        print(f"{lab:>10s} f={f:>4.3f} {med:>12.3f} {pf:>11.1%} {pdd:>10.1%} "
              f"{ruin:>12.1%} {mdd:>10.1%}")

    # K2b -- the conservative unit: resample by DAY (captures same-slate upset correlation)
    fk_d, _ = kelly_fraction(dr)
    hor_d = min(n_day, 200)
    print(f"\nK2b -- DAY-BLOCK bootstrap over {hor_d} days (same-slate correlation captured); "
          f"day-Kelly f*={fk_d:.3f}")
    print(f"{'fraction':>16s} {'med final x':>12s} {'P(final<1)':>11s} "
          f"{'P(DD>50%)':>10s} {'P(ruin<20%)':>12s} {'med maxDD':>10s}")
    print("-" * 76)
    for lab, f in [("1/8-Kelly", fk_d / 8), ("1/4-Kelly", fk_d / 4),
                   ("flat 2%", 0.02), ("flat 5%", 0.05)]:
        med, pf, pdd, ruin, mdd = simulate(dr, f, hor_d)
        print(f"{lab:>10s} f={f:>4.3f} {med:>12.3f} {pf:>11.1%} {pdd:>10.1%} "
              f"{ruin:>12.1%} {mdd:>10.1%}")
    print("\n  Unit of risk = the EVENT (a game's bets are one bundled draw); DAY-block is the")
    print("  conservative check. 'ruin' = bankroll ever below 20% of start. The cap exists because")
    print("  the mean cannot pay for a tail that ruins you.")


if __name__ == "__main__":
    main()
