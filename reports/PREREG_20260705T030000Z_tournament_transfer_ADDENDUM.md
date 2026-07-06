# PRE-REGISTRATION ADDENDUM — tournament-transfer verdict ladder (POWER-LIMITED vs IDIOSYNCRATIC)

**Frozen:** 2026-07-05T03:00:00Z (UTC). Supersedes §5 of
`PREREG_20260705T024128Z_tournament_transfer.md` (adds one rung); everything else stands. Written
after the first live run, BEFORE any real-money action — belief-blind and action-neutral (the new rung
still means "not demonstrated, real money OFF, accrue").

## Defect found by running the frozen ladder

The frozen ladder collapsed every "transfer count < 2" outcome into `TOURNAMENT-IDIOSYNCRATIC — the
edge does NOT hold across tournaments (artifact stands)". The first live run showed that label is
INACCURATE for the actual data: the testable tournaments' edges are all **positive and sign-consistent**
(World Cup +5.1%, Wimbledon +6.9%, esports +14.7%) — they do NOT disagree. The reason none of the two
MAJOR tournaments "transfers" is that neither individually clears the 3% capture margin under
small-cluster t on 5–6 day-clusters (Wimbledon's t-LB is even negative from high day-to-day variance).
That is **power-limitation**, not **idiosyncrasy** — and "artifact stands" over-claims a refutation the
data does not support (nor does it support the optimistic "transfers"). The honest middle is a distinct
rung.

## Corrected §5 rung (frozen v2)

When `real_transfer_count < TRANSFER_MIN_TOURNAMENTS` (and not REFUTED), split on the SIGN-CONSISTENCY
of the testable (is_tournament, G≥2) tournaments' point-estimate surpluses:
- **`TOURNAMENT-POWER-LIMITED`** iff `≥ 0.6` of the testable tournaments have surplus `> 0` (edges
  consistent in sign but too few clusters per tournament to clear the capture margin individually) →
  INDETERMINATE, accrue more tournaments. This is action-identical to PENDING (real money OFF), but
  names the true blocker (per-tournament power / edge-thin-vs-cost), not a false artifact claim.
- **`TOURNAMENT-IDIOSYNCRATIC`** otherwise (edges genuinely disagree — mixed signs / some ≤0) → the
  edge is tournament-specific, artifact read stands.

Report `pos_frac` (fraction of testable tournaments with positive surplus) and the median testable
surplus so the reader sees WHY. All other constants, the small-cluster-t LB, the honest permutation-
guard diagnostics, and the CONTEMPORANEOUS/FORWARD split for `count ≥ 2` are unchanged.

**Belief-blind note:** this rung does not lower any bar or change the action — a POWER-LIMITED read is
still "not demonstrated, real money remains gated on λ + net-cost + forward accrual + Tue." It only
replaces an inaccurate "artifact stands" with the truthful "consistent-but-underpowered." The
direction is *less bleak*, which is disclosed here so it cannot masquerade as a neutral edit.
