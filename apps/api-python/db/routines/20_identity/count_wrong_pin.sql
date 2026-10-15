-- identity.count_wrong_pin(p_user identity.users, p_trusted boolean, p_now timestamptz) RETURNS integer
-- Purpose: count one wrong PIN in its scope (trusted devices: failed_attempts; untrusted: untrusted_failed_attempts) and return the new count; the try that brings the count to five starts the lock and writes "PIN locked after 5 wrong tries" to the change log.
-- Callers: api.auth_sign_in, api.auth_pin, api.auth_change_pin (after identity.lock_user).
-- Reads: identity.users, and what tenancy.sign_in_snapshot and identity.log_sign_in read. Writes: identity.users (counter, version), and what identity.log_sign_in writes.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.count_wrong_pin(
  p_user identity.users,
  p_trusted boolean,
  p_now timestamptz
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_before json;
  v_count integer;
BEGIN
  v_count := CASE WHEN p_trusted THEN p_user.failed_attempts ELSE p_user.untrusted_failed_attempts END;
  IF v_count + 1 >= identity.pin_tries() THEN
    v_before := tenancy.sign_in_snapshot(p_user.id, p_now);
  END IF;
  IF p_trusted THEN
    UPDATE identity.users
    SET failed_attempts = least(failed_attempts + 1, identity.pin_tries())
    WHERE id = p_user.id
    RETURNING failed_attempts INTO v_count;
  ELSE
    UPDATE identity.users
    SET untrusted_failed_attempts = least(untrusted_failed_attempts + 1, identity.pin_tries())
    WHERE id = p_user.id
    RETURNING untrusted_failed_attempts INTO v_count;
  END IF;
  PERFORM identity.touch_version(p_user.id);
  IF v_before IS NOT NULL THEN
    PERFORM identity.log_sign_in(
      p_user.id, p_user.id, ARRAY['PIN locked after 5 wrong tries'], v_before, p_now
    );
  END IF;
  RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION identity.count_wrong_pin(identity.users, boolean, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.count_wrong_pin(identity.users, boolean, timestamptz) TO xcode_api_executor;
