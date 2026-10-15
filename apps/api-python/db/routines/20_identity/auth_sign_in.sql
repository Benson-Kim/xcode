-- api.auth_sign_in(p_request_id text, p_user_id uuid, p_device_id text, p_pin_ok boolean, p_checked_pin_hash text, p_code_hash text, p_refresh_token_hash text, p_skip_cooldown boolean, p_now timestamptz) RETURNS jsonb
-- Purpose: statement two of the released A01/A02: record the service's PIN verdict (void when the stored hash changed since the lookup) and decide under the v2.33 lock (docs/07-auth.md 12.13 and 12.5): a pending forced reset and a lock are refused with nothing counted; a wrong PIN counts in its scope and the fifth from a trusted device answers paused; a right PIN asks an untrusted device for a new-device code and signs a device trusted by its id in.
-- Callers: IdentityRoutines.sign_in; the sign-in use case (A01, A02).
-- Reads: identity.users, identity.trusted_devices, identity.verification_codes, and what identity.policy_for reads. Writes: identity.users (counters, last sign-in, version), identity.verification_codes, identity.refresh_tokens, identity.trusted_devices.last_used_at, identity.sign_in_attempts, and the change log through identity.count_wrong_pin.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_sign_in(
  p_request_id text,
  p_user_id uuid,
  p_device_id text,
  p_pin_ok boolean,
  p_checked_pin_hash text,
  p_code_hash text,
  p_refresh_token_hash text,
  p_skip_cooldown boolean,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_user identity.users;
  v_digest text;
  v_pin_ok boolean;
  v_trusted boolean;
  v_policy identity.policy;
  v_pause integer;
  v_count integer;
  v_code_id uuid;
  v_result jsonb;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  IF p_user_id IS NOT NULL THEN
    v_user := identity.lock_user(p_user_id);
  END IF;

  -- No account (the lookup found none), removed, no PIN, or a forced reset pending.
  IF v_user.id IS NULL THEN
    PERFORM pg_advisory_xact_lock(hashtext('device:' || coalesce(p_device_id, '')));
    PERFORM identity.record_attempt(
      'sign_in', 'refused', 'unknown_number', NULL, identity.phone_digest(NULL), p_device_id, p_now
    );
    RETURN identity.outcome('refused', '{"refusal": "unknown_number"}');
  END IF;
  v_digest := identity.phone_digest(v_user.phone_number);
  IF v_user.status <> 'active' THEN
    PERFORM identity.record_attempt('sign_in', 'refused', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "inactive"}');
  END IF;
  IF v_user.pin_hash IS NULL THEN
    PERFORM identity.record_attempt('sign_in', 'refused', 'no_pin', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "no_pin"}');
  END IF;
  IF v_user.pin_reset_required THEN
    PERFORM identity.record_attempt('sign_in', 'refused', 'reset_required', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "reset_required"}');
  END IF;

  -- The verdict holds only for the hash the service checked: a PIN set or reset that
  -- committed after the lookup turns it into a wrong PIN.
  v_pin_ok := coalesce(p_pin_ok AND v_user.pin_hash = p_checked_pin_hash, false);
  -- The released routes trust a device by its id alone: a row without a token.
  v_trusted := identity.device_trusted(v_user.id, p_device_id, NULL, p_now);
  -- A locked PIN shows a released phone its paused screen, which offers the reset.
  v_policy := identity.policy_for(v_user.id);
  v_pause := coalesce(v_policy.lockout_minutes, 15) * 60;

  IF identity.locked_for(v_user, v_trusted) THEN
    IF v_trusted THEN
      PERFORM identity.record_attempt('sign_in', 'paused', 'locked', v_user.id, v_digest, p_device_id, p_now);
      RETURN identity.outcome('paused', jsonb_build_object(
        'refusal', 'locked', 'retry_after_seconds', v_pause
      ));
    END IF;
    PERFORM identity.record_attempt('sign_in', 'refused', 'locked', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "locked"}');
  END IF;

  IF NOT v_pin_ok THEN
    v_count := identity.count_wrong_pin(v_user, v_trusted, p_now);
    IF v_trusted AND v_count >= identity.pin_tries() THEN
      PERFORM identity.record_attempt('sign_in', 'paused', 'wrong_pin', v_user.id, v_digest, p_device_id, p_now);
      RETURN identity.outcome('paused', jsonb_build_object(
        'refusal', 'wrong_pin', 'retry_after_seconds', v_pause
      ));
    END IF;
    PERFORM identity.record_attempt('sign_in', 'refused', 'wrong_pin', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "wrong_pin"}');
  END IF;

  -- A code or tokens follow: token eligibility first, with nothing changed yet.
  IF v_policy.organization_id IS NULL THEN
    PERFORM identity.record_attempt('sign_in', 'refused', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "inactive"}');
  END IF;

  IF NOT v_trusted THEN
    v_code_id := identity.issue_code(
      v_user.id, 'new_device', p_device_id, p_code_hash, p_skip_cooldown, false, p_now
    );
    PERFORM identity.record_attempt(
      'sign_in', 'verification_required', NULL, v_user.id, v_digest, p_device_id, p_now
    );
    RETURN identity.outcome('verification_required', jsonb_build_object(
      'purpose', 'new_device',
      'masked_email', identity.mask_email(v_user.email),
      'code_issued', v_code_id IS NOT NULL,
      'code_id', v_code_id,
      'email', CASE WHEN v_code_id IS NOT NULL THEN v_user.email END
    ));
  END IF;

  UPDATE identity.users SET failed_attempts = 0 WHERE id = v_user.id AND failed_attempts <> 0;
  v_result := identity.issue_session(v_user.id, p_device_id, p_refresh_token_hash, v_policy, true, p_now);
  PERFORM identity.touch_version(v_user.id);
  PERFORM identity.record_attempt('sign_in', 'authenticated', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN v_result;
END;
$$;
