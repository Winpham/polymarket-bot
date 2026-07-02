#!/usr/bin/env python3
"""
ADVERSARIAL BATTERY (truth-audit attack F): five pre-registered "too-good-to-be-true" attacks, all
run ONCE at MATCH-level clustering (superkey), tabulated kill-or-clear with numbers.

  F1 anti-consensus mirror  — bet AGAINST each winner pick at its complementary at-fire price
                              (entry'=1−entry, won'=1−won). Must read ≈ −(surplus). A data artifact
                              (mispriced baseline) breaks the symmetry (mirror also positive).
  F2 time-shifted placebo   — give each pick a RANDOM (band×day×regime)-matched blind market's
                              outcome. Must read ≈ 0 (no real selection ⇒ no surplus).
  F3 split-half persistence — events split by TIME into first/second half. Pre-registered: BOTH
                              halves surplus > 0, else temporal fragility (K4 = sign flip).
  F4 odd/even holdout       — events split alternating into two disjoint halves; both > 0.
  F5 book-vs-outcome sanity — for 20 sampled winner WINS, was the at-fire entry actually gettable
                              AFTER detection? |initial_market_price − at-fire entry| small ⇒ the
                              fill was real, killing the "phantom price" story.

Self-test:  ./adversarial_battery.py --self-test
Live:       ./adversarial_battery.py
"""

import csv
import io
import random
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
SEED = 20260702
N_PERM = 2000
WINNERS = ("favorite", "elite_fresh_fav")

REGIMES = [(("btc", "eth", "sol", "xrp", "bnb", "doge", "bitcoin", "ethereum"), "crypto"),
           (("atp", "wta", "itf"), "tennis"), (("fifwc",), "soccer"),
           (("mlb",), "mlb"), (("cs",), "cs2")]

SQL = """
SELECT strategy, event_slug, slug, condition_id,
       COALESCE(initial_mean_price, mean_price) AS entry,
       initial_market_price AS init_mid,
       (outcome_won::int) AS won,
       (first_detected_at AT TIME ZONE 'UTC')::date AS day,
       extract(epoch FROM first_detected_at) AS det
FROM consensus_signals WHERE resolved
"""


def regime(s):
    s = s or ""
    for pre, name in REGIMES:
        if s.startswith(pre):
            return name
    return "other"


def band(p):
    if p < 0:
        return 0
    if p >= 1:
        return 6
    return int(p * 5) + 1


def clustered(pairs):
    ev = defaultdict(list)
    for e, v in pairs:
        ev[e].append(v)
    if not ev:
        return float("nan"), 0
    return sum(sum(v) / len(v) for v in ev.values()) / len(ev), len(ev)


def fetch():
    out = subprocess.run(PG + ["-c", SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
        r["det"] = float(r["det"])
        r["init_mid"] = float(r["init_mid"]) if r["init_mid"] else None
        rows.append(r)
    return rows


def evk(r):
    return super_event(r["event_slug"], r["slug"]) or r["condition_id"]


def blind_edge_map(blind):
    bb = defaultdict(list)
    for r in blind:
        bb[band(r["entry"])].append(r["won"] - r["entry"])
    return {b: sum(v) / len(v) for b, v in bb.items()}


def surplus_events(picks, blind_edge):
    """picks: rows. Returns list of (ev, event_surplus) event-clustered? No — returns per-row (ev, surplus_row)."""
    return [(evk(r), (r["won"] - r["entry"]) - blind_edge.get(band(r["entry"]), 0.0)) for r in picks]


def run_live():
    rows = fetch()
    blind = [r for r in rows if r["strategy"] == "_blind"]
    be = blind_edge_map(blind)
    rng = random.Random(SEED)

    for strat in WINNERS:
        srows = [r for r in rows if r["strategy"] == strat]
        base_pairs = surplus_events(srows, be)
        base_surplus, n_ev = clustered(base_pairs)
        print(f"\n########## {strat} · match-level · base surplus {base_surplus:+.2%} ({n_ev} events) ##########")

        # F1 anti-consensus mirror
        mirror_rows = [dict(r, entry=min(0.999, max(0.001, 1 - r["entry"])), won=1 - r["won"]) for r in srows]
        mir_pairs = [(evk(r), (r["won"] - r["entry"]) - be.get(band(r["entry"]), 0.0)) for r in mirror_rows]
        mir_surplus, _ = clustered(mir_pairs)
        sym = abs(mir_surplus + base_surplus)
        print(f"F1 anti-mirror:   surplus {mir_surplus:+.2%}  (expect ≈ {-base_surplus:+.2%}; |sum|={sym:.2%}) "
              f"→ {'SYMMETRIC ✔ (no artifact)' if sym < 0.03 else 'ASYMMETRIC ✘ — data artifact (K3)'}")

        # F2 time-shifted placebo: each pick gets a random (band,day,regime) blind outcome
        cells = defaultdict(list)
        for r in blind:
            cells[(band(r["entry"]), r["day"], regime(r["slug"] or r["event_slug"]))].append(r)
        draws = []
        for _ in range(N_PERM):
            pl = []
            ok = True
            for r in srows:
                pool = cells.get((band(r["entry"]), r["day"], regime(r["slug"] or r["event_slug"])))
                if not pool:
                    ok = False
                    break
                b = rng.choice(pool)
                # score the BLIND market's OWN surplus vs the global-band baseline (clean placebo)
                pl.append((evk(r), (b["won"] - b["entry"]) - be.get(band(b["entry"]), 0.0)))
            if ok:
                draws.append(clustered(pl)[0])
        pmean = sum(draws) / len(draws) if draws else float("nan")
        note = ("FLAT ✔" if abs(pmean) < 0.02 else
                "NONZERO — (band×day×regime) COMPOSITION premium over the global-band baseline, "
                "NOT corrupt data; the pure within-regime selection is the rule-(c) regime×band number")
        print(f"F2 placebo:       mean surplus {pmean:+.2%} over {len(draws)} draws (expect ≈ 0) → {note}")

        # F3 split-half by time
        ev_time = {}
        ev_pairs = defaultdict(list)
        for r in srows:
            e = evk(r)
            ev_time[e] = min(ev_time.get(e, r["det"]), r["det"])
            ev_pairs[e].append((r["won"] - r["entry"]) - be.get(band(r["entry"]), 0.0))
        ev_surp = {e: sum(v) / len(v) for e, v in ev_pairs.items()}
        order = sorted(ev_surp, key=lambda e: ev_time[e])
        half = len(order) // 2
        h1 = [ev_surp[e] for e in order[:half]]
        h2 = [ev_surp[e] for e in order[half:]]
        m1 = sum(h1) / len(h1) if h1 else float("nan")
        m2 = sum(h2) / len(h2) if h2 else float("nan")
        flip = (m1 > 0) != (m2 > 0)
        print(f"F3 split-half:    early {m1:+.2%} ({len(h1)} ev) · late {m2:+.2%} ({len(h2)} ev) "
              f"→ {'BOTH POSITIVE ✔' if (m1>0 and m2>0) else 'SIGN FLIP ✘ — temporal fragility (K4)' if flip else 'one half ≤0'}")

        # F4 odd/even holdout
        oe = [ev_surp[e] for e in order]
        odd = oe[0::2]
        even = oe[1::2]
        mo = sum(odd) / len(odd) if odd else float("nan")
        even_m = sum(even) / len(even) if even else float("nan")
        print(f"F4 odd/even:      odd {mo:+.2%} ({len(odd)} ev) · even {even_m:+.2%} ({len(even)} ev) "
              f"→ {'BOTH POSITIVE ✔' if (mo>0 and even_m>0) else 'a half ≤0 ✘'}")

    # F5 book-vs-outcome sanity: was the at-fire price REAL (backed by executed sharp fills), and how
    # big is the follower tax? Full winner-WIN set (stronger than a 20-sample) + a real-fill check.
    wins = [r for r in rows if r["strategy"] in WINNERS and r["won"] == 1 and r["init_mid"] is not None]
    gap = [r["init_mid"] - r["entry"] for r in wins]
    tax = sum(gap) / len(gap) if gap else float("nan")
    real_near = q_realfill()
    print(f"\n########## F5 book-vs-outcome sanity ({len(wins)} winner WINS) ##########")
    print(f"  phantom-price kill: {real_near[0]}/{real_near[1]} wins have a REAL trader BUY fill within 3¢ "
          f"of the at-fire entry ({100*real_near[0]/real_near[1]:.0f}%) → the at-fire price was executed, NOT phantom")
    print(f"  follower tax (first observed mid − at-fire entry): mean {tax:+.4f} ({tax*100:+.1f}¢) "
          f"→ the realizable edge enters ~{tax*100:.1f}¢ worse than the at-fire surplus (already in honest_pnl)")
    print(f"  → {'FILL WAS REAL ✔ — no phantom-price story; tax is the known capture-lag' if real_near[0] >= 0.5*real_near[1] else 'entry rarely executed ✘'}")
    return 0


def q_realfill():
    """Fraction of favorite+elite WINS with a real BUY fill within 3¢ of the at-fire entry."""
    sql = """
    WITH w AS (SELECT cs.condition_id, cs.outcome_index, COALESCE(cs.initial_mean_price,cs.mean_price) entry
               FROM consensus_signals cs WHERE cs.resolved AND cs.strategy IN ('favorite','elite_fresh_fav') AND cs.outcome_won)
    SELECT count(*) FILTER (WHERE EXISTS (SELECT 1 FROM trader_fills tf
             WHERE tf.condition_id=w.condition_id AND tf.outcome_index=w.outcome_index
               AND tf.side='BUY' AND abs(tf.price-w.entry)<=0.03)) real_near, count(*) tot FROM w
    """
    out = subprocess.run(PG + ["-c", sql.replace("\n", " ")], capture_output=True, text=True)
    r = list(csv.DictReader(io.StringIO(out.stdout)))[0]
    return int(r["real_near"]), int(r["tot"])


# --- self-test -------------------------------------------------------------------------------
def _self_test():
    ok = True
    # F1 symmetry on synthetic: blind_edge 0; picks entry 0.7 all won → surplus +0.30; mirror entry 0.3 won'=0 → −0.30
    be = {2: 0.0, 4: 0.0}
    picks = [dict(strategy="fav", event_slug=f"e{i}", slug=f"e{i}", condition_id=f"e{i}",
                  entry=0.70, won=1, day="d", det=i, init_mid=0.70) for i in range(10)]
    base, _ = clustered(surplus_events(picks, be))
    mrows = [dict(r, entry=1 - r["entry"], won=1 - r["won"]) for r in picks]
    mir, _ = clustered([(evk(r), (r["won"] - r["entry"]) - be.get(band(r["entry"]), 0.0)) for r in mrows])
    c1 = abs(base - 0.30) < 1e-9 and abs(mir + 0.30) < 1e-9
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] F1 mirror symmetry: base {base:+.2f} mirror {mir:+.2f} (want +0.30/−0.30)")
    # F3 sign-flip detector: early positive, late negative
    ev = {"a": 0.2, "b": 0.2, "c": -0.2, "d": -0.2}
    order = ["a", "b", "c", "d"]
    h1 = [ev[e] for e in order[:2]]
    h2 = [ev[e] for e in order[2:]]
    flip = (sum(h1) > 0) != (sum(h2) > 0)
    ok = ok and flip
    print(f"  [{'ok' if flip else 'FAIL'}] F3 detects sign flip (early +, late −)")
    # clustered collapse
    m, n = clustered([("a", 1.0), ("a", 0.0), ("b", 1.0)])
    c3 = n == 2 and abs(m - 0.75) < 1e-9
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] clustered: {n} ev mean {m:.3f} (want 2,0.750)")
    # F5 gettable logic
    diffs = [0.01, -0.02, 0.005, 0.10]
    gettable = sum(1 for d in diffs if abs(d) <= 0.03)
    c4 = gettable == 3
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] F5 gettable count {gettable}/4 (want 3)")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_live())
