#!/usr/bin/env python3
"""
PORTFOLIO CONCENTRATION — how few INDEPENDENT bets the forward record actually holds.

The companion to the risk engine (scripts/risk_engine.py). Sizing sizes an edge; this
instrument measures how CONCENTRATED the record is, so the risk engine's Monte Carlo
resamples the real correlation structure and does not fake diversification that isn't
there. Read-only, paper-only, changes nothing live. Reuses selection_null.py machinery
(band/regime/fetch) so the statistic is byte-identical to the gate's.

The battery (pre-registered — see reports/entries/2026-07-02-12-diversification-risk.md):

  ICC per grain   intraclass correlation of event-level advantage residuals, clustered by
                  (a) MATCH  = slug with the market suffix stripped (fifwc-bra-jpn-DATE):
                        favorite fires -exact-score AND -more-markets of ONE game; the gate
                        counts them as 2 events, they are 1 correlated bet.
                  (b) SLATE  = regime × UTC-day (the Phase-2 block-bootstrap grain; it
                        subsumes MATCH since matches nest in slates).
                  (c) REGIME = sport across days (the coarsest, most conservative grain).
  N_eff           N_events / design-effect, DE = 1 + (m̄−1)·ICC, per grain. The single most
                  important number: how many independent bets the record CONTAINS. SLATE is
                  the headline; REGIME is the conservative floor. Block-bootstrap CI (resample
                  slate blocks) — it is WIDE on 4 days; that width is the finding, not noise.
  HHI             exposure concentration by regime / event-day / tournament, on event-count
                  AND on realizable P&L. 1/HHI = the effective number of buckets.
  top-tournament  share of realizable P&L from the single largest tournament — the
                  over-reliance number the owner asked about, stated as % of profit.
  cross-strategy  favorite ∩ elite_fresh_fav overlap by event, DEDUPED: adding a nested
                  strategy adds ZERO independent bets. Never double-count.

Every number inherits a 4-day, one-WC-weekend + one-Wimbledon-fortnight record. Stated so.

Modes:
  ./portfolio_concentration.py            # live DB (docker-exec psql), writes JSON artifact
  ./portfolio_concentration.py --selftest # synthetic known-ICC fixtures: the ICC and N_eff
                                          # estimators must recover the injected design
                                          # effect; iid fixture must give ICC≈0, N_eff≈N.
                                          # Exit non-zero on failure.
"""

import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn  # band(), regime(), fetch()

POPULATIONS = ["favorite", "elite_fresh_fav", "strict"]
SEED = 20260702
N_BOOT = 2000
HAIRCUT = 0.005          # measured median haircut (D11), matches slice_study.py
FEE = 0.02
STAKE = 100.0            # flat-shares normaliser (per event)

# Match key: strip the polymarket market-type suffix that follows the YYYY-MM-DD date, so
# the exact-score / more-markets / first-to-score sub-markets of one game collapse to the
# game. Anything without a parseable date keeps its full ev key (its own singleton match).
_DATE_RE = re.compile(r"^(.*\d{4}-\d{2}-\d{2})(?:-.*)?$")


def match_key(event_slug, ev):
    s = event_slug or ""
    m = _DATE_RE.match(s)
    if m:
        return m.group(1)
    return ev  # crypto / unparseable: its own match


def tournament(event_slug, ev):
    """Coarse tournament bucket for HHI. Sports: <prefix> before the two competitors
    (fifwc, mlb, lol, cs); tennis lumps atp/wta = the current Grand Slam (Wimbledon on this
    record). Crypto/other: the regime name. Honest at this record's granularity."""
    s = event_slug or ""
    rg = sn.regime(event_slug)
    if rg == "tennis":
        return "tennis-slam"     # atp+wta over this fortnight = Wimbledon
    if rg in ("soccer", "mlb", "cs2"):
        tok = s.split("-", 1)[0]
        return tok or rg
    if rg == "crypto":
        return "crypto"
    tok = s.split("-", 1)[0] if s else ""
    return tok or rg


def icc_oneway(groups):
    """One-way random-effects ICC(1) via ANOVA. groups: list of lists of floats.
    Returns (icc, m_bar, k_groups, n_total). ICC clamped to [0,1]."""
    groups = [g for g in groups if len(g) >= 1]
    k = len(groups)
    n_total = sum(len(g) for g in groups)
    if k < 2 or n_total <= k:
        return 0.0, (n_total / k if k else 0.0), k, n_total
    grand = sum(sum(g) for g in groups) / n_total
    ssb = sum(len(g) * (np.mean(g) - grand) ** 2 for g in groups)
    ssw = sum(sum((x - np.mean(g)) ** 2 for x in g) for g in groups)
    msb = ssb / (k - 1)
    msw = ssw / (n_total - k)
    # adjusted average group size m0 (unequal clusters)
    m0 = (n_total - sum(len(g) ** 2 for g in groups) / n_total) / (k - 1)
    denom = msb + (m0 - 1) * msw
    icc = 0.0 if denom <= 0 else (msb - msw) / denom
    icc = max(0.0, min(1.0, icc))
    return icc, n_total / k, k, n_total


def n_eff(n_total, m_bar, icc):
    de = 1.0 + (m_bar - 1.0) * icc
    return n_total / de if de > 0 else float(n_total), de


def hhi(counts):
    tot = float(sum(counts))
    if tot <= 0:
        return float("nan"), float("nan")
    shares = [c / tot for c in counts]
    h = sum(s * s for s in shares)
    return h, (1.0 / h if h > 0 else float("nan"))


def build_baseline(blind):
    rb, bb = defaultdict(list), defaultdict(list)
    for r in blind:
        rb[(sn.regime(r["event_slug"]), sn.band(r["entry"]))].append(r["won"] - r["entry"])
        bb[sn.band(r["entry"])].append(r["won"] - r["entry"])
    base_rb = {k: sum(v) / len(v) for k, v in rb.items()}
    base_b = {k: sum(v) / len(v) for k, v in bb.items()}

    def baseline(r):
        return base_rb.get((sn.regime(r["event_slug"]), sn.band(r["entry"])),
                           base_b.get(sn.band(r["entry"]), 0.0))
    return baseline


def ev_residuals(prows, baseline):
    """Collapse rows to per-ev metadata + two per-ev series:
      resid = advantage residual (a − matched-blind edge) — INDEPENDENT-EVIDENCE grain
              (the pre-registered estimator; answers 'how many independent edge reads').
      raw   = raw advantage a = won − entry — BANKROLL-SWING grain (answers 'how correlated
              are the P&L swings the drawdown/ruin math sees'; two markets of one game
              resolve together). The risk engine's block bootstrap resamples the raw joint
              structure directly; this ICC just makes the concentration legible.
    plus per-ev realizable flat-shares P&L for the HHI/top-tournament reads."""
    by_ev_resid, by_ev_raw = defaultdict(list), defaultdict(list)
    meta = {}
    for r in prows:
        by_ev_resid[r["ev"]].append(r["won"] - r["entry"] - baseline(r))
        by_ev_raw[r["ev"]].append(r["won"] - r["entry"])
        c = min(0.999, r["entry"] + HAIRCUT)
        pnl = STAKE * (r["won"] - c) - FEE * STAKE * c   # flat-shares realizable
        meta.setdefault(r["ev"], {"pnls": []})
        meta[r["ev"]]["pnls"].append(pnl)
        meta[r["ev"]].update(
            match=match_key(r["event_slug"], r["ev"]),
            slate=(sn.regime(r["event_slug"]), r["day"]),
            regime=sn.regime(r["event_slug"]),
            tourn=tournament(r["event_slug"], r["ev"]),
            day=r["day"])
    resid = {ev: float(np.mean(v)) for ev, v in by_ev_resid.items()}
    raw = {ev: float(np.mean(v)) for ev, v in by_ev_raw.items()}
    for ev in meta:
        meta[ev]["pnl"] = float(np.mean(meta[ev]["pnls"]))
    return resid, raw, meta


def grain_icc(resid, meta, grain_field):
    groups = defaultdict(list)
    for ev, x in resid.items():
        groups[meta[ev][grain_field]].append(x)
    icc, m_bar, k, n = icc_oneway(list(groups.values()))
    ne, de = n_eff(n, m_bar, icc)
    return {"icc": icc, "m_bar": m_bar, "k_groups": k, "n_events": n,
            "design_effect": de, "n_eff": ne}


def concentration(prows, baseline, nprng, n_boot=N_BOOT):
    resid, raw, meta = ev_residuals(prows, baseline)
    evs = list(resid.keys())
    n = len(evs)
    out = {"n_events": n}
    for field, name in [("match", "match"), ("slate", "slate"), ("regime", "regime")]:
        out[name] = grain_icc(resid, meta, field)
        out[name]["icc_raw"] = grain_icc(raw, meta, field)["icc"]

    # Block-bootstrap CI on the SLATE-grain N_eff FRACTION (resample slate blocks with
    # replacement, CI the ratio N_eff/N so it stays bounded by N — resampled totals vary).
    slates = defaultdict(list)
    for ev in evs:
        slates[meta[ev]["slate"]].append(ev)
    slate_keys = list(slates.keys())
    frac_boot = []
    for _ in range(n_boot):
        idx = nprng.integers(0, len(slate_keys), len(slate_keys))
        rr, mm = {}, {}
        for j, si in enumerate(idx):
            for ev in slates[slate_keys[si]]:
                key = f"{ev}#{j}"        # de-alias resampled duplicates
                rr[key] = resid[ev]
                mm[key] = {**meta[ev], "slate": (meta[ev]["slate"], j)}
        g = grain_icc(rr, mm, "slate")
        if g["n_events"] > 0:
            frac_boot.append(g["n_eff"] / g["n_events"])
    out["slate"]["n_eff_ci"] = [float(np.percentile(frac_boot, 2.5)) * n,
                                float(np.percentile(frac_boot, 97.5)) * n]

    # HHI by regime / event-day / tournament, on event-count and on realizable P&L.
    for field, name in [("regime", "regime"), ("day", "event_day"), ("tourn", "tournament")]:
        cnt = defaultdict(int)
        pnl = defaultdict(float)
        for ev in evs:
            cnt[meta[ev][field]] += 1
            pnl[meta[ev][field]] += meta[ev]["pnl"]
        h_c, eff_c = hhi(list(cnt.values()))
        # P&L "share of profit": positive-P&L mass only (share of gains).
        tot_pnl = sum(pnl.values())
        gains = {k: v for k, v in pnl.items() if v > 0}
        tot_gain = sum(gains.values())
        top = max(pnl.items(), key=lambda kv: kv[1]) if pnl else (None, 0.0)
        out[f"hhi_{name}"] = {
            "hhi_count": h_c, "eff_buckets_count": eff_c,
            "buckets": {str(k): {"n_events": cnt[k], "pnl": round(pnl[k], 1)}
                        for k in cnt},
            "total_pnl": round(tot_pnl, 1),
            "top_bucket": str(top[0]),
            "top_pnl_share_of_gross_gain": (round(top[1] / tot_gain, 4)
                                            if tot_gain > 0 else None),
            "top_pnl_share_of_net": (round(top[1] / tot_pnl, 4)
                                     if abs(tot_pnl) > 1e-9 else None)}
    return out, meta


def cross_strategy(pop_rows):
    ev_sets = {p: {r["ev"] for r in pop_rows[p]} for p in pop_rows}
    out = {}
    names = list(pop_rows.keys())
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            inter = ev_sets[a] & ev_sets[b]
            out[f"{a}∩{b}"] = {
                "n_a": len(ev_sets[a]), "n_b": len(ev_sets[b]),
                "shared": len(inter),
                "share_of_b_in_a": round(len(inter) / max(1, len(ev_sets[b])), 4),
                "share_of_a_in_b": round(len(inter) / max(1, len(ev_sets[a])), 4),
                "union_deduped": len(ev_sets[a] | ev_sets[b]),
                "independent_bets_added_by_b": len(ev_sets[b] - ev_sets[a])}
    return out


def run(populations=POPULATIONS, quiet=False):
    rows = sn.fetch()
    nprng = np.random.default_rng(SEED)
    blind = [r for r in rows if r["strategy"] == "_blind"]
    if not blind:
        sys.exit("no _blind baseline")
    baseline = build_baseline(blind)
    pop_rows = {p: [r for r in rows if r["strategy"] == p] for p in populations}

    result = {"meta": {"seed": SEED, "n_boot": N_BOOT, "haircut": HAIRCUT, "fee": FEE,
                       "days": sorted({r["day"] for r in rows}),
                       "populations": populations},
              "strategies": {}, "cross_strategy": cross_strategy(pop_rows)}
    metas = {}
    for p in populations:
        if not pop_rows[p]:
            continue
        c, meta = concentration(pop_rows[p], baseline, nprng)
        result["strategies"][p] = c
        metas[p] = meta
    if not quiet:
        _print(result)
    return result, metas


def _print(result):
    print(f"portfolio concentration · seed {result['meta']['seed']} · "
          f"record {len(result['meta']['days'])}d "
          f"{result['meta']['days'][0]}→{result['meta']['days'][-1]} · "
          f"haircut {HAIRCUT*100:.1f}¢ fee {FEE:.0%}")
    print("\nHOW MANY INDEPENDENT BETS DO WE ACTUALLY HOLD?  (N_eff = N / design-effect)")
    print("  ICC on advantage RESIDUALS (edge-evidence); (raw)=on raw advantage (P&L swings)")
    hdr = (f"{'strategy':<16}{'N_ev':>5}{'ICC_match':>16}{'ICC_slate':>16}"
           f"{'ICC_reg':>8}{'Neff_slate':>16}{'Neff_reg':>9}")
    print(hdr)
    print("-" * len(hdr))
    for p, c in result["strategies"].items():
        ci = c["slate"].get("n_eff_ci", [None, None])
        mm = f"{c['match']['icc']:.3f}({c['match']['icc_raw']:.2f})"
        sl = f"{c['slate']['icc']:.3f}({c['slate']['icc_raw']:.2f})"
        ne = f"{c['slate']['n_eff']:.0f}[{ci[0]:.0f},{ci[1]:.0f}]"
        print(f"{p:<16}{c['n_events']:>5}{mm:>16}{sl:>16}"
              f"{c['regime']['icc']:>8.3f}{ne:>16}{c['regime']['n_eff']:>9.1f}")
    print("\nCONCENTRATION (HHI: 1.0 = all in one bucket; 1/HHI = effective # buckets)")
    for p, c in result["strategies"].items():
        h = c["hhi_tournament"]
        print(f"{p:<16} tournament HHI={h['hhi_count']:.3f} "
              f"(≈{h['eff_buckets_count']:.1f} tournaments) · top='{h['top_bucket']}' "
              f"{'' if h['top_pnl_share_of_gross_gain'] is None else f'''holds {h['top_pnl_share_of_gross_gain']:.0%} of gross profit'''}")
    print("\nCROSS-STRATEGY OVERLAP (adding a nested strategy adds how many independent bets?)")
    for k, v in result["cross_strategy"].items():
        print(f"  {k}: shared {v['shared']}/{v['n_b']} of B "
              f"({v['share_of_b_in_a']:.0%} of B ⊂ A) · union {v['union_deduped']} · "
              f"B adds {v['independent_bets_added_by_b']} independent events")


# --- Self-test: injected known-ICC fixtures; the estimators must recover them. --------
def _synth_clustered(icc_target, n_slates=40, per_slate=8, seed=SEED):
    """Event residuals with a KNOWN slate-level ICC. u_slate ~ N(0, icc), e ~ N(0, 1-icc);
    x = u_slate + e ⇒ true ICC = icc_target. Returns (resid, meta)."""
    rng = np.random.default_rng(seed)
    sb = np.sqrt(icc_target)
    sw = np.sqrt(1.0 - icc_target)
    resid, meta = {}, {}
    for s in range(n_slates):
        u = rng.normal(0, sb) if sb > 0 else 0.0
        for j in range(per_slate):
            ev = f"e{s}_{j}"
            resid[ev] = float(u + rng.normal(0, sw))
            meta[ev] = {"slate": f"s{s}", "regime": f"r{s%3}", "match": f"m{s}_{j//2}",
                        "day": f"d{s%4}", "tourn": f"t{s%3}"}
    return resid, meta


def selftest():
    ok = True
    print("— known-ICC recovery (slate grain) —")
    for target in (0.0, 0.25, 0.6):
        # average over several seeds to beat estimator sampling noise on k=40 groups
        iccs, neffs = [], []
        for sd in range(8):
            resid, meta = _synth_clustered(target, seed=SEED + sd)
            g = grain_icc(resid, meta, "slate")
            iccs.append(g["icc"])
            neffs.append(g["n_eff"])
        icc_hat = float(np.mean(iccs))
        # analytic N_eff for the fixture: DE = 1 + (per_slate-1)*icc
        de_true = 1 + (8 - 1) * target
        neff_true = (40 * 8) / de_true
        neff_hat = float(np.mean(neffs))
        tol_icc = 0.06
        tol_neff = 0.20 * neff_true + 15
        pass_icc = abs(icc_hat - target) <= tol_icc
        pass_neff = abs(neff_hat - neff_true) <= tol_neff
        ok = ok and pass_icc and pass_neff
        print(f"  ICC target {target:.2f} → est {icc_hat:.3f} "
              f"[{'ok' if pass_icc else 'FAIL'}] · "
              f"N_eff true {neff_true:.0f} → est {neff_hat:.0f} "
              f"[{'ok' if pass_neff else 'FAIL'}]")

    print("— iid fixture: ICC≈0, N_eff≈N —")
    resid, meta = _synth_clustered(0.0, seed=SEED + 99)
    g = grain_icc(resid, meta, "slate")
    pass_iid = g["icc"] <= 0.05 and g["n_eff"] >= 0.75 * len(resid)
    ok = ok and pass_iid
    print(f"  ICC {g['icc']:.3f}, N_eff {g['n_eff']:.0f}/{len(resid)} "
          f"[{'ok' if pass_iid else 'FAIL'}]")

    print("— HHI sanity: uniform → 1/k, degenerate → 1 —")
    h_uni, eff_uni = hhi([10, 10, 10, 10])
    h_deg, _ = hhi([40, 0, 0, 0])
    pass_hhi = abs(h_uni - 0.25) < 1e-9 and abs(eff_uni - 4) < 1e-9 and abs(h_deg - 1) < 1e-9
    ok = ok and pass_hhi
    print(f"  uniform HHI {h_uni:.3f} (eff {eff_uni:.1f}), degenerate {h_deg:.3f} "
          f"[{'ok' if pass_hhi else 'FAIL'}]")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    result, _ = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "reports", "portfolio_concentration.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("\nartifact → reports/portfolio_concentration.json")


if __name__ == "__main__":
    main()
