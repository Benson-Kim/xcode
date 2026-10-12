-- api.auth_account_lookup_user(p_request_id text, p_user_id uuid, p_device_id text, p_now timestamptz) RETURNS SETOF api.account_state
-- Purpose: statement two of a PIN change (N07, after session resolution): the signed-in person's account state with the stored hash and number; device_trusted says whether the session's device row is live; no row when the user is gone.
-- Callers: IdentityRoutines.account_lookup_user; the change-PIN use case (N07).
-- Reads: identity.users, identity.trusted_devices, and what identity.policy_for reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION api.auth_account_lookup_user(
  p_request_id text,
  p_user_id uuid,
  p_device_id text,
  p_now timestamptz
)
RETURNS SETOF api.account_state
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM set_config('xcode.request_id', coalesce(p_request_id, ''), true);
  RETURN QUERY
  SELECT u.id,
         u.status,
         u.pin_hash,
         u.phone_number,
         u.security_version,
         u.failed_attempts,
         u.untrusted_failed_attempts,
         u.pin_reset_required,
         EXISTS (
           SELECT 1
           FROM identity.trusted_devices AS d
           WHERE d.user_id = u.id AND d.device_id = p_device_id AND identity.device_live(d, p_now)
         ),
         to_jsonb(identity.policy_for(u.id))
  FROM identity.users AS u
  WHERE u.id = p_user_id;
END;
$$;
