#!/usr/bin/env python3
"""
REGIME-TYPE CLASSIFIER — the one genuinely new primitive of the regime-persistence run.

Defines ONCE (imported by regime_edge / regime_persistence / regime_net_edge / readiness_ledger)
the recurring/expiring/unknown split that the whole run's stationarity verdict rests on. A
`recurring` regime is a claim that the regime REPEATS and is the ONLY label that can count toward
certification; `expiring` is a bounded tournament / single-elim / playoff / World Cup / Wimbledon /
one-off; `unknown` is unclassifiable and is treated as EXPIRING for the conservative verdict.
Mislabeling an expiring regime as recurring would smuggle a soccer artifact into a "persists"
verdict — the exact failure this run exists to prevent. When in doubt: `unknown`.

Rules are FROZEN in reports/PREREG_20260704T191458Z_regime_persistence.md §2 (cited, identical
values). Deterministic; no network / no DB in the pure `classify_regime` path (the sport_category
comes from the existing market_taxonomy.category derivation — NOT a new bucket). The `--live` audit
DOES read the archive so a human can eyeball every edge case before trusting the verdict.

Modes:
  ./regime_classify.py --selftest   # WC→expiring, regular-season→recurring, playoff→expiring,
                                    # unclassifiable→unknown(→expiring); tennis/esports→unknown.
  ./regime_classify.py [--live]     # audit: every populated regime in the archive → type + rule fired.
"""

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_taxonomy import category  # the EXISTING sport/category derivation (do not reinvent)

# PREREG §7: single source of truth for the time-block unit (composed by callers).
PREREG = "reports/PREREG_20260704T191458Z_regime_persistence.md"

# --- Rule E: EXPIRING keyword markers (bounded events). Highest priority. (PREREG §2 Rule E) ---
# Matched on the lower-cased `slug + " " + title`. Word-ish boundaries where a bare token would be
# too greedy; substring where the token is unambiguous (fifwc, wimbledon, ...).
_EXPIRING_KW = [
    "world-cup", "worldcup", "world cup", "fifwc", "-wc-",
    "wimbledon", "roland", "us open", "usopen", "australian open", "ausopen",
    "french open", "grand slam", "-slam", "olympic",
    "playoff", "play-off", "postseason", "knockout", "elimination",
    "round-of", "round of", "semifinal", "semi-final", "quarterfinal", "quarter-final",
    "-final", "grand final", "finals", "-cup", "championship",
    "worlds", "-msi-", "major", "super bowl", "superbowl", "world series",
]

# --- Rule R: recurring venues (PREREG §2 Rule R) ---
_RECURRING_CATS = {"mlb", "nba/cbb", "nfl/cfb", "nhl", "crypto", "econ/other", "politics/elections"}
# regular-league soccer slug prefixes (recurring when NOT flagged by Rule E)
_RECURRING_SOCCER_PREFIXES = ("epl", "mls", "laliga", "seriea", "bund", "ligue", "erediv",
                              "mar1", "bra2", "kbo", "npb")

RECURRING, EXPIRING, UNKNOWN = "recurring", "expiring", "unknown"


def _norm(slug, title):
    return ((slug or "") + " " + (title or "")).lower()


def _match_expiring(text):
    for kw in _EXPIRING_KW:
        if kw in text:
            return kw
    return None


def explain(slug, title, sport=None):
    """Return (regime_type, rule_tag, detail) for one market — the audit-legible form."""
    cat = sport if sport is not None else category(slug, title)
    text = _norm(slug, title)
    s = (slug or "").lower().strip()

    kw = _match_expiring(text)
    if kw is not None:
        return EXPIRING, "E", f"keyword '{kw}'"

    if cat in _RECURRING_CATS:
        return RECURRING, "R", f"recurring category '{cat}'"
    if s.startswith(_RECURRING_SOCCER_PREFIXES):
        return RECURRING, "R", f"regular-league soccer prefix"

    # Rule U — tennis (slam-ambiguous slugs), esports (league/tournament-ambiguous), other.
    why = "tennis: no tournament marker in slug (Wimbledon-era → conservative)" if cat == "tennis" \
        else ("esports: no league/tournament marker" if cat == "esports"
              else f"unclassifiable category '{cat}'")
    return UNKNOWN, "U", why


def classify_regime(sport, market_type, slug, title):
    """(regime_id, regime_type). regime_id = the sport_category (the month is composed by callers).
    market_type is accepted for signature completeness (the type rule does not currently split on it,
    but keeping it in the signature lets a future prop-vs-main split slot in without a caller change)."""
    cat = sport if sport is not None else category(slug, title)
    rtype, _, _ = explain(slug, title, cat)
    return cat, rtype


def is_expiring_for_verdict(regime_type):
    """unknown is treated as expiring for the conservative verdict (PREREG §2)."""
    return regime_type != RECURRING


# --------------------------------------------------------------------------------------------
PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
_AUDIT_SQL = """
SELECT slug, event_slug, title,
       to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM') AS month
FROM consensus_signals WHERE resolved AND strategy='favorite'
"""


def _fetch_audit():
    import csv
    import io
    import subprocess
    out = subprocess.run(PG + ["-c", _AUDIT_SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def run_audit():
    rows = _fetch_audit()
    # group by sport_category; within each, count by type + record the rule that fired + a sample.
    by_cat = defaultdict(lambda: {"n": 0, "types": defaultdict(int), "rules": defaultdict(int),
                                  "months": set(), "sample": None, "detail": None})
    for r in rows:
        cat = category(r["slug"], r["title"])
        rtype, rule, detail = explain(r["slug"], r["title"], cat)
        d = by_cat[cat]
        d["n"] += 1
        d["types"][rtype] += 1
        d["rules"][rule] += 1
        d["months"].add(r["month"])
        if d["sample"] is None:
            d["sample"] = r["event_slug"] or r["slug"]
            d["detail"] = detail
    print("REGIME-TYPE CLASSIFIER · live audit of the favorite archive · rules frozen in")
    print(f"  {PREREG} §2 (recurring counts toward certification; unknown→treated expiring)\n")
    hdr = f"{'sport_category':<18}{'n':>5}{'type':>11}{'rule':>6}{'months':>8}  sample / rule detail"
    print(hdr); print("-" * (len(hdr) + 20))
    # order: recurring first (the ones that matter), then expiring, then unknown
    order = {RECURRING: 0, EXPIRING: 1, UNKNOWN: 2}
    def dom_type(d):
        return max(d["types"].items(), key=lambda kv: kv[1])[0]
    for cat in sorted(by_cat, key=lambda c: (order[dom_type(by_cat[c])], -by_cat[c]["n"])):
        d = by_cat[cat]
        t = dom_type(d)
        rule = max(d["rules"].items(), key=lambda kv: kv[1])[0]
        mixed = "" if len(d["types"]) == 1 else f"  (MIXED: {dict(d['types'])})"
        print(f"{cat:<18}{d['n']:>5}{t:>11}{rule:>6}{len(d['months']):>8}  {d['sample']}  [{d['detail']}]{mixed}")
    print("-" * (len(hdr) + 20))
    rec = [c for c in by_cat if dom_type(by_cat[c]) == RECURRING]
    exp = [c for c in by_cat if dom_type(by_cat[c]) == EXPIRING]
    unk = [c for c in by_cat if dom_type(by_cat[c]) == UNKNOWN]
    print(f"RECURRING sport-categories (can certify): {sorted(rec) or 'NONE'}")
    print(f"EXPIRING  (reported, excluded from verdict): {sorted(exp) or 'NONE'}")
    print(f"UNKNOWN   (treated expiring, conservative): {sorted(unk) or 'NONE'}")
    print("\nread: only RECURRING regimes count toward the ≥2-disjoint-non-expiring bar. Soccer=World")
    print("Cup and tennis=Wimbledon are EXPIRING by construction — the crux of the stationarity test.")
    return 0


# --------------------------------------------------------------------------------------------
def _selftest():
    ok = True
    cases = [
        # (slug, title, sport_or_None, want_type, label)
        ("fifwc-bra-jpn-2026-07-01", "Brazil vs Japan", "soccer", EXPIRING, "World Cup soccer"),
        ("fifwc-bra-jpn-2026-07-01-exact-score-2-0", "Exact Score 2-0", "soccer", EXPIRING, "WC deriv"),
        ("mlb-laa-sea-2026-06-30", "Angels vs Mariners", "mlb", RECURRING, "MLB regular season"),
        ("kbo-lg-ssg-2026-07-02", "LG vs SSG", "mlb", RECURRING, "KBO regular league"),
        ("btc-updown-5m-1782", "Bitcoin Up or Down", "crypto", RECURRING, "crypto ongoing"),
        ("nba-lal-bos-2026-06-01-playoffs-game7", "Lakers vs Celtics Game 7", "nba/cbb", EXPIRING, "NBA playoff"),
        ("nba-lal-bos-2026-10-22", "Lakers vs Celtics", "nba/cbb", RECURRING, "NBA regular season"),
        ("atp-jong-hijikata-2026-06-29", "Jong vs Hijikata", "tennis", UNKNOWN, "tennis (slam-ambiguous)"),
        ("lol-t1-tl2-2026-07-01", "T1 vs TL", "esports", UNKNOWN, "esports (league-ambiguous)"),
        ("who-visited-island", "Will X be confirmed?", "other", UNKNOWN, "unclassifiable→unknown"),
        ("uefa-champions-league-final-2026", "Champions League Final", "soccer", EXPIRING, "cup final"),
        ("epl-ars-che-2026-08-15", "Arsenal vs Chelsea", "soccer", RECURRING, "EPL regular league"),
    ]
    for slug, title, sport, want, label in cases:
        _, got = classify_regime(sport, "main", slug, title)
        good = got == want
        ok = ok and good
        _, rule, detail = explain(slug, title, sport)
        print(f"  [{'ok' if good else 'FAIL'}] {label:<28} → {got:<9} (rule {rule}: {detail})  want {want}")

    # conservative-treatment contract: unknown is treated as expiring for the verdict.
    c_u = is_expiring_for_verdict(UNKNOWN) and is_expiring_for_verdict(EXPIRING) \
        and not is_expiring_for_verdict(RECURRING)
    ok = ok and c_u
    print(f"  [{'ok' if c_u else 'FAIL'}] is_expiring_for_verdict: unknown&expiring→True, recurring→False")

    # determinism: same input twice → same output.
    c_d = classify_regime("soccer", "main", "fifwc-x-y-2026-07-01", "X vs Y") == \
        classify_regime("soccer", "main", "fifwc-x-y-2026-07-01", "X vs Y")
    ok = ok and c_d
    print(f"  [{'ok' if c_d else 'FAIL'}] deterministic (idempotent)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        sys.exit(run_audit())
