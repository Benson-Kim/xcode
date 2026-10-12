-- setup.vehicle_away_on(p_vehicle_id uuid, p_day date) RETURNS boolean
-- Purpose: whether the day falls inside one of the vehicle's away periods [left_on, returned_on).
-- Callers: setup.vehicle_active_on, and the revenue routines (the away refusal differs from the inactive one).
-- Reads: setup.vehicle_away_periods. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.vehicle_away_on(p_vehicle_id uuid, p_day date)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM setup.vehicle_away_periods AS a
    WHERE a.organization_id = tenancy.current_organization()
      AND a.vehicle_id = p_vehicle_id
      AND p_day >= a.left_on
      AND p_day < a.returned_on
  );
$$;

REVOKE ALL ON FUNCTION setup.vehicle_away_on(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.vehicle_away_on(uuid, date) TO xcode_api_executor;
