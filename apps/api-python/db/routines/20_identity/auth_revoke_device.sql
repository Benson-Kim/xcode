-- api.auth_revoke_device(p_request_id text, p_user_id uuid, p_device_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: A12: revoke the caller's device: its trust, its live refresh tokens and its unconsumed codes, logging "Trusted device removed" when a live remembered row ended; always device_revoked.
-- Callers: IdentityRoutines.revoke_device; the revoke-device use case (A12, after session resolution).
-- Reads: identity.users, identity.trusted_devices. Writes: identity.trusted_devices, identity.refresh_tokens, identity.verification_codes, identity.sign_in_attempts, and the change log through identity.log_sign_in.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_revoke_device(
  p_request_id text,
  p_user_id uuid,
  p_device_id text,
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
  v_row_id uuid;
  v_before json;
  v_names text[];
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  IF p_user_id IS NOT NULL THEN
    v_user := identity.lock_user(p_user_id);
  END IF;
  IF v_user.id IS NULL THEN
    PERFORM pg_advisory_xact_lock(hashtext('device:' || coalesce(p_device_id, '')));
    PERFORM identity.record_attempt(
      'revoke_device', 'device_revoked', NULL, NULL, identity.phone_digest(NULL), p_device_id, p_now
    );
    RETURN identity.outcome('device_revoked');
  END IF;

  SELECT d.id INTO v_row_id
  FROM identity.trusted_devices AS d
  WHERE d.user_id = v_user.id AND d.device_id = p_device_id;
  IF v_row_id IS NOT NULL THEN
    v_before := tenancy.sign_in_snapshot(v_user.id, p_now);
    v_names := identity.remove_devices(v_user.id, p_now, v_row_id);
  END IF;
  -- Tokens and codes of a device without a row end too.
  PERFORM identity.revoke_tokens(v_user.id, p_device_id);
  UPDATE identity.verification_codes
  SET consumed = true
  WHERE user_id = v_user.id AND device_id = p_device_id AND NOT consumed;
  IF cardinality(v_names) > 0 THEN
    PERFORM identity.log_sign_in(v_user.id, v_user.id, ARRAY['Trusted device removed'], v_before, p_now);
  END IF;
  PERFORM identity.record_attempt(
    'revoke_device', 'device_revoked', NULL, v_user.id, identity.phone_digest(v_user.phone_number),
    p_device_id, p_now
  );
  RETURN identity.outcome('device_revoked');
END;
$$;
