# Per-sport edge tracker — softness vs skill, watched forward (2026-07-02, entry 15)

Branch `feat/sport-tracker` (worktree off `main` 2002e00, tag `pre-sport-tracker-20260702`).
Follow-up to the truth audit (entry 13): the favorite edge is real but lives on ~4 correlated
summer days. The open question — is it a durable selection SKILL that survives in the sharp
markets of the fall (NFL Sept, NBA Oct), or a soft-tournament artifact? — is now watchable per
sport as samples grow.

## The instrument
`scripts/sport_edge_tracker.py` (self-test PASS: soft-no-skill vs efficient-skill fixtures, verdict
routing, fall-sport classification, N-floor). For each sport it decomposes the consensus-favorite
edge, event-clustered at the match super-key, at-fire entry:
- **market SOFTNESS** = blind-favorite edge (mean `won − entry` over `_blind` favorites, entry≥0.6).
  Large ⇒ favorites underpriced ⇒ soft/inefficient market. ≤0 ⇒ sharp market.
- **selection SKILL** = surplus over the regime×band blind favorite — what the consensus ADDS. This
  is the durable number; it must survive where softness ≈ 0.
- **total** = softness-at-band + skill.

Sports below N=20 events read INDETERMINATE (the watch-list). NFL/NBA/CFB/CBB/NHL slug prefixes are
pre-wired so they classify the moment they appear in the fall.

## First read (favorite, 2026-07-02)

| sport | ev | ev/d | win% | softness | skill | total | interpretation |
|---|---|---|---|---|---|---|---|
| **tennis** | 48 | 12.0 | 90% | **+1.8%** | **+11.8%** | +12.6% | **REAL skill in an EFFICIENT market ★ (transfer signal)** |
| soccer | 11 | 2.8 | 93% | +8.1% | +6.4% | +9.3% | watch (thin) — half softness, half skill |
| mlb | 9 | 3.0 | 100% | **−3.7%** | +25.4% | +23.8% | watch (thin) — sharp market, big point est. on N=9 |
| other | 5 | 2.5 | 100% | +1.0% | +15.9% | +16.9% | watch (thin) |

`elite_fresh_fav`: tennis 19 ev (skill +8.0%, efficient) + soccer 10 ev (skill +5.7%, soft) — both
below floor, both tournament-only. Confirms elite has no MLB/other regime (goes silent post-Wimbledon).

## What it tells us
- **The one sport over the floor — tennis — is the transfer signal.** Wimbledon is an *efficient*
  favorite market (softness +1.8%) yet consensus-favorite skill is +11.8%. That is genuine selection,
  not soft-market riding — the best evidence the edge could survive in efficient markets like NFL/NBA.
- **Soccer's edge is half softness** (+8.1% soft market) — that half will NOT transfer to sharp sports.
- **MLB is the live efficient-market test** (softness −3.7%, favorites overpriced). Its +25.4% skill is
  on 9 events — almost certainly small-sample; the point of the tracker is to watch it converge as MLB
  accrues daily through October, then NFL (Sept) and NBA (Oct).
- **The durable question is now measurable:** does SKILL persist where SOFTNESS≈0? Re-run at +7 days /
  after each new sport crosses N=20 / at the WC & Wimbledon ends. A big TOTAL that is all softness is a
  summer artifact; skill in efficient markets is the real edge.
