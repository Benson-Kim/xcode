-- api.auth_complete_pin(p_request_id text, p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_new_pin_is_current boolean, p_checked_pin_hash text, p_pin_hash text, p_device_name text, p_trust boolean, p_device_token_hash text, p_refresh_token_hash text, p_trust_days integer, p_now timestamptz) RETURNS jsonb
-- Purpose: A06, A09 and N06: with a valid code, set the new PIN (a reset refuses the PIN being replaced as invalid_pin "unchanged" with the code kept, and a verdict on a hash replaced since the lookup with nothing changed), end every session and code, clear both lock scopes and a forced reset, remove every device on a reset, trust this device (remembered with its token unless p_trust is false; the released routes pass true and no token), log the PIN event and sign in (docs/07-auth.md 12.4, 12.9).
-- Callers: IdentityRoutines.complete_pin; the PIN completion use cases (A06, A09, N06).
-- Reads: identity.users, identity.verification_codes, identity.trusted_devices, and what identity.policy_for reads. Writes: identity.verification_codes, identity.users (PIN, counters, forced reset, security version, last sign-in, version), identity.refresh_tokens, identity.trusted_devices, identity.sign_in_attempts, and the change log through identity.log_sign_in.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_complete_pin(
  p_request_id text,
  p_phone text,
  p_device_id text,
  p_purpose text,
  p_code_hash text,
  p_new_pin_is_current boolean,
  p_checked_pin_hash text,
  p_pin_hash text,
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
  v_user identity.users;
  v_digest text := identity.phone_digest(coalesce(identity.normalize_phone(p_phone), p_phone));
  v_refusal text;
  v_check identity.code_check;
  v_policy identity.policy;
  v_trust boolean := coalesce(p_trust, true);
  v_before json;
  v_result jsonb;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);

  IF v_user.id IS NULL THEN
    PERFORM identity.record_attempt('complete_pin', 'refused', 'unknown_number', NULL, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "unknown_number"}');
  END IF;

  IF v_user.status <> 'active' THEN
    v_refusal := 'inactive';
  ELSIF p_purpose = 'pin_reset' AND v_user.pin_hash IS NULL THEN
    v_refusal := 'no_pin';
  END IF;
  IF v_refusal IS NOT NULL
     OR p_purpose IS NULL
     OR p_purpose NOT IN ('first_setup', 'pin_reset')
     OR (p_purpose = 'first_setup' AND v_user.pin_hash IS NOT NULL) THEN
    PERFORM identity.record_attempt('complete_pin', 'refused', v_refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object('refusal', v_refusal));
  END IF;

  -- The code as in verify-code: a wrong one counts a try, the third voids it.
  v_check := identity.matching_code(v_user.id, p_purpose, p_device_id, p_code_hash, p_now);
  IF v_check.code_id IS NULL THEN
    PERFORM identity.record_attempt('complete_pin', 'refused', v_check.refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object('refusal', v_check.refusal));
  END IF;

  -- The PIN being replaced is refused only to someone holding a valid code; the code is kept.
  IF p_purpose = 'pin_reset' THEN
    IF p_checked_pin_hash IS DISTINCT FROM v_user.pin_hash THEN
      PERFORM identity.record_attempt('complete_pin', 'refused', 'verdict_void', v_user.id, v_digest, p_device_id, p_now);
      RETURN identity.outcome('refused', '{"refusal": "verdict_void"}');
    END IF;
    IF p_new_pin_is_current THEN
      PERFORM identity.record_attempt('complete_pin', 'refused', 'pin_rule', v_user.id, v_digest, p_device_id, p_now);
      RETURN identity.outcome('invalid_pin', jsonb_build_object(
        'refusal', 'pin_rule', 'pin_problem', 'unchanged', 'minimum_pin_length', 4
      ));
    END IF;
  END IF;

  -- Token eligibility before any state change.
  v_policy := identity.policy_for(v_user.id);
  IF v_policy.organization_id IS NULL THEN
    PERFORM identity.record_attempt('complete_pin', 'refused', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "inactive"}');
  END IF;

  v_before := tenancy.sign_in_snapshot(v_user.id, p_now);
  UPDATE identity.verification_codes SET consumed = true WHERE id = v_check.code_id;
  -- A new PIN ends every outstanding access token, both lock scopes and a forced reset.
  UPDATE identity.users
  SET pin_hash = p_pin_hash,
      untrusted_failed_attempts = 0,
      failed_attempts = 0,
      pin_reset_required = false,
      security_version = security_version + 1
  WHERE id = v_user.id;
  IF p_purpose = 'pin_reset' THEN
    PERFORM identity.remove_devices(v_user.id, p_now);
  ELSE
    PERFORM identity.revoke_tokens(v_user.id);
    UPDATE identity.verification_codes SET consumed = true WHERE user_id = v_user.id AND NOT consumed;
  END IF;
  PERFORM identity.trust_device(
    v_user.id, p_device_id, p_device_name, p_device_token_hash, v_trust, p_trust_days, p_now
  );
  v_result := identity.issue_session(v_user.id, p_device_id, p_refresh_token_hash, v_policy, true, p_now);
  PERFORM identity.touch_version(v_user.id);
  PERFORM identity.log_sign_in(
    v_user.id,
    v_user.id,
    ARRAY[CASE WHEN p_purpose = 'first_setup' THEN 'PIN set at first sign in' ELSE 'PIN reset with a code' END]
      || CASE WHEN v_trust THEN ARRAY['Device trusted'] ELSE '{}'::text[] END,
    v_before,
    p_now
  );
  PERFORM identity.record_attempt('complete_pin', 'authenticated', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN v_result || jsonb_build_object(
    'device_token_issued', v_trust AND p_device_token_hash IS NOT NULL
  );
END;
$$;
