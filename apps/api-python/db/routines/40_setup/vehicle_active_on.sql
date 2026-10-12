-- setup.vehicle_active_on(p_vehicle_id uuid, p_day date) RETURNS boolean
-- Purpose: whether the vehicle is in the fleet on the day: joined by then, not yet left, and not away; false for an unknown vehicle.
-- Callers: setup.target_on, setup.day_target, the revenue routines, and the petty-cash expense checks (pettycash.check_expense, api.pettycash_options_get).
-- Reads: setup.fleet_vehicles, and what setup.vehicle_away_on reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.vehicle_active_on(p_vehicle_id uuid, p_day date)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_vehicle setup.fleet_vehicles;
BEGIN
  SELECT f.* INTO v_vehicle
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = tenancy.current_organization() AND f.id = p_vehicle_id;
  IF NOT FOUND OR p_day IS NULL THEN
    RETURN false;
  END IF;
  RETURN v_vehicle.joined_on <= p_day
    AND (v_vehicle.left_on IS NULL OR p_day < v_vehicle.left_on)
    AND NOT setup.vehicle_away_on(p_vehicle_id, p_day);
END;
$$;

REVOKE ALL ON FUNCTION setup.vehicle_active_on(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.vehicle_active_on(uuid, date) TO xcode_api_executor;
