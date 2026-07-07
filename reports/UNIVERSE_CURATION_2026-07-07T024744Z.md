# TRADER-UNIVERSE CURATION — Cycle 9 (beat-best-trader)

**UTC 2026-07-07T02:47:44Z** · branch `run/beat-best-trader` · PAPER-ONLY · adopts/arms/promotes/prunes
**NOTHING** · DB read-only (zero writes to `followed_traders`) · no Rust/migration edits · cost-zero (Max-only).

Tue's directive: *"get rid of the unprofitable users, and find new cohorts/people that are more
profitable — long-term, consistent, high-performing ROI/profitability. Ignore the really bad traders
that are somehow in the top leaderboard."*

**Reproduce:** `python3 scripts/universe_curation.py` → `reports/universe_scorecard.json`;
`python3 scripts/curation_guardcheck.py` → `reports/curation_guardcheck.json`. Both `--selftest` green.

---

## The load-bearing nuance (Cycle-8) — honored throughout
Two trader ROLES; a wallet can be good at one and bad at the other:
- **CONSENSUS BACKER** — feeds the favorite-consensus STANDARD. The favorite edge **rides on**
  high-volume/MM-flagged backers. Quantified this cycle: the standard's **522 events are backed by only
  107 distinct wallets, and 473/522 (91%) sit at exactly `min_backers=3`** — so the standard is
  *extremely* fragile to pruning any backer. MM/high-volume is therefore **not** grounds to prune.
- **TAIL / COPY CANDIDATE** — a durable directional predictor we would tail. Curate aggressively HERE.

Every number is LABELED by price basis:
- **THEIR-PRICE skill** = per-event calibration gap at the trader's own fill price (detects skill *now*;
  belief-blind per-wallet null, H0 mean 0 exact). Reused verbatim from `reliability_score.py`.
- **OUR-PRICE realizable** = copy_return at `our_entry = price + 0.013 tax + band_spread`, minus fee
  (the tax-gated *copyable* edge). Reused from `trader_scorecard.py`. Skill at their price does **not**
  imply a copyable edge at ours — that gap is the whole game.

Scope: **1023 tracked wallets** (universe grew from ~475). 850 have fills; **147 are judgeable** (≥30
band-scored events, band 0.45–0.90, trailing 365d); the other ~876 are power-thin (unjudgeable).

---

## U1 — Full-universe scorecard
`reports/universe_scorecard.json` holds every tracked wallet with both roles' factors: their-price
cal_gap + belief-blind null_p, our-price realizable_roi + drop-best-3 robustness, downside-dev/max-DD,
positive-window consistency, n_events/n_days/active-span, longshot %, favorite %, MM/bot flags, and the
durable-quality gate result. Bucket tally over the **147 judgeable**:

| bucket | n | meaning |
|---|---:|---|
| **mm_arber** | 86 | two-sided spread/rebate capture, ~0 directional (MM/bot flagged) |
| **bad_predictor** | 28 | negative calibration gap at their OWN price |
| **skill_within_luck** | 22 | positive cal_gap but not beyond luck (null_p > 0.05) |
| **genuinely_skilled** | 7 | positive **and** copyable at OUR price |
| **longshot_lucky** | 3 | headline carried by a few longshot bombs; dies on drop-best-3 |
| **skilled_not_copyable** | 1 | real skill at their price, eaten by the tax at ours |

**59% of the judgeable top-leaderboard universe are market-makers/arbers** — leaderboard-topping via
volume, not directional prediction.

---

## U2 — The "bad leaderboard" traders to IGNORE (for tailing)

**Headline: 103 of 147 judgeable top-leaderboard traders (70%) are BAD predictors at OUR price.**
Cross-tab of leaderboard rank vs our-price realizable skill:

| rank tier | judgeable | bad@our-price | buckets |
|---|---:|---:|---|
| **1–10** | 4 | **3 (75%)** | mm_arber 4 |
| **11–50** | 24 | 14 (58%) | mm_arber 12, bad_predictor 6, **genuinely_skilled 5**, skill_within_luck 1 |
| **51–100** | 28 | 20 (71%) | mm_arber 18, skill_within_luck 6, bad_predictor 3, skilled_not_copyable 1 |
| **101–200** | 91 | 66 (73%) | mm_arber 52, bad_predictor 19, skill_within_luck 15, longshot_lucky 3, **genuinely_skilled 2** |

Top-**PnL** decile (14 wallets): 8/14 bad at our price; 9 mm_arber, 3 bad_predictor, only 2 genuinely
skilled. **The very top of the leaderboard (rank 1–10) is 100% market-makers** — exactly Tue's "really
bad traders somehow in the top leaderboard." They are inflated by:
- **(a) pure MM/arb** (dominant, 86 wallets): profit from spread/rebate, not prediction. e.g. rank-4
  `wr0ngw4yb3tt0r` (realizable **−12.8%** as a tail candidate).
- **(b) longshot-lucky** (3): positive per-event only via a handful of longshot bombs; drop-best-3 turns
  them negative.
- **(c) big-bankroll-mediocre / bad_predictor** (28): high headline PnL, negative calibration at their
  own price. e.g. rank-15 `dv-pm` (−15.5%), rank-27 `shutitfatty` (−16.1%).
- **(d) genuinely skilled** (7): the only ones worth tailing (U3).

> **IGNORE-for-tailing list** = every `mm_arber` / `bad_predictor` / `longshot_lucky` wallet in the
> scorecard (117 of 147 judgeable). Full per-wallet list with the inflation reason is in
> `universe_scorecard.json` (`bucket` + `bucket_reason`). **But note the U5 guard-check:** 32 of these
> "bad" wallets are consensus-critical backers — ignore them *as tail candidates*, do **not** prune them.

---

## U3 — The high-quality durable cohort (+ NEW names)

**Honest headline: at the strict DURABLE quality bar (≥100 events + ≥20 days + consistent + non-longshot
+ directional + copyable), ZERO wallets clear.** This is a real, uncomfortable finding, and it has a
clean root cause: **every wallet durable enough (≥100 band events) is MM-flagged**; every wallet with
clean directional skill has **< 100 events**. The clean and the durable populations don't intersect yet.

At the **relaxed ≥30-event bar**, 7 wallets are genuinely skilled **and** copyable at our price:

| name | ev | span(d) | cal_gap (their) | null_p | **realizable (our)** | drop-best3 | sports | rank | durable? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:--|
| **cnyek** ⭐NEW | 34 | 58 | +0.177 | 0.0002 | **+21.3%** | +14.1% | 1 | 21 | no (single-sport) |
| RISK-IS-NEVER-OK ⭐NEW | 34 | 8 | +0.149 | 0.004 | +17.3% | +9.8% | 1 | 22 | no (8-day burst) |
| **master-wuji** (of 4) | 78 | 60 | +0.132 | 0.0004 | **+15.7%** | +12.2% | 3 | 136 | **YES** |
| cigarettes ⭐NEW | 82 | 6 | +0.098 | 0.003 | +7.0% | +3.5% | 3 | 32 | no (6-day burst) |
| **acorp** (of 4) | 70 | 80 | +0.077 | 0.021 | **+5.9%** | +1.8% | 4 | 170 | **YES** |
| Oneger ⭐NEW | 58 | 23 | +0.074 | 0.037 | +5.6% | +0.6% | 1 | 42 | no (single-sport) |
| lookaon ⭐NEW | 31 | 44 | +0.062 | 0.003 | +3.9% | **−2.5%** | 1 | 42 | no (drop3 negative) |

**Only master-wuji and acorp are durable** (long active span, multi-sport, robust to dropping the best 3
events). They are 2 of the current 4 — **and they survive**. The 5 NEW names (cnyek, RISK-IS-NEVER-OK,
cigarettes, Oneger, lookaon) are **promising but power-limited**: single-sport, or an 6–8-day burst, or
fragile on drop-best-3. They are **WATCH candidates, not certifiable** — do not tail on this evidence.

**Status of the current "4":**
- **master-wuji** ✅ durable, best all-rounder (nba/multi, +15.7% realizable).
- **acorp** ✅ durable, broadest (4 sports, +5.9% realizable).
- **Sportbetting76** ⚠️ **DECAYED** — now `skill_within_luck` (cal_gap +0.007, null_p 0.40,
  realizable **−5.8%**) over the trailing 365d. No longer a skilled tail candidate → **DROP candidate**.
- **DaBossHogg** ⚠️ now **MM-flagged** (`mm_arber`; 264 events, 5 sports, realizable **+0.9%**). Durable
  and near-copyable but flagged two-sided; marginal as a tail candidate. Keep tracking, don't tail.

The near-miss (fail only `directional_not_mm`, but ≥100 events and positive realizable): `0x6db568e6`
(167 ev, +3.3%), `Latina` (104 ev, +3.0%), `DaBossHogg` (264 ev, +0.9%). If the MM screen is
over-excluding genuine directional traders who *also* do some two-sided flow (the Cycle-8 open question),
these three are the only durable+copyable candidates in the whole universe — worth a **targeted MM-screen
audit** (deferred), not a tail decision.

---

## U4 — Sub-cohorts / sub-groups

Segmenting the 103 positive-skill judgeable wallets by their best (sport × band) cell (`≥2` wallets):

| cell | wallets | copyable@our-price | mean gap (their) | notable members |
|---|---:|---:|---:|---|
| **soccer · band-4 (0.60–0.80)** | 20 | 6 | +0.117 | cnyek, acorp, Oneger, sport-intelligence, Sportbetting76 |
| **soccer · band-3 (0.40–0.60)** | 17 | 9 | +0.154 | RISK-IS-NEVER-OK, johndegen, Latina, DaBossHogg |
| tennis · band-5 (0.80–1.0) | 9 | 3 | +0.130 | RN1, tradecraft, ferrariChampions2026 |
| mlb · band-3 | 6 | 4 | +0.133 | (mostly hashed wallets) |
| **nba · band-3** | 5 | 2 | +0.187 | **master-wuji, djokowin** |
| other · band-4 | 6 | 2 | +0.182 | cigarettes, JT716 |

**Finding:** directional skill **concentrates in the favorite-leaning bands of soccer/mlb/nba (b3–b4)** —
exactly where the favorite-consensus STANDARD already lives (consistent, cross-validating). The best-
populated groups are soccer b3/b4. **But the copyable fraction is only ~30–50%** (their-price skill ≫
our-price survivors), and this is a *descriptive* segmentation of best-cells, **not** an out-of-sample
certified +EV sub-cohort. **No sub-cohort is certifiable** on this record — none clears ≥2 disjoint
NON-soccer regimes with a copyable-at-our-price LB. Diversification note: the clean directional names are
spread across soccer/nba/mlb cells, so a *future* multi-name tail book would have some sport
diversification — but the pool is too thin and too soccer-weighted to bank now.

---

## U5 — Prune + Add, GUARD-CHECKED

### PRUNE (deferred human review — DB not touched)
**79 wallets** are safe-to-prune tail candidates: they help **neither** role — a losing/no-skill
predictor at our price **AND** not one of the 107 favorite-consensus backers. Breakdown:
mm_arber 36, bad_predictor 21, skill_within_luck 18, longshot_lucky 3, skilled_not_copyable 1. Full list
in `curation_guardcheck.json` → `U5_prune_guard.prune_list`. (Plus ~173 tracked wallets with **zero
captured fills** — pure dead weight — could be dropped, but conservatively left for a capture-health
review rather than pruned blind.)

### GUARD-CHECK — pruning must NOT regress the consensus standard ✅
- **32 "bad-looking" wallets are consensus-critical backers** (21 mm_arber, 7 bad_predictor, 4
  skill_within_luck; incl. **rank-4 `wr0ngw4yb3tt0r`**, realizable −12.8% *as a tail candidate* but a
  backer the standard rides on). These are **excluded from the prune list and flagged KEEP** — the exact
  tension the nuance warns about. Pruning them *would* strip the standard.
- Because the favorite consensus signals are **defined by their backer set**, pruning only the 79
  **non-backer** tail wallets **cannot change the recorded signals by construction** — the standard is
  unaffected.
- Confirmed via `scripts/standard_guard.py` (re-measure, no code change): champion **REGRESSION STATUS =
  HEALTHY** (belief-blind LB **+4.42% > 0**, p_emp 0.0000, 167 ev). **The champion STANDS unchanged** —
  the pruned universe removes no backer, so it neither beats nor regresses the standard. Pruning the bad
  TAIL traders is **safe**.

### ADD (deferred — no API calls, `followed_traders` untouched)
The universe is **not** missing quality at the top — the top is MM. The binding gap is **power/durability**
(every clean directional trader has < 100 events), **not coverage**. Recommendations:
1. **Do NOT ingest by headline rank/PnL** — rank ≤ 10 is 100% market-makers (bad tail candidates).
2. **Deepen fill history** on the existing near-miss cohort (master-wuji, acorp, cnyek, djokowin, Oneger,
   RISK-IS-NEVER-OK) so they can reach the ≥100-event durable bar — the fastest path to a *real* cohort.
3. **Audit the MM screen** against the 3 durable+copyable near-misses (`0x6db568e6`, `Latina`,
   `DaBossHogg`) — if it's over-excluding genuine directional traders with incidental two-sided flow,
   they are the only durable copyable names in the universe.
4. Ingest more **mid-rank (20–170) recurring WEEK+MONTH** members to grow the clean-directional pool
   (that rank band is where cnyek/master-wuji/acorp/Oneger actually live).

---

## Honest bottom line (critical partner)
- **The complaint is real and quantified:** ~70% of judgeable top-leaderboard traders are bad at our
  price; the very top (rank 1–10) is entirely market-makers.
- **The high-quality durable cohort is still tiny and fragile:** at the strict long-term bar it is
  **empty**; at the relaxed bar it is **7**, of which only **master-wuji and acorp** are durable — and
  those two are already tracked. The 5 NEW names are watch-list, not bankable (single-sport / burst /
  drop-3-fragile). This is **skill detectable at their price**, not a **certified copyable edge at ours**.
- **One of the current 4 (Sportbetting76) has decayed** and a second (DaBossHogg) is now MM-flagged —
  the cohort erodes without maintenance, which is itself the argument for this scoring loop.
- **Nothing is promoted, armed, adopted, or pruned.** Prune (79) / add / drop-Sportbetting76 are DEFERRED
  human-review recommendations; the guard-check confirms the safe prune does not touch the standard,
  which stands HEALTHY. Real-money eligibility unchanged (binding constraint: non-expiring regime
  persistence over months + the realizable tax).
