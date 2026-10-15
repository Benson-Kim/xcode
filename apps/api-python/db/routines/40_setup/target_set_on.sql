-- setup.target_set_on(p_vehicle_id uuid, p_day date) RETURNS setup.vehicle_target_sets
-- Purpose: the target set in force on the day, the one with the latest start on or before it; a row of nulls when none has started.
-- Callers: setup.day_target, setup.target_on, api.setup_vehicle_list, api.setup_target_set_save, api.setup_vehicle_update.
-- Reads: setup.vehicle_target_sets. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.target_set_on(p_vehicle_id uuid, p_day date)
RETURNS setup.vehicle_target_sets
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT s.*
  FROM setup.vehicle_target_sets AS s
  WHERE s.organization_id = tenancy.current_organization()
    AND s.vehicle_id = p_vehicle_id
    AND s.starts_on <= p_day
  ORDER BY s.starts_on DESC
  LIMIT 1;
$$;

REVOKE ALL ON FUNCTION setup.target_set_on(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.target_set_on(uuid, date) TO xcode_api_executor;
