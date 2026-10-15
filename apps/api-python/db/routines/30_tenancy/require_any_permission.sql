-- tenancy.require_any_permission(p_permissions text[]) RETURNS void
-- Purpose: refuse unless the current actor holds at least one of the permissions (endpoints two features share).
-- Callers: tenant routines gated by several permissions (revenue capture, vehicle list, petty cash).
-- Reads: what tenancy.effective_permissions reads. Writes: nothing.
-- Raises: XC403 permission_missing.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.require_any_permission(p_permissions text[])
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF NOT coalesce(
    tenancy.effective_permissions(tenancy.current_organization(), tenancy.current_actor())
      && p_permissions,
    false
  ) THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.require_any_permission(text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.require_any_permission(text[]) TO xcode_api_executor;
