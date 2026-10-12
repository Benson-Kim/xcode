-- api.auth_device_remove(p_request_id text, p_user_id uuid, p_row_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: N09, the signed-in person removes one of their own live device rows by its id: the row, its refresh tokens and its codes end at once (removing the device in use ends this session), "Trusted device removed" is logged when it was a remembered device; device_revoked.
-- Callers: IdentityRoutines.device_remove; the remove-device use case (N09, after session resolution).
-- Reads: identity.users, identity.trusted_devices. Writes: identity.trusted_devices, identity.refresh_tokens, identity.verification_codes, identity.sign_in_attempts, and the change log through identity.log_sign_in.
-- Raises: XC404 not_found.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_device_remove(
  p_request_id text,
  p_user_id uuid,
  p_row_id uuid,
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
  v_device identity.trusted_devices;
  v_before json;
  v_names text[];
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  IF p_user_id IS NOT NULL THEN
    v_user := identity.lock_user(p_user_id);
  END IF;
  SELECT d.* INTO v_device
  FROM identity.trusted_devices AS d
  WHERE d.id = p_row_id AND d.user_id = v_user.id;
  IF v_user.id IS NULL OR NOT identity.device_live(v_device, p_now) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_before := tenancy.sign_in_snapshot(v_user.id, p_now);
  v_names := identity.remove_devices(v_user.id, p_now, p_row_id);
  IF cardinality(v_names) > 0 THEN
    PERFORM identity.log_sign_in(v_user.id, v_user.id, ARRAY['Trusted device removed'], v_before, p_now);
  END IF;
  PERFORM identity.record_attempt(
    'remove_device', 'device_revoked', NULL, v_user.id, identity.phone_digest(v_user.phone_number),
    v_device.device_id, p_now
  );
  RETURN identity.outcome('device_revoked');
END;
$$;
