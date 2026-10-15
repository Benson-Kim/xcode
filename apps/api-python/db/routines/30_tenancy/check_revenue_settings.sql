-- tenancy.check_revenue_settings(p_document jsonb) RETURNS void
-- Purpose: validate a revenue settings document (document keys, values already JSON numbers): the low-day threshold 0 or more, the amber band 0 to 100 per cent, each with at most two decimal places and within the table's columns.
-- Callers: api.organization_settings_set (the merged section).
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 revenue_settings_invalid.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.check_revenue_settings(p_document jsonb)
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_threshold numeric := (p_document ->> 'low_day_threshold')::numeric;
  v_amber numeric := (p_document ->> 'gap_amber_percent')::numeric;
BEGIN
  IF coalesce(v_threshold NOT BETWEEN 0 AND 999999999999.99, true)
     OR round(v_threshold, 2) <> v_threshold
     OR coalesce(v_amber NOT BETWEEN 0 AND 100, true)
     OR round(v_amber, 2) <> v_amber THEN
    PERFORM tenancy.refuse('revenue_settings_invalid', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_revenue_settings(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_revenue_settings(jsonb) TO xcode_api_executor;
