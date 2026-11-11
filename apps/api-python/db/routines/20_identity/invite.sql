-- identity.invite(p_user_id uuid, p_organization_id uuid, p_actor uuid, p_token_hash text, p_code_hash text, p_now timestamptz) RETURNS uuid
-- Purpose: the one place an invitation is made: revoke the person's live invitation as replaced, then store the link and code digests for 7 days, delivery pending; its id. A missing digest fails on NOT NULL.
-- Callers: api.people_create, api.people_update (email changed), api.people_invite.
-- Reads: identity.invitations. Writes: identity.invitations.
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION identity.invite(
  p_user_id uuid,
  p_organization_id uuid,
  p_actor uuid,
  p_token_hash text,
  p_code_hash text,
  p_now timestamptz
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_id uuid;
BEGIN
  PERFORM identity.revoke_invitations(p_user_id, 'replaced', p_now);
  INSERT INTO identity.invitations (
    organization_id, user_id, invited_by, token_hash, code_hash, created_at, expires_at
  )
  VALUES (p_organization_id, p_user_id, p_actor, p_token_hash, p_code_hash, p_now, p_now + interval '7 days')
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

REVOKE ALL ON FUNCTION identity.invite(uuid, uuid, uuid, text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.invite(uuid, uuid, uuid, text, text, timestamptz) TO xcode_api_executor;
