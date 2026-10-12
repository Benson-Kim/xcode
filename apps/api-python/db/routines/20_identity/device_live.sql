-- identity.device_live(p_device identity.trusted_devices, p_now timestamptz) RETURNS boolean
-- Purpose: whether a device row still holds a session: not revoked, used within the last 90 days, and before its optional trust expiry.
-- Callers: identity.device_trusted, identity.remove_devices, tenancy.sign_in_snapshot, api.auth_resolve_session, api.auth_refresh, api.auth_device_list, api.auth_device_remove.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.device_live(p_device identity.trusted_devices, p_now timestamptz)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT p_device.id IS NOT NULL
     AND NOT p_device.revoked
     AND p_now < p_device.last_used_at + make_interval(days => identity.device_idle_days())
     AND (p_device.trust_expires_at IS NULL OR p_now < p_device.trust_expires_at);
$$;

REVOKE ALL ON FUNCTION identity.device_live(identity.trusted_devices, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.device_live(identity.trusted_devices, timestamptz) TO xcode_api_executor;
