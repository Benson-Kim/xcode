-- api.auth_sign_out(p_request_id text, p_token_hash text, p_device_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: A11: when a token matches both the digest and the device, revoke every live token of that user on that device, and the device row too when it was trusted for that session only (not remembered); always signed_out (a remembered device and access tokens untouched).
-- Callers: IdentityRoutines.sign_out; the sign-out use case (A11).
-- Reads: identity.refresh_tokens, identity.users. Writes: identity.refresh_tokens (revoke), identity.trusted_devices (a device not remembered), identity.sign_in_attempts.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_sign_out(
  p_request_id text,
  p_token_hash text,
  p_device_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_user_id uuid;
  v_user identity.users;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  SELECT t.user_id INTO v_user_id
  FROM identity.refresh_tokens AS t
  WHERE t.token_hash = p_token_hash AND t.device_id = p_device_id;

  IF v_user_id IS NULL THEN
    PERFORM pg_advisory_xact_lock(hashtext('device:' || coalesce(p_device_id, '')));
    PERFORM identity.record_attempt(
      'sign_out', 'signed_out', 'token_unknown', NULL, identity.phone_digest(NULL), p_device_id, p_now
    );
    RETURN identity.outcome('signed_out', '{"refusal": "token_unknown"}');
  END IF;

  v_user := identity.lock_user(v_user_id);
  PERFORM identity.revoke_tokens(v_user.id, p_device_id);
  UPDATE identity.trusted_devices
  SET revoked = true, updated_at = p_now
  WHERE user_id = v_user.id AND device_id = p_device_id AND NOT remembered AND NOT revoked;
  PERFORM identity.record_attempt(
    'sign_out', 'signed_out', NULL, v_user.id, identity.phone_digest(v_user.phone_number), p_device_id, p_now
  );
  RETURN identity.outcome('signed_out');
END;
$$;
