-- identity.sign_in_status(p_user identity.users, p_member_active boolean) RETURNS text
-- Purpose: the person's sign-in status, first match wins: blocked (user removed or no active membership), not_signed_in (no PIN), pin_reset_due (a forced reset is pending), locked (either scope at five wrong PINs), else active; the one definition behind the people list, the person's sign-in pane and the sign-in snapshot.
-- Callers: tenancy.sign_in_snapshot, api.ops_account_state, the people routines.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.sign_in_status(p_user identity.users, p_member_active boolean)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_user.status <> 'active' OR NOT coalesce(p_member_active, false) THEN 'blocked'
           WHEN p_user.pin_hash IS NULL THEN 'not_signed_in'
           WHEN p_user.pin_reset_required THEN 'pin_reset_due'
           WHEN p_user.failed_attempts >= identity.pin_tries()
             OR p_user.untrusted_failed_attempts >= identity.pin_tries() THEN 'locked'
           ELSE 'active'
         END;
$$;

REVOKE ALL ON FUNCTION identity.sign_in_status(identity.users, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.sign_in_status(identity.users, boolean) TO xcode_api_executor;
