-- identity.lock_user(p_user_id uuid) RETURNS identity.users
-- Purpose: lock and return the user row (SELECT ... FOR UPDATE), the per-account serialisation point of every auth and operator routine; a NULL row when it does not exist.
-- Callers: identity.lock_account, the api.auth_* routines that work from a user id or a token, the api.ops_* user routines.
-- Reads: identity.users. Writes: nothing (a row lock).
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py, tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.lock_user(p_user_id uuid)
RETURNS identity.users
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT u.* FROM identity.users AS u WHERE u.id = p_user_id FOR UPDATE;
$$;

REVOKE ALL ON FUNCTION identity.lock_user(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.lock_user(uuid) TO xcode_api_executor;
