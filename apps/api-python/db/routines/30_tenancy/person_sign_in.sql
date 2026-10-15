-- tenancy.person_sign_in(p_user_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: the "Sign in" pane of a person in the current organization: the people status, which lock holds (every_device after five wrong PINs on trusted devices, new_devices after five on others, else null), the last sign-in, where codes go, and the live remembered devices, most recently used first, as {status, lock, last_signed_in_at, email, devices: [{id, name, trusted_at, last_used_at}]}.
-- Callers: api.people_get.
-- Reads: identity.users, identity.trusted_devices, tenancy.memberships. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py.
-- Reads tenant rows under row-level security: the organization setting must already be set.

CREATE OR REPLACE FUNCTION tenancy.person_sign_in(p_user_id uuid, p_now timestamptz)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT jsonb_build_object(
           'status', identity.sign_in_status(u, m.active),
           'lock', CASE
                     WHEN u.failed_attempts >= identity.pin_tries() THEN 'every_device'
                     WHEN u.untrusted_failed_attempts >= identity.pin_tries() THEN 'new_devices'
                   END,
           'last_signed_in_at', u.last_signed_in_at,
           'email', u.email,
           'devices', (
             SELECT coalesce(
                      jsonb_agg(
                        jsonb_build_object(
                          'id', d.id,
                          'name', d.name,
                          'trusted_at', d.trusted_at,
                          'last_used_at', d.last_used_at
                        )
                        ORDER BY d.last_used_at DESC, d.id
                      ),
                      '[]'::jsonb
                    )
             FROM identity.trusted_devices AS d
             WHERE d.user_id = u.id AND d.remembered AND identity.device_live(d, p_now)
           )
         )
  FROM tenancy.memberships AS m
  JOIN identity.users AS u ON u.id = m.user_id
  WHERE m.organization_id = tenancy.current_organization()
    AND m.user_id = p_user_id;
$$;

REVOKE ALL ON FUNCTION tenancy.person_sign_in(uuid, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.person_sign_in(uuid, timestamptz) TO xcode_api_executor;
