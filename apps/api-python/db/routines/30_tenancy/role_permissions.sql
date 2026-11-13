-- tenancy.role_permissions(p_role_name text) RETURNS text[]
-- Purpose: a role's catalogue permissions with their dependencies, in catalogue order, the name matched ignoring case: a built-in role's defaults (the Owner's hidden organization.manage is left out: no person save names it), or the permissions of the current organization's custom role of that name; any other name has none.
-- Callers: tenancy.role_document, tenancy.check_person_grant, tenancy.save_person, tenancy.save_role, api.access_role_delete, tenancy.seed_demo_user.
-- Reads: tenancy.role_defaults, tenancy.roles, tenancy.role_grants, and what tenancy.expand_permissions reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py, tests/db/test_role_routines.py.

CREATE OR REPLACE FUNCTION tenancy.role_permissions(p_role_name text)
RETURNS text[]
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.expand_permissions(coalesce(array_agg(granted.permission), '{}'::text[]))
  FROM (
    SELECT d.permission
    FROM tenancy.role_defaults AS d
    WHERE lower(d.role_name) = lower(p_role_name)
    UNION ALL
    SELECT g.permission
    FROM tenancy.roles AS r
    JOIN tenancy.role_grants AS g ON g.organization_id = r.organization_id AND g.role_id = r.id
    WHERE r.organization_id = tenancy.current_organization()
      AND NOT r.built_in
      AND lower(r.name) = lower(p_role_name)
  ) AS granted;
$$;

REVOKE ALL ON FUNCTION tenancy.role_permissions(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.role_permissions(text) TO xcode_api_executor;
