# PRE-REGISTRATION ADDENDUM #2 — small-cluster inference + leak-free baseline (audit-driven corrections)

**Frozen:** 2026-07-04T21:01:32Z (UTC). Supersedes two specifics of
`PREREG_20260704T191458Z_regime_persistence.md`: the LB critical value (§3/§7 `Z`) and the leg-(a)
temporal baseline (§4 leg a). Everything else stands. Written in response to an **independent
adversarial audit** (`reports/entries/2026-07-04-regime-persistence-AUDIT.md`) that reproduced the
whole deliverable and found these two methodology defects. **Belief-blind note:** both corrections
make inference STRICTER / more correct and **strengthen** the non-certification verdict — the verdict
is `SOCCER-ARTIFACT` under both the old and new conventions — so there is no result-shopping incentive
in adopting them. They are applied because they are right, not to reach a target.

## Correction A — small-cluster inference: normal z(1.96) → t(G−1)

**Defect (audit Phase 3.4 / Phase 6 statistics lens):** every reported cluster-robust LB used a normal
`Z = 1.96` even though the cluster count `G` is typically 2–6. `effective_n.py`'s own docstring warns
that a normal-z LB on few clusters is misleading and small-cluster **t(G−1)** is required. Backing the
SE out of the committed LBs and re-reading at t(G−1) at one-sided 95% flips the sign of at least one
informational sub-claim (e.g. a G=2 regime at `t(1)≈6.31`).

**Frozen v2:** the one-sided 95% lower bound is `LB = θ − t_{0.95}(G−1) · se_CR`, computed via
`effective_n._t_ppf(0.95, G−1)` (the module's own t machinery, matching its alpha convention and the
audit's independent re-derivation). `LB = None` for `G < 2` (a single cluster carries no
between-cluster information — a net_positive / clearance claim on one cluster is NOT certifiable).
Implemented once in `regime_edge.lb_small_cluster(...)` and reused by `regime_edge`,
`regime_persistence`, and `regime_net_edge`.

**Consequences (snapshot-dependent, non-load-bearing):** the load-bearing POOLED edge survives
(t-LB ≈ +2.7% > 0). Any `G = 2` regime cannot clear (`t(1)≈6.31`), so a per-regime "net-positive" or
"transfers" claim resting on 2 clusters flips negative; at the audit's 286-signal snapshot this dropped
the net-positive recurring count 2→1 and leg-(b)'s transfer count 2→1. On a later snapshot a borderline
regime may reach `G = 3` and survive — the count DRIFTS with the live data. What does NOT drift: all
recurring regimes remain far below the 10-cluster persistence floor, leg-(a) is PENDING, and PERSISTS
is unreachable — so the exact count is informational, never load-bearing.

## Correction B — leg-(a) temporal baseline: full-record blind → IN-period-only (leak-free)

**Defect (audit Phase 3.3 / Phase 6 leakage lens):** the leg-(a) temporal test split the record at a
cutoff and read the OUT edge, but the matched (category × band) baseline was fit on the FULL-record
blind pool — including ~43% post-cutoff (OUT-period) blind rows. That is look-ahead: the "leak-free"
forward test's baseline saw future data. It was benign in DIRECTION today (it DEFLATED the OUT edge,
+19% leaky vs +21% leak-free) and leg-(a) is PENDING on the 3<10 cluster gate regardless — but once
≥10 recurring OUT clusters accrue (the Aug–Sep certification path), the OUT LB becomes the binding
PASS gate and this same leak would contaminate the certification LB.

**Frozen v2:** the leg-(a) temporal baseline is fit on **IN-period (strictly pre-cutoff) blind rows
only** (`regime_persistence.build_events_leakfree`), applied to both IN and OUT favorite events; cells
absent from the IN-period blind default to a 0 baseline (documented). Leg-(b) is NOT a forward test
(leave-one-regime-out, in-sample), so it keeps the full-record matched baseline (the `regime_edge`
convention) — only the temporal forward test needs the strictly-causal baseline.

## Correction C (labeling, not a threshold) — leg-(b) reported honestly

The audit showed the leg-(b) regime-permutation null is NON-DISCRIMINATING on the current record: its
concentration guard cannot fire (min achievable `p_conc ≈ 0.22 ≥ 0.05` for any real count) and the
original upper-tail beat-null cannot pass. So leg-(b) reduces to a raw "≥2 recurring regimes transfer"
count and must NOT be headlined as a passed statistical test. The instrument now reports
`guard_can_fire` / `beat_null_can_pass` / `guard_inert_note` and prints "RAW COUNT — guard inert"
rather than "PASS". No threshold changed; this is a truthfulness fix to presentation. (Leg-(b) remains
immaterial to the verdict — it is only consulted when leg-(a) PASSes, which is PENDING.)

## Correction D (classifier) — one-off elections are expiring

`politics/elections` was hardcoded recurring; the live political markets are one-off Colorado primaries
(substantively expiring). Removed `politics/elections` from the recurring set (→ unknown → treated
expiring) and added election keywords (`primary`, `nominee`, `runoff`, …) to Rule E. Raises the
expiring share (~0.566 → ~0.57–0.585), REINFORCING SOCCER-ARTIFACT. Latent-bug fix; harmless today.

## Unchanged

`PERSIST_MIN_CLUSTERS = 10`, `MARGIN = 0.03`, one-sided 95% confidence level, `TRANSFER_MIN_REGIMES = 2`,
`N_PERM_REGIME = 1000`, `SEED = 20260704`, the regime taxonomy, the event super-key, the matched-baseline
CONSTRUCTION (only its FITTING POOL changes for leg a), the net-after-tax rule, and the verdict ladder
all stand as frozen in the original prereg and ADDENDUM #1.
