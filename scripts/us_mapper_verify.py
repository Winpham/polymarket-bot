#!/usr/bin/env python3
"""ADVERSARIAL VERIFICATION of the venue mapper — resolution agreement on settled markets.

The mapper's coverage number is worthless if the maps are WRONG. A high-coverage mapper that
inverts the side is far more dangerous than one that maps nothing: it would price "Brazil
win" and buy "Morocco win", losing money on every single trade while looking healthy.

So we check the one thing that cannot lie: on markets BOTH venues have already SETTLED, do
they agree on what happened? If the intl book says our proposition came true and the US book
says it did not, the map is broken. There is no third explanation.

THE TRAP THIS EXISTS TO CATCH (verified on the real corpus):
    atc-fwc-kor-cze-2026-06-11-cze   outcomes ["No","Yes"]   prices ["0","1"]
    atc-fwc-bra-mar-2026-06-13-bra   outcomes ["Yes","No"]   prices ["0","1"]
The `outcomes` array ORDER IS NOT CONSTANT. Reading `outcomePrices[0]` as P(Yes) is correct
on the first market and INVERTED on the second. Any code that indexes by position instead of
zipping outcomes->prices and finding "Yes" BY NAME is wrong on roughly half the book, and
would be wrong SILENTLY.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_mapper as M  # noqa: E402


def us_side_won(side_desc: str, prices: str, our_label: str):
    """Did the side WE backed win, on the US venue? True/False/None.

    THE ORIENTATION RULE, and it is the whole ballgame:

        outcomePrices[i]  corresponds to  side_desc[i].
        The `outcomes` array is NOT reliably ordered and must be IGNORED.

    Evidence, because this is exactly the thing you cannot afford to get wrong:

      * `outcomes` disagrees with `side_desc` on the same market —
            aec-atp-lorson-joesch: outcomes ["Joel Schwaerzler","Lorenzo Sonego"]
                                   side_desc ["Lorenzo Sonego","Joel Schwaerzler"]
                                   prices    ["1","0"]        (Sonego won)
        Aligning to side_desc gives Sonego; aligning to outcomes gives Schwaerzler. Inverted.

      * On Yes/No markets side_desc is always ["Yes","No"], which is why "prices[0] = P(Yes)"
        held: it is a special case of this rule, not a separate rule.

      * Decided against the hard invariant that a 3-way soccer result has EXACTLY ONE winning
        leg among {home, away, draw}:
            zip outcomes->prices by name : 322/783 fixtures consistent, 461 VIOLATIONS
            align to side_desc           : 783/783 fixtures consistent,   0 violations

    `our_label` is "Yes"/"No" on a proposition market and a PLAYER/TEAM NAME on a two-way
    moneyline, so we match Yes/No exactly and names by distinctive-token overlap.
    """
    try:
        sides = json.loads(side_desc or "[]")
        pxs = json.loads(prices or "[]")
    except Exception:
        return None
    if not sides or len(sides) != len(pxs):
        return None

    lab = (our_label or "").strip().lower()
    hit = None
    if lab in ("yes", "no"):
        for i, s in enumerate(sides):
            if str(s).strip().lower() == lab:
                hit = i
                break
    else:
        want = M.name_tokens(our_label)
        if not want:
            return None
        cands = [i for i, s in enumerate(sides) if want & M.name_tokens(str(s))]
        if len(cands) == 1:            # ambiguous -> refuse, never guess
            hit = cands[0]
    if hit is None:
        return None
    try:
        v = float(pxs[hit])
    except (TypeError, ValueError):
        return None
    return v == 1.0 if v in (0.0, 1.0) else None  # anything else = not settled


def main() -> None:
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{M.PG_DSN}' AS pg (TYPE postgres, READ_ONLY);")
    idx = M.build_index(con)

    us = {r[0]: (r[1], r[2]) for r in con.execute(
        f"SELECT slug, side_desc, outcomePrices FROM read_parquet('{M.US_PARQUET}')").fetchall()}

    sigs = con.execute("""
        SELECT strategy, event_slug, slug, title, outcome_label, outcome_won
        FROM pg.consensus_signals
        WHERE resolved AND outcome_won IS NOT NULL
          AND strategy IN ('favorite','weather_fav','favorite_v2','elite_fresh_fav')
    """).fetchall()

    agree = disagree = unsettled = unmapped = 0
    bad = []
    for strat, es, ms, title, label, won in sigs:
        m = M.map_signal(idx, es, ms, title)
        if m.confidence < M.THRESHOLD:
            unmapped += 1
            continue
        sd, p = us.get(m.us_slug, (None, None))
        uy = us_side_won(sd, p, label)
        if uy is None:
            unsettled += 1
            continue
        # Both sides now answer the SAME question: "did the side we backed win?"
        intl_yes = bool(won)
        if intl_yes == uy:
            agree += 1
        else:
            disagree += 1
            if len(bad) < 10:
                bad.append((es, m.us_slug, label, won, intl_yes, uy))

    n = agree + disagree
    print("RESOLUTION AGREEMENT — settled on BOTH venues")
    print(f"  comparable pairs : {n:,}")
    print(f"  AGREE            : {agree:,}" + (f"  ({100*agree/n:.1f}%)" if n else ""))
    print(f"  DISAGREE         : {disagree:,}" + (f"  ({100*disagree/n:.1f}%)" if n else ""))
    print(f"  (skipped: {unmapped:,} unmapped, {unsettled:,} not settled on the US side)\n")

    if disagree:
        print("✗ MAP IS BROKEN on these — the venues disagree about what happened:")
        for es, uss, lab, won, iy, uy in bad:
            print(f"    intl {es}\n      -> US {uss}\n      we backed {lab!r}: intl says won={iy}, US says won={uy}")
        sys.exit(1)
    if n == 0:
        print("⚠ NO comparable settled pairs — verification is VACUOUS, not passing.")
        sys.exit(1)
    print("✓ every settled mapped pair agrees on the real-world outcome.")


if __name__ == "__main__":
    main()
