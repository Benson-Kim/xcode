-- revenue.percent(p_amount numeric, p_target_sum numeric) RETURNS integer
-- Purpose: what an amount is of the expected figure p_target_sum (a sum of day targets), as a whole percent rounded half away from zero and held to the integer range; NULL when nothing is expected.
-- Callers: revenue.vehicle_week, api.revenue_week_get, api.revenue_dashboard_get.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.
-- amount * 100 / target is computed with 30 decimals, so an exact half (5,750 of 10,000 is
-- 57.5) rounds up to 58 instead of drifting below it.

CREATE OR REPLACE FUNCTION revenue.percent(p_amount numeric, p_target_sum numeric)
RETURNS integer
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_target_sum IS NULL OR p_target_sum = 0 THEN NULL
           ELSE greatest(
                  least(round((p_amount * 100)::numeric(60, 30) / p_target_sum), 2147483647),
                  -2147483648
                )::integer
         END;
$$;

REVOKE ALL ON FUNCTION revenue.percent(numeric, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.percent(numeric, numeric) TO xcode_api_executor;
