-- api.access_role_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the organization's roles, built-in first and then by name, each as tenancy.role_document (permissions with their dependencies, built_in, version); read only (the catalogue roles are seeded when the organization is created).
-- Callers: TenancyRoutines.access_roles; ListAccessRoles (GET /setup/access/roles).
-- Reads: tenancy.roles, and what tenancy.role_document reads. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization.
-- Tests: tests/db/test_access_routines.py, tests/api/test_access.py.

CREATE OR REPLACE FUNCTION api.access_role_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.view');
  RETURN (
    SELECT coalesce(
             jsonb_agg(tenancy.role_document(r.id) ORDER BY r.built_in DESC, lower(r.name), r.id),
             '[]'::jsonb)
    FROM tenancy.roles AS r
    WHERE r.organization_id = p_organization_id
  );
END;
$$;
