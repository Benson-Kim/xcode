-- identity.device_trusted(p_user_id uuid, p_device_id text, p_token_hash text, p_now timestamptz) RETURNS boolean
-- Purpose: whether the device may sign in with the PIN alone: its row is live and remembered, and either p_token_hash is NULL (the released routes) and the row has no token (trusted by device id, v2.11), or p_token_hash equals the row's token digest. The new routes pass '' for a missing token, which matches no row.
-- Callers: api.auth_account_lookup, api.auth_sign_in, api.auth_start, api.auth_pin.
-- Reads: identity.trusted_devices. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py, tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.device_trusted(
  p_user_id uuid,
  p_device_id text,
  p_token_hash text,
  p_now timestamptz
)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM identity.trusted_devices AS d
    WHERE d.user_id = p_user_id
      AND d.device_id = p_device_id
      AND d.remembered
      AND identity.device_live(d, p_now)
      AND CASE
            WHEN p_token_hash IS NULL THEN d.token_hash IS NULL
            ELSE d.token_hash = p_token_hash
          END
  );
$$;

REVOKE ALL ON FUNCTION identity.device_trusted(uuid, text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.device_trusted(uuid, text, text, timestamptz) TO xcode_api_executor;
