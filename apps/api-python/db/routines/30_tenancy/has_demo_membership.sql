-- tenancy.has_demo_membership(p_user_id uuid) RETURNS boolean
-- Purpose: whether the user has a membership, active or not, in an organization flagged demo, so provisioning keeps every such person out of the real organization, a deactivated one too.
-- Callers: api.ops_provision_user.
-- Reads: tenancy.memberships, tenancy.organizations (every organization). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.
-- SECURITY DEFINER owned by xcode_owner (the table owner) so it reads past row-level security; it returns one boolean and nothing else, and only xcode_api_executor may execute it.

CREATE OR REPLACE FUNCTION tenancy.has_demo_membership(p_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM tenancy.memberships AS m
    JOIN tenancy.organizations AS o ON o.id = m.organization_id
    WHERE m.user_id = p_user_id AND o.demo
  );
$$;

ALTER FUNCTION tenancy.has_demo_membership(uuid) OWNER TO xcode_owner;
REVOKE ALL ON FUNCTION tenancy.has_demo_membership(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.has_demo_membership(uuid) TO xcode_api_executor;
