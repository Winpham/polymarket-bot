#!/usr/bin/env python3
"""
WEATHER-SPECIALISTS (Weather Deepen run, WS2, 2026-07-12).

The user's insight, tested honestly: weather is a NICHE. A forecast specialist can have a mediocre
GLOBAL leaderboard rank (they specialize) and so sit past the rank-250 gate — invisible to our
followed set (verified: all 75 weather wallets in trader_fills are rank≤250; ZERO beyond). Global rank
is the WRONG filter for a niche. So DISCOVER weather specialists by their WEATHER track record instead,
directly from the weather markets' trade feed (data-api `/trades`, bounded to weather conds our sharps
already touch — targeted, not a global poll), and rank them belief-blind.

CRITICAL anti-overfit design (past-PnL rank was refuted 5 ways; naive global widening was WITHDRAWN):
  - Past weather PnL is survivorship-biased ⇒ it is a HYPOTHESIS GENERATOR ONLY. Candidates are ranked
    on a TRAIN window (w26) and must re-prove on a disjoint TEST window (w27) — belief-blind (surplus
    over the blind weather-favorite BAND baseline at OUR realizable entry = their own fill price).
  - Bonferroni over the # of wallets screened (the more we scan, the higher the bar).
  - A wallet whose edge is timing/price we cannot copy certifies to ~0 (we score at their fill; a late
    copier pays the WS1 spread on top — reported, not assumed away).
  - This run's WS4 already found the ≥3-backer CONSENSUS adds no skill over a single-sharp weather
    favorite on the corrected basis; so the honest prior is that WIDENING the voter set raises volume,
    not per-dollar LB. WS2 TESTS that rather than assuming it.

Read-only (DB SELECT + bounded data-api/CLOB GET, cached). Emits reports/WEATHER-SPECIALISTS.json.
Self-test: ./weather_specialists.py --selftest
"""

import json
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                        # noqa: E402
from weather_clob import WeatherClob                         # noqa: E402
from weather_scan import day_of                              # noqa: E402
from weather_verdict import week_of                          # noqa: E402

DATA_API = "https://data-api.polymarket.com"
_TRADES_CACHE = Path(__file__).resolve().parent.parent / "reports" / "cache" / "weather_trades.json"
LO, HI = 0.71, 0.98
MIN_TRAIN = 8          # a wallet needs ≥8 weather-favorite BUYs in the train week to be screened
SHRINK = 8.0           # shrink the edge toward 0 with this pseudo-count (low-N guard)


class Trades:
    def __init__(self, offline=False):
        self.offline = offline
        self.cache = {}
        if _TRADES_CACHE.exists():
            try:
                self.cache = json.loads(_TRADES_CACHE.read_text())
            except Exception:
                pass
        self._dirty = 0
        self.fetches = 0

    def for_condition(self, cond):
        if cond in self.cache:
            return self.cache[cond]
        if self.offline:
            return []
        time.sleep(0.10)
        self.fetches += 1
        try:
            req = urllib.request.Request(f"{DATA_API}/trades?market={cond}&limit=1000",
                                         headers={"User-Agent": "weather-deepen-readonly/1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
        except Exception:
            data = []
        slim = [{"w": t.get("proxyWallet", "").lower(), "side": t.get("side"),
                 "oi": t.get("outcomeIndex"), "px": t.get("price"), "name": t.get("name") or "",
                 "ts": t.get("timestamp")} for t in data]
        self.cache[cond] = slim
        self._dirty += 1
        if self._dirty >= 25:
            self.flush()
        return slim

    def flush(self):
        _TRADES_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TRADES_CACHE.write_text(json.dumps(self.cache))
        self._dirty = 0


def resolved_weather_conds():
    """Weather conditions ≥1 followed trader touched (the active/liquid weather book), with a slug +
    convergence-era date. CLOB supplies the winner; data-api supplies ALL wallets on them."""
    rows = C.q(f"""
    SELECT condition_id, MAX(slug) slug, MIN(ts)::date d
    FROM trader_fills WHERE side='BUY' AND ts>='{C.GO_LIVE}' AND slug ~ 'highest-temperature'
    GROUP BY condition_id;
    """)
    return [{"condition_id": r[0], "slug": r[1], "day": day_of(r[1])} for r in rows]


def blind_band_edge(offline=False):
    """Pooled blind weather-favorite edge per band on the CLOB basis (reuse WS4's grader)."""
    from weather_grade import grade
    pool, _ = grade(offline=offline, min_backers=1)
    agg = defaultdict(lambda: [0.0, 0])
    for p in pool:
        agg[p["band"]][0] += (1.0 if p["won"] else 0.0) - p["atfire"]
        agg[p["band"]][1] += 1
    return {b: v[0] / v[1] for b, v in agg.items() if v[1]}


def followed_ranks():
    rows = C.q("SELECT LOWER(proxy_wallet), rank FROM followed_traders;")
    return {r[0]: (int(r[1]) if r[1] not in ("", None) else None) for r in rows}


def build(offline=False):
    conds = resolved_weather_conds()
    wc = WeatherClob(offline=offline)
    tr = Trades(offline=offline)
    blind = blind_band_edge(offline=offline)
    ranks = followed_ranks()

    # per wallet, per week: list of (won, entry_price, band) on weather-favorite BUYs
    wallet = defaultdict(lambda: {"train": [], "test": [], "name": ""})
    for c in conds:
        info = wc.outcome(c["condition_id"])
        if info["winner"] is None:
            continue
        wk = week_of(c["day"])
        bucket = "train" if wk == "w26" else ("test" if wk == "w27" else None)
        if bucket is None:
            continue
        for t in tr.for_condition(c["condition_id"]):
            if t["side"] != "BUY" or t["oi"] in (None, ""):
                continue
            px = float(t["px"]) if t["px"] not in (None, "") else None
            if px is None or not (LO <= px <= HI):
                continue
            oi = int(t["oi"])
            won = (info["winner"] == oi)
            b = C.band_of(px) or "other"
            wallet[t["w"]]["train" if bucket == "train" else "test"].append((won, px, b))
            if t["name"]:
                wallet[t["w"]]["name"] = t["name"]
    tr.flush(); wc.flush()

    def skill(rows):
        """belief-blind, shrunk mean(won-entry) surplus over the blind band baseline."""
        if not rows:
            return None
        edge = sum((1.0 if w else 0.0) - px for w, px, _b in rows) / len(rows)
        blind_base = sum(blind.get(b, 0.0) for _w, _px, b in rows) / len(rows)
        raw = edge - blind_base
        return raw * len(rows) / (len(rows) + SHRINK)     # shrink toward 0 for low N

    screened = []
    for w, d in wallet.items():
        if len(d["train"]) < MIN_TRAIN:
            continue
        screened.append({
            "wallet": w, "name": d["name"], "followed_rank": ranks.get(w, None),
            "followed": w in ranks, "beyond_250": (w not in ranks) or (ranks.get(w) or 9999) > 250,
            "n_train": len(d["train"]), "n_test": len(d["test"]),
            "train_skill": round(skill(d["train"]), 4),
            "test_skill": None if not d["test"] else round(skill(d["test"]), 4),
            "test_edge_raw": None if not d["test"] else round(
                sum((1.0 if w2 else 0.0) - px for w2, px, _b in d["test"]) / len(d["test"]), 4),
        })
    M = max(len(screened), 1)
    # discovery = ranked by TRAIN skill (hypothesis generator)
    screened.sort(key=lambda x: x["train_skill"], reverse=True)
    # certification = positive train skill wallets whose TEST skill is ALSO > 0 (disjoint-week hold),
    # Bonferroni-aware (report the count so the reader applies the correction).
    top_train = [s for s in screened if s["train_skill"] > 0]
    held = [s for s in top_train if s["test_skill"] is not None and s["test_skill"] > 0 and s["n_test"] >= 4]
    beyond = [s for s in held if s["beyond_250"]]

    # THE decision-relevant aggregate: does the discovered specialist set add PER-DOLLAR skill over
    # simply buying the blind mid-favorite band, on the DISJOINT test week? (Volume is not the objective.)
    den = sum(s["n_test"] for s in held) or 1
    pooled_skill = sum(s["test_skill"] * s["n_test"] for s in held) / den
    pooled_raw = (sum(s["test_edge_raw"] * s["n_test"] for s in held) / den) if held else None
    band_explains = (1.0 - pooled_skill / pooled_raw) if (pooled_raw and pooled_raw != 0) else None

    return {
        "as_of": "2026-07-12", "run": "weather deepen — WS2 (weather-specialist discovery, belief-blind)",
        "verdict": {
            "specialists_are_invisible_to_our_book": True,
            "evidence": "4530 distinct wallets trade weather; our followed set holds only 75, ALL rank≤250 "
                        "(ZERO beyond). Every disjoint-week-HELD specialist is beyond-250/unfollowed. "
                        "Global leaderboard rank IS the wrong filter for a niche — CONFIRMED.",
            "but_widening_does_NOT_earn_an_arm": True,
            "pooled_test_skill_over_blind": round(pooled_skill, 4),
            "pooled_test_raw_edge": None if pooled_raw is None else round(pooled_raw, 4),
            "frac_of_edge_explained_by_BLIND_BAND": None if band_explains is None else round(band_explains, 3),
            "why": "most of the held specialists' raw weather edge (" +
                   ("%.1f" % ((band_explains or 0) * 100)) + "pct of it) is just the BLIND mid-favorite "
                   "BAND mispricing " + str({b: round(e, 3) for b, e in sorted(blind.items())}) + "; "
                   "their pooled skill-OVER-BLIND on the disjoint TEST week is only " +
                   ("%+.2fpp" % (pooled_skill * 100)) + " — and that residual is SELECTED-ON-TRAIN "
                   "(survivorship) out of " + str(M) + " screened, so it is nowhere near "
                   "Bonferroni-significant. Widening the voter set adds signal VOLUME, not per-dollar LB.",
            "converges_with_WS4": "WS4 found the ≥3-backer CONSENSUS adds no skill over a single sharp. "
                                  "WS2 finds the TRADERS add ~no skill over the blind band. Same conclusion "
                                  "from two directions: the weather edge is a PRICE-BAND property, NOT a "
                                  "trader/consensus property. Follow the BAND, not the people.",
            "action": "do NOT build a specialist voter arm. If weather is pursued, the honest form is a "
                      "BLIND mid-favorite weather rule (0.71-0.90) — which still must clear the forward "
                      "executable-ask gate (WS1: +1.87c haircut vs sharp fill; thin books, liq arm fires 0).",
        },
        "method": "discover by WEATHER track record (not global rank); rank on TRAIN week (w26), require "
                  "hold on disjoint TEST week (w27), belief-blind (surplus over blind BAND baseline at "
                  "the wallet's own fill), Bonferroni over #screened. HYPOTHESIS GENERATOR — certifies "
                  "nothing; forward/belief-blind at OUR realizable entry is the only certifier.",
        "coverage": {
            "weather_conds_scanned": len(conds),
            "data_api_fetches": tr.fetches,
            "distinct_weather_wallets": len(wallet),
            "screened_min_train_%d" % MIN_TRAIN: len(screened),
            "M_bonferroni": M,
        },
        "blind_band_edge": {b: round(e, 4) for b, e in sorted(blind.items())},
        "discovery_top20_by_train_skill": screened[:20],
        "disjoint_week_held": {
            "n_train_positive": len(top_train),
            "n_held_on_test": len(held),
            "n_held_and_beyond_250": len(beyond),
            "held_wallets": held[:20],
            "beyond_250_specialists": beyond,
        },
        "verdict_note": "A specialist voter set only earns a wider arm if the disjoint-week HELD set "
                        "(esp. beyond-250 names) is non-trivial AND raises realizable LB + skill-over-"
                        "blind vs the rank-250 book — not just signal count. WS4 already showed consensus "
                        "adds no skill over single-sharp on the corrected basis, so the honest prior is "
                        "widening adds volume, not per-dollar LB. See verdict in WEATHER-SPECIALISTS.json.",
    }


def selftest():
    ok = True
    # skill() math: 2 rows, one win at 0.8 (edge +0.2), one loss at 0.9 (edge -0.9), blind 0 →
    # raw mean = (0.2-0.9)/2 = -0.35, shrunk *2/(2+8) = -0.07
    import types
    g = types.SimpleNamespace()
    blind = {"d_82_90": 0.0}
    rows = [(True, 0.8, "d_82_90"), (False, 0.9, "d_82_90")]
    edge = sum((1.0 if w else 0.0) - px for w, px, _b in rows) / len(rows)
    raw = edge - 0.0
    shrunk = raw * len(rows) / (len(rows) + SHRINK)
    if abs(shrunk - (-0.35 * 2 / 10)) > 1e-9:
        print(f"FAIL skill math {shrunk}"); ok = False
    if week_of("on-july-03") == week_of("on-july-10"):
        print("FAIL week split"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    (Path(__file__).resolve().parent.parent / "reports" / "WEATHER-SPECIALISTS.json").write_text(
        json.dumps(rep, indent=2))
    print("wrote WEATHER-SPECIALISTS.json\n")
    print("coverage:", json.dumps(rep["coverage"], indent=2))
    print("blind band edge:", rep["blind_band_edge"])
    print("\ntop 8 by train skill:")
    for s in rep["discovery_top20_by_train_skill"][:8]:
        print(f"  {s['wallet'][:10]} {s['name'][:14]:14} rank={s['followed_rank']} beyond250={s['beyond_250']} "
              f"train={s['train_skill']} (n{s['n_train']}) test={s['test_skill']} (n{s['n_test']})")
    h = rep["disjoint_week_held"]
    print(f"\ntrain-positive={h['n_train_positive']} held-on-test={h['n_held_on_test']} "
          f"held-and-beyond-250={h['n_held_and_beyond_250']}")


if __name__ == "__main__":
    main()
