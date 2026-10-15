-- tenancy.require_permission(p_permission text) RETURNS void
-- Purpose: refuse unless the current actor holds the permission; for routines whose permission depends on the request.
-- Callers: tenant routines that pick their permission after entering the organization.
-- Reads: what tenancy.effective_permissions reads. Writes: nothing.
-- Raises: XC403 permission_missing.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.require_permission(p_permission text)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF NOT tenancy.has_permission(p_permission) THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.require_permission(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.require_permission(text) TO xcode_api_executor;
