-- identity.issue_code(p_user_id uuid, p_purpose text, p_device_id text, p_code_hash text, p_skip_cooldown boolean, p_replacement boolean, p_now timestamptz) RETURNS uuid
-- Purpose: the one place a capped code is issued: when the caps allow (identity.code_caps), store it with identity.store_code; its id, or NULL (silent) when a cap stops it or there is no digest.
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
BEGIN
  IF p_code_hash IS NULL
     OR NOT identity.code_caps(p_user_id, p_skip_cooldown, p_replacement, p_now) THEN
    RETURN NULL;
  END IF;
  RETURN identity.store_code(p_user_id, p_purpose, p_device_id, p_code_hash, p_now);
END;
$$;

REVOKE ALL ON FUNCTION identity.issue_code(uuid, text, text, text, boolean, boolean, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.issue_code(uuid, text, text, text, boolean, boolean, timestamptz)
  TO xcode_api_executor;
