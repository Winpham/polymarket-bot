-- Deep-pool edge run (RUN-DEEP-DATA-EDGE): durable EARNED eligibility.
--
-- `consensus_eligible` (033) is rank-derived provenance: the leaderboard refresh
-- recomputes it from rank ≤ TRACK_CONSENSUS_RANK_CUTOFF at every upsert, so it can
-- never carry an earned promotion — a deep trader flipped there would be clobbered
-- on the next refresh (or keep a vote after falling off the board).
--
-- `earned_eligible` is the DURABLE half: set only by the deliberate, flag-gated
-- promotion pass (EARN_DEEP_SHARPS) for deep traders whose belief-blind
-- `trust_verdict` is Trusted (surplus lower bound > capture margin over ≥30
-- distinct resolved events, Bonferroni-corrected, day-deflated). The leaderboard
-- upsert never touches this column, so rank churn cannot revoke or grant it.
--
-- Consensus counts a trader iff (consensus_eligible OR earned_eligible). DEFAULT
-- FALSE ⇒ every existing row and every future refresh is byte-for-byte unchanged
-- until a promotion is deliberately recorded. Revocation is a deliberate manual
-- act (UPDATE ... SET earned_eligible = FALSE), never automatic.
ALTER TABLE followed_traders
    ADD COLUMN IF NOT EXISTS earned_eligible BOOLEAN NOT NULL DEFAULT FALSE;
