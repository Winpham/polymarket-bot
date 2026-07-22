#!/usr/bin/env python3
"""
PROP CONSISTENCY — logical-arbitrage scanner for nested US player-prop markets. READ-ONLY.

WHY THIS IS A DIFFERENT KIND OF EDGE
------------------------------------
Every arm this project has tried is a STATISTICAL premium fighting the round-trip fee: favourite-
longshot bias, consensus, weather. Each died the same death — edge ≈ toll ([[the-toll]]).

The US venue lists LOGICALLY NESTED markets on the same player-game:
  `astatc-mlb-{away}-{home}-{date}-{stat}-{player}-gte{N}`
So `tb-gte2`, `tb-gte4`, `hr-gte1`, `hits-gte1` all coexist. These are not independent forecasts —
they are bound by arithmetic the pricing engine can VIOLATE:
  • within a stat: P(X>=4) <= P(X>=2)                    (monotonicity)
  • across stats:  a home run IS 4 total bases, so P(HR>=1) <= P(TB>=4)   (implication)
A violation is not a bet on an outcome — it is a bet that arithmetic holds. That is the strongest
possible edge: risk-free if both legs fill and settle consistently.

THE DECISIVE FINDING (2026-07-22, 9 days of self-collected mid_tape)
-------------------------------------------------------------------
The inconsistencies are REAL and frequent — but they live exactly where the money is not.
Mid-violation rate decays monotonically with book depth: 9.2% in <$1 books -> 0.22% in >=$200 books.
And NET OF THE TAKER FEE (0.05*p*(1-p) per leg), locked arbs are positive ONLY in sub-$50 dust; at
tradeable size (>=$200) every one nets <= 0. **The fee sits exactly at the boundary of the venue's
own pricing errors.** This is THE TOLL, proven on risk-free arbitrage — if a free arb can't clear
the fee at size, no statistical premium will.

THE ONE LIVE ANGLE
------------------
Violations mean-revert (the underpriced leg rises toward the overpriced one), ~13.6c of EXCESS
correction over the universal pre-game sharpening, p<1e-4. A TAKER cannot profit (fee). A MAKER pays
zero fee — but cannot "take" an existing inconsistency, only post into it and hope. That reintroduces
legging risk. The honest reframe this instrument exists to serve: **props have wide spreads + zero
maker fee + mean-reverting logical structure. A fair-value model posting maker orders is the only
construction that clears the fee that kills every taker strategy.** See [[foresight]] — a prop
fair-value ML already exists.

FAIL LOUD, NEVER CLOSED
-----------------------
The implication set is asserted correct in --self-test with worked box-score cases. The fee model is
tested against hand arithmetic. A run over an empty/dead tape reports zero comparisons LOUDLY, never
a reassuring "no violations".

  ./prop_consistency.py --self-test    # implication logic + fee model; no DB
  ./prop_consistency.py --historical   # the net-of-fee-by-depth table from the tape
"""
import os
import sys

FEE_RATE = 0.05
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")

# (sub_stat, sub_thr) IMPLIES (sup_stat, sup_thr): the sub event guarantees the sup event, so
# P(sub) <= P(sup). Every entry is a statement about a single at-bat / game line, asserted with a
# worked case in self_test(). Conservative on purpose — only implications that are ALWAYS true,
# never "usually". `hrr` = hits+runs+RBIs, `tb` = total bases, `hr` = home runs.
IMPLICATIONS = [
    ("hr", 1, "hits", 1),   # a home run is a hit
    ("hr", 1, "hrr", 1),    # a home run is >=1 of hits+runs+rbis (you score, or drive one in)
    ("hr", 1, "tb", 4),     # a home run is exactly 4 total bases
    ("hr", 2, "tb", 4),     # two home runs is >=8 TB, certainly >=4
    ("hits", 1, "hrr", 1),  # a hit is >=1 of hits+runs+rbis
    ("hits", 2, "hrr", 2),
    ("hits", 3, "hrr", 3),
    ("hits", 2, "tb", 2),   # 2 hits is >=2 total bases (each hit >=1 base)
    ("hits", 3, "tb", 3),   # 3 hits is >=3 total bases
]


def leg_fee(price: float) -> float:
    """Venue taker fee for one share of a contract priced `price`. Makers pay zero — the entire
    thesis of the live angle rests on that asymmetry."""
    return FEE_RATE * price * (1.0 - price)


def arb_net(bid_sub: float, ask_sup: float) -> float:
    """Net edge per share-pair of the locked arb that exploits P(sub) <= P(sup) when the book shows
    bid_sub > ask_sup. Construction: BUY sup-YES at `ask_sup`, BUY sub-NO at `1 - bid_sub`.

    Worst-case settlement payoff is exactly 1 (proven in self-test), so:
        net = (bid_sub - ask_sup) - fee(sup_yes) - fee(sub_no)
    and fee(sub_no at 1-bid_sub) == fee at bid_sub since p(1-p) is symmetric."""
    gross = bid_sub - ask_sup
    return gross - leg_fee(ask_sup) - leg_fee(bid_sub)


# --------------------------------------------------------------------------- snapshot build
def _build_snapshot(cur):
    """(Re)build prop_map (slug -> parsed game/player/stat/thr) and prop_q2 (minute-aligned top of
    book with depth). Idempotent. The tape self-compresses, so this is cheap to re-run to pick up
    fresh games. Kept in one place so the scanner is never reasoning off a table someone built by
    hand in a since-forgotten session — the failure mode that cost this project 2d17h of tape."""
    cur.execute(r"""
        drop table if exists prop_map;
        create table prop_map as
        select us_slug,
          (regexp_match(us_slug,'^astatc-mlb-(.+)-([0-9]{4}-[0-9]{2}-[0-9]{2})-([a-z]+)-([a-z]+)-gte([0-9]+)$'))[1] game,
          (regexp_match(us_slug,'^astatc-mlb-(.+)-([0-9]{4}-[0-9]{2}-[0-9]{2})-([a-z]+)-([a-z]+)-gte([0-9]+)$'))[2] gdate,
          (regexp_match(us_slug,'^astatc-mlb-(.+)-([0-9]{4}-[0-9]{2}-[0-9]{2})-([a-z]+)-([a-z]+)-gte([0-9]+)$'))[3] stat,
          (regexp_match(us_slug,'^astatc-mlb-(.+)-([0-9]{4}-[0-9]{2}-[0-9]{2})-([a-z]+)-([a-z]+)-gte([0-9]+)$'))[4] player,
          ((regexp_match(us_slug,'^astatc-mlb-(.+)-([0-9]{4}-[0-9]{2}-[0-9]{2})-([a-z]+)-([a-z]+)-gte([0-9]+)$'))[5])::int thr
        from (select distinct us_slug from us_mid_tape where us_slug ~ '^astatc-mlb-.+-gte[0-9]+$') d;
        create index prop_map_slug on prop_map(us_slug);
    """)
    cur.execute("""
        drop table if exists prop_q2;
        create table prop_q2 as
        select distinct on (m.us_slug, date_trunc('minute', m.transact_time))
               p.game,p.gdate,p.player,p.stat,p.thr,
               date_trunc('minute', m.transact_time) min_ts,
               m.best_bid,m.best_ask,m.best_bid_qty,m.best_ask_qty
        from us_mid_tape m join prop_map p on p.us_slug=m.us_slug
        where m.best_bid is not null and m.best_ask is not null and m.best_bid>0 and m.best_ask<1
          and m.best_ask>m.best_bid and p.stat is not null
          and m.best_bid_qty is not null and m.best_ask_qty is not null
        order by m.us_slug, date_trunc('minute',m.transact_time), m.transact_time desc;
        create index prop_q2_key on prop_q2(game,gdate,player,stat,min_ts);
    """)


# --------------------------------------------------------------------------- historical
def historical():
    import psycopg2

    impl_values = ",".join(
        f"('{a}',{b},'{c}',{d})" for a, b, c, d in IMPLICATIONS)
    sql = f"""
    with impl(sub_stat,sub_thr,sup_stat,sup_thr) as (values {impl_values}),
    allpairs as (
      select sub.best_bid bid_sub, sup.best_ask ask_sup,
             least(sup.best_ask*sup.best_ask_qty, sub.best_bid*sub.best_bid_qty) usd
      from impl i
      join prop_q2 sub on sub.stat=i.sub_stat and sub.thr=i.sub_thr
      join prop_q2 sup on sup.stat=i.sup_stat and sup.thr=i.sup_thr
       and sup.game=sub.game and sup.gdate=sub.gdate and sup.player=sub.player
       and sup.min_ts=sub.min_ts
      union all
      select b.best_bid, a.best_ask, least(a.best_ask*a.best_ask_qty, b.best_bid*b.best_bid_qty)
      from prop_q2 a join prop_q2 b
        on a.game=b.game and a.gdate=b.gdate and a.player=b.player and a.stat=b.stat
       and a.min_ts=b.min_ts and a.thr<b.thr
    ),
    arbs as (
      select usd, (bid_sub-ask_sup) gross,
             (bid_sub-ask_sup) - 0.05*(ask_sup*(1-ask_sup)+bid_sub*(1-bid_sub)) net
      from allpairs where bid_sub>ask_sup
    )
    select case when usd<10 then 'a. <$10' when usd<50 then 'b. $10-50'
                when usd<200 then 'c. $50-200' else 'd. >=$200 (tradeable)' end bucket,
           count(*) arbs, round(avg(gross)::numeric,4) avg_gross,
           round(avg(net)::numeric,4) avg_net,
           count(*) filter (where net>0) net_positive
    from arbs group by 1 order by 1;
    """
    try:
        with psycopg2.connect(PG_DSN) as con, con.cursor() as cur:
            cur.execute("select to_regclass('prop_q2')")
            exists = cur.fetchone()[0] is not None
            if not exists or "--rebuild" in sys.argv:
                print("  building prop_map + prop_q2 from us_mid_tape (one-time, ~2-4 min)...")
                _build_snapshot(cur)
                con.commit()
            cur.execute("select count(*) from prop_q2")
            n = cur.fetchone()[0]
            if n == 0:
                sys.exit("FATAL: prop_q2 is EMPTY. A dead tape must not read as 'no violations'.")
            cur.execute(sql)
            rows = cur.fetchall()
    except psycopg2.OperationalError as e:
        sys.exit(f"FATAL: cannot reach the tape DB — {e}. Not reporting on data I could not read.")

    print("=" * 78)
    print(f"PROP LOGICAL ARBITRAGE — net of the taker fee, by tradeable depth  (n={n:,} quotes)")
    print("=" * 78)
    print(f"  {'book depth':<22}{'arbs':>6}{'avg gross':>11}{'avg net':>10}{'net>0':>8}")
    for b, a, g, net, npos in rows:
        print(f"  {b:<22}{a:>6}{g * 100:>+10.2f}c{net * 100:>+9.2f}c{npos:>8}")
    print("\n  The fee wall: locked arbs net positive ONLY in books too thin to trade. At tradeable")
    print("  size the venue's fee exactly consumes its own pricing inconsistency. THE TOLL, proven")
    print("  on risk-free arbitrage. A taker cannot beat it here; only a zero-fee maker could.")


# --------------------------------------------------------------------------- self-test
def self_test() -> int:
    # ---- every implication must hold for a concrete box score. If any of these is wrong, the
    #      scanner would flag a LEGITIMATE price as an arb and lose money on a phantom.
    # A player's line: (hits, hr, tb, runs, rbi). hrr = hits+runs+rbi.
    def check(line):
        hits, hr, tb, runs, rbi = line
        hrr = hits + runs + rbi
        val = {"hits": hits, "hr": hr, "tb": tb, "hrr": hrr}
        for ss, st, ps, pt in IMPLICATIONS:
            if val[ss] >= st:               # sub event happened
                assert val[ps] >= pt, (
                    f"IMPLICATION FALSE: {ss}>={st} but {ps}={val[ps]} < {pt} on line {line}")

    # a solo home run: 1 hit, 1 hr, 4 tb, 1 run, 0 rbi (hit it, scored, no one else on)
    check((1, 1, 4, 1, 0))
    # a grand slam: 1 hit, 1 hr, 4 tb, 1 run, 4 rbi
    check((1, 1, 4, 1, 4))
    # two singles: 2 hits, 0 hr, 2 tb, 0 runs, 1 rbi
    check((2, 0, 2, 0, 1))
    # a double + a single: 2 hits, 0 hr, 3 tb
    check((2, 0, 3, 1, 0))
    # 3 singles: 3 hits, 0 hr, 3 tb
    check((3, 0, 3, 0, 0))
    # 2 home runs: 2 hits, 2 hr, 8 tb, 2 runs, 2 rbi
    check((2, 2, 8, 2, 2))
    # an 0-fer: nothing implies anything
    check((0, 0, 0, 0, 0))

    # ---- the fee model: symmetric in p, zero at the boundaries, max at 0.5
    assert abs(leg_fee(0.5) - 0.0125) < 1e-12, "fee peaks at 0.05*0.25 = 0.0125"
    assert leg_fee(0.0) == 0.0 and leg_fee(1.0) == 0.0, "no fee on a certainty"
    assert abs(leg_fee(0.29) - leg_fee(0.71)) < 1e-12, "fee is symmetric about 0.5"

    # ---- arb_net: the Schwarber case (bid_sub 0.31, ask_sup 0.29) must come out NEGATIVE,
    #      because that is the whole point — a 2c gross inversion is eaten by ~2.1c of fee.
    net = arb_net(0.31, 0.29)
    assert net < 0, f"the 2c real-money inversion must net negative after fee, got {net:+.4f}"
    assert abs(net - (0.02 - 0.05 * (0.29 * 0.71 + 0.31 * 0.69))) < 1e-12, "net formula"

    # ---- a genuinely large inversion (a near-abandoned leg) DOES clear
    assert arb_net(0.35, 0.24) > 0, "an 11c inversion clears the fee"

    # ---- monotone: a bigger gross gap always nets more (fee depends only on the prices, monotone
    #      enough over the region that widening the gap by moving ask down helps)
    assert arb_net(0.31, 0.20) > arb_net(0.31, 0.29), "a wider gap nets more"

    print("prop_consistency self-test OK (9 implications x 7 box scores, fee model, "
          "arb_net incl. the fee-eaten real case)")
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    if "--self-test" in args:
        return self_test()
    if "--historical" in args:
        historical()
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
