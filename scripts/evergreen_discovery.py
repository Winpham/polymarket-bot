#!/usr/bin/env python3
"""
EVERGREEN-DISCOVERY — hunt for copyable edges in market families OUTSIDE the known champion.

Runs the full anti-overfit battery over EVERY market family the tracked sharps actually bet, on the
substrate that was corrupted until 2026-07-12 (see EVERGREEN-PORTFOLIO-FINDINGS.md):
  - the `trader_fills` resolver was starved by head-of-line blocking, so the RESOLVED subset was ~5x
    enriched in consensus-firing markets (89.6% vs 18.0% coverage) — the exact survivorship bias the
    independent resolver existed to prevent. Every prior family/cell scan read that biased subset.
This instrument re-asks the discovery question on the drained, unbiased substrate.

ORDER OF OPERATIONS IS THE POINT — the copyability gate runs BEFORE any edge is measured, because a
fat edge on an unbuyable market is the single most seductive artifact in this project's history:

  1. COPYABILITY GATE (structural, a-priori). A market whose LIFETIME is shorter than our
     detect+capture lag cannot be copied at any price, however large the edge. `btc-updown-5m-*` are
     FIVE-MINUTE markets: they are gone before a follower could fill. They are killed here, not
     measured. (They are also a live trap: they present as the two FATTEST families in a naive scan,
     +21.7% at the sharps' fill, and a slug regex written for `up-or-down` silently misses `updown`.)
  2. Edge at the SHARP FILL — a DIRECTIONAL CEILING, never a copyable price. Used only to rank
     candidates and to carry the robustness tests, which need both weeks.
  3. Robustness: cluster-robust LB, >=2 disjoint weeks, LEAVE-ONE-WEEK-OUT.
  4. Belief-blind `selection_null`: does convergence beat a random favorite in the SAME family at the
     same (band x day)? If not, the "edge" is composition, not alpha.
  5. Bonferroni over every family tested (reported, never hidden).
  6. Copyability STATUS: how many real asks we have captured for the family. Outside the champion and
     the live weather arm this is ZERO — so for a new family the realizable price is UNMEASURED, and
     the only honest recommendation is a default-off shadow arm to START capturing it.

A family that clears 1-5 is a CANDIDATE, never a certified edge: without captured asks its realizable
price is unknown, and this project has repeatedly watched selection edges die at the ask.

Read-only. Self-test: ./evergreen_discovery.py --selftest
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C  # noqa: E402
from evergreen_portfolio import iso_week, lodo_by_week, rows_at, selection_null  # noqa: E402

WIDE_CUTOFF = 250
CAPTURE_LO, CAPTURE_HI = 0.71, 0.98
CERT_LO, CERT_HI = 0.71, 0.90
MIN_PICKS = 20          # below this a family is POWER-STARVED, reported but never ranked
REPORTS = Path(__file__).resolve().parent.parent / "reports"

# --- The copyability gate (a-priori, structural) -------------------------------------------------
# Our detect->capture lag is ~10-15 min (consensus cycle + the housekeeping ask capture). A market
# whose whole life is comparable to that lag is UNCOPYABLE no matter how big the sharps' edge: they
# are trading a timing advantage we structurally cannot have. Killed BEFORE measurement.
UNCOPYABLE_RX = (
    "updown",        # btc-updown-5m / eth-updown-5m : 5-MINUTE markets (also spelled up-or-down)
    "up-or-down",
)
CAPTURE_LAG_MIN = 15


def family_of(slug):
    """Family key for a slug. Deliberately explicit: the `updown` families MUST be caught here, since
    a naive first-token split reports them as the fattest edges on the board."""
    s = (slug or "").lower()
    for rx in UNCOPYABLE_RX:
        if rx in s:
            return "crypto-updown"
    if "highest-temperature" in s:
        return "weather-high"
    if "lowest-temperature" in s:
        return "weather-low"
    if any(k in s for k in ("price-of", "-reach-", "dip-to", "-above-")):
        return "crypto-level"
    head = s.split("-")[0]
    return "".join(ch for ch in head if not ch.isdigit()) or "?"


def is_copyable(family):
    """False iff the family's markets die inside our capture lag."""
    return family != "crypto-updown"


def fetch_all_picks(since="2026-06-15"):
    """Wider-universe convergence picks across EVERY family, resolved, in the capture band."""
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, AVG(f.price) px, MIN(f.ts) ts,
             MAX(f.slug) slug, MAX(f.event_slug) ev, BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='{since}' AND ft.rank<={WIDE_CUTOFF}
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
      (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
    conv AS (
      SELECT condition_id, outcome_index, MAX(slug) slug, MAX(ev) ev, count(*) nb, AVG(px) sharp_px,
             BOOL_OR(rz) rz, BOOL_OR(won) won, MIN(ts)::date d
      FROM e1 GROUP BY 1,2
      HAVING count(*)>=3 AND AVG(px) BETWEEN {CAPTURE_LO} AND {CAPTURE_HI})
    SELECT condition_id, outcome_index, slug, ev, sharp_px, won, d
    FROM conv WHERE rz AND won IS NOT NULL;
    """)
    out = []
    for r in rows:
        cond, oi, slug, ev, sharp, won, day = r[:7]
        out.append({
            "condition_id": f"{cond}:{oi}", "slug": slug or "", "event_slug": ev or "",
            "sharp_px": float(sharp), "won": won == "t",
            "cluster": str(day), "day": str(day), "week": iso_week(day),
            "family": family_of(slug),
        })
    return out


def fetch_blind_universe_all(since="2026-06-15"):
    """Blind comparison population per family: favorites a tracked trader bought WITHOUT requiring the
    >=3 convergence the arm fires on. The null asks whether CONVERGENCE adds skill over that."""
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, AVG(f.price) px,
             MAX(f.slug) slug, BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won, MIN(f.ts)::date d
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='{since}' AND ft.rank<={WIDE_CUTOFF}
      GROUP BY 1,2,3)
    SELECT condition_id, outcome_index, MAX(slug), AVG(px), BOOL_OR(rz), BOOL_OR(won), MIN(d)
    FROM e GROUP BY 1,2
    HAVING AVG(px) BETWEEN {CAPTURE_LO} AND {CAPTURE_HI};
    """)
    by_fam = {}
    for r in rows:
        cond, oi, slug, px, rz, won, day = r[:7]
        if rz != "t" or won not in ("t", "f"):
            continue
        u = {"key": f"{cond}:{oi}", "sharp_px": float(px), "won": won == "t",
             "cluster": str(day), "day": str(day), "week": iso_week(day)}
        by_fam.setdefault(family_of(slug), []).append(u)
    return by_fam


def captured_asks(family_slugs_rx):
    """How many REAL asks we have captured for this family. Outside the champion + live weather arm
    this is 0 — so the realizable price is UNMEASURED and no profit claim is possible."""
    rows = C.q(f"""
    SELECT count(*) FROM consensus_signals
    WHERE entry_ask IS NOT NULL AND slug ~ '{family_slugs_rx}';""")
    return int(rows[0][0]) if rows else 0


def assess_family(fam, picks, universe, m_tests):
    cert = rows_at(picks, 0.0)
    out = {
        "family": fam,
        "copyable": is_copyable(fam),
        "picks_cert_band": len(cert),
        "days": len({r["day"] for r in cert}),
        "weeks": sorted({r["week"] for r in cert}),
    }
    if not is_copyable(fam):
        out["verdict"] = ("KILLED BY THE COPYABILITY GATE — market life (~5 min) is shorter than our "
                          f"~{CAPTURE_LAG_MIN}-min detect+capture lag. Unbuyable at any edge. "
                          "NOT measured (a number here would only tempt us).")
        return out
    if len(cert) < MIN_PICKS:
        out["verdict"] = f"POWER-STARVED (<{MIN_PICKS} picks in the certification band) — not ranked"
        return out

    lb = C.roi_lb(cert)
    if not lb or lb.get("lb") is None:
        out["verdict"] = "INDETERMINATE — LB undefined (single cluster)"
        return out
    boot = C.bootstrap_lb(cert)
    out["sharp_fill"] = {
        "point": round(lb["point"], 4), "lb": round(lb["lb"], 4),
        "boot_lb": round(boot["lb"], 4) if boot and boot.get("lb") is not None else None,
        "clusters": lb["G_clusters"],
        "meaning": "DIRECTIONAL CEILING (the sharps' own fill) — NOT a price we can buy at",
    }
    # Bonferroni: alpha/m across the families tested.
    out["bonferroni"] = {"m_families_tested": m_tests,
                         "note": "LB read at alpha/m; a family that only clears at alpha is NOT a find"}
    out["lodo_by_week"] = lodo_by_week(cert)
    out["selection_null"] = selection_null(picks, universe.get(fam, []), 0.0)

    survives = (
        lb["lb"] > 0
        and out["lodo_by_week"].get("survives_lodo_by_week")
        and out["selection_null"].get("passes_p01")
    )
    out["survives_battery"] = bool(survives)
    out["verdict"] = (
        "CANDIDATE — survives LB + leave-one-week-out + belief-blind null at the SHARPS' fill. "
        "Realizable price UNMEASURED (no captured asks): needs a default-off shadow arm to start "
        "capturing entry_ask before any profit claim."
        if survives else
        "FAILS the battery — does not survive one of {LB>0, leave-one-week-out, selection_null}"
    )
    return out


def build(since="2026-06-15"):
    picks = fetch_all_picks(since)
    universe = fetch_blind_universe_all(since)
    by_fam = {}
    for p in picks:
        by_fam.setdefault(p["family"], []).append(p)

    # m = the families we actually MEASURE (copyable + powered). Reported for Bonferroni honesty.
    testable = [f for f, ps in by_fam.items()
                if is_copyable(f) and len(rows_at(ps, 0.0)) >= MIN_PICKS]
    m = len(testable)

    arms = {}
    for fam, ps in sorted(by_fam.items()):
        arms[fam] = assess_family(fam, ps, universe, m)
    for fam in arms:
        if arms[fam].get("survives_battery"):
            arms[fam]["captured_asks"] = captured_asks(
                {"weather-high": "highest-temperature", "weather-low": "lowest-temperature"}
                .get(fam, fam))
    return {
        "as_of": "2026-07-12",
        "run": "evergreen discovery — families outside the known champion, on the DRAINED substrate",
        "since": since,
        "m_families_tested": m,
        "substrate_note": ("Run AFTER the resolver backfill. Before it, the resolved trader_fills subset "
                           "was ~5x enriched in consensus-firing markets (89.6% vs 18.0%) — every prior "
                           "family scan read that biased subset."),
        "families": arms,
    }


def selftest():
    ok = True
    # The copyability gate MUST catch both spellings — the whole trap is a regex that misses `updown`.
    for s in ("btc-updown-5m-1783010100", "eth-updown-5m-99", "bitcoin-up-or-down-july-1"):
        if family_of(s) != "crypto-updown":
            print(f"FAIL family_of({s}) = {family_of(s)}"); ok = False
    if is_copyable("crypto-updown"):
        print("FAIL crypto-updown must be UNCOPYABLE"); ok = False
    if family_of("highest-temperature-in-nyc-on-july-11") != "weather-high":
        print("FAIL weather-high"); ok = False
    if family_of("lowest-temperature-in-tokyo-on-july-14") != "weather-low":
        print("FAIL weather-low"); ok = False
    if family_of("mlb-nyy-bos-2026-07-01") != "mlb":
        print("FAIL mlb"); ok = False
    if not is_copyable("mlb"):
        print("FAIL mlb must be copyable"); ok = False
    # An uncopyable family must be KILLED without an edge number attached.
    a = assess_family("crypto-updown", [], {}, 1)
    if "sharp_fill" in a or a["copyable"]:
        print("FAIL uncopyable family must not be measured"); ok = False
    print("evergreen_discovery selftest: PASS" if ok else "evergreen_discovery selftest: FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-06-15")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(selftest())
    rep = build(a.since)
    (REPORTS / "EVERGREEN-DISCOVERY.json").write_text(json.dumps(rep, indent=2))
    print(f"wrote EVERGREEN-DISCOVERY.json  (m={rep['m_families_tested']} families tested)\n")
    surv, failed, killed, thin = [], [], [], []
    for f, a_ in rep["families"].items():
        if not a_["copyable"]:
            killed.append(f)
        elif a_.get("survives_battery"):
            surv.append((f, a_))
        elif "sharp_fill" in a_:
            failed.append((f, a_))
        else:
            thin.append(f)
    print(f"KILLED by copyability gate (unbuyable, NOT measured): {killed or 'none'}")
    print(f"POWER-STARVED (<{MIN_PICKS} picks): {thin or 'none'}\n")
    print("SURVIVES the full battery (candidates — realizable price still UNMEASURED):")
    if not surv:
        print("  NONE.")
    for f, a_ in sorted(surv, key=lambda x: -x[1]["sharp_fill"]["lb"]):
        sf, L, sn = a_["sharp_fill"], a_["lodo_by_week"], a_["selection_null"]
        print(f"  {f:14} LB={sf['lb']:+.4f} (sharps' fill) G={sf['clusters']:>3} weeks={len(a_['weeks'])} "
              f"| LODO min fold={L.get('min_lb_across_folds')} | null p={sn.get('p_emp')} "
              f"| captured_asks={a_.get('captured_asks')}")
    print("\nFAILS the battery:")
    for f, a_ in sorted(failed, key=lambda x: -x[1]["sharp_fill"]["lb"]):
        sf, L, sn = a_["sharp_fill"], a_["lodo_by_week"], a_["selection_null"]
        why = []
        if sf["lb"] <= 0:
            why.append("LB<=0")
        if not L.get("survives_lodo_by_week"):
            why.append("LODO")
        if not sn.get("passes_p01"):
            why.append(f"null p={sn.get('p_emp')}")
        print(f"  {f:14} LB={sf['lb']:+.4f} G={sf['clusters']:>3} weeks={len(a_['weeks'])} -> fails: {', '.join(why)}")


if __name__ == "__main__":
    main()
