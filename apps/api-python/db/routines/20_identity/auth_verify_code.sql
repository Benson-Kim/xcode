-- api.auth_verify_code(p_request_id text, p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_replacement_code_hash text, p_now timestamptz) RETURNS jsonb
-- Purpose: the released A05/A08: check a first_setup or pin_reset code without consuming it (code_verified), or refuse; the third wrong try voids it and issues a replacement, mailed after the reply, while the answer stays the uniform refusal (docs/07-auth.md 12.6).
-- Callers: IdentityRoutines.verify_code; the setup-pin and pin-reset verify use cases (A05, A08).
-- Reads: identity.users, identity.verification_codes. Writes: identity.verification_codes (failed tries, the replacement), identity.sign_in_attempts.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_verify_code(
  p_request_id text,
  p_phone text,
  p_device_id text,
  p_purpose text,
  p_code_hash text,
  p_replacement_code_hash text,
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
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);

  IF v_user.id IS NULL THEN
    PERFORM identity.record_attempt('verify_code', 'refused', 'unknown_number', NULL, v_digest, p_device_id, p_now);
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
    PERFORM identity.record_attempt('verify_code', 'refused', v_refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object('refusal', v_refusal));
  END IF;

  v_check := identity.matching_code(v_user.id, p_purpose, p_device_id, p_code_hash, p_now);
  IF v_check.code_id IS NULL THEN
    IF v_check.voided THEN
      v_code_id := identity.issue_code(
        v_user.id, p_purpose, p_device_id, p_replacement_code_hash, false, true, p_now
      );
    END IF;
    PERFORM identity.record_attempt('verify_code', 'refused', v_check.refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object(
      'refusal', v_check.refusal,
      'purpose', CASE WHEN v_check.voided THEN p_purpose END,
      'code_issued', CASE WHEN v_check.voided THEN v_code_id IS NOT NULL END,
      'code_id', v_code_id,
      'email', CASE WHEN v_code_id IS NOT NULL THEN v_user.email END
    ));
  END IF;

  PERFORM identity.record_attempt('verify_code', 'code_verified', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN identity.outcome('code_verified', jsonb_build_object('purpose', p_purpose));
END;
$$;
