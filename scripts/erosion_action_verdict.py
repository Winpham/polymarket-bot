#!/usr/bin/env python3
"""
PHASE C -- the action verdict.

Verdict: NO ACTION IS WARRANTED. This script assembles the evidence for that and computes the
FORWARD decay gate (the only thing that can actually settle the question), including the power
analysis that shows why the current window cannot.

The single most important number in this whole run:
  to detect a drop from +8% to 0% at 95% you need ~61 matches PER WINDOW.
  The "recent" window has 38 (k=5) / 20 (k=3).
  => The data is UNDERPOWERED to detect the decay we are worried about. "We cannot yet tell"
     is the honest state of knowledge, and no exclusion rule can be justified from it.

Read-only. Emits reports/EROSION-ACTION-VERDICT.json.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erosion_lib as E  # noqa: E402
import erosion_decompose as D  # noqa: E402

Z1, Z2 = 1.645, 1.96


def main():
    rows = E.fetch()
    ls, blind, nb = D.enrich(rows)
    mday = E.match_day(ls)
    u = D.match_units(ls)

    n = len(u)
    tt = sum(v[1] for v in u.values())
    contrib = np.array([v[0] / (tt / n) for v in u.values()])
    sd = float(contrib.std(ddof=1))
    roi_all = D._roi(list(u.values()))

    def per_window(delta):
        return int(np.ceil(2 * (Z2 * sd / delta) ** 2))

    verdict = {
        "verdict": "NO ACTION WARRANTED",
        "one_paragraph": (
            "The recent softening of the `favorite` 0.71-0.98 champion is NOT an established edge "
            "decay -- it is a cold streak that the data is underpowered to distinguish from one. "
            "Under the honest day-block permutation null (whole slates exchangeable, respecting "
            "intra-day correlation) and BH-corrected for the four windows examined, the drop's "
            "minimum adjusted p is 0.086: a constant +8% edge is NOT excluded. Every mechanical "
            "cause was tested and every one came back negative: the belief-blind `_blind` "
            "structural edge is FLAT (1.70%->1.81%), so softness is not being arbitraged away and "
            "this is not crowding; convergence quality is unchanged (net_count 2.59->2.65, "
            "n_backers 3.08->3.06), so it is not trader rotation; the headline series already runs "
            "on a stationary price basis with 100% coverage, so it is not a capture artifact; and "
            "the firing MIX did shift hard (soccer 75%->33% of turnover) but in our FAVOUR -- the "
            "Oaxaca mix term is +2.5pt, while the damage sits entirely in the -7.4pt within-cell "
            "performance term. That within-cell loss localises to tennis (+13.4% -> -9.9%), and "
            "tennis in turn localises to a SINGLE SLATE: drop 07-13 alone (10 of the 19 recent "
            "tennis matches) and recent tennis flips back to +6.3%. The tennis 'decay' carries a "
            "95% CI of [-36.2%, +16.3%] -- which contains the earlier +13.4% -- and a Bonferroni "
            "p of 0.100 once charged for the seven categories scanned. Excluding tennis would "
            "therefore be precisely the forbidden dredge (remove whatever lost last week), and it "
            "would not even pay: the non-tennis remainder is +3.4% with a 95% LB of -5.8%. The "
            "cumulative slide from 8.4% to 7.1% is a 1.3pt wobble inside a band the series has "
            "occupied since 07-03, and volume is NOT draining (07-13 was the second-heaviest slate "
            "of the window at 16 matches), so no volume floor is triggered either. The decisive "
            "fact is power: detecting a fall from +8% to 0% requires ~61 matches per window and the "
            "recent window holds 38. The correct action is to change NOTHING, keep the champion and "
            "every incumbent byte-identical, keep running paper, and let the frozen forward gate "
            "below settle durability in the weeks past the World Cup final (~07-19) -- which is "
            "also the first genuine out-of-tournament test the edge has ever faced."
        ),
        "axes_tested": {
            "1_edge_decay": "INCONCLUSIVE-UNDERPOWERED — skill drop not separable from noise",
            "2_crowding": "NEGATIVE — _blind structural edge flat (1.70% -> 1.81%)",
            "3_mix_shift": "NEGATIVE (backwards) — mix term +2.5pt; damage is the -7.4pt perf term",
            "4_band_drift": "NEGATIVE — mean entry 0.860 -> 0.842; sub-band moves within noise",
            "5_convergence": "NEGATIVE — net_count/n_backers unchanged",
            "6_pipeline_artifact": "NEGATIVE for the headline series (stationary `imp` basis, 100% "
                                   "coverage). BUT see measurement_hazard below.",
            "7_cell_contamination": "POSITIVE but NOT ACTIONABLE — localises to tennis, which "
                                    "localises to the single 07-13 slate; dies on multiplicity+CI",
        },
        "rejected_responses": [
            {"response": "exclude tennis",
             "why_rejected": "found by scanning 7 categories (Bonferroni p=0.100); recent-tennis "
                             "95% CI [-36.2%,+16.3%] contains the earlier +13.4%; one LODO day "
                             "(07-13) flips it to +6.3%; and the non-tennis remainder has a "
                             "NEGATIVE 95% LB (-5.8%). Textbook data-dredge."},
            {"response": "exclude knockout-phase / late-tournament favorites",
             "why_rejected": "the mix shift HELPED (+2.5pt). There is no cell the strategy moved "
                             "INTO that is dragging it."},
            {"response": "self-suspend on a volume floor",
             "why_rejected": "volume is not draining — 07-13 was the 2nd-heaviest slate of the "
                             "window (16 matches). The trigger does not fire; adding it now would "
                             "be fitting a mechanism to a story the data does not support."},
            {"response": "tighten the price band",
             "why_rejected": "sub-band moves are within noise on 18-25 recent legs each; finer "
                             "bands are a settled-refused overfit (see DO-NOT list)."},
        ],
        "measurement_hazard_FOUND": {
            "what": "Any metric computed on COALESCE(entry_ask, initial_mean_price) is contaminated "
                    "for TIME-COMPARISONS.",
            "why": "entry_ask coverage is non-stationary — ~5% of legs on 06-29, ~70% on 07-13 (the "
                   "capture work landed mid-window) — and entry_ask sits ABOVE initial_mean_price. "
                   "So that basis silently swaps in a more expensive price source for a growing "
                   "share of legs as the window advances, manufacturing a downward drift.",
            "impact_here": "NONE — the incumbent daily table already uses initial_mean_price, which "
                           "has 100% coverage on all 16 days. Verified: it reproduces the brief's "
                           "series exactly (8.35/8.29/8.04/7.78/7.07).",
            "action": "Documented, not patched. Any FUTURE time-series analysis must use a "
                      "stationary basis; erosion_lib.legs(basis=...) enforces this and refuses to "
                      "mix band-membership and P&L bases.",
        },
        "strategy_changes_made": "NONE. champion `favorite` + all incumbents + ConsensusParams "
                                 "byte-identical. No new arm, no new flag, no migration.",
        "power_analysis": {
            "per_match_roi_sd": sd,
            "n_matches_total": n,
            "roi_full_sample": roi_all,
            "matches_per_window_to_detect_8pt_drop_95pct": per_window(0.08),
            "matches_per_window_to_detect_12pt_drop_95pct": per_window(0.12),
            "matches_in_recent_window_k5": 38,
            "matches_in_recent_window_k3": 20,
            "conclusion": "UNDERPOWERED. The recent window cannot resolve the question it is being "
                          "asked to resolve. Only forward accumulation can.",
        },
        "forward_gate": {
            "prereg": "reports/PREREG_20260714_erosion.md",
            "objective": "cluster-robust (match-level) ROI-on-turnover at OUR entry, belief-blind "
                         "surplus over `_blind`, stationary price basis",
            "decay_declared_if": "the day-block-permutation test on a forward window of >=61 "
                                 "matches returns BH-adjusted p < 0.05 for a drop vs the "
                                 "06-29..07-14 baseline",
            "healthy_if": "forward >=61-match window holds a 95% LB > 0 on belief-blind surplus",
            "critical_window": "the weeks AFTER the World Cup final (~2026-07-19) — the first "
                               "genuine non-tournament test this edge has ever had",
            "explicitly_frozen": "no exclusion, no band change, no new arm may be derived from the "
                                 "06-29..07-14 sample. Any future cut must be pre-registered BEFORE "
                                 "seeing its result.",
        },
    }

    os.makedirs("reports", exist_ok=True)
    with open("reports/EROSION-ACTION-VERDICT.json", "w") as f:
        json.dump(verdict, f, indent=2)

    print("VERDICT:", verdict["verdict"])
    print()
    print(f"per-match ROI SD = {sd:.3f} | full-sample ROI = {100*roi_all:.2f}% on {n} matches")
    print(f"matches/window needed to detect an 8pt drop  : {per_window(0.08)}")
    print(f"matches/window needed to detect a 12pt drop  : {per_window(0.12)}")
    print("matches in the recent window                 : 38 (k=5) / 20 (k=3)")
    print("=> UNDERPOWERED. Cannot distinguish cold streak from decay. No action.")
    print()
    for k, v in verdict["axes_tested"].items():
        print(f"  {k:24s} {v}")
    print("\n-> reports/EROSION-ACTION-VERDICT.json")


if __name__ == "__main__":
    main()
