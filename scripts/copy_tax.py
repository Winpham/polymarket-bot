#!/usr/bin/env python3
"""
H5 COPYABILITY TAX — a MEASUREMENT, not a gate (PREREG_20260706T000604Z §3.H5).

The whole favorite-consensus edge is measured at the sharps' at-fire fill (`mean_price`). A
follower cannot fill there: by the time the signal is observed and acted on, the executable price
has moved. §H5 measures that move directly from the dense capture (`signal_price_trajectory`):

    tax = (first executable price >= 60s after fire) - (at-fire mean_price)          [a BUY: ask]

per (band x sport-category), for strategies `favorite` and `strict`. Rows lacking a >=60s
executable trajectory point are EXCLUDED (no imputation). The 2% fee buffer is NOT netted out
here (it stays a separate conservative buffer, per prereg §1). No certification language: the only
downstream claim is a "realizable LB after tax" = an H1/H2 LB minus the band-matched tax.

Conventions mirrored from the shipped instruments (no re-derivation):
  - band(entry), entry = COALESCE(initial_mean_price, mean_price), 5x0.2 bands int(p*5)+1 clip[1,5]
    (favconsensus_reverify.band) -- so tax cells line up with the H1/H2 band4/band5 cells.
  - category(slug, title)  (market_taxonomy.category).
  - executable price = best `ask` (what a follower pays to BUY); mirrors clv_lambda's use of the
    trajectory table. "first >=60s point" = earliest row with secs_after_fire >= 60 AND ask NOT NULL
    (secs_after_fire is the recorded ts - first_detected_at offset; the ts>=fire+60s filter is
    equivalent). Its median secs_after_fire (the ACTUAL lag) is reported per cell -- for `favorite`
    the capture is sparse so the earliest >=60s point is a MEDIAN ~900s out, NOT ~60s: stated, not
    hidden.

Two cruder proxies already in the repo are reported on the SAME signal subset so the three
estimates can be reconciled (DATA-MODEL.md):
  - capture-drift proxy = initial_market_price - mean_price   (first-observed mid drift, ~10-15min)
  - ask-haircut proxy   = entry_ask - entry_ask_mid           (spread paid, same-pass mid vs ask)

Usage:
  ./copy_tax.py                 # measure on the live record; writes reports/copy_tax.json
  ./copy_tax.py --self-test     # synthetic fixtures (assert-based; no DB); exits non-zero on fail
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from collections import defaultdict
from statistics import mean, median, pstdev, stdev

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_taxonomy import category  # noqa: E402
from superkey import super_event      # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
MIN_LAG_SECS = 60          # >= 60s after fire (frozen, §H5)
POOL_FALLBACK_N = 5        # cell tax with N<5 falls back to the pooled-strategy tax (team-lead rule)
STRATEGIES = ("favorite", "strict")

# 0.7c follower-tax proxy referenced in the brief = copyability.json band-4 band_spread.
FOLLOWER_TAX_PROXY = 0.0071

SIG_SQL = """
SELECT id, strategy, slug, event_slug, title,
       mean_price,
       COALESCE(initial_mean_price, mean_price) AS entry,
       initial_market_price, entry_ask, entry_ask_mid,
       (resolved AND outcome_won IS NOT NULL)::int AS graded
FROM consensus_signals
WHERE strategy IN ('favorite','strict')
"""

# earliest executable (ask NOT NULL) trajectory point at >= 60s after fire, per signal.
FIRST_SQL = """
SELECT DISTINCT ON (t.signal_id) t.signal_id, t.ask, t.mid, t.secs_after_fire
FROM signal_price_trajectory t
WHERE t.ask IS NOT NULL AND t.secs_after_fire >= {lag}
ORDER BY t.signal_id, t.secs_after_fire ASC
""".format(lag=MIN_LAG_SECS)


def band(p):
    """favconsensus_reverify.band -- 5x0.2 bands, clip to [1,5]."""
    if p < 0:
        return 1
    if p >= 1:
        return 5
    return int(p * 5) + 1


def _q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def _f(v):
    return float(v) if v not in (None, "", "NULL") else None


def fetch():
    firsts = {r["signal_id"]: {"ask": _f(r["ask"]), "mid": _f(r["mid"]),
                               "lag": int(r["secs_after_fire"])} for r in _q(FIRST_SQL)}
    sigs = []
    for r in _q(SIG_SQL):
        entry = _f(r["entry"])
        mp = _f(r["mean_price"])
        if entry is None or mp is None:
            continue
        fp = firsts.get(r["id"])
        sigs.append({
            "id": r["id"], "strategy": r["strategy"],
            "band": band(entry), "cat": category(r["slug"] or "", r["title"] or ""),
            "sk": super_event(r.get("event_slug"), r.get("slug")),
            "mean_price": mp, "entry": entry,
            "graded": r["graded"] == "1",
            "initial_market_price": _f(r["initial_market_price"]),
            "entry_ask": _f(r["entry_ask"]), "entry_ask_mid": _f(r["entry_ask_mid"]),
            "first": fp,
            # primary tax (None if no usable >=60s executable point -> EXCLUDED, not imputed)
            "tax": (fp["ask"] - mp) if fp else None,
        })
    return sigs


# ---- pure aggregation (self-testable, no DB) -------------------------------------------------
def _agg(vals):
    """[float] -> summary dict (mean/median/sd/n). SD = sample sd (n>=2), else None."""
    vals = [v for v in vals if v is not None]
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "sd": None}
    return {"n": n, "mean": mean(vals), "median": median(vals),
            "sd": (stdev(vals) if n >= 2 else None)}


def tax_cells(sigs, strat):
    """Per band x category and pooled tax for one strategy, + coverage vs graded."""
    used = [s for s in sigs if s["strategy"] == strat and s["tax"] is not None]
    graded = [s for s in sigs if s["strategy"] == strat and s["graded"]]

    def cell(subset_used, subset_graded, label):
        a = _agg([s["tax"] for s in subset_used])
        a["label"] = label
        a["n_graded"] = len(subset_graded)
        a["coverage"] = (len(subset_used) / len(subset_graded)) if subset_graded else None
        a["n_super_events"] = len({s["sk"] for s in subset_used})
        a["median_lag_s"] = (median([s["first"]["lag"] for s in subset_used])
                             if subset_used else None)
        # proxies on the SAME (usable) subset, for reconciliation
        a["proxy_capture_drift"] = _agg([s["initial_market_price"] - s["mean_price"]
                                         for s in subset_used
                                         if s["initial_market_price"] is not None])
        a["proxy_ask_haircut"] = _agg([s["entry_ask"] - s["entry_ask_mid"]
                                       for s in subset_used
                                       if s["entry_ask"] is not None
                                       and s["entry_ask_mid"] is not None])
        return a

    out = {"pooled": cell(used, graded, f"{strat} pooled")}
    for b in (4, 5):
        out[f"band{b}"] = cell([s for s in used if s["band"] == b],
                               [s for s in graded if s["band"] == b], f"{strat} band{b}")
    by_bc = {}
    keys = {(s["band"], s["cat"]) for s in used} | {(s["band"], s["cat"]) for s in graded}
    for b, c in sorted(keys):
        by_bc[f"band{b}|{c}"] = cell([s for s in used if s["band"] == b and s["cat"] == c],
                                     [s for s in graded if s["band"] == b and s["cat"] == c],
                                     f"{strat} band{b}|{c}")
    out["by_band_cat"] = by_bc
    return out


def matched_tax(fav_cells, band_label, cat):
    """Band-matched favorite tax for an H1/H2 positive cell; pool if the band x cat cell has N<5.
    Returns (tax_value, source_label)."""
    key = f"{band_label}|{cat}"
    c = fav_cells["by_band_cat"].get(key)
    if c and c["n"] >= POOL_FALLBACK_N and c["mean"] is not None:
        return c["mean"], f"cell:{key} (N={c['n']})"
    bc = fav_cells.get(band_label)
    if bc and bc["n"] >= POOL_FALLBACK_N and bc["mean"] is not None:
        return bc["mean"], f"band:{band_label} (N={bc['n']}; {key} had N<{POOL_FALLBACK_N})"
    p = fav_cells["pooled"]
    return p["mean"], f"pooled favorite (N={p['n']}; {key} & {band_label} below N floor)"


def realizable(fav_cells):
    """Task 2: subtract band-matched favorite tax from every H1/H2 positive LB. Pure arithmetic
    on the two result JSONs, clearly labeled. No new certification claim."""
    rv = _load("favconsensus_reverify.json")
    sb = _load("regime_cell_scoreboard.json")
    rows = []

    def add(name, band_label, cat, surplus, lb):
        if lb is None or lb <= 0:
            return
        tax, src = matched_tax(fav_cells, band_label, cat)
        rows.append({
            "positive": name, "band_for_tax": band_label, "cat_for_tax": cat,
            "surplus_ev": surplus, "lb_ev": lb,
            "matched_tax": tax, "tax_source": src,
            "surplus_minus_tax": (surplus - tax) if tax is not None else None,
            "realizable_lb_after_tax": (lb - tax) if tax is not None else None,
        })

    # H1.1 pooled favorite (bands 4+5) -> pooled favorite tax
    p = rv["H1_1_pooled"]
    add("H1.1 favorite pooled", "pooled", "*", p["surplus_ev"], p["lb_ev"])
    # H1.2 bands
    for b, c in rv["H1_2_bands"].items():
        add(f"H1.2 band{b}", f"band{b}", "*", c["surplus_ev"], c["lb_ev"])
    # H1 by category (pooled band within category -> match by category, band pooled)
    for cat, c in rv["by_category"].items():
        add(f"H1 cat:{cat}", "pooled", cat, c["surplus_ev"], c["lb_ev"])
    # H1 by block (pooled band) -> pooled favorite tax
    for blk, c in rv["by_block"].items():
        add(f"H1 block:{blk}", "pooled", "*", c["surplus_ev"], c["lb_ev"])
    # H2 counted regime cells
    for c in sb["cells"]:
        if not c.get("counted") or c.get("lb") is None or c["lb"] <= 0:
            continue
        cat = c["cell"].split("|")[0]
        bl = c["cell"].split("|")[1]      # 'band4' / 'band5'
        add(f"H2 {c['cell']}", bl, cat, c["surplus"], c["lb"])
    return rows


def directional(fav_cells, strict_cells):
    """Task 3: is tax larger at higher band, and in sharp (mlb) vs soft (soccer/esports)?"""
    def bmean(cells, bl):
        c = cells.get(bl)
        return (c["mean"], c["n"]) if c and c["mean"] is not None else (None, 0)

    fav4, fav5 = bmean(fav_cells, "band4"), bmean(fav_cells, "band5")
    st4, st5 = bmean(strict_cells, "band4"), bmean(strict_cells, "band5")

    def catmean(cells, cat):
        vals, n = [], 0
        for k, c in cells["by_band_cat"].items():
            if k.endswith("|" + cat) and c["mean"] is not None:
                vals += [c["mean"]] * c["n"]
                n += c["n"]
        return (mean(vals) if vals else None), n

    sports = {}
    for cat in ("mlb", "soccer", "esports", "tennis"):
        fm, fn = catmean(fav_cells, cat)
        sm, sn = catmean(strict_cells, cat)
        sports[cat] = {"favorite": {"mean": fm, "n": fn}, "strict": {"mean": sm, "n": sn}}
    return {"favorite_band4": {"mean": fav4[0], "n": fav4[1]},
            "favorite_band5": {"mean": fav5[0], "n": fav5[1]},
            "strict_band4": {"mean": st4[0], "n": st4[1]},
            "strict_band5": {"mean": st5[0], "n": st5[1]},
            "by_sport": sports}


def _load(name):
    with open(os.path.join(REPORT_DIR, name)) as f:
        return json.load(f)


def run_live():
    sigs = fetch()
    fav = tax_cells(sigs, "favorite")
    strict = tax_cells(sigs, "strict")
    res = {
        "prereg": "PREREG_20260706T000604Z_favconsensus_deepen.md",
        "measurement_only": True,
        "definition": "tax = first_executable_ask(secs_after_fire>=60) - at_fire_mean_price; "
                      "rows without a >=60s executable point EXCLUDED (no imputation); 2% fee NOT netted.",
        "follower_tax_proxy_ref": FOLLOWER_TAX_PROXY,
        "favorite": fav,
        "strict": strict,
        "realizable_after_tax": realizable(fav),
        "directional": directional(fav, strict),
    }
    with open(os.path.join(REPORT_DIR, "copy_tax.json"), "w") as f:
        json.dump(res, f, indent=2, default=str)
    _print(res)
    return res


def _c(x, d=4):
    return "  n/a " if x is None else f"{x:+.{d}f}"


def _pct(x):
    return " n/a" if x is None else f"{x:.1%}"


def _print(res):
    print("=" * 82)
    print("H5 COPYABILITY TAX (measurement) ·", res["definition"][:70])
    print("=" * 82)
    for strat in STRATEGIES:
        s = res[strat]
        p = s["pooled"]
        print(f"\n[{strat}]  pooled tax={_c(p['mean'])}  median={_c(p['median'])}  "
              f"sd={_c(p['sd'])}  N={p['n']}  cov={_pct(p['coverage'])}  "
              f"med_lag={p['median_lag_s']}s")
        for bl in ("band4", "band5"):
            c = s[bl]
            print(f"   {bl}: tax={_c(c['mean'])} sd={_c(c['sd'])} N={c['n']} "
                  f"cov={_pct(c['coverage'])} med_lag={c['median_lag_s']}s | "
                  f"drift={_c(c['proxy_capture_drift']['mean'])}(N{c['proxy_capture_drift']['n']}) "
                  f"haircut={_c(c['proxy_ask_haircut']['mean'])}(N{c['proxy_ask_haircut']['n']})")
    print("\n-- realizable LB after tax (H1/H2 positives) --")
    for r in res["realizable_after_tax"]:
        print(f"  {r['positive']:<22} lb={_c(r['lb_ev'])} - tax={_c(r['matched_tax'])} "
              f"= {_c(r['realizable_lb_after_tax'])}   [{r['tax_source']}]")
    d = res["directional"]
    print("\n-- directional --")
    print(f"  favorite band4={_c(d['favorite_band4']['mean'])}(N{d['favorite_band4']['n']}) "
          f"band5={_c(d['favorite_band5']['mean'])}(N{d['favorite_band5']['n']}) | "
          f"strict band4={_c(d['strict_band4']['mean'])} band5={_c(d['strict_band5']['mean'])}")
    for cat, v in d["by_sport"].items():
        print(f"  {cat:<8} favorite={_c(v['favorite']['mean'])}(N{v['favorite']['n']}) "
              f"strict={_c(v['strict']['mean'])}(N{v['strict']['n']})")
    print("=" * 82)


# ---- self-test (assert-based; no DB) ---------------------------------------------------------
def self_test():
    # Fixture: 3 favorite signals; one lacks a >=60s point (must be EXCLUDED, not imputed).
    sigs = [
        # band4 soccer, ask 0.68, mean 0.65 -> tax +0.03 ; lag 62
        {"id": "1", "strategy": "favorite", "band": 4, "cat": "soccer", "sk": "m1",
         "mean_price": 0.65, "entry": 0.65, "graded": True,
         "initial_market_price": 0.66, "entry_ask": 0.68, "entry_ask_mid": 0.665,
         "first": {"ask": 0.68, "mid": 0.67, "lag": 62}, "tax": 0.68 - 0.65},
        # band5 soccer, ask 0.92, mean 0.90 -> tax +0.02 ; lag 900
        {"id": "2", "strategy": "favorite", "band": 5, "cat": "soccer", "sk": "m2",
         "mean_price": 0.90, "entry": 0.90, "graded": True,
         "initial_market_price": 0.905, "entry_ask": 0.92, "entry_ask_mid": 0.905,
         "first": {"ask": 0.92, "mid": 0.91, "lag": 900}, "tax": 0.92 - 0.90},
        # band4 graded but NO >=60s point -> excluded from tax, counted in coverage denom
        {"id": "3", "strategy": "favorite", "band": 4, "cat": "soccer", "sk": "m3",
         "mean_price": 0.70, "entry": 0.70, "graded": True,
         "initial_market_price": None, "entry_ask": None, "entry_ask_mid": None,
         "first": None, "tax": None},
    ]
    fav = tax_cells(sigs, "favorite")

    # 1. exclusion + no imputation: pooled N=2 (id3 dropped), graded denom=3 -> coverage 2/3
    assert fav["pooled"]["n"] == 2, fav["pooled"]["n"]
    assert fav["pooled"]["n_graded"] == 3, fav["pooled"]
    assert abs(fav["pooled"]["coverage"] - 2 / 3) < 1e-9, fav["pooled"]["coverage"]

    # 2. tax arithmetic: mean of {+0.03, +0.02} = +0.025 ; band4 cell = +0.03 (only id1)
    assert abs(fav["pooled"]["mean"] - 0.025) < 1e-9, fav["pooled"]["mean"]
    assert abs(fav["band4"]["mean"] - 0.03) < 1e-9, fav["band4"]["mean"]
    assert fav["band4"]["n"] == 1 and fav["band5"]["n"] == 1

    # 3. median lag surfaced (not hidden): band5 cell median lag 900s
    assert fav["band5"]["median_lag_s"] == 900, fav["band5"]["median_lag_s"]

    # 4. proxies on same subset: band4 drift = 0.66-0.65 = +0.01 ; haircut = 0.68-0.665 = +0.015
    assert abs(fav["band4"]["proxy_capture_drift"]["mean"] - 0.01) < 1e-9
    assert abs(fav["band4"]["proxy_ask_haircut"]["mean"] - 0.015) < 1e-9

    # 5. matched_tax fallback: band4|mlb cell absent -> falls to pooled (band4 N=1 < 5)
    tax, src = matched_tax(fav, "band4", "mlb")
    assert abs(tax - 0.025) < 1e-9 and "pooled" in src, (tax, src)
    # band-match when cell rich enough
    rich = tax_cells([dict(s, id=str(100 + i)) for i in range(6)
                      for s in [sigs[0]]], "favorite")
    tax2, src2 = matched_tax(rich, "band4", "soccer")
    assert abs(tax2 - 0.03) < 1e-9 and src2.startswith("cell:"), (tax2, src2)

    # 6. realizable arithmetic: lb - tax, sign preserved
    r = {"positive": "x", "band_for_tax": "band4", "cat_for_tax": "soccer",
         "surplus_ev": 0.10, "lb_ev": 0.05, "matched_tax": 0.03}
    assert abs((r["lb_ev"] - r["matched_tax"]) - 0.02) < 1e-9

    # 7. band() parity with favconsensus_reverify scheme
    assert band(0.65) == 4 and band(0.90) == 5 and band(0.20) == 2 and band(1.0) == 5

    print("SELF-TEST PASS (exclusion/no-imputation, tax arithmetic, lag surfaced, "
          "proxy reconciliation, pooled fallback, realizable, band parity)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(self_test())
    run_live()


if __name__ == "__main__":
    main()
