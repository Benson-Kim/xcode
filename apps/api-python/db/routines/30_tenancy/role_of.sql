-- tenancy.role_of(p_user_id uuid) RETURNS text
-- Purpose: the name of a person's role in the current organization, NULL when they have none.
-- Callers: tenancy.check_person_grant, tenancy.save_person, api.people_set_active, api.people_sign_out (the Owner rules).
-- Reads: tenancy.person_roles, tenancy.roles. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.role_of(p_user_id uuid)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT r.name
  FROM tenancy.person_roles AS pr
  JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id AND r.id = pr.role_id
  WHERE pr.organization_id = tenancy.current_organization()
    AND pr.user_id = p_user_id;
$$;

REVOKE ALL ON FUNCTION tenancy.role_of(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.role_of(uuid) TO xcode_api_executor;
