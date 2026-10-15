-- api.auth_check_code(p_request_id text, p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_replacement_code_hash text, p_device_name text, p_trust boolean, p_device_token_hash text, p_refresh_token_hash text, p_trust_days integer, p_now timestamptz) RETURNS jsonb
-- Purpose: N03, the code step (docs/07-auth.md 12.6): an unknown number answers as the PIN-reset code a stranger could have asked for (tries left, the third code_resent; any other purpose has no code); a wrong code counts and the third voids it and issues a replacement (code_resent, silent past the hourly and daily caps); a first_setup or pin_reset code that matches answers code_verified and is kept for N06; a new_device code that matches clears both lock scopes, trusts the device (remembered with its token when p_trust, else for this session only), logs "Device trusted" when remembered, and signs in.
-- Callers: IdentityRoutines.check_code; the code-step use case (N03).
-- Reads: identity.users, identity.verification_codes, identity.sign_in_attempts, and what identity.policy_for reads. Writes: identity.verification_codes, identity.users (counters, last sign-in, version), identity.trusted_devices, identity.refresh_tokens, identity.sign_in_attempts, and the change log through identity.log_sign_in.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_check_code(
  p_request_id text,
  p_phone text,
  p_device_id text,
  p_purpose text,
  p_code_hash text,
  p_replacement_code_hash text,
  p_device_name text,
  p_trust boolean,
  p_device_token_hash text,
  p_refresh_token_hash text,
  p_trust_days integer,
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
  v_refusal text;
  v_tries integer;
  v_check identity.code_check;
  v_code_id uuid;
  v_policy identity.policy;
  v_trust boolean := coalesce(p_trust, true);
  v_before json;
  v_result jsonb;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);

  -- The simulated reset code of an unknown number: three wrong tries, then a "new" one.
  IF v_user.id IS NULL THEN
    IF p_purpose = 'pin_reset' THEN
      v_tries := identity.unknown_code_tries(v_digest, p_device_id, p_now);
    END IF;
    IF v_tries IS NULL THEN
      PERFORM identity.record_attempt('code', 'refused', 'code_expired', NULL, v_digest, p_device_id, p_now);
      RETURN identity.outcome('refused', '{"refusal": "code_expired"}');
    END IF;
    IF v_tries + 1 >= 3 THEN
      PERFORM identity.record_attempt('code', 'code_resent', 'wrong_code', NULL, v_digest, p_device_id, p_now);
      RETURN identity.outcome('code_resent', jsonb_build_object('refusal', 'wrong_code', 'purpose', p_purpose));
    END IF;
    PERFORM identity.record_attempt('code', 'refused', 'wrong_code', NULL, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object(
      'refusal', 'wrong_code', 'tries_left', 3 - (v_tries + 1)
    ));
  END IF;

  -- Ready: active; new_device and pin_reset need a PIN (new_device also no pending reset);
  -- first_setup needs none.
  IF v_user.status <> 'active' THEN
    v_refusal := 'inactive';
  ELSIF p_purpose IN ('new_device', 'pin_reset') AND v_user.pin_hash IS NULL THEN
    v_refusal := 'no_pin';
  ELSIF p_purpose = 'new_device' AND v_user.pin_reset_required THEN
    v_refusal := 'reset_required';
  END IF;
  IF v_refusal IS NOT NULL
     OR p_purpose IS NULL
     OR p_purpose NOT IN ('first_setup', 'new_device', 'pin_reset')
     OR (p_purpose = 'first_setup' AND v_user.pin_hash IS NOT NULL) THEN
    PERFORM identity.record_attempt('code', 'refused', v_refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object('refusal', v_refusal));
  END IF;

  v_check := identity.matching_code(v_user.id, p_purpose, p_device_id, p_code_hash, p_now);
  IF v_check.code_id IS NULL THEN
    IF v_check.voided THEN
      v_code_id := identity.issue_code(
        v_user.id, p_purpose, p_device_id, p_replacement_code_hash, false, true, p_now
      );
      PERFORM identity.record_attempt('code', 'code_resent', 'wrong_code', v_user.id, v_digest, p_device_id, p_now);
      RETURN identity.outcome('code_resent', jsonb_build_object(
        'refusal', 'wrong_code',
        'purpose', p_purpose,
        'code_issued', v_code_id IS NOT NULL,
        'code_id', v_code_id,
        'email', CASE WHEN v_code_id IS NOT NULL THEN v_user.email END
      ));
    END IF;
    PERFORM identity.record_attempt('code', 'refused', v_check.refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object(
      'refusal', v_check.refusal, 'tries_left', v_check.tries_left
    ));
  END IF;

  IF p_purpose <> 'new_device' THEN
    PERFORM identity.record_attempt('code', 'code_verified', NULL, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('code_verified', jsonb_build_object('purpose', p_purpose));
  END IF;

  v_policy := identity.policy_for(v_user.id);
  IF v_policy.organization_id IS NULL THEN
    PERFORM identity.record_attempt('code', 'refused', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "inactive"}');
  END IF;

  v_before := tenancy.sign_in_snapshot(v_user.id, p_now);
  UPDATE identity.verification_codes SET consumed = true WHERE id = v_check.code_id;
  UPDATE identity.users SET failed_attempts = 0, untrusted_failed_attempts = 0 WHERE id = v_user.id;
  PERFORM identity.trust_device(
    v_user.id, p_device_id, p_device_name, p_device_token_hash, v_trust, p_trust_days, p_now
  );
  v_result := identity.issue_session(v_user.id, p_device_id, p_refresh_token_hash, v_policy, true, p_now);
  PERFORM identity.touch_version(v_user.id);
  IF v_trust THEN
    PERFORM identity.log_sign_in(v_user.id, v_user.id, ARRAY['Device trusted'], v_before, p_now);
  END IF;
  PERFORM identity.record_attempt('code', 'authenticated', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN v_result || jsonb_build_object(
    'device_token_issued', v_trust AND p_device_token_hash IS NOT NULL
  );
END;
$$;
