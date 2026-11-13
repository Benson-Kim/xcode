-- tenancy.sign_in_notice_sends() RETURNS integer
-- Purpose: how many times one sign-in notice is sent before it is given up as failed: 5.
-- Callers: api.sign_in_notice_result, api.sign_in_notice_claim.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_sign_in_notices.py.

CREATE OR REPLACE FUNCTION tenancy.sign_in_notice_sends()
RETURNS integer
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT 5;
$$;

REVOKE ALL ON FUNCTION tenancy.sign_in_notice_sends() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.sign_in_notice_sends() TO xcode_api_executor;
