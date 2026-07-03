#!/usr/bin/env python3
"""
MARKET TAXONOMY — the category × market-type classifier that reaches beyond sports (2026-07-03).

`sport_edge_tracker.py` classifies sports by slug prefix. The softness×skill map needs the SAME
idea extended to the whole book — including the non-sports venues where casual money may pool
(politics/elections) and the softest observed sports (esports) — plus a coarse market-TYPE split
(the headline "main/moneyline" market vs a conditional "derivative/prop"), because softness is a
CELL (category × market-type × band), not a sport.

Two documented, deterministic layers (no fitting):

  category(slug, title):
    1. STRUCTURED slugs (sports, crypto) classify by slug prefix — these are machine-generated
       `<disc>-<t1>-<t2>-<date>-<market>` slugs and are reliable. Traps handled explicitly:
         - `co-...`      = Call of Duty  ⇒ esports   (NOT Colorado)
         - `world-...`   = World Cup props ⇒ soccer
         - `mar1/bra2/chi/kbo/...` league prefixes ⇒ their sport
         - `hype`        = HYPE token    ⇒ crypto
         - `spx`         = S&P 500 up/down ⇒ econ/other (a financial derivative, not a token)
    2. UNSTRUCTURED slugs (question-style: `will-...`, `who-...`, `colorado-...`, `highest-...`)
       classify by TITLE keywords — slug prefixes like "will"/"who" are unreliable (many markets
       start that way), so the human-readable title is primary here:
         - election / nominee / senate / president / primary / vote ⇒ politics/elections
         - temperature / Netflix / Spotify / box-office / film / song ⇒ econ/other (culture/weather)
         - else ⇒ other

  market_type(slug, title):  main | deriv | None
    - main  = the event's single headline outcome: match winner / moneyline / who-advances /
              election nominee-or-winner / crypto up-or-down.
    - deriv = a market CONDITIONAL on a sub-event: exact-score, spread, total/over-under, BTTS,
              corners, cards, first-blood, halftime, scorer, per-game props, temperature bins…
    - None  = unclassifiable (reported as coverage; a low-coverage cell is INDETERMINATE, not a
              silent mislabel).
    Reuses the pre-registered patterns from slice_study.classify_mtype and collapses its fine
    types to the binary the map needs (documented in `_MT_COLLAPSE`).

Softness is measured on the `_blind` favorites in each cell; a category that never fires the
consensus (crypto, per the sport tracker) is an OBSERVATION, not a steerable arm (K4).

Self-test:  ./market_taxonomy.py --self-test   (hand-labeled sample incl. every trap + null cases)
Coverage:   ./market_taxonomy.py               (live per-category volume / resolved / fire counts)
"""

import csv
import io
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# --- layer 1: structured slug-prefix → category (order = most specific first) ---------------
# Every prefix here is a machine-generated discipline stem; the mapping is 1:1 and reliable.
_STRUCT = [
    (("atp", "wta", "itf"), "tennis"),
    # soccer leagues + WC props ("world-"): fifwc = FIFA WC; mar1/bra2/chi/crint = league codes
    (("fifwc", "world", "epl", "uefa", "mls", "laliga", "seriea", "bund",
      "mar1", "bra2", "chi", "crint", "ligue", "erediv"), "soccer"),
    (("mlb", "kbo", "npb"), "mlb"),                       # baseball bucket
    (("nfl", "ncaaf", "cfb"), "nfl/cfb"),
    (("nba", "wnba", "ncaab", "cbb", "bkfiba"), "nba/cbb"),   # bkfiba = FIBA basketball
    (("nhl", "khl", "hok"), "nhl"),                       # hockey bucket
    # esports — `co-` is Call of Duty (trap: NOT Colorado, which is a `colorado-` political slug)
    (("lol", "cs2", "csgo", "cs-", "val", "valorant", "dota2", "dota",
      "r6siege", "r6", "co-", "ow-", "rl-", "kabaddi"), "esports"),
    # crypto tokens (spx/nasdaq handled in layer 2 as econ — index derivs, not tokens)
    (("btc", "eth", "sol", "xrp", "bnb", "doge", "hype", "bitcoin", "ethereum",
      "solana", "ada", "avax", "link", "ltc", "matic", "shib", "pepe", "ton", "trx"), "crypto"),
]

# --- layer 2: title keywords for unstructured (question-style) slugs -------------------------
_POLITICS_KW = re.compile(
    r"\b(election|nominee|senate|senator|president|primary|governor|congress|"
    r"parliament|referendum|impeach|cabinet|nomination|caucus|ballot|"
    r"biden|trump|harris|kamala|hickenlooper|democratic|republican|gop)\b", re.I)
_ECON_CULTURE_KW = re.compile(
    r"\b(temperature|weather|rain|snow|netflix|spotify|box office|gross|film|movie|"
    r"song|album|listeners|s&p|nasdaq|dow|gdp|cpi|inflation|fed|interest rate|"
    r"unemployment|gold|oil|stock)\b", re.I)
# structured non-token index/econ slugs that must NOT read as crypto
_ECON_SLUG = ("spx", "nasdaq", "highest", "lowest", "top-", "top ")


def category(slug, title):
    """Return the pre-registered category label for a market."""
    s = (slug or "").lower().strip()
    t = (title or "")
    # layer-2 econ slugs first (spx/highest/… would otherwise miss the structured table cleanly)
    if s.startswith(_ECON_SLUG):
        return "econ/other"
    for prefixes, name in _STRUCT:      # layer 1: structured disciplines
        if s.startswith(prefixes):
            return name
    # layer 2: unstructured question slugs → title keywords
    if _POLITICS_KW.search(t):
        return "politics/elections"
    if _ECON_CULTURE_KW.search(t):
        return "econ/other"
    return "other"


# --- market-type: collapse slice_study's fine classifier to main | deriv --------------------
# fine type → binary. futures (championship / nominee / "to win the") = the headline outcome of
# its event ⇒ main; every conditional sub-market ⇒ deriv.
_MT_COLLAPSE = {
    "moneyline": "main", "futures": "main",
    "exact-score": "deriv", "spread": "deriv", "over-under": "deriv",
    "prop": "deriv", "draw": "deriv",
}


def _classify_mtype_fine(slug, title):
    """Vendored copy of slice_study.classify_mtype (kept in sync; imported there via patterns).

    Duplicated deliberately so the taxonomy has NO import cycle with slice_study and can be
    self-tested standalone; the two must agree (asserted in the self-test)."""
    s, t = (slug or ""), (title or "")
    if "-exact-score" in s or t.startswith("Exact Score"):
        return "exact-score"
    if "-spread-" in s or t.startswith("Spread:"):
        return "spread"
    if "-handicap" in s or "handicap" in t.lower():   # tennis/soccer handicap = spread-like deriv
        return "spread"
    if "-total-" in s or "O/U" in t or "Over/Under" in t:
        return "over-under"
    if "-btts" in s or "Both Teams to Score" in t:
        return "prop"
    if s.endswith("-draw") or "end in a draw" in t:
        return "draw"
    tl = t.lower()
    if "champion" in tl or "to win the" in tl or "nominee" in tl or s.endswith("-winner"):
        return "futures"
    if ("up-or-down" in s or "-above-" in s or " above " in tl or "up or down" in tl):
        return "over-under"
    if ("-halftime" in s or "-first-to-score" in s or "-goals-" in s
            or "first-half" in s or "-corners" in s or "-cards" in s
            or "-scorer" in s or "first blood" in tl or "-game" in s):
        return "prop"
    if re.match(r"^[a-z0-9]+(-[a-z0-9]+)*-\d{4}-\d{2}-\d{2}$", s) and " vs" in tl:
        return "moneyline"
    if ("-team-to-advance" in s or re.search(r"-game\d+$", s)
            or re.match(r"^will .* win on \d{4}-\d{2}-\d{2}\?", tl)):
        return "moneyline"
    return None


_UPDOWN = re.compile(r"up[- ]?or[- ]?down|updown|\bup or down\b", re.I)


def market_type(slug, title):
    """main | deriv | None (uncovered).

    Special case (documented): a crypto/index UP-OR-DOWN market is that event's HEADLINE
    outcome (there is no separate "moneyline"), so it is `main` — even though its fine type is
    over-under-shaped. Temperature/threshold bins in econ/other are NOT up-or-down and stay
    deriv. Sports totals stay deriv (a total is conditional on the match's main winner market)."""
    s, t = (slug or ""), (title or "")
    if _UPDOWN.search(s) or _UPDOWN.search(t):
        if category(slug, title) in ("crypto", "econ/other"):
            return "main"
    fine = _classify_mtype_fine(slug, title)
    return _MT_COLLAPSE.get(fine) if fine is not None else None


def classify(slug, title):
    return category(slug, title), market_type(slug, title)


# --- live coverage report -------------------------------------------------------------------
SQL = """
SELECT strategy, slug, event_slug, title,
       (resolved::int) AS resolved,
       COALESCE(initial_mean_price, mean_price) AS entry,
       to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals
"""


def _fetch():
    out = subprocess.run(PG + ["-c", SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def run_coverage():
    rows = _fetch()
    from collections import defaultdict
    # per category: total rows, resolved, days, and consensus-fire counts (favorite/elite)
    stat = defaultdict(lambda: dict(total=0, resolved=0, days=set(), blind_fav=0,
                                    fires=0, elite=0, mt=defaultdict(int)))
    uncovered_mt = 0
    for r in rows:
        cat = category(r["slug"], r["title"])
        mt = market_type(r["slug"], r["title"])
        d = stat[cat]
        d["total"] += 1
        if r["resolved"] == "1":
            d["resolved"] += 1
            d["days"].add(r["day"])
        d["mt"][mt or "—"] += 1
        if mt is None:
            uncovered_mt += 1
        strat = r["strategy"]
        try:
            entry = float(r["entry"]) if r["entry"] not in ("", None) else 0.0
        except ValueError:
            entry = 0.0
        if strat == "_blind" and entry >= 0.6:
            d["blind_fav"] += 1
        if strat == "favorite":
            d["fires"] += 1
        if strat == "elite_fresh_fav":
            d["elite"] += 1
    print("MARKET TAXONOMY · coverage by category (whole book) · "
          f"mtype coverage {100*(1-uncovered_mt/max(len(rows),1)):.1f}%\n")
    hdr = (f"{'category':<18}{'rows':>7}{'resolvd':>8}{'days':>5}{'ev/day':>7}"
           f"{'blindFav':>9}{'FIRES':>6}{'elite':>6}  fire-verdict")
    print(hdr)
    print("-" * len(hdr))
    for cat in sorted(stat, key=lambda c: -stat[c]["resolved"]):
        d = stat[cat]
        nd = max(len(d["days"]), 1)
        # K4: soft-but-never-fires is an observation, not an arm
        if d["fires"] + d["elite"] == 0:
            fv = "NEVER FIRES consensus (K4 — observation)"
        elif d["fires"] + d["elite"] < 20:
            fv = "data-starved (< N floor)"
        else:
            fv = "measurable"
        print(f"{cat:<18}{d['total']:>7}{d['resolved']:>8}{len(d['days']):>5}"
              f"{d['resolved']/nd:>7.1f}{d['blind_fav']:>9}{d['fires']:>6}{d['elite']:>6}  {fv}")
    print("\nread: FIRES = resolved `favorite` picks in the cell; a category that NEVER fires the")
    print("consensus (crypto) is a softness OBSERVATION, not a steerable arm (K4). market-type split")
    print("per category printed by softness_map.py.")
    return 0


# --- self-test ------------------------------------------------------------------------------
# Hand-labeled sample: every category branch, every documented trap, and NULL cases that MUST
# fall through to ("other", None) rather than a confident mislabel.
_LABELED = [
    # (slug, title, want_category, want_mtype)
    ("atp-jong-hijikata-2026-06-29", "Jong vs Hijikata", "tennis", "main"),
    ("atp-jong-hijikata-2026-06-29-set-handicap-away-1pt5", "Set Handicap: away", "tennis", "deriv"),
    ("fifwc-bel-sen-2026-07-01", "Belgium vs Senegal", "soccer", "main"),
    ("fifwc-bel-sen-2026-07-01-exact-score-2-0", "Exact Score 2-0", "soccer", "deriv"),
    ("world-penalty-shootouts", "Will 2+ matches be decided by penalty shootout during the 2026 FIFA World Cup?", "soccer", None),
    ("mar1-cod-far-2026-07-01-total-0pt5", "COD Meknès vs. AS FAR: AS FAR O/U 0.5", "soccer", "deriv"),
    ("mlb-laa-sea-2026-06-30", "Angels vs Mariners", "mlb", "main"),
    ("mlb-laa-sea-2026-06-30-total-5pt5", "Angels vs Mariners O/U 5.5", "mlb", "deriv"),
    ("kbo-lg-ssg-2026-07-02", "LG vs SSG", "mlb", "main"),
    ("nba-lal-bos-2026-10-22", "Lakers vs Celtics", "nba/cbb", "main"),
    ("nfl-kc-buf-2026-09-10", "Chiefs vs Bills", "nfl/cfb", "main"),
    ("nhl-bos-tor-2026-10-08", "Bruins vs Maple Leafs", "nhl", "main"),
    # esports — the `co-` Call-of-Duty trap
    ("co-faze-lat-2026-06-29", "Call of Duty: FaZe Vegas vs Los Angeles Thieves (BO5)", "esports", None),
    ("cs2-1win-inox-2026-07-01", "Counter-Strike: 1WIN vs INOX Division (BO3)", "esports", None),
    ("lol-t1-tl2-2026-07-01-game1", "First Blood in Game 1?", "esports", "deriv"),
    ("dota2-team-a-team-b-2026-07-01", "Team A vs Team B", "esports", None),
    # crypto tokens + the hype trap
    ("btc-updown-5m-1782784500", "Bitcoin Up or Down", "crypto", "main"),
    ("hype-up-or-down-2026-07-01-11pm", "HYPE Up or Down - July 1, 11PM ET", "crypto", "main"),
    # econ / culture (structured econ slugs + title keywords)
    ("spx-updown-2026-07-01", "S&P 500 (SPX) Up or Down on July 1?", "econ/other", "main"),
    ("highest-temp-amsterdam-2026-07-02", "Will the highest temperature in Amsterdam be 22°C on July 2?", "econ/other", None),
    ("top-spotify-2026-07", "Will Bad Bunny have the greatest number of monthly Spotify listeners this month?", "econ/other", None),
    ("what-netflix-2026-w27", "Will \"Flowers in the Attic\" be the top global Netflix movie this week?", "econ/other", None),
    # politics — title-keyword layer (colorado = politics, NOT the co- CoD trap)
    ("colorado-senate-dem-primary", "Will John Hickenlooper be the Democratic nominee for Senate in Colorado?", "politics/elections", "main"),
    ("will-biden-drop-out", "Biden drops out of presidential race?", "politics/elections", None),
    # NULL cases — genuinely ambiguous ⇒ must be ("other", None), never a confident guess
    ("who-visited-island", "Will Bill Clinton be confirmed to have visited Epstein's island?", "other", None),
    ("claude-fable-restore", "Will Claude Fable 5 be restored for US customers by August 31?", "other", None),
    ("elon-tweets-240-259", "Will Elon Musk post 240-259 tweets from June 23 to June 30, 2026?", "other", None),
]


def _self_test():
    ok = True
    cat_hits = mt_hits = mt_total = 0
    misfires = []
    for slug, title, wcat, wmt in _LABELED:
        gcat = category(slug, title)
        gmt = market_type(slug, title)
        if gcat == wcat:
            cat_hits += 1
        else:
            misfires.append(f"    CAT  {slug:<40} got {gcat!r} want {wcat!r}")
        if wmt is not None:
            mt_total += 1
            if gmt == wmt:
                mt_hits += 1
            else:
                misfires.append(f"    MTYPE {slug:<40} got {gmt!r} want {wmt!r}")
    n = len(_LABELED)
    c1 = cat_hits == n
    print(f"  [{'ok' if c1 else 'FAIL'}] category: {cat_hits}/{n} labeled markets classified correctly")
    c2 = mt_hits == mt_total
    print(f"  [{'ok' if c2 else 'FAIL'}] market_type: {mt_hits}/{mt_total} typed markets correct")
    # NULL discipline: the ambiguous cases must be ("other", None) — no confident mislabel
    null_cases = [("who-visited-island", "Will Bill Clinton be confirmed to have visited Epstein's island?"),
                  ("claude-fable-restore", "Will Claude Fable 5 be restored for US customers by August 31?")]
    c3 = all(category(s, t) == "other" and market_type(s, t) is None for s, t in null_cases)
    print(f"  [{'ok' if c3 else 'FAIL'}] null discipline: ambiguous markets → (other, None), not a guess")
    # trap discipline: co-=esports, colorado=politics, world=soccer, spx/highest=econ, hype=crypto
    traps = [
        (category("co-faze-lat-2026-06-29", "Call of Duty: FaZe vs Thieves") == "esports"),
        (category("colorado-senate", "Will X be the Democratic nominee for Senate in Colorado?") == "politics/elections"),
        (category("world-shootouts", "penalty shootout during the 2026 FIFA World Cup") == "soccer"),
        (category("spx-updown", "S&P 500 (SPX) Up or Down?") == "econ/other"),
        (category("hype-up", "HYPE Up or Down") == "crypto"),
    ]
    c4 = all(traps)
    print(f"  [{'ok' if c4 else 'FAIL'}] traps: co-→esports, colorado→politics, world→soccer, spx→econ, hype→crypto")
    # parity with slice_study's fine classifier where it is importable (no drift)
    c5 = True
    try:
        import slice_study as ss
        probe = [("mlb-x-2026-07-01-total-5pt5", "O/U 5.5"),
                 ("atp-a-b-2026-06-29", "A vs B"),
                 ("fifwc-a-b-2026-07-01-exact-score-2-0", "Exact Score 2-0")]
        c5 = all(_classify_mtype_fine(s, t) == ss.classify_mtype(s, t) for s, t in probe)
        print(f"  [{'ok' if c5 else 'FAIL'}] mtype parity with slice_study.classify_mtype")
    except Exception as e:  # slice_study import optional (numpy); parity is a bonus check
        print(f"  [skip] slice_study parity ({type(e).__name__}: import unavailable)")
    ok = c1 and c2 and c3 and c4 and c5
    if misfires:
        print("  misfires:")
        print("\n".join(misfires))
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_coverage())
