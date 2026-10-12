-- api.auth_pin(p_request_id text, p_phone text, p_device_id text, p_device_token_hash text, p_pin_ok boolean, p_checked_pin_hash text, p_code_hash text, p_refresh_token_hash text, p_skip_cooldown boolean, p_now timestamptz) RETURNS jsonb
-- Purpose: N02, statement two of the PIN step (docs/07-auth.md 12.3), first match wins: an unknown number is a simulated account (its tries come from the lookup's rows: tries left, then pin_locked at five); blocked; no PIN or a forced reset sends that code; a verdict on a replaced hash is a wrong PIN; locked for this device pin_locked with nothing counted; a wrong PIN counts in its scope (tries left, pin_locked and the change log at five); a right PIN asks an untrusted device for a new-device code and signs a trusted device in.
-- Callers: IdentityRoutines.pin; the PIN-step use case (N02).
-- Reads: identity.users, identity.trusted_devices, identity.verification_codes, identity.sign_in_attempts, and what identity.policy_for reads. Writes: identity.users (counters, last sign-in, version), identity.verification_codes, identity.refresh_tokens, identity.trusted_devices.last_used_at, identity.sign_in_attempts, and the change log through identity.count_wrong_pin.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_pin(
  p_request_id text,
  p_phone text,
  p_device_id text,
  p_device_token_hash text,
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
  v_digest text := identity.phone_digest(coalesce(identity.normalize_phone(p_phone), p_phone));
  v_user identity.users;
  v_policy identity.policy;
  v_tries integer := identity.pin_tries();
  v_count integer;
  v_trusted boolean;
  v_purpose text;
  v_code_id uuid;
  v_result jsonb;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);

  -- The simulated account: the lookup of this request already recorded this try.
  IF v_user.id IS NULL THEN
    v_count := identity.unknown_pin_tries(v_digest);
    IF v_count >= v_tries THEN
      PERFORM identity.record_attempt('pin', 'pin_locked', 'unknown_number', NULL, v_digest, p_device_id, p_now);
      RETURN identity.outcome('pin_locked', '{"refusal": "unknown_number"}');
    END IF;
    PERFORM identity.record_attempt('pin', 'refused', 'unknown_number', NULL, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object(
      'refusal', 'unknown_number', 'tries_left', v_tries - v_count
    ));
  END IF;

  v_policy := identity.policy_for(v_user.id);
  IF v_user.status <> 'active' OR v_policy.organization_id IS NULL THEN
    PERFORM identity.record_attempt('pin', 'blocked', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('blocked', '{"refusal": "inactive"}');
  END IF;

  IF v_user.pin_hash IS NULL OR v_user.pin_reset_required THEN
    v_purpose := CASE WHEN v_user.pin_hash IS NULL THEN 'first_setup' ELSE 'pin_reset' END;
    v_code_id := identity.issue_code(
      v_user.id, v_purpose, p_device_id, p_code_hash, p_skip_cooldown, false, p_now
    );
    PERFORM identity.record_attempt(
      'pin', 'verification_required', CASE WHEN v_user.pin_hash IS NULL THEN 'no_pin' ELSE 'reset_required' END,
      v_user.id, v_digest, p_device_id, p_now
    );
    RETURN identity.outcome('verification_required', jsonb_build_object(
      'purpose', v_purpose,
      'masked_email', identity.mask_email(v_user.email),
      'code_issued', v_code_id IS NOT NULL,
      'code_id', v_code_id,
      'email', CASE WHEN v_code_id IS NOT NULL THEN v_user.email END
    ));
  END IF;

  v_trusted := identity.device_trusted(
    v_user.id, p_device_id, coalesce(p_device_token_hash, ''), p_now
  );
  IF identity.locked_for(v_user, v_trusted) THEN
    PERFORM identity.record_attempt('pin', 'pin_locked', 'locked', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('pin_locked', '{"refusal": "locked"}');
  END IF;

  -- A verdict on a hash replaced since the lookup is a wrong PIN.
  IF NOT coalesce(p_pin_ok AND v_user.pin_hash = p_checked_pin_hash, false) THEN
    v_count := identity.count_wrong_pin(v_user, v_trusted, p_now);
    IF v_count >= v_tries THEN
      PERFORM identity.record_attempt('pin', 'pin_locked', 'wrong_pin', v_user.id, v_digest, p_device_id, p_now);
      RETURN identity.outcome('pin_locked', '{"refusal": "wrong_pin"}');
    END IF;
    PERFORM identity.record_attempt(
      'pin', 'refused', CASE WHEN p_pin_ok THEN 'verdict_void' ELSE 'wrong_pin' END,
      v_user.id, v_digest, p_device_id, p_now
    );
    RETURN identity.outcome('refused', jsonb_build_object(
      'refusal', 'wrong_pin', 'tries_left', v_tries - v_count
    ));
  END IF;

  IF NOT v_trusted THEN
    v_code_id := identity.issue_code(
      v_user.id, 'new_device', p_device_id, p_code_hash, p_skip_cooldown, false, p_now
    );
    PERFORM identity.record_attempt(
      'pin', 'verification_required', NULL, v_user.id, v_digest, p_device_id, p_now
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
  PERFORM identity.record_attempt('pin', 'authenticated', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN v_result;
END;
$$;
