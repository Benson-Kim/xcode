-- revenue.reason_label(p_code smallint) RETURNS text
-- Purpose: the wire text of a no-earnings reason (Garage, Arrest, No Crew, Other); NULL for no reason or an unknown code.
-- Callers: api.revenue_capture (the change-log reason).
-- Reads: revenue.no_earnings_reasons. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.

CREATE OR REPLACE FUNCTION revenue.reason_label(p_code smallint)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT r.label FROM revenue.no_earnings_reasons AS r WHERE r.code = p_code;
$$;

REVOKE ALL ON FUNCTION revenue.reason_label(smallint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.reason_label(smallint) TO xcode_api_executor;
