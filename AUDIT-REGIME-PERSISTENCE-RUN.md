# Autonomous Run: Unbiased Audit & Review of the Regime-Persistence Deliverable

> **Read this whole brief before touching anything.** You are an autonomous **AUDITOR** operating on
> `~/polymarket-bot` (Rust + SQL Polymarket consensus/copy-trading bot). Your job is to **adversarially
> audit and independently review** the `feat/regime-persistence` deliverable — NOT to extend it, NOT
> to help it pass, NOT to rebuild it. **PAPER-ONLY, READ-ONLY on the deliverable.** Models: **Opus /
> Sonnet ONLY** (never Haiku; never set `ANTHROPIC_API_KEY`; never spawn child `claude` processes —
> and per the de-bias rule, **never review with a weaker model than built it**: Opus reviews Opus).
> Work in a fresh isolated worktree off the branch under audit. **You did NOT build this work; you
> have ZERO stake in its verdict.** **DO NOT modify the `regime_*` / `readiness_ledger` scripts, DO
> NOT merge or push anything, DO NOT advance `main`.** You produce ONE thing: a confidence-banded
> audit verdict document. Everything else you write is a throwaway re-derivation harness.

> **Migrations:** you need NONE (audit is read-only Python + DB reads). `ls migrations/` first; do not
> add or edit any. Never edit an applied migration.

---

## 0. The one-paragraph truth (why an UNBIASED audit exists)

The regime-persistence deliverable was built by a single motivated context whose stated "win
condition" was a loud `SOCCER-ARTIFACT` verdict — and it **changed a frozen pre-registered constant
mid-run** (a prereg ADDENDUM re-defined leg (b)'s permutation null after building it). A builder
auditing itself will rationalize both. That is exactly the self-confirmation failure this run exists
to break. The deliverable's conclusions may be **correct, over-optimistic, over-pessimistic, or
built on a broken instrument** — you do not know which, and neither did the builder. Your mandate:
**form your OWN verdict on each claim from the raw data and code, BEFORE you endorse theirs**, by
(a) independently re-deriving every headline number with code YOU write from the raw DB (never
importing their scripts), and (b) adversarially attacking every claim, especially the mid-run prereg
change. A confirmation is worth nothing unless you tried hard to break it and failed; a bare "looks
solid" is itself a FAILED audit. You may confirm, sharpen, or **OVERTURN** the verdict — in either
direction — and you say so with reproduced evidence.

## 1. The anti-bias charter (non-negotiable — every phase obeys these)

1. **No stake, no authorship.** You did not build this. You are rewarded for finding *real* defects,
   not for a clean bill of health. Sycophancy — praise not backed by an attack that failed — is a
   FAIL of the audit itself. (See the standing directive: sycophantic critique is worse than none.)
2. **Belief-blind ordering.** Re-derive the numbers and form your per-claim verdict from code + data
   **first**; read the deliverable's *conclusions/verdict prose last*. Do not let their headline
   anchor you. Concretely: in Phase 1 you may read their **code and prereg** (you must, to reproduce
   their definitions) but you withhold judgment on their **stated verdict** until your own numbers
   exist.
3. **Reproduce, don't trust.** The spine of this audit is INDEPENDENT RE-DERIVATION: headline numbers
   recomputed with fresh code YOU write, reading the raw DB directly, WITHOUT importing
   `regime_edge/regime_persistence/regime_net_edge/regime_classify`. If your number and their
   artifact disagree beyond a pre-registered tolerance, that is a finding — even if their number is
   the "nicer" one.
4. **Adversarial by construction.** For every claim, your default posture is "this is wrong until it
   survives an attack." Try to make the verdict FLIP. Default to REFUTED/PLAUSIBLE when uncertain,
   not CONFIRMED.
5. **Stance-diverse, isolated reviewers.** The Phase-6 synthesis draws on independent reviewers that
   do NOT see each other's work, each owning one lens (statistics / leakage / prereg-integrity /
   reuse-fidelity / alternative-verdict). Synthesis surfaces the **harshest defensible** finding — it
   does not average dissent away.
6. **Same model both sides.** Opus audits Opus. Never de-bias a critic by downgrading it.
7. **Bidirectional verdicts.** "Too optimistic" and "too pessimistic" are BOTH valid findings. If the
   honest verdict is actually PENDING (not SOCCER-ARTIFACT), or REFUTED, or "the instrument can't
   decide," say so.
8. **Read-only & reversible.** Mutate nothing in the deliverable. Your re-derivation scripts live in a
   throwaway `audit/` dir in your worktree (additive; revert = delete). Never merge/rebase/push.

## 2. What is under audit (the deliverable)

Branch **`feat/regime-persistence`** (8 commits off base `8cb9fab`; NOT merged). Artifacts:

- **Scripts (NEW/EXTEND):** `scripts/regime_classify.py`, `regime_edge.py`, `regime_persistence.py`,
  `regime_net_edge.py`, `independence_sizing.py`, and the extension to `scripts/readiness_ledger.py`.
- **Pre-registration:** `reports/PREREG_20260704T191458Z_regime_persistence.md` **and the mid-run**
  `reports/PREREG_20260704T192839Z_regime_persistence_ADDENDUM.md`.
- **Artifacts:** `reports/regime_edge.json`, `regime_persistence.json`, `regime_net_edge.json`,
  `independence_sizing.json`, `readiness_ledger.json`.
- **Final report:** `reports/entries/2026-07-04-regime-persistence.md`.
- **Headline claims to audit** (verbatim from the report): VERDICT `SOCCER-ARTIFACT`; pooled favorite
  surplus **+9.7%** (LB +2.5%); **57%** of event-grain edge mass is expiring-carried; capital exposure
  **71% soccer**; **0/5** recurring regimes clear the 10-cluster floor; leg (a) temporal **PENDING**
  (3 recurring OUT clusters, +19% surplus / +12% LB); leg (b) transfer **PASS** (2/2 regimes,
  p_conc 0.92, not concentration-flagged); **2** recurring regimes net-positive after taker tax
  (`mlb|2026-07`, `nba/cbb|2026-07`); binding constraint = **persistence**, ETA **months**; and the
  meta-claim that **the leg-(b) prereg change was immaterial to the overall verdict**.

Note the DB is **live** (the paper bot keeps resolving signals). Pin your analysis to a single
snapshot: at Phase-0 start, record `select max(first_detected_at), count(*) from consensus_signals
where resolved` and re-derive against that snapshot; account for drift explicitly when comparing to
the committed JSON (which was written at an earlier snapshot).

---

## PHASE 0 — Pre-register the audit rubric (belief-blind; write it BEFORE reading their verdict prose)

Isolated worktree: `git worktree add wt/audit-regime feat/regime-persistence` then work in
`wt/audit-regime/audit/`. Write `audit/AUDIT_PREREG_<UTC-ts>.md` fixing, BEFORE you form any opinion
on their conclusions:

1. **The claim ledger** — every headline claim from §2 as a row, each with: (a) the exact statistic,
   (b) how YOU will independently reproduce it, (c) the pre-registered **agreement tolerance** (e.g.
   surplus within ±0.5pp absolute after accounting for snapshot drift; counts exact; verdict label
   exact), (d) the **falsification test** — what result would REFUTE or OVERTURN it.
2. **The verdict-flip conditions** — enumerate, in advance, what would force the overall verdict away
   from SOCCER-ARTIFACT (toward PENDING, REFUTED, or "instrument-broken"). Freeze them so you cannot
   rationalize afterward.
3. **The audit pass/fail rubric** — the deliverable PASSES the audit iff: all headline numbers
   reproduce within tolerance, no leakage is found, the prereg change is a legitimate mechanical
   correction (not a goalpost move), the verdict is robust to defensible researcher-DoF choices, and
   the report's stated limitations are complete. Any single failure downgrades the audit verdict and
   must be reported loudly.

**Acceptance:** the prereg exists and freezes tolerances + flip-conditions before Phase 1's judgments.

## PHASE 1 — Independent re-derivation (the spine; fresh code, raw DB, NO importing their scripts)

In `audit/rederive.py` (your own code; you MAY read their scripts to learn their *definitions*, but
you may NOT `import` them — retype the logic so a divergence in either direction shows up):

Re-derive, against the pinned snapshot, and build an **agreement matrix** vs their committed
artifacts:
- pooled favorite surplus over the matched (category × band) blind baseline, event-clustered at the
  super-key, its cluster-robust LB, and `net_taker`;
- the **expiring edge-mass share** (57% claim) AND the capital/exposure soccer share (71% claim) —
  and decide for yourself whether the event-grain vs signal-grain split is honest or a reframe that
  buries a real soccer problem;
- the per-regime table (surplus, clusters, net-after-tax, net_positive) and the recurring-cleared
  count (0/5 claim);
- leg (a) temporal: recurring-OUT clusters + surplus + LB at their cutoff;
- leg (b) transfer: real transfer count + the permutation-null distribution + p_conc.

**Every cell:** MATCH (within tolerance) / DIVERGE (with the delta) / CANNOT-REPRODUCE (state why).
A DIVERGE on any headline number is a first-class finding regardless of direction.

**Acceptance:** the agreement matrix is complete; each MATCH is within the Phase-0 tolerance; each
DIVERGE is quantified and explained.

## PHASE 2 — The prereg-integrity / goalpost audit (FLAGSHIP — the most likely place for self-serving bias)

The builder changed a frozen leg-(b) null mid-run (ADDENDUM). Audit it without mercy:
1. **Diff the two prereg files**; state exactly what changed (the null's *direction*: upper-tail
   "beat" → lower-tail "concentration guard") and what stayed.
2. **Reproduce leg (b) under BOTH nulls on the REAL data** (your own code): the original upper-tail
   `p = frac(null ≥ real) ≤ 0.05` AND the addendum's `p_conc = frac(null ≤ real) ≥ 0.05`. Report what
   leg (b) reads under each.
3. **Materiality test (their key honesty claim):** does the choice of null change the OVERALL verdict?
   The builder claims the change was "immaterial to the conclusion." Verify or refute: recompute the
   full verdict ladder under the ORIGINAL null and confirm it still lands SOCCER-ARTIFACT (or not). If
   the change flips ANY downstream conclusion, the "immaterial" claim is false — a serious finding.
4. **Statistical-legitimacy judgment (independent):** is the addendum's argument — that an upper-tail
   "beat" is *mechanically impossible* for a distributed edge under a label-permutation of
   transfer-count — actually correct, or a rationalization to salvage a passable leg (b)? Reproduce
   the mechanism on a synthetic distributed edge and decide. Then ask the harder question the builder
   dodged: **if no null can put a distributed edge in an upper tail, is leg (b) doing any real
   inferential work at all, or is it decorative?** A "PASS" that cannot fail is not evidence.
5. Verdict: **legitimate mechanical correction** vs **goalpost move**. Belief-blind — the answer could
   go either way; report the evidence, not a preferred story.

**Acceptance:** both nulls reproduced on real data; the materiality claim independently verified or
refuted; a defended verdict on whether the change was honest and whether leg (b) is load-bearing.

## PHASE 3 — Validity attacks (classifier, baseline, event-key, leakage, small-N statistics)

Attack each foundation the verdict rests on:
1. **Classifier.** Independently re-label a random sample of the archive (≥40 markets by hand);
   compute YOUR FP/FN vs `regime_classify`. Challenge the debatable calls: `politics/elections →
   recurring` (a single primary is arguably a one-off/expiring event), tennis → expiring via a
   *title* keyword (is "Wimbledon" reliably in the title? what about non-slam ATP weeks?), the 2
   "unknown" soccer rows, esports → unknown. **Sensitivity:** if tennis were recurring, or politics
   expiring, does the recurring-cleared count or the expiring-share move enough to change the verdict?
2. **Baseline & event key.** Verify the matched (cat×band) baseline is truly byte-identical to
   `softness_map` (re-derive; diff the cell means). Spot-check the `super_event` collapse on real
   games — is it over-collapsing (hiding independent bets) or under-collapsing (double-counting)?
3. **LEAKAGE / look-ahead (high-value target).** The matched baseline is built from the FULL-record
   blind pool — including post-cutoff (OUT-period) blind rows. Does that leak future information into
   the leak-free temporal split (leg a), contaminating the OUT surplus? Construct the leak-free
   baseline (IN-period blind only) and recompute leg (a); report whether the leak is real and whether
   it changes the number. Check for any other look-ahead (regime labels, cutoff selection).
4. **Small-cluster statistics.** `effective_n.py`'s own docstring warns that a normal-z CR LB on G<3
   clusters is nonsense and small-cluster **t(G−1)** is required. `regime_persistence`/`regime_edge`
   report LBs with `Z=1.96` on regimes of 2–4 clusters (e.g. the +12% recurring-OUT LB on 3 clusters,
   the per-regime net_positive flags on 2–4 clusters). Recompute those LBs with small-cluster t and
   report whether the "net-positive" / "+12% LB" claims survive — or are noise dressed as signal. Is
   the 1000-draw permutation null even meaningful over a discrete space of ~5 tiny regimes?

**Acceptance:** classifier FP/FN measured independently with a verdict-sensitivity read; baseline
byte-identity checked; the full-record-baseline leak explicitly tested and quantified; small-cluster
LBs recomputed with the correct t and their claims re-adjudicated.

## PHASE 4 — Verdict robustness / alternative-verdict search

Enumerate the researcher degrees of freedom and test whether SOCCER-ARTIFACT is stable or fragile:
- baseline choice (cat×band vs regime×band vs global), event key (super_event vs match_key vs raw
  condition), classifier edge-calls (Phase 3), temporal cutoff (median vs other leak-free splits),
  time-block (calendar-month vs a truly-disjoint definition — the builder flagged that its "2 disjoint
  months" are actually contiguous days), the 0.5 expiring-carried threshold.
For each **defensible** alternative, recompute the verdict. Produce a **verdict-stability surface**:
under how many defensible configurations does it read SOCCER-ARTIFACT vs PENDING vs REFUTED vs
PERSISTS? If the verdict flips under reasonable choices, it is fragile and that is the headline.

**Acceptance:** a stability table across defensible configurations with the fraction landing on each
verdict, and a statement of how robust SOCCER-ARTIFACT actually is.

## PHASE 5 — Compliance & report-honesty audit

1. **Brief compliance:** did the build obey its own constraints — helpers reused byte-identically (not
   subtly diverged), no migration added, nothing armed (`PILOT_ARMED` unset, `EARN_DEEP_SHARPS`
   false, alert path untouched), `main` never merged/rebased, additive-only? Diff against base `8cb9fab`
   and verify.
2. **Report honesty:** trace EVERY quantitative claim in `2026-07-04-regime-persistence.md` to an
   artifact and reproduce it. Are the stated **limitations complete**, or is a material caveat omitted
   (e.g. the small-cluster-t issue, the full-record-baseline leak if real, leg-(b)'s decorativeness if
   Phase 2 finds it)? An incomplete limitations section on an "honest" report is itself a finding.
3. **Selftest integrity:** re-run every `--selftest`; then check whether the selftests actually
   *exercise the failure modes they claim* (e.g. does the PERSISTS selftest pass only because the
   fixture was shaped to pass, per Phase 2's "can leg (b) ever fail?").

**Acceptance:** a compliance checklist (pass/fail each) and a claim-by-claim report-honesty trace.

## PHASE 6 — Stance-diverse synthesis → confidence-banded verdict

Spawn **independent, isolated, READ-ONLY reviewers** (separate agent invocations; they do NOT see
each other's notes), one per lens: {statistics/small-N, leakage/look-ahead, prereg-integrity/goalpost,
reuse-fidelity/compliance, alternative-verdict}. Each returns its single harshest **defensible**
finding with reproduced evidence and a confidence. (Read-only reviewers only — never run write/git
subagents alongside your own work.)

Synthesize WITHOUT averaging away dissent: the audit verdict is gated by the **harshest finding that
survives scrutiny**, not the mean sentiment. Emit a **confidence-banded verdict** per claim —
`CONFIRMED` (reproduced + survived attack) / `PLAUSIBLE` (consistent but not independently decisive) /
`REFUTED` / `OVERTURNED` — and an **overall**: does `SOCCER-ARTIFACT` stand, and are the instruments
trustworthy for the ongoing months-long accrual watch they're meant to power?

**Acceptance:** per-claim bands + an overall audit verdict with the single most important finding
stated first, and a clear "trust / trust-with-fixes / do-not-trust" call on the instruments.

---

## STANDING GUARDRAILS
- READ-ONLY on the deliverable; NO REAL MONEY; `PILOT_ARMED` unset; alert path untouched. Mutate none
  of the `regime_*` / `readiness_ledger` scripts. Never merge/rebase/push; never advance `main`; no
  new migration.
- Opus audits Opus (never a weaker critic). No `ANTHROPIC_API_KEY`; no child `claude` processes; no
  Haiku.
- Belief-blind: your numbers before their verdict. Default to REFUTED/PLAUSIBLE under uncertainty.
- Reproduce every headline number with YOUR code from the raw DB; a DIVERGE is a finding in either
  direction. A clean pass is only credible with the attacks that failed shown alongside it.
- Read-only reviewers may run in parallel; never run write/git subagents alongside your own git work.

## FINAL REPORT
`reports/entries/<UTC-date>-regime-persistence-AUDIT.md` — per phase: what was reproduced / attacked /
found, the agreement matrix, the prereg-integrity verdict (honest correction vs goalpost move + is
leg (b) load-bearing), the leakage finding, the small-cluster-t re-adjudication, the
verdict-stability surface, the compliance + report-honesty trace, and the Phase-6 confidence-banded
verdict. Lead with the SINGLE most important finding — whether that is "the SOCCER-ARTIFACT verdict is
independently reproduced and survives every attack" or "here is the defect that changes the
conclusion." Be brutally honest in either direction; a rigorously-earned confirmation and a
well-evidenced overturn are BOTH wins — a vague rubber-stamp is the only failure. Then STOP and hand
back; do not merge, do not modify the audited work, do not act on any real money.
