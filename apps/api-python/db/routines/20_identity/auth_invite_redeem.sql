-- api.auth_invite_redeem(p_request_id text, p_token_hash text, p_phone text, p_device_id text, p_code_hash text, p_now timestamptz) RETURNS jsonb
-- Purpose: the invitation link step: with the link's token and the person's number, store the server-made first_setup code for this device outside the caps and answer verification_required (first_setup, the code id, the masked email). An unknown token, an unknown number or a token of another person all refuse alike as invite_invalid, and a known token with the wrong number counts one failed try on that invitation; only with both matching does it refuse invite_used (accepted, or the person has a PIN), invite_revoked (revoked, or the person or membership is no longer active) or invite_expired. Neither the invitation's failed tries nor its code hash bound the link.
-- Callers: IdentityRoutines.invite_redeem; the invitation redeem use case.
-- Reads: identity.users, identity.invitations, identity.verification_codes, and what identity.active_organization and identity.invitation_org read. Writes: identity.invitations (failed tries), identity.verification_codes, identity.sign_in_attempts.
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION api.auth_invite_redeem(
  p_request_id text,
  p_token_hash text,
  p_phone text,
  p_device_id text,
  p_code_hash text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_digest text := identity.phone_digest(coalesce(identity.normalize_phone(p_phone), p_phone));
  v_user identity.users;
  v_organization_id uuid;
  v_invitation identity.invitations;
  v_refusal text;
  v_code_id uuid;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  v_user := identity.lock_account(p_phone, p_device_id);
  v_organization_id := identity.invitation_org(p_token_hash);
  IF v_organization_id IS NOT NULL THEN
    PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
    SELECT i.* INTO v_invitation
    FROM identity.invitations AS i
    WHERE i.token_hash = p_token_hash
    FOR UPDATE;
  END IF;

  IF v_invitation.id IS NULL OR v_user.id IS NULL OR v_invitation.user_id <> v_user.id THEN
    IF v_invitation.id IS NOT NULL THEN
      UPDATE identity.invitations SET failed_attempts = failed_attempts + 1 WHERE id = v_invitation.id;
    END IF;
    PERFORM identity.record_attempt('invite_redeem', 'refused', 'invite_invalid', NULL, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "invite_invalid"}');
  END IF;

  IF v_invitation.accepted_at IS NOT NULL OR v_user.pin_hash IS NOT NULL THEN
    v_refusal := 'invite_used';
  ELSIF v_invitation.revoked_at IS NOT NULL THEN
    v_refusal := 'invite_revoked';
  ELSIF p_now > v_invitation.expires_at THEN
    v_refusal := 'invite_expired';
  ELSIF v_user.status <> 'active'
     OR identity.active_organization(v_user.id) IS DISTINCT FROM v_invitation.organization_id THEN
    v_refusal := 'invite_revoked';
  END IF;
  IF v_refusal IS NOT NULL THEN
    PERFORM identity.record_attempt('invite_redeem', 'refused', v_refusal, v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', jsonb_build_object('refusal', v_refusal));
  END IF;

  v_code_id := identity.store_code(v_user.id, 'first_setup', p_device_id, p_code_hash, p_now);
  PERFORM identity.record_attempt(
    'invite_redeem', 'verification_required', NULL, v_user.id, v_digest, p_device_id, p_now
  );
  RETURN identity.outcome('verification_required', jsonb_build_object(
    'purpose', 'first_setup',
    'masked_email', identity.mask_email(v_user.email),
    'code_id', v_code_id
  ));
END;
$$;

