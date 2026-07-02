-- Deep-leaderboard ingestion (RUN-DEEP-LEADERBOARD-500): capture the deep pool
-- (ranks 51..depth) as PROFILED CANDIDATES without letting them vote in consensus.
--
-- `consensus_eligible` is the belief-blind provenance flag that decouples CAPTURE
-- (poll + archive every tracked trader's fills, for the efficiency/profile pass)
-- from VOTING (only eligible traders count as consensus backers/opposers).
--
-- DEFAULT TRUE is deliberate and additive: every pre-existing row — and every
-- manual `/follow` — stays eligible exactly as today. Deep traders are the only
-- rows set FALSE (at upsert, when rank > TRACK_CONSENSUS_RANK_CUTOFF), so with the
-- default TRACK_DEPTH=40 no row is ever ineligible and the consensus engine is
-- byte-for-byte unchanged. A deep trader flips to TRUE only by clearing the
-- belief-blind earned-trust gate — never by mere leaderboard presence.
ALTER TABLE followed_traders
    ADD COLUMN IF NOT EXISTS consensus_eligible BOOLEAN NOT NULL DEFAULT TRUE;
