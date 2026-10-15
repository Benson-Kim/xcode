-- identity.touch_version(p_user_id uuid) RETURNS bigint
-- Purpose: bump the user row's version once per routine that changed the row (the concurrency token) and return it.
-- Callers: the api.auth_* and api.ops_* routines that change a user row or issue tokens.
-- Reads: identity.users. Writes: identity.users.version.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.touch_version(p_user_id uuid)
RETURNS bigint
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  UPDATE identity.users SET version = version + 1 WHERE id = p_user_id RETURNING version;
$$;

REVOKE ALL ON FUNCTION identity.touch_version(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.touch_version(uuid) TO xcode_api_executor;
