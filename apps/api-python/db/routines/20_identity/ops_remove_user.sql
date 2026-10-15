-- api.ops_remove_user(p_operator text, p_request_id text, p_email text, p_now timestamptz) RETURNS jsonb
-- Purpose: mark a user removed (security version bumped, so every access token stops) and revoke every refresh token; devices and membership are left as they are.
-- Callers: OpsRoutines.remove_user; CLI remove-user.
-- Reads: identity.users. Writes: ops.operator_actions, identity.users (status, security version, version), identity.refresh_tokens.
-- Raises: XC404 not_found.
-- Tests: tests/db/test_ops_routines.py, tests/api/test_cli.py.

CREATE OR REPLACE FUNCTION api.ops_remove_user(
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
  v_removed boolean;
  v_tokens integer;
BEGIN
  PERFORM ops.record_operator_action(
    p_operator, 'remove-user', v_email, jsonb_build_object('request_id', p_request_id), p_now
  );
  SELECT u.id INTO v_user_id FROM identity.users AS u WHERE u.email = v_email;
  IF v_user_id IS NULL THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_user := identity.lock_user(v_user_id);
  v_removed := v_user.status = 'active';
  IF v_removed THEN
    UPDATE identity.users
    SET status = 'removed', security_version = security_version + 1
    WHERE id = v_user.id;
    PERFORM identity.touch_version(v_user.id);
  END IF;
  v_tokens := identity.revoke_tokens(v_user.id);
  RETURN jsonb_build_object('user_id', v_user.id, 'removed', v_removed, 'tokens', v_tokens);
END;
$$;
