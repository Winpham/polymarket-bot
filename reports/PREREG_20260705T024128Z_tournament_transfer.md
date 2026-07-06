# PRE-REGISTRATION — Tournament-transfer frame (does the favorite-softness edge repeat across tournaments?)

**Frozen:** 2026-07-05T02:41:28Z (UTC). **Branch:** `feat/tournament-transfer`. **Paper-only,
read-only, promotes nothing, arms nothing.** Belief-blind: all rules/thresholds/verdicts frozen here
BEFORE the instrument runs. Inherits every audited convention of the merged regime work
(small-cluster **t(G−1)** LBs, matched cat×band baseline, super-event key, honest permutation-guard
labeling) — see `reports/entries/2026-07-04-regime-persistence-AUDIT.md` and its ADDENDUM2.

## 0. The thesis being tested (why this frame exists)

The merged regime run labeled the edge `SOCCER-ARTIFACT` because it lives in *expiring tournaments*
(World Cup soccer, Wimbledon tennis) rather than regular-season leagues. But **tournaments are a
perpetual class** — one ends, the next begins (Wimbledon → US Open → next major → playoffs → next
World-Cup cycle). If the edge is *"casual/patriotic money floods thin high-profile tournament markets
and underprices favorites,"* it is NOT expiring — it is a recurring structural feature. This frame
re-parameterizes the regime axis from `sport×month` to **tournament identity** and asks the thesis's
real question: **does the favorite-softness edge TRANSFER across DIFFERENT tournaments?** If yes, the
"artifact" reframes as a durable tournament-class edge. If no (each tournament idiosyncratic), the
artifact read stands. This changes WHAT we test, NOT how rigorously — the belief-blind gate holds.

## 1. Tournament classifier (frozen)

`classify_tournament(sport, market_type, slug, title) -> (tournament_id, is_tournament)`, deterministic,
matched on lower-cased `slug + " " + title`. `tournament_id` is the canonical competition; `is_tournament`
gates which regimes count for the cross-tournament test.

- **Tournament keyword → canonical id** (first match wins): `world cup`/`worldcup`/`fifwc` → `world-cup`;
  `wimbledon` → `wimbledon`; `us open`/`usopen` → `us-open`; `roland`/`french open` → `roland-garros`;
  `australian open`/`ausopen` → `australian-open`; `euro ` → `euro`; `champions league`/`-ucl-` →
  `champions-league`; `-msi-`/` msi ` → `lol-msi`; `worlds` → `esports-worlds`; `olympic` → `olympics`;
  `super bowl`/`superbowl` → `super-bowl`; `world series` → `world-series`; `playoff`/`postseason` →
  `<sport>-playoffs`; other bounded markers (`grand slam`, `-final`, `knockout`, one-off `primary`/
  `nominee`) → `<sport>-tournament-other`. `is_tournament = True` for any of the above.
- **Non-tournament** (regular-season league play, ongoing crypto/econ): `is_tournament = False`,
  `tournament_id = f"{sport}-league"`. These are reported but EXCLUDED from the cross-tournament
  transfer count (a league is not a tournament instance).
- A printed live audit maps every event to its `tournament_id` so a human can eyeball edge cases.

## 2. Edge metric per tournament (frozen)

For each `tournament_id`: favorite surplus over the MATCHED (category×5-band) blind-favorite baseline,
event-clustered at the super-event key, flat-SHARES, at-fire entry; independent-cluster COUNT (G);
one-sided 95% **small-cluster t(G−1)** LB (`regime_edge.lb_small_cluster`, `None` for G<2); and
`net_taker` / `net_maker` after the copyability tax (reuse `regime_net_edge`). Reuse the merged
helpers byte-identically.

## 3. Cross-tournament transfer test (frozen) — the binding leg

Leave-one-**tournament**-out over `is_tournament=True` regimes with data:
- fit "edge exists" (matched-baseline surplus > 0) on all-but-one tournament; test held-out tournament
  `t(G−1) LB > MARGIN`; count how many of ≥ `TRANSFER_MIN_TOURNAMENTS = 2` hold out successfully.
- matched **tournament-permutation null** (permute tournament labels, preserve sizes, `N_PERM=1000`,
  `SEED=20260705`) as a CONCENTRATION guard, reported honestly with the ADDENDUM1 direction and the
  ADDENDUM2 honesty diagnostics (`guard_can_fire`, `min_p_conc`, `beat_null_can_pass`). Leg is a RAW
  count when the guard is inert — never headlined "PASS".

## 4. Contemporaneity axis (frozen) — the honesty crux

Cross-tournament transfer is measured on tournaments that may OVERLAP in time. Report, per tournament,
its calendar span, and classify the transfer:
- **CONTEMPORANEOUS** — the transferring tournaments overlap in time (e.g. this record: World Cup +
  Wimbledon + MSI all within one 6-day window). This is cross-SPORT / cross-tournament transfer but
  NOT forward-in-time — it is NECESSARY but NOT SUFFICIENT for real money.
- **FORWARD** — at least one transferring tournament is time-SEPARATED (starts after the others end),
  so the held-out tournament is a genuine forward out-of-sample instance of the tournament class.
Two tournaments are "time-separated" iff their date ranges do not overlap.

## 5. Verdict ladder (frozen)

Applied to `is_tournament=True` regimes:
1. **`PENDING`** — < `TRANSFER_MIN_TOURNAMENTS` tournaments with computable (G≥2) data.
2. **`REFUTED`** — a held-out tournament's edge upper bound < 0 (the edge decayed on a held-out tournament).
3. **`TOURNAMENT-IDIOSYNCRATIC`** — transfer count < 2 (the edge does NOT hold out on other tournaments)
   → each tournament's edge is its own thing → the artifact read stands.
4. **`CROSS-TOURNAMENT-CONTEMPORANEOUS`** — ≥2 tournaments transfer, but all CONTEMPORANEOUS → the
   favorite-softness edge is not sport-specific (encouraging for the thesis), but forward-in-time
   persistence is unproven. Real money REMAINS gated. (Today's expected read: World Cup + Wimbledon
   [+ MSI] all contemporaneous.)
5. **`CROSS-TOURNAMENT-FORWARD`** — ≥2 tournaments transfer AND ≥1 is time-SEPARATED (forward) → genuine
   forward persistence of the tournament-class edge → the real prize. STILL gated (§6).

## 6. Real-money stance (unchanged, non-negotiable)

Cross-tournament transfer — even FORWARD — is NECESSARY but NOT SUFFICIENT for real money. The other GO
gates stand: **edge-reality (λ̂ > 0.25)** — is it information or favorite-longshot bias? — and
**net-positive after the copyability tax** in the transferring tournaments. Real money is a Tue-gated
pilot decision after λ + persistence + net-positive all clear; NEVER armed autonomously. `PILOT_ARMED`
unset, `EARN_DEEP_SHARPS` false, alert path untouched. The verdict promotes nothing.

## 7. Frozen constants
`MARGIN=0.03`, one-sided 95% small-cluster t(G−1), `TRANSFER_MIN_TOURNAMENTS=2`, `N_PERM=1000`,
`SEED=20260705`, matched cat×band baseline, super-event key, flat-shares, copyability tax
(`FOLLOWER_TAX=0.013`, `FEE=0.02` buffer + fee=0 companion), maker δ0/5m from `maker_fill_sim.json`.
