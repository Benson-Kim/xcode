-- api.auth_withdraw_code(p_request_id text, p_code_id uuid, p_now timestamptz) RETURNS void
-- Purpose: withdraw a code whose mail could not be sent (consumed, expires_at = created_at), so it neither starts the cooldown nor counts toward the caps.
-- Callers: IdentityRoutines.withdraw_code; the sign-in use case (new-device mail failure) and the mail queue (setup and reset mail failures).
-- Reads: identity.verification_codes, identity.users. Writes: identity.verification_codes.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_withdraw_code(
  p_request_id text,
  p_code_id uuid,
  p_now timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_user_id uuid;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  SELECT c.user_id INTO v_user_id FROM identity.verification_codes AS c WHERE c.id = p_code_id;
  IF v_user_id IS NULL THEN
    RETURN;
  END IF;
  PERFORM identity.lock_user(v_user_id);
  -- A code already used or superseded keeps its state.
  UPDATE identity.verification_codes
  SET consumed = true, expires_at = created_at
  WHERE id = p_code_id AND NOT consumed;
END;
$$;
