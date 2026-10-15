-- setup.vehicle_money_in(p_vehicle_id uuid, p_window daterange) RETURNS numeric
-- Purpose: the revenue recorded for the vehicle on the days of the window (a day with a no-earnings reason adds nothing); 0 for an empty window.
-- Callers: setup.vehicle_net, api.setup_vehicle_report.
-- Reads: revenue.records. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_vehicle_routines.py.

CREATE OR REPLACE FUNCTION setup.vehicle_money_in(p_vehicle_id uuid, p_window daterange)
RETURNS numeric
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(sum(r.amount), 0)
  FROM revenue.records AS r
  WHERE r.organization_id = tenancy.current_organization()
    AND r.vehicle_id = p_vehicle_id
    AND r.business_date >= lower(p_window)
    AND r.business_date < upper(p_window);
$$;

REVOKE ALL ON FUNCTION setup.vehicle_money_in(uuid, daterange) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.vehicle_money_in(uuid, daterange) TO xcode_api_executor;
