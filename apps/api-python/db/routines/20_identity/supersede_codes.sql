-- identity.supersede_codes(p_user_id uuid, p_purpose text) RETURNS integer
-- Purpose: consume every unconsumed code of the user and purpose on every device before a new one is issued; superseded codes still count toward the cooldown and the caps (only a withdrawn code does not).
-- Callers: api.auth_sign_in (new_device), api.auth_request_code (first_setup, pin_reset).
-- Reads: identity.verification_codes. Writes: identity.verification_codes.consumed.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.supersede_codes(p_user_id uuid, p_purpose text)
RETURNS integer
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH superseded AS (
    UPDATE identity.verification_codes
    SET consumed = true
    WHERE user_id = p_user_id AND purpose = p_purpose AND NOT consumed
    RETURNING 1
  )
  SELECT count(*)::integer FROM superseded;
$$;

REVOKE ALL ON FUNCTION identity.supersede_codes(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.supersede_codes(uuid, text) TO xcode_api_executor;
