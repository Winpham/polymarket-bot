# FORGE DEBATES — Market-Making Stage-0 (compressed record)

## Pipeline
Diagnostician (opus) → Designer A Direct + Designer B Rethink (opus, parallel) → orchestrator
reality-check + synthesis (verified the two load-bearing claims against the LIVE API). 4 agents, 3 rounds.

## Diagnostician verdict
Do NOT pivot to MM. Dominant move = flip `DENSE_CAPTURE` (measure λ; serves both the favorite edge and
the MM signal-skew thesis; `signal_price_trajectory` is 0 rows today). MM earns at most a $0 Stage-0
measurement, gated on the US-person-ToS Tue question. Found an existing `MARKET-MAKING-THESIS-AND-PLAN.md`
(§3.1-3.6: infra-from-zero, legal bar, 10-100ms vs 0.36ms latency, reward compression, ~$50k floor, UMA
tail). All dossier code anchors verified (ClobBook drops bids/size, zero signing crates, pilot.rs
NoPlacer, ws.rs in trading-bot, dense_capture flag-OFF).

## Designer A — Direct (Rust build)
Full coding-ready Rust design: extend `ClobBook`/`BookLevel` (+bids,+size), `parse_book_depth`/
`fetch_book_depth`/`fetch_recent_trades`, `mm_capture.rs` (clone dense_capture), migration 039
(mm_book_depth + mm_trade_print), `MM_CAPTURE/MM_INTERVAL_SECS/MM_NICHE_TOKENS` flags, `mm_select_niches.py`,
`mm_spread_null.py`. **Its decisive honest call:** REST `/book` ALONE cannot observe adverse selection —
you need the executed-trade TAPE (fill happens between polls; /book shows only the resting book). Designed
a `/book`+`/trades` co-poll (no WS needed for slow niches) + a conservative back-of-queue fill model +
belief-blind null + surplus_bounds LB + D23-style go/no-go + self-tests. Flagged fee schedule / trade
endpoint / maker-taker flag as build-time unknowns.

## Designer B — Rethink (Python ladder)
Reframe: the Rust build is unnecessary to FALSIFY. Verified two facts that collapse it: (1) `/book`
already returns full L2 depth (bids+asks+sizes) — Rust struct limitation, not API; (2) `/prices-history
?interval=max&fidelity=1` gives dense retroactive 1-min mids for ANY market. 3-rung Python ladder, kill at
the cheapest rung: Rung 0 existing-data read (RAN it: reward 0.5¢ vs hazard 2-6¢ = 4-13× underwater;
+7¢ round-trip signal is survivorship bias — 47% sold, held 53% won 37%); Rung 1 retrospective hazard via
prices-history (adverse_τ + picked_off_τ shark proxy over slow niches); Rung 2 forward /book poll (only if
1 survives). Zero Rust, zero migration, zero capital, first kill in ~1 hour.

## Reality-check (orchestrator, against LIVE API)
- CLAIM `/book` full depth → **CONFIRMED**: keys bids/asks each price+size (24 bids/219 asks on probe),
  plus tick_size/min_order_size/last_trade_price. ⇒ Designer A's Rust struct extension is UNNECESSARY for
  measurement.
- CLAIM `/prices-history` dense retroactive → **CONFIRMED**: 4,306 pts / ~30 days, 1-min.
- NUANCE vindicating A: `/book` carries only `last_trade_price` (one point), NOT the tape ⇒ fill-conditioned
  adverse selection (greenlight-grade) still needs the trade stream; Rung 1's mid-drift is kill-grade only.

## Synthesis decisions
- **Shape = Designer B's kill-cheapest-first Python ladder** (dominates on cost/reversibility; facts verified).
- **Rigor = Designer A grafted in:** Rung 1 labeled honestly as a hazard UPPER-bound proxy (mids can't
  detect fills); Rung 2 adds A's trade-tape co-poll + conservative fill model + null + gate.
- **Rust build (A) REJECTED for Stage-0**, retained as Stage-1+ upgrade only if a fast niche qualifies
  (a latency-tolerant precondition guarantees it won't). A's statistics kept.
- **Both agree:** reuse selection_null/surplus_bounds/superkey; self-tests mandatory; D23-style gate;
  legal-question gate; NULL = successful run.
- **Above all:** the DENSE_CAPTURE λ flip dominates the entire MM branch and is done first, independent of it.

## Key insight
The "market-maker's edge" these wallets have is invisible to a resolution-based pipeline BY CONSTRUCTION,
and — verified numerically — the reward (~0.5¢ spread) is 4-13× smaller than the hazard (~2-6¢ adverse
drift) on every niche we can see. The only escape hatch (an untracked slow niche) is closable with public
HTTP, no build. Expected end state: a fast, honest NULL for $0 — unless Tue can't legally deploy, in which
case even the measurement is moot past Rung 0.
