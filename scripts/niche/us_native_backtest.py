#!/usr/bin/env python3
"""
THE DECISIVE EXTERNAL-VALIDITY TEST: run the FROZEN collapse model on REAL US PRICES.

Everything upstream is on the international book. Tue trades Polymarket US — a different exchange,
different book. `US-TRANSFERABILITY.md` showed the port is plausible (fee-covered, depth-covered) but
NOT validated, because the cross-venue basis is tail-noisy. This is the validation: the model's
features and its verdict are recomputed on the US venue's OWN price tape, end to end.

DATA (all local, no network; the DMR endpoint moved but we don't need it):
  * US Time & Sales parquet  ~/polymarket-archive/us_time_sales/YYYY-MM-DD.parquet  (back to 06-24)
      columns: Transaction Time, Symbol, Last Price, Last Quantity. Each US Symbol is a BINARY YES
      contract, so its print series IS the price path — no outcome pairing needed (cleaner than intl).
  * Settlement from the T&S itself: a settled binary's last price -> 0/1. Validated against the
      explicit DMR Settlement Price on the 2 days we have it: **98.1% agreement**. We tighten to
      last>0.95 (win) / last<0.05 (loss) and DROP ambiguous symbols (unresolved/voided in-window).

MODEL: the frozen artifact model/collapse_model_frozen.pkl (sha256[:16]=ff23718d558ff0a1). NOT
retrained. Features are the SAME 14 backward-looking ones, recomputed from the US path, with the SAME
niche vocabulary the model trained on. No lookahead: features use only prints strictly before the
decision time; the label is the final settlement.

COSTS: US taker fee theta=0.06*p*(1-p) + a 0.5c ask haircut (we add size). Event-clustered by game.

  ./us_native_backtest.py --self-test
  ./us_native_backtest.py --from 2026-06-24 --to 2026-07-11
"""
import argparse
import glob
import os
import pickle
import re
import sys
from collections import defaultdict

import numpy as np

ARCHIVE = os.path.expanduser("~/polymarket-archive/us_time_sales")
MODEL = "model/collapse_model_frozen.pkl"
SEED = 20260714
BAND_LO = 0.80
MAX_DP = 8
# EXACT training vocabulary (collapse_risk.py: SPORTS order) — must match the frozen model
SPORTS = ("soccer", "mlb", "tennis", "esports", "nba", "nhl", "ufc")
NICHE_IDX = {n: i for i, n in enumerate(SPORTS)}
TRADEABLE = ("soccer", "tennis", "esports", "ufc")
THETA_US = 0.06
FEATS = ["p", "persistence", "n_prints", "elapsed", "max_p", "dd_from_max", "vol",
         "n_dips", "n_flips", "drift_15m", "drift_1h", "staleness", "mean_p_1h", "niche"]
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def fee_us(p):
    return THETA_US * p * (1 - p)


# Exotic/derivative US submarkets the intl model NEVER trained on — a "0.95" exact-score prop wins
# only ~77% (calibration gap −0.18). Pointing the model at these pollutes everything. EXCLUDE.
EXOTIC = re.compile(r"astatc|exact|corn|cor-|stat|gte|lte|-g-|neg-|pt5|total|over|under|"
                    r"handicap|nrfi|assist|halftime|-set-|first-set|-map-|-team-total|-tt-|scorer")


def is_exotic(sym):
    return bool(EXOTIC.search(sym.lower()))


def grade_niche(sym):
    """US symbol slug -> training niche vocabulary. Conservative: unknown -> None (dropped)."""
    s = sym.lower()
    toks = set(re.split(r"[-_]", s))
    if toks & {"fwc", "fifwc", "asc", "astatc", "epl", "ucl", "lliga", "seri", "bund", "mls", "soc"} \
            or "soccer" in s or "-fc-" in s:
        return "soccer"
    if toks & {"atp", "wta", "ten"} or "tennis" in s:
        return "tennis"
    if toks & {"cs2", "dota2", "dota", "lol", "val", "esp"} or "esport" in s:
        return "esports"
    if "ufc" in toks or "mma" in toks:
        return "ufc"
    if "mlb" in toks:
        return "mlb"
    if "nba" in toks:
        return "nba"
    if "nhl" in toks:
        return "nhl"
    return None


def event_key(sym):
    m = DATE_RE.search(sym)
    if not m:
        return sym
    # everything through the date groups a game's submarkets
    return sym[:m.end()]


def featurize(path, i, niche):
    """path = [(t_epoch, price)] ascending for ONE US symbol. Uses ONLY path[:i+1].
    Byte-for-byte the same feature logic as collapse_risk.py::featurize."""
    t, p = path[i]
    hist = path[:i + 1]
    ps = np.array([x[1] for x in hist], float)
    ts = np.array([x[0] for x in hist], float)
    start = None
    for (tt, pp) in hist:
        if pp >= BAND_LO:
            start = tt if start is None else start
        else:
            start = None
    persistence = 0.0 if start is None else t - start
    max_p = float(ps.max())
    elapsed = float(t - ts[0])
    recent = ps[-30:]
    vol = float(recent.std()) if len(recent) > 2 else 0.0
    n_dips = int(np.sum((ps[:-1] >= BAND_LO) & (ps[1:] < BAND_LO))) if len(ps) > 1 else 0
    n_flips = int(np.sum((ps[:-1] >= .5) != (ps[1:] >= .5))) if len(ps) > 1 else 0

    def px_ago(sec):
        j = min(max(np.searchsorted(ts, t - sec), 0), len(ps) - 1)
        return float(ps[j])

    m1h = ts >= (t - 3600)
    return [p, persistence, float(len(hist)), elapsed, max_p, max_p - p, vol,
            float(n_dips), float(n_flips), p - px_ago(900), p - px_ago(3600),
            float(t - ts[-2]) if len(ts) > 1 else 0.0,
            float(ps[m1h].mean()) if m1h.any() else p,
            float(NICHE_IDX.get(niche, -1))]


def settle(path):
    """last price -> outcome, with an ambiguity guard. Returns 1.0 / 0.0 / None."""
    last = path[-1][1]
    if last >= 0.95:
        return 1.0
    if last <= 0.05:
        return 0.0
    return None


def boot_event(rows, nb=4000, seed=SEED):
    by = defaultdict(list)
    for ev, net, p in rows:
        by[ev].append((net, p))
    cl = list(by)
    if len(cl) < 15:
        return None
    net = np.array([np.mean([x[0] for x in by[c]]) for c in cl], float)
    roi = np.array([sum(x[0] for x in by[c]) / sum(x[1] for x in by[c]) for c in cl], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(cl), (nb, len(cl)))
    bn, br = net[idx].mean(1), roi[idx].mean(1)
    return {"net": float(net.mean()), "net_lo": float(np.percentile(bn, 2.5)),
            "net_hi": float(np.percentile(bn, 97.5)),
            "roi": float(roi.mean()), "roi_lo": float(np.percentile(br, 2.5)),
            "roi_hi": float(np.percentile(br, 97.5)), "p": float((br <= 0).mean()),
            "n_ev": len(cl), "n_rows": len(rows)}


def self_test():
    assert grade_niche("asc-fwc-fra-swe-2026-06-30-neg-1pt5") == "soccer"
    assert grade_niche("atp-searle-basing-2026-07-11") == "tennis"
    assert grade_niche("cs2-bhe-keyd-2026-07-08-map-handicap-away-1pt5") == "esports"
    assert grade_niche("random-xyz") is None
    assert event_key("mlb-tex-cle-2026-07-01-nrfi") == "mlb-tex-cle-2026-07-01"
    assert NICHE_IDX["soccer"] == 0 and NICHE_IDX["tennis"] == 2 and NICHE_IDX["esports"] == 3
    # settlement guard
    assert settle([(0, .5), (9, .99)]) == 1.0 and settle([(0, .5), (9, .01)]) == 0.0
    assert settle([(0, .5), (9, .60)]) is None
    # no-lookahead: rewriting the future must not change features
    path = [(0, .5), (100, .85), (200, .86), (300, .10)]
    a = featurize(path, 2, "soccer")
    b = featurize(path[:3] + [(300, .99)], 2, "soccer")
    assert a == b, "US feature builder leaks the future"
    print("self-test OK  (niche grading, settlement guard, no-lookahead, niche vocab matches model)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--from", dest="d0", default="2026-06-24")
    ap.add_argument("--to", dest="d1", default="2026-07-11")
    ap.add_argument("--haircut", type=float, default=0.005)
    ap.add_argument("--curated", action="store_true",
                    help="exclude exotic submarkets + require liquidity (the model's universe)")
    ap.add_argument("--min-prints", type=int, default=50)
    ap.add_argument("--one-dp", action="store_true",
                    help="one decision point per symbol (first >=0.80 cross) — kills per-print "
                         "weighting, matches the intl R2 test and the calibration check")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    import pyarrow.parquet as pq

    files = sorted(f for f in glob.glob(f"{ARCHIVE}/*.parquet")
                   if a.d0 <= os.path.basename(f)[:10] <= a.d1)
    print(f"US T&S days: {len(files)}  ({a.d0} .. {a.d1})   curated={a.curated}")
    # build per-symbol price paths across all days
    paths = defaultdict(list)
    nprints = defaultdict(int)
    niche_of = {}
    for f in files:
        t = pq.read_table(f, columns=["Transaction Time", "Symbol", "Last Price"]).to_pandas()
        t["ep"] = t["Transaction Time"].astype("int64") / 1e9
        for sym, px, ep in zip(t["Symbol"].values, t["Last Price"].values, t["ep"].values):
            if sym not in niche_of:
                niche_of[sym] = grade_niche(sym)
            if niche_of[sym] in TRADEABLE and not (a.curated and is_exotic(sym)):
                paths[sym].append((float(ep), float(px)))
                nprints[sym] += 1
        sys.stdout.write(f"\r  loaded {os.path.basename(f)}  symbols={len(paths):,}")
        sys.stdout.flush()
    print()
    if a.curated:
        paths = {s: p for s, p in paths.items() if nprints[s] >= a.min_prints}
        print(f"  curated to standard, liquid (>={a.min_prints} prints): {len(paths):,} symbols")

    clf = pickle.load(open(MODEL, "rb"))
    rng = np.random.default_rng(SEED)

    # decision points + frozen-model prediction
    rowsX, meta = [], []
    n_sym = n_settled = 0
    for sym, path in paths.items():
        if len(path) < 5:
            continue
        path.sort()
        n_sym += 1
        won = settle(path)
        if won is None:
            continue
        n_settled += 1
        cand = [j for j, (t, p) in enumerate(path) if p >= BAND_LO]
        if not cand:
            continue
        if a.one_dp:
            pick = [cand[0]]                      # first >=0.80 cross only
        else:
            pick = cand if len(cand) <= MAX_DP else list(rng.choice(cand, MAX_DP, replace=False))
        n = niche_of[sym]
        for j in sorted(pick):
            rowsX.append(featurize(path, j, n))
            meta.append((event_key(sym), won, path[j][1], n))
    print(f"symbols with a path: {n_sym:,}   settled (unambiguous): {n_settled:,}   "
          f"decision points: {len(rowsX):,}")
    if len(rowsX) < 50:
        sys.exit("too few US decision points — widen the date range")

    X = np.array(rowsX, float)
    pw = clf.predict_proba(X)[:, 1]
    ev = np.array([pw[i] - meta[i][2] - fee_us(meta[i][2]) for i in range(len(meta))])

    def rows(thr):
        out = []
        for i in range(len(meta)):
            evk, won, p, n = meta[i]
            if ev[i] > thr:
                out.append((evk, won - p - fee_us(p) - a.haircut, p))
        return out

    W = 100
    print("\n" + "=" * W)
    print(f"US-NATIVE BACKTEST — FROZEN model on REAL US prices "
          f"(US fee theta=0.06 + {a.haircut*100:.1f}c haircut, event-clustered)")
    print("=" * W)
    print(f"{'policy':>30s} {'NET c/sh':>9s} {'net 95% CI':>17s} | "
          f"{'ROI/turn':>9s} {'ROI 95% CI':>18s} {'p':>6s} {'ev':>5s} {'sigs':>6s}")
    print("-" * W)
    for lab, thr in [("BLIND: every US favourite", -9), ("MODEL EV>+0.00", 0.0),
                     ("MODEL EV>+0.01", 0.01), ("MODEL EV>+0.03", 0.03)]:
        r = boot_event(rows(thr))
        if not r:
            print(f"{lab:>30s}   -- too few events --")
            continue
        print(f"{lab:>30s} {r['net']*100:>+8.3f}c "
              f"[{r['net_lo']*100:+.2f},{r['net_hi']*100:+.2f}] | "
              f"{r['roi']*100:>+8.2f}% [{r['roi_lo']*100:+.2f}%,{r['roi_hi']*100:+.2f}%] "
              f"{r['p']:>6.3f} {r['n_ev']:>5,} {r['n_rows']:>6,}")

    print("\n  This is the frozen intl-trained model, judged on the US venue's OWN tape end to end.")
    print("  If MODEL ROI LB > 0 here, the port is VALIDATED, not merely plausible.")

    # ---- BIAS-ROBUST TRANSFER TEST: model-selected MINUS blind, PAIRED by event.
    # Both legs inherit the same T&S settlement-completeness bias (winners that stop trading below
    # 0.95 get dropped), so DIFFERENCING inside the event cancels it -- exactly the intl matched-
    # blind logic. A positive surplus = the model's selection transfers, bias-robustly.
    print("\n" + "=" * W)
    print("BIAS-ROBUST TRANSFER: model-selected MINUS blind, PAIRED per event (cancels the shared")
    print("settlement bias). The absolute level is biased; this DIFFERENCE is not.")
    print("=" * W)
    by_ev_all = defaultdict(list)
    for i in range(len(meta)):
        evk, won, p, n = meta[i]
        by_ev_all[evk].append((won - p - fee_us(p) - a.haircut, ev[i]))
    for thr in (0.00, 0.01, 0.03):
        diffs = []
        for evk, items in by_ev_all.items():
            sel = [nt for nt, e in items if e > thr]
            blind = [nt for nt, e in items]
            if sel and blind:
                diffs.append(float(np.mean(sel) - np.mean(blind)))
        if len(diffs) < 15:
            print(f"  EV>{thr:+.2f}: too few paired events")
            continue
        d = np.array(diffs)
        rng2 = np.random.default_rng(SEED)
        bs = d[rng2.integers(0, len(d), (4000, len(d)))].mean(1)
        print(f"  EV>{thr:+.2f}: surplus {d.mean()*100:>+6.3f}c/share "
              f"[{np.percentile(bs,2.5)*100:+.2f},{np.percentile(bs,97.5)*100:+.2f}] "
              f"p={float((bs<=0).mean()):.3f}  ({len(d):,} events)")
    print("  (surplus > 0 => the model picks better than blind ON US, independent of the label bias)")


if __name__ == "__main__":
    main()
