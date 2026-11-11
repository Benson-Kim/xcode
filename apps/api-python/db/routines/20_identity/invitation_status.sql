-- identity.invitation_status(p_user_id uuid, p_now timestamptz) RETURNS text
-- Purpose: the people status of the person's live invitation by time alone: invited while p_now <= expires_at, invite_expired after; NULL with no live invitation.
-- Callers: identity.people_status.
-- Reads: identity.invitations. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION identity.invitation_status(p_user_id uuid, p_now timestamptz)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE WHEN p_now <= i.expires_at THEN 'invited' ELSE 'invite_expired' END
  FROM identity.invitations AS i
  WHERE i.user_id = p_user_id AND i.accepted_at IS NULL AND i.revoked_at IS NULL;
$$;

REVOKE ALL ON FUNCTION identity.invitation_status(uuid, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.invitation_status(uuid, timestamptz) TO xcode_api_executor;
