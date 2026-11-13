-- tenancy.role_document(p_role_id uuid) RETURNS jsonb
-- Purpose: one role of the current organization as the roles routes answer it: {id, name, permissions (tenancy.role_permissions), built_in, version}; NULL for a role the organization lacks.
-- Callers: api.access_role_list, tenancy.save_role.
-- Reads: tenancy.roles, and what tenancy.role_permissions reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_role_routines.py.
-- Reads tenant rows under row-level security: the organization setting must already be set.

CREATE OR REPLACE FUNCTION tenancy.role_document(p_role_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN (
    SELECT jsonb_build_object(
             'id', r.id,
             'name', r.name,
             'permissions', to_jsonb(tenancy.role_permissions(r.name)),
             'built_in', r.built_in,
             'version', r.version
           )
    FROM tenancy.roles AS r
    WHERE r.organization_id = tenancy.current_organization()
      AND r.id = p_role_id
  );
END;
$$;

REVOKE ALL ON FUNCTION tenancy.role_document(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.role_document(uuid) TO xcode_api_executor;
