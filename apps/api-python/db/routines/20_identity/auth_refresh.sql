-- api.auth_refresh(p_request_id text, p_token_hash text, p_device_id text, p_new_token_hash text, p_now timestamptz) RETURNS jsonb
-- Purpose: A10: rotate a refresh token with freshly read claims; a replayed token revokes the device's live tokens, an inactive user's every token; refused while the PIN is locked on every device or the device row is not live (unused for 90 days, revoked, expired); a rotation marks the device used (docs/07-auth.md section 3.6, 12.13).
-- Callers: IdentityRoutines.refresh; the refresh use case (A10).
-- Reads: identity.refresh_tokens, identity.users, identity.trusted_devices, and what identity.policy_for reads. Writes: identity.refresh_tokens (revoke, insert), identity.trusted_devices.last_used_at, identity.users.version, identity.sign_in_attempts.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_refresh(
  p_request_id text,
  p_token_hash text,
  p_device_id text,
  p_new_token_hash text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_token identity.refresh_tokens;
  v_user identity.users;
  v_digest text;
  v_policy identity.policy;
  v_result jsonb;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  SELECT t.* INTO v_token FROM identity.refresh_tokens AS t WHERE t.token_hash = p_token_hash;

  -- Unknown token, or presented from another device: nothing written.
  IF v_token.id IS NULL OR v_token.device_id <> p_device_id THEN
    PERFORM pg_advisory_xact_lock(hashtext('device:' || coalesce(p_device_id, '')));
    PERFORM identity.record_attempt(
      'refresh', 'refused', 'token_unknown', v_token.user_id,
      identity.phone_digest((SELECT u.phone_number FROM identity.users AS u WHERE u.id = v_token.user_id)),
      p_device_id, p_now
    );
    RETURN identity.outcome('refused', '{"refusal": "token_unknown"}');
  END IF;

  -- Lock the account, then read the token again: a concurrent rotation may have revoked it.
  v_user := identity.lock_user(v_token.user_id);
  SELECT t.* INTO v_token FROM identity.refresh_tokens AS t WHERE t.id = v_token.id FOR UPDATE;
  v_digest := identity.phone_digest(v_user.phone_number);

  IF v_user.status <> 'active' THEN
    PERFORM identity.revoke_tokens(v_user.id);
    PERFORM identity.record_attempt('refresh', 'refused', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "inactive"}');
  END IF;
  IF v_token.revoked THEN
    -- Replay: every live token of the user on this device dies; the device stays trusted.
    PERFORM identity.revoke_tokens(v_user.id, p_device_id);
    PERFORM identity.record_attempt('refresh', 'refused', 'token_replayed', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "token_replayed"}');
  END IF;
  IF p_now >= v_token.expires_at THEN
    PERFORM identity.record_attempt('refresh', 'refused', 'token_expired', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "token_expired"}');
  END IF;
  IF v_user.failed_attempts >= identity.pin_tries() THEN
    PERFORM identity.record_attempt('refresh', 'refused', 'locked', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "locked"}');
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM identity.trusted_devices AS d
    WHERE d.user_id = v_user.id AND d.device_id = p_device_id AND identity.device_live(d, p_now)
  ) THEN
    PERFORM identity.record_attempt('refresh', 'refused', 'device_untrusted', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "device_untrusted"}');
  END IF;

  -- Token eligibility before any state change.
  v_policy := identity.policy_for(v_user.id);
  IF v_policy.organization_id IS NULL THEN
    PERFORM identity.record_attempt('refresh', 'refused', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "inactive"}');
  END IF;

  UPDATE identity.refresh_tokens SET revoked = true, version = version + 1 WHERE id = v_token.id;
  v_result := identity.issue_session(v_user.id, p_device_id, p_new_token_hash, v_policy, false, p_now);
  PERFORM identity.touch_version(v_user.id);
  PERFORM identity.record_attempt('refresh', 'authenticated', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN v_result;
END;
$$;
