-- api.invite_delivery_start(p_token_hash text, p_now timestamptz) RETURNS jsonb
-- Purpose: begin one send of the invitation with that link digest: only while its delivery is pending and it is live (not accepted, not revoked, p_now <= expires_at), count the attempt (attempted_at, delivery_attempts) and return what the email needs (identity.invitation_delivery); NULL otherwise, which is the caller's only test of whether to send.
-- Callers: IdentityRoutines.invite_delivery_start; the post-commit invitation send.
-- Reads: identity.invitations, and what identity.invitation_org and identity.invitation_delivery read. Writes: identity.invitations (attempted_at, delivery_attempts).
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION api.invite_delivery_start(p_token_hash text, p_now timestamptz)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := identity.invitation_org(p_token_hash);
  v_invitation identity.invitations;
BEGIN
  IF v_organization_id IS NULL THEN
    RETURN NULL;
  END IF;
  PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
  UPDATE identity.invitations AS i
  SET attempted_at = p_now, delivery_attempts = i.delivery_attempts + 1
  WHERE i.token_hash = p_token_hash
    AND i.delivery_state = 'pending'
    AND i.accepted_at IS NULL AND i.revoked_at IS NULL
    AND p_now <= i.expires_at
  RETURNING i.* INTO v_invitation;
  IF v_invitation.id IS NULL THEN
    RETURN NULL;
  END IF;
  RETURN identity.invitation_delivery(v_invitation);
END;
$$;
