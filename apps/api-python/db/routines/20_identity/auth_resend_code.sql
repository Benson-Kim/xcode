-- api.auth_resend_code(p_request_id text, p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_skip_cooldown boolean, p_now timestamptz) RETURNS jsonb
-- Purpose: N04 "Send a new code" (docs/07-auth.md 12.6): a new code of the purpose for this device, superseding the older one, only when the person may have one (new_device: a new_device code for this device in the last 10 minutes, so after a right PIN there; first_setup: no PIN yet; pin_reset: a pending forced reset or a pin_reset code for this device in the last 10 minutes) and the caps allow; always verification_required, issued or not.
-- Callers: IdentityRoutines.resend_code; the resend use case (N04).
-- Reads: identity.users, identity.verification_codes, and what identity.policy_for reads. Writes: identity.verification_codes, identity.sign_in_attempts.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_resend_code(
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
  v_recent boolean;
  v_allowed boolean;
  v_code_id uuid;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);

  IF v_user.id IS NULL THEN
    PERFORM identity.record_attempt('resend_code', 'verification_required', 'unknown_number', NULL, v_digest, p_device_id, p_now);
    RETURN identity.outcome('verification_required', jsonb_build_object('purpose', p_purpose));
  END IF;

  -- A code of this purpose was issued to this device less than 10 minutes ago (a withdrawn
  -- one, whose mail failed, does not count).
  v_recent := EXISTS (
    SELECT 1
    FROM identity.verification_codes AS c
    WHERE c.user_id = v_user.id
      AND c.purpose = p_purpose
      AND c.device_id = p_device_id
      AND c.created_at > p_now - interval '10 minutes'
      AND NOT (c.consumed AND c.expires_at <= c.created_at)
  );
  v_allowed := v_user.status = 'active'
    AND (identity.policy_for(v_user.id)).organization_id IS NOT NULL
    AND CASE p_purpose
          WHEN 'new_device' THEN v_user.pin_hash IS NOT NULL AND NOT v_user.pin_reset_required AND v_recent
          WHEN 'first_setup' THEN v_user.pin_hash IS NULL
          WHEN 'pin_reset' THEN v_user.pin_hash IS NOT NULL AND (v_user.pin_reset_required OR v_recent)
          ELSE false
        END;
  IF v_allowed THEN
    v_code_id := identity.issue_code(
      v_user.id, p_purpose, p_device_id, p_code_hash, p_skip_cooldown, false, p_now
    );
  END IF;
  PERFORM identity.record_attempt(
    'resend_code', 'verification_required', CASE WHEN NOT v_allowed THEN 'inactive' END,
    v_user.id, v_digest, p_device_id, p_now
  );
  RETURN identity.outcome('verification_required', jsonb_build_object(
    'purpose', p_purpose,
    'code_issued', v_code_id IS NOT NULL,
    'code_id', v_code_id,
    'email', CASE WHEN v_code_id IS NOT NULL THEN v_user.email END
  ));
END;
$$;
