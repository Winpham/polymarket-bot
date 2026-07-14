#!/usr/bin/env python3
"""US-VENUE FEE / REBATE / SUBSIDY MODEL — the instrument every US claim is priced through.

VERIFIED AT SOURCE (docs.polymarket.us/fees, 2026-07-14), not quoted from a brief:

    Fee = THETA * C * p * (1-p)          C = contracts, p = trade price in (0.01, 0.99)

    taker  THETA = +0.06     (a COST)
    maker  THETA = -0.0125   (a REBATE, credited to balance)

Independently confirmed on the venue itself: every one of 2,999 live markets returns
`feeCoefficient: 0.06` from gateway.polymarket.us/v1/markets. So the taker coefficient is real
and uniform -- not a docs aspiration.

THE TWO FACTS THAT SHAPE EVERY POSTURE DECISION
-----------------------------------------------
1. p*(1-p) is MAXIMAL at p=0.50 and collapses at the extremes. Taking costs 1.50c/share at a
   coin-flip but only 0.12c at p=0.98. Our champion favorite band (p 0.71-0.98) is therefore
   ALREADY the cheapest place on the venue to be a taker, and weather-style coin-flips are the
   most expensive -- which compounds, on pure cost grounds, the finding that weather doesn't
   transfer to US.
2. The maker rebate is 4.8x SMALLER than the taker fee (0.0125 vs 0.06) at every price. Making
   instead of taking swings ~0.93c/share at p=0.85. That is 15-30% of a 3-7c edge -- meaningful,
   but the rebate ALONE is not the prize, and it is nowhere near large enough to pay for being
   picked off. The liquidity subsidy is the thing that could.

TIERS (prior calendar-month TAKER notional; rebate paid weekly)
    >= $250k -> 10% | >= $1M -> 25% | >= $10M -> 50%   of taker fees rebated.
ACCELERATED TIER PLACEMENT: verifiable trailing-30-day volume on ANOTHER prediction market can be
submitted to be assigned the corresponding tier immediately -- i.e. our INTL volume may buy the
25-50% tier from day one on US. That is a real, actionable discount (see us_economics.py).

WHAT THIS MODULE WILL NOT DO
----------------------------
It will not hand you an incentive-reward number. Rewards are pro-rata against competitors we do
not observe, so a reward is only ever an ESTIMATE conditioned on observed near-touch depth --
that lives in us_reward_model.py, and it is a CEILING, never income. A pool is a published
schedule, not money (run brief, hard rule 6). Likewise adverse selection is MEASURED
(us_adverse_selection.py), never assumed.
"""
from __future__ import annotations

# Verified 2026-07-14 at docs.polymarket.us/fees; taker coefficient re-verified against the live
# `feeCoefficient` field on all 2,999 markets served by gateway.polymarket.us/v1/markets.
THETA_TAKER = 0.06
THETA_MAKER = -0.0125          # negative == the maker is PAID

# Prior-calendar-month taker notional -> fraction of taker fees rebated back.
TAKER_REBATE_TIERS = [
    (10_000_000, 0.50),
    (1_000_000, 0.25),
    (250_000, 0.10),
    (0, 0.00),
]

PRICE_MIN, PRICE_MAX = 0.01, 0.99          # the venue's tradable price domain
VOLUME_INCENTIVE_BAND = (0.03, 0.97)       # only trades in [3c, 97c] count for the volume program


def _check_price(p: float) -> None:
    if not (PRICE_MIN <= p <= PRICE_MAX):
        raise ValueError(f"price {p} outside the venue's tradable domain "
                         f"[{PRICE_MIN}, {PRICE_MAX}]")


def taker_fee(p: float, contracts: float = 1.0, tier_rebate: float = 0.0) -> float:
    """Taker fee in DOLLARS (positive = you pay). Per-share cost = taker_fee(p).

    `tier_rebate` is the volume-tier fraction rebated (0.0 / 0.10 / 0.25 / 0.50). It is applied
    here rather than bolted on later because a fee net of its rebate is the only number that
    should ever reach a sizing decision.
    """
    _check_price(p)
    return THETA_TAKER * contracts * p * (1.0 - p) * (1.0 - tier_rebate)


def maker_rebate(p: float, contracts: float = 1.0) -> float:
    """Maker rebate in DOLLARS (positive = you are PAID). Not affected by the taker tiers."""
    _check_price(p)
    return -THETA_MAKER * contracts * p * (1.0 - p)


def tier_for_volume(prior_month_taker_notional: float) -> float:
    """The rebate fraction earned by prior-month taker notional (or granted by Accelerated Tier
    Placement against trailing-30d volume on another prediction market)."""
    for threshold, rebate in TAKER_REBATE_TIERS:
        if prior_month_taker_notional >= threshold:
            return rebate
    return 0.0


def volume_incentive_eligible(p: float) -> bool:
    """The Volume Incentive Program pays a pro-rata share of a pool on eligible contracts, to
    MAKER OR TAKER (the docs say both -- the run brief's 'pays takers' is incomplete), but only
    for trades between 3c and 97c. Deep favorites at 0.98 fall OUTSIDE the band: the cheapest
    place to take is also a place the volume subsidy does not reach. Worth knowing before we
    claim a deep-favorite taker is subsidised."""
    return VOLUME_INCENTIVE_BAND[0] <= p <= VOLUME_INCENTIVE_BAND[1]


def net_edge(gross_edge: float, p: float, posture: str, contracts: float = 1.0,
             tier_rebate: float = 0.0, reward_per_share: float = 0.0,
             adverse_selection: float = 0.0) -> float:
    """THE fee-adjusted edge instrument, in DOLLARS PER SHARE unless `contracts` is given.

    net = gross
          - taker_fee(p)            [taker]   net of any volume-tier rebate
          + maker_rebate(p)         [maker]
          + reward_per_share                  MEASURED/estimated incentive share, never a pool figure
          - adverse_selection                 MEASURED markout cost (makers); ~0 for a taker, who
                                              pays the spread instead of being picked off by it

    A candidate scored WITHOUT this is scored at a price we cannot trade at. `gross_edge` is the
    arm's edge in dollars per share at the price it actually fills.
    """
    if posture not in ("taker", "maker"):
        raise ValueError("posture must be 'taker' or 'maker'")
    per_share = gross_edge
    if posture == "taker":
        per_share -= taker_fee(p, 1.0, tier_rebate)
    else:
        per_share += maker_rebate(p, 1.0)
        per_share -= adverse_selection
    per_share += reward_per_share
    return per_share * contracts


def fee_table(prices=(0.50, 0.71, 0.80, 0.85, 0.90, 0.95, 0.98)):
    """Per-share economics across the price grid, in CENTS. The shape of this table is the
    single most decision-relevant fact about the venue."""
    rows = []
    for p in prices:
        t = taker_fee(p) * 100
        m = maker_rebate(p) * 100
        rows.append({
            "p": p,
            "taker_fee_c": t,
            "maker_rebate_c": m,
            "make_vs_take_swing_c": t + m,      # what switching posture is worth, before AS/reward
            "taker_fee_t25_c": taker_fee(p, 1.0, 0.25) * 100,
            "taker_fee_t50_c": taker_fee(p, 1.0, 0.50) * 100,
            "vol_incentive_eligible": volume_incentive_eligible(p),
        })
    return rows


if __name__ == "__main__":
    print("US fee schedule — per share, in cents (Fee = THETA * C * p * (1-p))")
    print(f"{'p':>6} {'taker':>8} {'maker':>8} {'swing':>8} {'taker@25%':>10} {'taker@50%':>10} {'volIncent':>10}")
    for r in fee_table():
        print(f"{r['p']:>6.2f} {r['taker_fee_c']:>7.2f}c {r['maker_rebate_c']:>+7.2f}c "
              f"{r['make_vs_take_swing_c']:>7.2f}c {r['taker_fee_t25_c']:>9.2f}c "
              f"{r['taker_fee_t50_c']:>9.2f}c {str(r['vol_incentive_eligible']):>10}")
    print("\nmaker rebate is 1/4.8 of the taker fee at EVERY price (0.0125 / 0.06).")
    print("fees are cheapest at the extremes: our favorite band (0.71-0.98) is the cheapest")
    print("place on the venue to take; coin-flips (weather) are the most expensive.")
