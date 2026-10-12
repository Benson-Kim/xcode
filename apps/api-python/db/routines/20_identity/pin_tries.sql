-- identity.pin_tries() RETURNS integer
-- Purpose: the wrong PINs in a row that lock a scope (5); the twin of domain.policies.PIN_TRIES, parity-tested.
-- Callers: identity.locked_for, identity.count_wrong_pin, identity.unknown_pin_tries, identity.sign_in_status and the api.auth_* routines that answer tries left.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.pin_tries()
RETURNS integer
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT 5;
$$;

REVOKE ALL ON FUNCTION identity.pin_tries() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.pin_tries() TO xcode_api_executor;
