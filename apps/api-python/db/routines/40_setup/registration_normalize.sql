-- setup.registration_normalize(p_input text) RETURNS text
-- Purpose: a registration in its stored form: trimmed, upper-cased, spaces removed, checked against K + two letters + three digits + a letter, and returned with one space after the third character (KDA 482M).
-- Callers: api.setup_vehicle_create, api.setup_vehicle_update.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 vehicle_registration_format.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.registration_normalize(p_input text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_compact text := replace(upper(coalesce(tenancy.trim_text(p_input), '')), ' ', '');
BEGIN
  IF v_compact !~ '^K[A-Z]{2}[0-9]{3}[A-Z]$' THEN
    PERFORM tenancy.refuse('vehicle_registration_format', 'XC422');
  END IF;
  RETURN left(v_compact, 3) || ' ' || substr(v_compact, 4);
END;
$$;

REVOKE ALL ON FUNCTION setup.registration_normalize(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.registration_normalize(text) TO xcode_api_executor;
