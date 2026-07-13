#!/usr/bin/env python3
"""
WEATHER-CLOB (Weather Deepen run, WS4 enabler, 2026-07-12).

Bounded, cached, READ-ONLY Polymarket CLOB reader — the ONLY new "ingestion" this run adds, and it is
strictly scoped to weather markets (condition_ids handed in by the weather grader). It exists to break
ONE blocker: the decisive gate (real LODO-by-week over ≥2 disjoint weeks) cannot run because week-28
(july 6-12) weather convergence is not RESOLVED in our DB — the trader_fills resolver is a 42k-deep
oldest-first FIFO throttled at 200 conds/cycle, so recent weather is head-of-line-blocked, and the
`_blind` at-fire-mid snapshot pipeline lagged too (only 11/557 week-28 picks have a mid). The market
OUTCOMES and at-fire mids ARE public on the CLOB. This reads them directly (bounded to the weather
conditions), so the certification math is unblocked WITHOUT touching the shared resolution pipeline,
without a migration, and without waiting on the FIFO. It writes NOTHING to the DB and places NO orders.

Two reads per weather condition, both cached to disk (reports/cache/weather_clob.json) so re-runs are
instant and a reaped long run is fully salvageable from the cache:
  outcome(cond)      -> {"winner": <outcome_index or None if open>, "tokens": {oi: token_id}}
  mid_at(tid, ts)    -> the CLOB mid at/nearest-BEFORE ts (prices-history) — the honest at-fire mid,
                        NO look-ahead (last tick with t <= ts). None if no history.

Self-test (offline, no network): ./weather_clob.py --selftest
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

CLOB = "https://clob.polymarket.com"
_CACHE_PATH = Path(__file__).resolve().parent.parent / "reports" / "cache" / "weather_clob.json"
_SLEEP = 0.10


class WeatherClob:
    def __init__(self, cache_path=_CACHE_PATH, offline=False):
        self.cache_path = Path(cache_path)
        self.offline = offline
        self.cache = {"markets": {}, "hist": {}}
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text())
                self.cache.setdefault("markets", {})
                self.cache.setdefault("hist", {})
            except Exception:
                pass
        self._dirty = 0
        self.fetches = 0

    def _get(self, url):
        if self.offline:
            raise RuntimeError("offline")
        time.sleep(_SLEEP)
        self.fetches += 1
        req = urllib.request.Request(url, headers={"User-Agent": "weather-deepen-readonly/1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    def outcome(self, condition_id):
        """{'winner': oi|None, 'tokens': {oi: token_id}, 'closed': bool, 'end_iso': str}. Cached.
        winner=None if open. `end_iso` (the market's own resolution time) is what lets a NEUTRAL
        reference price be taken at a fixed LEAD before resolution — with no sharp anchoring."""
        c = self.cache["markets"].get(condition_id)
        if c is not None and ("end_iso" in c or c.get("err")):
            return c
        try:
            d = self._get(f"{CLOB}/markets/{condition_id}")
        except Exception:
            # NEGATIVE-CACHE the failure. Many weather conds 404 on /markets; without this they were
            # re-fetched on EVERY run (~2.4k retries/run), which is what made the first WS2 pass slow.
            res = {"winner": None, "tokens": {}, "closed": False, "err": True}
            self.cache["markets"][condition_id] = res
            self._maybe_flush()
            return res
        toks = {}
        winner = None
        for i, t in enumerate(d.get("tokens", [])):
            toks[str(i)] = t.get("token_id")
            if t.get("winner") is True:
                winner = i
        res = {"winner": winner, "tokens": toks, "closed": bool(d.get("closed")),
               "end_iso": d.get("end_date_iso") or d.get("end_date") or ""}
        self.cache["markets"][condition_id] = res
        self._maybe_flush()
        return res

    def mid_at(self, token_id, ts_epoch):
        """CLOB mid at/nearest-BEFORE ts_epoch (no look-ahead). Cached per token (full history)."""
        h = self.cache["hist"].get(token_id)
        if h is None:
            try:
                resp = self._get(f"{CLOB}/prices-history?market={token_id}&interval=max&fidelity=1")
                h = [[int(x["t"]), float(x["p"])] for x in resp.get("history", [])]
            except Exception:
                h = []
            self.cache["hist"][token_id] = h
            self._maybe_flush()
        if not h:
            return None
        ts = int(ts_epoch)
        prior = [p for t, p in h if t <= ts]
        return prior[-1] if prior else h[0][1]

    def _maybe_flush(self):
        self._dirty += 1
        if self._dirty >= 25:
            self.flush()

    def flush(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache))
        self._dirty = 0


def selftest():
    ok = True
    wc = WeatherClob(cache_path="/tmp/_wc_selftest.json", offline=True)
    wc.cache["markets"]["cond"] = {"winner": 1, "tokens": {"0": "a", "1": "b"}, "closed": True,
                                   "end_iso": "2026-07-13T00:00:00Z"}
    wc.cache["hist"]["b"] = [[100, 0.5], [200, 0.8], [300, 0.9]]
    if wc.outcome("cond")["winner"] != 1:
        print("FAIL outcome"); ok = False
    if wc.mid_at("b", 250) != 0.8:
        print(f"FAIL mid_at nearest-before: {wc.mid_at('b', 250)}"); ok = False
    if wc.mid_at("b", 50) != 0.5:
        print("FAIL mid_at pre-first fallback"); ok = False
    if wc.mid_at("b", 999) != 0.9:
        print("FAIL mid_at last"); ok = False
    if wc.mid_at("missing", 100) is not None:
        print("FAIL mid_at empty"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print("WeatherClob is a library — import it. Run --selftest to verify.")
