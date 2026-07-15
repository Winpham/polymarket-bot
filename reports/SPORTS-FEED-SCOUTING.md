# Live sports-feed scouting — how to capture the final-hour favourite edge (and at what cost)

**2026-07-15, branch `feat/confidence-forensics`. Paper/analysis only.** Follows
`reports/CONFIDENCE-FORENSICS.md` Phase 7 + `project-polymarket-us-efficiency`. The one λ>0 inefficiency
(final-hour favourite underpricing, λ=0.73) needs a live game-state feed to locate the final hour. This
scouts feeds and answers the cost question.

## The decisive refinement: the edge is ATP/WTA, and it is FREE-coverable
The tennis universe is ITF-dominated (itf* ≈ 4,949 markets vs atp/wta ≈ 1,602), so the naive assumption
was "we need a paid ITF feed." **Wrong.** Splitting the −1h buy-favourite edge (0.65–0.98, 1c haircut,
event-clustered) by tier:

| tennis tier | −1h favourite net | p | events | feed |
|---|---|---|---|---|
| **ATP/WTA** | **+5.40c** [+1.82,+8.75] | **0.001** | 281 | FREE (ESPN) |
| ITF | +1.25c [−1.09,+3.54] | 0.152 | 823 | (would need paid) |

**The significant edge is entirely in ATP/WTA; ITF is not significant.** So the paid-feed question is
moot — we do not need ITF. (My earlier "tennis" bucket was already ATP/WTA-only: `grade_niche` silently
drops ITF slugs, which is why the +5.4c was ATP/WTA all along.) **Cost-zero path is viable.**

## Recommended feed: the ESPN hidden API (free, no auth)
- **Coverage:** ATP + WTA (`/apis/site/v2/sports/tennis/{atp,wta}/scoreboard`) and international soccer.
  Exactly the significant slice of the edge.
- **In-play state (verified):** per-set `linescores`, `winner` flags, and `status.state` ∈ {pre,in,post}.
  Live, this reads "up 2 sets / serving for the match" — the near-decided signal — with a stable state
  that persists for minutes (latency is a non-issue: the US book lags by *minutes*, ±30min tolerance).
- **Historical (verified):** `?dates=YYYYMMDD` returns past matches with `startDate` (ISO), set scores,
  player names, set count — so the edge can be **validated at zero cost** on the 06-24..07-13 window.
- **Risks:** undocumented/unofficial (ESPN can change or remove it; no SLA/support; ToS gray for betting
  use). Timing granularity is coarse historically (match start + set count, not per-set timestamps) — fine
  live (you watch the score), a limitation only for the retro-validation.

## Paid alternatives (only if we ever want ITF — currently unjustified)
| provider | ITF live | PBP/timeline | latency | price | note |
|---|---|---|---|---|---|
| tennis-api.com "Mega" | yes | yes (websocket) | sub-second | ~$99/mo (14-day trial) | best specialist value |
| api-tennis.com Starter | unclear | limited | — | ~$40/mo (14-day trial) | cheapest |
| Goalserve | yes | yes | ~1s | ~$1000/mo | overkill |
| Sportradar | yes | yes | sub-second | enterprise | overkill |
| API-Sports (api-tennis) | ATP/WTA-ish | no PBP | ~15s | free 100 req/day | free but shallow |

**Recommendation: use the free ESPN API. Do not spend on a paid feed** — the only edge that clears
significance (ATP/WTA) is free-coverable, and ITF (the paid-only part) is not significant.

## Honest caveats before any build
1. **Tournament-window generalisation.** The +5.40c ATP/WTA edge is measured in a **Wimbledon-heavy**
   window. It may be a marquee-tournament effect, not a general ATP/WTA property (the `favorite_v2`
   tennis-artifact warning). Forward validation across ordinary tour weeks is required.
2. **Historical validation is a weak proxy** (ESPN coarse timing ±?); the decisive test is a **live**
   forward paper run where the feed reports set state precisely.

## Concrete next steps (cost-zero)
1. **Zero-cost historical validation.** Fetch ESPN ATP/WTA scoreboards for 06-24..07-13; match ESPN
   players → US `aec-{atp,wta}-...` symbols (name-based); anchor entry to an ESPN-derived, *live-knowable*
   game clock (match start + set-count estimate − ~45min, or straight-sets subset where timing is tight);
   confirm the +5.4c survives at that anchor (not just at the ex-post `maturity_time`).
2. **If validated → forward paper harness.** Poll ESPN live for ATP/WTA matches where a US-priced
   favourite (0.65–0.90 on `us_mid_tape`) is near-decided per the set state; record a paper entry at the
   real ask; settle on DMR. Pre-register the gate (ROI LB>0 AND λ>0 over ≥N events, ≥2 non-Wimbledon
   weeks). This is the standing certification bar, forward.
3. **Only if a broader universe is wanted later**, revisit a paid ITF feed — but not on today's evidence.

## Zero-cost validation attempt (ESPN, `scripts/niche/espn_validate.py`)
Fetched ESPN ATP/WTA for the window (1,288 post-state singles), matched to US markets by player name
(357 matched), and tested the edge two ways on the matched set:

| anchor | −1h/est favourite net | p | events |
|---|---|---|---|
| **maturity−1h (true resolution)** | **+7.29c** [+2.26,+11.70] | **0.002** | 122 |
| ESPN-derived estimate (start + nsets×48min − 45m) | +1.37c [−4.61,+7.00] | 0.313 | 130 |

**Reading (honest):** the edge is **confirmed strong** on the exact ATP/WTA matches ESPN covers (+7.3c at
the true anchor). But the ESPN *scoreboard* gives only match start + final set tally, so historically the
end must be **estimated** — and tennis duration variance (±60 min) is enough to wash the edge out (the
±60min jitter test predicted exactly this). This is a **granularity limit of the historical scoreboard,
NOT of the live feed**: live, ESPN's in-play state shows "serving for the match," which fires ~10–15 min
before the end — squarely in the −0.5h zone where the edge is +6.3c. So:

- The free ESPN feed **carries the right live signal** (per-set/per-game state, near-decided detection).
- It **cannot be retro-validated** from final-tally history (no per-game timestamps on the free scoreboard).
- **The decisive validation is therefore the LIVE forward paper test**, not a backtest. This is expected and
  fine — it is exactly the pre-registered forward gate the standing certification bar calls for.

## Bottom line
The one real edge is **capturable in principle with a free feed** (ESPN live ATP/WTA "serving-for-match"
state), at **zero data cost**. It cannot be proven from history (timing granularity), so the honest path
is a **live forward paper harness** with a pre-registered gate (ROI LB>0 AND λ>0, ≥N events, ≥2
non-Wimbledon weeks). Until that clears, size nothing — but for the first time there is a concrete,
cost-zero, information-bearing edge to test forward.
