-- tenancy.check_typed_reason(p_reason text) RETURNS text
-- Purpose: trim an optional typed reason; NULL or blank gives NULL, otherwise it must be 1..500 characters.
-- Callers: every logged write that accepts a typed reason.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 reason_length.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.check_typed_reason(p_reason text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_reason text := tenancy.trim_text(p_reason);
BEGIN
  IF char_length(v_reason) > 500 THEN
    PERFORM tenancy.refuse('reason_length', 'XC422');
  END IF;
  RETURN v_reason;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_typed_reason(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_typed_reason(text) TO xcode_api_executor;
