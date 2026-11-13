-- api.access_role_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_name text, p_permissions text[], p_now timestamptz) RETURNS jsonb
-- Purpose: add a custom role with its permissions (tenancy.save_role) and answer it as tenancy.role_document.
-- Callers: TenancyRoutines.create_access_role; CreateAccessRole (POST /setup/access/roles).
-- Reads: what tenancy.save_role reads. Writes: what tenancy.save_role writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 role_name_invalid via tenancy.save_role, XC422 role_permissions_invalid via tenancy.save_role, XC422 role_permission_unknown via tenancy.save_role, XC422 role_name_taken via tenancy.save_role, XC422 role_permission_not_held via tenancy.save_role.
-- Tests: tests/db/test_role_routines.py, tests/api/test_access_roles.py.

CREATE OR REPLACE FUNCTION api.access_role_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_name text,
  p_permissions text[],
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'access.manage');
  RETURN tenancy.save_role(NULL, p_name, p_permissions, NULL, p_now);
END;
$$;
