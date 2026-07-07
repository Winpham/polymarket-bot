#!/usr/bin/env python3
"""
SPECIALIZE — "play to each trader's strengths" done the honest way (event-grain).

Two strictly separated layers:
  (1) DESCRIPTIVE PROFILE (no promotion): where each trader's copyable directional surplus and
      CLV concentrate — by axis: sport, market-type (moneyline/total/exact_score/spread),
      favorite-vs-longshot, early-vs-late entry. The MAP of "what is each good at".
  (2) CERTIFICATION (guardrail vs the dead specialist book): a (trader × cell) "strength" counts
      only if it survives a LABEL-PERMUTATION NULL over EVERY cell at once — within each price
      band, permute event surpluses across events (breaks the event->skill link, preserves band
      difficulty + cell sizes), recompute all cells, N times. A real specialization must beat the
      count of survivors noise manufactures across the whole grid. Slicing per-trader×cell
      AMPLIFIES the winner's curse, so this multiplicity control is mandatory.

Everything at OUR copyable price: our_entry = price + 0.013 (tax) + band_spread;
ret = (won - our_entry)/our_entry - 0.02 (fee); surplus = ret - fleet_blind[band]. CLV at our
price = closing_line(last-20% tape) - our_entry. Event-clustered (ev=COALESCE(event_slug,
condition_id)); one row per (wallet,ev). NON-MM cohort (churn screen). READ-ONLY. --selftest ok.
"""
import argparse, json, math, os, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))   # scripts/ holds mm_common
import mm_common as mc      # noqa: E402

REPORT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "reports", "specialize", "specialize.json")
MIN_CELL = 15
Z = 1.6449

SQL = r"""
WITH spreads AS (
  SELECT width_bucket(initial_mean_price,0.0,1.0,5) band,
         AVG(GREATEST(entry_ask - entry_ask_mid, 0)) spread
  FROM consensus_signals
  WHERE entry_ask IS NOT NULL AND entry_ask_mid IS NOT NULL AND entry_ask_at IS NOT NULL
    AND EXTRACT(EPOCH FROM (entry_ask_at - first_detected_at)) <= 900
  GROUP BY 1),
f AS (
  SELECT lower(wallet) w, condition_id co, outcome_index oi, COALESCE(event_slug,condition_id) ev,
         EXTRACT(EPOCH FROM ts) t, price, side, (outcome_won::int) won,
         COALESCE(sport,'other') sport,
         CASE WHEN slug ILIKE '%exact-score%' OR slug ILIKE '%correct-score%' THEN 'exact_score'
              WHEN slug ILIKE '%-total-%' OR slug ILIKE '%over-under%' THEN 'total'
              WHEN slug ILIKE '%spread%' OR slug ILIKE '%handicap%' THEN 'spread'
              ELSE 'moneyline' END mtype,
         width_bucket(price,0.0,1.0,5) band
  FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL),
span AS (SELECT co, oi, min(t) tmin, max(t) tmax FROM f GROUP BY 1,2),
clo AS (
  SELECT f.co, f.oi, avg(f.price) close_price FROM f JOIN span s ON f.co=s.co AND f.oi=s.oi
  WHERE s.tmax>s.tmin AND f.t >= s.tmax - 0.2*(s.tmax-s.tmin) GROUP BY 1,2 HAVING count(*)>=5),
buys AS (
  SELECT f.w, f.ev, f.sport, f.mtype, f.band, f.won,
         (f.price + 0.013 + COALESCE(sp.spread,0)) our_entry, c.close_price,
         (f.t - s.tmin)/NULLIF(s.tmax-s.tmin,0) lateness
  FROM f JOIN span s ON f.co=s.co AND f.oi=s.oi
  LEFT JOIN clo c ON c.co=f.co AND c.oi=f.oi
  LEFT JOIN spreads sp ON sp.band=f.band
  WHERE f.side='BUY'),
we AS (
  SELECT w, ev,
    AVG((won::float8 - our_entry)/NULLIF(our_entry,0) - 0.02) ret,
    AVG(CASE WHEN close_price IS NOT NULL THEN close_price - our_entry END) clv,
    round(AVG(band))::int band,
    MIN(sport) sport, MIN(mtype) mtype, AVG(lateness) lateness
  FROM buys GROUP BY w, ev)
SELECT w, ev, ret, clv, band, sport, mtype, lateness FROM we;
"""


def load():
    rows = mc.q(SQL)
    micro = mc.microstructure()
    band_ret = defaultdict(list)
    ev = []
    for r in rows:
        try:
            w, evk = r[0], r[1]
            ret = float(r[2]); clv = float(r[3]) if r[3] not in ("", None) else None
            band = int(float(r[4])); sport = r[5]; mtype = r[6]
            lateness = float(r[7]) if r[7] not in ("", None) else None
        except (ValueError, IndexError):
            continue
        m = micro.get(w)
        if m is None or mc.is_churner(m):
            continue
        band_ret[band].append(ret)
        ev.append({"w": w, "ev": evk, "ret": ret, "clv": clv, "band": band,
                   "sport": sport, "mtype": mtype, "lateness": lateness})
    blind = {b: sum(v)/len(v) for b, v in band_ret.items()}
    for e in ev:
        e["surplus"] = e["ret"] - blind.get(e["band"], 0.0)
        e["fav"] = "fav" if e["band"] >= 3 else "dog"
        e["timing"] = None if e["lateness"] is None else ("early" if e["lateness"] < 0.5 else "late")
    return ev, blind


AXES = ["sport", "mtype", "fav", "timing"]


def lb(vals):
    n = len(vals)
    if n < 3:
        return None
    m = sum(vals)/n
    var = sum((x-m)**2 for x in vals)/(n-1)
    return m - Z*math.sqrt(var/n)


def run(n_perm=1000):
    ev, blind = load()
    if len(ev) < 500:
        return {"error": "insufficient data", "n_events": len(ev)}
    # cell -> list of event indices
    cell_idx = defaultdict(list)
    for i, e in enumerate(ev):
        for axis in AXES:
            val = e[axis]
            if val is None:
                continue
            cell_idx[(e["w"], axis, val)].append(i)
    surplus = [e["surplus"] for e in ev]
    clv = [e["clv"] for e in ev]
    band = [e["band"] for e in ev]

    elig = [(k, idxs) for k, idxs in cell_idx.items() if len(idxs) >= MIN_CELL]

    # observed survivors (copyable surplus LB > 0)
    obs = []
    for k, idxs in elig:
        v = lb([surplus[i] for i in idxs])
        if v is not None and v > 0:
            obs.append((k, v, len(idxs)))
    n_obs = len(obs)

    # permutation null: within each band, permute surplus across events; recompute survivor count
    band_members = defaultdict(list)
    for i, b in enumerate(band):
        band_members[b].append(i)
    rng = _LCG()
    null_counts = []
    for _ in range(n_perm):
        perm = surplus[:]  # copy
        for b, members in band_members.items():
            vals = [surplus[i] for i in members]
            for j in range(len(vals)-1, 0, -1):
                kk = rng.idx(j+1)
                vals[j], vals[kk] = vals[kk], vals[j]
            for i, val in zip(members, vals):
                perm[i] = val
        cnt = 0
        for k, idxs in elig:
            v = lb([perm[i] for i in idxs])
            if v is not None and v > 0:
                cnt += 1
        null_counts.append(cnt)
    null_counts.sort()
    null_mean = sum(null_counts)/len(null_counts)
    null_p95 = null_counts[min(len(null_counts)-1, int(0.95*len(null_counts)))]
    pval = sum(1 for c in null_counts if c >= n_obs)/len(null_counts)

    # descriptive: build survivor detail + top strength cells (by surplus LB)
    obs.sort(key=lambda x: x[1], reverse=True)
    surv = [{"wallet": k[0][:12], "axis": k[1], "cell": k[2], "n_ev": n, "surplus_LB": round(v, 4)}
            for (k, v, n) in obs]
    # per-trader descriptive profile (top powered cells regardless of certification)
    prof = defaultdict(list)
    for k, idxs in elig:
        w, axis, val = k
        s_lb = lb([surplus[i] for i in idxs])
        cvals = [clv[i] for i in idxs if clv[i] is not None]
        prof[w].append({"axis": axis, "cell": val, "n_ev": len(idxs),
                        "surplus_mean": round(sum(surplus[i] for i in idxs)/len(idxs), 4),
                        "surplus_LB": round(s_lb, 4) if s_lb is not None else None,
                        "clv_mean": round(sum(cvals)/len(cvals), 4) if cvals else None})
    for w in prof:
        prof[w].sort(key=lambda c: (c["surplus_LB"] if c["surplus_LB"] is not None else -9), reverse=True)

    return {
        "cohort": "non-MM directional (churn-locked)", "price": "our copyable entry (tax+spread+fee)",
        "n_events": len(ev), "n_wallets": len({e["w"] for e in ev}),
        "n_eligible_cells": len(elig), "min_cell_events": MIN_CELL, "axes": AXES, "n_perm": n_perm,
        "certification": {
            "observed_cells_surplus_LB_pos": n_obs,
            "null_expected_survivors_mean": round(null_mean, 1),
            "null_95pct": null_p95,
            "p_value_observed_ge_null": round(pval, 4),
            "verdict": ("SPECIALIZATION SURVIVES multiplicity — real per-cell strengths exist"
                        if (pval < 0.05 and n_obs > null_p95) else
                        "NO SPECIALIZATION BEYOND CHANCE — observed 'strength' cells are within the "
                        "label-permutation null; per-trader×cell edges are winner's-curse artifacts. "
                        "Descriptive map is fine to READ; do not bet on it. Forward CLV-at-our-price "
                        "per cell + expansion is the only path to real specialization.")},
        "top_certified_or_apparent_cells": surv[:25],
        "n_traders_profiled": len(prof),
        "example_profiles": {w: prof[w][:5] for w in list(sorted(prof))[:6]},
    }


class _LCG:
    def __init__(self, seed=0x9E3779B97F4A7C15):
        self.s = seed & 0xFFFFFFFFFFFFFFFF
    def nxt(self):
        self.s = (6364136223846793005*self.s + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return self.s
    def idx(self, n):
        return (self.nxt() >> 17) % n


def selftest():
    rng = _LCG()
    assert 0 <= rng.idx(7) < 7
    assert abs(lb([1.0, 1.0, 1.0, 1.0]) - 1.0) < 1e-9
    v = lb([-1.0, 0.0, 1.0, -0.5, 0.2]); assert v < 0
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--n-perm", type=int, default=1000)
    a = ap.parse_args()
    if a.selftest:
        selftest(); sys.exit(0)
    res = run(a.n_perm)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps(res, indent=2, default=str)[:2600])
