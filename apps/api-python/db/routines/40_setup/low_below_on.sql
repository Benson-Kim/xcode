-- setup.low_below_on(p_vehicle_id uuid, p_day date) RETURNS numeric
-- Purpose: the low revenue figure in force for the vehicle on the day: that of the target set in force then, before the first set that of the first set, and KES 4,000 for a vehicle with no set.
-- Callers: revenue.capture_row, api.setup_vehicle_list, api.setup_target_set_save, api.setup_vehicle_create.
-- Reads: setup.vehicle_target_sets. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.
-- revenue.vehicle_days is its set form; a test holds the two equal.

CREATE OR REPLACE FUNCTION setup.low_below_on(p_vehicle_id uuid, p_day date)
RETURNS numeric
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(
    (
      SELECT s.low_below
      FROM setup.vehicle_target_sets AS s
      WHERE s.organization_id = tenancy.current_organization()
        AND s.vehicle_id = p_vehicle_id
      ORDER BY s.starts_on <= p_day DESC,
               CASE WHEN s.starts_on <= p_day THEN s.starts_on END DESC NULLS LAST,
               s.starts_on
      LIMIT 1
    ),
    4000
  );
$$;

REVOKE ALL ON FUNCTION setup.low_below_on(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.low_below_on(uuid, date) TO xcode_api_executor;
