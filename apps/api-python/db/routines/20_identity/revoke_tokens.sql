-- identity.revoke_tokens(p_user_id uuid, p_device_id text DEFAULT NULL) RETURNS integer
-- Purpose: revoke the user's live refresh tokens (all, or the named device's), bumping each token's version, and return how many.
-- Callers: api.auth_complete_pin, api.auth_refresh, api.auth_sign_out, api.auth_revoke_device, the api.ops_* user routines, and the people routines.
-- Reads: identity.refresh_tokens. Writes: identity.refresh_tokens (revoked, version).
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.revoke_tokens(p_user_id uuid, p_device_id text DEFAULT NULL)
RETURNS integer
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH revoked AS (
    UPDATE identity.refresh_tokens
    SET revoked = true, version = version + 1
    WHERE user_id = p_user_id
      AND (p_device_id IS NULL OR device_id = p_device_id)
      AND NOT revoked
    RETURNING 1
  )
  SELECT count(*)::integer FROM revoked;
$$;

REVOKE ALL ON FUNCTION identity.revoke_tokens(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.revoke_tokens(uuid, text) TO xcode_api_executor;
