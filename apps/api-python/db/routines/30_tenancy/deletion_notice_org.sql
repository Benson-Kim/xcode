-- tenancy.deletion_notice_org(p_notice_id uuid) RETURNS uuid
-- Purpose: the organization of the deletion notice with that id, whatever its state; NULL when none; the one cross-tenant lookup recording a send needs, since it runs after the request with no actor.
-- Callers: api.deletion_notice_result.
-- Reads: tenancy.deletion_notices (every organization). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_deletion_routines.py.
-- SECURITY DEFINER owned by xcode_owner (the table owner) so it reads past row-level security; it returns one id and nothing else, and only xcode_api_executor may execute it.

CREATE OR REPLACE FUNCTION tenancy.deletion_notice_org(p_notice_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT n.organization_id FROM tenancy.deletion_notices AS n WHERE n.id = p_notice_id;
$$;

ALTER FUNCTION tenancy.deletion_notice_org(uuid) OWNER TO xcode_owner;
REVOKE ALL ON FUNCTION tenancy.deletion_notice_org(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.deletion_notice_org(uuid) TO xcode_api_executor;
