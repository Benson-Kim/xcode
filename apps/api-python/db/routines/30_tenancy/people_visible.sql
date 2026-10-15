-- tenancy.people_visible(p_viewer uuid) RETURNS SETOF uuid
-- Purpose: the people of the current organization a viewer may see: themselves; everyone for an all-companies viewer; people whose company scope meets the viewer's companies or their vehicles' companies; people whose vehicle scope holds a vehicle the viewer can see.
-- Callers: the people and change-log routines.
-- Reads: tenancy.memberships, tenancy.data_scopes, tenancy.data_scope_companies, tenancy.data_scope_vehicles, setup.fleet_vehicles. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.people_visible(p_viewer uuid)
RETURNS SETOF uuid
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH
  viewer_companies AS (
    SELECT c.company_id
    FROM tenancy.data_scope_companies AS c
    WHERE c.organization_id = tenancy.current_organization() AND c.user_id = p_viewer
  ),
  viewer_vehicles AS (
    SELECT v.vehicle_id
    FROM tenancy.data_scope_vehicles AS v
    WHERE v.organization_id = tenancy.current_organization() AND v.user_id = p_viewer
  ),
  reached_companies AS (
    SELECT viewer_companies.company_id FROM viewer_companies
    UNION
    SELECT f.company_id
    FROM setup.fleet_vehicles AS f
    JOIN viewer_vehicles ON viewer_vehicles.vehicle_id = f.id
    WHERE f.organization_id = tenancy.current_organization()
  ),
  seen_vehicles AS (
    SELECT viewer_vehicles.vehicle_id FROM viewer_vehicles
    UNION
    SELECT f.id
    FROM setup.fleet_vehicles AS f
    JOIN viewer_companies ON viewer_companies.company_id = f.company_id
    WHERE f.organization_id = tenancy.current_organization()
  )
  SELECT m.user_id
  FROM tenancy.memberships AS m
  WHERE m.organization_id = tenancy.current_organization()
    AND (
      m.user_id = p_viewer
      OR EXISTS (
        SELECT 1 FROM tenancy.data_scopes AS s
        WHERE s.organization_id = m.organization_id AND s.user_id = p_viewer AND s.all_companies
      )
      OR EXISTS (
        SELECT 1 FROM tenancy.data_scope_companies AS c
        WHERE c.organization_id = m.organization_id
          AND c.user_id = m.user_id
          AND c.company_id IN (SELECT reached_companies.company_id FROM reached_companies)
      )
      OR EXISTS (
        SELECT 1 FROM tenancy.data_scope_vehicles AS v
        WHERE v.organization_id = m.organization_id
          AND v.user_id = m.user_id
          AND v.vehicle_id IN (SELECT seen_vehicles.vehicle_id FROM seen_vehicles)
      )
    );
$$;

REVOKE ALL ON FUNCTION tenancy.people_visible(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.people_visible(uuid) TO xcode_api_executor;
