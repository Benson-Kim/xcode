-- identity.phone_digest(p_value text) RETURNS text
-- Purpose: the SHA-256 hex digest the sign-in trail stores instead of a phone number (of the normalised number, or of the raw input when it does not normalise).
-- Callers: identity.lock_account and the api.auth_* routines.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.phone_digest(p_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT encode(sha256(convert_to(coalesce(p_value, ''), 'UTF8')), 'hex');
$$;

REVOKE ALL ON FUNCTION identity.phone_digest(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.phone_digest(text) TO xcode_api_executor;
