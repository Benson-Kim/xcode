-- identity.invitation_tries() RETURNS integer
-- Purpose: the wrong invitation codes that void the invitation's code (5); the link keeps working.
-- Callers: identity.usable_invitation, identity.matching_code.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION identity.invitation_tries()
RETURNS integer
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT 5;
$$;

REVOKE ALL ON FUNCTION identity.invitation_tries() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.invitation_tries() TO xcode_api_executor;
