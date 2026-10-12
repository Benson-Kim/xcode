-- api.meta_unassigned_user_count() RETURNS integer
-- Purpose: how many active users have no active membership and so cannot sign in; feeds the startup warning.
-- Callers: OpsRoutines.unassigned_user_count; the API startup summary.
-- Reads: identity.users, tenancy.memberships (through identity.active_organization). Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.

CREATE OR REPLACE FUNCTION api.meta_unassigned_user_count()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT count(*)::integer
  FROM identity.users AS u
  WHERE u.status = 'active' AND identity.active_organization(u.id) IS NULL;
$$;
