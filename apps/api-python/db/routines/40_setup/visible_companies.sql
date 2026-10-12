-- setup.visible_companies() RETURNS SETOF uuid
-- Purpose: the companies the current actor can see: every company for an all-companies scope, else their companies and every company that owns a vehicle they hold.
-- Callers: api.access_my_scope, api.history_list, and the setup lists.
-- Reads: setup.psv_companies, setup.fleet_vehicles, and what tenancy.actor_scope reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py, tests/db/test_history_routines.py.

CREATE OR REPLACE FUNCTION setup.visible_companies()
RETURNS SETOF uuid
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT c.id
  FROM setup.psv_companies AS c, tenancy.actor_scope() AS s
  WHERE c.organization_id = tenancy.current_organization()
    AND (
      s.all_companies
      OR c.id = ANY (s.company_ids)
      OR EXISTS (
        SELECT 1
        FROM setup.fleet_vehicles AS f
        WHERE f.organization_id = c.organization_id
          AND f.company_id = c.id
          AND f.id = ANY (s.vehicle_ids)
      )
    );
$$;

REVOKE ALL ON FUNCTION setup.visible_companies() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.visible_companies() TO xcode_api_executor;
