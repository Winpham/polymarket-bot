# Autonomous run — "Option B: turn on the truth" — deploy dense capture + winners-alert, then run the forward λ-measurement loop to a real go/no-go

> **How to run.** Paste this whole file as the task for a fresh Claude Code session opened in
> `~/polymarket-bot`, or dispatch it:
> `claude -p "$(cat ~/polymarket-bot/OPTION-B-FORWARD-CAPTURE-PROMPT.md)"`
> This is a **long, self-directed, partly-recurring** run: the first pass deploys-and-verifies the
> switch and takes the first readings; then it re-runs the forward loop on a cadence (re-dispatch it,
> or wrap it in `/loop`/`/schedule`) across the ~2–4 week accrual window. Work autonomously to
> finished, gate-green, merged deliverables. **Stop only for the decisions that are genuinely Tue's**
> (below). Everything else — verify, monitor, report, prepare — you do without asking.
> Companion reading (ground truth + house style): `DECISIONS.md` (D22, D25 — and D23/D24 from the
> parallel softness/specialist runs), `REFINED-STRATEGY.md`, and the instruments this loop drives:
> `scripts/{clv_monitor,readiness_ledger,clv_lambda,copyability,softness_fade,persistence_tracker,
> alert_leak_shadow}.py`.

---

## 0. The mission (read twice)

Every profit number this project has produced is conditional on **λ** — how much of the +11pt favorite
edge is real *information* versus favorite-longshot *bias* — and today λ is **un-measurable**, because
the CLV recorder (`signal_price_trajectory`, migration 034) has never run: `DENSE_CAPTURE` is default
OFF. The D25 readiness ledger states the honest distance to real money as **2/4 GO gates met, binding
constraint = persistence (months), real-money-eligible = FALSE**, and it names the **one lever that
unblocks progress: turn on dense capture** so λ becomes measurable at all. In the same breath, the
+EV winners (`favorite`/`elite_fresh_fav`) have fired **334 signals / 0 alerts** while the only
surfaced stream is `strict` (which contains the reliably-losing DODGE residue) — a **≈+$2,122 realized
leak** (D22/WS-C) that costs nothing to stop.

**Option B is the single deploy that fixes both** — `DENSE_CAPTURE=true` +
`CONSENSUS_ALERT_STRATEGIES=strict,favorite,elite_fresh_fav` +
`CONSENSUS_ALERT_WATCH_FOR=favorite,elite_fresh_fav` in `.env.consensus`, shipped via
`scripts/consensus-autoupdate.sh`. **This run's job is to make that switch real and then run the
forward loop that turns the accruing data into TRUTH**: measure λ for real, watch persistence accrue,
watch the fade-thesis lead (D25/WS-4) either firm up or evaporate post-tournament, keep the alert
volume sane, and escalate the one decision that data unlocks — arm a tiny de-levered pilot, or pivot —
to Tue. **No real money is placed by this run. No new modeling is built. The point is to buy TRUTH by
capturing it, not to invent more of it.**

> **One sentence:** flip the switch that starts real CLV/λ measurement and stops the free alert leak,
> then run the forward loop to the honest moment where the data says GO-a-pilot, PIVOT, or KEEP-WAITING
> — and stop there for Tue.

**The motto:** *we have modeled the edge to death; now capture the truth and let the data decide.*

---

## The two decisions that are Tue's — STOP for each, never auto-execute

1. **The deploy itself is Tue's DIRECT hand.** Flipping `favorite`/`elite_fresh_fav` alerts live sends
   real pushes to Tue's phone and changes which signal he acts on; the auto-mode safety guard reserves
   the `.env.consensus` write for Tue to run himself. **You do NOT write `.env.consensus` or run the
   deploy in auto mode.** You either (a) verify it if Tue has already run it, or (b) emit the exact
   commands and STOP for Tue to paste (via the `!` prefix or outside auto mode). See Phase 0.
2. **Committing real money to the pilot is Tue's.** Even when every gate clears, arming the pilot
   (`PILOT_ARMED=1` + master switch) is Tue's call. You prepare and escalate; you never arm.

Everything else — verifying the deploy, running the instruments, monitoring health, reporting,
updating the ledger — you do autonomously.

---

## Ground truth you must NOT relitigate (build ON these; evidence in DECISIONS.md)

- **λ is INDETERMINATE-BY-DATA, and the proxy points LOW** (D22/WS-A): trajectory globally empty; the
  `mean_price` proxy gives λ̂≈0.15 (CLV-explained ~15% of surplus), **below** the λ=0.25 profitability
  floor (D21). Do NOT re-derive the proxy; the whole point of Option B is to replace it with a real
  measurement. The instrument (`clv_lambda.py`) **auto-switches proxy→trajectory** the moment coverage
  exists — you don't rebuild it, you feed it data.
- **The de-lever fraction is PINNED at ⅟₁₂-Kelly** (D22/WS-B; ⅟₁₆ conservative, flat floor). Don't
  re-open sizing (settled D20/D21/D22).
- **Copyability is NOT the binding constraint for favorites** (D25/WS-3): ~69% survives to a fillable
  price. The killers are edge-reality (λ) and persistence.
- **The realer thesis is a LEAD, not an edge** (D25/WS-4): fading overhyped favorites
  (`soccer/directional/band5`, +8.2% net, one FDR cell, WC-heavy) is the strongest exploitable signal
  and the *opposite* of copy-tailing — but it needs to persist post-tournament. The parallel D23/D24
  runs both landed NULL/INDETERMINATE-by-power on the same accrual wall. Treat FADE as a
  pre-registered forward watch-list; do NOT bet it.
- **The binding constraint everywhere is ACCRUAL, not analysis** (D25 meta-finding). This run's value
  is *capturing* data and *reading* it honestly over weeks — not producing another instrument.
- **The bot is PAPER-ONLY** — there is no order-placement path. Dense capture writes trajectory rows;
  it places nothing. The alert flip pushes notifications; it places nothing.

## Non-negotiable guardrails

1. **Paper/measurement-only. No real money, no order placement, no arming.** The only live change is
   the Tue-run deploy (dense capture + alerts). Nothing you do bets.
2. **You never write `.env.consensus` or run the deploy in auto mode** (guardrail-blocked; Tue's
   direct hand). You verify, or you hand off exact commands and STOP.
3. **Deploys ONLY via `scripts/consensus-autoupdate.sh`** (never manual `docker compose up`). Confirm
   the autoupdater log line after any deploy; a doc/script-only change must show "skipped rebuild."
4. **Reversibility.** A backup of `.env.consensus` is made before any edit (Tue makes it, or you
   instruct it). Rollback = restore the backup (or set `DENSE_CAPTURE=false`,
   `CONSENSUS_ALERT_STRATEGIES=`) and re-run the autoupdater. If capture or alerting misbehaves
   (spam, crash-loop, wedged daemon), **roll back first, diagnose second.**
5. **Gate every code/script commit:** `python3 -m py_compile` + the instrument's `--selftest`; for any
   Rust, `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy
   --workspace --all-targets && cargo test --workspace`. Re-run the FULL gate on `main` AFTER you land
   (main moves under you — other chats).
6. **Multi-chat coordination.** Other Claude sessions run in parallel (the D23/D24 softness/specialist
   runs collided with D25 once already). Before building anything: `git worktree list`, keep your file
   slice non-overlapping, rename rather than clobber, say so in the entry. This run should need almost
   NO new building — prefer running the existing instruments over writing new ones.
7. **Minimal-noise reporting.** Report only material changes (a gate flip, a health failure, a
   threshold breach, the go/no-go moment). Silence between readings is correct; a daily one-line digest
   is enough. Never push a "still accruing, nothing changed" alarm.
8. **Cost-zero** (Max only; no `ANTHROPIC_API_KEY`; no child `claude` spawns). **DB read-only** via
   `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket --csv -q`.

---

## Pre-registration (freeze these thresholds BEFORE reading any accruing data)

- **Deploy-healthy ⇔ ALL of:** container `Up`, no crash-loop (restart count stable over 10 min),
  trajectory rows **climbing** (`select count(*) from signal_price_trajectory` increases across two
  readings ≥1 dense interval apart), winners **alerting** (a resolved-or-live `favorite`/`elite`
  signal produced a `consensus_alerts` row post-deploy), and alert **volume sane** (total alerts/day
  ≤ ~2.5× the pre-deploy `strict`/day baseline — D22 predicted 2.23×; a blow-up ⇒ K-SPAM).
- **CLV coverage floor (K1):** the real λ read is trustworthy only at trajectory **coverage ≥ 50%** of
  resolved favorites (`clv_monitor.py` state MEASURED). Below that it stays a proxy — report ACCRUING,
  do not quote a λ.
- **λ floor (the edge-reality gate):** MEASURED **and** `λ̂` CI lower bound **> 0.25** ⇒ CLEARS
  (edge-reality gate met); MEASURED and CI_lo ≤ 0.25 ⇒ BELOW (the edge is bias, not information → the
  PIVOT signal). Frozen in `clv_monitor.py`; do not move it.
- **Persistence bar (the binding gate, D18/D7):** ≥5 **independent, NON-EXPIRING** regimes with
  positive surplus, accrued over **months** — NOT more World-Cup weekends. `persistence_tracker.py` +
  the ledger track it; it will read NOT_MET for a long time. That is honest, not failure.
- **Degenerate-price guard (K3):** the CLV close must never be the post-resolution 0/1 print
  (`clv_lambda.py` excludes mid ∉ [0.02,0.98]). Spot-check that early trajectory reads aren't
  contaminated (a favorite "closing" at 0.99 the instant before resolution is hindsight, not CLV).
- **Kill criteria (report honestly; a negative IS the deliverable):**
  - **K-SPAM** alert volume > ~2.5× baseline, or the same market re-alerting past the 60-min
    cross-dedup ⇒ propose a rate-limit and recommend Tue revert the alert half (keep dense capture).
  - **K-CAPTURE** trajectory stops growing / dense loop logs errors ⇒ capture is broken; roll back
    `DENSE_CAPTURE`, file the failure; λ stays a proxy.
  - **K-BELOW** once MEASURED, if λ̂ CI_lo stays ≤ 0.25 across the window ⇒ the edge is bias; this is a
    genuine result — escalate the PIVOT (fade thesis / stop pouring into copy-tailing), do not launder.
  - **K-FADE-DIES** the D25 fade lead (`soccer/dir/band5`) fails to persist on post-WC data ⇒ say so;
    it was WC over-hype, not structural.

---

## Phases

### Phase 0 — Deploy the switch (Tue's hand) & VERIFY (yours). ~30 min active, then watch.
1. **Read current state** (no writes): running-container env for `DENSE_CAPTURE`,
   `CONSENSUS_ALERT_STRATEGIES`, `CONSENSUS_ALERT_WATCH_FOR`; `select count(*) from
   signal_price_trajectory`; recent `consensus_alerts` by strategy.
2. **If NOT deployed:** emit the exact, copy-paste commands and **STOP for Tue** —
   ```
   cp ~/polymarket-bot/.env.consensus ~/polymarket-bot/.env.consensus.bak-$(date +%Y%m%d)
   printf '\nDENSE_CAPTURE=true\nCONSENSUS_ALERT_STRATEGIES=strict,favorite,elite_fresh_fav\nCONSENSUS_ALERT_WATCH_FOR=favorite,elite_fresh_fav\n' >> ~/polymarket-bot/.env.consensus
   cd ~/polymarket-bot && bash scripts/consensus-autoupdate.sh
   ```
   (In an interactive session, tell Tue to run these with the `!` prefix so they execute in his
   context.) Do not proceed to the loop until they're applied.
3. **If deployed (or once Tue confirms):** VERIFY against the Phase-0 pre-registration — container
   healthy, trajectory rows climbing over one dense interval, winners alerting, volume sane, no
   degenerate-price contamination. If any check fails → **roll back and diagnose** (K-CAPTURE/K-SPAM).
   Record the first clean reading. **No commit needed for verification; note the autoupdater log line.**

### Phase 1 — First real CLV read & baselines.
Run `clv_monitor.py` (state should move EMPTY→ACCRUING once rows exist), `readiness_ledger.py` (the
`operational` gate should flip NOT_MET→MET), `alert_leak_shadow.py` (confirm the leak is now being
captured — winners alerting). Record the accrual-log entry. Report the one material change: "dense
capture live, λ now measurable, alert leak closed." Baseline the alert volume/day and the ask-coverage
climb (`copyability.py` — decision-time ask coverage should start rising off n=5).

### Phase 2 — The forward measurement loop (the long part; re-run on a cadence over ~2–4 wk).
On each pass (daily digest / weekly deep read), re-run and append to the logs:
- `clv_monitor.py` — coverage %, λ̂ trend, state, floor verdict. **The headline number.**
- `readiness_ledger.py` — which gates flipped; the binding constraint; distance to money.
- `persistence_tracker.py` — out-of-sample clusters; are NON-EXPIRING regimes accruing (post-WC/
  Wimbledon → MLB and beyond)?
- `softness_fade.py` **and** the D24 `softness_map.py` — does the FADE lead (and D24's soft pockets)
  persist as the blind universe grows, or was it WC over-hype (K-FADE-DIES)?
- `copyability.py` — is the DIRECT @ask read climbing out of INDETERMINATE as decision-time asks
  accrue (favorite n was 5)?
Report **only** material changes (minimal-noise). Keep the do-not-bet guardrail standing throughout.

### Phase 3 — Health & guardrail watch (every pass).
Alert volume vs baseline (K-SPAM); dense-capture liveness (K-CAPTURE); degenerate-price contamination
(K3); cost/haircut drift (`copyability` spread by band). Any breach ⇒ roll back the offending half,
report, do not silently continue.

### Phase 4 — The go/no-go escalation (STOP for Tue).
When the ledger's gates move, escalate the decision the data unlocks:
- **GO-PILOT path:** `clv_monitor` MEASURED/CLEARS (λ̂ CI_lo > 0.25) **AND** persistence ≥5
  non-expiring regimes **AND** sizing/power/copyability hold ⇒ present the readiness board + the
  unarmed-pilot go-conditions and **STOP for Tue's real-money decision.** Never arm.
- **PIVOT path:** MEASURED/BELOW (K-BELOW) ⇒ the copy-consensus edge is confirmed bias; present the
  fade-thesis evidence (if it survived Phase 2) and recommend redirecting effort — **STOP for Tue's
  strategic call.**
- **KEEP-WAITING:** neither triggered ⇒ the honest state; keep the loop running, report the distance.

### Phase 5 — Synthesis (only when a phase-4 trigger fires, or at run end).
`DECISIONS.md += D26` (the measured λ̂ with its real CI, the persistence state, the fade-thesis verdict,
the alert-leak outcome, and which of GO/PIVOT/WAIT the data reached). Update `REFINED-STRATEGY.md` and
the memory topic. Merge `--no-ff`; re-gate post-merge main; confirm the autoupdater "skipped rebuild"
for the doc/script parts. Final report to Tue: the real λ̂, the distance to money, and the one decision
awaiting his yes/no.

---

## Rejected approaches (do not build)

- **Writing `.env.consensus` or deploying in auto mode** — Tue's direct hand (guard-blocked). Verify or
  hand off.
- **Placing real money / arming the pilot** — Tue's decision; the run prepares and stops.
- **Building a NEW instrument** — the measurement apparatus already exists (D22/D25). This run *runs*
  it over accruing data; it does not re-invent it. If a genuine gap appears, coordinate (worktree +
  claim) and prefer the smallest additive change.
- **Quoting a λ before coverage ≥ 50%** — that's the proxy, not a measurement. Report ACCRUING.
- **Re-deriving sizing / the game cap / a second strategy** — settled / supply-limited (D15–D22).
- **Betting the fade lead** — one WC-heavy FDR cell; it's a forward watch-list item until it persists.

## Acceptance

Dense capture verified live and writing trajectory (coverage climbing); the alert leak closed and
volume sane (no K-SPAM); `clv_monitor.py` advancing EMPTY→ACCRUING→(eventually)MEASURED with an
honest floor verdict; `readiness_ledger.py` re-read each pass with the binding constraint named; the
fade lead and persistence tracked forward; kill criteria honored (a negative reported, not laundered);
and — when the data reaches it — the GO-PILOT / PIVOT / KEEP-WAITING moment escalated to Tue with the
board and the one decision awaiting his yes/no. **Live behavior changed only by the Tue-run deploy;
nothing armed; no real money.** The output is **the edge turned from an assumption into a MEASUREMENT
as the data accrues, the free realized-P&L leak stopped, and the honest go/no-go delivered to Tue on
real evidence instead of a proxy.**
