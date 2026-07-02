#!/usr/bin/env python3
"""
RISK ENGINE — correlation-aware paper sizing, and an HONEST P(profit) number.

The companion to scripts/portfolio_concentration.py. It answers ONE question with numbers,
not vibes: given a strategy's MEASURED (edge, odds, variance, correlation, costs), which
sizing policy — from a FROZEN menu — maximises long-run growth subject to explicit
loss-probability ceilings, and what is the resulting P(P&L>0) and P(max-drawdown>X)?

THREE THINGS THIS ENGINE IS NOT (binding, K3):
  1. It is NOT a promise of profit. Every P(profit) below is CONDITIONAL on the measured
     edge being real (D7's job, not this engine's) and on it persisting. If the edge is
     zero, every policy loses to costs — this engine sizes an edge, it cannot create one.
  2. It is NOT a diversification manufacturer. The record holds few independent bets
     (see portfolio_concentration.py); the block bootstrap prices TODAY's correlation, it
     does not wish more away.
  3. It is NOT applied to anything. The recommended policy is PRE-REGISTERED for the
     hypothetical day D7 + pilot floors + Tue ever say real money — not switched on here.

METHOD (pre-registered — reports/entries/2026-07-02-12-diversification-risk.md):
  * Pick stream = a strategy's resolved picks, event-clustered (one bet per event, fire
    order), at-fire entry (D6), measured costs (0.5¢ haircut + 2% fee).
  * Kelly inputs are PER-BAND with SE shrinkage (never per-market fitting): full Kelly on
    the band's (win-rate, cost), shrunk toward 0 by shrink = clamp(edge_LB / edge, 0, 1).
    A band whose edge lower bound ≤ 0 gets f=0 (no unproven bet).
  * Monte Carlo = BLOCK BOOTSTRAP at the slate grain (resample (regime × UTC-day) blocks
    with replacement, preserving within-slate & within-match correlation EXACTLY). NEVER
    iid-per-pick (that fakes diversification). Sensitivity at event-day and regime-week
    grains; the CONSERVATIVE grain binds (K2).
  * Nested horizons H ∈ {100, 300, 1000} snapshotted along one path. Ruin = bankroll ever
    ≤ 20% of B; maxDD = peak-to-trough of the bankroll path (peak seeded at the start B).

RECOMMENDED policy = highest median log-growth subject to P(maxDD > 30% of B) ≤ 10%,
at the conservative grain. Ceiling frozen BEFORE any simulation.

Modes:
  ./risk_engine.py             # live DB, full matrix, writes reports/risk_engine.json
  ./risk_engine.py --selftest  # analytic-Kelly match; correlated-fixture variance recovery
                               # (incl. the iid-understates proof); cap-truncation proof.
                               # Exit non-zero on failure.
"""

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn  # band(), regime(), fetch()

POPULATIONS = ["favorite", "elite_fresh_fav", "strict"]
SEED = 20260702
HAIRCUT = 0.005
FEE = 0.02
STAKE = 100.0                       # 1 "unit" = $100 notional (flat-shares & cap accounting)
BANKROLLS = [1_000.0, 5_000.0, 25_000.0]
HORIZONS = [100, 300, 1000]
N_PATHS = 10_000                    # ≥10k per the pre-registration (slate grain, full matrix)
N_PATHS_SENS = 4_000                # grain-sensitivity comparison (event-day, regime-week)
RUIN_FRAC = 0.20                    # bankroll ≤ 20% of B = ruin
DD_CEIL = 0.30                      # P(maxDD > 30% of B) ceiling
DD_CEIL_P = 0.10

# Frozen cap parameters (P4/P5). Caps are evaluated WITHIN each resampled block (the
# bootstrap unit doubles as the risk-budget window): the block's events are the "slate";
# for event-day/regime-week grains a block spans regimes so the per-regime cap engages.
CAP_MAX_PER_SLATE = 3              # ≤3 units per regime within a block
CAP_REGIME_FRAC = 0.40            # ≤40% of a block's bet count in one regime
CAP_STOP_LOSS_UNITS = 5.0         # daily stop: pause new entries once block P&L ≤ −5 units
CAP_STOP_LOSS = CAP_STOP_LOSS_UNITS * STAKE

POLICIES = ["flat_dollar_100", "flat_shares_100", "kelly_quarter", "kelly_eighth",
            "flat_shares_capped", "kelly_eighth_capped"]
CAPPED = {"flat_shares_capped", "kelly_eighth_capped"}
KELLY_MULT = {"kelly_quarter": 0.25, "kelly_eighth": 0.125,
              "kelly_eighth_capped": 0.125}


# ---------------------------------------------------------------------------------------
# Per-band Kelly inputs (SE-shrunk, frozen).
# ---------------------------------------------------------------------------------------
def kelly_by_band(events):
    """events: list of dicts with c (cost), won (0/1 or clustered frac), band. Returns
    {band: f_full} = the SE-shrunk FULL-Kelly fraction per band (policies scale it 1/4,1/8)."""
    by_band = defaultdict(list)
    for e in events:
        by_band[e["band"]].append(e)
    out = {}
    for b, evs in by_band.items():
        c = float(np.mean([e["c"] for e in evs]))
        w = float(np.mean([e["won"] for e in evs]))
        n = len(evs)
        r_win = (1.0 - c) / c - FEE          # $ return per $ staked on a win
        r_lose = -1.0 - FEE                  # ... on a loss (stake + fee)
        if r_win <= 0:                       # no favourable payout ⇒ never bet
            out[b] = 0.0
            continue
        f_star = w / (-r_lose) - (1.0 - w) / r_win   # exact two-outcome Kelly
        # realized per-event return (won interpolated for clustered fractions) → edge + SE
        per_ev = np.array([e["won"] * r_win + (1.0 - e["won"]) * r_lose for e in evs])
        edge = float(np.mean(per_ev))
        se = float(np.std(per_ev, ddof=1) / np.sqrt(n)) if n > 1 else float("inf")
        edge_lb = edge - 1.96 * se
        shrink = max(0.0, min(1.0, edge_lb / edge)) if edge > 0 else 0.0
        out[b] = max(0.0, min(0.99, f_star * shrink))
    return out


# ---------------------------------------------------------------------------------------
# Record → events → blocks.
# ---------------------------------------------------------------------------------------
def build_events(prows):
    """Event-cluster the strategy's rows → one bet per event (fire order)."""
    by_ev = defaultdict(list)
    for r in prows:
        by_ev[r["ev"]].append(r)
    events = []
    for ev, rs in by_ev.items():
        c = min(0.999, float(np.mean([x["entry"] for x in rs])) + HAIRCUT)
        won = float(np.mean([x["won"] for x in rs]))
        rg = sn.regime(rs[0]["event_slug"])
        events.append({"ev": ev, "c": c, "won": won, "band": sn.band(c - HAIRCUT),
                       "regime": rg, "day": rs[0]["day"], "slate": (rg, rs[0]["day"]),
                       "t_fire": rs[0].get("t_fire", 0.0)})
    events.sort(key=lambda e: (e["day"], e["regime"], e.get("t_fire", 0.0), e["ev"]))
    return events


def blocks_by_grain(events, grain):
    """slate=(regime,day); event_day=day (multi-regime); regime_week=regime (record <1wk)."""
    key = {"slate": lambda e: e["slate"], "event_day": lambda e: e["day"],
           "regime_week": lambda e: e["regime"]}[grain]
    g = defaultdict(list)
    for e in events:
        g[key(e)].append(e)
    return [sorted(v, key=lambda e: (e["day"], e["regime"], e.get("t_fire", 0.0)))
            for v in g.values()]


def structural_mask(block):
    """Outcome-independent cap mask: ≤3 per regime and ≤40% of the block's count per
    regime. Uses only regime + fire order — never outcomes (no leakage)."""
    n = len(block)
    limit_frac = max(1, int(np.ceil(CAP_REGIME_FRAC * n)))
    per_reg = defaultdict(int)
    mask = np.zeros(n, dtype=bool)
    for i, e in enumerate(block):
        rg = e["regime"]
        if per_reg[rg] < CAP_MAX_PER_SLATE and per_reg[rg] < limit_frac:
            mask[i] = True
            per_reg[rg] += 1
    return mask


# ---------------------------------------------------------------------------------------
# The Monte Carlo. Three code paths (all identical semantics; split only for speed):
#   vectorised   flat_dollar / flat_shares / kelly_quarter / kelly_eighth  (no caps)
#   capped-flat  flat_shares_capped  (additive $ → per-block vectorised, B-independent)
#   capped-kelly kelly_eighth_capped (compounding + absolute $ stop-loss → sequential, per-B)
# ---------------------------------------------------------------------------------------
def _prep(events, grain, kelly_full, edge_mult=1.0):
    """edge_mult λ (K3 stress): won_eff = c + λ·(won − c) scales each event's realized
    advantage by λ while preserving which events win/lose (so correlation is untouched).
    λ=1 = measured; λ=0 = costs-only (a LOSING world — the honest 'if the edge isn't real')."""
    blocks = blocks_by_grain(events, grain)
    pos = {e["ev"]: i for i, e in enumerate(events)}
    block_idx = [np.array([pos[e["ev"]] for e in blk]) for blk in blocks]
    block_masks = [structural_mask(blk) for blk in blocks]
    block_lens = np.array([len(b) for b in block_idx])
    c = np.array([e["c"] for e in events])
    won_raw = np.array([e["won"] for e in events])
    won = c + edge_mult * (won_raw - c)
    unit = won / c - 1.0 - FEE
    f_full = np.array([kelly_full.get(e["band"], 0.0) for e in events])
    arrs = {"unit": unit, "f_full": f_full,
            "flat_dollar": STAKE * unit,
            "flat_shares": STAKE * (won - c * (1.0 + FEE))}
    return block_idx, block_masks, block_lens, arrs


def _draw_blocks(block_lens, Hmax, rng):
    """Return list of (bi, take) block draws whose total presented length == Hmax."""
    nblk = len(block_lens)
    chosen, tot = [], 0
    while tot < Hmax:
        bi = int(rng.integers(0, nblk))
        chosen.append(bi)
        tot += int(block_lens[bi])
    over = tot - Hmax
    draws = [(bi, int(block_lens[bi])) for bi in chosen]
    if over > 0:
        bi, ln = draws[-1]
        draws[-1] = (bi, ln - over)
    return draws


def _finalize(bank_traj, B):
    """bank_traj: length-Hmax bankroll AFTER each presented event. Snapshot terminal / min /
    maxDD at each horizon. maxDD is PEAK-RELATIVE (fraction of the running high-water mark,
    seeded at the starting bankroll B) — the standard drawdown definition, bounded [0,1),
    scale-invariant so it stays meaningful when a Kelly bankroll compounds. 'P(maxDD>30%)'
    = probability of ever drawing down 30% from a high-water mark."""
    peak = np.maximum.accumulate(np.maximum(bank_traj, B))
    dd = (peak - bank_traj) / peak
    out = {}
    for H in HORIZONS:
        seg_term = bank_traj[H - 1]
        seg_min = min(B, float(bank_traj[:H].min()))
        seg_dd = float(dd[:H].max())
        out[H] = (float(seg_term), seg_min, seg_dd)
    return out


def simulate(events, grain, policy, B, n_paths, seed, kelly_full, edge_mult=1.0):
    rng = np.random.default_rng(seed)
    block_idx, block_masks, block_lens, arrs = _prep(events, grain, kelly_full, edge_mult)
    Hmax = HORIZONS[-1]
    snaps = {H: {"term": np.empty(n_paths), "minb": np.empty(n_paths),
                 "maxdd": np.empty(n_paths)} for H in HORIZONS}
    is_capped = policy in CAPPED
    is_kelly = policy.startswith("kelly")
    kmult = KELLY_MULT.get(policy, 1.0)
    flat_arr = arrs["flat_dollar"] if policy == "flat_dollar_100" else arrs["flat_shares"]

    for p in range(n_paths):
        draws = _draw_blocks(block_lens, Hmax, rng)
        if not is_capped:
            # vectorised: gather effects, cumsum (flat) / cumprod (kelly)
            seq = np.concatenate([block_idx[bi][:take] for bi, take in draws])
            if is_kelly:
                mult = 1.0 + kmult * arrs["f_full"][seq] * arrs["unit"][seq]
                bank_traj = B * np.cumprod(mult)
            else:
                bank_traj = B + np.cumsum(flat_arr[seq])
        elif policy == "flat_shares_capped":
            parts = []
            for bi, take in draws:
                idx = block_idx[bi][:take]
                m = block_masks[bi][:take]
                eff = np.where(m, flat_arr[idx], 0.0)
                cum = np.cumsum(eff)
                breach = np.where(cum <= -CAP_STOP_LOSS)[0]
                if breach.size:
                    eff[breach[0] + 1:] = 0.0   # pause new entries after the breach
                parts.append(eff)
            bank_traj = B + np.cumsum(np.concatenate(parts))
        else:  # kelly_eighth_capped — sequential (compounding + absolute $ stop-loss)
            bank_traj = np.empty(Hmax)
            bank = B
            w = 0
            for bi, take in draws:
                idx = block_idx[bi][:take]
                m = block_masks[bi][:take]
                block_cum = 0.0
                stopped = False
                for k in range(len(idx)):
                    if m[k] and not stopped:
                        j = idx[k]
                        delta = kmult * arrs["f_full"][j] * bank * arrs["unit"][j]
                        bank += delta
                        block_cum += delta
                        if block_cum <= -CAP_STOP_LOSS:
                            stopped = True
                    bank_traj[w] = bank
                    w += 1
        fin = _finalize(bank_traj, B)
        for H in HORIZONS:
            t, mn, d = fin[H]
            snaps[H]["term"][p] = t
            snaps[H]["minb"][p] = mn
            snaps[H]["maxdd"][p] = d
    return snaps


def summarize(snaps, B):
    out = {}
    for H, s in snaps.items():
        pnl = s["term"] - B
        with np.errstate(divide="ignore"):
            logr = np.log(np.maximum(s["term"], 1e-9) / B)
        out[str(H)] = {
            "median_pnl": float(np.median(pnl)),
            "p5_pnl": float(np.percentile(pnl, 5)),
            "p_profit": float(np.mean(pnl > 0)),
            "median_maxdd_frac": float(np.median(s["maxdd"])),
            "p_maxdd_over_30pct": float(np.mean(s["maxdd"] > DD_CEIL)),
            "p_ruin": float(np.mean(s["minb"] <= RUIN_FRAC * B)),
            "median_log_growth_per_100ev": float(np.median(logr) * (100.0 / H)),
        }
    return out


def _rescale_kelly(snaps, B0, B):
    """Uncapped Kelly is scale-invariant: bank_t = B·∏mult, so peak-relative maxDD, ruin
    fraction and P(profit) are all B-independent; only the $ terminal/min scale linearly."""
    return {H: {"term": s["term"] / B0 * B, "minb": s["minb"] / B0 * B,
                "maxdd": s["maxdd"]} for H, s in snaps.items()}


# Only uncapped fractional Kelly is scale-invariant → simulate once + rescale. Every other
# policy has a B-dependent risk profile (flat: peak-relative maxDD depends on B; capped
# Kelly: absolute $ stop-loss) → simulate per bankroll.
RESCALABLE = {"kelly_quarter", "kelly_eighth"}


def run_strategy(events, grain, n_paths, seed):
    kelly_full = kelly_by_band(events)
    res = {}
    for policy in POLICIES:
        res[policy] = {}
        if policy in RESCALABLE:
            base = simulate(events, grain, policy, BANKROLLS[0], n_paths, seed, kelly_full)
            for B in BANKROLLS:
                res[policy][str(int(B))] = summarize(
                    _rescale_kelly(base, BANKROLLS[0], B), B)
        else:
            for B in BANKROLLS:
                res[policy][str(int(B))] = summarize(
                    simulate(events, grain, policy, B, n_paths, seed, kelly_full), B)
    return res, kelly_full


EDGE_MULTS = [1.0, 0.5, 0.25, 0.0]


def edge_stress(events, kelly_full, policy, B, n_paths, seed, H=300):
    """K3 robustness curve: P(profit) & median P&L of a policy as the MEASURED edge is
    haircut by λ. λ=0 is the costs-only (losing) world — the honest floor under the
    conditional-on-edge caveat. Slate grain, event-clustered, block bootstrap."""
    out = {}
    for lam in EDGE_MULTS:
        s = summarize(simulate(events, "slate", policy, B, n_paths, seed, kelly_full,
                               edge_mult=lam), B)[str(H)]
        out[str(lam)] = {"p_profit": s["p_profit"], "median_pnl": s["median_pnl"]}
    return out


CONSERVATIVE_DEFAULT = "kelly_eighth_capped"


def recommend(res, horizons=HORIZONS):
    """Frozen rule: highest median log-growth per 100 events subject to P(maxDD>30%)≤10% at
    EVERY horizon, at the conservative bankroll ($1k, the tightest DD test).

    HONESTY OVERRIDE (the record has no adversity): if the frozen rule selects the MOST
    AGGRESSIVE menu policy (kelly_quarter) and even it shows ~0 drawdown, the ceiling is
    SLACK — the 4-day record contains no losing slate, so the block bootstrap CANNOT price
    drawdown, and 'max growth under a non-binding ceiling' just means 'bet as hard as the
    menu allows'. In that case the actionable pre-registered recommendation is the
    structurally-capped policy (drawdown bounded by CONSTRUCTION), not the frozen pick.
    The frozen pick earns its aggression only once adverse regimes accrue and the ceiling
    can actually bind."""
    B = str(int(BANKROLLS[0]))
    best, best_g = None, -1e9
    for policy in POLICIES:
        cells = [res[policy][B][str(H)] for H in horizons]
        if any(c["p_maxdd_over_30pct"] > DD_CEIL_P for c in cells):
            continue
        g = min(c["median_log_growth_per_100ev"] for c in cells)
        if g > best_g:
            best_g, best = g, policy
    slack = (best == "kelly_quarter"
             and all(res["kelly_quarter"][B][str(H)]["p_maxdd_over_30pct"] < 0.02
                     for H in horizons))
    honest = CONSERVATIVE_DEFAULT if slack else best
    return {"frozen_max_growth_pick": best, "ceiling_slack": slack,
            "conservative_default": CONSERVATIVE_DEFAULT, "honest_recommendation": honest}


def simulate_multiregime(events, policy, B, n_paths, seed, kelly_full, n_regimes, H=100):
    """Spread the SAME H-event volume across n_regimes INDEPENDENT slate-bootstrap
    sub-streams (zero cross-stream correlation, real within-stream correlation), then
    compound. Isolates the diversification value of independent regimes: if within-regime
    correlation is high, more independent regimes cut variance; if events are already
    ~independent, it buys ≈ what more volume would (√N). Non-capped policies only."""
    rng = np.random.default_rng(seed)
    block_idx, _, block_lens, arrs = _prep(events, "slate", kelly_full)
    is_kelly = policy.startswith("kelly")
    kmult = KELLY_MULT.get(policy, 1.0)
    flat_arr = arrs["flat_dollar"] if policy == "flat_dollar_100" else arrs["flat_shares"]
    per = H // n_regimes
    term = np.empty(n_paths)
    maxdd = np.empty(n_paths)
    for p in range(n_paths):
        seqs = []
        for _r in range(n_regimes):
            draws = _draw_blocks(block_lens, per, rng)
            seqs.append(np.concatenate([block_idx[bi][:take] for bi, take in draws]))
        seq = np.concatenate(seqs)[:H]
        if is_kelly:
            traj = B * np.cumprod(1.0 + kmult * arrs["f_full"][seq] * arrs["unit"][seq])
        else:
            traj = B + np.cumsum(flat_arr[seq])
        peak = np.maximum.accumulate(np.maximum(traj, B))
        term[p] = traj[-1]
        maxdd[p] = float(((peak - traj) / peak).max())
    pnl = term - B
    return {"sd_pnl": float(np.std(pnl)), "p5_pnl": float(np.percentile(pnl, 5)),
            "p_profit": float(np.mean(pnl > 0)),
            "p_maxdd_over_30pct": float(np.mean(maxdd > DD_CEIL)),
            "median_pnl": float(np.median(pnl))}


def diversification(pop_events, kelly_fulls, n_paths, seed):
    """The pre-registered diversification experiments (Phase 3), all flat_shares H=100:
      A eff-redundancy: elite_fresh_fav ⊂ favorite ⇒ deduped union == favorite (marginal 0).
      B PRIORITIZE-restriction: favorite-all vs favorite∩band[0.80,0.90) — growth vs shrink.
      C value-of-an-independent-regime: favorite spread over k=1,2,3 independent regimes."""
    out = {}
    fav = pop_events["favorite"]
    kf = kelly_fulls["favorite"]

    # A — overlap redundancy (event sets)
    fav_ev = {e["ev"] for e in fav}
    eff_ev = {e["ev"] for e in pop_events.get("elite_fresh_fav", [])}
    out["A_eff_redundancy"] = {
        "favorite_events": len(fav_ev), "eff_events": len(eff_ev),
        "eff_subset_of_favorite": eff_ev.issubset(fav_ev),
        "deduped_union": len(fav_ev | eff_ev),
        "independent_bets_eff_adds": len(eff_ev - fav_ev)}

    # B — PRIORITIZE band restriction (band 0.80–0.90 is a slice-study PRIORITIZE cell)
    fav_prio = [e for e in fav if 0.80 <= (e["c"] - HAIRCUT) < 0.90]
    b_all = simulate(fav, "slate", "flat_shares_100", 1000.0, n_paths, seed, kf)
    b_prio = (simulate(fav_prio, "slate", "flat_shares_100", 1000.0, n_paths, seed,
                       kelly_by_band(fav_prio)) if len(fav_prio) >= 10 else None)
    out["B_prioritize_restriction"] = {
        "favorite_all": {"n_events": len(fav_ev), **summarize(b_all, 1000.0)["100"]},
        "favorite_band_0.80_0.90": (
            {"n_events": len({e["ev"] for e in fav_prio}),
             **summarize(b_prio, 1000.0)["100"]} if b_prio else "N<10")}

    # C — value of an independent regime (favorite, flat_shares H=100)
    out["C_independent_regime_value"] = {}
    for k in (1, 2, 3):
        out["C_independent_regime_value"][f"{k}_regimes"] = simulate_multiregime(
            fav, "flat_shares_100", 1000.0, n_paths, seed + k, kf, k, H=100)
    return out


def run(populations=POPULATIONS, n_paths=N_PATHS, quiet=False):
    rows = sn.fetch()
    pop_rows = {p: [r for r in rows if r["strategy"] == p] for p in populations}
    result = {"meta": {"seed": SEED, "n_paths": n_paths, "haircut": HAIRCUT, "fee": FEE,
                       "bankrolls": BANKROLLS, "horizons": HORIZONS,
                       "dd_ceiling": DD_CEIL, "dd_ceiling_p": DD_CEIL_P,
                       "ruin_frac": RUIN_FRAC, "policies": POLICIES,
                       "cap": {"max_per_slate": CAP_MAX_PER_SLATE,
                               "regime_frac": CAP_REGIME_FRAC,
                               "stop_loss_units": CAP_STOP_LOSS_UNITS},
                       "days": sorted({r["day"] for r in rows})},
              "strategies": {}, "kelly_by_band": {}, "grain_sensitivity": {},
              "recommendation": {}, "edge_stress": {}, "diversification": {}}
    pop_events, kelly_fulls = {}, {}
    for p in populations:
        if not pop_rows[p]:
            continue
        events = build_events(pop_rows[p])
        pop_events[p] = events
        res, kelly_full = run_strategy(events, "slate", n_paths, SEED)
        kelly_fulls[p] = kelly_full
        result["strategies"][p] = res
        result["kelly_by_band"][p] = {str(k): round(v, 4) for k, v in kelly_full.items()}
        result["grain_sensitivity"][p] = {}
        for grain in ("slate", "event_day", "regime_week"):
            snaps = simulate(events, grain, "kelly_eighth", BANKROLLS[0],
                             N_PATHS_SENS, SEED + 7, kelly_full)
            result["grain_sensitivity"][p][grain] = summarize(snaps, BANKROLLS[0])["300"]
        # recommended policy (frozen ceiling + honesty override) + edge-haircut stress (K3)
        rec = recommend(res)
        B0 = str(int(BANKROLLS[0]))
        rec["frozen_cells"] = ({str(H): res[rec["frozen_max_growth_pick"]][B0][str(H)]
                                for H in HORIZONS} if rec["frozen_max_growth_pick"] else None)
        rec["honest_cells"] = {str(H): res[rec["honest_recommendation"]][B0][str(H)]
                               for H in HORIZONS}
        result["recommendation"][p] = rec
        result["edge_stress"][p] = edge_stress(events, kelly_full,
                                               rec["honest_recommendation"], BANKROLLS[0],
                                               N_PATHS_SENS, SEED + 11)
    # diversification experiments (Phase 3) — favorite-focused
    if "favorite" in pop_events:
        result["diversification"] = diversification(pop_events, kelly_fulls,
                                                     N_PATHS_SENS, SEED + 3)
    if not quiet:
        _print(result)
    return result


def _print(result):
    m = result["meta"]
    print(f"risk engine · seed {m['seed']} · {m['n_paths']} block-bootstrap paths · "
          f"record {len(m['days'])}d · haircut {HAIRCUT*100:.1f}¢ fee {FEE:.0%} · "
          f"ceiling P(maxDD>{DD_CEIL:.0%})≤{DD_CEIL_P:.0%}")
    print("ALL P(profit) BELOW ARE CONDITIONAL ON THE MEASURED EDGE BEING REAL & PERSISTING.")
    print("If the edge is not real, every policy loses to costs — this sizes an edge, "
          "it does not create one.\n")
    for p, pol in result["strategies"].items():
        kb = result["kelly_by_band"].get(p, {})
        print(f"### {p}   full-Kelly-by-band (SE-shrunk): "
              f"{', '.join(f'{k}:{v}' for k, v in sorted(kb.items())) or '(none>0)'}")
        hdr = (f"{'policy':<22}{'B':>7}{'H':>6}{'med P&L':>10}{'5th P&L':>10}"
               f"{'P(profit)':>10}{'medDD':>7}{'P(DD>30%)':>10}{'P(ruin)':>9}"
               f"{'g/100ev':>9}")
        print(hdr)
        print("-" * len(hdr))
        for policy in POLICIES:
            for B in BANKROLLS:
                bs = pol[policy][str(int(B))]
                for H in HORIZONS:
                    s = bs[str(H)]
                    flag = "" if s["p_maxdd_over_30pct"] <= DD_CEIL_P else " x"
                    print(f"{policy:<22}{int(B):>7}{H:>6}{s['median_pnl']:>+10.0f}"
                          f"{s['p5_pnl']:>+10.0f}{s['p_profit']:>10.1%}"
                          f"{s['median_maxdd_frac']:>7.1%}"
                          f"{s['p_maxdd_over_30pct']:>10.1%}{s['p_ruin']:>9.1%}"
                          f"{s['median_log_growth_per_100ev']:>+9.3f}{flag}")
        print()
    print("GRAIN SENSITIVITY (kelly_eighth, B=$1k, H=300; conservative grain binds — K2)")
    print(f"{'strategy':<16}{'grain':<14}{'P(profit)':>10}{'P(DD>30%)':>11}{'P(ruin)':>9}")
    for p, gs in result["grain_sensitivity"].items():
        for grain, s in gs.items():
            print(f"{p:<16}{grain:<14}{s['p_profit']:>10.1%}"
                  f"{s['p_maxdd_over_30pct']:>11.1%}{s['p_ruin']:>9.1%}")

    print("\nRECOMMENDED POLICY (max median log-growth s.t. P(maxDD>30%)≤10% at every "
          "horizon, B=$1k)")
    for p, r in result["recommendation"].items():
        slack = " [CEILING SLACK — record has no losing slate; frozen pick untrustworthy]" \
                if r["ceiling_slack"] else ""
        print(f"  {p}: frozen-rule pick = {r['frozen_max_growth_pick']}{slack}")
        print(f"      → HONEST recommendation = {r['honest_recommendation']}"
              + (" (structurally capped; drawdown bounded by construction)"
                 if r["ceiling_slack"] else ""))
        for H in HORIZONS:
            s = r["honest_cells"][str(H)]
            print(f"      H={H:<5} P(profit) {s['p_profit']:.1%}  "
                  f"med P&L(@$1k) {s['median_pnl']:+.0f}  P(maxDD>30%) "
                  f"{s['p_maxdd_over_30pct']:.1%}  P(ruin) {s['p_ruin']:.1%}  "
                  f"g/100 {s['median_log_growth_per_100ev']:+.3f}")

    print("\nEDGE-HAIRCUT STRESS (recommended policy, H=300, B=$1k) — P(profit) is "
          "CONDITIONAL on the measured edge; here it is haircut by λ (λ=0 = costs-only):")
    print(f"{'strategy':<16}{'λ=1.0':>16}{'λ=0.5':>16}{'λ=0.25':>16}{'λ=0.0':>16}")
    for p, es in result["edge_stress"].items():
        cells = " ".join(f"{es[str(l)]['p_profit']:>6.1%}/{es[str(l)]['median_pnl']:>+8.0f}"
                         for l in EDGE_MULTS)
        print(f"{p:<16}{cells}")

    div = result.get("diversification", {})
    if div:
        print("\nDIVERSIFICATION (Phase 3, favorite, flat_shares):")
        a = div["A_eff_redundancy"]
        print(f"  A · elite_fresh_fav ⊂ favorite = {a['eff_subset_of_favorite']}; "
              f"deduped union {a['deduped_union']} = favorite ({a['favorite_events']}); "
              f"eff adds {a['independent_bets_eff_adds']} independent bets → 0 risk reduction")
        b = div["B_prioritize_restriction"]
        ba, bp = b["favorite_all"], b["favorite_band_0.80_0.90"]
        print(f"  B · PRIORITIZE-restrict to band .80–.90 (H=100): "
              f"all N={ba['n_events']} g/100 {ba['median_log_growth_per_100ev']:+.3f} "
              f"P(DD>30%) {ba['p_maxdd_over_30pct']:.1%}  vs  band-only "
              + (f"N={bp['n_events']} g/100 {bp['median_log_growth_per_100ev']:+.3f} "
                 f"P(DD>30%) {bp['p_maxdd_over_30pct']:.1%}"
                 if isinstance(bp, dict) else str(bp)))
        print("  C · value of an independent regime (favorite over k independent regimes, "
              "same H=100 volume):")
        base_sd = div["C_independent_regime_value"]["1_regimes"]["sd_pnl"]
        for k in (1, 2, 3):
            cc = div["C_independent_regime_value"][f"{k}_regimes"]
            red = 1 - cc["sd_pnl"] / base_sd if base_sd else 0
            print(f"      k={k}: SD(P&L) {cc['sd_pnl']:.0f} ({red:+.0%} vs k=1) · "
                  f"5th-pct {cc['p5_pnl']:+.0f} · P(DD>30%) {cc['p_maxdd_over_30pct']:.1%}")


# =======================================================================================
# SELF-TESTS (mandatory; ship only on PASS).
# =======================================================================================
def _mk_events(specs):
    """specs: (entry, won, regime, day). Cost c = entry+haircut, band from entry — exactly
    build_events' convention."""
    evs = []
    for i, (entry, won, rg, day) in enumerate(specs):
        c = min(0.999, entry + HAIRCUT)
        evs.append({"ev": f"e{i}", "c": c, "won": won, "band": sn.band(entry),
                    "regime": rg, "day": day, "slate": (rg, day), "t_fire": float(i)})
    return evs


def _analytic_kelly(w, entry):
    c = min(0.999, entry + HAIRCUT)
    r_win = (1 - c) / c - FEE
    return w / (1 + FEE) - (1 - w) / r_win


def selftest():
    ok = True
    rng = np.random.default_rng(SEED)

    print("— test 1: analytic Kelly + iid growth + zero-edge-loses —")
    w, e = 0.70, 0.60           # e = entry price
    N = 4000
    specs = [(e, 1.0 if rng.random() < w else 0.0, "tennis", f"d{i % 50}") for i in range(N)]
    events = _mk_events(specs)
    kb = kelly_by_band(events)
    f_full_est, f_star = kb[sn.band(e)], _analytic_kelly(w, e)
    match = abs(f_full_est - f_star) <= 0.06
    ok = ok and match
    print(f"  full-Kelly est {f_full_est:.3f} vs analytic {f_star:.3f} "
          f"[{'ok' if match else 'FAIL'}]")
    s = summarize(simulate(events, "slate", "kelly_quarter", 1000.0, 3000, SEED, kb),
                  1000.0)["300"]
    grows = s["median_pnl"] > 0 and s["p_profit"] > 0.6
    ok = ok and grows
    print(f"  quarter-Kelly H=300: med P&L {s['median_pnl']:+.0f}, "
          f"P(profit) {s['p_profit']:.1%} [{'ok' if grows else 'FAIL'}]")
    specs0 = [(e, 1.0 if rng.random() < e else 0.0, "tennis", f"d{i % 50}") for i in range(N)]
    ev0 = _mk_events(specs0)
    s0 = summarize(simulate(ev0, "slate", "flat_shares_100", 1000.0, 3000, SEED,
                            kelly_by_band(ev0)), 1000.0)["300"]
    zero_loses = s0["median_pnl"] < 0
    ok = ok and zero_loses
    print(f"  zero-edge flat-shares H=300: med P&L {s0['median_pnl']:+.0f} "
          f"(must be <0 — costs) [{'ok' if zero_loses else 'FAIL'}]")

    print("— test 2: correlated fixture — block bootstrap vs iid understatement —")
    corr_specs = []
    for sday in range(60):
        slate_win = 1.0 if rng.random() < w else 0.0
        for _k in range(10):
            corr_specs.append((e, slate_win, "tennis", f"d{sday}"))  # perfect within-slate corr
    cev = _mk_events(corr_specs)
    kbc = kelly_by_band(cev)
    tb = simulate(cev, "slate", "flat_shares_100", 1000.0, 4000, SEED, kbc)[300]["term"]
    iid_specs = [(cc, ww, "tennis", f"d{i}") for i, (cc, ww, _r, _d) in enumerate(corr_specs)]
    iev = _mk_events(iid_specs)
    ti = simulate(iev, "slate", "flat_shares_100", 1000.0, 4000, SEED,
                  kelly_by_band(iev))[300]["term"]
    sd_b, sd_i = float(np.std(tb)), float(np.std(ti))
    understates = sd_i < 0.6 * sd_b
    ok = ok and understates
    print(f"  terminal-P&L SD: block {sd_b:,.0f} vs iid {sd_i:,.0f} "
          f"(iid must understate ≥40%) [{'ok' if understates else 'FAIL'}]")
    p5_b = float(np.percentile(tb - 1000.0, 5))
    p5_i = float(np.percentile(ti - 1000.0, 5))
    fatter = p5_b < p5_i
    ok = ok and fatter
    print(f"  5th-pct P&L: block {p5_b:+,.0f} vs iid {p5_i:+,.0f} "
          f"(block fatter loss tail) [{'ok' if fatter else 'FAIL'}]")

    print("— test 3: cap truncation on a scripted losing streak —")
    # A block of 20 straight losses in ONE slate (tennis-d0); the ≤3-per-slate cap must
    # bet ≤3 of them → strictly less drawdown than uncapped.
    streak = [(0.60, 0.0, "tennis", "d0") for _ in range(20)]
    filler = [(0.60, 1.0 if rng.random() < w else 0.0, "mlb", f"m{i % 30}")
              for i in range(600)]
    sev = _mk_events(streak + filler)
    kbs = kelly_by_band(sev)
    cap = simulate(sev, "slate", "flat_shares_capped", 1000.0, 2000, SEED, kbs)
    unc = simulate(sev, "slate", "flat_shares_100", 1000.0, 2000, SEED, kbs)
    dd_cap = float(np.percentile(cap[300]["maxdd"], 95))
    dd_unc = float(np.percentile(unc[300]["maxdd"], 95))
    truncates = dd_cap < dd_unc
    ok = ok and truncates
    print(f"  95th-pct maxDD: capped {dd_cap:.1%} vs uncapped {dd_unc:.1%} "
          f"(caps must truncate) [{'ok' if truncates else 'FAIL'}]")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    result = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "reports", "risk_engine.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("\nartifact → reports/risk_engine.json")


if __name__ == "__main__":
    main()
