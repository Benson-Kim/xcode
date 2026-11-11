-- identity.people_status(p_user identity.users, p_member_active boolean, p_now timestamptz) RETURNS text
-- Purpose: identity.sign_in_status for the people screens, with not_signed_in replaced by the invitation status (invited, invite_expired) when the person has a live invitation.
-- Callers: api.people_list, tenancy.person_document, tenancy.person_sign_in.
-- Reads: identity.invitations. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION identity.people_status(p_user identity.users, p_member_active boolean, p_now timestamptz)
RETURNS text
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_status text := identity.sign_in_status(p_user, p_member_active);
BEGIN
  IF v_status = 'not_signed_in' THEN
    RETURN coalesce(identity.invitation_status(p_user.id, p_now), v_status);
  END IF;
  RETURN v_status;
END;
$$;

REVOKE ALL ON FUNCTION identity.people_status(identity.users, boolean, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.people_status(identity.users, boolean, timestamptz) TO xcode_api_executor;
