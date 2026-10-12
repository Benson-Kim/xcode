-- setup.target_on(p_vehicle_id uuid, p_day date) RETURNS numeric
-- Purpose: the weekly target in force on the day: 0 when the vehicle is not in the fleet that day or no set has started, else the week total of the target set in force.
-- Callers: api.setup_vehicle_list, api.setup_vehicle_update.
-- Reads: what setup.vehicle_active_on and setup.target_set_on read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.target_on(p_vehicle_id uuid, p_day date)
RETURNS numeric
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF NOT setup.vehicle_active_on(p_vehicle_id, p_day) THEN
    RETURN 0;
  END IF;
  RETURN coalesce(setup.week_total(setup.target_set_on(p_vehicle_id, p_day)), 0);
END;
$$;

REVOKE ALL ON FUNCTION setup.target_on(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.target_on(uuid, date) TO xcode_api_executor;
