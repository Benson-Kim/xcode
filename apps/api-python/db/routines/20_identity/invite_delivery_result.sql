-- api.invite_delivery_result(p_token_hash text, p_sent boolean, p_now timestamptz) RETURNS void
-- Purpose: record how a send ended, only while the invitation with that link digest is still pending (a late answer for a digest the sweep has since replaced changes nothing): sent with sent_at; a failure marks it failed once it has used identity.invitation_sends() attempts, and otherwise leaves it pending for api.invite_claim_undelivered to try again.
-- Callers: IdentityRoutines.invite_delivery_result; the post-commit invitation send and the undelivered sweep.
-- Reads: identity.invitations, and what identity.invitation_org reads. Writes: identity.invitations (delivery_state, sent_at).
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION api.invite_delivery_result(p_token_hash text, p_sent boolean, p_now timestamptz)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := identity.invitation_org(p_token_hash);
BEGIN
  IF v_organization_id IS NULL THEN
    RETURN;
  END IF;
  PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
  IF p_sent THEN
    UPDATE identity.invitations
    SET delivery_state = 'sent', sent_at = p_now
    WHERE token_hash = p_token_hash AND delivery_state = 'pending';
  ELSE
    UPDATE identity.invitations
    SET delivery_state = 'failed'
    WHERE token_hash = p_token_hash
      AND delivery_state = 'pending'
      AND delivery_attempts >= identity.invitation_sends();
  END IF;
END;
$$;
