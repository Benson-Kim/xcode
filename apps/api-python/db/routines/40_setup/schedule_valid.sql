-- setup.schedule_valid(p_frequency integer, p_day integer, p_last_day boolean, p_month integer) RETURNS boolean
-- Purpose: the ck_recurring_versions_schedule rule as a predicate: weekly on a weekday 0..6, monthly on a day 1..28 or the last day, yearly on a month 1..12 with the monthly day rule, daily with neither; a missing last_day counts as false.
-- Callers: setup.save_recurring (the recurring_schedule_shape refusal).
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.schedule_valid(
  p_frequency integer,
  p_day integer,
  p_last_day boolean,
  p_month integer
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(
    (p_frequency = 2 AND p_day BETWEEN 0 AND 6 AND NOT coalesce(p_last_day, false) AND p_month IS NULL)
    OR (
      p_frequency IN (3, 4)
      AND (
        (p_day BETWEEN 1 AND 28 AND NOT coalesce(p_last_day, false))
        OR (p_day IS NULL AND coalesce(p_last_day, false))
      )
      AND ((p_frequency = 4) = (p_month IS NOT NULL))
      AND (p_month IS NULL OR p_month BETWEEN 1 AND 12)
    )
    OR (p_frequency = 1 AND p_day IS NULL AND NOT coalesce(p_last_day, false) AND p_month IS NULL),
    false
  );
$$;

REVOKE ALL ON FUNCTION setup.schedule_valid(integer, integer, boolean, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.schedule_valid(integer, integer, boolean, integer) TO xcode_api_executor;
