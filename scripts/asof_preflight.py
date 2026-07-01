#!/usr/bin/env python3
"""
§0.5 MINIMUM DECISIVE PRE-FLIGHT — falsify-or-proceed on the diversification premise.

Runs the leak-free as-of certification (scripts/asof_slice_scores.sql) at one or more
event-date cuts and answers the binding decision rule:

  (1) How many wallets are gate-Trusted at the CAPTURE bar (Bonferroni one-sided lower
      bound > slippage+fee = 3%), N>=30 distinct events, on a single sport slice,
      certified on the TRAIN window (event date < cut) -- and how many PERSIST as
      Trusted-in-that-sport on the TEST window (event date >= cut)?
  (2) Among survivors, are >=2 Trusted in DIFFERENT sports, and do they avoid
      collapsing onto the same slate?

DECISION (binding, charter §0.5): if (1) yields <2 capturable, persistent per-sport
specialists across >=2 disjoint cuts, OR (2) shows slate collapse -> premise DEAD.

Exact math mirrors scanner/promotion.rs::{surplus_bounds, promotion_verdict}:
  n_comparisons = per-wallet count of slices with non-null surplus
  z    = probit(1 - 0.05/n_comparisons)          # scipy ppf == Acklam probit to <1e-4
  se   = surplus_sd / sqrt(n_events)
  lo   = surplus - z*se ;  hi = surplus + z*se
  Trusted@capture  <=> n_events>=30 AND lo > 0.03
  Avoid@capture    <=> n_events>=30 AND hi < -0.03
"""
import csv, io, subprocess, sys
from math import sqrt
from scipy.stats import norm

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
SQL = __file__.rsplit("/", 1)[0] + "/asof_slice_scores.sql"
SQL_TEXT = open(SQL).read()
MARGIN = 0.03      # slippage_pct(0.01) + fee_pct(0.02)
FLOOR  = 30        # PromotionParams.min_events
ALPHA  = 0.05

def slice_scores(d_lo, d_hi):
    out = subprocess.run(
        PG + ["-v", f"d_lo={d_lo}", "-v", f"d_hi={d_hi}", "-f", "-"],
        input=SQL_TEXT, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = list(csv.DictReader(io.StringIO(out.stdout)))
    for r in rows:
        r["n_events"] = int(r["n_events"])
        r["surplus"]  = float(r["surplus"])  if r["surplus"]  else None
        r["surplus_sd"] = float(r["surplus_sd"]) if r["surplus_sd"] else None
    return rows

def verdicts(rows):
    """wallet -> {(kind,key): dict(verdict, lo, hi, surplus, n)}  with per-wallet Bonferroni."""
    by_wallet = {}
    for r in rows:
        by_wallet.setdefault(r["wallet"], []).append(r)
    out = {}
    for w, slices in by_wallet.items():
        n_comp = max(1, sum(1 for s in slices if s["surplus"] is not None))
        z = norm.ppf(1 - min(0.5, max(1e-6, ALPHA / n_comp)))
        tbl = {}
        for s in slices:
            if s["surplus"] is None:
                continue
            n, surplus = s["n_events"], s["surplus"]
            sd = (s["surplus_sd"] or 0.0)
            sd = sd if sd > 1e-9 else 1e-9
            se = sd / sqrt(max(1, n))
            lo, hi = surplus - z*se, surplus + z*se
            if n < FLOOR:
                v = "INDET(floor)"
            elif lo > MARGIN:
                v = "TRUSTED"
            elif hi < -MARGIN:
                v = "AVOID"
            else:
                v = "INDET"
            tbl[(s["slice_kind"], s["slice_key"])] = dict(
                verdict=v, lo=lo, hi=hi, surplus=surplus, n=n, n_comp=n_comp)
        out[w] = tbl
    return out

def sport_specialists(vd):
    """wallets Trusted@capture on some sport slice -> list of (wallet, sport, rec)."""
    res = []
    for w, tbl in vd.items():
        for (kind, key), rec in tbl.items():
            if kind == "sport" and key != "other" and rec["verdict"] == "TRUSTED":
                res.append((w, key, rec))
    return res

def run_cut(cut, hi="2100-01-01", lo="1900-01-01"):
    print(f"\n{'='*78}\nCUT = {cut}   (train: [{lo}, {cut}) ; test: [{cut}, {hi}))\n{'='*78}")
    train = verdicts(slice_scores(lo, cut))
    test  = verdicts(slice_scores(cut, hi))
    tr_spec = sport_specialists(train)
    print(f"TRAIN per-sport specialists Trusted@capture (lo>{MARGIN:.0%}, N>=30): {len(tr_spec)}")
    persistent = []
    for w, sport, rec in sorted(tr_spec, key=lambda x: -x[2]["lo"]):
        t = test.get(w, {}).get(("sport", sport))
        tstr = (f"test N={t['n']} lo={t['lo']:+.3f} -> {t['verdict']}" if t
                else "NO test-window events for this wallet-sport")
        keeps = bool(t and t["verdict"] == "TRUSTED")
        persistent.append((w, sport) if keeps else None)
        print(f"  {w[:12]}… {sport:8s} | train N={rec['n']:3d} surplus={rec['surplus']:+.3f} "
              f"lo={rec['lo']:+.3f} (nComp={rec['n_comp']}) || {tstr} | persists={keeps}")
    persistent = [p for p in persistent if p]
    sports = {s for _, s in persistent}
    print(f"PERSISTENT per-sport specialists (Trusted@capture BOTH windows): {len(persistent)}"
          f" across {len(sports)} distinct sports {sorted(sports)}")
    return tr_spec, persistent

if __name__ == "__main__":
    # Two disjoint cuts (H2 requires confirmation on >=2). Late June 2026 is where the
    # only both-sided coverage could exist; everything else is a pre-tournament trickle.
    for cut in ["2026-06-29", "2026-06-30"]:
        run_cut(cut)
