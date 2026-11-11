-- identity.store_code(p_user_id uuid, p_purpose text, p_device_id text, p_code_hash text, p_now timestamptz) RETURNS uuid
-- Purpose: store a code for 10 minutes without asking the caps: supersede the person's unconsumed codes of the purpose on every device, then insert the digest for this device; its id.
-- Callers: identity.issue_code (after the caps), identity.matching_code and api.auth_invite_redeem (the invitation code, outside the caps).
-- Reads: identity.verification_codes. Writes: identity.verification_codes.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.store_code(
  p_user_id uuid,
  p_purpose text,
  p_device_id text,
  p_code_hash text,
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
  PERFORM identity.supersede_codes(p_user_id, p_purpose);
  INSERT INTO identity.verification_codes (user_id, purpose, device_id, code_hash, created_at, expires_at)
  VALUES (p_user_id, p_purpose, p_device_id, p_code_hash, p_now, p_now + interval '10 minutes')
  RETURNING id INTO v_code_id;
  RETURN v_code_id;
END;
$$;

REVOKE ALL ON FUNCTION identity.store_code(uuid, text, text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.store_code(uuid, text, text, text, timestamptz) TO xcode_api_executor;
