#!/usr/bin/env python3
"""
PER-SPORT EDGE TRACKER — softness vs skill, watched as samples grow (2026-07-02).

The consensus-favorite edge lives on ~4 correlated summer days (World Cup soccer + Wimbledon
tennis). The open question is whether it's a REAL selection skill that will survive in the sharp,
efficient markets of the fall (NFL Sept, NBA Oct) or a soft-tournament artifact. This instrument
answers it forward, per sport, by DECOMPOSING each sport's consensus-favorite edge into:

  market SOFTNESS  = blind-favorite edge = event-clustered mean(won − entry) over the `_blind`
                     pool's favorites (entry ≥ 0.6) in that sport. Large ⇒ favorites underpriced
                     ⇒ soft/inefficient market (World Cup). ≤0 ⇒ sharp market (MLB/NFL/NBA).
  selection SKILL  = surplus = event-clustered mean((won − entry) − blind_edge[regime,band]) for
                     the strategy — how much the CONSENSUS adds beyond the blind favorite at the
                     same price. This is the part that must survive in efficient markets.
  total edge       = softness-at-band + skill = mean(won − entry) for the strategy.

Skill in an EFFICIENT sport (softness ≈ 0) is the strong evidence the edge is real; a big total
edge that is all softness is just riding a soft market and will not transfer. Everything is
event-clustered at the match super-key, at-fire entry (COALESCE(initial_mean_price, mean_price)).
Sports below the N floor read INDETERMINATE — the whole point is to watch them cross it.

New sports auto-classify by slug prefix (nfl/nba/ncaaf/ncaab/nhl already wired for the fall).

Self-test:  ./sport_edge_tracker.py --self-test   (soft-no-skill vs efficient-skill fixtures)
Live:       ./sport_edge_tracker.py               [--strategy favorite]
"""

import csv
import io
import math
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
FAV_FLOOR = 0.6         # "favorite" price floor for the softness measure
N_FLOOR = 20            # events below this read INDETERMINATE (pre-registered)
DEFAULT_STRATS = ("favorite", "elite_fresh_fav")

# slug-prefix → sport. Fall sports pre-wired so they classify the moment they appear.
# Soccer league codes: `fifwc`/`world` (World Cup + props) and the machine-generated league
# stems. AMBIGUOUS stems (`col`~Colorado politics, `chi`~Chicago, `swe`, `ucl`) are matched
# WITH a trailing hyphen so they only catch the structured `col-fc-...` slug form, never a
# `colorado-...` question slug. Audited against the live book 2026-07-09 (see check_coverage).
_SOCCER_HYPHEN = ("col-", "chi-", "ucl-", "swe-", "world-", "bra-", "arg-", "por-", "ned-",
                  "bel-", "crint-", "ligue-", "erediv-", "mar1-", "bra2-")
REGIMES = [
    (("atp", "wta", "itf"), "tennis"),
    (("fifwc", "epl", "uefa", "mls", "laliga", "seriea", "bund"), "soccer"),
    (_SOCCER_HYPHEN, "soccer"),
    (("mlb", "kbo", "npb"), "mlb"),
    (("nfl", "ncaaf"), "nfl/cfb"),
    (("nba", "ncaab", "wnba"), "nba/cbb"),
    (("nhl",), "nhl"),
    # esports — `co-` is Call of Duty (trap: NOT Colorado); kept AFTER soccer so `col-` wins.
    (("lol", "val", "cs2", "csgo", "cs-", "dota2", "dota", "r6", "co-", "ow-", "rl-"), "esports"),
    (("btc", "eth", "sol", "xrp", "bnb", "doge", "bitcoin", "ethereum"), "crypto"),
]


def sport(slug):
    s = (slug or "")
    for pre, name in REGIMES:
        if s.startswith(pre):
            return name
    return "other"


def check_coverage(strat="favorite", max_other_sports_pct=5.0):
    """Measurement-integrity assertion: of the is_sports rows this strategy fired, at most
    `max_other_sports_pct`% may fall through to 'other'. A regression here means a new league
    prefix is unmapped and is silently corrupting the soccer/ex-soccer split. Read-only."""
    import csv as _csv
    import io as _io
    import subprocess as _sp
    sql = (f"SELECT slug, event_slug, is_sports FROM consensus_signals "
           f"WHERE strategy='{strat}' AND resolved")
    out = _sp.run(PG + ["-c", sql], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("psql failed:\n" + out.stderr)
    n_sports = n_other = 0
    misses = {}
    for r in _csv.DictReader(_io.StringIO(out.stdout)):
        if r["is_sports"] not in ("t", "true", "1"):
            continue
        n_sports += 1
        slug = r["event_slug"] or r["slug"] or ""
        if sport(slug) == "other":
            n_other += 1
            pre = slug.split("-", 1)[0]
            misses[pre] = misses.get(pre, 0) + 1
    pct = 100.0 * n_other / n_sports if n_sports else 0.0
    ok = pct <= max_other_sports_pct
    print(f"sport-map coverage · {strat}: {n_sports} sports rows, {n_other} → 'other' "
          f"({pct:.1f}%, cap {max_other_sports_pct}%) → {'OK' if ok else 'FAIL'}")
    if misses:
        print("  unmapped sports prefixes:", dict(sorted(misses.items(), key=lambda kv: -kv[1])))
    return ok


def band(p):
    if p < 0:
        return 0
    if p >= 1:
        return 6
    return int(p * 5) + 1


def clustered(pairs):
    """(ev, value) → (event-clustered mean, n_events)."""
    ev = defaultdict(list)
    for e, v in pairs:
        ev[e].append(v)
    if not ev:
        return float("nan"), 0
    return sum(sum(v) / len(v) for v in ev.values()) / len(ev), len(ev)


SQL = """
SELECT strategy, event_slug, slug, condition_id,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals WHERE resolved
"""


def fetch():
    out = subprocess.run(PG + ["-c", SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
        rows.append(r)
    return rows


def evk(r):
    return super_event(r["event_slug"], r["slug"]) or r["condition_id"]


def analyze(rows, strat):
    """Return per-sport dict(events, ev_per_day, win_pct, softness, skill, total, status)."""
    blind = [r for r in rows if r["strategy"] == "_blind"]
    # regime×band blind baseline (for skill) and regime favorite softness (for softness)
    rb = defaultdict(list)
    soft = defaultdict(list)
    for r in blind:
        sp = sport(r["slug"] or r["event_slug"])
        rb[(sp, band(r["entry"]))].append(r["won"] - r["entry"])
        if r["entry"] >= FAV_FLOOR:
            soft[sp].append((evk(r), r["won"] - r["entry"]))
    rb_edge = {k: sum(v) / len(v) for k, v in rb.items()}
    softness = {sp: clustered(pairs)[0] for sp, pairs in soft.items()}

    srows = [r for r in rows if r["strategy"] == strat]
    out = {}
    by_sport = defaultdict(list)
    for r in srows:
        by_sport[sport(r["slug"] or r["event_slug"])].append(r)
    for sp, rs in by_sport.items():
        total, n_ev = clustered([(evk(r), r["won"] - r["entry"]) for r in rs])
        skill, _ = clustered([(evk(r), (r["won"] - r["entry"]) - rb_edge.get((sp, band(r["entry"])), 0.0)) for r in rs])
        win_pct = 100.0 * sum(r["won"] for r in rs) / len(rs)
        days = len({r["day"] for r in rs})
        status = "OK" if n_ev >= N_FLOOR else "INDETERMINATE (N<%d)" % N_FLOOR
        out[sp] = dict(events=n_ev, ev_per_day=n_ev / max(days, 1), win_pct=win_pct,
                       softness=softness.get(sp, float("nan")), skill=skill, total=total, status=status)
    return out


SKILL_MIN = 0.03   # a meaningful selection-skill surplus (points over the blind favorite)


def verdict(soft, skill, n_ev):
    if n_ev < N_FLOOR or math.isnan(skill):
        return "watch (thin sample)"
    if skill < SKILL_MIN:                       # no meaningful skill (handles skill≈0 either sign)
        if soft >= 0.02:
            return "NO skill — edge is soft-market only (won't transfer)"
        return "no edge (skill≈0 in an efficient market)"
    if abs(soft) < 0.02:                         # real skill AND market is efficient
        return "REAL skill in an EFFICIENT market ★ (transfer signal)"
    return "skill + soft market (both help)"


def run_live(strat):
    rows = fetch()
    res = analyze(rows, strat)
    print(f"PER-SPORT EDGE · strategy={strat} · match-level · at-fire · softness=blind-fav edge, "
          f"skill=surplus over blind fav · N floor {N_FLOOR}\n")
    print(f"{'sport':<10} {'ev':>4} {'ev/d':>5} {'win%':>5} {'softness':>9} {'skill':>7} {'total':>7}  interpretation")
    order = sorted(res, key=lambda s: -res[s]["events"])
    for sp in order:
        d = res[sp]
        v = verdict(d["softness"], d["skill"], d["events"])
        soft = f"{d['softness']:+.1%}" if not math.isnan(d["softness"]) else "  n/a"
        print(f"{sp:<10} {d['events']:>4} {d['ev_per_day']:>5.1f} {d['win_pct']:>4.0f}% "
              f"{soft:>9} {d['skill']:>+6.1%} {d['total']:>+6.1%}  {v}")
    print("\nread: SKILL is the durable number — it must survive where SOFTNESS≈0 (efficient markets:")
    print("mlb now, nfl/cfb Sept, nba/cbb Oct). A big TOTAL that is all SOFTNESS won't transfer.")
    print("INDETERMINATE sports are the watch-list; re-run as their samples cross the N floor.")
    return 0


# --- self-test -------------------------------------------------------------------------------
def _mk(strategy, sp_slug, entry, won, i, day="d"):
    return dict(strategy=strategy, event_slug=f"{sp_slug}-{i}", slug=f"{sp_slug}-{i}",
                condition_id=f"{sp_slug}-{i}", entry=entry, won=won, day=day)


def _self_test():
    ok = True
    rows = []
    # SOFT sport (fifwc): blind favorites at 0.80 win 92% → soft (+12% blind edge); strategy just
    # tracks the pool (won like the pool) → skill ≈ 0.
    rows += [_mk("_blind", "fifwc-a-b", 0.80, 1 if i < 46 else 0, i) for i in range(50)]  # 92% win
    rows += [_mk("favorite", "fifwc-a-b", 0.80, 1 if i < 23 else 0, 1000 + i) for i in range(25)]  # 92% too
    # EFFICIENT sport (mlb): blind favorites at 0.80 win 80% → efficient (~0 blind edge); strategy
    # wins 92% → real skill (+12% over blind).
    rows += [_mk("_blind", "mlb-c-d", 0.80, 1 if i < 40 else 0, i) for i in range(50)]  # 80% win
    rows += [_mk("favorite", "mlb-c-d", 0.80, 1 if i < 23 else 0, 2000 + i) for i in range(25)]  # 92% win
    res = analyze(rows, "favorite")
    soc, mlb = res["soccer"], res["mlb"]
    # soccer: softness high (~+12%), skill ~0
    c1 = soc["softness"] > 0.08 and abs(soc["skill"]) < 0.03
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] SOFT sport: softness {soc['softness']:+.1%} (hi), skill {soc['skill']:+.1%} (~0)")
    # mlb: softness ~0, skill high (~+12%)
    c2 = abs(mlb["softness"]) < 0.03 and mlb["skill"] > 0.08
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] EFFICIENT sport: softness {mlb['softness']:+.1%} (~0), skill {mlb['skill']:+.1%} (hi)")
    # verdict routing
    c3 = "EFFICIENT" in verdict(mlb["softness"], mlb["skill"], mlb["events"]) and \
         "soft-market" in verdict(soc["softness"], soc["skill"], soc["events"]).lower()
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] verdicts route: mlb→transfer-signal, soccer→soft-only")
    # sport classifier incl. fall sports
    c4 = sport("nfl-kc-buf-2026-09-10") == "nfl/cfb" and sport("nba-lal-bos-2026-10-22") == "nba/cbb"
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] fall sports classify (nfl→nfl/cfb, nba→nba/cbb)")
    # N floor → INDETERMINATE
    c5 = res["mlb"]["status"] == "OK" and analyze(rows[:60] + [_mk("favorite", "nfl-x", 0.8, 1, 9)], "favorite").get("nfl/cfb", {}).get("status", "").startswith("INDETERMINATE")
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] N floor: thin sport → INDETERMINATE")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    if "--coverage" in sys.argv:
        sys.exit(0 if check_coverage() else 1)
    strat = DEFAULT_STRATS[0]
    if "--strategy" in sys.argv:
        strat = sys.argv[sys.argv.index("--strategy") + 1]
    sys.exit(run_live(strat))
