-- api.ops_account_state(p_operator text, p_request_id text, p_email text, p_now timestamptz) RETURNS jsonb
-- Purpose: what a support call needs about an account: status, whether a PIN is set, a pending forced reset, the sign-in status, the last sign-in, both lock counters, live remembered device and live-token counts, whether a membership is active; never a hash or digest.
-- Callers: OpsRoutines.account_state; CLI account-state.
-- Reads: identity.users, identity.trusted_devices, identity.refresh_tokens, tenancy.memberships. Writes: ops.operator_actions.
-- Raises: XC404 not_found.
-- Tests: tests/db/test_ops_routines.py, tests/api/test_cli.py.

CREATE OR REPLACE FUNCTION api.ops_account_state(
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
  v_user identity.users;
BEGIN
  PERFORM ops.record_operator_action(
    p_operator, 'account-state', v_email, jsonb_build_object('request_id', p_request_id), p_now
  );
  SELECT u.* INTO v_user FROM identity.users AS u WHERE u.email = v_email;
  IF v_user.id IS NULL THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  RETURN jsonb_build_object(
    'user_id', v_user.id,
    'status', v_user.status,
    'has_pin', v_user.pin_hash IS NOT NULL,
    'pin_reset_required', v_user.pin_reset_required,
    'sign_in_status', identity.sign_in_status(v_user, identity.active_organization(v_user.id) IS NOT NULL),
    'last_signed_in_at', v_user.last_signed_in_at,
    'failed_attempts', v_user.failed_attempts,
    'untrusted_failed_attempts', v_user.untrusted_failed_attempts,
    'trusted_devices', (
      SELECT count(*)
      FROM identity.trusted_devices AS d
      WHERE d.user_id = v_user.id AND d.remembered AND identity.device_live(d, p_now)
    ),
    'live_refresh_tokens', (
      SELECT count(*)
      FROM identity.refresh_tokens AS t
      WHERE t.user_id = v_user.id AND NOT t.revoked AND p_now < t.expires_at
    ),
    'active_membership', identity.active_organization(v_user.id) IS NOT NULL
  );
END;
$$;
