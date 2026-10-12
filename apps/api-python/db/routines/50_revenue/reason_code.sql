-- revenue.reason_code(p_text text) RETURNS smallint
-- Purpose: the code of a no-earnings reason the clients send: its label (Garage, Arrest, No Crew, Other) or the label without spaces (NoCrew), case-sensitive; NULL for anything else.
-- Callers: api.revenue_capture (after trimming; a NULL answer for a non-blank text is the refusal revenue_reason_invalid).
-- Reads: revenue.no_earnings_reasons. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.

CREATE OR REPLACE FUNCTION revenue.reason_code(p_text text)
RETURNS smallint
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT r.code
  FROM revenue.no_earnings_reasons AS r
  WHERE r.label = p_text OR replace(r.label, ' ', '') = p_text;
$$;

REVOKE ALL ON FUNCTION revenue.reason_code(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.reason_code(text) TO xcode_api_executor;
