-- tenancy.role_permissions(p_role_name text) RETURNS text[]
-- Purpose: a catalogue role's default catalogue permissions with their dependencies, in catalogue order (the Owner's hidden organization.manage is left out: no person save names it); the name is matched ignoring case and any other name has none.
-- Callers: api.access_role_list, tenancy.check_person_grant, tenancy.save_person.
-- Reads: tenancy.role_defaults, and what tenancy.expand_permissions reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.role_permissions(p_role_name text)
RETURNS text[]
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.expand_permissions(coalesce(array_agg(d.permission), '{}'::text[]))
  FROM tenancy.role_defaults AS d
  WHERE lower(d.role_name) = lower(p_role_name);
$$;

REVOKE ALL ON FUNCTION tenancy.role_permissions(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.role_permissions(text) TO xcode_api_executor;
