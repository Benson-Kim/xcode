-- api.auth_request_code(p_request_id text, p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_skip_cooldown boolean, p_now timestamptz) RETURNS jsonb
-- Purpose: A04, A07 and N05: issue a first_setup or pin_reset code when the account is ready (active; first_setup without a PIN, pin_reset with one) and the per-person caps allow (identity.issue_code): check_email with the stored address, else silent; no lock or device check, so a locked person may reset. A pin_reset request is recorded as forgot_pin, a first_setup one as request_code.
-- Callers: IdentityRoutines.request_code; the code request use cases (A04, A07, N05).
-- Reads: identity.users, identity.verification_codes. Writes: identity.verification_codes (supersede, insert), identity.sign_in_attempts.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_request_code(
  p_request_id text,
  p_phone text,
  p_device_id text,
  p_purpose text,
  p_code_hash text,
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
  v_digest text := identity.phone_digest(coalesce(identity.normalize_phone(p_phone), p_phone));
  v_operation text := CASE WHEN p_purpose = 'pin_reset' THEN 'forgot_pin' ELSE 'request_code' END;
  v_refusal text;
  v_code_id uuid;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);

  IF v_user.id IS NULL THEN
    PERFORM identity.record_attempt(v_operation, 'check_email', 'unknown_number', NULL, v_digest, p_device_id, p_now);
    RETURN identity.outcome('silent', jsonb_build_object('refusal', 'unknown_number', 'purpose', p_purpose));
  END IF;

  IF v_user.status <> 'active' THEN
    v_refusal := 'inactive';
  ELSIF p_purpose = 'pin_reset' AND v_user.pin_hash IS NULL THEN
    v_refusal := 'no_pin';
  END IF;
  IF v_refusal IS NULL
     AND p_purpose IN ('first_setup', 'pin_reset')
     AND NOT (p_purpose = 'first_setup' AND v_user.pin_hash IS NOT NULL) THEN
    v_code_id := identity.issue_code(
      v_user.id, p_purpose, p_device_id, p_code_hash, p_skip_cooldown, false, p_now
    );
  END IF;
  IF v_code_id IS NULL THEN
    PERFORM identity.record_attempt(v_operation, 'check_email', v_refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('silent', jsonb_build_object('refusal', v_refusal, 'purpose', p_purpose));
  END IF;

  PERFORM identity.record_attempt(v_operation, 'check_email', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN identity.outcome('check_email', jsonb_build_object(
    'purpose', p_purpose,
    'code_issued', true,
    'code_id', v_code_id,
    'email', v_user.email
  ));
END;
$$;
