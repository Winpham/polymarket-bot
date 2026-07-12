#!/usr/bin/env python3
"""
WEATHER REGION MAP — synoptic-region grouping for honest independent-N (Weather Edge Refinement,
2026-07-11). Pure-DAY clustering treats every global city on a date as ONE correlated unit — too
conservative: a heat dome is ~1000km, so Tokyo and NYC on the same day are independent weather events.
Clustering by (synoptic region × day) recovers that spatial independence. It may still OVER-count
TEMPORAL independence within a single persistent week, so day-clustering (lower) and region-day (upper)
BRACKET the true independent-N — reported as a bracket, never a single inflated number.

Regions are broad synoptic groupings (no fitting; assigned before measuring). Unknown cities → 'other'
(reported as coverage; a large 'other' would flag the map as incomplete).
"""

_REGION = {
    # China (one broad monsoon/continental regime)
    "beijing": "china", "shanghai": "china", "guangzhou": "china", "shenzhen": "china",
    "chengdu": "china", "qingdao": "china", "wuhan": "china", "chongqing": "china", "hong-kong": "china",
    # Korea / Japan / Taiwan
    "busan": "easia", "seoul": "easia", "taipei": "easia", "tokyo": "easia",
    # SE Asia
    "kuala-lumpur": "seasia", "singapore": "seasia", "manila": "seasia",
    # South Asia
    "karachi": "sasia", "lucknow": "sasia",
    # Europe
    "warsaw": "europe", "paris": "europe", "london": "europe", "milan": "europe", "madrid": "europe",
    "amsterdam": "europe", "munich": "europe", "moscow": "europe", "istanbul": "europe",
    "ankara": "europe", "helsinki": "europe",
    # Middle East
    "jeddah": "mideast", "tel-aviv": "mideast",
    # North America — east vs west (distinct synoptic regimes)
    "nyc": "us_east", "atlanta": "us_east", "chicago": "us_east", "houston": "us_east",
    "miami": "us_east", "austin": "us_east", "dallas": "us_east", "toronto": "us_east",
    "san-francisco": "us_west", "denver": "us_west", "seattle": "us_west", "los-angeles": "us_west",
    # Latin America
    "mexico-city": "latam", "panama-city": "latam", "buenos-aires": "latam", "sao-paulo": "latam",
    # Southern hemisphere singletons
    "wellington": "oceania", "cape-town": "africa",
}


def region(city):
    return _REGION.get(city, "other")


if __name__ == "__main__":
    # coverage self-check
    import sys
    from collections import Counter
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from weather_scan import fetch_weather_picks
    picks = fetch_weather_picks()
    reg = Counter(region(p["city"]) for p in picks)
    print("region coverage:", dict(reg))
    print("unmapped 'other':", reg.get("other", 0), "of", len(picks))
