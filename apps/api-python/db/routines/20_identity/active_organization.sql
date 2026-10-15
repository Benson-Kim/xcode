-- identity.active_organization(p_user_id uuid) RETURNS uuid
-- Purpose: the organization of the user's single active membership, NULL when none; the one cross-tenant lookup sign-in needs before any organization is known.
-- Callers: identity.policy_for, api.auth_resolve_session, api.meta_unassigned_user_count.
-- Reads: tenancy.memberships (every organization). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.
-- SECURITY DEFINER owned by xcode_owner (the table owner) so it reads past row-level security; it returns one id and nothing else, and only xcode_api_executor may execute it.

CREATE OR REPLACE FUNCTION identity.active_organization(p_user_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT m.organization_id FROM tenancy.memberships AS m WHERE m.user_id = p_user_id AND m.active;
$$;

ALTER FUNCTION identity.active_organization(uuid) OWNER TO xcode_owner;
REVOKE ALL ON FUNCTION identity.active_organization(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.active_organization(uuid) TO xcode_api_executor;
