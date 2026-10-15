-- api.auth_change_pin(p_request_id text, p_user_id uuid, p_device_id text, p_current_ok boolean, p_checked_pin_hash text, p_pin_hash text, p_now timestamptz) RETURNS jsonb
-- Purpose: N07 "Change PIN" for the signed-in person (docs/07-auth.md 12.12): a verdict on a hash replaced since the lookup is a wrong PIN; locked on every device pin_locked; a wrong current PIN counts as a trusted-device wrong PIN (tries left, pin_locked and the change log at five); a right one stores the new hash, clears both lock scopes, logs "PIN changed" and keeps sessions and devices.
-- Callers: IdentityRoutines.change_pin; the change-PIN use case (N07, after session resolution and api.auth_account_lookup_user).
-- Reads: identity.users. Writes: identity.users (PIN, counters, version), identity.sign_in_attempts, and the change log through identity.log_sign_in and identity.count_wrong_pin.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_change_pin(
  p_request_id text,
  p_user_id uuid,
  p_device_id text,
  p_current_ok boolean,
  p_checked_pin_hash text,
  p_pin_hash text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_user identity.users;
  v_digest text;
  v_tries integer := identity.pin_tries();
  v_count integer;
  v_before json;
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  IF p_user_id IS NOT NULL THEN
    v_user := identity.lock_user(p_user_id);
  END IF;
  IF v_user.id IS NULL THEN
    PERFORM pg_advisory_xact_lock(hashtext('device:' || coalesce(p_device_id, '')));
    PERFORM identity.record_attempt(
      'change_pin', 'refused', 'unknown_number', NULL, identity.phone_digest(NULL), p_device_id, p_now
    );
    RETURN identity.outcome('refused', '{"refusal": "unknown_number"}');
  END IF;
  v_digest := identity.phone_digest(v_user.phone_number);
  IF v_user.status <> 'active' OR v_user.pin_hash IS NULL THEN
    PERFORM identity.record_attempt('change_pin', 'refused', 'inactive', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('refused', '{"refusal": "inactive"}');
  END IF;
  IF v_user.failed_attempts >= v_tries THEN
    PERFORM identity.record_attempt('change_pin', 'pin_locked', 'locked', v_user.id, v_digest, p_device_id, p_now);
    RETURN identity.outcome('pin_locked', '{"refusal": "locked"}');
  END IF;

  IF NOT coalesce(p_current_ok AND v_user.pin_hash = p_checked_pin_hash, false) THEN
    v_count := identity.count_wrong_pin(v_user, true, p_now);
    IF v_count >= v_tries THEN
      PERFORM identity.record_attempt('change_pin', 'pin_locked', 'wrong_pin', v_user.id, v_digest, p_device_id, p_now);
      RETURN identity.outcome('pin_locked', '{"refusal": "wrong_pin"}');
    END IF;
    PERFORM identity.record_attempt(
      'change_pin', 'refused', CASE WHEN p_current_ok THEN 'verdict_void' ELSE 'wrong_pin' END,
      v_user.id, v_digest, p_device_id, p_now
    );
    RETURN identity.outcome('refused', jsonb_build_object(
      'refusal', 'wrong_pin', 'tries_left', v_tries - v_count
    ));
  END IF;

  v_before := tenancy.sign_in_snapshot(v_user.id, p_now);
  UPDATE identity.users
  SET pin_hash = p_pin_hash, failed_attempts = 0, untrusted_failed_attempts = 0
  WHERE id = v_user.id;
  PERFORM identity.touch_version(v_user.id);
  PERFORM identity.log_sign_in(v_user.id, v_user.id, ARRAY['PIN changed'], v_before, p_now);
  PERFORM identity.record_attempt('change_pin', 'pin_changed', NULL, v_user.id, v_digest, p_device_id, p_now);
  RETURN identity.outcome('pin_changed');
END;
$$;
