# Autonomous Run: Regime Persistence & Net-Edge — is the edge stationary, or soccer-shaped?

> **Read this whole brief before touching anything.** You are an autonomous build worker on
> `~/polymarket-bot` (Rust + SQL Polymarket consensus/copy-trading bot). **PAPER-ONLY.** Models:
> **Opus / Sonnet ONLY** (never Haiku; never set `ANTHROPIC_API_KEY`; never spawn child `claude`
> processes). Work on ONE branch `feat/regime-persistence` in a git worktree
> (`git worktree add wt/regime-persistence -b feat/regime-persistence`). Build items **SEQUENTIALLY**.
> Gate per item = `cargo build && cargo test` (if you touch Rust) + `--selftest` for every script.
> **DO NOT merge to main** — a `main` HEAD advance auto-deploys to the running bot (launchd
> autoupdater, `scripts/consensus-autoupdate.sh`). Leave the branch for review.

> **Migrations:** this run should need **NONE** (all instruments are read-only Python + JSON
> forward-seals). `ls migrations/` first; highest today is `039`. `040` is claimed by the MM-filter
> chat. If you can prove a durable per-regime snapshot table is genuinely required, claim `042`
> (check it's free first) — but PREFER a forward-sealed JSON. **NEVER edit an already-applied
> migration** (sqlx checksum crash-loops the app).

---

## 0. The one-paragraph truth (why this run exists)

Time-diversification (spreading independent bets across many days instead of forcing them into one
day) **solves statistical power** — 300 uncorrelated events give the same power whether collected in
a day or a year, and the risk policy already does this (flat-shares + 13%/day deploy cap). What it
does **not** solve is **stationarity**: today's ~+5% edge is *soccer-carried, World-Cup-heavy* — an
**expiring** regime. Pooling 500 more soccer bets tightens the estimate of a possibly-non-repeating
phenomenon; a precise estimate of a disappearing edge is worthless. The gate's "≥2 disjoint
NON-EXPIRING regimes over months" requirement is exactly this stationarity test, not a disguised
sample-size ask. **This run builds the instrument that decomposes the edge PER REGIME, tests whether
it REPEATS out-of-sample in DISJOINT recurring regimes (beating a matched null), nets it against the
copyability tax per regime, and makes the whole thing legible on the readiness board so
"accumulate over months" becomes watchable.** It answers, honestly and pre-registered: *is there an
edge that survives a regime change and survives costs — or only a soccer artifact?* It promotes
nothing and touches no real money.

## 1. What ALREADY exists — extend/reconcile, do NOT rebuild (read these first)

- `scripts/persistence_tracker.py` — TEMPORAL out-of-sample test (split at a cutoff, read edge on
  OUT rows only; cluster-robust SE + independent-cluster-COUNT floor; already emits a per-regime OUT
  breakdown flagging regimes NOT present in-sample). Verdict: PENDING / PERSISTS / REFUTED /
  INDETERMINATE. **This is your spine — extend it, don't fork it.**
- `scripts/softness_map.py` — per `category × market-type × band` cell decomposition with a MATCHED
  baseline, BH-FDR multiplicity, bootstrap realizable LB. The model for per-cell edge + the
  composition-trap-safe baseline. Reuses `selection_null` (fetch/band/regime/blind edge),
  `effective_n` (cluster_robust, independent-cluster count), `portfolio_concentration` (match key).
  **Reuse those helper modules byte-identically** — do not re-derive event-clustering, the baseline,
  or the cluster count.
- `scripts/copyability.py` + `reports/copyability.json` — the copyability tax at OUR repriced entry
  (`price + 0.013 follower-tax + band spread`, fee 2% buffer). `scripts/maker_fill_sim.py` +
  `reports/maker_fill_sim.json` — the maker-at-price execution finding (limit at δ=0¢ / 5m dominates
  taker with a favorable adverse-selection gap). **Net-after-tax uses these, does not re-measure the
  tax.**
- `scripts/best_trader_benchmark.py`, `scripts/unified_book.py`, `scripts/readiness_ledger.py` (now
  carries `router_gate` / `unified_book` / `beats_best_trader` rows from the capture-hardening run) —
  the board you'll extend in Item 5.
- `DECISIONS.md` D16–D28; memory-relevant reports: `reports/entries/2026-07-04-*` (proven-router,
  unified-risk-benchmark, capture-hardening). The edge facts to hold in mind: favorite mean +5.4% /
  LB −7.1%; router surplus +5.3% p=0.034 / LB −9.8% soccer-carried; λ̂≈0.15 (< 0.25 floor);
  B_LB (best copyable) +3.4%; 0/12 orthogonal strategies certified. **Nothing is bankable — the
  honest prior is INDETERMINATE-BY-POWER, leaning positive, with a real chance it's net-negative.**

## 2. Non-negotiable anti-self-deception rules (every item obeys these)

1. **Belief-blind, pre-registered.** Freeze every threshold, regime definition, and null in Item 0
   BEFORE any instrument runs. Write them to `reports/PREREG_<UTC-ts>_regime_persistence.md`. Do not
   tune anything afterward. If a later item wants a different constant, it FAILS — re-register in a
   new stamped file and say why.
2. **The unit of independence is the EVENT/game, day-clustered.** Event-cluster at the match
   super-key (`superkey.super_event`, as softness_map/persistence_tracker do), then cluster the SE by
   independent-cluster COUNT (not a day-deflated SE that over-credits correlated days). Raw signal
   count is NEVER the N. Reuse `effective_n.cluster_robust`.
3. **The right baseline, never zero.** Edge = surplus over the MATCHED (category/regime × band)
   blind-favorite baseline — the composition-trap-safe convention from softness_map. Comparing a
   pooled surplus to a 0-baseline false-promotes population favorite-longshot bias (the `market_resid`
   trap, D-record). Blind-favorite base rate is the floor, not zero.
4. **A selection/transfer claim must beat a MATCHED null, not just chance** (the MM-filter D29
   lesson: excluding flagged wallets did NOT beat a matched-subset null → NO-GO). "The edge transfers
   across regimes" must beat a null where regime labels are permuted / a matched random regime split —
   report the permutation p and the null distribution, not just the point.
5. **Expiring regimes do NOT count toward the non-expiring bar.** A World-Cup / single-elimination /
   playoff / one-tournament edge is EXPIRING by construction; it can be *reported* but must be
   EXCLUDED from the "≥2 disjoint non-expiring regimes" verdict. This is the crux of the whole run.
6. **flat-SHARES, never flat-$** (flat-$ flips the sign of the favorite edge; D-record). All sizing/
   P&L reads are flat-shares.
7. **Read-only, paper-only, additive.** No arming, `PILOT_ARMED` stays unset, `EARN_DEEP_SHARPS`
   false, alert path untouched. Nothing promotes. Every new file is additive (revert = delete).

---

## ITEM 0 — PRE-REGISTRATION (write the frozen spec FIRST; build nothing else until it's written)

Write `reports/PREREG_<UTC-ts>_regime_persistence.md` fixing ALL of the following BEFORE any
instrument runs. This file is the honesty anchor; the instruments must read their constants from it
(or hard-code the identical frozen values with a comment pointing back to it).

1. **Regime taxonomy.** `regime_id = (sport/category, time-block)` where time-block = calendar month
   (the disjoint-cluster unit). Sport/category from the existing `market_taxonomy` / `sport_bucket`
   derivation the scripts already use (do NOT invent a new one).
2. **Regime-TYPE classifier (the crux).** A deterministic rule assigning each regime one of:
   `recurring` (regular-season league play that recurs indefinitely — e.g. MLB/NBA/EPL regular
   season, ongoing crypto/econ markets), `expiring` (bounded tournaments / single-elimination /
   playoffs / World Cup / Wimbledon / one-off events), or `unknown` (unclassifiable → treated as
   expiring for the conservative verdict). State the exact keyword/slug rules. Err toward `expiring`
   when ambiguous (conservative: harder to certify).
3. **The edge metric per regime:** event-clustered surplus over the matched blind-favorite baseline,
   at OUR repriced entry (copyability-tax-netted), flat-shares, with a cluster-robust one-sided 95%
   LB. Arms in scope: `favorite` and `proven_router` (the two live paper arms).
4. **The persistence bar (frozen).** The edge "persists" only if BOTH: (a) TEMPORAL — LB(OUT-of-
   sample surplus) > `PERSIST_MARGIN` on ≥ `PERSIST_MIN_CLUSTERS` independent OUT clusters (reuse
   persistence_tracker's frozen constants — do NOT re-pick them); AND (b) CROSS-REGIME — leave-one-
   regime-out transfer: the edge fit on all-but-one RECURRING regime holds (LB>margin) on the held-out
   RECURRING regime, for ≥ `TRANSFER_MIN_REGIMES` (register = 2) disjoint recurring regimes, beating a
   matched regime-permutation null at `p ≤ 0.05`. Register the exact numbers.
5. **Net-after-tax rule.** A regime is `net_positive` iff its tax-netted LB > 0 using the measured
   copyability tax (and, as a second column, under the maker-at-price δ=0¢/5m policy). Register the
   tax source (`reports/copyability.json` / `maker_fill_sim.json`) and that fee=2% is the buffer basis
   with a fee=0 companion column.
6. **The overall verdict ladder (frozen):** `SOCCER-ARTIFACT` (edge concentrated in expiring
   regimes; recurring-regime edge INDETERMINATE/negative) · `PENDING` (recurring regimes below the
   cluster floor — the accrual wall; report how many more days) · `PERSISTS-NET` (both persistence
   legs pass on recurring regimes AND ≥2 recurring regimes are net_positive) · `REFUTED` (recurring
   OUT upper-bound < 0). Today's expected read is `SOCCER-ARTIFACT` or `PENDING` — that is the honest
   state, and saying so loudly is a successful outcome.

**Acceptance:** the file exists, every downstream instrument cites it, and no later item introduces a
threshold not in it.

## ITEM 1 — Regime-type classifier (the one genuinely new primitive)

`scripts/regime_classify.py` (read-only, importable): `classify_regime(sport, market_type, slug,
title) -> (regime_id, regime_type)` implementing Item-0's rules exactly. Deterministic, no network,
no DB in the pure path. This is imported by Items 2–5 so the expiring/recurring split is defined
ONCE. `--selftest`: a World-Cup soccer slug → `expiring`; an MLB regular-season slug → `recurring`;
a playoff/single-elim slug → `expiring`; an unclassifiable slug → `unknown`→treated-expiring. Include
a printed audit of how every regime currently in the archive classifies (so a human can eyeball the
edge cases before trusting the verdict).

**Acceptance:** `--selftest` green; the live audit prints each populated regime with its type and the
rule that fired.

## ITEM 2 — Per-regime edge decomposition + concentration (`scripts/regime_edge.py`)

Reusing `selection_null` / `effective_n` / `softness_map`'s baseline (byte-identically), for each arm
× regime: event-clustered tax-netted surplus over the matched baseline, N_events, N independent
clusters, cluster-robust LB, and `regime_type`. Then the two headline reads the pooled number hides:

- **Concentration:** HHI (or top-1 share) of the pooled edge across regimes — "is the +5% one-regime-
  carried?" Report the single regime carrying the most, and the pooled edge with that regime removed.
- **Breadth:** how many DISTINCT regimes have any data, split recurring vs expiring, and how many
  clear the per-regime cluster floor.

Emit `reports/regime_edge.json`. `--selftest` on fixtures: an injected soccer-only edge reads high
concentration + `SOCCER-ARTIFACT`-shaped; an edge spread across 3 recurring regimes reads low
concentration.

**Acceptance:** live run prints the per-regime table + concentration/breadth; JSON written; selftest
green. (Expected today: pooled edge heavily concentrated in expiring soccer.)

## ITEM 3 — Cross-regime persistence test (extend `persistence_tracker.py` → `scripts/regime_persistence.py`)

The binding test. Two legs, both required, verdict resting ONLY on `recurring` regimes:

- **Temporal (leg a):** reuse persistence_tracker's leak-free cutoff split + frozen cluster floor,
  but read the OUT edge PER regime_type; the verdict uses recurring-regime OUT clusters only.
- **Cross-regime transfer (leg b):** leave-one-regime-out — fit "edge exists" (matched-baseline
  surplus > 0) on all-but-one recurring regime, test LB>margin on the held-out recurring regime;
  require ≥ `TRANSFER_MIN_REGIMES`. Beat a matched **regime-permutation null** (permute regime labels
  N times; where does the real transfer sit?) at the registered p. Report the null distribution.

Emit `reports/regime_persistence.json` with the Item-0 verdict ladder result + both legs' numbers +
the null. `--selftest`: a synthetic edge present in 3 recurring regimes → PERSISTS; an edge only in
one expiring regime → SOCCER-ARTIFACT; thin recurring data → PENDING; a decaying edge → REFUTED.

**Acceptance:** selftest exercises all four verdicts; live run reads the honest current state and
names the binding constraint (almost certainly: too few recurring-regime clusters → PENDING).

## ITEM 4 — Net-edge-after-tax per regime (`scripts/regime_net_edge.py`)

For each arm × regime: gross surplus → minus the measured copyability tax (`copyability.json`) →
`net_taker`; and minus the maker-at-price δ=0¢/5m improvement (`maker_fill_sim.json`) → `net_maker`.
Flag `net_positive` per Item-0. Answer: **even if it persists, in WHICH regimes is it net-positive
after costs — and is any recurring regime net-positive?** Both fee=2%-buffer and fee=0 columns.
Emit `reports/regime_net_edge.json`. `--selftest` on fixtures (a +8% gross soccer cell nets positive;
a +3% gross cell under a 5% tax nets negative → not bankable even if real).

**Acceptance:** live table of gross → net_taker → net_maker per regime with the net_positive flags;
JSON + selftest green.

## ITEM 5 — Readiness board: make "accumulate over months" legible (extend `readiness_ledger.py`)

Add a **per-regime persistence panel** (informational, NOT a GO gate) reading
`regime_persistence.json` / `regime_edge.json` / `regime_net_edge.json`:
- one line per recurring regime with data: STATUS / edge LB / N clusters / net-after-tax / net_positive;
- a `concentration` line (pooled edge one-regime-carried? top-1 share);
- a `breadth` line (recurring regimes cleared / needed toward the ≥2 non-expiring bar);
- REWIRE the existing `persistence` GO-gate's `current`/`needs` to consume `regime_persistence.json`
  so the binding-constraint read is regime-aware (e.g. "1/2 recurring regimes cleared; soccer is
  expiring") — but keep it a GO gate with the SAME frozen bar; do not weaken it.
Keep the binding-constraint headline logic intact (longest-horizon unmet GO gate). `--selftest` on
fixture JSONs for the new panel + the rewired persistence gate.

**Acceptance:** board renders the panel + regime-aware persistence line; selftest green; the
headline still reads NOT-YET / binding=persistence.

## ITEM 6 — (STRETCH, report-only) Within-day effective-independence sizing check (`scripts/independence_sizing.py`)

Validates the sizing thesis directly: measure the ACTUAL same-day cross-market correlation
(game-stacking / same-slate) and report `N_eff` (effective independent bets/day) vs the NOMINAL
count, and whether the 13%/day deploy cap is sized to `N_eff` (true independence) rather than nominal
market count. Reuse `portfolio_concentration`'s match key + `effective_n`. Emit
`reports/independence_sizing.json`. `--selftest`. **Report a recommendation only — build/deploy
nothing.** If the spine (Items 0–5) consumed the run, SKIP this and note it in the report.

## ITEM 7 — DO NOT BUILD (report status only)

Anything that arms, sizes real money, or flips a live flag. If the verdict comes back PERSISTS-NET
(it will not, today), the correct next action is a Tue-gated pilot decision, NOT an autonomous build.
State that and stop.

---

## STANDING GUARDRAILS
- NO REAL MONEY. `PILOT_ARMED` unset; `EARN_DEEP_SHARPS` false; alert path (strict-only) untouched.
- Never move a threshold / prereg constant / regime rule after Item 0 freezes it. Never merge/rebase
  `main`. Never push to origin. No new migration unless truly required (then `042`, checked free).
- Commit per item with a NEW/EXTEND-flagged message ending
  `Co-Authored-By: <model> <noreply@anthropic.com>`.
- Reconcile, don't duplicate: reuse `selection_null` / `effective_n` / `portfolio_concentration` /
  `persistence_tracker` / `softness_map` helpers byte-identically. If you find yourself re-deriving
  event-clustering, the baseline, or the cluster count, STOP and import instead.

## FINAL REPORT
`reports/entries/<UTC-date>-regime-persistence.md` — per item built/tested/what-changed/how-verified,
then the headline: **the current honest verdict** (SOCCER-ARTIFACT / PENDING / PERSISTS-NET /
REFUTED), the concentration number, how many recurring regimes have cleared vs the ≥2 bar, which
regimes (if any) are net-positive after tax, and the single binding constraint with its ETA. Be
brutally honest — a loud "it's a soccer artifact, here's exactly how many months of recurring-regime
data until we can tell" is the WIN condition, not a hedge. Then STOP and hand back for review; the
reviewing chat (or Tue) merges → autoupdater deploys.
