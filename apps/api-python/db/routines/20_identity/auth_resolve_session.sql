-- api.auth_resolve_session(p_user_id uuid, p_device_id text, p_security_version integer, p_now timestamptz) RETURNS jsonb
-- Purpose: the per-request session check of every bearer route: the user exists and is active, the security version matches the token, the device row is live (used within 90 days, not revoked, not expired; remembered or for this session only); returns {organization_id, role} for the log context.
-- Callers: IdentityRoutines.resolve_session; the bearer principal (every authenticated request).
-- Reads: identity.users, identity.trusted_devices, tenancy.person_roles, tenancy.roles. Writes: nothing.
-- Raises: XC401 session_invalid.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_resolve_session(
  p_user_id uuid,
  p_device_id text,
  p_security_version integer,
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
  v_organization_id uuid;
  v_role text;
BEGIN
  SELECT u.* INTO v_user FROM identity.users AS u WHERE u.id = p_user_id;
  IF v_user.id IS NULL
     OR v_user.status <> 'active'
     OR v_user.security_version IS DISTINCT FROM p_security_version
     OR NOT EXISTS (
       SELECT 1
       FROM identity.trusted_devices AS d
       WHERE d.user_id = v_user.id AND d.device_id = p_device_id AND identity.device_live(d, p_now)
     ) THEN
    PERFORM tenancy.refuse('session_invalid', 'XC401');
  END IF;

  v_organization_id := identity.active_organization(v_user.id);
  IF v_organization_id IS NOT NULL THEN
    PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
    SELECT r.name INTO v_role
    FROM tenancy.person_roles AS pr
    JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id AND r.id = pr.role_id
    WHERE pr.organization_id = v_organization_id AND pr.user_id = v_user.id;
  END IF;
  RETURN jsonb_build_object('organization_id', v_organization_id, 'role', v_role);
END;
$$;
