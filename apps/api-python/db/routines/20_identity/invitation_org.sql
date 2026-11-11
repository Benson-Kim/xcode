-- identity.invitation_org(p_token_hash text) RETURNS uuid
-- Purpose: the organization of the invitation with that link digest, whatever its state; NULL when none; the one cross-tenant lookup the link step needs before any organization is known.
-- Callers: api.auth_invite_redeem, api.invite_delivery_start, api.invite_delivery_result.
-- Reads: identity.invitations (every organization). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_invitations.py.
-- SECURITY DEFINER owned by xcode_owner (the table owner) so it reads past row-level security; it returns one id and nothing else, and only xcode_api_executor may execute it.

CREATE OR REPLACE FUNCTION identity.invitation_org(p_token_hash text)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT i.organization_id FROM identity.invitations AS i WHERE i.token_hash = p_token_hash;
$$;

ALTER FUNCTION identity.invitation_org(text) OWNER TO xcode_owner;
REVOKE ALL ON FUNCTION identity.invitation_org(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.invitation_org(text) TO xcode_api_executor;
