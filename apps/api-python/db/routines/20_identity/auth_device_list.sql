-- api.auth_device_list(p_user_id uuid, p_device_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: N08, the signed-in person's own trusted devices: the live remembered rows, most recently used first, as [{id, name, trusted_at, last_used_at, this_device}]; a read, so no history row.
-- Callers: IdentityRoutines.device_list; the trusted-devices use case (N08, after session resolution).
-- Reads: identity.trusted_devices. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_device_list(
  p_user_id uuid,
  p_device_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN (
  SELECT coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', d.id,
        'name', d.name,
        'trusted_at', d.trusted_at,
        'last_used_at', d.last_used_at,
        'this_device', d.device_id = p_device_id
      )
      ORDER BY d.last_used_at DESC, d.id
    ),
    '[]'::jsonb
  )
  FROM identity.trusted_devices AS d
  WHERE d.user_id = p_user_id AND d.remembered AND identity.device_live(d, p_now)
  );
END;
$$;
