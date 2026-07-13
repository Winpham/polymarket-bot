#!/usr/bin/env python3
"""
EVERGREEN-PORTFOLIO — per-market-type arm verdict (Evergreen-Portfolio run, 2026-07-12).

Judges each evergreen branch (highest-temperature, lowest-temperature) on its OWN gate, then asks
whether the branches together diversify. Emits reports/EVERGREEN-PORTFOLIO-VERDICT.json. Certifies
nothing by itself — the frozen preregs are the arbiter.

WHAT THIS RUN CHANGED ABOUT WHAT IS EVEN MEASURABLE (both defects fixed/quantified here):

1. RESOLUTION (fixed). The `trader_fills` resolver was a strict oldest-first FIFO whose head was
   permanently-unresolvable markets (2028-nomination markets that don't settle for years), so it never
   reached ANY recent market — 4,153 weather conditions sat unresolved while their outcomes were public
   the whole time. Draining that backlog created the SECOND DISJOINT WEEK, so **LODO-by-week — the
   decisive gate, previously declared IMPOSSIBLE — runs here for the first time.**

2. BASIS (quantified, and it is NOT what the prior run believed). Every earlier weather number was
   measured at `COALESCE(initial_mean_price, mean_price)` and called "the at-fire CLOB mid ... a fast
   copier's fill". It is neither: `mean_price` is the mean price the BACKERS THEMSELVES FILLED at. The
   real market price column (`initial_market_price`) is NULL on all 2,131 `_blind` weather signals, and
   the prior "copyability haircut ~= 0" simply compared two fill-price averages drawn from overlapping
   populations — near-tautologically close, and silent about what a COPIER pays.
   The live arm has now captured 85 REAL asks, so the copier's cost is finally measured, not modeled:
       entry_ask - entry_ask_mid  = +1.09c   (the thin-book spread tax)
       entry_ask - vote-mean      = +2.03c   (~2.3pp of ROI-on-turnover the prior basis never charged)
   A reconstruction of the mid from CLOB prices-history was attempted and REJECTED by its own
   validation gate (see atfire_recon.py) — it did not track the real captured mid, so it is not used.

Consequently this instrument reports TWO clearly-labelled bases and never conflates them:
  * `sharp_fill`  — entry = the backers' own mean fill. Available on BOTH weeks, so it is what carries
                    the LODO-by-week test. It is a DIRECTIONAL CEILING, not a copyable price: no one but
                    the sharps gets it. It answers "does the SELECTION survive a disjoint week?"
  * `copier_ask`  — entry = sharp fill + the MEASURED haircut a copier actually pays (derived from the
                    live captures above, per family). It answers "is there money left AT OUR PRICE?"
An edge that lives only in `sharp_fill` is a signal we cannot buy.

Read-only. Self-test: ./evergreen_portfolio.py --selftest
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C  # noqa: E402

WIDE_CUTOFF = 250
CAPTURE_LO, CAPTURE_HI = 0.71, 0.98   # what the arms CAPTURE
CERT_LO, CERT_HI = 0.71, 0.90         # what they CERTIFY on (deep chalk 0.90+ is the win-rate trap)

FAMILIES = {
    "weather":     {"regex": "highest-temperature", "arm": "weather_fav"},
    "weather_low": {"regex": "lowest-temperature",  "arm": "weather_low_fav"},
}
REPORTS = Path(__file__).resolve().parent.parent / "reports"


def iso_week(day):
    """ISO week key from a 'YYYY-MM-DD' string (the disjoint-week unit of the frozen gate)."""
    import datetime as dt
    y, m, d = (int(x) for x in str(day).split("-"))
    return "%d-W%02d" % dt.date(y, m, d).isocalendar()[:2]


def fetch_picks(family_regex):
    """Wider-universe convergence picks (>=3 one-sided backers, capture band, resolved) for ONE family.
    `cluster` = the resolution DAY: cross-city same-day temperature is correlated (one heat dome resolves
    ~20 cities together), so the honest independent unit is the day, never the city-market."""
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, AVG(f.price) px, MIN(f.ts) ts,
             MAX(f.slug) slug, BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='2026-07-01' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{family_regex}'
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
      (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
    conv AS (
      SELECT condition_id, outcome_index, MAX(slug) slug, count(*) nb, AVG(px) sharp_px,
             BOOL_OR(rz) rz, BOOL_OR(won) won, MIN(ts)::date d
      FROM e1 GROUP BY 1,2
      HAVING count(*)>=3 AND AVG(px) BETWEEN {CAPTURE_LO} AND {CAPTURE_HI})
    SELECT condition_id, outcome_index, slug, nb, sharp_px, won, d
    FROM conv WHERE rz AND won IS NOT NULL;
    """)
    out = []
    for r in rows:
        cond, oi, slug, nb, sharp, won, day = r[:7]
        out.append({
            "condition_id": f"{cond}:{oi}", "slug": slug, "n_backers": int(nb),
            "sharp_px": float(sharp), "won": won == "t",
            "cluster": str(day), "day": str(day), "week": iso_week(day),
        })
    return out


def measure_haircut(arm, family_regex):
    """The copier's REAL cost, from the live arm's captured asks — measured against the SAME
    `sharp_px` basis the history is measured on, so the two are comparable. Never modeled."""
    rows = C.q(f"""
    WITH conv AS (
      SELECT f.condition_id, f.outcome_index, AVG(f.price) sharp_px
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{family_regex}'
      GROUP BY 1,2)
    SELECT s.entry_ask, s.entry_ask_mid, c.sharp_px
    FROM consensus_signals s JOIN conv c
      ON c.condition_id=s.condition_id AND c.outcome_index=s.outcome_index
    WHERE s.strategy='{arm}' AND s.entry_ask IS NOT NULL AND s.entry_ask_mid IS NOT NULL;
    """)
    hs, spreads = [], []
    for r in rows:
        ask, mid, sharp = float(r[0]), float(r[1]), float(r[2])
        hs.append(ask - sharp)
        spreads.append(ask - mid)
    if not hs:
        return {"n": 0, "haircut_vs_sharp": None, "spread_ask_minus_mid": None,
                "note": "NO captured asks yet — the copier's price for this family is UNMEASURED"}
    return {
        "n": len(hs),
        "haircut_vs_sharp": round(statistics.fmean(hs), 4),
        "haircut_sd": round(statistics.pstdev(hs), 4) if len(hs) > 1 else None,
        "spread_ask_minus_mid": round(statistics.fmean(spreads), 4),
    }


def fetch_blind_universe(family_regex):
    """The BELIEF-BLIND comparison population: every (market, favorite-side) in this family that a
    tracked wider-universe trader bought in the capture band and that RESOLVED — WITHOUT requiring the
    >=3 one-sided convergence the arm fires on.

    This is the honest null for the arm's SELECTION: given the sharps touched a weather market at all,
    does CONVERGING on it add skill over a random weather favorite at the same (band x day)? If not, the
    "edge" is composition — several bots co-reading the same public NOAA/ECMWF forecast — and it
    certifies to ~0. Note the scope: this conditions on "a tracked trader bet it", so it tests the
    convergence rule, not forecastability of the whole weather book (the `_blind` arm never covered
    weather, so a full-book blind does not exist in our data — stated, not papered over)."""
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, AVG(f.price) px,
             BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won, MIN(f.ts)::date d
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='2026-07-01' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{family_regex}'
      GROUP BY 1,2,3)
    SELECT condition_id, outcome_index, AVG(px) px, BOOL_OR(rz) rz, BOOL_OR(won) won, MIN(d) d
    FROM e GROUP BY 1,2
    HAVING AVG(px) BETWEEN {CAPTURE_LO} AND {CAPTURE_HI};
    """)
    out = []
    for r in rows:
        cond, oi, px, rz, won, day = r[:6]
        if rz != "t" or won not in ("t", "f"):
            continue
        out.append({"key": f"{cond}:{oi}", "sharp_px": float(px), "won": won == "t",
                    "cluster": str(day), "day": str(day), "week": iso_week(day)})
    return out


def selection_null(picks, universe, haircut, n_perm=2000, seed=20260712):
    """Belief-blind guard. Draw `n_perm` placebo arms from the blind universe, matched to the real
    arm's (band x day) profile, and ask how often a placebo's day-clustered LB beats the real one.
    p_emp <= 0.01 required. A high p means the convergence rule selects no better than chance among
    the weather favorites the sharps touched — i.e. forecast-co-reading, not alpha."""
    import random
    rng = random.Random(seed)
    real_rows = rows_at(picks, haircut)
    if len(real_rows) < 2:
        return {"p_emp": None, "verdict": "INSUFFICIENT DATA"}
    real = C.roi_lb(real_rows)
    if not real or real.get("lb") is None:
        return {"p_emp": None, "verdict": "INSUFFICIENT DATA"}
    real_lb = real["lb"]

    picked = {p["condition_id"] for p in picks}
    # Match the arm's profile: same number of draws per (band x day) cell, from the blind universe.
    want = defaultdict(int)
    for p in picks:
        if CERT_LO <= p["sharp_px"] < CERT_HI:
            want[(C.band_of(p["sharp_px"]), p["day"])] += 1
    pool = defaultdict(list)
    for u in universe:
        if u["key"] in picked:
            continue  # a placebo must be drawn from what the arm did NOT pick
        if CERT_LO <= u["sharp_px"] < CERT_HI:
            pool[(C.band_of(u["sharp_px"]), u["day"])].append(u)

    drawable = sum(min(k, len(pool[cell])) for cell, k in want.items())
    if drawable < 0.5 * sum(want.values()):
        return {"p_emp": None, "n_matched": drawable, "n_real": sum(want.values()),
                "verdict": "INDETERMINATE — the blind universe is too thin to build a matched placebo "
                           "(the arm picks nearly everything the sharps touched, so there is little "
                           "left to draw a placebo FROM)"}

    beats = 0
    for _ in range(n_perm):
        draw = []
        for cell, k in want.items():
            cand = pool.get(cell) or []
            if not cand:
                continue
            draw.extend(rng.sample(cand, min(k, len(cand))))
        rows = [{"entry": min(max(u["sharp_px"] + haircut, 0.01), 0.99), "won": u["won"],
                 "condition_id": u["key"], "cluster": u["cluster"], "day": u["day"], "week": u["week"]}
                for u in draw]
        if len(rows) < 2:
            continue
        placebo = C.roi_lb(rows)
        if placebo and placebo.get("lb") is not None and placebo["lb"] >= real_lb:
            beats += 1
    p = (beats + 1) / (n_perm + 1)
    return {
        "p_emp": round(p, 4), "n_perm": n_perm, "real_lb": round(real_lb, 4),
        "n_matched": drawable, "n_real": sum(want.values()),
        "passes_p01": p <= 0.01,
        "verdict": ("PASSES — convergence selects better than a random weather favorite at the same band x day"
                    if p <= 0.01 else
                    "FAILS — no better than a random weather favorite (forecast-co-reading / composition)"),
    }


def rows_at(picks, haircut, lo=CERT_LO, hi=CERT_HI):
    """Objective rows in the certification band at a given entry basis (haircut=0 => sharp fill)."""
    out = []
    for p in picks:
        if not (lo <= p["sharp_px"] < hi):
            continue
        entry = min(max(p["sharp_px"] + haircut, 0.01), 0.99)
        out.append({"entry": entry, "won": p["won"], "condition_id": p["condition_id"],
                    "cluster": p["cluster"], "slug": p["slug"], "week": p["week"], "day": p["day"]})
    return out


def lodo_by_week(rows):
    """THE decisive gate — impossible before this run's resolver fix. Leave each calendar week out in
    turn and recompute. An edge that survives only WITH its dominant week is that week's streak."""
    weeks = sorted({r["week"] for r in rows})
    if len(weeks) < 2:
        return {"weeks": weeks, "possible": False,
                "verdict": "IMPOSSIBLE — single window (cannot distinguish a strategy from one regime)"}
    per, folds = {}, []
    for w in weeks:
        kept = [r for r in rows if r["week"] != w]
        held = [r for r in rows if r["week"] == w]
        lb_out = C.roi_lb(kept)
        lb_in = C.roi_lb(held)
        per[w] = {
            "n_in_week": len(held),
            "days_in_week": len({r["day"] for r in held}),
            "lb_this_week_alone": round(lb_in["lb"], 4) if lb_in and lb_in.get("lb") is not None else None,
            "point_this_week_alone": round(lb_in["point"], 4) if lb_in else None,
            "lb_without_this_week": round(lb_out["lb"], 4) if lb_out and lb_out.get("lb") is not None else None,
        }
        if lb_out and lb_out.get("lb") is not None:
            folds.append(lb_out["lb"])
    survives = bool(folds) and all(f > 0 for f in folds)
    return {
        "weeks": weeks, "possible": True, "per_week": per,
        "min_lb_across_folds": round(min(folds), 4) if folds else None,
        "survives_lodo_by_week": survives,
        "verdict": ("SURVIVES — LB stays >0 with any single week removed" if survives
                    else "FAILS — the edge does not survive dropping a week (single-regime streak)"),
    }


def daily_roi(rows):
    """Per-day ROI-on-turnover — the unit for cross-arm correlation (a day, never a city-market)."""
    pnl, stk = defaultdict(float), defaultdict(float)
    for r in rows:
        pnl[r["day"]] += C.pnl(r["entry"], r["won"])
        stk[r["day"]] += r["entry"]
    return {d: pnl[d] / stk[d] for d in pnl if stk[d] > 0}


def correlation(a, b):
    """Cross-arm correlation on COMMON days. Diversification only counts if each arm is +EV AND the
    arms are genuinely low-correlated — and a handful of common days can only ever be INDICATIVE."""
    common = sorted(set(a) & set(b))
    if len(common) < 3:
        return {"common_days": len(common), "corr": None,
                "verdict": "INDETERMINATE — too few common days to estimate correlation"}
    xs, ys = [a[d] for d in common], [b[d] for d in common]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    if vx == 0 or vy == 0:
        return {"common_days": len(common), "corr": None, "verdict": "INDETERMINATE — zero variance"}
    c = cov / (vx * vy)
    return {
        "common_days": len(common), "corr": round(c, 3),
        "low_correlated": abs(c) < 0.30,
        "verdict": ("INDICATIVE ONLY — too few common days to rely on"
                    if len(common) < 20 else "estimated on >=20 common days"),
    }


def assess(name, picks, haircut_info, universe):
    """One branch, on both bases, against its own gate."""
    hc = haircut_info.get("haircut_vs_sharp")
    sharp_rows = rows_at(picks, 0.0)
    out = {
        "family": name,
        "picks_capture_band": len(picks),
        "picks_cert_band": len(sharp_rows),
        "days": len({r["day"] for r in sharp_rows}),
        "weeks": sorted({r["week"] for r in sharp_rows}),
        "copier_cost_measured": haircut_info,
    }
    if len(sharp_rows) < 2:
        out["verdict"] = "NO DATA in the certification band"
        return out

    sharp_lb = C.roi_lb(sharp_rows)
    out["sharp_fill_basis"] = {
        "point": round(sharp_lb["point"], 4), "lb": round(sharp_lb["lb"], 4) if sharp_lb.get("lb") is not None else None,
        "day_clusters": sharp_lb["G_clusters"],
        "meaning": "DIRECTIONAL CEILING — the sharps' own fill. Nobody else can buy at this price.",
    }
    out["lodo_by_week_sharp_basis"] = lodo_by_week(sharp_rows)
    out["selection_null"] = selection_null(picks, universe, 0.0)

    if hc is None:
        out["copier_ask_basis"] = {"verdict": "UNMEASURED — no captured asks for this family yet"}
        out["daily_roi"] = daily_roi(sharp_rows)
        return out

    ask_rows = rows_at(picks, hc)
    ask_lb = C.roi_lb(ask_rows)
    boot = C.bootstrap_lb(ask_rows) if len(ask_rows) >= 2 else None
    out["copier_ask_basis"] = {
        "haircut_charged": round(hc, 4),
        "point": round(ask_lb["point"], 4) if ask_lb else None,
        "lb": round(ask_lb["lb"], 4) if ask_lb and ask_lb.get("lb") is not None else None,
        "boot_lb": round(boot["lb"], 4) if boot and boot.get("lb") is not None else None,
        "day_clusters": ask_lb["G_clusters"] if ask_lb else None,
        "meaning": "REALIZABLE — the sharps' fill plus the haircut a copier actually paid (measured).",
    }
    out["lodo_by_week_copier_basis"] = lodo_by_week(ask_rows)
    out["daily_roi"] = daily_roi(ask_rows)
    return out


def build():
    rep = {
        "as_of": "2026-07-12",
        "run": "evergreen per-market-type arm portfolio",
        "cluster_unit": "resolution DAY (cross-city same-day temperature is correlated)",
        "cert_band": [CERT_LO, CERT_HI],
        "champion_honest_floor": 0.056,
        "bases": {
            "sharp_fill": "backers' own mean fill — DIRECTIONAL CEILING, not buyable",
            "copier_ask": "sharp fill + MEASURED copier haircut from the live arm's captured asks",
        },
        "arms": {},
    }
    dailies = {}
    for name, f in FAMILIES.items():
        picks = fetch_picks(f["regex"])
        hc = measure_haircut(f["arm"], f["regex"])
        a = assess(name, picks, hc, fetch_blind_universe(f["regex"]))
        dailies[name] = a.pop("daily_roi", {})
        rep["arms"][name] = a

    rep["diversification"] = correlation(dailies.get("weather", {}), dailies.get("weather_low", {}))

    # Portfolio: equal-weight the arms' per-day ROI on days where either fires. Only meaningful if the
    # arms independently certify — reported regardless, but flagged, never used to rescue a dead arm.
    alldays = sorted(set(dailies.get("weather", {})) | set(dailies.get("weather_low", {})))
    port = []
    for d in alldays:
        vals = [dailies[k][d] for k in dailies if d in dailies[k]]
        if vals:
            port.append(statistics.fmean(vals))
    rep["portfolio"] = {
        "days": len(port),
        "mean_daily_roi": round(statistics.fmean(port), 4) if port else None,
        "note": ("A portfolio number is only meaningful once EACH arm independently certifies. "
                 "It is reported for completeness, never to rescue an arm that failed its own gate."),
    }
    return rep


def selftest():
    ok = True
    if iso_week("2026-07-06") == iso_week("2026-07-05"):
        print("FAIL iso_week: 07-05 (Sun) and 07-06 (Mon) must differ"); ok = False
    if iso_week("2026-07-08") != iso_week("2026-07-06"):
        print("FAIL iso_week: same week"); ok = False
    # LODO is IMPOSSIBLE on one week and POSSIBLE on two — the whole point of the resolver fix.
    one = [{"entry": 0.8, "won": True, "condition_id": f"c{i}", "cluster": f"d{i}",
            "day": f"d{i}", "week": "2026-W27"} for i in range(4)]
    if lodo_by_week(one)["possible"]:
        print("FAIL lodo: single week must be IMPOSSIBLE"); ok = False
    two = one + [{"entry": 0.8, "won": True, "condition_id": f"k{i}", "cluster": f"e{i}",
                  "day": f"e{i}", "week": "2026-W28"} for i in range(4)]
    if not lodo_by_week(two)["possible"]:
        print("FAIL lodo: two weeks must be POSSIBLE"); ok = False
    # An all-win set must survive; a set that only wins in one week must FAIL.
    if not lodo_by_week(two)["survives_lodo_by_week"]:
        print("FAIL lodo: an all-win set should survive"); ok = False
    streak = [{"entry": 0.8, "won": True, "condition_id": f"c{i}", "cluster": f"d{i}",
               "day": f"d{i}", "week": "2026-W27"} for i in range(5)] + \
             [{"entry": 0.8, "won": False, "condition_id": f"k{i}", "cluster": f"e{i}",
               "day": f"e{i}", "week": "2026-W28"} for i in range(5)]
    if lodo_by_week(streak)["survives_lodo_by_week"]:
        print("FAIL lodo: a one-week streak must NOT survive"); ok = False
    # correlation: too few common days => INDETERMINATE, never a number
    if correlation({"a": 0.1}, {"a": 0.2})["corr"] is not None:
        print("FAIL correlation: <3 common days must be INDETERMINATE"); ok = False
    print("evergreen_portfolio selftest: PASS" if ok else "evergreen_portfolio selftest: FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(selftest())
    rep = build()
    (REPORTS / "EVERGREEN-PORTFOLIO-VERDICT.json").write_text(json.dumps(rep, indent=2))
    print("wrote EVERGREEN-PORTFOLIO-VERDICT.json\n")
    for name, a_ in rep["arms"].items():
        print(f"=== {name}  picks(cert)={a_.get('picks_cert_band')}  days={a_.get('days')}  weeks={a_.get('weeks')}")
        cc = a_.get("copier_cost_measured", {})
        print(f"    copier haircut (measured, n={cc.get('n')}): {cc.get('haircut_vs_sharp')}  "
              f"spread(ask-mid)={cc.get('spread_ask_minus_mid')}")
        sf = a_.get("sharp_fill_basis", {})
        print(f"    sharp_fill  : point={sf.get('point')} LB={sf.get('lb')} G={sf.get('day_clusters')}")
        ca = a_.get("copier_ask_basis", {})
        print(f"    copier_ask  : point={ca.get('point')} LB={ca.get('lb')} boot={ca.get('boot_lb')}")
        sn = a_.get("selection_null")
        if sn:
            print(f"    selection_null: p={sn.get('p_emp')} ({sn.get('n_real')} real vs {sn.get('n_matched')} matched) -> {sn.get('verdict')}")
        for basis in ("lodo_by_week_sharp_basis", "lodo_by_week_copier_basis"):
            L = a_.get(basis)
            if L:
                print(f"    {basis}: {L.get('verdict')}  min_fold_LB={L.get('min_lb_across_folds')}")
    print(f"\nDIVERSIFICATION: {json.dumps(rep['diversification'])}")
    print(f"PORTFOLIO: {json.dumps(rep['portfolio'])}")


if __name__ == "__main__":
    main()
