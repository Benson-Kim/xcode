-- identity.issue_code(p_user_id uuid, p_purpose text, p_device_id text, p_code_hash text, p_skip_cooldown boolean, p_replacement boolean, p_now timestamptz) RETURNS uuid
-- Purpose: the one place a code is issued: when the caps allow (identity.code_caps), supersede the person's unconsumed codes of the purpose on every device and store the new digest for 10 minutes; its id, or NULL (silent) when a cap stops it or there is no digest.
-- Callers: api.auth_start, api.auth_pin, api.auth_sign_in, api.auth_request_code, api.auth_resend_code, api.auth_check_code, api.auth_verify_device, api.auth_verify_code.
-- Reads: identity.verification_codes. Writes: identity.verification_codes.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.issue_code(
  p_user_id uuid,
  p_purpose text,
  p_device_id text,
  p_code_hash text,
  p_skip_cooldown boolean,
  p_replacement boolean,
  p_now timestamptz
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_code_id uuid;
BEGIN
  IF p_code_hash IS NULL
     OR NOT identity.code_caps(p_user_id, p_skip_cooldown, p_replacement, p_now) THEN
    RETURN NULL;
  END IF;
  PERFORM identity.supersede_codes(p_user_id, p_purpose);
  INSERT INTO identity.verification_codes (user_id, purpose, device_id, code_hash, created_at, expires_at)
  VALUES (p_user_id, p_purpose, p_device_id, p_code_hash, p_now, p_now + interval '10 minutes')
  RETURNING id INTO v_code_id;
  RETURN v_code_id;
END;
$$;

REVOKE ALL ON FUNCTION identity.issue_code(uuid, text, text, text, boolean, boolean, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.issue_code(uuid, text, text, text, boolean, boolean, timestamptz)
  TO xcode_api_executor;
