#!/usr/bin/env python3
"""PHASE B — map an INTERNATIONAL signal to a POLYMARKET US instrument.

There is NO shared key between the venues: no condition_id, no token_id, nothing joins. The
only thing both sides agree on is the real-world event, so we match on

    (league  x  entity set  x  event date  x  market subtype)

FAIL-CLOSED. Every match carries a confidence; below THRESHOLD we SKIP, never guess. A
signal we cannot map with confidence is a signal we do not trade. An INVERTED map (buying
the other side) is a silent, catastrophic, money-losing bug, so orientation is never
inferred from position — only from an explicit side identifier.

THREE THINGS THAT MADE THE FIRST VERSION UNDERCOUNT (all false negatives — worth knowing,
because a mapper that quietly under-reports coverage will kill a live thesis by accident):

 1. The US venue DOES have exact-score markets. A too-strict slug regex
    (`^(aec|atc)-lg-a-b-date(-win)?$`) rejected `atc-fwc-fra-swe-2026-06-30-exact-score-3-1`
    and `...-fh-exact-score-2-0`, and 200 signals were written off as "US has no such market
    type". False. The suffix is free-form; parse it, don't gate on it.

 2. The venues use DIFFERENT ENTITY CODES.
      intl = ISO-3166 alpha-3      US = FIFA codes
      hrv/prt/nld/che/ury/cvi/cdr  cro/por/ned/sui/uru/cpv/cod
    71 World-Cup signals looked like "no US market" purely because of this.

 3. Tennis codes do not correspond at all: intl truncates the surname (`shapova`, `busta`),
    the US uses first3+last3 (`kammaj` = Kamil Majchrzak). 163 ATP/WTA signals were lost.
    But BOTH venues carry the full names in text (intl `title`, US `question`), so tennis is
    matched on NAMES, not codes.

Usage:  python3 scripts/us_mapper.py          # coverage report over every fired signal
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

import duckdb

US_PARQUET = os.path.expanduser("~/polymarket-archive/us_markets.parquet")
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
THRESHOLD = 0.90

LEAGUE = {
    "fifwc": "fwc", "atp": "atp", "wta": "wta", "mlb": "mlb", "lol": "lol",
    "wnba": "wnba", "nba": "nba", "nfl": "nfl", "nhl": "nhl", "epl": "epl",
    "ucl": "ucl", "uel": "uel", "cs2": "cs2",
}

# intl ISO-3166 alpha-3  ->  US FIFA code. Derived by diffing the two venues' World-Cup
# vocabularies (46 codes each); every entry below is a real country whose two codes differ.
COUNTRY = {
    "hrv": "cro",  # Croatia
    "prt": "por",  # Portugal
    "nld": "ned",  # Netherlands
    "che": "sui",  # Switzerland
    "ury": "uru",  # Uruguay
    "cvi": "cpv",  # Cape Verde
    "cdr": "cod",  # DR Congo
    "kr": "kor",   # Korea (intl truncation)
}

# Tennis-style leagues: entity codes do not correspond, so match on NAMES.
NAME_LEAGUES = {"atp", "wta"}

# The five (and only five) US climate stations. mdw = Chicago MIDWAY, so the US contract
# resolves off a SPECIFIC NWS station — the same city name is not automatically the same
# contract, and any live use must confirm resolution agreement, not just the city.
CITY = {"nyc": "nyc", "new-york": "nyc", "miami": "mia",
        "chicago": "mdw", "los-angeles": "lax", "san-francisco": "sfo"}

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}


@dataclass
class Match:
    us_slug: str | None
    confidence: float
    reason: str


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower())


def name_tokens(s: str) -> set[str]:
    """Distinctive (>=4 char) tokens of a person's name — robust to compound surnames."""
    return {t for t in norm(s).split() if len(t) >= 4}


def intl_bucket_to_us(b: str) -> str | None:
    """82-83f -> gte82lt83f | 93forbelow -> lt94f | 91forhigher -> gte91f.

    The off-by-one on `forbelow` is why this is a function: "93 or below" and "less than 93"
    are DIFFERENT CONTRACTS, and in the tails is exactly where the favourite arm lives.
    """
    b = b.lower().strip("-")
    if m := re.match(r"^(\d+)-(\d+)f$", b):
        return f"gte{m.group(1)}lt{m.group(2)}f"
    if m := re.match(r"^(\d+)f?or(below|lower)$", b):
        return f"lt{int(m.group(1)) + 1}f"
    if m := re.match(r"^(\d+)f?or(higher|above)$", b):
        return f"gte{m.group(1)}f"
    return None  # every °C bucket lands here — those are non-US cities and cannot map anyway


# Country name -> FIFA code, built from the intl titles we actually see. Only needed to read
# the SUBJECT of our own market ("Will Brazil win..." -> bra), never to find the fixture.
NAME2CODE = {
    "brazil": "bra", "morocco": "mar", "mexico": "mex", "south africa": "rsa",
    "korea republic": "kor", "south korea": "kor", "czechia": "cze", "czech republic": "cze",
    "qatar": "qat", "switzerland": "sui", "united states": "usa", "usa": "usa",
    "england": "eng", "germany": "ger", "france": "fra", "spain": "esp", "argentina": "arg",
    "portugal": "por", "netherlands": "ned", "croatia": "cro", "uruguay": "uru",
    "belgium": "bel", "japan": "jpn", "australia": "aus", "canada": "can", "austria": "aut",
    "ecuador": "ecu", "egypt": "egy", "ghana": "gha", "colombia": "col", "senegal": "sen",
    "sweden": "swe", "norway": "nor", "denmark": "den", "poland": "pol", "italy": "ita",
    "paraguay": "par", "panama": "pan", "haiti": "hai", "iran": "irn", "iraq": "irq",
    "jordan": "jor", "saudi arabia": "ksa", "tunisia": "tun", "turkey": "tur",
    "new zealand": "nzl", "uzbekistan": "uzb", "scotland": "sco", "algeria": "alg",
    "cape verde": "cpv", "curacao": "cuw", "ivory coast": "civ", "cote d ivoire": "civ",
    "bosnia and herzegovina": "bih", "dr congo": "cod", "peru": "per", "chile": "chi",
}


def _code_in(text: str, us_ents: frozenset) -> str | None:
    t = norm(text).strip()
    code = NAME2CODE.get(t)
    if code and code in us_ents:
        return code
    best = None
    for name, c in NAME2CODE.items():
        if c in us_ents and name in t:
            if best is None or len(name) > len(best[0]):
                best = (name, c)
    return best[1] if best else None


def us_subject_from_title(title: str, us_ents: frozenset, us_a: str, us_b: str) -> str | None:
    """Which PROPOSITION is our intl market about — 'bra', 'mar', 'draw', 'exact-score-2-1'?

    Read out of our OWN title; never guessed from position. One fixture is many US markets, so
    returning an arbitrary one would be an inverted-map generator. If we cannot establish the
    proposition we return None and the caller SKIPS the signal.
    """
    raw = title or ""
    t = norm(raw)
    if not t:
        return None

    # PERIOD markets are a DIFFERENT PROPOSITION at a different price. One intl event_slug
    # covers full-time AND halftime variants, and the US venue keeps them as separate
    # instruments (`-fh-draw`, `-sh-arg`). The verifier caught exactly this: an intl
    # `...-halftime-result` was being mapped onto the FULL-TIME draw, which is simply the
    # wrong contract. We fail closed and skip rather than map a period market to a full-time
    # one — a wrong map is worse than a missing one.
    if re.search(r"halftime|half time|first half|second half|1st half|2nd half", t):
        return None

    # "Exact Score: Mexico 1 - 1 Ecuador?"  ->  exact-score-{goals_a}-{goals_b}
    # ORIENTATION IS THE WHOLE GAME HERE. The US slug's score is written in ITS OWN (a,b) team
    # order, which need not equal our title's order — so we bind each number to the team it
    # actually sits beside, then re-emit in the US slug's order. Getting this backwards maps
    # "Mexico wins 2-1" onto "Ecuador wins 2-1".
    m = re.search(r"exact score:?\s*(.+?)\s*(\d+)\s*-\s*(\d+)\s*(.+)", raw.lower())
    if m:
        n1, n2 = int(m.group(2)), int(m.group(3))
        c1 = _code_in(m.group(1), us_ents)
        c2 = _code_in(m.group(4), us_ents)
        if not c1 or not c2 or c1 == c2:
            return None
        goals = {c1: n1, c2: n2}
        if us_a not in goals or us_b not in goals:
            return None
        return f"exact-score-{goals[us_a]}-{goals[us_b]}"

    if "draw" in t:
        return "draw"
    if m := re.search(r"will (.+?) win", t):
        return _code_in(m.group(1), us_ents)
    return None


def parse_us(slug: str):
    """-> (kind, league, entities, date, suffix) — suffix is free-form, never gated on."""
    if not slug:
        return None
    if m := re.match(r"^(aec|atc|tsc|asc)-([a-z0-9]+)-([a-z0-9]+)-([a-z0-9]+)-(\d{4}-\d{2}-\d{2})(?:-(.*))?$", slug):
        pre, lg, a, b, d, suf = m.groups()
        return ("sport", lg, frozenset((a, b)), d, suf or "", (a, b))
    if m := re.match(r"^tc-temp-([a-z]+?)(high|low)-(\d{4}-\d{2}-\d{2})-(.+)$", slug):
        city, _hl, d, bucket = m.groups()
        return ("climate", city, frozenset((city,)), d, bucket, (city, city))
    return None


def us_subtype(suffix: str) -> str:
    if "exact-score" in suffix:
        return "fh-exact-score" if suffix.startswith("fh-") else "exact-score"
    return "match"


def parse_intl(event_slug: str):
    if not event_slug:
        return None
    if m := re.match(r"^highest-temperature-in-(.+?)-on-([a-z]+)-(\d{1,2})-(\d{4})", event_slug):
        city, mon, day, yr = m.groups()
        if mon not in MONTHS:
            return None
        return ("climate", city, frozenset((city,)), f"{yr}-{MONTHS[mon]:02d}-{int(day):02d}", "")
    if m := re.match(r"^([a-z0-9]+)-([a-z0-9]+)-([a-z0-9]+)-(\d{4}-\d{2}-\d{2})(?:-(.*))?$", event_slug):
        lg, a, b, d, suf = m.groups()
        sub = "exact-score" if suf and "exact-score" in suf else "match"
        return ("sport", lg, frozenset((a, b)), d, sub)
    return None


def build_index(con):
    rows = con.execute(
        f"SELECT slug, question, sportsMarketTypeV2, closed FROM read_parquet('{US_PARQUET}')"
    ).fetchall()
    by_code: dict[tuple, list] = defaultdict(list)   # (league, entities, date) -> markets
    by_ld: dict[tuple, list] = defaultdict(list)     # (league, date) -> markets  [name matching]
    climate: dict[tuple, list] = defaultdict(list)
    for slug, q, mt, closed in rows:
        p = parse_us(slug)
        if not p:
            continue
        kind, lg, ents, d, suf, order = p
        rec = {"slug": slug, "q": q or "", "type": mt, "closed": closed,
               "suffix": suf, "sub": us_subtype(suf), "ents": ents, "order": order}
        if kind == "climate":
            climate[(lg, d, suf)].append(rec)
        else:
            by_code[(lg, ents, d)].append(rec)
            by_ld[(lg, d)].append(rec)
    return by_code, by_ld, climate


def map_signal(idx, event_slug, market_slug, title):
    by_code, by_ld, climate = idx
    p = parse_intl(event_slug)
    if not p:
        return Match(None, 0.0, "intl slug unparseable")
    kind, lg, ents, d, sub = p

    # ---------- climate ----------
    if kind == "climate":
        city = lg
        if city not in CITY:
            return Match(None, 0.0, "weather: city not listed on the US venue")
        us_city = CITY[city]
        if not market_slug:
            return Match(None, 0.0, "weather: no market slug (cannot read the bucket)")
        pre = f"highest-temperature-in-{city}-on-"
        tail = market_slug[len(pre):] if market_slug.startswith(pre) else ""
        bm = re.match(r"^[a-z]+-\d{1,2}-\d{4}-(.+)$", tail)
        if not bm:
            return Match(None, 0.0, "weather: bucket unreadable")
        us_b = intl_bucket_to_us(bm.group(1))
        if not us_b:
            return Match(None, 0.0, "weather: °C bucket — not expressible on the US venue")
        hit = climate.get((us_city, d, us_b), [])
        if not hit:
            return Match(None, 0.0, "weather: US has no matching temperature rung that day")
        return Match(hit[0]["slug"], 0.95, "weather: city+date+bucket")

    # ---------- sports ----------
    us_lg = LEAGUE.get(lg)
    if not us_lg:
        return Match(None, 0.0, f"league {lg!r} not on the US venue")

    if us_lg in NAME_LEAGUES:
        # ONE intl event_slug covers MANY tennis markets. `atp-sinner-struff-2026-07-07` is the
        # match winner, but ALSO "Set Handicap: Sinner (-1.5) vs Struff (+1.5)" and "Set 1
        # Winner: ...". Mapping those onto the US MATCH-WINNER moneyline is not a missing map,
        # it is a WRONG one — a different proposition at a different price. Only the plain
        # match-winner title may map here; the rest are skipped.
        t = norm(title)
        if re.search(r"set \d|set handicap|game handicap|total games|tie ?break|first set", t):
            return Match(None, 0.0, "tennis: not a match-winner market (set/handicap prop) — skipped")
        # Codes do not correspond; match on the full names both venues carry in text.
        who = title.split(":", 1)[-1] if title else ""
        parts = re.split(r"\bvs\.?\b", who)
        if len(parts) != 2:
            return Match(None, 0.0, "tennis: cannot read both names from the intl title")
        want = [name_tokens(parts[0]), name_tokens(parts[1])]
        if not all(want):
            return Match(None, 0.0, "tennis: intl names unusable")
        cands = []
        for rec in by_ld.get((us_lg, d), []):
            up = re.split(r"\bvs\.?\b", rec["q"])
            if len(up) != 2:
                continue
            got = [name_tokens(up[0]), name_tokens(up[1])]
            fwd = bool(want[0] & got[0]) and bool(want[1] & got[1])
            rev = bool(want[0] & got[1]) and bool(want[1] & got[0])
            if fwd or rev:
                cands.append(rec)
        if not cands:
            return Match(None, 0.0, "tennis: no US market for these players that day")
        if len({c["ents"] for c in cands}) > 1:
            return Match(None, 0.0, "tennis: AMBIGUOUS — multiple US fixtures matched (skipped)")
        return Match(cands[0]["slug"], 0.95, "tennis: league+date+both names")

    us_ents = frozenset(COUNTRY.get(e, e) for e in ents)
    cands = by_code.get((us_lg, us_ents, d), [])
    if not cands:
        return Match(None, 0.0, f"no US {us_lg} market for these entities that day")
    same = [c for c in cands if c["sub"] == sub]
    if not same:
        subs = sorted({c["sub"] for c in cands})
        return Match(None, 0.0, f"{us_lg}: fixture exists but no {sub!r} market (has: {','.join(subs)})")

    # ---- resolve the PROPOSITION, never take cands[0] ----------------------------------
    # One fixture is MANY US markets. A soccer tie maps to three:
    #   atc-fwc-bra-mar-2026-06-13-bra    "Will Brazil win?"
    #   atc-fwc-bra-mar-2026-06-13-mar    "Will Morocco win?"
    #   atc-fwc-bra-mar-2026-06-13-draw   "Will it end in a draw?"
    # Returning an arbitrary one of those is an INVERTED-MAP GENERATOR: we would price
    # "Brazil win" and buy "Morocco win". So we read the SUBJECT out of our own title and
    # demand the US slug's suffix agree. If we cannot establish the subject, we SKIP.
    ua, ub = same[0]["order"]
    subj = us_subject_from_title(title, us_ents, ua, ub)
    if subj is None:
        return Match(None, 0.0, f"{us_lg}: cannot determine the proposition from the intl title")
    exact = [c for c in same if c["suffix"] == subj]
    if not exact:
        # `same` may legitimately hold only the other side(s) of the fixture.
        return Match(None, 0.0, f"{us_lg}: no US market for the proposition {subj!r}")
    if len({c["slug"] for c in exact}) > 1 and sub == "match":
        return Match(None, 0.0, f"{us_lg}: AMBIGUOUS proposition {subj!r} (skipped)")
    return Match(exact[0]["slug"], 0.95, f"{us_lg}: entities+date+subtype+proposition")


def main() -> None:
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{PG_DSN}' AS pg (TYPE postgres, READ_ONLY);")
    idx = build_index(con)
    print(f"US index: {len(idx[0]):,} code keys, {len(idx[2]):,} climate keys\n")

    sigs = con.execute("""
        SELECT strategy, event_slug, slug, title, is_sports
        FROM pg.consensus_signals
        WHERE strategy IN ('favorite','weather_fav','favorite_v2','elite_fresh_fav')
    """).fetchall()

    per = defaultdict(lambda: {"n": 0, "ok": 0})
    reasons = Counter()
    for strat, es, ms, title, _ in sigs:
        m = map_signal(idx, es, ms, title)
        b = per[strat]
        b["n"] += 1
        if m.confidence >= THRESHOLD:
            b["ok"] += 1
        else:
            reasons[m.reason] += 1

    print(f"{'strategy':<18}{'signals':>9}{'MAPPED':>9}{'coverage':>10}")
    print("-" * 46)
    tot = ok = 0
    for s, b in sorted(per.items(), key=lambda x: -x[1]["n"]):
        tot += b["n"]; ok += b["ok"]
        print(f"{s:<18}{b['n']:>9,}{b['ok']:>9,}{100*b['ok']/b['n']:>9.1f}%")
    print("-" * 46)
    print(f"{'TOTAL':<18}{tot:>9,}{ok:>9,}{100*ok/tot:>9.1f}%\n")
    print("WHY SIGNALS FAIL TO MAP:")
    for r, n in reasons.most_common(10):
        print(f"  {n:>6,}  {r}")


if __name__ == "__main__":
    main()
