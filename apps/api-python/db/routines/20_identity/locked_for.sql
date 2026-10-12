-- identity.locked_for(p_user identity.users, p_trusted boolean) RETURNS boolean
-- Purpose: whether the PIN is locked for this device: five wrong PINs in a row from trusted devices lock every device; five from untrusted devices lock untrusted devices only.
-- Callers: api.auth_start, api.auth_pin, api.auth_sign_in.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.locked_for(p_user identity.users, p_trusted boolean)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN p_user.failed_attempts >= identity.pin_tries()
      OR (NOT p_trusted AND p_user.untrusted_failed_attempts >= identity.pin_tries());
END;
$$;

REVOKE ALL ON FUNCTION identity.locked_for(identity.users, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.locked_for(identity.users, boolean) TO xcode_api_executor;
