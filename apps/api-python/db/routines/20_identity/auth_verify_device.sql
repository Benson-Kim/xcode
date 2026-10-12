-- api.auth_verify_device(p_request_id text, p_phone text, p_device_id text, p_code_hash text, p_replacement_code_hash text, p_refresh_token_hash text, p_trust_days integer, p_now timestamptz) RETURNS jsonb
-- Purpose: the released A03: check the new-device code (the third wrong try voids it and issues a replacement, mailed after the reply; the answer stays the uniform refusal), then clear both lock scopes, trust the device by its id (a row without a token), log "Device trusted" and sign in (docs/07-auth.md 12.13).
-- Callers: IdentityRoutines.verify_device; the verify-device use case (A03).
-- Reads: identity.users, identity.verification_codes, and what identity.policy_for reads. Writes: identity.verification_codes, identity.users (counters, last sign-in, version), identity.trusted_devices, identity.refresh_tokens, identity.sign_in_attempts, and the change log through identity.log_sign_in.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_verify_device(
  p_request_id text,
  p_phone text,
  p_device_id text,
  p_code_hash text,
  p_replacement_code_hash text,
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
  v_user identity.users;
  v_digest text := identity.phone_digest(coalesce(identity.normalize_phone(p_phone), p_phone));
  v_refusal text;
  v_check identity.code_check;
  v_code_id uuid;
  v_policy identity.policy;
  v_before json;
  v_result jsonb;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);

  IF v_user.id IS NULL THEN
    PERFORM identity.record_attempt('verify_device', 'refused', 'unknown_number', NULL, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "unknown_number"}');
  END IF;
  IF v_user.status <> 'active' THEN
    v_refusal := 'inactive';
  ELSIF v_user.pin_hash IS NULL THEN
    v_refusal := 'no_pin';
  ELSIF v_user.pin_reset_required THEN
    v_refusal := 'reset_required';
  END IF;
  IF v_refusal IS NOT NULL THEN
    PERFORM identity.record_attempt('verify_device', 'refused', v_refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object('refusal', v_refusal));
  END IF;

  v_check := identity.matching_code(v_user.id, 'new_device', p_device_id, p_code_hash, p_now);
  IF v_check.code_id IS NULL THEN
    IF v_check.voided THEN
      v_code_id := identity.issue_code(
        v_user.id, 'new_device', p_device_id, p_replacement_code_hash, false, true, p_now
      );
    END IF;
    PERFORM identity.record_attempt('verify_device', 'refused', v_check.refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object(
      'refusal', v_check.refusal,
      'purpose', CASE WHEN v_check.voided THEN 'new_device' END,
      'code_issued', CASE WHEN v_check.voided THEN v_code_id IS NOT NULL END,
      'code_id', v_code_id,
      'email', CASE WHEN v_code_id IS NOT NULL THEN v_user.email END
    ));
  END IF;

  -- Token eligibility before any state change.
  v_policy := identity.policy_for(v_user.id);
  IF v_policy.organization_id IS NULL THEN
    PERFORM identity.record_attempt('verify_device', 'refused', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "inactive"}');
  END IF;

  v_before := tenancy.sign_in_snapshot(v_user.id, p_now);
  UPDATE identity.verification_codes SET consumed = true WHERE id = v_check.code_id;
  UPDATE identity.users SET failed_attempts = 0, untrusted_failed_attempts = 0 WHERE id = v_user.id;
  PERFORM identity.trust_device(v_user.id, p_device_id, NULL, NULL, true, p_trust_days, p_now);
  v_result := identity.issue_session(v_user.id, p_device_id, p_refresh_token_hash, v_policy, true, p_now);
  PERFORM identity.touch_version(v_user.id);
  PERFORM identity.log_sign_in(v_user.id, v_user.id, ARRAY['Device trusted'], v_before, p_now);
  PERFORM identity.record_attempt('verify_device', 'authenticated', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN v_result;
END;
$$;
