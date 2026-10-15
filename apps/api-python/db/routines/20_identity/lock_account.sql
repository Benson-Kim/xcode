-- identity.lock_account(p_phone text, p_device_id text) RETURNS identity.users
-- Purpose: find the account of a phone number and lock its row, or, for an unknown or non-normalising number, take the transaction lock on "device:<device id>"; a NULL row then.
-- Callers: the api.auth_* routines that start from a phone number.
-- Reads: identity.users. Writes: nothing (a row lock or an advisory transaction lock).
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.lock_account(p_phone text, p_device_id text)
RETURNS identity.users
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_phone text := identity.normalize_phone(p_phone);
  v_user_id uuid;
  v_user identity.users;
BEGIN
  IF v_phone IS NOT NULL THEN
    SELECT u.id INTO v_user_id FROM identity.users AS u WHERE u.phone_number = v_phone;
  END IF;
  IF v_user_id IS NOT NULL THEN
    v_user := identity.lock_user(v_user_id);
    -- The number may have moved to another person while this call waited for the lock.
    IF v_user.phone_number = v_phone THEN
      RETURN v_user;
    END IF;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('device:' || coalesce(p_device_id, '')));
  RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION identity.lock_account(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.lock_account(text, text) TO xcode_api_executor;
