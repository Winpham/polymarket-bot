#!/usr/bin/env python3
"""
H3 — ROUTING ENRICHMENTS (PREREG_20260706T000604Z_favconsensus_deepen.md §3.H3).

Three pre-registered, frozen-threshold tests on the historical trader_fills mine, all judged at
OUR repriced follower entry and with the UNION MM-exclusion ON for every follow-set. This is a
thin extension of the deployed scorecard machinery — it REUSES:

  - trader_scorecard.py : reprice()/FEE/FOLLOWER_TAX/band spreads, the frozen membership
      procedure members() (n_fills>=100, n_days>=15, copy_return>=+10%), the microstructure MM
      screen is_mm(), fetch_micro(), and clustered() (per-wallet event-clustered copy-return).
  - the UNION MM-exclusion exactly as router_verify.py defines it: is_mm(microstructure) OR
      followed_traders.trader_type='bot'.  members(scored, micro, bots) applies both.
  - superkey.super_event() : THE cluster key (match-level), never event_slug, never rows.
  - market_taxonomy.category() : the sport-category label.

Repriced entry convention (mirrors trader_scorecard.py exactly — NOT the +0.7c fallback):
    our_entry = price + FOLLOWER_TAX(0.013) + band_spread(band);  ret = (won - e)/e - FEE(0.02).

THE THREE TESTS (all H1->H2, split by TIME at the midpoint of event time, WHOLE super-events):
  1. Regime-conditional scorecard: per-sport-category follow-sets vs one global follow-set, both
     built on H1 with the SAME frozen procedure; compare forward H2 copy-return (b vs a).
  2. Conviction weighting: global follow-set, forward H2 read restricted to fills >=$1000 vs all.
  3. Survivorship correction (measurement, no cert): forward H2 with vs without the
     CAPTURE_DROPPED-recovered fills (a dropped wallet's post-last_seen_on_lb fills). Bias
     direction + magnitude only.

DATA-QUALITY NOTE (surfaced, not silently handled): trader_fills.resolved_at is only populated
over the last ~7 days (recent backfill) — it collapses the whole year into one week and is
UNUSABLE as the year-long event clock. The prereg asks to split at "the midpoint of resolved-event
time"; the honest available proxy is per-super_event MAX(ts) (last fill ~ match time). The split
stays whole-super-event, so it is leak-free regardless of the clock proxy.

Frozen: seed 20260706 (bootstrap SE), Bonferroni divisor k=3, $1000 conviction threshold, band
[0.45, 0.90), 365d window. No fitted learners, no threshold tuning.

  ./routing_enrich.py            # live read; writes reports/routing_enrich.json
  ./routing_enrich.py --self-test   # synthetic fixtures, assert-based, no DB; exit!=0 on failure
"""

import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc          # reprice/FEE/members/is_mm/clustered/fetch_micro/...
import superkey                          # super_event() cluster key
import market_taxonomy as mtax           # category()

SEED = 20260706
N_BOOT = 2000
K_FAMILY = 3                             # Bonferroni divisor (H3 family size = 3, frozen)
CONVICTION_USD = 1000.0                  # frozen $1k conviction threshold
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "routing_enrich.json")

try:
    from scipy.stats import norm
    _Z_BONF = float(norm.ppf(1.0 - 0.05 / K_FAMILY))   # one-sided 95%/k ~ 2.128
except Exception:                                       # pragma: no cover
    _Z_BONF = 2.1280344      # frozen fallback = norm.ppf(1 - 0.05/3)


# ---------------------------------------------------------------- data shaping
def fetch_rows():
    """One row per resolved band BUY fill, with the reprice inputs, super-key inputs, the
    sport-category inputs, size, and the CAPTURE_DROPPED 'recovered' flag (a fill by a wallet
    that has dropped off the leaderboard, after last_seen_on_lb+1d — the survivorship rows)."""
    return tsc.q(f"""
      SELECT lower(f.wallet) AS wallet, f.event_slug, f.slug, f.title,
             EXTRACT(EPOCH FROM f.ts) AS ts, (f.ts AT TIME ZONE 'UTC')::date AS day,
             f.price, f.outcome_won::int AS won, COALESCE(f.size_usd, 0) AS size_usd,
             (t.active IS NOT TRUE AND t.last_seen_on_lb IS NOT NULL
              AND f.ts > t.last_seen_on_lb + INTERVAL '1 day')::int AS recovered
      FROM trader_fills f
      LEFT JOIN followed_traders t ON lower(t.proxy_wallet) = f.wallet
      WHERE f.side = 'BUY' AND f.resolved AND f.outcome_won IS NOT NULL
        AND f.price >= {tsc.BAND_LO} AND f.price < {tsc.BAND_HI}
        AND f.ts >= NOW() - INTERVAL '{tsc.WINDOW_DAYS} days'""")


def fetch_bots():
    rows = tsc.q("SELECT lower(proxy_wallet) AS wallet, trader_type FROM followed_traders")
    return {r["wallet"]: r["trader_type"] for r in rows}


def shape(rows):
    """Annotate each row with super_event ('ev'), sport-category ('cat'), floats. Rows missing a
    super-key (no slug AND no event_slug) fall back to condition-free 'ev' = wallet+idx? no — drop
    them (can't cluster); reported as a data-quality count."""
    out, dropped = [], 0
    for i, r in enumerate(rows):
        se = superkey.super_event(r.get("event_slug"), r.get("slug"))
        if not se:
            dropped += 1
            continue
        out.append({
            "wallet": r["wallet"], "ev": se, "day": r["day"],
            "ts": float(r["ts"]), "price": float(r["price"]), "won": int(r["won"]),
            "size_usd": float(r["size_usd"]), "recovered": int(r["recovered"]),
            "cat": mtax.category(r.get("slug"), r.get("title")),
        })
    return out, dropped


def time_split(rows):
    """WHOLE-super-event split into equal H1/H2 HALVES at the MEDIAN event time (the prereg's
    "midpoint of resolved-event time" = the time with half the super-events on each side — NOT the
    range midpoint, which the recency-skewed activity would make wildly unbalanced). Event time of
    a super_event = MAX(ts) of its fills (resolved_at is degenerate; last-fill time is the honest
    proxy). Ties broken by super_event key for determinism. Returns (h1_rows, h2_rows, meta)."""
    ev_time = {}
    for r in rows:
        ev_time[r["ev"]] = max(ev_time.get(r["ev"], -math.inf), r["ts"])
    if not ev_time:
        return [], [], {"midpoint": None, "n_events": 0}
    order = sorted(ev_time, key=lambda e: (ev_time[e], e))     # oldest first, deterministic ties
    cut = len(order) // 2
    h1_ev = set(order[:cut])
    mid = ev_time[order[cut]] if cut < len(order) else ev_time[order[-1]]
    h1 = [r for r in rows if r["ev"] in h1_ev]
    h2 = [r for r in rows if r["ev"] not in h1_ev]
    return h1, h2, {"midpoint": mid, "n_events": len(ev_time),
                    "n_events_h1": len(h1_ev), "n_events_h2": len(ev_time) - len(h1_ev)}


# ---------------------------------------------------------------- follow-set + forward read
def union_mm(micro, bots):
    """Predicate: is wallet an MM under the UNION detector (microstructure OR trader_type='bot')."""
    def f(w):
        return tsc.is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0})) or bots.get(w) == "bot"
    return f


def followset(rows, spreads, micro, bots):
    """Frozen scorecard membership on `rows` (event-clustered by super_event via tsc.clustered,
    UNION-MM excluded via tsc.members). Returns the sorted member wallet list."""
    scored = tsc.clustered(rows, spreads)          # ev == super_event  => super-event clustering
    return tsc.members(scored, micro, bots)         # applies is_mm(micro) AND bots!='bot' + floors


def forward_per_event(rows, keep):
    """Pool the forward fills the predicate `keep(row)` selects, dedup to one obs per super_event
    (mean of that event's per-fill repriced returns across the follow-set), event-clustered.
    Returns {super_event: (day, ret)}.  Empty if nothing kept."""
    ev = defaultdict(list)
    ev_day = {}
    for r in rows:
        if not keep(r):
            continue
        e = r["price"] + tsc.FOLLOWER_TAX + _spread_of(r["price"])
        ev[r["ev"]].append((r["won"] - e) / e - tsc.FEE)
        ev_day[r["ev"]] = r["day"]
    return {se: (ev_day[se], sum(v) / len(v)) for se, v in ev.items()}


_SPREADS = {}     # set once in run(); reprice mirrors tsc.reprice(price, _SPREADS)


def _spread_of(price):
    return _SPREADS.get(tsc.band(price), 0.0)


def cr(per_ev):
    """Copy-return = mean over super-events (one obs per event). None if empty."""
    if not per_ev:
        return None
    vals = [v[1] for v in per_ev.values()]
    return sum(vals) / len(vals)


def ndays(per_ev):
    return len({v[0] for v in per_ev.values()})


def bootstrap_diff(per_a, per_b, seed=SEED, n_boot=N_BOOT):
    """Cluster-robust SE of D = cr(b) - cr(a) by resampling WHOLE super-events (the cluster) with
    replacement — captures the paired overlap between the two arms' event sets automatically.
    Returns (point_D, se, bonf_lb). Bonferroni(3) one-sided LB = D - z_{1-.05/3} * se."""
    ca, cb = cr(per_a), cr(per_b)
    if ca is None or cb is None:
        return (None, None, None)
    D = cb - ca
    universe = sorted(set(per_a) | set(per_b))
    n = len(universe)
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        draw = [universe[rng.randrange(n)] for _ in range(n)]
        a_vals = [per_a[e][1] for e in draw if e in per_a]
        b_vals = [per_b[e][1] for e in draw if e in per_b]
        if not a_vals or not b_vals:
            continue
        diffs.append((sum(b_vals) / len(b_vals)) - (sum(a_vals) / len(a_vals)))
    if len(diffs) < 2:
        return (D, None, None)
    m = sum(diffs) / len(diffs)
    se = math.sqrt(sum((x - m) ** 2 for x in diffs) / (len(diffs) - 1))
    return (D, se, D - _Z_BONF * se)


def verdict(D, se, lb):
    """positive: Bonferroni(3) LB > 0 (per-sport / conviction robustly beats baseline).
    negative: Bonferroni(3) UPPER bound < 0 (robustly WORSE, sign not a power artifact).
    else indeterminate-by-power (the CI straddles 0 — the frozen power gate, >=30 super-events,
    is what fails; the difference cannot be distinguished from noise)."""
    if D is None:
        return "no-data"
    if lb is not None and lb > 0:
        return "positive (Bonf3 LB>0)"
    if se is not None and (D + _Z_BONF * se) < 0:
        return "negative (Bonf3 UB<0)"
    return "indeterminate-by-power (CI straddles 0)"


# ---------------------------------------------------------------- the three tests
def test1_regime_scorecard(h1, h2, spreads, micro, bots):
    """Per-sport follow-sets (b) vs global follow-set (a); forward H2 copy-return, b - a."""
    g_fs = set(followset(h1, spreads, micro, bots))                 # (a) global
    cats = sorted({r["cat"] for r in h1})
    per_sport = {}                                                  # cat -> member set
    qualified_pairs = set()                                         # (wallet, cat) for (b)
    for c in cats:
        h1c = [r for r in h1 if r["cat"] == c]
        fsc = followset(h1c, spreads, micro, bots)
        if fsc:
            per_sport[c] = sorted(fsc)
            for w in fsc:
                qualified_pairs.add((w, c))
    a_ev = forward_per_event(h2, lambda r: r["wallet"] in g_fs)
    b_ev = forward_per_event(h2, lambda r: (r["wallet"], r["cat"]) in qualified_pairs)
    D, se, lb = bootstrap_diff(a_ev, b_ev)
    return {
        "global_followset_n": len(g_fs), "global_followset": sorted(g_fs),
        "per_sport_followset_n": len({w for w, _ in qualified_pairs}),
        "per_sport_followsets": per_sport,
        "forward_copy_return_global_a": cr(a_ev), "forward_copy_return_persport_b": cr(b_ev),
        "difference_b_minus_a": D, "cluster_robust_se": se, "bonferroni3_lb": lb,
        "n_events_a": len(a_ev), "n_events_b": len(b_ev),
        "n_days_a": ndays(a_ev), "n_days_b": ndays(b_ev),
        "verdict": verdict(D, se, lb),
    }


def test2_conviction(h1, h2, spreads, micro, bots):
    """Global follow-set; forward H2 read restricted to fills >=$1k (b) vs all (a); b - a."""
    g_fs = set(followset(h1, spreads, micro, bots))
    a_ev = forward_per_event(h2, lambda r: r["wallet"] in g_fs)
    b_ev = forward_per_event(h2, lambda r: r["wallet"] in g_fs and r["size_usd"] >= CONVICTION_USD)
    D, se, lb = bootstrap_diff(a_ev, b_ev)
    return {
        "global_followset_n": len(g_fs),
        "forward_copy_return_all_a": cr(a_ev),
        "forward_copy_return_ge1k_b": cr(b_ev),
        "difference_b_minus_a": D, "cluster_robust_se": se, "bonferroni3_lb": lb,
        "conviction_usd": CONVICTION_USD,
        "n_events_a": len(a_ev), "n_events_b": len(b_ev),
        "n_days_a": ndays(a_ev), "n_days_b": ndays(b_ev),
        "verdict": verdict(D, se, lb),
    }


def test3_survivorship(h1, h2, spreads, micro, bots):
    """Global follow-set; forward H2 WITH (all) vs WITHOUT (censor recovered/post-drop) fills.
    Measurement only: bias = cr(with) - cr(without), direction + magnitude."""
    g_fs = set(followset(h1, spreads, micro, bots))
    with_ev = forward_per_event(h2, lambda r: r["wallet"] in g_fs)
    without_ev = forward_per_event(h2, lambda r: r["wallet"] in g_fs and not r["recovered"])
    cw, cwo = cr(with_ev), cr(without_ev)
    bias = (cw - cwo) if (cw is not None and cwo is not None) else None
    n_recovered = sum(1 for r in h2 if r["wallet"] in g_fs and r["recovered"])
    recov_wallets = sorted({r["wallet"] for r in h2 if r["wallet"] in g_fs and r["recovered"]})
    return {
        "global_followset_n": len(g_fs),
        "forward_copy_return_with_recovered": cw,
        "forward_copy_return_without_recovered": cwo,
        "bias_with_minus_without": bias,
        "bias_direction": (None if bias is None else
                           ("upward: recovered fills raise the forward read" if bias > 0 else
                            "downward: recovered fills lower the forward read" if bias < 0 else
                            "none")),
        "n_recovered_fills_in_followset_h2": n_recovered,
        "n_recovered_wallets_in_followset": len(recov_wallets),
        "n_events_with": len(with_ev), "n_events_without": len(without_ev),
        "note": "measurement only, no certification (prereg H3.3)",
    }


# ---------------------------------------------------------------- live run
def run():
    global _SPREADS
    spreads = tsc.fetch_band_spreads()
    _SPREADS = spreads
    micro = tsc.fetch_micro()
    bots = fetch_bots()
    raw = fetch_rows()
    rows, dropped = shape(raw)
    h1, h2, split_meta = time_split(rows)

    t1 = test1_regime_scorecard(h1, h2, spreads, micro, bots)
    t2 = test2_conviction(h1, h2, spreads, micro, bots)
    t3 = test3_survivorship(h1, h2, spreads, micro, bots)

    out = {
        "meta": {
            "prereg": "PREREG_20260706T000604Z_favconsensus_deepen.md#H3",
            "seed": SEED, "n_boot": N_BOOT, "bonferroni_k": K_FAMILY, "z_bonferroni": _Z_BONF,
            "fee": tsc.FEE, "follower_tax": tsc.FOLLOWER_TAX, "band": [tsc.BAND_LO, tsc.BAND_HI],
            "window_days": tsc.WINDOW_DAYS, "conviction_usd": CONVICTION_USD,
            "membership": {"min_fills": tsc.MIN_FILLS, "min_days": tsc.MIN_DAYS,
                           "min_return": tsc.MIN_RETURN},
            "mm_exclusion": "UNION(microstructure is_mm, followed_traders.trader_type='bot')",
            "cluster_key": "superkey.super_event (match-level)",
            "sport_category": "market_taxonomy.category(slug,title)",
            "reprice": "price + follower_tax + band_spread; ret=(won-e)/e - fee "
                       "(mirrors trader_scorecard.py)",
            "event_clock": "per-super_event MAX(ts) (resolved_at degenerate: only last ~7d "
                           "populated); split whole-event so leak-free",
            "band_spreads": {str(k): round(v, 4) for k, v in sorted(spreads.items())},
        },
        "data": {"n_fills": len(rows), "n_super_events": split_meta["n_events"],
                 "dropped_no_superkey": dropped, **split_meta},
        "test1_regime_conditional_scorecard": t1,
        "test2_conviction_weighting": t2,
        "test3_survivorship_correction": t3,
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    def fmt(x, p="+.4f"):
        return format(x, p) if isinstance(x, (int, float)) else "—"
    print(f"data: {len(rows)} fills, {split_meta['n_events']} super-events "
          f"(H1={split_meta.get('n_events_h1')} / H2={split_meta.get('n_events_h2')}), "
          f"dropped_no_superkey={dropped}")
    print(f"T1 regime scorecard: global_fs={t1['global_followset_n']} "
          f"per_sport_fs={t1['per_sport_followset_n']} | "
          f"H2 cr a(global)={fmt(t1['forward_copy_return_global_a'])} "
          f"b(per-sport)={fmt(t1['forward_copy_return_persport_b'])} | "
          f"D={fmt(t1['difference_b_minus_a'])} SE={fmt(t1['cluster_robust_se'],'.4f')} "
          f"Bonf3-LB={fmt(t1['bonferroni3_lb'])} | N_ev(a/b)={t1['n_events_a']}/{t1['n_events_b']} "
          f"| {t1['verdict']}")
    print(f"T2 conviction >=$1k: cr all={fmt(t2['forward_copy_return_all_a'])} "
          f">=1k={fmt(t2['forward_copy_return_ge1k_b'])} | D={fmt(t2['difference_b_minus_a'])} "
          f"SE={fmt(t2['cluster_robust_se'],'.4f')} Bonf3-LB={fmt(t2['bonferroni3_lb'])} | "
          f"N_ev(all/1k)={t2['n_events_a']}/{t2['n_events_b']} | {t2['verdict']}")
    print(f"T3 survivorship: cr with={fmt(t3['forward_copy_return_with_recovered'])} "
          f"without={fmt(t3['forward_copy_return_without_recovered'])} | "
          f"bias={fmt(t3['bias_with_minus_without'])} "
          f"({t3['n_recovered_fills_in_followset_h2']} recovered fills, "
          f"{t3['n_recovered_wallets_in_followset']} wallets) | {t3['bias_direction']}")
    print(f"wrote {REPORT}")


# ---------------------------------------------------------------- self-test (no DB)
def _self_test():
    global _SPREADS
    _SPREADS = {}     # reprice = price + follower_tax (no band spread model in the fixture)

    # -- shape(): super_event collapse + category ------------------------------------------------
    raw = [
        {"event_slug": "fifwc-bel-sen-2026-07-01-exact-score", "slug": "fifwc-bel-sen-2026-07-01-exact-score-2-0",
         "ts": "10", "day": "d1", "price": "0.7", "won": "1", "size_usd": "500", "recovered": "0",
         "title": "Belgium vs Senegal", "wallet": "w"},
        {"event_slug": "fifwc-bel-sen-2026-07-01", "slug": "fifwc-bel-sen-2026-07-01-bel",
         "ts": "20", "day": "d1", "price": "0.7", "won": "1", "size_usd": "500", "recovered": "0",
         "title": "Belgium vs Senegal", "wallet": "w"},
        {"event_slug": None, "slug": None,      # no super-key => dropped
         "ts": "30", "day": "d1", "price": "0.7", "won": "1", "size_usd": "1", "recovered": "0",
         "title": "x", "wallet": "w"},
    ]
    shaped, dropped = shape(raw)
    assert dropped == 1, f"expected 1 dropped, got {dropped}"
    assert len({r["ev"] for r in shaped}) == 1, "two Belgium-Senegal sub-markets must collapse to 1 super-event"
    assert shaped[0]["cat"] == "soccer", shaped[0]["cat"]

    # -- time_split(): whole-event split at the midpoint of event time ---------------------------
    def row(ev, ts, cat="soccer", w="w", won=1, price=0.7, size=100, rec=0, day="d"):
        return {"wallet": w, "ev": ev, "ts": float(ts), "day": day, "price": price, "won": won,
                "size_usd": float(size), "recovered": rec, "cat": cat}
    rr = [row("e1", 0), row("e1", 5), row("e2", 100), row("e3", 1000)]  # 3 events; median split @ cut=1
    h1, h2, meta = time_split(rr)
    assert {r["ev"] for r in h1} == {"e1"} and {r["ev"] for r in h2} == {"e2", "e3"}, (h1, h2)
    assert meta["n_events_h1"] == 1 and meta["n_events_h2"] == 2

    # -- forward_per_event(): dedup across wallets to one obs per super-event ---------------------
    fwd = forward_per_event([row("e1", 0, w="a", won=1), row("e1", 1, w="b", won=0),
                             row("e2", 2, w="a", won=1)], keep=lambda r: True)
    # e1: mean of ret(won=1) and ret(won=0) at price .7 -> ((1-.713)/.713-.02 + (0-.713)/.713-.02)/2
    e = 0.7 + tsc.FOLLOWER_TAX
    r_win, r_los = (1 - e) / e - tsc.FEE, (0 - e) / e - tsc.FEE
    assert abs(fwd["e1"][1] - (r_win + r_los) / 2) < 1e-9, fwd["e1"]
    assert len(fwd) == 2, fwd

    # -- bootstrap_diff(): b uniformly +0.10 above a on the SAME events => D~+0.10, LB finite -----
    per_a = {f"e{i}": ("d", 0.00) for i in range(40)}
    per_b = {f"e{i}": ("d", 0.10) for i in range(40)}
    D, se, lb = bootstrap_diff(per_a, per_b)
    assert abs(D - 0.10) < 1e-9 and se is not None and abs(se) < 1e-6 and lb is not None, (D, se, lb)
    # identical arms => D=0
    D0, _, _ = bootstrap_diff(per_a, dict(per_a))
    assert abs(D0) < 1e-12, D0
    # verdict wiring
    assert verdict(0.05, 0.01, 0.02).startswith("positive")          # LB>0
    assert verdict(-0.30, 0.05, -0.40).startswith("negative")        # UB<0 => robustly worse
    assert verdict(-0.05, 0.10, -0.30).startswith("indeterminate")   # CI straddles 0

    # -- end-to-end: test1 prefers per-sport when a wallet is skilled ONLY in its own sport -------
    micro, bots = {}, {}
    # H1: 'soc' wallet skilled in soccer (85% at .7 over >=100 fills, >=15 days, >=30 events),
    #     junk elsewhere; global pooling dilutes it below the +10% floor in a mixed sport.
    def mk(w, cat, n, hit, base_ev, base_ts, days=20):
        out = []
        for i in range(n):
            out.append(row(f"{cat}-{base_ev}-{i}", base_ts + i, cat=cat, w=w,
                           won=1 if (i % 100) < hit * 100 else 0, day=f"{cat}d{i % days}"))
        return out
    h1r = mk("soc", "soccer", 200, 0.90, "h1", 0) + mk("soc", "tennis", 200, 0.55, "h1", 5000)
    h2r = mk("soc", "soccer", 60, 0.90, "h2", 100000) + mk("soc", "tennis", 60, 0.55, "h2", 200000)
    t1 = test1_regime_scorecard(h1r, h2r, {}, micro, bots)
    # per-sport must qualify 'soc' in soccer (skilled) and route only its soccer H2 fills; global
    # may or may not qualify it, but per-sport's forward read must be >= global's here.
    assert ("soc", "soccer") in {(w, c) for c, ws in t1["per_sport_followsets"].items() for w in ws}, t1
    assert t1["forward_copy_return_persport_b"] is not None

    # -- test3: censoring recovered fills changes the read in the correct direction ---------------
    g_h1 = mk("v", "soccer", 200, 0.80, "h1", 0)
    # H2: base soccer fills (won mostly) + recovered fills that are LOSSES => removing them raises read
    g_h2 = mk("v", "soccer", 40, 0.80, "h2", 100000)
    g_h2 += [row(f"rec-{i}", 300000 + i, cat="soccer", w="v", won=0, rec=1, day=f"rd{i}") for i in range(20)]
    t3 = test3_survivorship(g_h1, g_h2, {}, {}, {})
    assert t3["n_recovered_fills_in_followset_h2"] == 20, t3
    assert t3["bias_with_minus_without"] is not None and t3["bias_with_minus_without"] < 0, t3
    assert t3["bias_direction"].startswith("downward"), t3

    print("self-test OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
    else:
        run()
