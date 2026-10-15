-- tenancy.check_writable(p_day date, p_as_of timestamptz) RETURNS void
-- Purpose: refuse a write of a record dated p_day by the current actor when that day is before their earliest writable date, taken from the business date of p_as_of in the organization's time zone (the held business date when one is set); called after the permission and existence checks, before the version check.
-- Callers: the writes the limit applies to: revenue capture and change, petty-cash expense add, edit, delete and reopen, cash issue, credit note and cash delete, central expense add and edit.
-- Reads: what tenancy.business_date and tenancy.earliest_writable read. Writes: nothing.
-- Raises: XC422 record_too_old, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_back_limit.py.

CREATE OR REPLACE FUNCTION tenancy.check_writable(p_day date, p_as_of timestamptz)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_earliest date;
BEGIN
  v_earliest := tenancy.earliest_writable(
    v_organization_id, tenancy.current_actor(), tenancy.business_date(v_organization_id, p_as_of)
  );
  IF p_day < v_earliest THEN
    PERFORM tenancy.refuse(
      'record_too_old', 'XC422', jsonb_build_object('earliest', to_char(v_earliest, 'YYYY-MM-DD'))
    );
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_writable(date, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_writable(date, timestamptz) TO xcode_api_executor;
