-- revenue.gap_band(p_gap numeric, p_target numeric, p_amber_percent numeric) RETURNS text
-- Purpose: the colour of a gap to target: green at or above the target, amber below it by up to p_amber_percent of the target, red beyond; NULL when nothing is expected.
-- Callers: revenue.vehicle_week, api.revenue_week_get.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.

CREATE OR REPLACE FUNCTION revenue.gap_band(p_gap numeric, p_target numeric, p_amber_percent numeric)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_target IS NULL OR p_target = 0 THEN NULL
           WHEN p_gap >= 0 THEN 'green'
           WHEN -p_gap * 100 <= p_target * p_amber_percent THEN 'amber'
           ELSE 'red'
         END;
$$;

REVOKE ALL ON FUNCTION revenue.gap_band(numeric, numeric, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.gap_band(numeric, numeric, numeric) TO xcode_api_executor;
