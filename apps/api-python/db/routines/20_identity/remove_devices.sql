-- identity.remove_devices(p_user_id uuid, p_now timestamptz, p_row_id uuid DEFAULT NULL) RETURNS text[]
-- Purpose: revoke the person's trusted-device rows (all, or the one row named) with their live refresh tokens and unconsumed codes (all of the person's when removing all); returns the names of the live remembered rows it removed (NULL for an unnamed one), oldest trust first, for the change log.
-- Callers: api.auth_complete_pin (a reset), api.auth_device_remove, api.auth_revoke_device, and the people routines.
-- Reads: identity.trusted_devices. Writes: identity.trusted_devices, identity.refresh_tokens, identity.verification_codes.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.remove_devices(
  p_user_id uuid,
  p_now timestamptz,
  p_row_id uuid DEFAULT NULL
)
RETURNS text[]
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_names text[];
  v_devices text[];
BEGIN
  SELECT coalesce(array_agg(d.name ORDER BY d.trusted_at, d.id)
                    FILTER (WHERE d.remembered AND identity.device_live(d, p_now)), '{}'),
         coalesce(array_agg(d.device_id), '{}')
  INTO v_names, v_devices
  FROM identity.trusted_devices AS d
  WHERE d.user_id = p_user_id
    AND (p_row_id IS NULL OR d.id = p_row_id)
    AND NOT d.revoked;

  UPDATE identity.trusted_devices
  SET revoked = true, updated_at = p_now
  WHERE user_id = p_user_id AND (p_row_id IS NULL OR id = p_row_id) AND NOT revoked;
  UPDATE identity.refresh_tokens
  SET revoked = true, version = version + 1, updated_at = p_now
  WHERE user_id = p_user_id AND NOT revoked AND (p_row_id IS NULL OR device_id = ANY (v_devices));
  UPDATE identity.verification_codes
  SET consumed = true
  WHERE user_id = p_user_id AND NOT consumed AND (p_row_id IS NULL OR device_id = ANY (v_devices));
  RETURN v_names;
END;
$$;

REVOKE ALL ON FUNCTION identity.remove_devices(uuid, timestamptz, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.remove_devices(uuid, timestamptz, uuid) TO xcode_api_executor;
