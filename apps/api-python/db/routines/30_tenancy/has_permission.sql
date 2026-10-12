-- tenancy.has_permission(p_permission text) RETURNS boolean
-- Purpose: whether the current actor holds a permission in the current organization; for shaping results (can_edit, hidden figures).
-- Callers: tenant routines that shape documents by permission; tenancy.require_permission.
-- Reads: what tenancy.effective_permissions reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.has_permission(p_permission text)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(
    p_permission = ANY (
      tenancy.effective_permissions(tenancy.current_organization(), tenancy.current_actor())
    ),
    false
  );
$$;

REVOKE ALL ON FUNCTION tenancy.has_permission(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.has_permission(text) TO xcode_api_executor;
