-- api.auth_account_lookup(p_request_id text, p_phone text, p_device_id text, p_device_token_hash text, p_pin_try boolean, p_now timestamptz) RETURNS SETOF api.account_state
-- Purpose: statement one of A01, A02, N02 and of a reset completion (A09, N06): the account state the service needs to verify a PIN (hash, number, counters, forced reset, device trust with the token digest, NULL on the released routes, policy); no row for an unknown or non-normalising number, which a PIN try (p_pin_try: A01, A02, N02) records as unknown_number, the one row per try that an unknown number's simulated lock counts; a reset completion records nothing here.
-- Callers: IdentityRoutines.account_lookup; the sign-in (A01, A02), PIN step (N02) and PIN completion (A09, N06) use cases.
-- Reads: identity.users, identity.trusted_devices, and what identity.policy_for reads. Writes: identity.sign_in_attempts (an unknown or non-normalising number on a PIN try only).
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_account_lookup(
  p_request_id text,
  p_phone text,
  p_device_id text,
  p_device_token_hash text,
  p_pin_try boolean,
  p_now timestamptz
)
RETURNS SETOF api.account_state
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_phone text := identity.normalize_phone(p_phone);
  v_user identity.users;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  IF v_phone IS NOT NULL THEN
    SELECT u.* INTO v_user FROM identity.users AS u WHERE u.phone_number = v_phone;
  END IF;

  IF v_user.id IS NULL THEN
    PERFORM pg_advisory_xact_lock(hashtext('device:' || coalesce(p_device_id, '')));
    IF p_pin_try THEN
      PERFORM identity.record_attempt(
        'sign_in', 'refused', 'unknown_number', NULL,
        identity.phone_digest(coalesce(v_phone, p_phone)), p_device_id, p_now
      );
    END IF;
    RETURN;
  END IF;

  RETURN QUERY
  SELECT v_user.id,
         v_user.status,
         v_user.pin_hash,
         v_user.phone_number,
         v_user.security_version,
         v_user.failed_attempts,
         v_user.untrusted_failed_attempts,
         v_user.pin_reset_required,
         identity.device_trusted(v_user.id, p_device_id, p_device_token_hash, p_now),
         to_jsonb(identity.policy_for(v_user.id));
END;
$$;
