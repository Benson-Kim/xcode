-- api.access_role_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_role_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: delete a custom role nobody holds, active or blocked, whose permissions the actor all holds, with its permission rows; log one roles change with the role as it was.
-- Callers: TenancyRoutines.delete_access_role; DeleteAccessRole (DELETE /setup/access/roles/{id}).
-- Reads: tenancy.roles, tenancy.person_roles, and what tenancy.role_permissions and tenancy.effective_permissions read. Writes: tenancy.role_grants, tenancy.roles, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC422 role_built_in, XC422 role_not_held, XC409 in_use via tenancy.refuse_role_in_use.
-- Tests: tests/db/test_role_routines.py, tests/api/test_access_roles.py.
-- FOR UPDATE waits for a person save giving this role (it holds KEY SHARE on the role), so
-- the holder count below sees that person; the foreign key is the backstop.

CREATE OR REPLACE FUNCTION api.access_role_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_role_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_role tenancy.roles;
  v_permissions text[];
  v_before json;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'access.manage');
  SELECT r.* INTO v_role
  FROM tenancy.roles AS r
  WHERE r.organization_id = p_organization_id AND r.id = p_role_id
  FOR UPDATE;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF v_role.built_in THEN
    PERFORM tenancy.refuse('role_built_in', 'XC422');
  END IF;
  v_permissions := tenancy.role_permissions(v_role.name);
  IF NOT v_permissions <@ tenancy.effective_permissions(p_organization_id, p_actor_id) THEN
    PERFORM tenancy.refuse('role_not_held', 'XC422');
  END IF;
  PERFORM tenancy.refuse_role_in_use(v_role);

  v_before := tenancy.compact_json(json_build_object('Name', v_role.name, 'Permissions', v_permissions));
  DELETE FROM tenancy.role_grants
  WHERE organization_id = p_organization_id AND role_id = p_role_id;
  DELETE FROM tenancy.roles WHERE organization_id = p_organization_id AND id = p_role_id;
  PERFORM tenancy.record_change(
    'roles', p_role_id, NULL, v_before, 'null'::json, 'Deleted role ' || v_role.name,
    'role.deleted', p_role_id::text, v_before::jsonb, NULL, p_now
  );
  RETURN ROW(p_role_id, v_role.version + 1, 'updated')::api.write_result;
END;
$$;
