-- identity.revoke_invitations(p_user_id uuid, p_reason text, p_now timestamptz) RETURNS integer
-- Purpose: end the person's live invitation (not accepted, not revoked) with the reason (replaced, blocked, removed, email_changed); how many were revoked.
-- Callers: identity.invite (replaced), api.people_update (email_changed), api.people_set_active (blocked), api.ops_remove_user (removed), api.people_erase (removed).
-- Reads: identity.invitations. Writes: identity.invitations (revoked_at, revoke_reason).
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION identity.revoke_invitations(p_user_id uuid, p_reason text, p_now timestamptz)
RETURNS integer
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH revoked AS (
    UPDATE identity.invitations
    SET revoked_at = p_now, revoke_reason = p_reason
    WHERE user_id = p_user_id AND accepted_at IS NULL AND revoked_at IS NULL
    RETURNING 1
  )
  SELECT count(*)::integer FROM revoked;
$$;

REVOKE ALL ON FUNCTION identity.revoke_invitations(uuid, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.revoke_invitations(uuid, text, timestamptz) TO xcode_api_executor;
