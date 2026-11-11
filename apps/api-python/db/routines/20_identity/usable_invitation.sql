-- identity.usable_invitation(p_user_id uuid, p_now timestamptz) RETURNS identity.invitations
-- Purpose: the one definition of a usable invitation, locked FOR UPDATE: of the person's active organization, live (not accepted, not revoked), p_now <= expires_at and fewer than identity.invitation_tries() failed tries; a row of NULLs when there is none. Sets the transaction-local organization setting to the person's active organization first, as an invitation is a tenant row.
-- Callers: api.auth_start, identity.matching_code (first_setup fallback).
-- Reads: identity.invitations, and what identity.active_organization reads. Writes: nothing (a row lock and the organization setting).
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION identity.usable_invitation(p_user_id uuid, p_now timestamptz)
RETURNS identity.invitations
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := identity.active_organization(p_user_id);
  v_invitation identity.invitations;
BEGIN
  IF v_organization_id IS NULL THEN
    RETURN NULL;
  END IF;
  PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
  SELECT i.* INTO v_invitation
  FROM identity.invitations AS i
  WHERE i.user_id = p_user_id
    AND i.accepted_at IS NULL AND i.revoked_at IS NULL
    AND i.organization_id = v_organization_id
    AND p_now <= i.expires_at AND i.failed_attempts < identity.invitation_tries()
  FOR UPDATE;
  RETURN v_invitation;
END;
$$;

REVOKE ALL ON FUNCTION identity.usable_invitation(uuid, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.usable_invitation(uuid, timestamptz) TO xcode_api_executor;
