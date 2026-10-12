-- api.ops_revoke_sessions(p_operator text, p_request_id text, p_email text, p_now timestamptz) RETURNS jsonb
-- Purpose: end every session of a user: security version bumped, every trusted device and refresh token revoked; the next sign-in needs an email code.
-- Callers: OpsRoutines.revoke_sessions; CLI revoke-sessions.
-- Reads: identity.users. Writes: ops.operator_actions, identity.users (security version, version), identity.trusted_devices, identity.refresh_tokens.
-- Raises: XC404 not_found.
-- Tests: tests/db/test_ops_routines.py, tests/api/test_cli.py.

CREATE OR REPLACE FUNCTION api.ops_revoke_sessions(
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
  v_devices integer;
  v_tokens integer;
BEGIN
  PERFORM ops.record_operator_action(
    p_operator, 'revoke-sessions', v_email, jsonb_build_object('request_id', p_request_id), p_now
  );
  SELECT u.id INTO v_user_id FROM identity.users AS u WHERE u.email = v_email;
  IF v_user_id IS NULL THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  PERFORM identity.lock_user(v_user_id);
  UPDATE identity.users SET security_version = security_version + 1 WHERE id = v_user_id;
  v_devices := identity.revoke_devices(v_user_id);
  v_tokens := identity.revoke_tokens(v_user_id);
  PERFORM identity.touch_version(v_user_id);
  RETURN jsonb_build_object('user_id', v_user_id, 'devices', v_devices, 'tokens', v_tokens);
END;
$$;
