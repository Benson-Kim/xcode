-- setup.saving_window_revenue(p_vehicle_id uuid, p_run_on date, p_days integer) RETURNS TABLE (revenue numeric, complete boolean)
-- Purpose: the revenue a saving's rule weighs for one run: over the p_days days ending on p_run_on, revenue is the sum of the recorded amounts (a reason-only day counts 0), and the window is complete when every day of it on which the vehicle is active (joined, not left, not away) has a record. A window with no active day is complete with no revenue. A 7-day rule weighs a Sunday-to-Saturday week instead, the latest ending on or before p_run_on (a Saturday run weighs its own week, any other day the week before), for run dates from the organization's change to Sunday weeks (the calendar date of tenancy.organizations.sunday_week_at; always when it has none); earlier run dates keep the 7 days ending on the run.
-- Callers: setup.decide_fleet_saving_runs, api.setup_recurring_runs.
-- Reads: revenue.records, tenancy.organizations, and what setup.vehicle_active_on and tenancy.calendar_date read. Writes: nothing.
-- Raises: XC422 time_zone_invalid via tenancy.calendar_date.
-- Tests: tests/db/test_setup_helpers.py, tests/db/test_recurring_pause_routines.py.

CREATE OR REPLACE FUNCTION setup.saving_window_revenue(p_vehicle_id uuid, p_run_on date, p_days integer)
RETURNS TABLE (revenue numeric, complete boolean)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_last date := p_run_on;
  v_since timestamptz;
BEGIN
  IF p_days = 7 THEN
    SELECT o.sunday_week_at INTO v_since FROM tenancy.organizations AS o WHERE o.id = v_organization_id;
    IF v_since IS NULL OR p_run_on >= tenancy.calendar_date(v_organization_id, v_since) THEN
      v_last := p_run_on - (extract(dow FROM p_run_on)::integer + 1) % 7;
    END IF;
  END IF;
  RETURN QUERY
  SELECT coalesce(sum(r.amount), 0)::numeric,
         bool_and(r.id IS NOT NULL OR NOT setup.vehicle_active_on(p_vehicle_id, d.day)) IS NOT FALSE
  FROM (
    SELECT g::date AS day
    FROM generate_series((v_last - p_days + 1)::timestamp, v_last::timestamp, interval '1 day') AS g
  ) AS d
  LEFT JOIN revenue.records AS r
    ON r.organization_id = v_organization_id
   AND r.vehicle_id = p_vehicle_id
   AND r.business_date = d.day;
END;
$$;

REVOKE ALL ON FUNCTION setup.saving_window_revenue(uuid, date, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.saving_window_revenue(uuid, date, integer) TO xcode_api_executor;
