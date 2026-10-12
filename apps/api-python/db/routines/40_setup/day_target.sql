-- setup.day_target(p_vehicle_id uuid, p_day date) RETURNS numeric
-- Purpose: the target of one day: 0 when the vehicle is not in the fleet that day or no set has started, else the figure for that weekday (ISO, Monday first) in the set in force.
-- Callers: api.setup_vehicle_report, and the revenue routines.
-- Reads: what setup.vehicle_active_on and setup.target_set_on read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.day_target(p_vehicle_id uuid, p_day date)
RETURNS numeric
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_set setup.vehicle_target_sets;
BEGIN
  IF NOT setup.vehicle_active_on(p_vehicle_id, p_day) THEN
    RETURN 0;
  END IF;
  v_set := setup.target_set_on(p_vehicle_id, p_day);
  RETURN coalesce(
    CASE extract(isodow FROM p_day)::integer
      WHEN 1 THEN v_set.monday
      WHEN 2 THEN v_set.tuesday
      WHEN 3 THEN v_set.wednesday
      WHEN 4 THEN v_set.thursday
      WHEN 5 THEN v_set.friday
      WHEN 6 THEN v_set.saturday
      ELSE v_set.sunday
    END,
    0
  );
END;
$$;

REVOKE ALL ON FUNCTION setup.day_target(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.day_target(uuid, date) TO xcode_api_executor;
