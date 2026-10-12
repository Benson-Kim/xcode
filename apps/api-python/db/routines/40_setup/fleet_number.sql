-- setup.fleet_number(p_value text) RETURNS text
-- Purpose: a fleet number in its stored form: trimmed, required, at most 20 characters.
-- Callers: api.setup_vehicle_create, api.setup_vehicle_update.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 vehicle_fleet_required, XC422 vehicle_fleet_length.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.fleet_number(p_value text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_value text := tenancy.trim_text(p_value);
BEGIN
  IF v_value IS NULL THEN
    PERFORM tenancy.refuse('vehicle_fleet_required', 'XC422');
  END IF;
  IF char_length(v_value) > 20 THEN
    PERFORM tenancy.refuse('vehicle_fleet_length', 'XC422');
  END IF;
  RETURN v_value;
END;
$$;

REVOKE ALL ON FUNCTION setup.fleet_number(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.fleet_number(text) TO xcode_api_executor;
