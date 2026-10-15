-- identity.matching_code(p_user_id uuid, p_purpose text, p_device_id text, p_code_hash text, p_now timestamptz) RETURNS identity.code_check
-- Purpose: check a presented code against the newest unconsumed code of that user, purpose and device: its id on a match (not consumed); code_expired when there is none, it expired (p_now > expires_at) or it already failed three times; wrong_code after counting a failed try, with the tries left, the third of which consumes (voids) it.
-- Callers: api.auth_check_code, api.auth_verify_device, api.auth_verify_code, api.auth_complete_pin.
-- Reads: identity.verification_codes. Writes: identity.verification_codes (failed_attempts, consumed on the third failure).
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.matching_code(
  p_user_id uuid,
  p_purpose text,
  p_device_id text,
  p_code_hash text,
  p_now timestamptz
)
RETURNS identity.code_check
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_code identity.verification_codes;
  v_failed integer;
BEGIN
  SELECT c.* INTO v_code
  FROM identity.verification_codes AS c
  WHERE c.user_id = p_user_id
    AND c.purpose = p_purpose
    AND c.device_id = p_device_id
    AND NOT c.consumed
  ORDER BY c.created_at DESC, c.id DESC
  LIMIT 1
  FOR UPDATE;

  IF NOT FOUND OR p_now > v_code.expires_at OR v_code.failed_attempts >= 3 THEN
    RETURN ROW(NULL, 'code_expired', false, NULL)::identity.code_check;
  END IF;

  IF p_code_hash IS NULL OR v_code.code_hash <> p_code_hash THEN
    UPDATE identity.verification_codes
    SET failed_attempts = failed_attempts + 1,
        consumed = failed_attempts + 1 >= 3
    WHERE id = v_code.id
    RETURNING failed_attempts INTO v_failed;
    RETURN ROW(NULL, 'wrong_code', v_failed >= 3, greatest(3 - v_failed, 0))::identity.code_check;
  END IF;

  RETURN ROW(v_code.id, NULL, false, NULL)::identity.code_check;
END;
$$;

REVOKE ALL ON FUNCTION identity.matching_code(uuid, text, text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.matching_code(uuid, text, text, text, timestamptz) TO xcode_api_executor;
