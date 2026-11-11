-- identity.invitation_sends() RETURNS integer
-- Purpose: the delivery attempts after which an unsent invitation is marked failed instead of tried again (5).
-- Callers: api.invite_delivery_result, api.invite_claim_undelivered.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION identity.invitation_sends()
RETURNS integer
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT 5;
$$;

REVOKE ALL ON FUNCTION identity.invitation_sends() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.invitation_sends() TO xcode_api_executor;
