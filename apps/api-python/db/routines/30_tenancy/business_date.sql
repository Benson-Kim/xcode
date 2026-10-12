-- tenancy.business_date(p_organization_id uuid, p_now timestamptz) RETURNS date
-- Purpose: the organization's business date: the held date when one is set, else the calendar date of p_now in its time zone.
-- Callers: every routine that needs "today" (setup, revenue, petty cash).
-- Reads: tenancy.organizations, tenancy.organization_localizations. Writes: nothing.
-- Raises: XC422 time_zone_invalid via tenancy.calendar_date.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.business_date(p_organization_id uuid, p_now timestamptz)
RETURNS date
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_held date;
BEGIN
  SELECT o.business_date INTO v_held FROM tenancy.organizations AS o WHERE o.id = p_organization_id;
  RETURN coalesce(v_held, tenancy.calendar_date(p_organization_id, p_now));
END;
$$;

REVOKE ALL ON FUNCTION tenancy.business_date(uuid, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.business_date(uuid, timestamptz) TO xcode_api_executor;
