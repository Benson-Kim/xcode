-- identity.trust_device(p_user_id uuid, p_device_id text, p_name text, p_token_hash text, p_remembered boolean, p_trust_days integer, p_now timestamptz) RETURNS void
-- Purpose: trust a device (insert, or renew an existing row): live again from p_now, named (an unnamed trust keeps the stored name), remembered with the new token digest or, when not remembered, for this session only and without a token; expiring p_trust_days after p_now or never when NULL.
-- Callers: api.auth_verify_device, api.auth_check_code, api.auth_complete_pin.
-- Reads: identity.trusted_devices. Writes: identity.trusted_devices.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.trust_device(
  p_user_id uuid,
  p_device_id text,
  p_name text,
  p_token_hash text,
  p_remembered boolean,
  p_trust_days integer,
  p_now timestamptz
)
RETURNS void
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  INSERT INTO identity.trusted_devices (
    user_id, device_id, revoked, trust_expires_at, token_hash, name, trusted_at, last_used_at,
    remembered, created_at, updated_at
  )
  VALUES (
    p_user_id,
    p_device_id,
    false,
    CASE WHEN p_trust_days IS NULL THEN NULL ELSE p_now + make_interval(days => p_trust_days) END,
    CASE WHEN p_remembered THEN p_token_hash END,
    p_name,
    p_now,
    p_now,
    p_remembered,
    p_now,
    p_now
  )
  ON CONFLICT (user_id, device_id) DO UPDATE
  SET revoked = false,
      trust_expires_at = EXCLUDED.trust_expires_at,
      token_hash = EXCLUDED.token_hash,
      name = coalesce(EXCLUDED.name, identity.trusted_devices.name),
      trusted_at = EXCLUDED.trusted_at,
      last_used_at = EXCLUDED.last_used_at,
      remembered = EXCLUDED.remembered,
      updated_at = EXCLUDED.updated_at;
$$;

REVOKE ALL ON FUNCTION identity.trust_device(uuid, text, text, text, boolean, integer, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.trust_device(uuid, text, text, text, boolean, integer, timestamptz)
  TO xcode_api_executor;
