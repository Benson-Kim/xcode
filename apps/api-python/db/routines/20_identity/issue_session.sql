-- identity.issue_session(p_user_id uuid, p_device_id text, p_refresh_token_hash text, p_policy identity.policy, p_signing_in boolean, p_now timestamptz) RETURNS jsonb
-- Purpose: store the refresh-token digest (expiring after the policy's days), mark the device row used now, and the person signed in now unless this is a refresh (p_signing_in false); return the authenticated outcome with the claim material the service signs.
-- Callers: api.auth_sign_in, api.auth_pin, api.auth_verify_device, api.auth_check_code, api.auth_complete_pin, api.auth_refresh (after token eligibility was checked).
-- Reads: identity.users. Writes: identity.refresh_tokens, identity.trusted_devices.last_used_at, identity.users.last_signed_in_at.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.issue_session(
  p_user_id uuid,
  p_device_id text,
  p_refresh_token_hash text,
  p_policy identity.policy,
  p_signing_in boolean,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_expires_at timestamptz := p_now + make_interval(days => p_policy.refresh_token_days);
  v_security_version integer;
BEGIN
  INSERT INTO identity.refresh_tokens (user_id, device_id, token_hash, expires_at, created_at, updated_at)
  VALUES (p_user_id, p_device_id, p_refresh_token_hash, v_expires_at, p_now, p_now);
  UPDATE identity.trusted_devices
  SET last_used_at = p_now, updated_at = p_now
  WHERE user_id = p_user_id AND device_id = p_device_id;
  IF p_signing_in THEN
    UPDATE identity.users SET last_signed_in_at = p_now WHERE id = p_user_id;
  END IF;

  SELECT u.security_version INTO v_security_version FROM identity.users AS u WHERE u.id = p_user_id;

  RETURN identity.outcome('authenticated', jsonb_build_object(
    'user_id', p_user_id,
    'organization_id', p_policy.organization_id,
    'role', p_policy.role_name,
    'first_name', p_policy.first_name,
    'last_name', p_policy.last_name,
    'permissions', to_jsonb(p_policy.permissions),
    'security_version', v_security_version,
    'access_token_minutes', p_policy.access_token_minutes,
    'refresh_expires_at', v_expires_at
  ));
END;
$$;

REVOKE ALL ON FUNCTION identity.issue_session(uuid, text, text, identity.policy, boolean, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.issue_session(uuid, text, text, identity.policy, boolean, timestamptz)
  TO xcode_api_executor;
