-- tenancy.refuse(p_code text, p_sqlstate text DEFAULT 'XC422', p_detail jsonb DEFAULT '{}') RETURNS void
-- Purpose: raise a business refusal with its stable code and JSON detail; the only RAISE site for refusals.
-- Callers: every routine and helper that refuses.
-- Reads: nothing. Writes: nothing.
-- Raises: the caller's SQLSTATE and code.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.refuse(
  p_code text,
  p_sqlstate text DEFAULT 'XC422',
  p_detail jsonb DEFAULT '{}'
)
RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RAISE EXCEPTION USING
    ERRCODE = p_sqlstate,
    MESSAGE = p_code,
    DETAIL = coalesce(p_detail, '{}'::jsonb)::text;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.refuse(text, text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.refuse(text, text, jsonb) TO xcode_api_executor;
