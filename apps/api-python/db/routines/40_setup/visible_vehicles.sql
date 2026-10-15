-- setup.visible_vehicles() RETURNS SETOF uuid
-- Purpose: the vehicles the current actor can see: every vehicle for an all-companies scope, else the vehicles of their companies and the vehicles they hold themselves.
-- Callers: api.access_my_scope, api.history_list, and the setup and revenue lists.
-- Reads: setup.fleet_vehicles, and what tenancy.actor_scope reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py, tests/db/test_history_routines.py.

CREATE OR REPLACE FUNCTION setup.visible_vehicles()
RETURNS SETOF uuid
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT f.id
  FROM setup.fleet_vehicles AS f, tenancy.actor_scope() AS s
  WHERE f.organization_id = tenancy.current_organization()
    AND (s.all_companies OR f.company_id = ANY (s.company_ids) OR f.id = ANY (s.vehicle_ids));
$$;

REVOKE ALL ON FUNCTION setup.visible_vehicles() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.visible_vehicles() TO xcode_api_executor;
