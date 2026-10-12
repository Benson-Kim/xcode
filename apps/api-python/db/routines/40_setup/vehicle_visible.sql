-- setup.vehicle_visible(p_vehicle_id uuid) RETURNS boolean
-- Purpose: whether the current actor can see the vehicle: an all-companies scope, the vehicle's company in their company scope, or the vehicle in their vehicle scope.
-- Callers: the vehicle, report, scheduled-item and investment routines.
-- Reads: setup.fleet_vehicles, and what tenancy.actor_scope reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.vehicle_visible(p_vehicle_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM setup.fleet_vehicles AS f, tenancy.actor_scope() AS s
    WHERE f.organization_id = tenancy.current_organization()
      AND f.id = p_vehicle_id
      AND (s.all_companies OR f.company_id = ANY (s.company_ids) OR f.id = ANY (s.vehicle_ids))
  );
$$;

REVOKE ALL ON FUNCTION setup.vehicle_visible(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.vehicle_visible(uuid) TO xcode_api_executor;
