-- setup.company_visible(p_company_id uuid) RETURNS boolean
-- Purpose: whether the current actor can see the company: an all-companies scope, the company in their company scope, or the company owning a vehicle in their vehicle scope.
-- Callers: the company, vehicle and scheduled-item routines.
-- Reads: setup.psv_companies, setup.fleet_vehicles, and what tenancy.actor_scope reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.company_visible(p_company_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM setup.psv_companies AS c, tenancy.actor_scope() AS s
    WHERE c.organization_id = tenancy.current_organization()
      AND c.id = p_company_id
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
      )
  );
$$;

REVOKE ALL ON FUNCTION setup.company_visible(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.company_visible(uuid) TO xcode_api_executor;
