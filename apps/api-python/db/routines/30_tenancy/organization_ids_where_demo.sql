-- tenancy.organization_ids_where_demo(p_demo boolean) RETURNS uuid[]
-- Purpose: the ids of the organizations whose demo flag is p_demo, oldest first: provisioning works in the one real organization, the App Review login in the one demo organization.
-- Callers: api.ops_provision_user, api.ops_review_account_create.
-- Reads: tenancy.organizations (every organization). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py, tests/db/test_review_account.py.
-- SECURITY DEFINER owned by xcode_owner (the table owner) so it reads past row-level security; it returns ids only, and only xcode_api_executor may execute it.

CREATE OR REPLACE FUNCTION tenancy.organization_ids_where_demo(p_demo boolean)
RETURNS uuid[]
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(array_agg(o.id ORDER BY o.created_at, o.id), '{}'::uuid[])
  FROM tenancy.organizations AS o
  WHERE o.demo = p_demo;
$$;

ALTER FUNCTION tenancy.organization_ids_where_demo(boolean) OWNER TO xcode_owner;
REVOKE ALL ON FUNCTION tenancy.organization_ids_where_demo(boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.organization_ids_where_demo(boolean) TO xcode_api_executor;
