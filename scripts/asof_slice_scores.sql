-- As-of per-(wallet, slice) surplus scores, leak-free by an explicit event-date window.
-- Faithful replica of Storage::trader_slice_scores (common/src/storage/consensus.rs)
-- with two changes required by the §0.5 pre-flight / H2 (leak-free as-of):
--   1. The economic time axis is the TRUE event date parsed from event_slug
--      (e.g. 'fifwc-fra-swe-2026-06-30' -> 2026-06-30), NOT trader_fills.resolved_at
--      nor ts. Both of those are bulk-backfill/crawl timestamps on this archive
--      (resolved_at ALL in 2026-06/07; ts mass on 2026-06-30) and are unusable as an
--      as-of cut. See DECISIONS.md D1.
--   2. The fleet band-blind AND the slice surplus are both restricted to the window,
--      so a train cut leaks no post-cut outcome (H2). recency7d/30d slices dropped
--      (ambiguous under an as-of cut, per blueprint Item 6).
-- Window is [ :d_lo , :d_hi ) on event date. Rows with no parseable slug date are
-- excluded from the split (cannot be placed in time).
WITH base AS (
    SELECT wallet,
           COALESCE(event_slug, condition_id) AS ev,
           width_bucket(price, 0.0, 1.0, 5) AS band,
           (outcome_won::int)::float8 - price AS a,
           (outcome_won::int)::float8 AS won,
           COALESCE(sport, 'other') AS sport,
           (regexp_match(event_slug, '(20[0-9]{2}-[0-9]{2}-[0-9]{2})'))[1]::date AS d
    FROM trader_fills
    WHERE resolved AND side = 'BUY' AND outcome_won IS NOT NULL
),
adv AS (
    SELECT * FROM base
    WHERE d IS NOT NULL AND d >= :'d_lo'::date AND d < :'d_hi'::date
),
blind AS ( SELECT band, AVG(a) AS blind_edge FROM adv GROUP BY band ),
surp AS (
    SELECT v.wallet, v.ev, v.band, v.sport, v.a, v.won,
           v.a - COALESCE(b.blind_edge, 0) AS s
    FROM adv v LEFT JOIN blind b USING (band)
),
tagged AS (
    SELECT wallet, 'overall'::text AS slice_kind, ''::text AS slice_key, ev, s FROM surp
    UNION ALL SELECT wallet, 'sport', sport,            ev, s FROM surp
    UNION ALL SELECT wallet, 'band',  'b'||band::text,  ev, s FROM surp
),
evl AS (
    SELECT wallet, slice_kind, slice_key, ev, AVG(s) AS ev_surplus
    FROM tagged GROUP BY wallet, slice_kind, slice_key, ev
)
SELECT wallet, slice_kind, slice_key,
       COUNT(DISTINCT ev)      AS n_events,
       AVG(ev_surplus)         AS surplus,
       STDDEV_SAMP(ev_surplus) AS surplus_sd
FROM evl
GROUP BY wallet, slice_kind, slice_key;
