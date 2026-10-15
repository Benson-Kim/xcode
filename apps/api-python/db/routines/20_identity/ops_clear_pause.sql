-- api.ops_clear_pause(p_operator text, p_request_id text, p_email text, p_now timestamptz) RETURNS jsonb
-- Purpose: lift a wrong-PIN lock for a person who cannot get a code: clear both scopes (every device and new devices); {user_id, was_locked}.
-- Callers: OpsRoutines.clear_pause; CLI clear-pause.
-- Reads: identity.users. Writes: ops.operator_actions, identity.users (both counters, version).
-- Raises: XC404 not_found.
-- Tests: tests/db/test_ops_routines.py, tests/api/test_cli.py.

CREATE OR REPLACE FUNCTION api.ops_clear_pause(
  p_operator text,
  p_request_id text,
  p_email text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_email text := lower(tenancy.trim_text(p_email));
  v_user_id uuid;
  v_user identity.users;
BEGIN
  PERFORM ops.record_operator_action(
    p_operator, 'clear-pause', v_email, jsonb_build_object('request_id', p_request_id), p_now
  );
  SELECT u.id INTO v_user_id FROM identity.users AS u WHERE u.email = v_email;
  IF v_user_id IS NULL THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_user := identity.lock_user(v_user_id);
  IF v_user.failed_attempts <> 0 OR v_user.untrusted_failed_attempts <> 0 THEN
    UPDATE identity.users SET failed_attempts = 0, untrusted_failed_attempts = 0 WHERE id = v_user.id;
    PERFORM identity.touch_version(v_user.id);
  END IF;
  RETURN jsonb_build_object(
    'user_id', v_user.id,
    'was_locked', v_user.failed_attempts >= identity.pin_tries()
      OR v_user.untrusted_failed_attempts >= identity.pin_tries()
  );
END;
$$;
