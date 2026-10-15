-- tenancy.calendar_date(p_organization_id uuid, p_now timestamptz) RETURNS date
-- Purpose: the calendar date of p_now in the organization's time zone (Africa/Nairobi when no localization row exists).
-- Callers: tenancy.business_date; the settings reads (calendar_date).
-- Reads: tenancy.organization_localizations. Writes: nothing.
-- Raises: XC422 time_zone_invalid.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.calendar_date(p_organization_id uuid, p_now timestamptz)
RETURNS date
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_zone text;
BEGIN
  SELECT l.time_zone INTO v_zone
  FROM tenancy.organization_localizations AS l
  WHERE l.organization_id = p_organization_id;
  v_zone := coalesce(v_zone, 'Africa/Nairobi');
  BEGIN
    RETURN (p_now AT TIME ZONE v_zone)::date;
  EXCEPTION
    WHEN invalid_parameter_value THEN
      -- A stored zone PostgreSQL does not know (written before validation, or a copied row).
      PERFORM tenancy.refuse('time_zone_invalid', 'XC422', jsonb_build_object('value', v_zone));
  END;
  RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.calendar_date(uuid, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.calendar_date(uuid, timestamptz) TO xcode_api_executor;
