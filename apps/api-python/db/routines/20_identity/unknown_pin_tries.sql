-- identity.unknown_pin_tries(p_phone_digest text) RETURNS integer
-- Purpose: the PIN tries (at most six: the lock and the try past it) recorded for a number that has no account: the lookup's unknown_number rows of that number's digest, one per A01, A02 and N02 try; the simulated account of the number step.
-- Callers: api.auth_start, api.auth_pin.
-- Reads: identity.sign_in_attempts (ix_sign_in_attempts_unknown, at most six rows). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.unknown_pin_tries(p_phone_digest text)
RETURNS integer
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT count(*)::integer
  FROM (
    SELECT 1
    FROM identity.sign_in_attempts AS a
    WHERE a.phone_digest = p_phone_digest
      AND a.user_id IS NULL
      AND a.operation = 'sign_in'
      AND a.refusal = 'unknown_number'
    LIMIT identity.pin_tries() + 1
  ) AS tries;
$$;

REVOKE ALL ON FUNCTION identity.unknown_pin_tries(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.unknown_pin_tries(text) TO xcode_api_executor;
