-- api.auth_start(p_request_id text, p_phone text, p_device_id text, p_device_token_hash text, p_code_hash text, p_skip_cooldown boolean, p_now timestamptz) RETURNS jsonb
-- Purpose: N01, the number step (docs/07-auth.md 12.2), first match wins: an unknown number answers as a simulated account with a PIN (pin_locked past five recorded tries, else pin_required); a blocked person blocked; no PIN or a forced reset a first_setup or pin_reset code for this device (silent past the caps) and verification_required; locked for this device pin_locked; else pin_required. Nothing is counted.
-- Callers: IdentityRoutines.start; the number-step use case (N01).
-- Reads: identity.users, identity.trusted_devices, identity.verification_codes, identity.sign_in_attempts, and what identity.policy_for reads. Writes: identity.verification_codes, identity.sign_in_attempts.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_start(
  p_request_id text,
  p_phone text,
  p_device_id text,
  p_device_token_hash text,
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
  v_digest text := identity.phone_digest(coalesce(identity.normalize_phone(p_phone), p_phone));
  v_user identity.users;
  v_policy identity.policy;
  v_purpose text;
  v_code_id uuid;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);

  IF v_user.id IS NULL THEN
    IF identity.unknown_pin_tries(v_digest) >= identity.pin_tries() THEN
      PERFORM identity.record_attempt('start', 'pin_locked', 'unknown_number', NULL, v_digest, p_device_id, p_now);
      RETURN identity.outcome('pin_locked', '{"refusal": "unknown_number"}');
    END IF;
    PERFORM identity.record_attempt('start', 'pin_required', 'unknown_number', NULL, v_digest, p_device_id, p_now);
    RETURN identity.outcome('pin_required', '{"refusal": "unknown_number"}');
  END IF;

  v_policy := identity.policy_for(v_user.id);
  IF v_user.status <> 'active' OR v_policy.organization_id IS NULL THEN
    PERFORM identity.record_attempt('start', 'blocked', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('blocked', '{"refusal": "inactive"}');
  END IF;

  IF v_user.pin_hash IS NULL OR v_user.pin_reset_required THEN
    v_purpose := CASE WHEN v_user.pin_hash IS NULL THEN 'first_setup' ELSE 'pin_reset' END;
    v_code_id := identity.issue_code(
      v_user.id, v_purpose, p_device_id, p_code_hash, p_skip_cooldown, false, p_now
    );
    PERFORM identity.record_attempt(
      'start', 'verification_required', NULL, v_user.id, v_digest, p_device_id, p_now
    );
    RETURN identity.outcome('verification_required', jsonb_build_object(
      'purpose', v_purpose,
      'masked_email', identity.mask_email(v_user.email),
      'code_issued', v_code_id IS NOT NULL,
      'code_id', v_code_id,
      'email', CASE WHEN v_code_id IS NOT NULL THEN v_user.email END
    ));
  END IF;

  IF identity.locked_for(
       v_user,
       identity.device_trusted(v_user.id, p_device_id, coalesce(p_device_token_hash, ''), p_now)
     ) THEN
    PERFORM identity.record_attempt('start', 'pin_locked', 'locked', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('pin_locked', '{"refusal": "locked"}');
  END IF;

  PERFORM identity.record_attempt('start', 'pin_required', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN identity.outcome('pin_required');
END;
$$;
