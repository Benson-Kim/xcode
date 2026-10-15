-- setup.week_total(p_set setup.vehicle_target_sets) RETURNS numeric
-- Purpose: the weekly target of a set, the sum of its seven day figures; null for a row of nulls.
-- Callers: setup.target_on, api.setup_vehicle_list, api.setup_target_set_list, api.setup_vehicle_create, revenue.vehicle_days.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.week_total(p_set setup.vehicle_target_sets)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT p_set.monday + p_set.tuesday + p_set.wednesday + p_set.thursday + p_set.friday
         + p_set.saturday + p_set.sunday;
$$;

REVOKE ALL ON FUNCTION setup.week_total(setup.vehicle_target_sets) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.week_total(setup.vehicle_target_sets) TO xcode_api_executor;
