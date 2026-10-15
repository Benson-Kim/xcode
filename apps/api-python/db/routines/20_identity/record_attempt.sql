-- identity.record_attempt(p_operation text, p_outcome text, p_refusal text, p_user_id uuid, p_phone_digest text, p_device_id text, p_now timestamptz) RETURNS void
-- Purpose: append the one sign-in trail row of an authentication decision, with the current request id.
-- Callers: every api.auth_* decision routine, once per call.
-- Reads: nothing. Writes: identity.sign_in_attempts.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py, tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.record_attempt(
  p_operation text,
  p_outcome text,
  p_refusal text,
  p_user_id uuid,
  p_phone_digest text,
  p_device_id text,
  p_now timestamptz
)
RETURNS void
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  INSERT INTO identity.sign_in_attempts (
    occurred_at, operation, outcome, refusal, user_id, phone_digest, device_id, request_id
  )
  VALUES (
    p_now, p_operation, p_outcome, p_refusal, p_user_id, p_phone_digest,
    coalesce(p_device_id, ''), tenancy.current_request()
  );
$$;

REVOKE ALL ON FUNCTION identity.record_attempt(text, text, text, uuid, text, text, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.record_attempt(text, text, text, uuid, text, text, timestamptz)
  TO xcode_api_executor;
