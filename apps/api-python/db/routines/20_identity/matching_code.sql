-- identity.matching_code(p_user_id uuid, p_purpose text, p_device_id text, p_code_hash text, p_now timestamptz) RETURNS identity.code_check
-- Purpose: check a presented code against the newest unconsumed code of that user, purpose and device: its id on a match (not consumed), and for new_device also when the code is the fixed one of an App Review login (identity.review_accounts), so that code works only while a code the PIN step issued to that device is live; code_expired when there is none, it expired (p_now > expires_at) or it already failed three times; wrong_code after counting a failed try, with the tries left, the third of which consumes (voids) it. For first_setup only, a usable invitation (identity.usable_invitation) is a second source: a device code that matches wins; otherwise the invitation's code matching stores a device code with the same digest (identity.store_code) and answers its id; a wrong code counts a try against the device code, when there is a usable one, and against the invitation, and is voided when the device code fails three times or the invitation reaches identity.invitation_tries(); the tries left are the fewer left on the two.
-- Callers: api.auth_check_code, api.auth_verify_device, api.auth_verify_code, api.auth_complete_pin.
-- Reads: identity.verification_codes, identity.review_accounts, and what identity.usable_invitation reads. Writes: identity.verification_codes (failed_attempts, consumed on the third failure), identity.invitations (failed_attempts).
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py, tests/db/test_invitations.py, tests/db/test_review_account.py.

CREATE OR REPLACE FUNCTION identity.matching_code(
  p_user_id uuid,
  p_purpose text,
  p_device_id text,
  p_code_hash text,
  p_now timestamptz
)
RETURNS identity.code_check
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_code identity.verification_codes;
  v_invitation identity.invitations;
  v_usable boolean;
  v_failed integer;
  v_invitation_failed integer;
  v_voided boolean := false;
  v_tries_left integer;
BEGIN
  SELECT c.* INTO v_code
  FROM identity.verification_codes AS c
  WHERE c.user_id = p_user_id
    AND c.purpose = p_purpose
    AND c.device_id = p_device_id
    AND NOT c.consumed
  ORDER BY c.created_at DESC, c.id DESC
  LIMIT 1
  FOR UPDATE;
  v_usable := FOUND AND p_now <= v_code.expires_at AND v_code.failed_attempts < 3;

  IF p_purpose = 'first_setup' THEN
    v_invitation := identity.usable_invitation(p_user_id, p_now);
  END IF;

  IF v_usable AND p_code_hash IS NOT NULL AND (
    v_code.code_hash = p_code_hash
    OR p_purpose = 'new_device' AND EXISTS (
      SELECT 1 FROM identity.review_accounts AS r
      WHERE r.user_id = p_user_id AND r.code_hash = p_code_hash
    )
  ) THEN
    RETURN ROW(v_code.id, NULL, false, NULL)::identity.code_check;
  END IF;

  IF v_invitation.id IS NOT NULL AND p_code_hash IS NOT NULL
     AND v_invitation.code_hash = p_code_hash THEN
    RETURN ROW(
      identity.store_code(p_user_id, p_purpose, p_device_id, p_code_hash, p_now), NULL, false, NULL
    )::identity.code_check;
  END IF;

  IF NOT v_usable AND v_invitation.id IS NULL THEN
    RETURN ROW(NULL, 'code_expired', false, NULL)::identity.code_check;
  END IF;

  IF v_invitation.id IS NOT NULL THEN
    UPDATE identity.invitations
    SET failed_attempts = failed_attempts + 1
    WHERE id = v_invitation.id
    RETURNING failed_attempts INTO v_invitation_failed;
    v_voided := v_invitation_failed >= identity.invitation_tries();
    v_tries_left := greatest(identity.invitation_tries() - v_invitation_failed, 0);
  END IF;

  IF v_usable THEN
    UPDATE identity.verification_codes
    SET failed_attempts = failed_attempts + 1,
        consumed = failed_attempts + 1 >= 3
    WHERE id = v_code.id
    RETURNING failed_attempts INTO v_failed;
    v_voided := v_voided OR v_failed >= 3;
    v_tries_left := least(coalesce(v_tries_left, 3), greatest(3 - v_failed, 0));
  END IF;

  RETURN ROW(NULL, 'wrong_code', v_voided, v_tries_left)::identity.code_check;
END;
$$;

REVOKE ALL ON FUNCTION identity.matching_code(uuid, text, text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.matching_code(uuid, text, text, text, timestamptz) TO xcode_api_executor;
