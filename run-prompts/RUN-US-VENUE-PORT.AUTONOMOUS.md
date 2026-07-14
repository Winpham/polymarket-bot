# RUN — US VENUE PORT: does our edge survive on a book we can legally trade?

**Type:** long autonomous run. **Repo:** `~/polymarket-bot`. **Owner:** Tue.
**Status at handoff:** nothing built. This prompt is the whole brief.

---

## 0. THE ONE-PARAGRAPH TRUTH

We built a copy-trading edge on the **international** Polymarket book (`clob.polymarket.com`) by watching
specific Polygon wallets' fills. **A US person cannot trade that book** — it is a separate exchange with a
separate order book, separate collateral (crypto vs USD), and separate identifiers, and its ToS bars US
persons and VPN circumvention. **Polymarket US (`api.polymarket.us`, QCX LLC, a CFTC-regulated DCM/DCO) is
a DIFFERENT VENUE** — proven empirically: the same contract ("Athletics win the 2026 World Series") quotes
**0.001/0.002 international vs 0.0020/0.0030 US** at the same instant. Different BBO = different book.

**So the plan is NOT "port the bot."** The plan is: keep the international book as the **INFORMATION**
venue (reading public data is not trading), and make the US book the **EXECUTION** venue. The entire run
exists to answer one question, honestly, with a control and a significance test:

> **Does the international consensus signal still certify when priced at the US book, after the US fee, at
> the US book's real depth?**

If yes, we have a legal, fundable business. **If no, we say so and stop.** Both answers are wins; only a
fabricated yes is a loss.

---

## 1. WHAT IS ALREADY KNOWN (verified live 2026-07-13 — do not re-litigate, DO spot-check)

- **US venue:** QCX LLC d/b/a Polymarket US. CFTC **DCM + DCO**. Hosts: `api.polymarket.us` (authed
  trading), `gateway.polymarket.us` (public data), `wss://api.polymarket.us/v1/ws/{private,markets}`. Also
  FIX 4.x and gRPC. Docs: `docs.polymarket.us` (see its `llms.txt` index).
- **Fiat, not crypto.** USD collateral, ACH/card funding, fully collateralized ($1.00 margin per short).
  **No wallet, no chain, no EIP-712.** Auth is `keyId` + `secretKey` (HMAC-style), issued at
  `polymarket.us/developer` **after the iOS app + identity verification** (an invite code may be required).
  Rate limit **20 rps/key**. Official SDKs: **Python + TypeScript only** — *no Rust*.
- **⚠️ FEES EXIST AND ARE NEW TO EVERY BACKTEST WE HAVE RUN.** Taker `Fee = 0.06 × C × p × (1−p)`
  (effective 2026-07-01). At the favorite band that is **1.24¢/share at p=0.71, 0.77¢ at p=0.85, 0.29¢ at
  p=0.95.** **Maker rebate = −0.0125 ⇒ a maker is PAID.** *Verify both against `docs.polymarket.us/fees`
  and then against a real trade event — do not trust this file.*
- **⚠️ NO COPY SIGNAL EXISTS ON THE US VENUE.** `gateway.polymarket.us/v1/{trades,leaderboard,activity,
  positions}` all **404**. No wallets, no public trade tape, no third-party positions. **You cannot observe
  a sharp there.** The signal must come from the international book. This is the load-bearing asymmetry of
  the whole design.
- **Identifiers do not join.** US schema is `Category → Subcategory → Series → Event + Product →
  Instrument`, slugs like `tec-mlb-champ-2026-09-27-ath`, `atp-petmak-thiwil-2026-07-14`. **No
  `condition_id`, no `token_id`.** Our join keys map to nothing. **Building the mapper is the core new
  engineering problem.**
- **Coverage (from `gateway.polymarket.us/v1/sports`):** includes `fwc`, `cs2`, `lol`, `valorant`, `dota2`,
  `nfl`, `nba`, `atp`, `epl`, `ucl`, `f1`, `ufc`, `boxing`. Weather contract FAQs exist. Politics/crypto/
  culture "coming soon". **Our two live arms are `favorite` (sports) and `weather_fav` — verify BOTH
  families are actually listed and liquid, or the run dies at Phase A.**
- **The rs SDK is international-only** (`polymarket_client_sdk_v2` — zero occurrences of `polymarket.us`).
  Its `check_geoblock()` asks the *international* site. **Do not use it for the US venue.**
- **`EXECUTOR_FORGE_PLAN.md`** (in the repo root) is the execution-layer blueprint written for the
  international venue. **Its cage, state machine, per-arm policy layer, N_eff sizing, and demotion ladder
  are venue-agnostic and should be REUSED. Its CLOB client is not.**

---

## 2. HARD RULES

1. **NO GEOBLOCK EVASION. NO VPN. NO ToS CIRCUMVENTION.** We trade the US venue because we are allowed to.
   If any step requires pretending not to be a US person, **stop and report** — do not design around it.
2. **Reading is not trading.** Continuing to ingest the international public APIs for signal is fine and
   is the premise of the whole design. Do not place an order there.
3. **The evidence rule (binding, earned via 4 retractions, 2 of which reversed sign):** no claim ships
   without **(a) a control/placebo arm, (b) a significance test, (c) explicit n + dispersion.** A number
   without those is a HYPOTHESIS, not a result, and must never be the basis for risking money.
4. **No fill model. Ever.** A fill is an exchange fill event. (D31/G2: `last_size` is book churn, not a
   trade — a volume-based fill model is the exact bug that produced two false "+4.8%" results.)
5. **`merge to main == auto-deploy to prod`** (launchd autoupdater). Work on a branch. Every new path is
   **default-OFF**. Follow the established `live.rs` pattern: *flag off ⇒ task never spawned ⇒ binary
   byte-identical.*
6. **Paper first, always.** No real order is placed in this run. Real money is a separate, human-gated
   decision **after** Phase D returns a verdict.
7. **Report honestly.** A timed-out or partial run is **"incomplete + resumable"**, never "done."
   Green `cargo test` is the only definition of done for code.
8. Commit incrementally on the branch — a reaped long run must be salvageable from the worktree.

---

## 3. THE PHASES (dependency-ordered; each has a kill gate — DO NOT skip a rung)

### PHASE 0 — THE D4 RETROSPECTIVE (do this FIRST; it is cheap and it may change everything)
Tue's direct question: **"what did the D4 fix actually do for us?"** Answer it with data, not narrative.

- **First, establish whether it is even RUNNING.** `EXECUTION-READINESS.md` says the D4 fresh-first
  ask-capture fix (`e74f4e7`, branch `feat/evergreen-portfolio`) is **NOT DEPLOYED**, and
  `EXECUTOR_FORGE_PLAN.md` Item 1 says the at-fire capture flag (`CAPTURE_ENTRY_ASK_AT_FIRE`, mig 042 on
  `feat/paper-executor`) is **not armed**. **If both are off, the honest answer to Tue's question is "the
  fix has done NOTHING for us yet, because it never shipped" — say that plainly and immediately.**
- Then quantify, on whatever data exists: ask-capture **lag distribution** (p50/p90 — the pre-fix p50 was
  ~75 min; target < 5s), the **loser-tilt** (`entry_ask` vs decision-time price, by outcome — the defect
  was −1.04% vs +1.71%), and the **band composition** (the defect put 69% of weather asks in the dead
  ≥0.90 band). Before vs after, with n.
- **Then ARM THE CAPTURE (Phase 0 of `EXECUTOR_FORGE_PLAN.md`): mig 042 + `CAPTURE_ENTRY_ASK_AT_FIRE=1`,
  and fix the tape universe (`common/src/storage/consensus.rs:1629` — a literal `AND is_sports` predicate
  means the tape has ZERO weather rows, and the universe is derived from tracked traders' fills rather
  than from our own fired signals).** **BACKFILL IS IMPOSSIBLE. Every day this stays off is a day of
  realizable-edge truth that can never be recovered — and it is the ceiling on what could ever transfer to
  the US book.** Do this even if every other phase fails.
- **Also correct the fee model** (`EXECUTOR_FORGE_PLAN.md` Item 3): four documents disagree by ~5.5×, and
  the certification gate's pass/fail margin sits **inside** that error bar.

**KILL GATE 0:** none — this phase always ships. **Deliverable:** `reports/D4-RETROSPECTIVE.md` with an
honest verdict, and the capture flags **armed in prod**.

---

### PHASE A — SEE THE US MARKET (the observability spine)
Build the US-venue read-only data spine, mirroring what we have internationally. **Read-only. No auth
needed for `gateway.polymarket.us`.**

- Ingest US **markets**, **BBO**, and **book depth** on a poll (and the public WS `.../v1/ws/markets` if it
  works unauthenticated — verify). New migration + tables (`us_markets`, `us_book_tape`), numbered **after**
  the existing collisions (main ends at 040; `feat/exec-policy` has 041; `feat/paper-executor` has 042).
- **Measure the book, honestly:** depth at the touch, spread, and **how many levels are real** vs
  absurd resting offers. (A spot-check found a US book with 2 bid levels vs 15 ask levels and offers at
  0.2020/0.4800/0.9700 — *that is not a mature book.*) **Report the depth distribution with n.**
- Answer: **are our arms' families even tradeable here?** Sports favorites — yes, apparently. **Weather —
  VERIFY (our best arm, LODO-survives, null p=0.0005, is a weather arm). If weather is not listed or is
  not liquid, say so loudly — it changes which arm we are even porting.**

**KILL GATE A:** if the US book cannot support **$50 clips** in our arms' families at anything near the
prices we model, **the business is capacity-dead and the run stops here with an honest report.** Measure
this; do not assume it either way.

---

### PHASE B — THE MAPPER (international `condition_id` ↔ US instrument)
**The core new engineering problem.** No shared keys. Build a resolver:

- Match on **(entity set × event time × market type)** — e.g. intl `will-brazil-beat-croatia` +
  `2026-07-20T18:00Z` ↔ US `fwc-bra-cro-2026-07-20`. Normalize team/player names, resolve the outcome
  ORIENTATION (a YES on one venue must map to the correct side on the other — **an inverted mapping is a
  silent, catastrophic, money-losing bug**), and handle the neg-risk/multi-outcome shapes.
- **The mapper MUST be fail-closed and confidence-scored.** An unmapped or low-confidence market is
  **SKIPPED**, never guessed. Emit a coverage number: *what fraction of our fired signals map to a live,
  liquid US instrument?* That fraction is a hard multiplier on the whole business — **report it early.**
- **Test it adversarially:** deliberately try to make it produce an inverted or mismatched map. Every
  match needs an independent verification (e.g. resolution agreement on already-settled markets — if the
  two venues disagree on who won, the map is wrong).

**KILL GATE B:** if mapped coverage of our fired signals is **< 50%**, the turnover collapses and the
thesis is on life support. Report the number honestly before proceeding.

---

### PHASE C — THE BASIS STUDY (does the US price already know?)
For every mapped pair, measure the **basis** = `us_price − intl_price`, over time, around our signal fires.

- Is there a systematic **lead/lag**? Does the US book **follow** the international book (arbitrageurs
  linking them), or does it drift independently (dumber/thinner money)?
- **The key sub-question: at the moment our signal fires on the international book, what is the US ask?**
  If the US book has *already* moved, the edge is gone before we act. If it has *not*, we may have a
  **larger** edge there than internationally — which is exactly Tue's "even more favorable" case, and it
  would be the single best finding available in this run.
- **Control required:** a matched pool of *untraded* markets, so a claimed lead/lag is not just generic
  drift. **This is the exact trap that produced the RETRACTED latency finding** (a "15min = 8¢" claim that
  collapsed to +2.05¢ ± 4.0¢, **p = 0.36**, when a placebo arm was finally added — and the placebo median
  drifted MORE). **Do not repeat it.**

---

### PHASE D — THE DECISIVE GATE: does the edge certify AT THE US PRICE?
Re-run the **frozen certification gate** — unchanged, no new knobs — but with the basis swapped:

- **Basis = the US executable ask** (the price *we* pay on the venue we can legally trade), **not** the
  international ask, **not** mid, **never** the sharps' fill.
- **Charge the real US taker fee** (`0.06·p·(1−p)`) — **and separately evaluate a maker/post-only leg,
  which earns the −0.0125 REBATE.** *Note: our single most robust finding across the entire project is
  that **the edge is in the FILL, not the pick** (a fire-time taker pays ~3.4¢ over mid and the whole edge
  is 3–7¢ wide). **A venue that PAYS you to make could be structurally better for us than the one we
  measured on.** Test this properly — it is the most valuable hypothesis in the run.*
- Gate floors are **frozen and unchanged**: ≥20 resolution-DAY clusters, ≥2 disjoint weeks, **LODO-by-week
  survives**, belief-blind `selection_null` **p ≤ 0.01** (≥1000 matched permutations), certification band
  **0.71–0.90**, champion floor **+5.6%**, |day-corr with champion| < 0.3.
- **Pre-register the gate BEFORE you look at the answer.** Write the prereg file, commit it, *then* run.

**KILL GATE D — and mean it:** if the signal does **not** certify at the US price after the US fee, the
answer is **"the edge does not transfer — retire the thesis,"** NOT "re-analyse until it does." *This
project has re-analysed four times and reversed sign twice.* **Be willing to hear NO.**

---

### PHASE E — THE EXECUTION LAYER (only if D passes)
Reuse `EXECUTOR_FORGE_PLAN.md` wholesale, swapping only the venue leg:

- **The cage is venue-agnostic — REUSE IT:** the order state machine (`INTENT → SENT → ACKED →
  FILLED|PARTIAL|CANCELLED|REJECTED|ORPHANED`), the crash-mid-send and cancel-race boundaries, the
  **persistent per-arm kill-switch**, the per-arm policy layer, **N_eff correlated sizing ("size the GAME"
  — 17 positions on one World Cup game resolve together)**, the demotion ladder, and invariants I1–I10 with
  their tests (crash-mid-send recovery, cancel-race, wedged-loop kill).
- **What changes:** a **new US client** (REST/WS, `keyId`+`secretKey` HMAC — **no Rust SDK exists, so this
  is a real build**; consider whether the Python/TS SDK behind a thin sidecar is honestly cheaper than a
  hand-rolled Rust client, and *justify the choice in writing*), a US-native idempotency story (**find out
  whether the US API supports a client order id — the international V2 API does NOT, and its absence
  reshaped the entire international design**), and US-native `min_order_size` / `tick_size` / margin rules.
- **Default posture is maker/post-only** given the rebate — **but only if Phase D's maker leg actually
  measured a fill rate.** *Adverse selection is the named enemy: a resting bid fills only when the price
  comes back to you ⇒ you catch reverters and miss winners (`wr_filled` 62–65% vs `wr_missed` → ~100% on
  long cancels).* **Never ship a fill rate you did not observe.**
- **Per-arm nuance is mandatory** (Tue's standing requirement — no global setting): weather (price barely
  moves, the BOOK binds, patient rest ~free), sports favorites (the ask drifts toward 1.0 *as the match
  runs* ⇒ a patient rest is adversely selected **by the clock**), router (edge is FRONT-LOADED — only
  28–36% of signals ever retrace ⇒ resting **structurally misses winners**).

---

## 4. DELIVERABLES

1. `reports/D4-RETROSPECTIVE.md` — what the D4 fix did (honestly: possibly "nothing, it never shipped"),
   and the capture flags **armed in prod**.
2. `reports/US-VENUE-MAP.md` — the US book's real depth/spread/coverage, with n and dispersion; which of
   our arms' families are actually tradeable.
3. The **mapper**, with its adversarial tests and an honest **coverage %** of our fired signals.
4. `reports/US-BASIS-STUDY.md` — lead/lag vs a matched placebo, with a significance test.
5. **`reports/US-CERTIFICATION.md`** — the frozen gate re-run at the US ask with the US fee, taker **and**
   maker legs. **The verdict, whatever it is.** Plus its prereg, committed *before* the result.
6. If (and only if) D passes: the Phase-E build, on a branch, **default-OFF**, `cargo test` green.
7. `DECISIONS.md` entry recording the verdict and the reasoning — including a **NO**.

## 5. WHAT NEEDS TUE (do not block the run on these; surface them)

- **A Polymarket US account + API key** (iOS app → identity verification → `polymarket.us/developer`; an
  invite code may be needed). **Phases 0/A/B/C/D need NONE of this** — `gateway.polymarket.us` is public
  and everything up to the verdict is read-only. **Only Phase E and any real order need the key.**
- **The funding decision** — after Phase D's verdict, not before. And per the international blueprint: the
  first real money is a **$1–5 plumbing order to read the actual fee off a trade event**, not a $50 pilot.
- **Confirm the US venue's fee schedule and maker rebate from inside the account** — the run's numbers are
  from public docs and must be verified against a real trade event before anything is sized on them.

## 6. THE HONEST FRAME (hold this the whole run)

Tue's instinct — *"we'll only trade where the edge is favorable; if it's worse in the US we don't do it,
if it's better we do; technically a win"* — is right **only if the signal transfers at all**. The selection
rule needs a signal to select on, and **the signal does not exist on the US venue**; it exists only on the
international one. So this run is not "port the bot." **It is one question: does an international signal
survive being priced on a US book?** Phase D answers it. Everything before Phase D exists to make that
answer trustworthy, and everything after exists only if the answer is yes.

**A NO here is a good outcome delivered cheaply. A fabricated YES is the only real failure.**
