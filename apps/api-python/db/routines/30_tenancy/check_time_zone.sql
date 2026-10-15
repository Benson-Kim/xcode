-- tenancy.check_time_zone(p_name text) RETURNS text
-- Purpose: accept only an IANA zone name PostgreSQL knows, matched exactly and case-sensitively, and return it.
-- Callers: the localization and preference writes that set or change a zone (tenancy.check_localization, api.preferences_set).
-- Reads: the server's time zone files (through the TimeZone setting). Writes: nothing (the setting is restored).
-- Raises: XC422 time_zone_invalid.
-- Tests: tests/db/test_tenancy_helpers.py.
-- Setting TimeZone opens the one zone file the name points to and reports the file's own name,
-- so a wrong case comes back different; abbreviations (EAT) are refused by the setting, and
-- POSIX rules (UTC+3, <+03>-3) by the name pattern. pg_timezone_names would load every zone
-- file, seconds on some hosts, which the statement timeout does not allow.

CREATE OR REPLACE FUNCTION tenancy.check_time_zone(p_name text)
RETURNS text
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_previous text := current_setting('TimeZone');
  v_canonical text;
BEGIN
  IF p_name ~ '^[A-Za-z]+([_-][A-Za-z]+)*(/[A-Za-z0-9]+([_+-][A-Za-z0-9]+)*)*$' THEN
    BEGIN
      PERFORM set_config('TimeZone', p_name, true);
      v_canonical := current_setting('TimeZone');
    EXCEPTION
      WHEN invalid_parameter_value THEN
        v_canonical := NULL;
    END;
    PERFORM set_config('TimeZone', v_previous, true);
  END IF;
  IF v_canonical IS DISTINCT FROM p_name OR p_name IS NULL THEN
    PERFORM tenancy.refuse('time_zone_invalid', 'XC422', jsonb_build_object('value', p_name));
  END IF;
  RETURN p_name;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_time_zone(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_time_zone(text) TO xcode_api_executor;
