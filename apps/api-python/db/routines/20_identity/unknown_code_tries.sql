-- identity.unknown_code_tries(p_phone_digest text, p_device_id text, p_now timestamptz) RETURNS integer
-- Purpose: the wrong tries on the simulated PIN-reset code of a number that has no account (a real account with a PIN can only hold a reset code a stranger asked for): NULL when no such code would be live on this device (no forgot_pin row, from A07 or N05, and no code_resent row of the digest and device in the last 10 minutes), else the wrong code rows of the device recorded after the newest of them; per device, as a real code is.
-- Callers: api.auth_check_code.
-- Reads: identity.sign_in_attempts (ix_sign_in_attempts_unknown). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.unknown_code_tries(
  p_phone_digest text,
  p_device_id text,
  p_now timestamptz
)
RETURNS integer
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH issued AS (
    SELECT max(a.id) AS id
    FROM identity.sign_in_attempts AS a
    WHERE a.phone_digest = p_phone_digest
      AND a.user_id IS NULL
      AND a.device_id = p_device_id
      AND a.occurred_at >= p_now - interval '10 minutes'
      AND (
        a.operation = 'forgot_pin'
        OR (a.operation = 'code' AND a.outcome = 'code_resent')
      )
  )
  SELECT CASE
           WHEN issued.id IS NULL THEN NULL
           ELSE (
             SELECT count(*)::integer
             FROM identity.sign_in_attempts AS a
             WHERE a.phone_digest = p_phone_digest
               AND a.user_id IS NULL
               AND a.device_id = p_device_id
               AND a.id > issued.id
               AND a.operation = 'code'
               AND a.refusal = 'wrong_code'
           )
         END
  FROM issued;
$$;

REVOKE ALL ON FUNCTION identity.unknown_code_tries(text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.unknown_code_tries(text, text, timestamptz) TO xcode_api_executor;
