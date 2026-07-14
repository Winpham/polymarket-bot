# Autonomous Run: Capture Integrity — fix the biased/incomplete ask capture, then settle SPEED, SPREAD, and SIZE

> **Read this whole brief before touching anything.** You are an autonomous build worker on
> `~/polymarket-bot` (Rust + Python + SQL Polymarket consensus/copy‑trading **PAPER** system). The
> realizable‑price pipeline is **BROKEN IN A WAY THAT BIASES EVERY NUMBER WE COMPUTE**, and the project's
> live edge (`weather_fav`, and the champion `favorite`) rests on it. Your job: **make the executable‑price
> capture COMPLETE, UNBIASED, and FAST — in that order of importance — then re‑settle, on clean data, the
> three questions that actually decide whether this is bankable: SPEED, SPREAD, and SIZE.**
>
> **⚠️ The framing trap this run must NOT fall into:** "the capture is 20–30 min late, therefore make it
> faster" is the WRONG lead. Two independent runs measured `corr(lag, spread) ≈ +0.03` and drift ≈ 0 ⇒
> **latency is not what's costing us price.** The real damage is **STARVATION BIAS** (below). Build
> capture‑at‑detection because it fixes COVERAGE + BIAS (a measurement‑integrity fix), NOT because speed
> buys a better price. **But do NOT treat "speed doesn't matter" as settled either** — that finding was
> itself derived from the BIASED sample, so it must be re‑tested once capture is clean (§WS3).
>
> **Both "capture is now ~complete/unbiased and here is the clean SPEED/SPREAD/SIZE verdict" and "capture
> is fixed and the edge does NOT survive the true spread / is not fillable at size — here is the proof"
> are SUCCESS.** A goal‑sought green is failure. If the honest answer is "weather isn't bankable at size,"
> that is a money‑SAVING result — report it plainly.

---

## 0. READ FIRST — inherit the state, do not re‑derive it

- Memory: **`project-polymarket-capture-defects`** (D1–D4 — the defect class), `project-polymarket-weather`,
  `project-polymarket-discovery-negative` (a RETRACTED false negative caused by exactly this bias),
  `project-polymarket-cell-scan`, `project-polymarket-exec-policy`.
- **`STRATEGY-HANDOFF-favorite-consensus.md` §4** — already names capture‑at‑detection "the highest‑value
  change in the whole project." **`DATA-MODEL.md`** — `entry_ask` / `entry_ask_at` / `entry_ask_mid` semantics.
- Reports from prior runs: `WEATHER-{LATENCY,VERDICT}.json`, `WEATHER-DEEPEN-FINDINGS.md`,
  `EVERGREEN-PORTFOLIO-FINDINGS.md`, and the prereg ADDENDUM `PREREG_20260712T192000Z_weather_ADDENDUM.md`
  (B1 realizable basis · B2 spread must be measured ON the 0.71–0.90 band · B4 size floor).
- Code: `copy-trading-bot/src/cycles/housekeeping.rs` (the bounded ask‑capture backlog),
  `cycles/consensus_cycle.rs` (signal upsert = where at‑detection capture belongs),
  `cycles/live_tape.rs` + `clob_price_tape` (a continuous, resolution‑speed‑INDEPENDENT ask source),
  `ENTRY_ASK_MAX_PER_CYCLE` / `ENTRY_ASK_DECISION_MAX_PER_CYCLE` / `CAPTURE_ENTRY_ASK` in `config.rs`.
- DB: `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket -c "..."`.

**THE DEFECT, measured live (do not re‑derive — confirm and fix):**
- Ask coverage is only **45% (`favorite`) / 53% (`weather_fav`)**; median capture lag **21–33 min**.
- **STARVATION BIAS (the real disease):** coverage on **LOSERS = 71.2%** vs **WINNERS = 41.7%**. The
  ask‑capture walks a **bounded** backlog (`ENTRY_ASK_*_MAX_PER_CYCLE`), so **fast‑resolving markets
  (obvious chalk ⇒ winners) resolve BEFORE the queue reaches them** and never get an ask, while slow /
  contested (loss‑prone) markets stay open and get captured. Every "realizable" number computed on the
  captured subsample is therefore **pessimistically biased**, and it has ALREADY produced a false negative
  that had to be retracted.
- **`weather_fav_liq` has captured ZERO** — the $1k‑liquidity twin has never fired. **SIZE is UNPROVEN;
  weather may not be bankable at any meaningful size.** This is existential and unanswered.
- The defect CLASS (D1–D4): *bounded budget + bad ordering = starvation.* **AUDIT EVERY BOUNDED QUEUE.**

---

## 0.5. THE OBJECTIVE (optimize THIS — nothing else)

> **Make the executable‑ask capture (a) COMPLETE (coverage → ~100% of resolved signals), (b) UNBIASED
> (winner/loser coverage parity — the 71%/42% gap → ~0), and (c) FAST (at detection) — in that priority
> order. Then, on that clean basis, deliver the honest verdict on the three questions that decide
> bankability: does SPEED buy price? does the edge survive the TRUE SPREAD on the 0.71–0.90 certification
> band? and is it FILLABLE AT SIZE?**

- **Coverage + bias parity is the primary metric.** A faster capture that is still starved is a FAILURE.
  Report `ask_cov_pct` overall AND split by winner/loser — the gap is the headline number.
- **Never trade coverage for leakage.** The ask must be captured while the signal is OPEN and must never
  peek at post‑resolution information (the set‑once, `resolved=FALSE` discipline is load‑bearing).
- **SIZE is a first‑class deliverable, not a footnote.** A fat % on unfillable size is NOT a strategy.

---

## 1. Mission — five workstreams, each HARD‑STOP + commit + write findings so a reaped run is salvageable

### WS1 — Root‑cause the starvation (audit EVERY bounded queue)
Prove the mechanism rather than assume it. Instrument the ask‑capture path end‑to‑end:
- Why is coverage 45–53%? Decompose the misses: (a) resolved before the queue reached them (starvation),
  (b) empty/absent book, (c) per‑cycle budget exhausted, (d) ordering (does the backlog walk oldest‑first,
  so fast‑resolving fresh signals never get a turn?), (e) any silent drop/error path.
- Quantify the winner/loser coverage gap by time‑to‑resolution — the smoking gun is that coverage should
  fall off a cliff for markets that resolve inside the capture window.
- **Audit every OTHER bounded queue for the same defect class** (D1–D4 says this is a CLASS, not a
  one‑off): the resolver, dense capture, tape subscriptions, any `*_MAX_PER_CYCLE` budget. A bounded
  budget with a bad order silently starves a non‑random subset — find them all.
- Deliverable: `reports/CAPTURE-DEFECT-FORENSICS.json` + the mechanism, with the coverage‑vs‑resolution‑speed
  curve. **Commit.**

### WS2 — Build capture‑at‑detection (fixes coverage + bias + lag in ONE move)
Capture the executable ask **at signal‑fire time**, in the consensus cycle at upsert, not in the bounded
housekeeping backlog. Two sources — evaluate BOTH, prefer whichever is complete and cheap:
- the CLOB `/book` call already used (bounded, but at detection the population is small and fresh), and/or
- **`clob_price_tape`** (migration 040) — a continuous, 1 Hz, **resolution‑speed‑INDEPENDENT** feed that by
  construction cannot be starved by fast resolution. This may be the cleanest unbiased source; note its
  retention is short (`TAPE_RETENTION_HOURS`) so it must be read at/near fire time.
- Preserve leak‑freedom (set‑once, while OPEN). Add a distinct provenance column/flag so at‑detection
  captures are distinguishable from legacy lagged ones (never silently mix bases).
- Default‑OFF behind a flag, incumbents byte‑identical, `cargo test` + clippy green. Stage compose; do NOT
  flip the live flag (human's call).
- **Backfill is NOT possible for past signals — say so.** The clean basis accrues forward only.
- Deliverable: the arm/flag + a coverage/bias dashboard query. **Commit.**

### WS3 — Re‑settle SPEED on clean, unbiased data (do NOT trust the prior finding)
The prior "latency doesn't cost price" (`corr(lag,spread)≈+0.03`, drift≈0) was computed on the
**loser‑tilted captured sample** — it may be an artifact of the very bias we're fixing. Once at‑detection
capture accrues:
- Re‑measure, on the UNBIASED sample: does the ask at detection differ materially from the ask at +20–30
  min? Is there adverse drift for a follower? Is there a decay curve (reuse `latency_edge_curve.py`)?
- If speed genuinely doesn't buy price on clean data → **say so and stop optimizing it** (the win was
  coverage/bias, not speed). If it DOES → quantify the per‑minute cost and it becomes an executor requirement.
- Deliverable: `reports/CAPTURE-SPEED-VERDICT.json` — an honest, clean answer either way. **Commit.**

### WS4 — SPREAD and SIZE: the constraints that actually decide bankability
- **SPREAD on the certification band.** Prior spread figures (+1.65¢ / +1.87¢) come from few, deep‑chalk‑skewed
  captures. Per prereg ADDENDUM **B2**, measure the executable bid‑ask spread **ON the 0.71–0.90 band** with
  clean at‑detection asks, and recompute the realizable LB charging it. Does the edge survive its true cost?
- **SIZE — the existential question.** `weather_fav_liq` has captured **0**. Determine the actual fillable
  depth at the good ask on these books (from `clob_price_tape` top‑of‑book + any depth signal available;
  the tape stores top‑of‑book only, so state the limits of what can be inferred and do NOT fabricate depth).
  Per ADDENDUM **B4**: if the liq‑floor arm cannot accrue ≥20 resolved picks, weather reads **NOT BANKABLE
  at size** regardless of its percentage. Report deployable $/pick and the capacity ceiling honestly.
- Deliverable: `reports/SPREAD-AND-SIZE-VERDICT.json` + a plain‑English bankability read. **Commit.**

### WS5 — Reliability hardening: make capture regressions IMPOSSIBLE to miss
- A standing **coverage + bias monitor**: `ask_cov_pct` overall and split winner/loser, per strategy, with a
  regression alarm (the 71%/42% gap should have been caught the day it appeared, and wasn't).
- No silent drops: every capture miss is logged with its reason (the WS1 taxonomy).
- Add the coverage/parity invariants to the honest board/digest so a future run cannot unknowingly compute
  realizable numbers on a starved sample.
- Deliverable: the monitor + invariants. **Commit.**

---

## 2. Rigor & guardrails (LOAD‑BEARING)

- **Coverage/bias parity beats speed.** Judge every change by (coverage %, winner/loser gap) FIRST, latency
  second. A fast starved capture is still a corrupt basis.
- **Leak‑freedom is non‑negotiable.** Set‑once while OPEN; never read post‑resolution state. A leak turns a
  measurement fix into a fake edge — worse than the bias.
- **Never mix bases silently.** At‑detection vs legacy‑lagged asks are DIFFERENT populations: tag provenance
  and report them separately until the clean basis stands alone.
- **No backfill fiction.** Past signals cannot get an honest at‑detection ask. Say "the clean basis starts
  now" — do not reconstruct one.
- **The prior speed finding is SUSPECT, not settled** (measured on the biased sample). Re‑test; don't inherit.
- **Paper‑only; promotes nothing; arms nothing real.** New capture behind a default‑off flag; champion
  `favorite` + `weather_fav`/`weather_fav_liq` + `ConsensusParams::default` + all incumbents BYTE‑IDENTICAL.
- **No `.env` ARMING edits without a human.** Stage compose + prereg; flipping a live flag is Tue's call.
- **Cost‑zero / Max‑only:** never set `ANTHROPIC_API_KEY`, never spawn child `claude`. Python =
  numpy/pandas/psql/stdlib. DB read‑only except normal accrual writes; `clob_price_tape`/`trader_fills`
  SELECT‑only. Respect poller/CLOB rate limits — a capture fix that gets us 429'd is a regression.
- **No new migration** unless a genuine schema defect (a provenance column may legitimately be one) — if so,
  it is ADDITIVE + idempotent, and applied migrations are IMMUTABLE (never edit one).
- Work in an ISOLATED worktree off `main`; `cargo test --bin copy-trading-bot` + clippy green; every Python
  instrument `--selftest` green.

---

## 3. Build order (checkpoint + commit after EACH; a timed‑out run is "incomplete + resumable")

1. WS1 forensics + bounded‑queue audit → `CAPTURE-DEFECT-FORENSICS.json`. **Commit.**
2. WS2 capture‑at‑detection (default‑off, leak‑free, provenance‑tagged) + coverage dashboard. **Commit.**
3. WS5 coverage/bias monitor + invariants (land EARLY so the fix is verifiable). **Commit.**
4. WS3 clean SPEED re‑test once unbiased captures accrue → `CAPTURE-SPEED-VERDICT.json`. **Commit.**
5. WS4 SPREAD (on the 0.71–0.90 band) + SIZE → `SPREAD-AND-SIZE-VERDICT.json` + bankability read. **Commit.**

---

## 4. Completion criteria (honest definition of done)

Green = ALL of: (1) the starvation mechanism is PROVEN (not assumed) and every other bounded queue audited
for the same class; (2) capture‑at‑detection is built, leak‑free, default‑off, provenance‑tagged, with
coverage → ~100% and the winner/loser gap → ~0 on the new basis; (3) a standing monitor makes a future
capture regression impossible to miss; (4) SPEED is re‑settled on CLEAN data (either "not the lever —
stop optimizing it" or a quantified per‑minute cost); (5) SPREAD on the 0.71–0.90 band and SIZE are
measured, with an explicit **BANKABLE / NOT‑BANKABLE‑AT‑SIZE** verdict.

**Do NOT claim the edge is "real"/"bankable" because capture got faster.** Claim: what coverage and
winner/loser parity now are; whether speed buys price on clean data; what the true spread costs the edge on
the certification band; and whether it is fillable at size. **If the clean basis shows the edge is eaten by
the spread, or `weather_fav_liq` still cannot fill — say it plainly and recommend retiring it.** The value
of this run is a TRUSTWORTHY MEASUREMENT BASIS and an honest bankability verdict — not a faster number.
