-- revenue.week_start(p_day date) RETURNS date
-- Purpose: the first day of the organization week that holds the day: the day itself or the latest earlier day that falls on the localization's first day of the week (0 Sunday .. 6 Saturday).
-- Callers: api.revenue_week_get, api.revenue_dashboard_get.
-- Reads: what tenancy.settings_document reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.

CREATE OR REPLACE FUNCTION revenue.week_start(p_day date)
RETURNS date
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT p_day - (extract(dow FROM p_day)::integer - s.first_day + 7) % 7
  FROM (
    SELECT (tenancy.settings_document('localization') ->> 'first_day_of_week')::integer AS first_day
  ) AS s;
$$;

REVOKE ALL ON FUNCTION revenue.week_start(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.week_start(date) TO xcode_api_executor;
