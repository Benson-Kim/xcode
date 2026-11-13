-- api.access_role_update(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_role_id uuid, p_name text, p_permissions text[], p_expected_version bigint, p_now timestamptz) RETURNS jsonb
-- Purpose: rename a custom role or change its permissions at the version the actor saw (tenancy.save_role), ending the sessions of everyone holding it when anything changed, and answer it as tenancy.role_document.
-- Callers: TenancyRoutines.update_access_role; UpdateAccessRole (PUT /setup/access/roles/{id}).
-- Reads: what tenancy.save_role reads. Writes: what tenancy.save_role writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 role_name_invalid via tenancy.save_role, XC422 role_permissions_invalid via tenancy.save_role, XC422 role_permission_unknown via tenancy.save_role, XC404 not_found,XC422 role_built_in via tenancy.save_role, XC409 version_conflict via tenancy.save_role, XC422 role_not_held via tenancy.save_role, XC422 role_name_taken via tenancy.save_role, XC422 role_permission_not_held via tenancy.save_role.
-- Tests: tests/db/test_role_routines.py, tests/api/test_access_roles.py.

CREATE OR REPLACE FUNCTION api.access_role_update(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_role_id uuid,
  p_name text,
  p_permissions text[],
  p_expected_version bigint,
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
  IF p_role_id IS NULL THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  RETURN tenancy.save_role(p_role_id, p_name, p_permissions, p_expected_version, p_now);
END;
$$;
