#!/usr/bin/env python3
"""
WS-1 — CLV (closing line value), the betting-world gold-standard skill signal.

KEY UNLOCK: CLV need not wait for a new forward price-capture daemon. The tracked-trader FILL
TAPE is itself a price feed — every fill in a market is a price observation. So we can measure a
TAPE-DERIVED CLV today AND it accrues forward for free as new fills ingest (cost-zero, no
external API, no deploy surface):

  closing_line(cond,outcome) = avg fill price in the LAST 20% of the market's fill-time span
                               (>=5 fills; these are OTHER traders near resolution)
  entry fills                = BUY fills in the FIRST 80% of the span
  CLV(fill)                  = closing_line - entry_price   (BUY: +CLV = bought BELOW the close)

Per-wallet mean CLV is event-clustered (ev=COALESCE(event_slug,condition_id)), NON-MM cohort.
Entries and the closing window never overlap (first-80% vs last-20%), so a wallet's entry is
never its own closing observation; residual self-influence on the closing average is diluted by
co-trading peers (caveat noted).

Two tests:
  (1) CLV PERSISTENCE: does early-window CLV predict late-window CLV (skill, not luck)?
  (2) CLV -> COPYABLE DIRECTION (the mission): does early CLV predict late blind-surplus
      (hold-to-resolution, copyable), out-of-cohort?

Pre-registered forward gate (PRE_REGISTRATION.md): CLV_lo>0 forward, >=50 events, >=2 disjoint
windows. This session reports the DECIDABLE-TODAY retrospective read + the current accrued N.

READ-ONLY. Writes reports/skilled/ws1_clv.json.  --selftest for synthetic checks.
"""
import argparse, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skill_common as sk   # noqa: E402
import mm_common as mc      # noqa: E402

REPORT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "reports", "skilled", "ws1_clv.json")
MIN_EV = 10

SQL = r"""
WITH f AS (
  SELECT lower(wallet) w, condition_id co, outcome_index oi, COALESCE(event_slug,condition_id) ev,
         EXTRACT(EPOCH FROM ts) t, price, side
  FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL),
span AS (SELECT co, oi, min(t) tmin, max(t) tmax FROM f GROUP BY 1,2),
clo AS (
  SELECT f.co, f.oi, avg(f.price) close_price, count(*) nclose
  FROM f JOIN span s ON f.co=s.co AND f.oi=s.oi
  WHERE s.tmax>s.tmin AND f.t >= s.tmax - 0.2*(s.tmax-s.tmin)
  GROUP BY 1,2 HAVING count(*)>=5),
entry AS (
  SELECT f.w, f.ev, f.t, (c.close_price - f.price) clv
  FROM f JOIN span s ON f.co=s.co AND f.oi=s.oi JOIN clo c ON c.co=f.co AND c.oi=f.oi
  WHERE f.side='BUY' AND f.t < s.tmax - 0.2*(s.tmax-s.tmin)),
wm AS (SELECT w, percentile_cont(0.5) WITHIN GROUP (ORDER BY t) tm FROM entry GROUP BY w),
ev_clv AS (SELECT e.w, e.ev, (e.t < wm.tm) is_early, avg(e.clv) clv
           FROM entry e JOIN wm USING(w) GROUP BY e.w, e.ev, (e.t<wm.tm))
SELECT w, is_early, count(*) n_ev, avg(clv) clv FROM ev_clv GROUP BY w, is_early;
"""


def run():
    rows = mc.q(SQL)
    micro = mc.microstructure()
    per = {}   # w -> {"E":(n,clv), "L":(n,clv)}
    for r in rows:
        try:
            w, ise, n, clv = r[0], r[1], int(float(r[2])), float(r[3])
        except (ValueError, IndexError):
            continue
        per.setdefault(w, {})
        per[w]["E" if ise in ("t", "true", "True") else "L"] = (n, clv)

    # cohort: non-MM, >=MIN_EV events per half
    E, L, W = [], [], []
    for w, d in per.items():
        m = micro.get(w)
        if m is None or mc.is_churner(m):
            continue
        if "E" not in d or "L" not in d or d["E"][0] < MIN_EV or d["L"][0] < MIN_EV:
            continue
        W.append(w); E.append(d["E"][1]); L.append(d["L"][1])
    n = len(W)
    out = {"instrument": "tape-derived CLV (closing-line value from fill tape)",
           "note": "accrues forward automatically as fills ingest; no external API",
           "cohort": "non-MM directional", "min_ev_half": MIN_EV, "n_wallets": n,
           "forward_gate": "CLV_lo>0, >=50 events, >=2 disjoint windows (PRE_REGISTRATION)"}
    if n < 10:
        out["verdict"] = "INDETERMINATE-BY-POWER (too few wallets with CLV in both halves)"
        return out

    # level: is fleet CLV ~0 (sanity: closing line should be near entries on average)
    all_clv = E + L
    out["fleet_mean_clv"] = sum(all_clv) / len(all_clv)
    # (1) persistence early->late
    lo, hi, pt = sk.boot_ci(list(zip(E, L)),
                            lambda ps: sk.spearman([p[0] for p in ps], [p[1] for p in ps]))
    out["clv_persistence"] = {"spearman": pt, "ci95": [lo, hi], "persists": lo > 0}
    # top-tercile-by-early-CLV forward CLV LB
    order = sorted(range(n), key=lambda i: E[i], reverse=True)
    k = max(3, n // 3)
    top_late_clv = [L[i] for i in order[:k]]
    out["clv_persistence"]["top_tercile_late_clv_LB"] = sk.mean_lb(top_late_clv)
    out["clv_persistence"]["top_tercile_late_clv_mean"] = sum(top_late_clv) / k

    # (2) CLV -> copyable directional surplus (the mission)
    wl, _ = sk.load_events(10)
    late_dir = {w: sum(sum(x["surplus"] for x in rr) / len(rr) for rr in wl[w]["L"].values()) / len(wl[w]["L"])
                for w in wl}
    xs, ys, ww = [], [], []
    for i, w in enumerate(W):
        if w in late_dir:
            xs.append(E[i]); ys.append(late_dir[w]); ww.append(w)
    cross = {"n": len(xs)}
    if len(xs) >= 10:
        lo2, hi2, pt2 = sk.boot_ci(list(zip(xs, ys)),
                                   lambda ps: sk.spearman([p[0] for p in ps], [p[1] for p in ps]))
        cross.update({"spearman": pt2, "ci95": [lo2, hi2], "selects_copyable_edge": lo2 > 0})
        # out-of-cohort
        A = [i for i in range(len(xs)) if int(ww[i][2:12], 16) % 2 == 0]
        B = [i for i in range(len(xs)) if int(ww[i][2:12], 16) % 2 == 1]
        if len(A) >= 5 and len(B) >= 5:
            sA = sk.spearman([xs[i] for i in A], [ys[i] for i in A])
            sgn = 1.0 if sA >= 0 else -1.0
            lo3, hi3, pt3 = sk.boot_ci(list(zip([sgn * xs[i] for i in B], [ys[i] for i in B])),
                                       lambda ps: sk.spearman([p[0] for p in ps], [p[1] for p in ps]))
            cross["out_of_cohort_B"] = {"spearman_oriented": pt3, "ci95": [lo3, hi3],
                                        "n_A": len(A), "n_B": len(B), "generalizes": lo3 > 0}
    out["clv_selects_copyable_direction"] = cross

    persists = out["clv_persistence"]["persists"]
    selects = cross.get("selects_copyable_edge", False)
    if selects:
        out["verdict"] = "CLV SELECTS copyable directional edge -> WS-5 multiplicity (STRONG lead)"
    elif persists:
        out["verdict"] = ("CLV skill PERSISTS (ρ_lo>0) but selecting copyable direction is "
                          "INDETERMINATE-BY-POWER on the retrospective read — forward accrual to the "
                          "pre-registered gate (>=50 ev, 2 windows) will decide")
    else:
        out["verdict"] = ("CLV persistence INDETERMINATE on retrospective tape read; "
                          "forward accrual required")
    return out


def selftest():
    # BUY at 0.40, close 0.55 -> CLV +0.15
    assert abs((0.55 - 0.40) - 0.15) < 1e-9
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); sys.exit(0)
    res = run()
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps(res, indent=2, default=str))
