-- tenancy.sign_in_snapshot(p_user_id uuid, p_now timestamptz) RETURNS json
-- Purpose: the change-log snapshot of a person's sign-in state: {"Status": Active | Not signed in yet | PIN reset due | Locked | Blocked, "Devices": [names of the live remembered devices by trust date, null for an unnamed one]}, compact.
-- Callers: identity.log_sign_in, identity.count_wrong_pin, the sign-in routines that take a snapshot before a change.
-- Reads: identity.users, identity.trusted_devices, tenancy.memberships (through identity.active_organization). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION tenancy.sign_in_snapshot(p_user_id uuid, p_now timestamptz)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(json_build_object(
    'Status', CASE identity.sign_in_status(u, identity.active_organization(u.id) IS NOT NULL)
                WHEN 'active' THEN 'Active'
                WHEN 'not_signed_in' THEN 'Not signed in yet'
                WHEN 'pin_reset_due' THEN 'PIN reset due'
                WHEN 'locked' THEN 'Locked'
                ELSE 'Blocked'
              END,
    'Devices', coalesce(
      (SELECT json_agg(d.name ORDER BY d.trusted_at, d.id)
       FROM identity.trusted_devices AS d
       WHERE d.user_id = u.id AND d.remembered AND identity.device_live(d, p_now)),
      '[]'::json
    )
  ))
  FROM identity.users AS u
  WHERE u.id = p_user_id;
$$;

REVOKE ALL ON FUNCTION tenancy.sign_in_snapshot(uuid, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.sign_in_snapshot(uuid, timestamptz) TO xcode_api_executor;
