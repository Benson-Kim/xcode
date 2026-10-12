-- tenancy.actor_scope() RETURNS tenancy.scope
-- Purpose: the current actor's data scope rows: the all-companies flag and the company and vehicle ids (empty arrays when none).
-- Callers: the visibility helpers (setup.visible_vehicles, setup.visible_companies) and the access routines.
-- Reads: what tenancy.person_scope reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.actor_scope()
RETURNS tenancy.scope
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN tenancy.person_scope(tenancy.current_actor());
END;
$$;

REVOKE ALL ON FUNCTION tenancy.actor_scope() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.actor_scope() TO xcode_api_executor;
