#!/usr/bin/env python3
"""
WEATHER-SLIPPAGE (Weather Capitalize run, 2026-07-13).

THE number that decides whether weather is executable: what is left of the edge AFTER you eat the book.

Every realizable figure so far assumed we buy at the TOUCH (best ask). With a median of ~$54 resting
within 1c of the touch, a real stake does NOT get the touch — it walks the book and pays a VWAP. This
measures that walk on LIVE cert-band weather books and converts it into the honest objective:

  entry(S) = VWAP of buying $S of the favorite, walking the real ask ladder
  ROI-turn(S) = mean pnl(entry(S), won) / entry(S), day-clustered, cluster-robust LB

Method: sample the live cert-band book SHAPE (the ask ladder relative to the touch), then apply that
shape to each historical graded pick (whose mid + outcome we know from the validated CLOB basis). This
keeps the OUTCOMES honest (real, resolved) while pricing the entry at a real, measured book.

A strategy is executable only where the LB at the stake we intend to trade still clears the bar. If the
edge only survives at $25/signal, say so plainly — that is a capacity verdict, not a strategy.

Read-only; no orders. Self-test: ./weather_slippage.py --selftest
"""
import json, sys, time, urllib.request, statistics as st
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C
import weather_verdict as V
from weather_grade import grade
from collections import defaultdict

CLOB = "https://clob.polymarket.com"
LO, HI = 0.71, 0.90
STAKES = [10, 25, 50, 100, 250, 500, 1000]
CHAMP_FLOOR = 0.056


def _get(u):
    r = urllib.request.Request(u, headers={"User-Agent": "weather-slip-readonly/1"})
    with urllib.request.urlopen(r, timeout=25) as resp:
        return json.loads(resp.read())


def vwap_walk(ladder, stake_usd):
    """Walk the ask ladder buying `stake_usd` notional. Returns (vwap, filled_usd).
    ladder: [(price, size_shares)] ascending in price. Unfilled remainder => filled<stake."""
    spent = shares = 0.0
    for px, sz in ladder:
        cap = px * sz
        take = min(cap, stake_usd - spent)
        if take <= 0:
            break
        spent += take
        shares += take / px
        if spent >= stake_usd - 1e-9:
            break
    if shares <= 0:
        return None, 0.0
    return spent / shares, spent


def sample_book_shapes(limit=1200):
    """Live cert-band weather ask ladders, normalised to the touch: [(px - best_ask, size_shares)]."""
    conds = [r[0] for r in C.q(f"""SELECT DISTINCT condition_id FROM trader_fills
        WHERE slug ~ 'highest-temperature' AND ts > now() - interval '3 days' LIMIT {limit};""")]
    shapes = []
    for cid in conds:
        try:
            m = _get(f"{CLOB}/markets/{cid}")
        except Exception:
            continue
        if m.get("closed"):
            continue
        for t in m.get("tokens", []):
            tid = t.get("token_id")
            if not tid:
                continue
            time.sleep(0.04)
            try:
                b = _get(f"{CLOB}/book?token_id={tid}")
            except Exception:
                continue
            asks, bids = b.get("asks") or [], b.get("bids") or []
            if not asks or not bids:
                continue
            lad = sorted(((float(a["price"]), float(a["size"])) for a in asks), key=lambda x: x[0])
            ba = lad[0][0]
            bb = max(float(x["price"]) for x in bids)
            mid = (ba + bb) / 2.0
            if not (LO <= mid <= HI):
                continue
            shapes.append({"half_spread": ba - mid,
                           "ladder_rel": [(px - ba, sz) for px, sz in lad]})
    return shapes


def entry_for(pick_mid, shape, stake):
    """Price this pick's entry using a real measured book shape anchored at the pick's mid."""
    ba = pick_mid + shape["half_spread"]
    lad = [(ba + d, sz) for d, sz in shape["ladder_rel"]]
    vwap, filled = vwap_walk(lad, stake)
    return vwap, filled


def build():
    shapes = sample_book_shapes()
    if not shapes:
        return {"n_shapes": 0, "verdict": "NO LIVE CERT-BAND BOOKS"}
    picks = [p for p in grade(offline=True)[0] if LO <= p["atfire"] < HI]
    pool = [p for p in grade(offline=True, min_backers=1)[0] if LO <= p["atfire"] < HI]

    def curve(ps, label):
        out = []
        for S in STAKES:
            rows, unfilled = [], 0
            for i, p in enumerate(ps):
                sh = shapes[i % len(shapes)]          # deterministic round-robin over measured books
                vwap, filled = entry_for(p["atfire"], sh, S)
                if vwap is None or vwap >= 0.999:
                    continue
                if filled < S * 0.999:
                    unfilled += 1
                if filled <= 0:
                    continue
                rows.append({"entry": vwap, "won": p["won"], "cluster": p["cluster"],
                             "condition_id": p["condition_id"], "slug": p["slug"],
                             "filled": filled})
            if len(rows) < 5:
                continue
            r = C.roi_lb(rows)
            bw = defaultdict(set)
            for x in rows:
                bw[V.week_of(x["cluster"])].add(x["cluster"])
            dom = max(bw, key=lambda w: len(bw[w]))
            rest = [x for x in rows if V.week_of(x["cluster"]) != dom]
            rl = C.roi_lb(rest)
            avg_fill = st.mean([x["filled"] for x in rows])
            out.append({
                "stake_usd": S,
                "mean_entry_vwap": round(st.mean([x["entry"] for x in rows]), 4),
                "mean_filled_usd": round(avg_fill, 2),
                "fill_ratio": round(avg_fill / S, 3),
                "frac_partially_unfilled": round(unfilled / len(rows), 3),
                "roi_turn_LB": None if not r or r.get("lb") is None else round(r["lb"], 4),
                "roi_turn_point": None if not r else round(r["point"], 4),
                "lodo_held_out_LB": None if not rl or rl.get("lb") is None else round(rl["lb"], 4),
                "clears_champion_floor": bool(r and r.get("lb") is not None and r["lb"] > CHAMP_FLOOR),
                "expected_gross_per_day_usd": round(avg_fill * (len(ps) / len({p["cluster"] for p in ps}))
                                                    * (r["lb"] if r and r.get("lb") else 0), 2),
            })
        return {"cell": label, "n_picks": len(ps), "curve": out}

    hs = [s["half_spread"] for s in shapes]
    return {
        "as_of": "2026-07-13", "run": "weather capitalize — SLIPPAGE (executable edge vs stake)",
        "n_live_book_shapes": len(shapes),
        "measured_half_spread": {"median": round(st.median(hs), 4), "mean": round(st.mean(hs), 4)},
        "method": "walk the REAL measured ask ladder for $S; outcomes are the real resolved picks; "
                  "entry is the VWAP a taker actually gets. Day-clustered cluster-robust LB + LODO.",
        "consensus_arm": curve(picks, "weather_fav consensus (>=3)"),
        "BLIND_BAND_rule": curve(pool, "blind band (1+ sharp favorite) — the recommended form"),
        "champion_floor": CHAMP_FLOOR,
        "read": "the stake at which the LB stops clearing the champion floor IS the capacity ceiling. "
                "Beyond it, weather is not executable at that size — regardless of the headline edge.",
    }


def selftest():
    lad = [(0.80, 100), (0.81, 100)]      # $80 then $81
    v, f = vwap_walk(lad, 80)
    if abs(v - 0.80) > 1e-9 or abs(f - 80) > 1e-9:
        print(f"FAIL vwap touch {v} {f}"); return 1
    v, f = vwap_walk(lad, 161)            # eats both levels
    if abs(f - 161) > 1e-6 or not (0.80 < v < 0.81):
        print(f"FAIL vwap walk {v} {f}"); return 1
    v, f = vwap_walk(lad, 1000)           # book exhausted -> partial
    if f >= 1000:
        print("FAIL partial fill"); return 1
    print("selftest PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    (Path(__file__).resolve().parent.parent / "reports" / "WEATHER-SLIPPAGE.json").write_text(
        json.dumps(rep, indent=2))
    print(f"live book shapes: {rep['n_live_book_shapes']}  half-spread median {rep['measured_half_spread']['median']}")
    for key in ("consensus_arm", "BLIND_BAND_rule"):
        c = rep[key]
        print(f"\n{c['cell']}  (n={c['n_picks']})")
        print("  stake   VWAP    filled   fill%   ROI-turn LB   LODO      $/day    clears champ")
        for r in c["curve"]:
            print(f"  ${r['stake_usd']:<5} {r['mean_entry_vwap']:.4f}  ${r['mean_filled_usd']:>7.2f} "
                  f"{r['fill_ratio']*100:5.1f}%   {(r['roi_turn_LB'] or 0)*100:+7.2f}%   "
                  f"{(r['lodo_held_out_LB'] or 0)*100:+6.2f}%  ${r['expected_gross_per_day_usd']:>7.0f}   "
                  f"{'YES' if r['clears_champion_floor'] else 'no'}")
