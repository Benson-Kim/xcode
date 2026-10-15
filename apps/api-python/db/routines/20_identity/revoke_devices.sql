-- identity.revoke_devices(p_user_id uuid, p_device_id text DEFAULT NULL) RETURNS integer
-- Purpose: revoke the user's trusted devices (all, or the one named) and return how many were still trusted.
-- Callers: api.auth_revoke_device, api.ops_provision_user, api.ops_revoke_sessions, and the people routines.
-- Reads: identity.trusted_devices. Writes: identity.trusted_devices.revoked.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.revoke_devices(p_user_id uuid, p_device_id text DEFAULT NULL)
RETURNS integer
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH revoked AS (
    UPDATE identity.trusted_devices
    SET revoked = true
    WHERE user_id = p_user_id
      AND (p_device_id IS NULL OR device_id = p_device_id)
      AND NOT revoked
    RETURNING 1
  )
  SELECT count(*)::integer FROM revoked;
$$;

REVOKE ALL ON FUNCTION identity.revoke_devices(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.revoke_devices(uuid, text) TO xcode_api_executor;
