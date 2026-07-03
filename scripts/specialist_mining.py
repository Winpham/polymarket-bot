#!/usr/bin/env python3
"""
PER-SPORT SPECIALIST MINING + COPYABILITY GATE
==============================================

Mission: stop tailing the GLOBAL PnL leaderboard blind (a lazy, lagging copycat that
loses edge to the follower tax). Instead mine, from the deep historical `trader_fills`
resolved-fill record, WHO is a real per-sport specialist, and certify them on
COPYABILITY -- surplus over the blind favorite at the price WE can actually get after
the follower tax -- not on their raw profitability.

This EXTENDS (does not relitigate) the congregation run's "per-sport specialist book
DEAD" verdict (DECISIONS D2), which certified on the 4-day FORWARD consensus record.
Two new axes here: (1) mine the far deeper historical trader_fills record on the
slug-parsed EVENT-DATE time axis (D1); (2) judge COPYABILITY at OUR price -- a question
the congregation run never asked.

Pipeline (all self-tested; --self-test runs the K1 battery on synthetic fixtures):
  Phase 1  raw per-(wallet x sport) surplus over sport x band cell-blind favorite,
           clustered at the MATCH super-key (superkey.super_event), with distinct-match
           N and distinct-event-DATE N (the honest independent-cluster count, the wall).
  Phase 2  the copyability transform: re-price at OUR realizable entry by subtracting
           the measured per-sport follower tax; report the copyability tax and how much
           of the raw edge survives it (kill criterion K2).
  Phase 3  mechanism classification: flag+exclude UNCOPYABLE profit -- two-sided /
           market-maker wallets, systematic price-improvement (liquidity provision).
           (In-play detection is CALENDAR/TIMESTAMP-blind on this archive: ts and
           resolved_at are backfill/crawl stamps, D1 -- reported as a limitation.)
  Phase 4  the belief-blind per-sport trust gate: the exact surplus_bounds / trust_verdict
           math (Bonferroni across the wallet's slices; lo > 3% capture margin;
           >=30-match floor), reported at BOTH the event-N SE and the DAY-DEFLATED SE
           (effective_n = clamp(n_dates,1,n_matches)) -- the accrual wall (D16-a/D17).
           Plus an inline selection-null and BH-FDR q=0.10 across the wallet x sport family.

Reuses: superkey.super_event (match clustering), the trader_slice_scores blind cascade
and surplus math (common/src/storage/consensus.rs), promotion.rs::surplus_bounds
(the Bonferroni lower-bound), selection_null.py's selection-null logic, slice_study.py's
BH-FDR. No migration, no env flip, no real money. Paper/analysis only.

Kill criteria (pre-registered):
  K1  self-test fails (injected copyable specialist -> Trusted; market-maker fixture ->
      excluded; coin-flip wallet -> not Trusted; noise family -> 0 FDR survivors;
      timing-only wallet -> NOT copyable) => STOP.
  K2  a wallet's edge is real at THEIR price but <=0 at OUR price => NOT copyable, exclude
      (report the tax that killed it).
  K3  the per-sport specialist follow-set does not beat blind global tailing forward =>
      specialist selection adds nothing here; report the null loudly (Phase 5, forward).
  K4  a sport's "top" wallets are dominated by market-makers / price-improvers => the
      sport's profit is structurally uncopyable -- a publishable finding, not a failure.

Usage:
  ./specialist_mining.py --self-test          # K1 battery on synthetic fixtures (no DB)
  ./specialist_mining.py                       # live mine from the DB (per-sport report)
  ./specialist_mining.py --floor 30            # override the certify floor (default 30)
"""
import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
from math import sqrt

# scipy is used by the sibling instruments (asof_preflight, selection_null); reuse it.
try:
    from scipy.stats import norm
    def probit(p):
        return float(norm.ppf(p))
except Exception:  # pragma: no cover - scipy is present in requirements.txt
    def probit(p):
        # Acklam approximation (matches promotion.rs::probit to <1e-4), fallback only.
        a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
             1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
        b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
             6.680131188771972e+01, -1.328068155288572e+01]
        c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
             -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
        d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
             3.754408661907416e+00]
        plow, phigh = 0.02425, 1 - 0.02425
        if p < plow:
            q = sqrt(-2 * math.log(p))
            return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                   ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        if p > phigh:
            q = sqrt(-2 * math.log(1 - p))
            return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                    ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from superkey import super_event  # noqa: E402  match-level clustering (self-tested)

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# --- the gate constants, mirrored from copy-trading-bot/src/scanner/promotion.rs ---
MARGIN = 0.03        # DEFAULT_PROMOTION_MARGIN (slippage 1% + fee 2%)
FLOOR = 30           # PromotionParams.min_events (the >=30 distinct-event trust floor)
ALPHA = 0.05         # promotion alpha (Bonferroni-split across the wallet's slices)
FDR_Q = 0.10         # BH-FDR q, matching slice_study.py
N_PERM = 2000        # selection-null draws, matching selection_null.py
SEED = 20260703
# The follower-tax floor: the truth audit (D16 F5) measured winners had already moved
# ~1.3c by our first observable mid. Sharp markets can eat 100% of a thin edge. We take
# max(measured_sport_tax, this floor) for the CONSERVATIVE copyability verdict, and also
# report the raw measured-tax (generous) reading, so the band is explicit.
TAX_FLOOR = 0.013


def psql(sql):
    out = subprocess.run(PG, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


# ---------------------------------------------------------------------------
# Phase 2 helper: measure the per-sport follower tax from consensus_signals.
# Tax = OUR realizable entry - the sharps' mean fill price, in price/share units.
# Surplus/share = won - entry, so a positive tax subtracts share-for-share from surplus.
# consensus_signals has no `sport` column -> derive a coarse sport from the event_slug.
# ---------------------------------------------------------------------------
TAX_SQL = r"""
WITH s AS (
  SELECT CASE
      WHEN event_slug LIKE 'fifwc%' OR event_slug LIKE 'soccer%'
           OR event_slug LIKE 'ucl%' OR event_slug LIKE 'uel%' THEN 'soccer'
      WHEN event_slug LIKE 'mlb%'  THEN 'mlb'
      WHEN event_slug LIKE 'atp%' OR event_slug LIKE 'wta%'
           OR event_slug LIKE 'tennis%' THEN 'tennis'
      WHEN event_slug LIKE 'nba%'  THEN 'nba'
      WHEN event_slug LIKE 'nfl%'  THEN 'nfl'
      WHEN event_slug LIKE 'lol%'  THEN 'lol'
      WHEN event_slug LIKE 'cs2%' OR event_slug LIKE 'csgo%' THEN 'cs2'
      ELSE 'other' END AS sport,
      mean_price, initial_market_price, entry_ask
  FROM consensus_signals
  WHERE is_sports = true AND mean_price IS NOT NULL
)
SELECT sport,
  count(*) FILTER (WHERE entry_ask IS NOT NULL)            AS n_ask,
  avg(entry_ask - mean_price) FILTER (WHERE entry_ask IS NOT NULL)              AS tax_ask,
  count(*) FILTER (WHERE initial_market_price IS NOT NULL) AS n_imp,
  avg(initial_market_price - mean_price) FILTER (WHERE initial_market_price IS NOT NULL) AS tax_imp
FROM s GROUP BY sport;
"""


def measure_tax():
    """Return {sport: (tax_measured, provenance)}. Prefer the executable-ask tax with
    n>=30; else the first-observed-mid tax with n>=30; else the global mean. All are
    measured on the forward consensus record (the only place we observe OUR entry next
    to a sharp fill), then applied to the historical fills as the best available proxy."""
    rows = psql(TAX_SQL)
    per, glob_num, glob_den = {}, 0.0, 0
    for r in rows:
        sp = r["sport"]
        n_ask = int(r["n_ask"] or 0)
        n_imp = int(r["n_imp"] or 0)
        t_ask = float(r["tax_ask"]) if r["tax_ask"] not in (None, "") else None
        t_imp = float(r["tax_imp"]) if r["tax_imp"] not in (None, "") else None
        if t_imp is not None:
            glob_num += t_imp * n_imp
            glob_den += n_imp
        if n_ask >= 30 and t_ask is not None:
            per[sp] = (t_ask, f"ask n={n_ask}")
        elif n_imp >= 30 and t_imp is not None:
            per[sp] = (t_imp, f"mid n={n_imp}")
    glob = (glob_num / glob_den) if glob_den else TAX_FLOOR
    per["__global__"] = (glob, f"global mid n={glob_den}")
    return per


def sport_tax(per, sport):
    return per.get(sport, per["__global__"])


# ---------------------------------------------------------------------------
# Phase 1: per-(wallet x sport x match) surplus over the sport x band cell-blind.
# Faithful to trader_slice_scores (favorite-residual cell-blind cascade, event-clustered)
# but clustered at the MATCH super-key (superkey) not event_slug -- the honest N
# (event_slug inflates N ~29%, truth-audit D16-E). Also carries the event-DATE.
# ---------------------------------------------------------------------------
MINE_SQL = r"""
WITH base AS (
  SELECT wallet,
         COALESCE(sport,'other') AS sport,
         width_bucket(price, 0.0, 1.0, 5) AS band,
         (outcome_won::int)::float8 - price AS a,
         (outcome_won::int)::float8 AS won,
         price,
         event_slug, slug,
         (regexp_match(event_slug, '(20[0-9]{2}-[0-9]{2}-[0-9]{2})'))[1] AS ev_date
  FROM trader_fills
  WHERE resolved AND side = 'BUY' AND outcome_won IS NOT NULL
),
blind_cell AS ( SELECT sport, band, AVG(a) AS be FROM base GROUP BY sport, band ),
blind_band AS ( SELECT band, AVG(a) AS be FROM base GROUP BY band ),
surp AS (
  SELECT b.wallet, b.sport, b.band, b.event_slug, b.slug, b.ev_date, b.price, b.won,
         b.a - COALESCE(bc.be, bb.be, 0) AS s
  FROM base b
  LEFT JOIN blind_cell bc USING (sport, band)
  LEFT JOIN blind_band bb USING (band)
)
SELECT wallet, sport, event_slug, slug, ev_date,
       AVG(s)     AS ev_surplus,
       AVG(won)   AS ev_won,
       AVG(price) AS ev_price,
       COUNT(*)   AS n_fills
FROM surp
GROUP BY wallet, sport, event_slug, slug, ev_date;
"""


def fetch_matches():
    """Return per-(wallet, sport) a list of match records. Clusters the raw
    (wallet,sport,event_slug) rows to the match super-key in Python (the canonical,
    self-tested super_event) so one match with N sub-markets counts once."""
    rows = psql(MINE_SQL)
    # collapse (event_slug, slug) -> match super-key, averaging surplus across sub-markets
    agg = {}  # (wallet,sport,mkey) -> dict
    for r in rows:
        w, sp = r["wallet"], r["sport"]
        mkey = super_event(r["event_slug"] or "", r["slug"] or "")
        nf = int(r["n_fills"])
        rec = agg.setdefault((w, sp, mkey), {"s": 0.0, "won": 0.0, "price": 0.0,
                                             "nf": 0, "date": r["ev_date"]})
        # weight sub-market averages by their fill count to recover the match mean
        rec["s"] += float(r["ev_surplus"]) * nf
        rec["won"] += float(r["ev_won"]) * nf
        rec["price"] += float(r["ev_price"]) * nf
        rec["nf"] += nf
        if r["ev_date"]:
            rec["date"] = r["ev_date"]
    cells = {}  # (wallet,sport) -> list of match dicts
    for (w, sp, mkey), rec in agg.items():
        nf = rec["nf"]
        cells.setdefault((w, sp), []).append({
            "mkey": mkey,
            "surplus": rec["s"] / nf,
            "won": rec["won"] / nf,
            "price": rec["price"] / nf,
            "date": rec["date"],
        })
    return cells


# ---------------------------------------------------------------------------
# Phase 3: mechanism classification (uncopyable profit sources).
# ---------------------------------------------------------------------------
MECH_SQL = r"""
WITH f AS (
  SELECT wallet, COALESCE(sport,'other') AS sport, condition_id, outcome_index, price
  FROM trader_fills
  WHERE resolved AND side = 'BUY' AND outcome_won IS NOT NULL
),
fleet AS ( SELECT condition_id, outcome_index, AVG(price) AS fleet_price
           FROM f GROUP BY condition_id, outcome_index ),
sided AS (
  SELECT wallet, sport, condition_id,
         COUNT(DISTINCT outcome_index) AS n_sides
  FROM f GROUP BY wallet, sport, condition_id
),
imp AS (
  SELECT f.wallet, f.sport, AVG(f.price - fl.fleet_price) AS price_improve, COUNT(*) AS nfill
  FROM f JOIN fleet fl USING (condition_id, outcome_index)
  GROUP BY f.wallet, f.sport
)
SELECT s.wallet, s.sport,
       COUNT(*)                                      AS n_conditions,
       COUNT(*) FILTER (WHERE s.n_sides >= 2)        AS n_twosided,
       i.price_improve
FROM sided s JOIN imp i USING (wallet, sport)
GROUP BY s.wallet, s.sport, i.price_improve;
"""


def fetch_mechanism():
    rows = psql(MECH_SQL)
    out = {}
    for r in rows:
        nc = int(r["n_conditions"])
        nts = int(r["n_twosided"])
        out[(r["wallet"], r["sport"])] = {
            "two_sided_frac": nts / nc if nc else 0.0,
            "price_improve": float(r["price_improve"]) if r["price_improve"] not in (None, "") else 0.0,
            "n_conditions": nc,
        }
    return out


def classify_mechanism(mech):
    """Return (excluded: bool, reason: str|None). Flags uncopyable profit sources."""
    if mech is None:
        return False, None
    # Two-sided / market-maker: holds both outcomes of the same market a lot.
    if mech["two_sided_frac"] >= 0.30:
        return True, f"market-maker (two-sided on {mech['two_sided_frac']:.0%} of markets)"
    # Systematic price-improvement: consistently fills BELOW the fleet mean price =>
    # they are providing liquidity (being taken from), not taking a directional read.
    if mech["price_improve"] <= -0.03:
        return True, f"price-improver (fills {mech['price_improve']*100:.1f}c below fleet mean)"
    return False, None


# ---------------------------------------------------------------------------
# Phase 4: the trust gate (surplus_bounds / trust_verdict math) + selection null + FDR.
# ---------------------------------------------------------------------------
def surplus_bounds(surplus, sd, eff_n, n_comp):
    """Mirror of promotion.rs::surplus_bounds. Returns (lo, hi)."""
    sd = max(sd if sd is not None else 0.0, 1e-9)
    alpha_corr = min(0.5, max(1e-6, ALPHA / max(1, n_comp)))
    z = probit(1 - alpha_corr)
    se = sd / sqrt(max(1, eff_n))
    return surplus - z * se, surplus + z * se


def cell_stats(matches):
    """Aggregate a (wallet x sport) match list to the certification statistics."""
    n = len(matches)
    ss = [m["surplus"] for m in matches]
    surplus = sum(ss) / n
    var = sum((x - surplus) ** 2 for x in ss) / (n - 1) if n > 1 else 0.0
    sd = sqrt(var)
    n_dates = len({m["date"] for m in matches if m["date"]})
    hit = sum(m["won"] for m in matches) / n
    price = sum(m["price"] for m in matches) / n
    return {"n_matches": n, "n_dates": n_dates or 1, "surplus": surplus,
            "sd": sd, "hit": hit, "mean_price": price}


def selection_null(matches, fleet_pool, rng_state):
    """Inline selection-null (mirrors selection_null.py's logic on the trader_fills pool).
    Is this wallet's MATCH selection distinguishable from random same-(band x date)-profile
    picks from the fleet's available matches? Returns p_emp (one-sided) or None if the pool
    is too thin. Deterministic LCG so no Date.now()/random-seed dependence."""
    # profile = the wallet's (band-of-price, date) multiset
    def band(p):
        return min(4, int(p * 5))
    profile = [(band(m["price"]), m["date"]) for m in matches]
    observed = sum(m["surplus"] for m in matches) / len(matches)
    # pool keyed by (band, date) -> list of fleet match surpluses available to pick
    from collections import defaultdict
    pool = defaultdict(list)
    for m in fleet_pool:
        pool[(band(m["price"]), m["date"])].append(m["surplus"])
    # if any profile cell is empty in the fleet pool, we cannot match -> skip
    if any(not pool.get(key) for key in profile):
        return None
    st = rng_state[0]
    def nxt():
        nonlocal st
        st = (1103515245 * st + 12345) & 0x7FFFFFFF
        return st / 0x7FFFFFFF
    ge = 0
    for _ in range(N_PERM):
        draw = 0.0
        for key in profile:
            choices = pool[key]
            draw += choices[int(nxt() * len(choices)) % len(choices)]
        draw /= len(profile)
        if draw >= observed:
            ge += 1
    rng_state[0] = st
    return (ge + 1) / (N_PERM + 1)


def bh_fdr(pvals, q=FDR_Q):
    """Benjamini-Hochberg. Return the set of indices that survive at level q."""
    m = len(pvals)
    if m == 0:
        return set()
    order = sorted(range(m), key=lambda i: pvals[i])
    survivors, kmax = set(), -1
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            kmax = rank
    for rank, i in enumerate(order, start=1):
        if rank <= kmax:
            survivors.add(i)
    return survivors


# ---------------------------------------------------------------------------
# The mining run (Phases 1-4 composed).
# ---------------------------------------------------------------------------
def mine(floor=FLOOR, readout=15):
    tax_map = measure_tax()
    cells = fetch_matches()
    mech = fetch_mechanism()

    # fleet pool per sport for the selection null (all matches, any wallet)
    fleet_by_sport = {}
    for (w, sp), matches in cells.items():
        fleet_by_sport.setdefault(sp, []).extend(matches)

    # per-wallet Bonferroni denominator = count of that wallet's sport-cells with data
    wallet_slice_count = {}
    for (w, sp) in cells:
        wallet_slice_count[w] = wallet_slice_count.get(w, 0) + 1

    records = []
    for (w, sp), matches in cells.items():
        st = cell_stats(matches)
        if st["n_matches"] < readout:
            continue
        tax, tax_prov = sport_tax(tax_map, sp)
        tax_cons = max(tax, TAX_FLOOR)                # conservative copyability tax
        our_surplus_meas = st["surplus"] - max(0.0, tax)     # generous (raw measured tax)
        our_surplus_cons = st["surplus"] - tax_cons          # conservative (floored tax)
        n_comp = max(1, wallet_slice_count[w])
        eff_n = min(max(1, st["n_dates"]), st["n_matches"])  # day-deflated effective N

        # trust bounds at THEIR price, and at OUR price, both SE conventions
        lo_their_evn, _ = surplus_bounds(st["surplus"], st["sd"], st["n_matches"], n_comp)
        lo_their_day, _ = surplus_bounds(st["surplus"], st["sd"], eff_n, n_comp)
        lo_our_evn, _ = surplus_bounds(our_surplus_cons, st["sd"], st["n_matches"], n_comp)
        lo_our_day, _ = surplus_bounds(our_surplus_cons, st["sd"], eff_n, n_comp)

        excluded, reason = classify_mechanism(mech.get((w, sp)))

        rec = {
            "wallet": w, "sport": sp,
            "n_matches": st["n_matches"], "n_dates": st["n_dates"], "eff_n": eff_n,
            "hit": st["hit"], "mean_price": st["mean_price"],
            "surplus_their": st["surplus"], "sd": st["sd"],
            "tax": tax, "tax_prov": tax_prov, "tax_cons": tax_cons,
            "our_surplus_meas": our_surplus_meas, "our_surplus_cons": our_surplus_cons,
            "surviving_frac": (our_surplus_cons / st["surplus"]) if st["surplus"] > 0 else 0.0,
            "lo_their_evn": lo_their_evn, "lo_their_day": lo_their_day,
            "lo_our_evn": lo_our_evn, "lo_our_day": lo_our_day,
            "n_comp": n_comp,
            "excluded": excluded, "exclude_reason": reason,
            "two_sided_frac": mech.get((w, sp), {}).get("two_sided_frac", 0.0),
            "price_improve": mech.get((w, sp), {}).get("price_improve", 0.0),
            # copyability kill K2: real at their price, dead at ours
            "k2_dies_at_our_price": st["surplus"] > 0 and our_surplus_cons <= 0,
            # gate verdicts (belief-blind), at OUR price, both SE conventions
            "trusted_our_evn": (st["n_matches"] >= floor and lo_our_evn > MARGIN and not excluded),
            "trusted_our_day": (st["n_matches"] >= floor and lo_our_day > MARGIN and not excluded),
        }
        records.append(rec)

    # selection null + BH-FDR across the certifiable family: cells that clear the floor,
    # are not mechanism-excluded, and have a POSITIVE our-price point surplus (the only
    # cells that could possibly certify). Everything else cannot pass regardless.
    rng_state = [SEED]
    cand = [r for r in records if r["n_matches"] >= floor and not r["excluded"]
            and r["our_surplus_cons"] > 0]
    pvals, pidx = [], []
    for i, r in enumerate(records):
        if r in cand:
            p = selection_null(cells[(r["wallet"], r["sport"])],
                               fleet_by_sport[r["sport"]], rng_state)
            r["sel_null_p"] = p
            if p is not None:
                pvals.append(p)
                pidx.append(i)
        else:
            r["sel_null_p"] = None
    survivors = bh_fdr(pvals) if pvals else set()
    surv_records = {pidx[j] for j in survivors}
    for i, r in enumerate(records):
        r["fdr_survives"] = i in surv_records

    return records, tax_map


# ---------------------------------------------------------------------------
# Reporting.
# ---------------------------------------------------------------------------
def fmt_pct(x):
    return f"{x*100:+.1f}%" if x is not None else "  n/a"


def report(records, tax_map, floor):
    by_sport = {}
    for r in records:
        by_sport.setdefault(r["sport"], []).append(r)

    print("\n================ PER-SPORT SPECIALIST MINING + COPYABILITY GATE ================\n")
    print("Measured per-sport follower tax (OUR entry - sharps' fill, from consensus_signals):")
    for sp in sorted(tax_map):
        if sp == "__global__":
            continue
        t, prov = tax_map[sp]
        print(f"  {sp:10s}  tax = {t*100:+.2f}c   ({prov})   conservative floor = {max(t,TAX_FLOOR)*100:.2f}c")
    gt, gprov = tax_map["__global__"]
    print(f"  {'GLOBAL':10s}  tax = {gt*100:+.2f}c   ({gprov})   [fallback + floor]\n")

    # -- headline honest counts (the null-first framing) --
    fam = [r for r in records if r["n_matches"] >= floor]
    cert_day = [r for r in fam if r["trusted_our_day"] and r["fdr_survives"]]
    cert_evn = [r for r in fam if r["trusted_our_evn"] and r["fdr_survives"]]
    k2 = [r for r in fam if r["k2_dies_at_our_price"]]
    excl = [r for r in fam if r["excluded"]]
    print(f"FAMILY: {len(fam)} (wallet x sport) cells clear the >={floor}-match floor "
          f"across {len(by_sport)} sports.\n")
    print(f"  CERTIFIED copyable specialists @ OUR price, DAY-deflated SE (the real bar): "
          f"{len(cert_day)}")
    print(f"  CERTIFIED @ OUR price, event-N SE (generous, no accrual penalty):           "
          f"{len(cert_evn)}")
    print(f"  K2 -- real edge @ THEIR price but DEAD @ OUR price (copyability tax killed): "
          f"{len(k2)}")
    print(f"  Mechanism-EXCLUDED (market-maker / price-improver, uncopyable):              "
          f"{len(excl)}\n")

    # -- per-sport tables --
    for sp in sorted(by_sport, key=lambda s: -len([r for r in by_sport[s] if r["n_matches"] >= floor])):
        rs = [r for r in by_sport[sp] if r["n_matches"] >= floor]
        if not rs:
            continue
        rs.sort(key=lambda r: -r["lo_our_day"])
        print(f"--- {sp.upper()}  ({len(rs)} cells >= {floor} matches; "
              f"tax={sport_tax(tax_map, sp)[0]*100:+.2f}c) ---")
        print(f"  {'wallet':14s} {'mtch':>4s} {'dts':>3s} {'hit':>5s} "
              f"{'surp@them':>9s} {'surp@us':>8s} {'surv':>5s} "
              f"{'LB@us,evN':>9s} {'LB@us,day':>9s} {'selnull':>7s}  flags")
        for r in rs:
            flags = []
            if r["excluded"]:
                flags.append("EXCL:" + (r["exclude_reason"] or ""))
            if r["k2_dies_at_our_price"]:
                flags.append("K2-dead@our")
            if r["trusted_our_day"] and r["fdr_survives"]:
                flags.append("**CERTIFIED**")
            elif r["trusted_our_evn"]:
                flags.append("cert@evN-only")
            wshort = r["wallet"][:12] + ".." if len(r["wallet"]) > 14 else r["wallet"]
            selp = f"{r['sel_null_p']:.3f}" if r["sel_null_p"] is not None else "  -  "
            print(f"  {wshort:14s} {r['n_matches']:4d} {r['n_dates']:3d} "
                  f"{r['hit']*100:4.0f}% {fmt_pct(r['surplus_their']):>9s} "
                  f"{fmt_pct(r['our_surplus_cons']):>8s} "
                  f"{r['surviving_frac']*100:4.0f}% "
                  f"{fmt_pct(r['lo_our_evn']):>9s} {fmt_pct(r['lo_our_day']):>9s} "
                  f"{selp:>7s}  {'; '.join(flags)}")
        print()

    return {"family": len(fam), "certified_day": len(cert_day),
            "certified_evn": len(cert_evn), "k2_dead": len(k2), "excluded": len(excl),
            "sports": {sp: len([r for r in by_sport[sp] if r["n_matches"] >= floor])
                       for sp in by_sport}}


# ---------------------------------------------------------------------------
# K1 self-test battery (synthetic fixtures, no DB).
# ---------------------------------------------------------------------------
def _synth_matches(n, mean, sd, n_dates, seed, base_price=0.7):
    """Build a synthetic (wallet x sport) match list with a target surplus mean/sd."""
    st = seed
    def nxt():
        nonlocal st
        st = (1103515245 * st + 12345) & 0x7FFFFFFF
        return st / 0x7FFFFFFF
    out = []
    for i in range(n):
        # box-muller-ish: sum of two uniforms centered, scaled to sd
        z = (nxt() + nxt() + nxt() + nxt() + nxt() + nxt() - 3.0) / 1.0  # ~N(0, ~0.5)
        surplus = mean + sd * z
        out.append({"mkey": f"m{seed}-{i}", "surplus": surplus,
                    "won": 1.0 if surplus + base_price > 0.6 else 0.0,
                    "price": base_price,
                    "date": f"2026-05-{(i % n_dates) + 1:02d}"})
    return out


def self_test():
    print("=== K1 self-test battery (synthetic fixtures) ===\n")
    ok = True

    # helper to gate one synthetic cell at OUR price (conservative tax), day-deflated
    def gate(matches, tax, n_comp=1, floor=FLOOR):
        st = cell_stats(matches)
        our = st["surplus"] - max(tax, TAX_FLOOR)
        eff = min(max(1, st["n_dates"]), st["n_matches"])
        lo_day, _ = surplus_bounds(our, st["sd"], eff, n_comp)
        lo_evn, _ = surplus_bounds(our, st["sd"], st["n_matches"], n_comp)
        return st, our, lo_day, lo_evn

    # 1. Injected COPYABLE specialist: large low-variance edge, well spread across dates,
    #    survives the tax -> must be Trusted at OUR price at BOTH SE conventions.
    spec = _synth_matches(60, mean=0.14, sd=0.05, n_dates=40, seed=101)
    st, our, lo_day, lo_evn = gate(spec, tax=0.013)
    passed = st["n_matches"] >= FLOOR and lo_day > MARGIN and lo_evn > MARGIN and our > 0
    print(f"  [1] injected copyable specialist -> Trusted@our: "
          f"n={st['n_matches']} surp@them={st['surplus']:+.3f} surp@us={our:+.3f} "
          f"lo_day={lo_day:+.3f} lo_evn={lo_evn:+.3f}  {'PASS' if passed else 'FAIL'}")
    ok &= passed

    # 2. Coin-flip wallet: ~zero edge -> must NOT be Trusted.
    flip = _synth_matches(60, mean=0.0, sd=0.08, n_dates=40, seed=202)
    st, our, lo_day, lo_evn = gate(flip, tax=0.013)
    passed = not (lo_day > MARGIN)
    print(f"  [2] coin-flip wallet -> NOT Trusted: "
          f"surp@them={st['surplus']:+.3f} lo_day={lo_day:+.3f}  "
          f"{'PASS' if passed else 'FAIL'}")
    ok &= passed

    # 3. Timing-only specialist: real edge @ their price, KILLED by a big tax (K2).
    timing = _synth_matches(60, mean=0.05, sd=0.04, n_dates=40, seed=303)
    st, our, lo_day, lo_evn = gate(timing, tax=0.06)  # 6c tax eats the 5c edge
    k2 = st["surplus"] > 0 and our <= 0
    print(f"  [3] timing-only wallet -> K2 dead@our: "
          f"surp@them={st['surplus']:+.3f} surp@us={our:+.3f}  "
          f"{'PASS' if k2 else 'FAIL'}")
    ok &= k2

    # 4. Market-maker fixture: two-sided on most markets -> mechanism-EXCLUDED.
    mm = {"two_sided_frac": 0.62, "price_improve": -0.001, "n_conditions": 80}
    excl, reason = classify_mechanism(mm)
    print(f"  [4] market-maker fixture -> excluded: {excl} ({reason})  "
          f"{'PASS' if excl else 'FAIL'}")
    ok &= excl

    # 4b. Price-improver fixture: fills well below fleet mean -> excluded.
    pimp = {"two_sided_frac": 0.05, "price_improve": -0.05, "n_conditions": 80}
    excl2, reason2 = classify_mechanism(pimp)
    print(f"  [4b] price-improver fixture -> excluded: {excl2} ({reason2})  "
          f"{'PASS' if excl2 else 'FAIL'}")
    ok &= excl2

    # 4c. A genuine directional predictor is NOT excluded.
    dpred = {"two_sided_frac": 0.02, "price_improve": +0.005, "n_conditions": 80}
    excl3, _ = classify_mechanism(dpred)
    print(f"  [4c] directional predictor -> NOT excluded: {not excl3}  "
          f"{'PASS' if not excl3 else 'FAIL'}")
    ok &= (not excl3)

    # 5. Noise family: many coin-flip wallets -> 0 BH-FDR survivors on their sel-null p.
    #    Build a fleet pool + a family of random wallets, all null; check FDR yields 0.
    fleet = []
    for s in range(30):
        fleet.extend(_synth_matches(40, mean=0.0, sd=0.08, n_dates=20, seed=1000 + s))
    rng = [SEED]
    ps = []
    for s in range(20):
        wm = _synth_matches(35, mean=0.0, sd=0.08, n_dates=20, seed=5000 + s)
        p = selection_null(wm, fleet, rng)
        if p is not None:
            ps.append(p)
    surv = bh_fdr(ps) if ps else set()
    passed = len(surv) == 0
    print(f"  [5] noise family ({len(ps)} null wallets) -> 0 FDR survivors: "
          f"got {len(surv)}  {'PASS' if passed else 'FAIL'}")
    ok &= passed

    # 6. selection-null recovers an injected match-selection edge (calibration sanity):
    #    a wallet that picks only the best fleet matches should get a small p.
    good_fleet = []
    for s in range(30):
        good_fleet.extend(_synth_matches(40, mean=0.0, sd=0.06, n_dates=20, seed=7000 + s))
    # wallet picks high-surplus matches from the same (band,date) profile
    picks = sorted(good_fleet, key=lambda m: -m["surplus"])[:35]
    p_good = selection_null(picks, good_fleet, [SEED])
    passed = p_good is not None and p_good < 0.05
    print(f"  [6] selection-null recovers a selection edge: p={p_good}  "
          f"{'PASS' if passed else 'FAIL'}")
    ok &= passed

    print(f"\n=== SELF-TEST {'PASS' if ok else 'FAIL'} ===")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true", help="run the K1 battery (no DB)")
    ap.add_argument("--floor", type=int, default=FLOOR, help="certify floor (distinct matches)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable summary")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    records, tax_map = mine(floor=args.floor)
    summary = report(records, tax_map, args.floor)
    if args.json:
        print("\nJSON_SUMMARY " + json.dumps(summary))


if __name__ == "__main__":
    main()
