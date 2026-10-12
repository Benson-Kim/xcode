-- tenancy.organization_ids() RETURNS uuid[]
-- Purpose: the ids of every organization in the database, oldest first; provisioning supports exactly one.
-- Callers: api.ops_provision_user.
-- Reads: tenancy.organizations (every organization). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.
-- SECURITY DEFINER owned by xcode_owner (the table owner) so it reads past row-level security; it returns ids only, and only xcode_api_executor may execute it.

CREATE OR REPLACE FUNCTION tenancy.organization_ids()
RETURNS uuid[]
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(array_agg(o.id ORDER BY o.created_at, o.id), '{}'::uuid[])
  FROM tenancy.organizations AS o;
$$;

ALTER FUNCTION tenancy.organization_ids() OWNER TO xcode_owner;
REVOKE ALL ON FUNCTION tenancy.organization_ids() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.organization_ids() TO xcode_api_executor;
