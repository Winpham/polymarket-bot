#!/usr/bin/env python3
"""
MATCH-LEVEL SUPER-KEY — the honest event-clustering key (truth-audit attack E).

The incumbent cluster key is `COALESCE(event_slug, condition_id)`. But event_slug only
groups OUTCOME variants of ONE sub-market:

    slug fifwc-civ-nor-2026-06-30-exact-score-3-0  → event_slug fifwc-civ-nor-2026-06-30-exact-score

A single real-world match spans SEVERAL event_slugs — game-winner, exact-score, "more-markets"
(spreads/totals/corners/halves), draw, etc.:

    fifwc-bel-sen-2026-07-01               (game winner)
    fifwc-bel-sen-2026-07-01-exact-score   (6 exact-score outcomes)
    fifwc-bel-sen-2026-07-01-more-markets  (spreads/totals/corners)
    ''  (empty event_slug; slug = fifwc-bel-sen-2026-07-01-total-1pt5)

Clustering on event_slug therefore treats one match as up to ~4 "independent events" → inflates
N, tightens the confidence bound, and lifts z. The honest unit is the MATCH.

Rule (documented, deterministic, no fitting):
  base = event_slug if non-empty else slug            # empty event_slug rows carry the match in slug
  if base contains a YYYY-MM-DD date:
      super_key = base up-to-and-INCLUDING the first date   # everything after the date is market-type noise
  else:
      super_key = base                                 # dateless markets (elections, crypto up/down) stay 1:1

Why "up to the first date" is safe: every sports slug is `<sport>-<t1>-<t2>-<YYYY-MM-DD>-<market...>`;
the date is the match boundary and the only market-type-free stem. Dateless markets (elections,
`btc-updown-5m-<epoch>`) have no shared stem to over-merge, so they pass through 1:1 (never LESS
strict than the incumbent key there). Doubleheaders (same teams, same date, two games) would
merge — accepted, vanishingly rare and CONSERVATIVE (fewer independent events, not more).

Self-test:  ./superkey.py --self-test    (exercises every branch; exits non-zero on any failure)
"""

import re
import sys

_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def super_event(event_slug, slug):
    """Return the match-level cluster key. event_slug may be '' / None; slug is the fallback."""
    base = (event_slug or "").strip()
    if not base:
        base = (slug or "").strip()
    if not base:
        return None  # caller decides (e.g. fall back to condition_id) — matches incumbent behaviour
    m = _DATE.search(base)
    if not m:
        return base  # dateless market: 1:1, never coarser than the incumbent key
    return base[: m.end()]  # stem through the first date; drop the market-type suffix


# --- self-test -------------------------------------------------------------------------------
_CASES = [
    # (event_slug, slug, expected, why)
    ("fifwc-bel-sen-2026-07-01", "fifwc-bel-sen-2026-07-01-bel",
     "fifwc-bel-sen-2026-07-01", "game-winner already at match level"),
    ("fifwc-bel-sen-2026-07-01-exact-score", "fifwc-bel-sen-2026-07-01-exact-score-2-0",
     "fifwc-bel-sen-2026-07-01", "exact-score sub-market strips to match"),
    ("fifwc-bel-sen-2026-07-01-more-markets", "fifwc-bel-sen-2026-07-01-spread-home-1pt5",
     "fifwc-bel-sen-2026-07-01", "more-markets sub-market strips to match"),
    ("", "fifwc-bel-sen-2026-07-01-total-1pt5",
     "fifwc-bel-sen-2026-07-01", "empty event_slug falls back to slug then strips"),
    ("atp-jong-hijikat-2026-06-29", "atp-jong-hijikat-2026-06-29-set-handicap-away-1pt5",
     "atp-jong-hijikat-2026-06-29", "tennis moneyline already 1:1 (unchanged)"),
    ("mlb-laa-sea-2026-06-30", "mlb-laa-sea-2026-06-30-total-5pt5",
     "mlb-laa-sea-2026-06-30", "mlb total's event_slug already the match"),
    ("co-01-democratic-primary-winner", "will-diana-degette-be-the-nominee",
     "co-01-democratic-primary-winner", "dateless election market stays 1:1"),
    ("btc-updown-5m-1782784500", "btc-updown-5m-1782784500",
     "btc-updown-5m-1782784500", "dateless crypto up/down stays 1:1"),
    ("lol-t1-tl2-2026-07-01", "lol-t1-tl2-2026-07-01-game3",
     "lol-t1-tl2-2026-07-01", "esports maps of one series collapse to the series"),
    (None, "fifwc-civ-nor-2026-06-30-exact-score-3-0",
     "fifwc-civ-nor-2026-06-30", "None event_slug + slug fallback"),
]


def _self_test():
    ok = True
    # 1. every documented branch
    for evt, slug, want, why in _CASES:
        got = super_event(evt, slug)
        flag = "ok" if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"  [{flag}] super_event({evt!r},{slug!r}) = {got!r}  ({why})")
    # 2. collapse property: the 3 Belgium-Senegal event_slugs + the empty-slug row → ONE key
    bel = {
        super_event("fifwc-bel-sen-2026-07-01", "x"),
        super_event("fifwc-bel-sen-2026-07-01-exact-score", "x"),
        super_event("fifwc-bel-sen-2026-07-01-more-markets", "x"),
        super_event("", "fifwc-bel-sen-2026-07-01-total-1pt5"),
    }
    if len(bel) != 1:
        ok = False
    print(f"  [{'ok' if len(bel)==1 else 'FAIL'}] 4 Belgium-Senegal slugs collapse to {len(bel)} key")
    # 3. NEVER coarser than incumbent on dateless keys (distinct dateless slugs stay distinct)
    a = super_event("co-01-democratic-primary-winner", "")
    b = super_event("colorado-governor-democratic-primary-winner", "")
    if a == b:
        ok = False
    print(f"  [{'ok' if a!=b else 'FAIL'}] two distinct dateless markets stay distinct")
    # 4. idempotence: super_event(super_event(x)) == super_event(x)
    idem = all(super_event(super_event(e, s), "") == super_event(e, s) for e, s, _, _ in _CASES)
    if not idem:
        ok = False
    print(f"  [{'ok' if idem else 'FAIL'}] idempotent")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    # filter mode: read "event_slug\tslug" lines, print the super key
    for line in sys.stdin:
        parts = line.rstrip("\n").split("\t")
        evt = parts[0] if len(parts) > 0 else ""
        slug = parts[1] if len(parts) > 1 else ""
        print(super_event(evt, slug))
