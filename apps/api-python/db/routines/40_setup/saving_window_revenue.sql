-- setup.saving_window_revenue(p_vehicle_id uuid, p_run_on date, p_days integer) RETURNS TABLE (revenue numeric, complete boolean)
-- Purpose: the revenue a saving's rule weighs for one run: over the p_days days ending on p_run_on, revenue is the sum of the recorded amounts (a reason-only day counts 0), and the window is complete when every day of it on which the vehicle is active (joined, not left, not away) has a record. A window with no active day is complete with no revenue.
-- Callers: setup.decide_saving_runs, api.setup_recurring_runs.
-- Reads: revenue.records, and what setup.vehicle_active_on reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py, tests/db/test_recurring_pause_routines.py.

CREATE OR REPLACE FUNCTION setup.saving_window_revenue(p_vehicle_id uuid, p_run_on date, p_days integer)
RETURNS TABLE (revenue numeric, complete boolean)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN QUERY
  SELECT coalesce(sum(r.amount), 0)::numeric,
         bool_and(r.id IS NOT NULL OR NOT setup.vehicle_active_on(p_vehicle_id, d.day)) IS NOT FALSE
  FROM (
    SELECT g::date AS day
    FROM generate_series((p_run_on - p_days + 1)::timestamp, p_run_on::timestamp, interval '1 day') AS g
  ) AS d
  LEFT JOIN revenue.records AS r
    ON r.organization_id = tenancy.current_organization()
   AND r.vehicle_id = p_vehicle_id
   AND r.business_date = d.day;
END;
$$;

REVOKE ALL ON FUNCTION setup.saving_window_revenue(uuid, date, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.saving_window_revenue(uuid, date, integer) TO xcode_api_executor;
