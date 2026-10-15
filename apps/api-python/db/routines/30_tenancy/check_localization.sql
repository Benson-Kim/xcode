-- tenancy.check_localization(p_document jsonb) RETURNS void
-- Purpose: validate a localization document (document keys, values already of the right JSON type): a BCP 47 locale, an IANA time zone PostgreSQL knows, and the format settings (date pattern, first day of the week 0..6, week numbering, ISO currency code, 0..2 decimals).
-- Callers: api.organization_settings_set (the merged section), tenancy.effective_settings (the stored section, on every read).
-- Reads: what tenancy.check_time_zone reads. Writes: nothing.
-- Raises: XC422 locale_invalid, XC422 format_settings_invalid, XC422 time_zone_invalid via tenancy.check_time_zone.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.check_localization(p_document jsonb)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF coalesce(p_document ->> 'locale' !~ '^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$', true) THEN
    PERFORM tenancy.refuse('locale_invalid', 'XC422');
  END IF;
  PERFORM tenancy.check_time_zone(p_document ->> 'time_zone');
  IF coalesce(p_document ->> 'date_pattern' NOT IN ('short', 'medium', 'long'), true)
     OR coalesce((p_document ->> 'first_day_of_week')::numeric NOT BETWEEN 0 AND 6, true)
     OR coalesce(p_document ->> 'week_numbering' NOT IN ('iso8601', 'local'), true)
     OR coalesce(p_document ->> 'currency' !~ '^[A-Z]{3}$', true)
     OR coalesce((p_document ->> 'number_decimals')::numeric NOT BETWEEN 0 AND 2, true) THEN
    PERFORM tenancy.refuse('format_settings_invalid', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_localization(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_localization(jsonb) TO xcode_api_executor;
